"""
LLM settings: Settings > LLM Providers, kept in ``pt_config.json``'s ``llm`` section.

The hub (the LLM Research tab and its Settings window) and the trader (the entry hook,
``llm_gate``) read the same file, so every process sees the same choices. API keys are
never here: they are in the OS credential store (``pt_secrets``), or in
``POWERTRADER_<PROVIDER>_API_KEY`` environment variables.

Keys (all under ``llm.``)
-------------------------
``preferred``             the provider asked first (``ollama``: local and free)
``fallbacks``             the providers asked next, in order (none by default, so no
                          paid provider is used unless the user lists it)
``health_timeout_s``      how long a provider's health check may take before the next
                          provider is asked (3 s)
``request_timeout_s``     how long one answer may take (120 s)
``providers.<id>``        ``enabled``, ``base_url``, ``model`` ("" = the Recommended
                          model), ``requests_per_minute``, ``monthly_cap_usd`` (None:
                          no cap)
``prices.<id>.<model>``   ``{"input": $, "output": $}`` per million tokens, as the user
                          enters them (no provider API gives prices)
``signal_mode``           ``off`` | ``log_only`` | ``confirm`` | ``veto`` |
                          ``confirm_and_veto`` (``log_only``)
``signal_timeout_s``      how long the trader waits for a signal at an entry (10 s)
``signal_reuse_minutes``  a coin's signal younger than this is used again (15)
``signal_use``            ``{"<provider>|<model>": true}``: the provider/models whose
                          signals may confirm or veto an entry (none until ticked)
``auto_refresh_minutes``  Market Analysis' auto-refresh interval (10)

A value that is missing or not usable takes its default; an unknown signal mode is
``log_only``, which never changes a trade.
"""

from __future__ import annotations

import copy
import math
from typing import Any, Dict, List, Mapping, Optional

SECTION = "llm"

# Display order in Settings; the ids are the pt_secrets entry names.
PROVIDERS = ("ollama", "openai", "anthropic", "nvidia")
PROVIDER_NAMES = {
    "ollama": "Ollama",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "nvidia": "NVIDIA",
}
# A provider that charges per token (Ollama runs on this computer, for nothing)
PAID = frozenset({"openai", "anthropic", "nvidia"})
# Providers that need an API key (pt_secrets.LLM_KEY_PROVIDERS)
KEYED = frozenset({"openai", "anthropic", "nvidia"})
# Providers whose base URL the user sets up (a local Ollama, NVIDIA's own endpoint)
BASE_URL_SET_UP = frozenset({"ollama", "nvidia"})

DEFAULT_BASE_URLS = {
    "ollama": "http://localhost:11434",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "nvidia": "https://integrate.api.nvidia.com/v1",
}
# Requests a minute each provider is kept to (rate_limits), unless the user sets
# another. Anthropic's lowest tier allows 50 a minute and NVIDIA's API catalogue 40;
# OpenAI's limit depends on the account's tier, so 60 is a cautious figure; a local
# Ollama answers one request at a time anyway.
DEFAULT_REQUESTS_PER_MINUTE = {
    "ollama": 60.0,
    "openai": 60.0,
    "anthropic": 50.0,
    "nvidia": 40.0,
}

SIGNAL_MODES = ("off", "log_only", "confirm", "veto", "confirm_and_veto")
DEFAULT_SIGNAL_MODE = "log_only"
SIGNAL_MODE_NAMES = {
    "off": "Off",
    "log_only": "Log only",
    "confirm": "Confirm entries",
    "veto": "Veto entries",
    "confirm_and_veto": "Confirm and veto entries",
}

DEFAULTS: Dict[str, Any] = {
    "preferred": "ollama",
    "fallbacks": [],
    "health_timeout_s": 3.0,
    "request_timeout_s": 120.0,
    "providers": {},
    "prices": {},
    "signal_mode": DEFAULT_SIGNAL_MODE,
    "signal_timeout_s": 10.0,
    "signal_reuse_minutes": 15.0,
    "signal_use": {},
    "auto_refresh_minutes": 10,
}
BOUNDS = {
    "health_timeout_s": (0.5, 30.0),
    "request_timeout_s": (5.0, 600.0),
    "signal_timeout_s": (1.0, 60.0),
    "signal_reuse_minutes": (0.0, 1440.0),
    "auto_refresh_minutes": (1, 1440),
    "requests_per_minute": (1.0, 10000.0),
    "monthly_cap_usd": (0.0, 100000.0),
    "price": (0.0, 10000.0),
}


def provider_name(provider: str) -> str:
    """The name a provider goes by on screen ("openai" -> "OpenAI")."""
    key = str(provider or "").strip().lower()
    return PROVIDER_NAMES.get(key) or key.title()


def provider_id(name: str) -> str:
    """The id behind a name ``provider_name`` gives; an id comes back as it is."""
    text = str(name or "").strip().lower()
    for key, shown in PROVIDER_NAMES.items():
        if shown.lower() == text:
            return key
    return text


def use_key(provider: str, model: str) -> str:
    """The ``signal_use`` key of a provider/model."""
    return f"{provider}|{model}"


def _number(value: Any, bounds, default):
    if isinstance(value, bool):
        return default
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(number):
        return default
    low, high = bounds
    return min(high, max(low, number))


def _optional_number(value: Any, bounds) -> Optional[float]:
    if value in (None, ""):
        return None
    number = _number(value, bounds, None)
    return None if number is None else float(number)


def default_provider(provider: str) -> Dict[str, Any]:
    return {
        "enabled": True,
        "base_url": DEFAULT_BASE_URLS[provider],
        "model": "",
        "requests_per_minute": DEFAULT_REQUESTS_PER_MINUTE[provider],
        "monthly_cap_usd": None,
    }


def _provider(provider: str, raw: Any) -> Dict[str, Any]:
    out = default_provider(provider)
    if not isinstance(raw, Mapping):
        return out
    if isinstance(raw.get("enabled"), bool):
        out["enabled"] = raw["enabled"]
    url = str(raw.get("base_url") or "").strip().rstrip("/")
    if url.startswith(("http://", "https://")):
        out["base_url"] = url
    out["model"] = str(raw.get("model") or "").strip()
    out["requests_per_minute"] = float(
        _number(
            raw.get("requests_per_minute"),
            BOUNDS["requests_per_minute"],
            out["requests_per_minute"],
        )
    )
    out["monthly_cap_usd"] = _optional_number(
        raw.get("monthly_cap_usd"), BOUNDS["monthly_cap_usd"]
    )
    return out


def _prices(raw: Any) -> Dict[str, Dict[str, Dict[str, float]]]:
    out: Dict[str, Dict[str, Dict[str, float]]] = {}
    if not isinstance(raw, Mapping):
        return out
    for provider, models in raw.items():
        if provider not in PROVIDERS or not isinstance(models, Mapping):
            continue
        for model, price in models.items():
            if not isinstance(price, Mapping) or not str(model).strip():
                continue
            pin = _optional_number(price.get("input"), BOUNDS["price"])
            pout = _optional_number(price.get("output"), BOUNDS["price"])
            if pin is None or pout is None:
                continue
            out.setdefault(provider, {})[str(model).strip()] = {
                "input": pin,
                "output": pout,
            }
    return out


def normalise(raw: Any) -> Dict[str, Any]:
    """A complete, usable ``llm`` section from whatever was saved."""
    raw = raw if isinstance(raw, Mapping) else {}
    out = copy.deepcopy(DEFAULTS)
    preferred = str(raw.get("preferred") or "").strip().lower()
    out["preferred"] = preferred if preferred in PROVIDERS else DEFAULTS["preferred"]
    fallbacks: List[str] = []
    for p in raw.get("fallbacks") or []:
        p = str(p or "").strip().lower()
        if p in PROVIDERS and p != out["preferred"] and p not in fallbacks:
            fallbacks.append(p)
    out["fallbacks"] = fallbacks
    for key in (
        "health_timeout_s",
        "request_timeout_s",
        "signal_timeout_s",
        "signal_reuse_minutes",
    ):
        out[key] = float(_number(raw.get(key), BOUNDS[key], DEFAULTS[key]))
    out["auto_refresh_minutes"] = int(
        _number(
            raw.get("auto_refresh_minutes"),
            BOUNDS["auto_refresh_minutes"],
            DEFAULTS["auto_refresh_minutes"],
        )
    )
    providers = (
        raw.get("providers") if isinstance(raw.get("providers"), Mapping) else {}
    )
    out["providers"] = {p: _provider(p, providers.get(p)) for p in PROVIDERS}
    out["prices"] = _prices(raw.get("prices"))
    mode = str(raw.get("signal_mode") or "").strip().lower()
    out["signal_mode"] = mode if mode in SIGNAL_MODES else DEFAULT_SIGNAL_MODE
    use = raw.get("signal_use") if isinstance(raw.get("signal_use"), Mapping) else {}
    out["signal_use"] = {
        str(k): True
        for k, v in use.items()
        if v is True and "|" in str(k) and str(k).split("|", 1)[0] in PROVIDERS
    }
    return out


def order(settings: Mapping[str, Any]) -> List[str]:
    """The providers in the order they are asked: the preferred, then the fallbacks."""
    return [settings["preferred"]] + [
        p for p in settings["fallbacks"] if p != settings["preferred"]
    ]


def price_of(
    settings: Mapping[str, Any], provider: str, model: str
) -> Optional[Dict[str, float]]:
    """``{"input", "output"}`` dollars per million tokens: 0 for Ollama, the user's
    figures for a paid provider's model, else None (not known)."""
    if provider not in PAID:
        return {"input": 0.0, "output": 0.0}
    return (settings.get("prices") or {}).get(provider, {}).get(model)


def read_llm_settings(source: Any = None) -> Dict[str, Any]:
    """The ``llm`` section of ``source``: None reads pt_config.json fresh; a mapping,
    path or SettingsManager is read as trading_mode reads them."""
    from trading_mode import lookup_setting, settings_mapping

    try:
        raw = lookup_setting(settings_mapping(source), SECTION)
    except Exception:
        raw = None
    return normalise(raw)


def save_llm_settings(values: Mapping[str, Any], manager: Any = None) -> bool:
    """Write the ``llm`` section (checked first) to pt_config.json."""
    if manager is None:
        from pt_settings_manager import SettingsManager

        manager = SettingsManager()
    return bool(manager.set_section(SECTION, normalise(values)))
