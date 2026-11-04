"""The LLM Research engine (llm_research_engine, llm_signals, llm_store): market
data from the exchange layer, answers through the provider layer, prompt versions,
signals read and scored after fees, reports and cost estimates.

No network: a fake exchange layer and a fake HTTP transport (helpers_llm).
"""

import os
import sys

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import llm_signals as ls  # noqa: E402
import pt_secrets  # noqa: E402
from helpers_llm import (  # noqa: E402
    HOUR_MS,
    OPENAI,
    FakeHttp,
    FakeLayer,
    answer_for,
    chat_answer,
    make_engine,
    ollama_routes,
    openai_models,
)
from llm_research_engine import DEFAULT_PROMPTS, render  # noqa: E402
from llm_store import LLMStore, SignalRecord  # noqa: E402

NOW = 1_800_000_000.0  # a fixed clock


@pytest.fixture
def store(tmp_path):
    return LLMStore(str(tmp_path / "llm.db"))


@pytest.fixture
def http():
    return FakeHttp(ollama_routes(answer_for))


def test_market_data_comes_from_the_exchange_layer_in_its_format(store, http):
    for exchange, pair in (("coinbase", "BTC-USD"), ("binance", "BTCUSDT")):
        engine = make_engine(store, http, layer=FakeLayer(exchange), clock=lambda: NOW)
        snap = engine.market.snapshot("btc")
        assert (snap.coin, snap.pair, snap.exchange) == ("BTC", pair, exchange)
        assert snap.price is not None and snap.rsi_14 is not None
        assert snap.sma_200 is not None and len(snap.closes_24h) == 24
        assert f"Market: {pair}" in snap.text()


def test_an_analysis_is_the_models_own_text_with_its_source(store, http):
    engine = make_engine(store, http, clock=lambda: NOW)
    result = engine.analyze("ETH")
    record = result.record
    assert (record.coin, record.pair, record.provider, record.model) == (
        "ETH",
        "ETH-USD",
        "ollama",
        "local:7b",
    )
    assert record.prompt_version == 1
    assert record.text.startswith("## Summary\n\nETH is in a **steady rise**")
    assert result.signal == "BUY" and record.facts["signal"] == "BUY"
    prompt = http.posts()[-1][3]["messages"][-1]["content"]
    assert "Analyse ETH (ETH-USD, prices in USD)" in prompt
    assert "Last hourly close:" in prompt and "${" not in prompt
    assert store.latest_analyses()["ETH"].text == record.text


def test_an_edited_prompt_is_a_new_version_and_an_old_one_can_be_restored(store, http):
    engine = make_engine(store, http, clock=lambda: NOW)
    assert engine.prompt("analysis").version == 1
    v2 = store.save_prompt("analysis", DEFAULT_PROMPTS["analysis"] + "\nBe brief.")
    assert v2.version == 2 and v2.active
    assert engine.analyze("BTC").record.prompt_version == 2
    assert "Be brief." in http.posts()[-1][3]["messages"][-1]["content"]
    versions = store.prompt_versions("analysis")
    assert [v.version for v in versions] == [1, 2] and versions[
        0
    ].created_at <= versions[1].created_at
    store.restore_prompt("analysis", 1)
    assert engine.analyze("BTC").record.prompt_version == 1
    with pytest.raises(ValueError):
        store.save_prompt("analysis", "   ")


def test_a_signal_records_everything_the_gate_and_the_tab_need(store, http):
    engine = make_engine(store, http, clock=lambda: NOW, mode="paper")
    result = engine.signal("SOL", source="manual")
    s = store.latest_signal("SOL")
    assert s.id == result.record.id
    assert (s.provider, s.model, s.prompt_version, s.coin, s.pair) == (
        "ollama",
        "local:7b",
        1,
        "SOL",
        "SOL-USD",
    )
    assert (s.direction, s.strength, s.confidence, s.time_horizon) == (
        "BUY",
        "bullish",
        72.0,
        "SHORT",
    )
    assert s.ts == NOW and s.price is not None
    assert (s.source, s.trading_mode, s.reasoning) == (
        "manual",
        "paper",
        "Momentum for SOL.",
    )


def test_reading_a_signal_from_an_answer():
    parsed = ls.parse_signal(
        'Here it is:\n```json\n{"direction": "long", "confidence": 0.8, '
        '"price_target": "1,234.5", "stop_loss": -3, "time_horizon": "soon"}\n```'
    )
    assert parsed["direction"] == "BUY" and parsed["confidence"] == 80.0
    assert parsed["price_target"] == 1234.5 and parsed["stop_loss"] is None
    assert parsed["time_horizon"] == "MEDIUM" and parsed["strength"] == "bullish"
    nothing = ls.parse_signal("I cannot say.")
    assert nothing["direction"] is None and nothing["reasoning"] == "I cannot say."
    assert ls.analysis_signal("...\n**SIGNAL: sell**") == "SELL"
    assert ls.analysis_signal("no line") is None


COSTS = ls.Costs(0.001, 0.0005, "test")


def bars(prices, start=0):
    return [[start + i * HOUR_MS, p, p, p, p, 1.0] for i, p in enumerate(prices)]


def test_a_buy_is_scored_after_fees_like_the_backtester():
    # the target is reached in the third bar: a win after both fees and slippage
    out = ls.score_signal(
        "BUY", 100.0, 0, "SHORT", 105.0, 95.0, bars([100, 102, 106]), COSTS, 10**12
    )
    assert (out.outcome, out.exit_price, out.hit) == ("target", 105.0, True)
    assert out.net_return == pytest.approx(
        0.999 * (105 * 0.9995) / (100 * 1.0005) * 0.999 - 1
    )
    # a stop and a target in the same bar: the stop is taken
    both = [[0, 100, 106, 94, 100, 1.0]]
    assert (
        ls.score_signal(
            "BUY", 100.0, 0, "SHORT", 105.0, 95.0, both, COSTS, 10**12
        ).outcome
        == "stop"
    )
    # a 0.1% rise does not beat the fees: a miss
    flat = bars([100.0] * 23 + [100.1])
    out = ls.score_signal("BUY", 100.0, 0, "SHORT", None, None, flat, COSTS, 10**12)
    assert (out.outcome, out.hit) == ("horizon", False) and out.net_return < 0
    # the horizon has not passed yet: still open
    assert (
        ls.score_signal(
            "BUY", 100.0, 0, "SHORT", None, None, bars([100, 101]), COSTS, 2 * HOUR_MS
        )
        is None
    )
    # a sell wins when the price falls
    down = ls.score_signal(
        "SELL", 100.0, 0, "SHORT", 97.0, 103.0, bars([100, 99, 96]), COSTS, 10**12
    )
    assert (down.outcome, down.hit) == ("target", True)
    # a hold says nothing to score
    assert (
        ls.score_signal("HOLD", 100.0, 0, "SHORT", None, None, flat, COSTS, 10**12)
        is None
    )


def test_the_fees_are_the_backtesters_until_an_exchange_states_its_own():
    from backtest.engine import CostModel

    costs = ls.trade_costs(FakeLayer())
    assert (costs.fee_rate, costs.slippage_rate) == (
        CostModel().fee_bps / 1e4,
        CostModel().slippage_bps / 1e4,
    )
    layer = FakeLayer()
    layer.connector.trading_fees = lambda: {"taker": 0.006, "maker": 0.004}
    assert ls.trade_costs(layer).fee_rate == 0.006
    assert "Coinbase taker fee" in ls.trade_costs(layer).source


def test_pending_signals_are_scored_once_their_outcome_is_known(store, http):
    start = 1_700_000_000.0
    clock = {"now": start}
    layer = FakeLayer(
        price=lambda coin, t: 100.0 if t < start * 1000 + 3 * HOUR_MS else 110.0
    )
    engine = make_engine(store, http, layer=layer, clock=lambda: clock["now"])
    s = store.add_signal(
        SignalRecord(
            ts=start,
            coin="BTC",
            provider="ollama",
            model="m",
            prompt_version=1,
            direction="BUY",
            price=100.0,
            price_target=108.0,
            time_horizon="SHORT",
            exchange="coinbase",
        )
    )
    hold = store.add_signal(
        SignalRecord(
            ts=start,
            coin="BTC",
            provider="ollama",
            model="m",
            prompt_version=1,
            direction="HOLD",
            price=100.0,
        )
    )
    clock["now"] = start + 1800
    assert engine.score_pending(COSTS) == 0  # no closed bar after it yet
    clock["now"] = start + 6 * 3600
    assert engine.score_pending(COSTS) == 1
    scored = {x.id: x for x in store.signals()}
    assert (scored[s.id].outcome, scored[s.id].hit, scored[s.id].exit_price) == (
        "target",
        True,
        108.0,
    )
    assert scored[hold.id].outcome == "no direction" and scored[hold.id].hit is None
    assert store.unscored_signals() == []


def test_a_report_file_names_its_provider_model_prompt_and_time(store, http):
    engine = make_engine(store, http, clock=lambda: NOW)
    result = engine.report("Market Overview", ["BTC", "ETH"])
    assert result.text == "# Market Overview\n\n## Summary\n\nAll coins rose.\n"
    text = result.markdown_file()
    assert text.startswith("---\ntitle: Market Overview\ncoins: BTC, ETH\n")
    for line in (
        "provider: Ollama",
        "model: local:7b",
        "prompt_version: report v1",
        "generated: 2027-01-15T08:00:00Z",
    ):
        assert line in text
    assert text.endswith("All coins rose.\n")


def test_the_cost_estimate_is_free_for_ollama_and_known_once_a_price_is_set(
    store, memory_keyring
):
    pt_secrets.set_secret("openai", "api_key", "sk")
    http = FakeHttp(
        {**ollama_routes("x"), ("GET", OPENAI + "/models"): openai_models(("m", 1))}
    )
    settings = {
        "preferred": "ollama",
        "fallbacks": ["openai", "anthropic"],
        "providers": {"openai": {"model": "m"}},
        "prices": {"openai": {"m": {"input": 1.0, "output": 4.0}}},
    }
    engine = make_engine(store, http, settings=settings)
    free, paid = engine.estimate(["BTC", "ETH"], 10)  # Anthropic has no key: left out
    assert (free.provider, free.per_refresh, free.per_day) == ("ollama", 0.0, 0.0)
    assert paid.provider == "openai" and paid.per_refresh > 0
    assert paid.per_day == pytest.approx(paid.per_refresh * 144)
    # with answers recorded, the estimate uses their tokens
    for kind in ("analysis", "signal"):
        store.record_usage("openai", "m", 1000, 500, None, kind)
    _free, paid = engine.estimate(["BTC"], 60)
    assert paid.per_refresh == pytest.approx(2 * (1000 * 1.0 + 500 * 4.0) / 1e6)
    settings["prices"] = {}
    assert (
        make_engine(store, http, settings=settings).estimate(["BTC"], 10)[1].per_refresh
        is None
    )


def test_templates_fill_their_fields_and_leave_the_rest():
    assert render("A ${coin} {x} $5 ${other}", coin="BTC") == "A BTC {x} $5 ${other}"
    for kind, template in DEFAULT_PROMPTS.items():
        assert "${market_data}" in template, kind


def test_a_fallback_answer_is_recorded_under_the_provider_that_gave_it(
    store, memory_keyring
):
    pt_secrets.set_secret("openai", "api_key", "sk")
    http = FakeHttp(
        {
            ("GET", OPENAI + "/models"): openai_models(("paid-m", 1)),
            ("POST", OPENAI + "/chat/completions"): chat_answer(
                answer_for("Analyse BTC (")
            ),
        }
    )
    engine = make_engine(
        store, http, settings={"preferred": "ollama", "fallbacks": ["openai"]}
    )
    result = engine.analyze("BTC")
    assert (result.record.provider, result.record.model) == ("openai", "paid-m")
    assert result.routed.paid_fallback
    assert "Answered by OpenAI, a paid provider" in result.record.facts["warning"]
