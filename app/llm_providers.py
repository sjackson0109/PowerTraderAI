"""
The LLM provider layer: one interface, a connector per provider, and a router that
asks the preferred provider first and the others in order (as the exchange layer,
pt_exchange_abstraction / pt_multi_exchange, does for exchanges).

Connectors: OpenAI, Anthropic, NVIDIA (build.nvidia.com, an OpenAI-compatible API)
and Ollama on this computer (http://localhost:11434 unless set up otherwise). Each
one implements:

* ``list_models()``  the provider's live model list, read with the user's key (or
  from Ollama itself). No model name is written in this code;
* ``health_check(timeout)``  a quick request that costs nothing (the model list, or
  Ollama's version);
* ``complete(prompt, options)``  one answer, with its token usage. Its cost comes
  from the user's prices for that model (Settings > LLM Providers): no provider API
  gives prices, so a paid model's cost is "not known" until a price is set. Ollama
  is free.

Every request goes through ``rate_limits.wait`` under the name ``llm-<provider>``,
at the provider's requests a minute (llm_settings). The HTTP call itself is the
``transport`` argument (``requests_transport`` by default), so tests stand in for
the network, Ollama on localhost included.

The Recommended model
---------------------
``recommended_model(models)`` picks, from the list the provider gave:

1. the models for chat: a model whose id names one other task (``NON_CHAT_TASKS``:
   embeddings, moderation, speech, transcription, audio, realtime, images, video,
   search, reranking, guard and reward models, parsing) is left out;
2. of those, the newest by the provider's own date (its ``created`` time; Ollama:
   when the model was pulled);
3. models with the same date, or with no date, keep the provider's order: the first
   one listed wins.

The user can choose any model the provider lists instead.

Keys are read from pt_secrets (the OS credential store, or the
``POWERTRADER_<PROVIDER>_API_KEY`` environment variables), never from a file.
"""

from __future__ import annotations

import abc
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import llm_settings
from llm_settings import PAID, provider_name

# Words in a model id that name a task other than chat (not model names).
NON_CHAT_TASKS = (
    "embed",
    "moderation",
    "tts",
    "transcribe",
    "speech",
    "audio",
    "realtime",
    "image",
    "video",
    "search",
    "rerank",
    "guard",
    "reward",
    "parse",
)


# --- HTTP -----------------------------------------------------------------------------


@dataclass(frozen=True)
class HttpResponse:
    status: int
    data: Any  # the JSON body, or None
    text: str = ""


Transport = Callable[[str, str, Dict[str, str], Optional[dict], float], HttpResponse]


def requests_transport(
    method: str, url: str, headers: Dict[str, str], body: Optional[dict], timeout: float
) -> HttpResponse:
    """One HTTP request with ``requests``; a network failure raises
    ProviderUnavailable."""
    import requests

    try:
        r = requests.request(method, url, headers=headers, json=body, timeout=timeout)
    except requests.Timeout as exc:
        raise ProviderUnavailable(f"no answer within {timeout:g} s") from exc
    except requests.RequestException as exc:
        raise ProviderUnavailable(f"could not connect ({type(exc).__name__})") from exc
    try:
        data = r.json()
    except ValueError:
        data = None
    return HttpResponse(int(r.status_code), data, (r.text or "")[:500])


# --- results and errors ---------------------------------------------------------------


class LLMError(RuntimeError):
    """A provider could not answer; the message says why (never a key)."""


class NotConfigured(LLMError):
    """The provider has no API key (or is turned off)."""


class ProviderUnavailable(LLMError):
    """No answer: the provider could not be reached, timed out or is down."""


class ProviderRefused(LLMError):
    """The provider answered with an error (a bad key, an unknown model ...)."""


class NoProviderAnswered(LLMError):
    """Every provider in the order was tried; ``attempts`` says what each did."""

    def __init__(self, attempts: Sequence[Tuple[str, str]]):
        self.attempts = list(attempts)
        text = "; ".join(f"{provider_name(p)}: {why}" for p, why in self.attempts)
        super().__init__(f"No LLM provider answered ({text or 'none set up'})")


@dataclass(frozen=True)
class ModelInfo:
    id: str
    created: Optional[float] = None  # epoch seconds, the provider's own date


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class HealthResult:
    ok: bool
    message: str
    elapsed_s: float = 0.0


@dataclass(frozen=True)
class CompletionOptions:
    model: str
    system: str = ""
    max_tokens: int = 1500
    temperature: Optional[float] = None
    timeout: float = 120.0


@dataclass(frozen=True)
class Completion:
    text: str
    provider: str
    model: str
    usage: Usage
    cost_usd: Optional[float]  # None: the model's price is not set
    elapsed_s: float = 0.0


def recommended_model(models: Sequence[ModelInfo]) -> Optional[str]:
    """The Recommended model of a fetched list (see the module docstring)."""
    chat = [
        (i, m)
        for i, m in enumerate(models)
        if m.id and not any(word in m.id.lower() for word in NON_CHAT_TASKS)
    ]
    if not chat:
        return None
    newest = max(
        chat,
        key=lambda im: (
            im[1].created if im[1].created is not None else float("-inf"),
            -im[0],
        ),
    )
    return newest[1].id


def cost_of(price: Optional[Mapping[str, float]], usage: Usage) -> Optional[float]:
    """Dollars for ``usage`` at ``price`` (dollars per million tokens); None when the
    price is not known."""
    if price is None:
        return None
    return (
        usage.input_tokens * float(price["input"])
        + usage.output_tokens * float(price["output"])
    ) / 1_000_000.0


def _iso_time(text: Any) -> Optional[float]:
    if not text:
        return None
    try:
        value = str(text).strip().replace("Z", "+00:00")
        if "." in value:  # Ollama's nanoseconds: datetime takes microseconds
            head, tail = value.split(".", 1)
            digits = "".join(ch for ch in tail if ch.isdigit())
            zone = tail[len(digits) :]
            value = f"{head}.{digits[:6]}{zone}"
        return datetime.fromisoformat(value).timestamp()
    except (ValueError, TypeError):
        return None


# --- connectors -----------------------------------------------------------------------


class LLMProvider(abc.ABC):
    """One provider. ``api_key`` is a str or pt_secrets.Secret (None for Ollama);
    ``price`` maps a model to ``{"input", "output"}`` dollars per million tokens."""

    provider_id = ""
    needs_key = True

    def __init__(
        self,
        api_key: Any = None,
        base_url: Optional[str] = None,
        transport: Optional[Transport] = None,
        requests_per_minute: Optional[float] = None,
        prices: Optional[Mapping[str, Mapping[str, float]]] = None,
    ):
        self._key = api_key
        self.base_url = (
            base_url or llm_settings.DEFAULT_BASE_URLS[self.provider_id]
        ).rstrip("/")
        self.transport = transport or requests_transport
        self.requests_per_minute = (
            requests_per_minute
            or llm_settings.DEFAULT_REQUESTS_PER_MINUTE[self.provider_id]
        )
        self.prices = dict(prices or {})

    @property
    def name(self) -> str:
        return provider_name(self.provider_id)

    @property
    def paid(self) -> bool:
        return self.provider_id in PAID

    def _key_text(self) -> str:
        key = self._key
        reveal = getattr(key, "reveal", None)
        return reveal() if callable(reveal) else str(key or "")

    def configured(self) -> bool:
        return bool(self._key_text()) or not self.needs_key

    def _headers(self) -> Dict[str, str]:
        return {"Content-Type": "application/json"}

    def _request(
        self, method: str, path: str, body: Optional[dict] = None, timeout: float = 30.0
    ) -> Any:
        """The JSON answer of one request, kept to the provider's request limit."""
        if not self.configured():
            raise NotConfigured("no API key")
        import rate_limits

        rate_limits.wait(f"llm-{self.provider_id}", self.requests_per_minute / 60.0)
        try:
            response = self.transport(
                method, self.base_url + path, self._headers(), body, timeout
            )
        except LLMError:
            raise
        except Exception as exc:  # a transport that raised something else
            raise ProviderUnavailable(
                f"could not connect ({type(exc).__name__})"
            ) from exc
        if response.status in (401, 403):
            raise ProviderRefused("the API key was refused")
        if response.status == 429:
            raise ProviderUnavailable("too many requests (the provider's limit)")
        if response.status >= 500:
            raise ProviderUnavailable(
                f"the provider's server failed ({response.status})"
            )
        if response.status >= 400:
            raise ProviderRefused(self._error_text(response))
        if response.data is None:
            raise ProviderRefused("the answer was not JSON")
        return response.data

    @staticmethod
    def _error_text(response: HttpResponse) -> str:
        data = response.data
        message = ""
        if isinstance(data, Mapping):
            error = data.get("error")
            if isinstance(error, Mapping):
                message = str(error.get("message") or "")
            elif error:
                message = str(error)
        return f"error {response.status}" + (f": {message[:200]}" if message else "")

    def health_check(self, timeout: float = 3.0) -> HealthResult:
        """A request that costs nothing; ok when the provider answered in time."""
        start = time.monotonic()
        try:
            self._ping(timeout)
        except LLMError as exc:
            return HealthResult(False, str(exc), time.monotonic() - start)
        elapsed = time.monotonic() - start
        if elapsed > timeout:
            return HealthResult(False, f"no answer within {timeout:g} s", elapsed)
        return HealthResult(True, f"answered in {elapsed:.1f} s", elapsed)

    def _ping(self, timeout: float) -> None:
        self._request("GET", "/models", timeout=timeout)

    def cost(self, model: str, usage: Usage) -> Optional[float]:
        if not self.paid:
            return 0.0
        return cost_of(self.prices.get(model), usage)

    @abc.abstractmethod
    def list_models(self) -> List[ModelInfo]:
        """The provider's models, in the order it lists them."""

    @abc.abstractmethod
    def complete(self, prompt: str, options: CompletionOptions) -> Completion:
        """One answer to ``prompt``."""

    def recommended(
        self, models: Optional[Sequence[ModelInfo]] = None
    ) -> Optional[str]:
        return recommended_model(self.list_models() if models is None else models)


class OpenAICompatibleProvider(LLMProvider):
    """The OpenAI API: ``GET /models`` and ``POST /chat/completions``."""

    max_tokens_field = "max_completion_tokens"

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._key_text()}",
        }

    def list_models(self) -> List[ModelInfo]:
        data = self._request("GET", "/models", timeout=30.0)
        rows = data.get("data") if isinstance(data, Mapping) else None
        out = []
        for row in rows or []:
            if isinstance(row, Mapping) and row.get("id"):
                created = row.get("created")
                out.append(
                    ModelInfo(
                        str(row["id"]),
                        float(created) if isinstance(created, (int, float)) else None,
                    )
                )
        return out

    def complete(self, prompt: str, options: CompletionOptions) -> Completion:
        messages = []
        if options.system:
            messages.append({"role": "system", "content": options.system})
        messages.append({"role": "user", "content": prompt})
        body: Dict[str, Any] = {
            "model": options.model,
            "messages": messages,
            self.max_tokens_field: int(options.max_tokens),
        }
        if options.temperature is not None:
            body["temperature"] = float(options.temperature)
        start = time.monotonic()
        data = self._request("POST", "/chat/completions", body, options.timeout)
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            raise ProviderRefused("the answer had no text") from None
        usage_raw = data.get("usage") or {}
        usage = Usage(
            int(usage_raw.get("prompt_tokens") or 0),
            int(usage_raw.get("completion_tokens") or 0),
        )
        return Completion(
            str(text),
            self.provider_id,
            options.model,  # the model asked for: signals are scored under its id
            usage,
            self.cost(options.model, usage),
            time.monotonic() - start,
        )


class OpenAIProvider(OpenAICompatibleProvider):
    provider_id = "openai"


class NvidiaProvider(OpenAICompatibleProvider):
    """build.nvidia.com: the OpenAI API at integrate.api.nvidia.com."""

    provider_id = "nvidia"
    max_tokens_field = "max_tokens"


class AnthropicProvider(LLMProvider):
    """The Anthropic API: ``GET /models`` and ``POST /messages``."""

    provider_id = "anthropic"
    API_VERSION = "2023-06-01"

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self._key_text(),
            "anthropic-version": self.API_VERSION,
        }

    def _ping(self, timeout: float) -> None:
        self._request("GET", "/models?limit=1", timeout=timeout)

    def list_models(self) -> List[ModelInfo]:
        out: List[ModelInfo] = []
        after = None
        for _page in range(20):  # the API pages its list
            path = "/models?limit=1000" + (f"&after_id={after}" if after else "")
            data = self._request("GET", path, timeout=30.0)
            rows = data.get("data") if isinstance(data, Mapping) else None
            for row in rows or []:
                if isinstance(row, Mapping) and row.get("id"):
                    out.append(
                        ModelInfo(str(row["id"]), _iso_time(row.get("created_at")))
                    )
            if not (
                isinstance(data, Mapping)
                and data.get("has_more")
                and data.get("last_id")
            ):
                break
            after = data["last_id"]
        return out

    def complete(self, prompt: str, options: CompletionOptions) -> Completion:
        body: Dict[str, Any] = {
            "model": options.model,
            "max_tokens": int(options.max_tokens),
            "messages": [{"role": "user", "content": prompt}],
        }
        if options.system:
            body["system"] = options.system
        if options.temperature is not None:
            body["temperature"] = float(options.temperature)
        start = time.monotonic()
        data = self._request("POST", "/messages", body, options.timeout)
        blocks = data.get("content") if isinstance(data, Mapping) else None
        text = "".join(
            str(b.get("text") or "")
            for b in blocks or []
            if isinstance(b, Mapping) and b.get("type") == "text"
        )
        if not blocks:
            raise ProviderRefused("the answer had no text")
        usage_raw = data.get("usage") or {}
        usage = Usage(
            int(usage_raw.get("input_tokens") or 0),
            int(usage_raw.get("output_tokens") or 0),
        )
        return Completion(
            text,
            self.provider_id,
            options.model,  # the model asked for: signals are scored under its id
            usage,
            self.cost(options.model, usage),
            time.monotonic() - start,
        )


class OllamaProvider(LLMProvider):
    """Ollama on this computer (or wherever its base URL points): ``/api/tags``,
    ``/api/version`` and ``/api/chat``. No key, no cost."""

    provider_id = "ollama"
    needs_key = False

    def _ping(self, timeout: float) -> None:
        self._request("GET", "/api/version", timeout=timeout)

    def list_models(self) -> List[ModelInfo]:
        data = self._request("GET", "/api/tags", timeout=10.0)
        rows = data.get("models") if isinstance(data, Mapping) else None
        return [
            ModelInfo(
                str(row.get("name") or row.get("model")),
                _iso_time(row.get("modified_at")),
            )
            for row in rows or []
            if isinstance(row, Mapping) and (row.get("name") or row.get("model"))
        ]

    def complete(self, prompt: str, options: CompletionOptions) -> Completion:
        messages = []
        if options.system:
            messages.append({"role": "system", "content": options.system})
        messages.append({"role": "user", "content": prompt})
        settings: Dict[str, Any] = {"num_predict": int(options.max_tokens)}
        if options.temperature is not None:
            settings["temperature"] = float(options.temperature)
        body = {
            "model": options.model,
            "messages": messages,
            "stream": False,
            "options": settings,
        }
        start = time.monotonic()
        data = self._request("POST", "/api/chat", body, options.timeout)
        message = data.get("message") if isinstance(data, Mapping) else None
        if not isinstance(message, Mapping):
            raise ProviderRefused("the answer had no text")
        usage = Usage(
            int(data.get("prompt_eval_count") or 0), int(data.get("eval_count") or 0)
        )
        return Completion(
            str(message.get("content") or ""),
            self.provider_id,
            options.model,  # the model asked for: signals are scored under its id
            usage,
            0.0,
            time.monotonic() - start,
        )


CONNECTORS = {
    "ollama": OllamaProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "nvidia": NvidiaProvider,
}


# --- the router -----------------------------------------------------------------------


@dataclass
class RoutedCompletion:
    """An answer and who gave it: the provider and model, what the providers asked
    before it did (``attempts``), and whether a paid provider answered in place of
    the preferred one."""

    completion: Completion
    attempts: List[Tuple[str, str]] = field(default_factory=list)
    preferred: str = ""

    @property
    def provider(self) -> str:
        return self.completion.provider

    @property
    def model(self) -> str:
        return self.completion.model

    @property
    def fell_back(self) -> bool:
        return self.provider != self.preferred

    @property
    def paid_fallback(self) -> bool:
        return self.fell_back and self.provider in PAID

    def answered_by(self) -> str:
        return f"{provider_name(self.provider)} ({self.model})"

    def warning(self) -> str:
        """Shown when a paid provider answered in place of the preferred one."""
        if not self.paid_fallback:
            return ""
        why = "; ".join(f"{provider_name(p)}: {r}" for p, r in self.attempts)
        return (
            f"Answered by {provider_name(self.provider)}, a paid provider, in place "
            f"of {provider_name(self.preferred)}" + (f" ({why})" if why else "")
        )


@dataclass(frozen=True)
class ProviderState:
    """What Settings shows for a provider: ``not configured`` (no key),
    ``connected`` or ``error`` (the last test), or ``not tested``."""

    state: str
    message: str = ""


class LLMRouter:
    """Asks the providers in the order of Settings > LLM Providers: the preferred one
    first, then each fallback. Before asking one it checks its health (within
    ``health_timeout_s``) and its monthly spend cap; a provider that fails either,
    or fails to answer, is passed over for the next.

    ``settings`` is the ``llm`` section (a dict), a callable returning it, or None
    (pt_config.json, read fresh on every request); ``secrets`` the pt_secrets module
    (or a stand-in); ``store`` an LLMStore for usage, spend, status and model lists.
    """

    def __init__(
        self,
        settings: Any = None,
        store: Any = None,
        transport: Optional[Transport] = None,
        secrets: Any = None,
        clock: Callable[[], float] = time.time,
    ):
        self._settings = settings
        self._store = store
        self.transport = transport
        self._secrets = secrets
        self.clock = clock
        self._models: Dict[str, List[ModelInfo]] = {}

    # ---- settings, keys and connectors ----

    def settings(self) -> Dict[str, Any]:
        source = self._settings
        if callable(source):
            source = source()
        if isinstance(source, Mapping) and "preferred" in source:
            return llm_settings.normalise(source)
        return llm_settings.read_llm_settings(source)

    @property
    def store(self):
        if self._store is None:
            from llm_store import LLMStore

            self._store = LLMStore()
        return self._store

    def _secret_module(self):
        if self._secrets is None:
            import pt_secrets

            self._secrets = pt_secrets
        return self._secrets

    def api_key(self, provider: str) -> Any:
        if provider not in llm_settings.KEYED:
            return None
        try:
            return self._secret_module().get_secret(provider, "api_key")
        except Exception:
            return None

    def key_source(self, provider: str) -> Optional[str]:
        """``environment``, ``keyring`` or None: where the provider's key comes from."""
        if provider not in llm_settings.KEYED:
            return None
        try:
            return self._secret_module().credential_source(provider)
        except Exception:
            return None

    def connector(
        self, provider: str, settings: Optional[Mapping] = None
    ) -> LLMProvider:
        settings = settings or self.settings()
        cfg = settings["providers"][provider]
        return CONNECTORS[provider](
            api_key=self.api_key(provider),
            base_url=cfg["base_url"],
            transport=self.transport,
            requests_per_minute=cfg["requests_per_minute"],
            prices=(settings.get("prices") or {}).get(provider, {}),
        )

    def order(self, settings: Optional[Mapping] = None) -> List[str]:
        return llm_settings.order(settings or self.settings())

    # ---- models ----

    def list_models(self, provider: str) -> List[ModelInfo]:
        """The provider's live model list (kept for the model pickers)."""
        models = self.connector(provider).list_models()
        self._models[provider] = models
        try:
            self.store.save_models(provider, [m.id for m in models], self.clock())
        except Exception:
            pass
        return models

    def cached_models(self, provider: str) -> List[str]:
        if provider in self._models:
            return [m.id for m in self._models[provider]]
        try:
            saved = self.store.models(provider)
        except Exception:
            saved = None
        return list(saved["ids"]) if saved else []

    def recommended(self, provider: str) -> Optional[str]:
        """The Recommended model from the last list fetched (none fetched: None)."""
        if provider in self._models:
            return recommended_model(self._models[provider])
        return recommended_model([ModelInfo(i) for i in self.cached_models(provider)])

    def model_for(
        self, provider: str, settings: Optional[Mapping] = None
    ) -> Optional[str]:
        """The model the user chose, else the Recommended one (the list is fetched
        when none is kept yet)."""
        settings = settings or self.settings()
        chosen = settings["providers"][provider]["model"]
        if chosen:
            return chosen
        if provider not in self._models and not self.cached_models(provider):
            self.list_models(provider)
        if provider in self._models:
            return recommended_model(self._models[provider])
        return recommended_model([ModelInfo(i) for i in self.cached_models(provider)])

    # ---- status ----

    def test_connection(self, provider: str) -> HealthResult:
        """Settings' Test connection: the health check, kept as the status."""
        settings = self.settings()
        connector = self.connector(provider, settings)
        if not connector.configured():
            result = HealthResult(False, "no API key")
        else:
            result = connector.health_check(settings["health_timeout_s"])
        try:
            self.store.set_status(provider, result.ok, result.message, self.clock())
        except Exception:
            pass
        return result

    def state(self, provider: str) -> ProviderState:
        if provider in llm_settings.KEYED and not self.api_key(provider):
            return ProviderState("not configured", "no API key")
        try:
            last = self.store.status(provider)
        except Exception:
            last = None
        if last is None:
            return ProviderState("not tested")
        return ProviderState("connected" if last["ok"] else "error", last["message"])

    # ---- spend ----

    def cap_problem(
        self, provider: str, model: str, settings: Mapping
    ) -> Optional[str]:
        """Why the monthly spend cap stops ``provider`` now, or None."""
        cap = settings["providers"][provider]["monthly_cap_usd"]
        if cap is None or provider not in PAID:
            return None
        if llm_settings.price_of(settings, provider, model) is None:
            return "a monthly spend cap is set but this model's price is not"
        spent = self.store.month_spend(provider, self.clock())
        if spent >= cap:
            return f"monthly spend cap reached (${spent:,.2f} of ${cap:,.2f})"
        return None

    # ---- answering ----

    def complete(
        self,
        prompt: str,
        purpose: str = "",
        system: str = "",
        max_tokens: int = 1500,
        temperature: Optional[float] = None,
        settings: Optional[Mapping] = None,
    ) -> RoutedCompletion:
        """An answer from the first provider in the order that can give one; raises
        NoProviderAnswered when none could."""
        settings = settings or self.settings()
        attempts: List[Tuple[str, str]] = []
        order = self.order(settings)
        for provider in order:
            cfg = settings["providers"][provider]
            if not cfg["enabled"]:
                attempts.append((provider, "turned off"))
                continue
            connector = self.connector(provider, settings)
            if not connector.configured():
                attempts.append((provider, "no API key"))
                continue
            health = connector.health_check(settings["health_timeout_s"])
            if not health.ok:
                attempts.append((provider, health.message))
                continue
            try:
                model = self.model_for(provider, settings)
            except LLMError as exc:
                attempts.append((provider, f"no model list ({exc})"))
                continue
            if not model:
                attempts.append((provider, "no model to use"))
                continue
            problem = self.cap_problem(provider, model, settings)
            if problem:
                attempts.append((provider, problem))
                continue
            options = CompletionOptions(
                model=model,
                system=system,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=settings["request_timeout_s"],
            )
            try:
                completion = connector.complete(prompt, options)
            except LLMError as exc:
                attempts.append((provider, str(exc)))
                continue
            try:
                self.store.record_usage(
                    provider,
                    completion.model,
                    completion.usage.input_tokens,
                    completion.usage.output_tokens,
                    completion.cost_usd,
                    purpose,
                    self.clock(),
                )
            except Exception:
                pass
            return RoutedCompletion(completion, attempts, order[0] if order else "")
        raise NoProviderAnswered(attempts)
