"""The LLM provider layer (llm_providers, llm_settings): four connectors behind one
interface, keys from the OS credential store, per-provider request limits, the
Recommended model rule, and the router's preferred-then-fallback order.

No network: every request goes to a fake transport (Ollama on localhost included),
under the isolation guard (app/conftest.py).
"""

import json
import os
import sys

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import llm_providers as lp  # noqa: E402
import llm_settings  # noqa: E402
import pt_secrets  # noqa: E402
from llm_store import LLMStore  # noqa: E402


class FakeHttp:
    """Answers requests from ``routes``: {(method, url prefix): response or
    exception}; records every request (method, url, headers, body, timeout)."""

    def __init__(self, routes=None):
        self.routes = dict(routes or {})
        self.requests = []

    def __call__(self, method, url, headers, body, timeout):
        self.requests.append((method, url, dict(headers), body, timeout))
        for (m, prefix), answer in sorted(
            self.routes.items(), key=lambda kv: -len(kv[0][1])
        ):
            if m == method and url.startswith(prefix):
                if isinstance(answer, Exception):
                    raise answer
                if callable(answer):
                    return answer(method, url, headers, body, timeout)
                status, data = answer
                return lp.HttpResponse(status, data, json.dumps(data))
        raise lp.ProviderUnavailable("could not connect (no route)")


OLLAMA = "http://localhost:11434"
OPENAI = "https://api.openai.com/v1"
ANTHROPIC = "https://api.anthropic.com/v1"
NVIDIA = "https://integrate.api.nvidia.com/v1"


def openai_models(*rows):
    return (200, {"object": "list", "data": [dict(id=i, created=c) for i, c in rows]})


def chat_answer(text, prompt_tokens=100, completion_tokens=50):
    return (
        200,
        {
            "choices": [{"message": {"role": "assistant", "content": text}}],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            },
        },
    )


# --- settings ---------------------------------------------------------------------------


def test_settings_defaults_are_local_first_and_log_only():
    s = llm_settings.normalise(None)
    assert s["preferred"] == "ollama" and s["fallbacks"] == []
    assert s["signal_mode"] == "log_only"
    assert s["providers"]["ollama"]["base_url"] == OLLAMA
    assert set(s["providers"]) == set(llm_settings.PROVIDERS)
    assert s["signal_use"] == {}


def test_settings_keep_what_is_usable_and_default_the_rest():
    s = llm_settings.normalise(
        {
            "preferred": "openai",
            "fallbacks": ["openai", "anthropic", "nope", "anthropic", "ollama"],
            "health_timeout_s": "abc",
            "signal_timeout_s": 999,
            "signal_mode": "yolo",
            "providers": {
                "openai": {"monthly_cap_usd": "5", "model": " m1 ", "base_url": "x"},
            },
            "prices": {"openai": {"m1": {"input": 2, "output": "8"}, "m2": {}}},
            "signal_use": {"openai|m1": True, "bad": True, "ollama|x": "yes"},
        }
    )
    assert s["fallbacks"] == ["anthropic", "ollama"]
    assert s["health_timeout_s"] == 3.0 and s["signal_timeout_s"] == 60.0
    assert s["signal_mode"] == "log_only"  # an unknown mode never trades
    assert s["providers"]["openai"]["monthly_cap_usd"] == 5.0
    assert s["providers"]["openai"]["model"] == "m1"
    assert s["providers"]["openai"]["base_url"] == OPENAI  # not a URL: the default
    assert s["prices"] == {"openai": {"m1": {"input": 2.0, "output": 8.0}}}
    assert s["signal_use"] == {"openai|m1": True}
    assert llm_settings.order(s) == ["openai", "anthropic", "ollama"]


def test_settings_are_saved_in_pt_config_without_any_key():
    import pt_paths
    from pt_settings_manager import SettingsManager

    values = llm_settings.normalise({"preferred": "anthropic"})
    values["providers"]["anthropic"]["api_key"] = "sk-must-not-be-written"
    assert llm_settings.save_llm_settings(values, SettingsManager())
    with open(pt_paths.settings_file(), encoding="utf-8") as f:
        text = f.read()
    assert "sk-must-not-be-written" not in text
    assert json.loads(text)["llm"]["preferred"] == "anthropic"
    assert llm_settings.read_llm_settings()["preferred"] == "anthropic"


# --- keys ---------------------------------------------------------------------------------


def test_a_provider_key_is_one_field_in_the_os_credential_store(memory_keyring):
    assert [f.name for f in pt_secrets.secret_fields("openai")] == ["api_key"]
    assert pt_secrets.env_var_names("anthropic") == ("POWERTRADER_ANTHROPIC_API_KEY",)
    assert pt_secrets.env_var_names("nvidia") == ("POWERTRADER_NVIDIA_API_KEY",)
    pt_secrets.set_secret("openai", "api_key", "sk-test")
    assert memory_keyring.entries == {
        (pt_secrets.SERVICE_NAME, "openai:api_key"): "sk-test"
    }
    router = lp.LLMRouter(settings=llm_settings.normalise({}))
    assert router.api_key("openai").reveal() == "sk-test"
    assert router.key_source("openai") == pt_secrets.SOURCE_KEYRING
    assert router.api_key("ollama") is None  # a local Ollama has no key


def test_an_environment_variable_key_wins(memory_keyring, monkeypatch):
    pt_secrets.set_secret("openai", "api_key", "from-keyring")
    monkeypatch.setenv("POWERTRADER_OPENAI_API_KEY", "from-env")
    router = lp.LLMRouter(settings=llm_settings.normalise({}))
    assert router.api_key("openai").reveal() == "from-env"
    assert router.key_source("openai") == pt_secrets.SOURCE_ENV


# --- connectors ---------------------------------------------------------------------------


def test_openai_lists_its_models_and_answers_with_usage_and_cost():
    http = FakeHttp(
        {
            ("GET", OPENAI + "/models"): openai_models(("a", 1), ("b", 2)),
            ("POST", OPENAI + "/chat/completions"): chat_answer("hi", 1000, 500),
        }
    )
    p = lp.OpenAIProvider(
        api_key="sk-1", transport=http, prices={"b": {"input": 2.0, "output": 10.0}}
    )
    assert [m.id for m in p.list_models()] == ["a", "b"]
    answer = p.complete("Say hi", lp.CompletionOptions(model="b", system="sys"))
    assert answer.text == "hi" and answer.model == "b" and answer.provider == "openai"
    assert answer.usage == lp.Usage(1000, 500)
    assert answer.cost_usd == pytest.approx((1000 * 2.0 + 500 * 10.0) / 1e6)
    method, url, headers, body, _ = http.requests[-1]
    assert headers["Authorization"] == "Bearer sk-1"
    assert body["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "Say hi"},
    ]
    assert body["max_completion_tokens"] == 1500 and "temperature" not in body
    # no price for a model: its cost is not known
    assert p.complete("x", lp.CompletionOptions(model="a")).cost_usd is None


def test_nvidia_is_the_openai_api_at_its_own_url():
    http = FakeHttp(
        {
            ("GET", NVIDIA + "/models"): openai_models(("org/m", 7)),
            ("POST", NVIDIA + "/chat/completions"): chat_answer("ok"),
        }
    )
    p = lp.NvidiaProvider(api_key="nv", transport=http)
    assert [m.id for m in p.list_models()] == ["org/m"]
    p.complete("q", lp.CompletionOptions(model="org/m", max_tokens=99))
    assert http.requests[-1][3]["max_tokens"] == 99
    assert p.paid


def test_anthropic_pages_its_model_list_and_answers():
    pages = {
        None: {
            "data": [{"id": "m-new", "created_at": "2026-02-01T00:00:00Z"}],
            "has_more": True,
            "last_id": "m-new",
        },
        "m-new": {
            "data": [{"id": "m-old", "created_at": "2025-01-01T00:00:00Z"}],
            "has_more": False,
        },
    }

    def models(method, url, headers, body, timeout):
        after = url.split("after_id=")[1] if "after_id=" in url else None
        return lp.HttpResponse(200, pages[after])

    http = FakeHttp(
        {
            ("GET", ANTHROPIC + "/models"): models,
            ("POST", ANTHROPIC + "/messages"): (
                200,
                {
                    "content": [{"type": "text", "text": "## Hello"}],
                    "usage": {"input_tokens": 12, "output_tokens": 3},
                },
            ),
        }
    )
    p = lp.AnthropicProvider(api_key="ak", transport=http)
    listed = p.list_models()
    assert [m.id for m in listed] == ["m-new", "m-old"]
    assert lp.recommended_model(listed) == "m-new"
    answer = p.complete("q", lp.CompletionOptions(model="m-new", system="s"))
    assert answer.text == "## Hello" and answer.usage == lp.Usage(12, 3)
    _, _, headers, body, _ = http.requests[-1]
    assert headers["x-api-key"] == "ak" and headers["anthropic-version"]
    assert body["system"] == "s" and body["messages"][0]["content"] == "q"


def test_ollama_is_local_free_and_needs_no_key():
    http = FakeHttp(
        {
            ("GET", OLLAMA + "/api/tags"): (
                200,
                {
                    "models": [
                        {
                            "name": "old:1b",
                            "modified_at": "2025-05-01T10:00:00.1234567+02:00",
                        },
                        {"name": "new:7b", "modified_at": "2026-01-01T10:00:00Z"},
                        {
                            "name": "some-embed-text",
                            "modified_at": "2026-06-01T10:00:00Z",
                        },
                    ]
                },
            ),
            ("GET", OLLAMA + "/api/version"): (200, {"version": "0.9"}),
            ("POST", OLLAMA + "/api/chat"): (
                200,
                {
                    "message": {"content": "local"},
                    "prompt_eval_count": 9,
                    "eval_count": 4,
                },
            ),
        }
    )
    p = lp.OllamaProvider(transport=http)
    assert p.configured() and not p.paid
    assert p.recommended() == "new:7b"  # newest pulled, embeddings left out
    assert p.health_check(2.0).ok
    answer = p.complete("q", lp.CompletionOptions(model="new:7b"))
    assert (answer.text, answer.cost_usd, answer.usage) == (
        "local",
        0.0,
        lp.Usage(9, 4),
    )
    assert http.requests[-1][3]["stream"] is False
    assert all("Authorization" not in r[2] for r in http.requests)


def test_errors_say_what_happened_and_never_show_the_key():
    http = FakeHttp(
        {
            ("GET", OPENAI + "/models"): (
                401,
                {"error": {"message": "bad key sk-secret"}},
            ),
            ("POST", OPENAI + "/chat/completions"): (500, {}),
        }
    )
    p = lp.OpenAIProvider(api_key="sk-secret", transport=http)
    with pytest.raises(lp.ProviderRefused) as refused:
        p.list_models()
    assert "sk-secret" not in str(refused.value)
    with pytest.raises(lp.ProviderUnavailable):
        p.complete("q", lp.CompletionOptions(model="m"))
    with pytest.raises(lp.NotConfigured):
        lp.OpenAIProvider(api_key="", transport=http).list_models()
    down = lp.OllamaProvider(transport=FakeHttp())
    health = down.health_check(1.0)
    assert not health.ok and "could not connect" in health.message


def test_every_request_is_kept_to_the_providers_limit(monkeypatch):
    import rate_limits

    waits = []
    monkeypatch.setattr(
        rate_limits, "wait", lambda name, rate: waits.append((name, rate))
    )
    http = FakeHttp({("GET", NVIDIA + "/models"): openai_models(("m", 1))})
    lp.NvidiaProvider(api_key="k", transport=http, requests_per_minute=30).list_models()
    assert waits == [("llm-nvidia", 0.5)]


# --- the Recommended model ----------------------------------------------------------------


def test_the_recommended_model_is_the_newest_chat_model():
    models = [
        lp.ModelInfo("text-embedding-x", 900),
        lp.ModelInfo("chat-a", 100),
        lp.ModelInfo("chat-b", 300),
        lp.ModelInfo("x-realtime-preview", 999),
        lp.ModelInfo("x-tts", 999),
        lp.ModelInfo("chat-c", 300),
    ]
    assert lp.recommended_model(models) == "chat-b"  # same date: the first listed
    undated = [lp.ModelInfo("first"), lp.ModelInfo("second")]
    assert lp.recommended_model(undated) == "first"
    assert lp.recommended_model([lp.ModelInfo("some-rerank")]) is None
    assert lp.recommended_model([]) is None


# --- the router ---------------------------------------------------------------------------


def router_with(http, store, **settings):
    base = {"preferred": "ollama", "fallbacks": ["openai", "anthropic"]}
    base.update(settings)
    return lp.LLMRouter(settings=base, store=store, transport=http)


@pytest.fixture
def store(tmp_path):
    return LLMStore(str(tmp_path / "llm.db"))


def test_with_ollama_stopped_the_next_provider_answers_with_a_warning(
    memory_keyring, store
):
    pt_secrets.set_secret("openai", "api_key", "sk-1")
    http = FakeHttp(
        {
            ("GET", OPENAI + "/models"): openai_models(("gpt-like", 5)),
            ("POST", OPENAI + "/chat/completions"): chat_answer("from openai", 10, 5),
        }
    )  # nothing answers on localhost: Ollama is stopped
    router = router_with(
        http, store, prices={"openai": {"gpt-like": {"input": 1, "output": 2}}}
    )
    answer = router.complete("q", purpose="analysis")
    assert (answer.provider, answer.model) == ("openai", "gpt-like")
    assert answer.fell_back and answer.paid_fallback
    assert answer.attempts[0][0] == "ollama"
    assert "Answered by OpenAI, a paid provider, in place of Ollama" in answer.warning()
    assert store.month_spend("openai") == pytest.approx((10 * 1 + 5 * 2) / 1e6)
    # the health check came before the request
    urls = [r[1] for r in http.requests]
    assert urls.index(OPENAI + "/models") < urls.index(OPENAI + "/chat/completions")


def test_the_preferred_provider_answers_when_it_is_up(store):
    http = FakeHttp(
        {
            ("GET", OLLAMA + "/api/version"): (200, {}),
            ("GET", OLLAMA + "/api/tags"): (200, {"models": [{"name": "m:1"}]}),
            ("POST", OLLAMA + "/api/chat"): (200, {"message": {"content": "local"}}),
        }
    )
    answer = router_with(http, store).complete("q")
    assert answer.provider == "ollama" and not answer.fell_back
    assert answer.warning() == ""


def test_a_provider_without_a_key_or_over_its_cap_is_passed_over(memory_keyring, store):
    pt_secrets.set_secret("anthropic", "api_key", "ak")
    store.record_usage("anthropic", "m", 1, 1, 9.0)
    http = FakeHttp(
        {
            ("GET", ANTHROPIC + "/models"): (200, {"data": [{"id": "m"}]}),
        }
    )
    router = router_with(
        http,
        store,
        providers={"anthropic": {"monthly_cap_usd": 5, "model": "m"}},
        prices={"anthropic": {"m": {"input": 1, "output": 1}}},
    )
    with pytest.raises(lp.NoProviderAnswered) as none:
        router.complete("q")
    reasons = dict(none.value.attempts)
    assert reasons["openai"] == "no API key"
    assert reasons["anthropic"].startswith("monthly spend cap reached")
    assert "Ollama" in str(none.value)
    # a cap with no price for the model: it cannot be kept, so the provider is skipped
    router = router_with(http, store, providers={"anthropic": {"monthly_cap_usd": 5}})
    router._models["anthropic"] = [lp.ModelInfo("m")]
    assert router.cap_problem("anthropic", "m", router.settings()) == (
        "a monthly spend cap is set but this model's price is not"
    )


def test_the_users_model_choice_wins_over_the_recommended_one(memory_keyring, store):
    pt_secrets.set_secret("openai", "api_key", "sk")
    http = FakeHttp({("GET", OPENAI + "/models"): openai_models(("a", 1), ("b", 2))})
    router = router_with(http, store)
    assert router.model_for("openai") == "b"
    assert store.models("openai")["ids"] == ["a", "b"]  # kept for the pickers
    chosen = router_with(http, store, providers={"openai": {"model": "a"}})
    assert chosen.model_for("openai") == "a"


def test_provider_states_for_settings(memory_keyring, store):
    http = FakeHttp({("GET", OLLAMA + "/api/version"): (200, {})})
    router = router_with(http, store)
    assert router.state("openai").state == "not configured"
    assert router.state("ollama").state == "not tested"
    assert router.test_connection("ollama").ok
    assert router.state("ollama").state == "connected"
    pt_secrets.set_secret("nvidia", "api_key", "k")
    assert not router.test_connection("nvidia").ok  # no route: not reachable
    assert router.state("nvidia").state == "error"
