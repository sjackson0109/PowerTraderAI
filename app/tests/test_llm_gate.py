"""LLM signals in trading (llm_gate, the pt_trader entry hook): a signal can only
confirm or veto an entry the strategy wants; off and log only change nothing; only a
provider/model/prompt version that has passed its gate in paper trading counts; a
slow or failing provider never blocks the trader; every decision is kept with the
trade it was for.

Under the isolation guard (app/conftest.py), with a fake signal source: no provider
is asked for anything.
"""

import os
import sys
import threading
import time
import types
from unittest import mock

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import llm_gate  # noqa: E402
import trading_mode as tm  # noqa: E402
from helpers import PaperTraderCase  # noqa: E402
from llm_store import LLMStore, SignalRecord  # noqa: E402

TRAINING = {"holdout_min_signals": 20, "holdout_min_hit_rate": 0.55}


@pytest.fixture
def requests_on(monkeypatch):
    monkeypatch.setattr(llm_gate, "REQUESTS_ENABLED", True)


def record(store, direction="BUY", model="m", version=1, ts=None, mode="paper", **kw):
    return store.add_signal(
        SignalRecord(
            ts=time.time() if ts is None else ts,
            coin=kw.pop("coin", "BTC"),
            provider=kw.pop("provider", "ollama"),
            model=model,
            prompt_version=version,
            direction=direction,
            confidence=kw.pop("confidence", 70.0),
            trading_mode=mode,
            **kw,
        )
    )


def pass_gate(store, model="m", version=1, mode="paper", hits=12, n=20):
    """``n`` scored signals of a provider/model/prompt version, ``hits`` of them won."""
    for i in range(n):
        s = record(
            store, model=model, version=version, ts=1000.0 + i, mode=mode, coin="OLD"
        )
        store.set_outcome(s.id, "horizon", 0.01 if i < hits else -0.01, i < hits, 100.0)


class FakeEngine:
    """Gives the next signal for a coin (its direction from ``directions``), after
    ``delay`` seconds, or raises ``error``."""

    def __init__(
        self, store, direction="BUY", model="m", version=1, delay=0.0, error=None
    ):
        self.store = store
        self.direction, self.model, self.version = direction, model, version
        self.delay, self.error = delay, error
        self.asked = []

    def signal(self, coin, source="manual", trading_mode="paper"):
        self.asked.append((coin, source, trading_mode))
        if self.delay:
            time.sleep(self.delay)
        if self.error:
            raise self.error
        s = record(
            self.store,
            self.direction,
            self.model,
            self.version,
            mode=trading_mode,
            coin=coin,
            source=source,
        )
        return types.SimpleNamespace(record=s)


def hook(store, engine, mode="confirm", use=True, **llm):
    settings = {
        "llm": dict(
            {
                "signal_mode": mode,
                "signal_timeout_s": 2,
                "signal_use": {"ollama|m": True} if use else {},
            },
            **llm,
        ),
        "training": TRAINING,
    }
    return llm_gate.EntryHook(settings, engine_factory=lambda: engine, store=store)


@pytest.fixture
def store(tmp_path):
    return LLMStore(str(tmp_path / "llm.db"))


# --- the rules ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "mode, direction, allow, decision",
    [
        ("confirm", "BUY", True, "confirmed"),
        ("confirm", "HOLD", False, "not_confirmed"),
        ("confirm", "SELL", False, "not_confirmed"),
        ("veto", "BUY", True, "not_vetoed"),
        ("veto", "HOLD", True, "not_vetoed"),
        ("veto", "SELL", False, "vetoed"),
        ("confirm_and_veto", "BUY", True, "confirmed"),
        ("confirm_and_veto", "HOLD", False, "not_confirmed"),
        ("confirm_and_veto", "SELL", False, "vetoed"),
    ],
)
def test_a_usable_signal_confirms_or_vetoes(mode, direction, allow, decision):
    signal = types.SimpleNamespace(
        provider="ollama",
        model="m",
        prompt_version=1,
        id=7,
        direction=direction,
        confidence=70.0,
    )
    verdict = llm_gate.decide(mode, signal)
    assert (verdict.allow, verdict.decision, verdict.signal_id) == (allow, decision, 7)
    assert (
        verdict.reason
        == f"Ollama m, signal prompt v1, signal 7: {direction} (70% confidence)"
    )


@pytest.mark.parametrize("mode", ["confirm", "veto", "confirm_and_veto"])
def test_with_no_usable_signal_the_entry_goes_ahead(mode):
    verdict = llm_gate.decide(mode, None, "no signal within 2 s")
    assert verdict.allow and verdict.decision == "no_signal"
    assert (
        verdict.reason
        == "no signal within 2 s; the entry goes ahead as the strategy decided"
    )


def test_the_gate_needs_enough_paper_signals_that_won_after_fees(store):
    assert not llm_gate.gate_status(store, "ollama", "m", 1, TRAINING).passed
    pass_gate(store, hits=10)  # 50%
    gate = llm_gate.gate_status(store, "ollama", "m", 1, TRAINING)
    assert (gate.scored, gate.hits, gate.passed) == (20, 10, False)
    assert gate.text() == "not passed: 50% after fees, 55% needed"
    pass_gate(store, model="m2", hits=12)
    gate = llm_gate.gate_status(store, "ollama", "m2", 1, TRAINING)
    assert gate.passed and gate.text() == "passed: 12 of 20 won, 60% after fees"


def test_live_signals_do_not_count_towards_the_gate(store):
    pass_gate(store, mode="live", hits=20)
    assert not llm_gate.gate_status(store, "ollama", "m", 1, TRAINING).passed


def test_a_new_prompt_version_is_logged_only_until_it_passes(store, requests_on):
    pass_gate(store, version=1)
    # version 1 has passed: its HOLD stops the entry
    engine = FakeEngine(store, direction="HOLD", version=1)
    assert not hook(store, engine).check("BTC", "ref-1").allow
    # an edited prompt (version 2) has no scored signals: its HOLD changes nothing
    engine = FakeEngine(store, direction="HOLD", version=2)
    h = hook(store, engine, signal_reuse_minutes=0)
    verdict = h.check("ETH", "ref-2")
    assert verdict.allow and verdict.decision == "no_signal"
    assert (
        "signal prompt v2 has not passed the gate (not passed: 0 of 20 signals scored"
        in verdict.reason
    )


def test_a_model_not_ticked_for_trading_only_logs(store, requests_on):
    pass_gate(store)
    verdict = hook(
        store, FakeEngine(store, direction="SELL"), mode="veto", use=False
    ).check("BTC")
    assert (
        verdict.allow and "Ollama m is not ticked for use in trading" in verdict.reason
    )


def test_off_asks_nothing_and_writes_nothing(tmp_path, requests_on):
    store = LLMStore(str(tmp_path / "none.db"))
    engine = FakeEngine(store)
    verdict = hook(store, engine, mode="off").check("BTC", "ref")
    assert verdict.allow and verdict.decision == "off"
    assert engine.asked == [] and not os.path.exists(store.path)


def test_log_only_asks_in_the_background_and_never_waits(store, requests_on):
    engine = FakeEngine(store, delay=0.5)
    h = hook(store, engine, mode="log_only")
    start = time.monotonic()
    verdict = h.check("BTC", "ref")
    assert verdict.allow and verdict.decision == "logged"
    assert time.monotonic() - start < 0.4  # it did not wait for the answer
    (thread,) = h.threads()
    thread.join(timeout=5)
    assert not thread.is_alive()
    (s,) = store.signals()
    assert (s.coin, s.source, s.trading_mode) == ("BTC", "entry", "paper")
    # a recent signal is used again: no second request
    assert h.check("BTC", "ref-2").decision == "logged"
    assert len(engine.asked) == 1
    assert store.decisions() == []  # log only decides nothing


def test_a_confirmed_entry_is_kept_with_its_trade(store, requests_on):
    pass_gate(store)
    h = hook(store, FakeEngine(store, direction="BUY"), mode="confirm")
    verdict = h.check("BTC", "client-123")
    assert verdict.allow and verdict.decision == "confirmed"
    h.placed("client-123", "order-9")
    (row,) = store.decisions()
    assert (
        row["coin"],
        row["decision"],
        row["allowed"],
        row["trade_ref"],
        row["order_id"],
    ) == (
        "BTC",
        "confirmed",
        1,
        "client-123",
        "order-9",
    )
    assert row["signal_id"] == verdict.signal_id and row["reason"] == verdict.reason


def test_a_slow_provider_costs_at_most_the_wait(store, requests_on):
    engine = FakeEngine(store, delay=1.5)
    h = hook(store, engine, mode="veto", signal_timeout_s=1)
    start = time.monotonic()
    verdict = h.check("BTC", "ref")
    waited = time.monotonic() - start
    assert verdict.allow and verdict.reason.startswith("no signal within 1 s")
    assert 0.9 <= waited < 1.4
    for thread in h.threads():
        thread.join(timeout=5)
        assert not thread.is_alive()


def test_a_failing_provider_or_a_broken_store_lets_the_entry_go_ahead(
    store, requests_on
):
    h = hook(store, FakeEngine(store, error=RuntimeError("down")), mode="confirm")
    verdict = h.check("BTC")
    assert verdict.allow and verdict.reason.startswith("no signal (down)")
    broken = hook(store, FakeEngine(store), mode="confirm")
    broken._store = types.SimpleNamespace()  # no methods at all
    assert broken.check("BTC").allow


def test_the_trader_loop_is_not_held_up_or_flooded(store, requests_on):
    """The loop asks on every pass while the strategy wants an entry."""
    # a provider that is down is not asked again on the next passes
    engine = FakeEngine(store, error=RuntimeError("down"))
    for mode in ("log_only", "veto"):
        h = hook(store, engine, mode=mode)
        h.check("BTC")
        for thread in h.threads():
            thread.join(timeout=5)
        verdict = h.check("BTC")
        assert verdict.allow
    assert len(engine.asked) == 2  # once per hook, not once per pass
    assert "got none" in verdict.reason
    # a slow answer is waited for once; the next pass does not wait again
    slow = FakeEngine(store, delay=2.5)
    h = hook(store, slow, mode="veto", signal_timeout_s=1, signal_reuse_minutes=0)
    h.check("ETH")
    start = time.monotonic()
    verdict = h.check("ETH")
    assert time.monotonic() - start < 0.3
    assert verdict.reason.startswith("a signal for ETH is still being asked for")
    for thread in h.threads():
        thread.join(timeout=5)
    # the same skip is kept once, not on every pass
    pass_gate(store)
    h = hook(store, FakeEngine(store, direction="SELL"), mode="veto")
    for _ in range(3):
        assert not h.check("SOL", "ref").allow
    assert [d["coin"] for d in store.decisions()].count("SOL") == 1


def test_live_uses_only_what_passed_in_paper(store, requests_on):
    pass_gate(store, mode="live", hits=20)  # live wins do not count
    h = hook(store, FakeEngine(store, direction="SELL"), mode="veto")
    verdict = h.check("BTC", "ref", live=True)
    assert verdict.allow and "has not passed the gate" in verdict.reason
    pass_gate(store, mode="paper", hits=15)
    assert (
        not hook(store, FakeEngine(store, direction="SELL"), mode="veto")
        .check("ETH", "ref", live=True)
        .allow
    )


# --- in the trader ------------------------------------------------------------------------


class TraderEntries(PaperTraderCase):
    """A legacy-mode paper trader on a $10,000 book with a long start signal for
    BTC: the strategy wants to enter."""

    def setUp(self):
        super().setUp()
        sleep = mock.patch.object(self.pt_trader.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        self.folder = os.path.join(self.tmp.name, "neural")
        os.makedirs(self.folder)
        for p in (
            mock.patch.object(self.pt_trader, "base_paths", {"BTC": self.folder}),
            mock.patch.object(self.pt_trader, "main_dir", self.folder),
            mock.patch.object(self.pt_trader, "crypto_symbols", ["BTC"]),
            mock.patch.object(llm_gate, "REQUESTS_ENABLED", True),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.quotes.bid, self.quotes.ask = 99.95, 100.05
        for name, value in (
            ("long_dca_signal.txt", "7"),
            ("short_dca_signal.txt", "0"),
        ):
            with open(os.path.join(self.folder, name), "w") as f:
                f.write(value)
        self.store = LLMStore(os.path.join(self.tmp.name, "llm.db"))

    def run_trader(self, mode, engine=None, passed=True, **llm):
        settings = {
            "trading": {"mode": "paper"},
            "strategy": {"engine": "legacy_neural"},
            "llm": dict({"signal_mode": mode, "signal_use": {"ollama|m": True}}, **llm),
            "training": TRAINING,
        }
        if passed:
            pass_gate(self.store)
        trader = self.trader(settings)
        engine = engine or FakeEngine(self.store)
        trader._llm_entry_hook = llm_gate.EntryHook(
            settings, engine_factory=lambda: engine, store=self.store
        )
        trader.manage_trades()
        for thread in trader._llm_entry_hook.threads():
            thread.join(timeout=5)
            assert not thread.is_alive()
        return trader, engine

    def orders(self):
        return list(tm.get_paper_exchange().account.orders.values())

    def entry(self):
        (order,) = self.orders()
        return str(order.side).lower(), float(
            order.filled_quantity * order.filled_price
        )

    def test_off_enters_as_without_the_hook(self):
        _, engine = self.run_trader("off", FakeEngine(self.store, direction="SELL"))
        side, usd = self.entry()
        assert side.endswith("buy") and usd == pytest.approx(100.0, rel=0.01)
        assert engine.asked == [] and self.store.decisions() == []

    def test_log_only_enters_as_without_the_hook_and_keeps_the_signal(self):
        # even a sell signal from a provider that passed changes nothing
        _, engine = self.run_trader(
            "log_only", FakeEngine(self.store, direction="SELL")
        )
        side, usd = self.entry()
        assert side.endswith("buy") and usd == pytest.approx(100.0, rel=0.01)
        assert engine.asked == [("BTC", "entry", "paper")]
        assert self.store.latest_signal("BTC").direction == "SELL"
        assert self.store.decisions() == []

    def test_a_usable_sell_signal_vetoes_the_entry(self):
        self.run_trader("veto", FakeEngine(self.store, direction="SELL"))
        assert self.orders() == []
        (row,) = self.store.decisions()
        assert (row["decision"], row["allowed"]) == ("vetoed", 0)

    def test_a_confirmed_entry_is_linked_to_its_order(self):
        self.run_trader("confirm", FakeEngine(self.store, direction="BUY"))
        (order,) = self.orders()
        (row,) = self.store.decisions()
        assert row["decision"] == "confirmed" and row["order_id"]
        history = self.ledger_rows()
        assert row["order_id"] in {str(r.get("order_id")) for r in history}

    def test_a_broken_hook_never_stops_an_entry(self):
        settings = {
            "trading": {"mode": "paper"},
            "strategy": {"engine": "legacy_neural"},
        }
        trader = self.trader(settings)
        trader._llm_entry_hook = types.SimpleNamespace(
            check=mock.Mock(side_effect=RuntimeError("boom")), placed=mock.Mock()
        )
        trader.manage_trades()
        assert len(self.orders()) == 1


def test_no_thread_is_left_running(store, requests_on):
    """Every request thread the hook started in this module has ended."""
    h = hook(store, FakeEngine(store, delay=0.1), mode="log_only")
    h.check("BTC")
    for thread in h.threads():
        thread.join(timeout=5)
    assert not [t for t in threading.enumerate() if t.name.startswith("llm-entry-")]
