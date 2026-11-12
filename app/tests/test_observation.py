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

import json
import os
import time

import numpy as np
import pandas as pd
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
DAY = 86_400


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


EXCHANGES = ["coinbase", "kraken", "kucoin"]


class TestTheLlmSettingsAndExchanges:
    """An LLM signal can confirm or veto an entry, and the exchange order decides the
    quote, fee, minimum and candles: changing either ends the segment."""

    def test_the_llm_signal_mode_or_use_ends_it(self, hub):
        obs.start(hub, CONFIG, GUI, now=1_700_000_000, exchanges=EXCHANGES)
        veto = {**CONFIG, "llm": {"signal_mode": "veto"}}
        ended = obs.check(hub, veto, GUI, 1_700_000_500, EXCHANGES)
        assert ended["end_reason"] == "settings changed: llm.signal_mode"
        assert ended["ended_s"] == 1_700_000_500
        obs.start(hub, CONFIG, GUI, now=1_700_001_000, exchanges=EXCHANGES)
        used = {**CONFIG, "llm": {"signal_use": {"openai|gpt": True}}}
        ended = obs.check(hub, used, GUI, 1_700_001_500, EXCHANGES)
        assert ended["end_reason"] == "settings changed: llm.signal_use"

    def test_the_exchange_order_ends_it(self, hub):
        seg = obs.start(hub, CONFIG, GUI, now=1_700_000_000, exchanges=EXCHANGES)
        assert seg["snapshot"]["exchanges"] == EXCHANGES
        assert seg["sha256"] == obs.digest(obs.snapshot(CONFIG, GUI, EXCHANGES))
        assert obs.check(hub, CONFIG, GUI, 1_700_000_100, list(EXCHANGES)) is None
        reordered = ["kraken", "coinbase", "kucoin"]
        ended = obs.check(hub, CONFIG, GUI, 1_700_000_500, reordered)
        assert ended["end_reason"] == "settings changed: exchanges"
        obs.start(hub, CONFIG, GUI, now=1_700_001_000, exchanges=EXCHANGES)
        ended = obs.check(hub, CONFIG, GUI, 1_700_001_500, EXCHANGES[:2])
        assert ended["end_reason"] == "settings changed: exchanges"


@pytest.fixture
def program(tmp_path):
    """A program folder holding every trading-path file, with stand-in text."""
    root = tmp_path / "program"
    for name in obs.code_hashes():
        path = root.joinpath(*name.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"# {name}\n".encode())
    return str(root)


class TestProgramFiles:
    """The owner's app runs from the checkout: a change to a trading-path file ends
    the segment, dated by the file."""

    def test_the_trading_path_is_hashed(self):
        code = obs.code_hashes()
        for name in (
            "pt_trader.py",
            "signal_engine.py",
            "trading_mode.py",
            "pt_paper_trading.py",
            "position_sizing.py",
            "pt_risk.py",
            "llm_gate.py",
            "pt_exchanges.py",
            "pt_multi_exchange.py",
            "strategies/catalogue.json",
            "strategies/breakout.py",
            "strategies/overlays.py",
            "strategies/runner.py",
            "market_data/candles.py",
            "signal_fusion/live.py",
        ):
            assert name in code, name
        missing = [name for name, sha in code.items() if sha is None]
        assert missing == []

    def test_a_changed_file_ends_it_when_it_was_written(self, hub, program):
        seg = obs.start(hub, CONFIG, GUI, now=1_700_000_000, code_root=program)
        assert seg["code"] == obs.code_hashes(program)
        assert obs.check(hub, CONFIG, GUI, 1_700_000_100, code_root=program) is None
        trader = os.path.join(program, "pt_trader.py")
        with open(trader, "wb") as f:  # the same text with CRLF line endings
            f.write(b"# pt_trader.py\r\n")
        assert obs.check(hub, CONFIG, GUI, 1_700_000_100, code_root=program) is None
        with open(trader, "ab") as f:
            f.write(b"x = 1\n")
        os.utime(trader, (1_700_050_000, 1_700_050_000))
        ended = obs.check(hub, CONFIG, GUI, 1_700_000_100, code_root=program)
        assert ended["end_reason"] == "program files changed: pt_trader.py"
        assert ended["ended_s"] == 1_700_050_000

    def test_a_removed_file_ends_it(self, hub, program):
        obs.start(hub, CONFIG, GUI, now=1_700_000_000, code_root=program)
        os.remove(os.path.join(program, "strategies", "breakout.py"))
        ended = obs.check(hub, CONFIG, GUI, 1_700_000_100, code_root=program)
        assert ended["end_reason"] == "program files changed: strategies/breakout.py"


def old_segment(hub, started_s=1_700_000_000):
    """A segment saved before the LLM settings, the exchanges and the program files
    were frozen, as that version wrote it; its path."""
    snap = {
        "config": {
            "trading.mode": "paper",
            **{k: CONFIG.get(k) for k in obs.CONFIG_SECTIONS},
        },
        "gui": {k: GUI.get(k) for k in obs.GUI_KEYS},
    }
    segment = {
        "id": "20231114-221320",
        "started_at": "2023-11-14T22:13:20+00:00",
        "started_s": started_s,
        "snapshot": snap,
        "sha256": obs.digest(snap),
        "ended_at": None,
        "end_reason": None,
    }
    os.makedirs(obs.folder(hub), exist_ok=True)
    path = os.path.join(obs.folder(hub), segment["id"] + ".json")
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(segment, f, indent=2, sort_keys=True)
        f.write("\n")
    return path


class TestOlderSegments:
    def test_what_it_did_not_freeze_does_not_end_it(self, hub):
        path = old_segment(hub)
        with open(path, "rb") as f:
            before = f.read()
        veto = {**CONFIG, "llm": {"signal_mode": "veto", "signal_use": {"a|b": True}}}
        assert obs.check(hub, veto, GUI, 1_700_000_500, ["kraken"]) is None
        with open(path, "rb") as f:
            assert f.read() == before  # never rewritten
        coins = {**GUI, "coins": ["AAA", "BBB"]}
        ended = obs.check(hub, veto, coins, 1_700_000_900, ["kraken"])
        assert ended["end_reason"] == "settings changed: coins"


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

    def test_a_trade_the_replay_exited_and_paper_holds_is_an_exit_not_placed(self):
        b = self.trades[1]
        assert not b.forced
        rows = [paper_row("buy", "ENTRY", b.entry_s + 60, b.entry_price)]
        out = obs.reconcile(self.segment, rows, {"AAA": self.frame}, self.end_s)
        (row,) = [r for r in out if r.paper_entry_s is not None]
        assert row.result == "exit_missed"
        assert row.replay_exit_s == b.exit_s and row.paper_exit_s is None

    def test_an_entry_after_the_newest_closed_candle_is_pending(self):
        day = 86_400
        rows = [paper_row("buy", "ENTRY", self.end_s - day, 100.0)]
        cut = self.frame.iloc[:-5]  # the newest closed candle opened 5 days earlier
        out = obs.reconcile(self.segment, rows, {"AAA": cut}, self.end_s)
        assert [r.result for r in out if r.paper_entry_s] == ["pending"]
        out = obs.reconcile(self.segment, rows, {"AAA": self.frame}, self.end_s)
        assert [r.result for r in out if r.paper_entry_s] == ["extra"]

    def test_a_partial_exit_is_one_exit(self):
        a = self.trades[0]
        rows = [
            paper_row("buy", "ENTRY", a.entry_s + 60, 100.0),
            paper_row("sell", "EXIT:strategy", a.exit_s + 60, 110.0, qty=0.4)
            | {"closes_position": False},
            paper_row("sell", "EXIT:strategy", a.exit_s + 120, 120.0, qty=0.6, fee=0.72)
            | {"closes_position": True},
        ]
        (trade,) = obs.paper_trades(rows, self.segment["started_s"], self.end_s)
        assert trade.exit_s == a.exit_s + 60
        assert trade.exit_price == pytest.approx((0.4 * 110 + 0.6 * 120) / 1.0)
        # 0.5% of 44 and 1% of 72
        assert trade.exit_fee == pytest.approx((0.22 + 0.72) / (44 + 72))


def probe_frame():
    """reconcile_probe.py's synthetic daily bars."""
    rng = np.random.default_rng(5)
    closes = list(100 * np.exp(np.cumsum(rng.normal(0.002, 0.03, 500))))
    t0 = pd.Timestamp("2023-01-01", tz="UTC")
    return pd.DataFrame(
        {
            "open_time": [t0 + pd.Timedelta(days=i) for i in range(len(closes))],
            "open": [closes[0]] + closes[:-1],
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": 100.0,
        }
    )


class TestTheProbeCases:
    """The five cases of docs/dev/strat-004-readiness/reconcile_probe.py (STRAT-004 at
    its defaults), each as what Reconcile must now report."""

    def setup_method(self):
        self.frame = probe_frame()
        config = {
            "trading": {"mode": "paper"},
            "strategy": {"active_id": "STRAT-004", "timeframe": "1d"},
        }
        self.snap = obs.snapshot(config, {"coins": ["AAA"]})
        self.start = int(self.frame.open_time.iloc[60].timestamp())
        self.end = int(self.frame.open_time.iloc[-1].timestamp())
        spec = obs.spec_of(self.snap)
        candles = {"AAA": self.frame}
        self.trades = obs.replay_trades(spec, candles, self.start, self.end)["AAA"]
        assert len(self.trades) == 5 and self.trades[-1].forced

    @staticmethod
    def row(side, tag, ts, price, qty=1.0, fee_rate=0.005, sid="STRAT-004"):
        return {
            "ts": ts,
            "side": side,
            "tag": tag,
            "symbol": "AAA-USD",
            "qty": qty,
            "price": price,
            "fees_usd": price * qty * fee_rate,
            "strategy_id": sid,
        }

    def reconcile(self, rows, frame=None):
        segment = {"started_s": self.start, "snapshot": self.snap}
        candles = {"AAA": self.frame if frame is None else frame}
        out = obs.reconcile(segment, rows, candles, self.end)
        return [r for r in out if r.result != "missed"], obs.summary(out)

    def test_1_a_second_entry_before_the_exit_is_flagged(self):
        a = self.trades[0]
        shown, counts = self.reconcile(
            [
                self.row("buy", "ENTRY", a.entry_s + 30, a.entry_price),
                self.row("buy", "ENTRY", a.entry_s + 90, a.entry_price),
                self.row("sell", "EXIT:strategy", a.exit_s + 30, a.exit_price, 2.0),
            ]
        )
        assert counts["matched"] == 1 and counts["duplicate"] == 1
        (second,) = [r for r in shown if r.result == "duplicate"]
        assert second.paper_entry_s == a.entry_s + 90
        assert ui.row_values(second)[1] == "Second entry"

    def test_2_a_late_fill_in_the_same_candle_reports_its_delay(self):
        a = self.trades[0]
        shown, _ = self.reconcile(
            [
                self.row("buy", "ENTRY", a.entry_s + 20 * 3600, a.entry_price * 1.03),
                self.row("sell", "EXIT:strategy", a.exit_s + 30, a.exit_price),
            ]
        )
        (row,) = shown
        assert row.result == "matched"
        assert row.entry_delay_s == 20 * 3600 and row.exit_delay_s == 30
        assert row.fill_vs_open == pytest.approx(0.03)
        values = dict(zip(ui.COLUMNS, ui.row_values(row)))
        assert (values["entry_delay"], values["exit_delay"]) == (
            "+20 h 00 min",
            "+30 s",
        )
        assert "entries up to +20 h 00 min" in ui.summary_text(shown)

    def test_3_the_exit_fee_is_shown_beside_the_entry_fee(self):
        a = self.trades[0]
        shown, _ = self.reconcile(
            [
                self.row("buy", "ENTRY", a.entry_s + 30, a.entry_price),
                self.row(
                    "sell", "EXIT:strategy", a.exit_s + 30, a.exit_price, fee_rate=0.012
                ),
            ]
        )
        (row,) = shown
        assert row.fee_rate_paid == pytest.approx(0.005)
        assert row.exit_fee_rate_paid == pytest.approx(0.012)
        assert row.exit_fill_vs_open == pytest.approx(0.0)
        values = dict(zip(ui.COLUMNS, ui.row_values(row)))
        assert (values["fee"], values["exit_fee"]) == ("0.500%", "1.200%")

    def test_4_a_trade_still_open_is_labelled_open(self):
        c = self.trades[-1]
        shown, counts = self.reconcile([self.row("buy", "ENTRY", c.entry_s + 30, 1.0)])
        (row,) = shown
        assert row.result == "open" and counts["timing"] == 0
        assert row.replay_exit_s is None and row.paper_exit_s is None
        assert ui.row_values(row)[1] == "Open"

    def test_4b_an_exit_after_the_newest_closed_candle_is_pending(self):
        c = self.trades[-1]
        cut = self.frame.iloc[:-2]
        newest = int(cut.open_time.iloc[-1].timestamp()) + DAY
        assert c.entry_s < newest
        shown, _ = self.reconcile(
            [
                self.row("buy", "ENTRY", c.entry_s + 30, c.entry_price),
                self.row("sell", "EXIT:strategy", newest + 300, c.entry_price),
            ],
            frame=cut,
        )
        (row,) = shown
        assert row.result == "pending" and row.replay_exit_s is None

    def test_5_rows_from_another_strategy_are_flagged_not_matched(self):
        a = self.trades[0]
        shown, counts = self.reconcile(
            [
                self.row(
                    "buy", "ENTRY", a.entry_s + 30, a.entry_price, sid="STRAT-001"
                ),
                self.row(
                    "sell",
                    "EXIT:strategy",
                    a.exit_s + 30,
                    a.exit_price,
                    sid="STRAT-001",
                ),
            ]
        )
        assert counts["matched"] == 0 and counts["missed"] == len(self.trades)
        assert [r.result for r in shown] == ["different", "different"]
        assert all(r.differs == ("strategy_id",) for r in shown)
        assert (shown[0].paper_entry_s, shown[1].paper_exit_s) == (
            a.entry_s + 30,
            a.exit_s + 30,
        )
        assert ui.row_values(shown[0])[-1] == "strategy"


class TestStrategyFields:
    def setup_method(self):
        config = {"strategy": {"active_id": "STRAT-004", "timeframe": "1d"}}
        self.spec = obs.spec_of(obs.snapshot(config, GUI))
        self.frozen = obs.strategy_fields(self.spec)

    def test_they_are_what_the_trader_writes(self):
        # STRAT-004 at its defaults (55, 20): docs/dev/STRAT-004-paper-readiness.md 6.2
        assert self.frozen == {
            "strategy_id": "STRAT-004",
            "strategy_version": "1.0.0",
            "strategy_params_sha256": (
                "89579608ee854d67afce197674141a23848b1adb3bcca6b5096d72dcfd726265"
            ),
            "strategy_timeframe": "1d",
            "strategy_overlays": [],
        }

    def test_each_differing_field_is_named_and_an_unrecorded_one_is_not(self):
        same = dict(self.frozen)
        assert obs.differing_fields(same, self.frozen) == ()
        assert obs.differing_fields({}, self.frozen) == ()
        other = {
            **same,
            "strategy_params_sha256": "0" * 64,
            "strategy_timeframe": "4h",
            "strategy_overlays": [{"id": "OVL-REGIME", "version": "1.0.0"}],
        }
        assert obs.differing_fields(other, self.frozen) == (
            "strategy_params_sha256",
            "strategy_timeframe",
            "strategy_overlays",
        )

    def test_any_row_from_other_settings_is_flagged_whatever_its_tag(self):
        start = 1_700_000_000
        segment = {"started_s": start, "snapshot": obs.snapshot(CONFIG, GUI)}
        rows = [
            # a neural-levels buy and a DCA buy inside the segment
            paper_row("buy", None, start + 60, 100.0)
            | {"strategy_id": "legacy_neural"},
            paper_row("buy", "DCA", start + 120, 90.0)
            | {"strategy_id": "legacy_neural"},
        ]
        out = obs.reconcile(segment, rows, {}, start + 3600)
        assert [(r.result, r.differs) for r in out] == [
            ("different", ("strategy_id",)),
            ("different", ("strategy_id",)),
        ]


class TestPaperCoins:
    def test_the_replay_uses_the_paper_trading_coins(self):
        gui = {**GUI, "coins": ["AAA", "BBB", "CCC"]}
        snap = obs.snapshot(CONFIG, gui)
        assert obs.replay_coins(snap) == ["AAA", "BBB", "CCC"]
        picked = {**gui, "paper_coins_mode": "override", "paper_coins": ["CCC", "AAA"]}
        assert obs.replay_coins(obs.snapshot(CONFIG, picked)) == ["AAA", "CCC"]
        live = {**CONFIG, "trading": {"mode": "live"}}
        assert obs.replay_coins(obs.snapshot(live, picked)) == ["AAA", "BBB", "CCC"]

    def test_reconcile_loads_only_the_paper_trading_coins(self, hub, monkeypatch):
        asked = []

        def load(spec, coins, start_s, end_s):
            asked.append(list(coins))
            return {}, {}

        monkeypatch.setattr(obs, "load_candles", load)
        gui = {
            **GUI,
            "coins": ["AAA", "BBB"],
            "paper_coins_mode": "override",
            "paper_coins": ["BBB"],
        }
        segment = {
            "started_s": 1_700_000_000,
            "ended_s": 1_700_100_000,
            "snapshot": obs.snapshot(CONFIG, gui),
        }
        assert ui.default_reconcile(hub, segment) == []
        assert asked == [["BBB"]]


def test_every_result_has_words():
    assert set(ui.RESULTS) == set(obs.RESULT_KINDS)
    assert set(ui.FIELDS) == set(obs.STRATEGY_FIELDS)


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

    @staticmethod
    def frozen_shown(win):
        tree = win.frozen_table.tree
        return dict(tree.item(i, "values") for i in tree.get_children())

    def test_it_shows_the_hash_and_the_frozen_values(self, root, hub):  # noqa: F811
        config = {**CONFIG, "llm": {"signal_mode": "off"}}
        win = ui.ObservationWindow(
            root, hub, lambda: (config, GUI, 1_700_000_000.0, EXCHANGES)
        )
        win.withdraw()
        assert win.hash_var.get() == "" and self.frozen_shown(win) == {}
        win.start()
        segment = obs.open_segment(hub)
        assert win.hash_var.get() == segment["sha256"]
        shown = self.frozen_shown(win)
        assert shown["llm.signal_mode"] == "off"
        assert shown["llm.signal_use"] == "Not set"
        assert shown["exchanges"] == "coinbase, kraken, kucoin"
        assert shown["coins"] == "AAA"
        assert shown["strategy"] == json.dumps(CONFIG["strategy"], sort_keys=True)
        assert shown["pt_trader.py"] == obs.code_hashes()["pt_trader.py"]
        assert ui.NOT_RECORDED not in shown.values()
        win.destroy()

    def test_an_older_segment_shows_what_it_did_not_record(
        self, root, hub
    ):  # noqa: F811
        path = old_segment(hub)
        with open(path, "rb") as f:
            before = f.read()
        config = {**CONFIG, "llm": {"signal_mode": "veto"}}
        win = ui.ObservationWindow(
            root, hub, lambda: (config, GUI, 1_700_000_500.0, EXCHANGES)
        )
        win.withdraw()
        assert win.status_var.get().startswith("Observing since")
        assert win.hash_var.get() == json.loads(before)["sha256"]
        shown = self.frozen_shown(win)
        for name in ("llm.signal_mode", "llm.signal_use", "exchanges", "Program files"):
            assert shown[name] == "Not recorded for this observation", name
        assert shown["coins"] == "AAA" and shown["trading.mode"] == "paper"
        with open(path, "rb") as f:
            assert f.read() == before
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
