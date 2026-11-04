"""Stand-ins for the LLM tests: a fake HTTP transport (no request leaves the test,
Ollama on localhost included) and canned provider answers."""

import json

import llm_providers as lp

OLLAMA = "http://localhost:11434"
OPENAI = "https://api.openai.com/v1"
ANTHROPIC = "https://api.anthropic.com/v1"
NVIDIA = "https://integrate.api.nvidia.com/v1"


class FakeHttp:
    """Answers requests from ``routes``: {(method, url prefix): (status, data), an
    exception, or a callable(method, url, headers, body, timeout)}; the longest
    prefix wins. Records every request (method, url, headers, body, timeout). With
    no route a request fails as a stopped server does."""

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

    def posts(self):
        return [r for r in self.requests if r[0] == "POST"]


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


def ollama_routes(answer="", models=("local:7b",)):
    """A running Ollama with ``models`` that answers every chat with ``answer``
    (a str, or a callable(prompt) -> str)."""

    def chat(method, url, headers, body, timeout):
        prompt = body["messages"][-1]["content"]
        text = answer(prompt) if callable(answer) else answer
        return lp.HttpResponse(
            200,
            {"message": {"content": text}, "prompt_eval_count": 50, "eval_count": 20},
        )

    return {
        ("GET", OLLAMA + "/api/version"): (200, {"version": "test"}),
        ("GET", OLLAMA + "/api/tags"): (200, {"models": [{"name": m} for m in models]}),
        ("POST", OLLAMA + "/api/chat"): chat,
    }


# --- the exchange layer and the research engine ---------------------------------------

HOUR_MS = 3600 * 1000


class FakeLayer:
    """Stands in for pt_multi_exchange.market_exchanges(): one connected exchange
    (a real connector, built offline, for its symbol format) serving hourly candles
    from ``price(coin, open_ms)`` (a gentle rise from 100 by default)."""

    def __init__(self, exchange="coinbase", price=None):
        import types

        import pt_exchanges  # noqa: F401  (registers the connectors)
        from pt_exchange_abstraction import ExchangeFactory, ExchangeType

        self.name = exchange
        self.connector = ExchangeFactory.get_exchange(
            ExchangeType(exchange), api_key="", api_secret=""
        )
        self.exchange_manager = types.SimpleNamespace(
            exchanges={ExchangeType(exchange): self.connector},
            exchange_names=lambda: [exchange],
        )
        self.price = price or (lambda coin, t: 100.0 + (t // HOUR_MS) % 50 * 0.1)
        self.asked = []

    def candles(
        self, symbol, tf, start_ms, end_ms, now_ms=None, only=None, closed_only=True
    ):
        from pt_exchange_abstraction import Sourced, dollar_symbol

        symbol = dollar_symbol(symbol)  # as the exchange layer takes it
        self.asked.append((symbol, tf, start_ms, end_ms, only))
        coin = symbol.split("-")[0]
        rows = []
        for t in range(int(start_ms), int(end_ms) + 1, HOUR_MS):
            p = float(self.price(coin, t))
            rows.append([t, p, p * 1.002, p * 0.998, p, 5.0])
        return Sourced(rows, self.name, self.connector.market_symbol(symbol), True)

    def __call__(self):
        return self


ANALYSIS_TEXT = (
    "## Summary\n\n{coin} is in a **steady rise** on the hourly chart.\n\n"
    "## Trend and momentum\n\n- RSI is firm\n- price above both averages\n\n"
    "SIGNAL: BUY"
)
SIGNAL_JSON = (
    '{{"direction": "{direction}", "strength": "bullish", "confidence": 72, '
    '"price_target": {target}, "stop_loss": {stop}, "time_horizon": "SHORT", '
    '"reasoning": "Momentum for {coin}."}}'
)
REPORT_TEXT = "# Market Overview\n\n## Summary\n\nAll coins rose.\n"


def answer_for(prompt, direction="BUY", target="null", stop="null"):
    """What a fake model answers: an analysis, a signal or a report, for the coin
    named in the prompt."""
    import re

    match = re.search(r"for (\w+) \(|Analyse (\w+) \(", prompt)
    coin = (match.group(1) or match.group(2)) if match else "?"
    if "Answer with one JSON object" in prompt:
        return SIGNAL_JSON.format(
            direction=direction, target=target, stop=stop, coin=coin
        )
    if "research report" in prompt:
        return REPORT_TEXT
    return ANALYSIS_TEXT.format(coin=coin)


def make_engine(store, http, settings=None, layer=None, clock=None, mode="paper"):
    import time

    from llm_research_engine import LLMResearchEngine, MarketData

    router = lp.LLMRouter(
        settings=settings or {"preferred": "ollama"}, store=store, transport=http
    )
    market = MarketData(layer=layer or FakeLayer(), clock=clock or time.time)
    return LLMResearchEngine(
        router=router,
        store=store,
        market=market,
        clock=clock or time.time,
        trading_mode=lambda: mode,
    )
