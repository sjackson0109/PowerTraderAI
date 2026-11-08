"""FDS-SR-001 milestone M6b: paper-trading observation segments and "Reconcile..."
(sections 5.11 and 12).

* A segment freezes the settings that decide a paper trade; only one runs at a time;
  any deciding change ends it at the time the file was written, naming what changed.
* Reconcile classifies every trade: matched, a different candle, not placed, extra; with
  paper's fill against the replay's open and the fee it charged.
* The window starts, ends and reconciles off the Tk thread; Settings > Paper trading
  opens it.

Synthetic candles and trade rows only: no network."""

from __future__ import annotations

import time

import pytest
from test_strategy_lab import frame_for
from test_strategy_settings_ui import root  # noqa: F401

import observation_ui as ui
from strategy_lab import observation as obs
from strategy_lab.candidates import RunnerSpec

CONFIG = {
    "trading": {"mode": "paper"},
    "strategy": {
        "active_id": "STRAT-004",
        "timeframe": "1d",
        "params": {"STRAT-004": {"entry_days": 20, "exit_days": 10}},
    },
    "risk": {"emergency_drawdown_pct": 8.0},
}
GUI = {"coins": ["AAA"], "start_allocation_pct": 1.0}


@pytest.fixture
def hub(tmp_path):
    return str(tmp_path / "hub")


class TestSegments:
    def test_one_segment_at_a_time_and_ended_by_hand(self, hub):
        seg = obs.start(hub, CONFIG, GUI, now=1_700_000_000)
        assert seg["sha256"] == obs.digest(obs.snapshot(CONFIG, GUI))
        with pytest.raises(obs.ObservationError, match="already running"):
            obs.start(hub, CONFIG, GUI)
        ended = obs.end(hub, "ended by hand", when=1_700_100_000)
        assert ended["end_reason"] == "ended by hand" and obs.open_segment(hub) is None

    def test_a_deciding_change_ends_it_when_the_file_was_written(self, hub):
        obs.start(hub, CONFIG, GUI, now=1_700_000_000)
        assert obs.check(hub, dict(CONFIG), dict(GUI), changed_at=1_700_000_500) is None
        changed = {**CONFIG, "strategy": {**CONFIG["strategy"], "timeframe": "4h"}}
        ended = obs.check(hub, changed, GUI, changed_at=1_700_050_000)
        assert ended["ended_s"] == 1_700_050_000
        assert ended["end_reason"] == "settings changed: strategy"
        obs.start(hub, CONFIG, GUI, now=1_700_060_000)
        ended = obs.check(hub, CONFIG, {**GUI, "coins": ["AAA", "BBB"]}, 1_700_070_000)
        assert "coins" in ended["end_reason"]

    def test_an_unrelated_setting_changes_nothing(self, hub):
        obs.start(hub, CONFIG, GUI, now=1_700_000_000)
        other = {**CONFIG, "llm": {"provider": "x"}, "display": {"theme": "dark"}}
        assert obs.check(hub, other, {**GUI, "chart_tf": "4h"}, 1_700_000_900) is None


def paper_row(side, tag, ts, price, qty=1.0, fee=None):
    return {
        "ts": ts,
        "side": side,
        "tag": tag,
        "symbol": "AAA-USD",
        "qty": qty,
        "price": price,
        "fees_usd": fee if fee is not None else price * qty * 0.005,
    }


class TestReconcile:
    def setup_method(self):
        self.frame = frame_for("1d", 400, seed=41)
        self.spec = RunnerSpec(
            "STRAT-004", {"entry_days": 20, "exit_days": 10}, (), "1d"
        )
        start = int(self.frame["open_time"].iloc[60].timestamp())
        self.segment = {
            "started_s": start,
            "snapshot": obs.snapshot(CONFIG, GUI),
        }
        self.end_s = int(self.frame["open_time"].iloc[-1].timestamp())
        self.trades = obs.replay_trades(
            self.spec, {"AAA": self.frame}, start, self.end_s
        )["AAA"]

    def test_every_trade_is_classified(self):
        assert len(self.trades) >= 4
        a, b = self.trades[0], self.trades[1]
        day = 86_400
        rows = [
            # matched: filled a minute into the replay's own candles, 0.1% above
            paper_row("buy", "ENTRY", a.entry_s + 60, a.entry_price * 1.001),
            paper_row("sell", "EXIT:strategy", a.exit_s + 60, a.exit_price),
            # a different candle: one day late
            paper_row("buy", "ENTRY", b.entry_s + day + 60, b.entry_price),
            paper_row("sell", "EXIT:strategy", b.exit_s + day + 60, b.exit_price),
            # extra: a trade the replay does not make, far from any of its own
            paper_row("buy", "ENTRY", self.end_s - day, 100.0),
        ]
        out = obs.reconcile(self.segment, rows, {"AAA": self.frame}, self.end_s)
        counts = obs.summary(out)
        assert counts["matched"] == 1 and counts["timing"] == 1 and counts["extra"] == 1
        assert counts["missed"] == len(self.trades) - 2
        matched = next(r for r in out if r.result == "matched")
        assert matched.fill_vs_open == pytest.approx(0.001)
        assert matched.fee_rate_paid == pytest.approx(0.005)

    def test_the_neural_levels_cannot_be_reconciled(self):
        legacy = obs.snapshot({**CONFIG, "strategy": {"engine": "legacy_neural"}}, GUI)
        with pytest.raises(obs.ObservationError, match="neural levels"):
            obs.spec_of(legacy)


class TestWindow:
    def test_start_end_and_reconcile(self, root, hub):  # noqa: F811
        state = {"config": dict(CONFIG), "gui": dict(GUI), "written": 1_700_000_000.0}
        seen = []

        def fake(hub_dir, segment):
            seen.append(segment["id"])
            return [obs.Row("AAA", "matched", 1, 1, 2, 2, 0.001, 0.005)]

        win = ui.ObservationWindow(
            root, hub, lambda: (state["config"], state["gui"], state["written"]), fake
        )
        win.withdraw()
        assert win.status_var.get() == "No observation yet."
        assert win.reconcile_button.instate(["disabled"])
        win.start()
        assert win.status_var.get().startswith("Observing since")
        assert win.start_button.instate(["disabled"])
        win.reconcile()
        end = time.time() + 10
        while time.time() < end and not win.rows:
            win.update()
            time.sleep(0.02)
        assert len(win.table.tree.get_children()) == 1
        assert win.summary_var.get().startswith("Matched 1")
        state["gui"] = {**GUI, "coins": ["AAA", "BBB"]}
        state["written"] = time.time()
        win.refresh()
        assert "ended: settings changed: coins" in win.status_var.get()
        assert win.start_button.instate(["!disabled"])
        win.destroy()


@pytest.fixture
def real_hub(monkeypatch):
    import helpers_trainer as ht
    import pt_hub

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    monkeypatch.setattr(pt_hub, "API_SERVER_AVAILABLE", False)
    yield hub
    ht.close_hub(hub)


def test_settings_paper_trading_opens_the_observation(real_hub):
    from test_trainer_launch import open_settings, press

    win = open_settings(real_hub)
    press(win, "Observation...")
    shown = real_hub._observation_win
    assert isinstance(shown, ui.ObservationWindow)
    assert shown.hub_dir == real_hub.hub_dir
    shown.withdraw()
    press(win, "Observation...")  # raises the open one
    assert real_hub._observation_win is shown
    shown.destroy()
    win.destroy()
