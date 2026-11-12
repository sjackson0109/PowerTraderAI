"""FDS-SR-001 milestone M5a: "Run a backtest..." and "Compare results..." (sections 5.8
and 12).

* A run reads only the development period: a period reaching 2025-05-06 or later is
  refused, by the run and by the window.
* A run takes the strategy's trades in the period, replays them in the chosen account
  against buy-and-hold, cash and random entries, logs an exploratory trial with its
  months, and saves itself; a stopped run saves nothing.
* The window offers only strategies and stops enabled for research, as ticked now; runs
  off the Tk thread; shows the results; and its words state facts only.
* "Compare results..." lists the saved runs, with a search.

Synthetic candles and a fake venue: no network."""

from __future__ import annotations

import threading
import time

import pytest
from test_strategy_lab import frame_for
from test_strategy_settings_ui import Box, folder, manager, root  # noqa: F401

import strategy_lab_ui as ui
import strategy_settings_ui as ssui
from strategy_lab import experiment, runs
from strategy_lab.venue import VenueRules
from strategy_lab.windows import ReservedPeriod

BANNED = ("FDS", "STRAT-", "OVL-", "Binance", "KuCoin", "_len", "_pct", "_days")


@pytest.fixture
def lab(tmp_path, monkeypatch):
    monkeypatch.setattr(experiment, "lab_dir", lambda: str(tmp_path / "strategy_lab"))
    return tmp_path / "strategy_lab"


FRAMES = {
    "AAA-USD": frame_for("1d", 800, seed=31),
    "BBB-USD": frame_for("1d", 800, seed=32, phase=1.0),
}


def loader(symbol, tf, start, end, **kw):
    out = FRAMES[symbol].copy()
    out.attrs.update(exchange="fake", pair=symbol)
    return out


def venue(coins):
    return VenueRules({c: 1.0 for c in coins}, {"AAA": 0.001}, {"BBB": "sell step"})


def config(**changes):
    base = dict(
        strategy_id="STRAT-004",
        params={"entry_days": 20, "exit_days": 10},
        overlays=[],
        timeframe="1d",
        coins=["AAA", "BBB"],
        start="2023-06-01",
        end="2025-01-01",
        account_gbp=500.0,
        gbp_usd=1.25,
        fee=0.005,
        draws=30,
    )
    base.update(changes)
    return runs.RunConfig(**base)


class TestRun:
    def test_a_run_compares_saves_and_logs_itself(self, lab):
        record = runs.run(config(), loader=loader, venue=venue, now=1_800_000_000)
        assert record["account_usd"] == 625.0
        s = record["strategy_result"]
        assert s["trades"] > 0 and record["buy_and_hold"]["trades"] == 2
        assert record["random_entries"]["draws"] == 30
        assert set(record["per_coin"]) <= {"AAA", "BBB"}
        assert record["curve"] and record["venue"]["unknown"] == {"BBB": "sell step"}
        assert record["strategy"]["params"] == {"entry_days": 20, "exit_days": 10}
        trials = experiment.trials()
        assert trials[-1]["kind"] == "exploration"
        assert (trials[-1]["start"], trials[-1]["end"]) == ("2023-06-01", "2025-01-01")
        assert [r["id"] for r in runs.list_runs()] == [record["id"]]

    def test_only_trades_decided_in_the_period_count(self, lab):
        record = runs.run(
            config(start="2024-06-01"), loader=loader, venue=venue, save=False
        )
        first = min(int(p[0]) for p in record["curve"])
        assert first >= 1_717_200_000  # 2024-06-01

    def test_the_reserved_months_are_refused(self, lab):
        with pytest.raises(ReservedPeriod):
            runs.run(config(end="2025-06-01"), loader=loader, venue=venue)
        assert runs.list_runs() == [] and experiment.trials() == []

    def test_a_stopped_run_saves_nothing(self, lab):
        stop = threading.Event()
        stop.set()
        with pytest.raises(runs.Stopped):
            runs.run(config(), loader=loader, venue=venue, stop=stop)
        assert runs.list_runs() == [] and experiment.trials() == []

    def test_a_run_with_the_market_regime_gate_runs(self, lab):
        # The run passes load_universe a tz-aware start; a gate's context series used
        # to stop there ("Cannot pass a datetime or Timestamp with tzinfo").
        gate = {"id": "OVL-REGIME", "params": {"reference": "self", "sma_days": 50}}
        gated = runs.run(
            config(overlays=[gate]), loader=loader, venue=venue, save=False
        )
        plain = runs.run(config(), loader=loader, venue=venue, save=False)
        assert gated["strategy"]["overlays"][0]["id"] == "OVL-REGIME"
        assert gated["strategy_result"]["trades"] <= plain["strategy_result"]["trades"]

    def test_the_rate_and_the_coins_are_required(self, lab):
        with pytest.raises(ValueError, match="rate"):
            runs.run(config(gbp_usd=0), loader=loader, venue=venue)
        with pytest.raises(ValueError, match="coin"):
            runs.run(config(coins=[]), loader=loader, venue=venue)

    def test_the_drawdown_at_the_lows_is_recorded_and_shown(self, lab):
        record = runs.run(config(), loader=loader, venue=venue, save=False)
        for part in ("strategy_result", "buy_and_hold"):
            s = record[part]
            assert s["intrabar_max_drawdown"] >= s["max_drawdown"]
            if s["halt_reached"]:
                assert s["intrabar_halt_reached"] <= s["halt_reached"]
        assert "valued at each bar's low" in ui.notes(record)
        # a run saved before these figures were recorded still shows its notes
        old = dict(record)
        old["strategy_result"] = {
            k: v
            for k, v in record["strategy_result"].items()
            if not k.startswith("intrabar_")
        }
        assert "each bar's low" not in ui.notes(old)
        assert "Logged as an exploratory run." in ui.notes(old)


def research(*ids):
    return {"strategy": {"research_enabled": list(ids)}}


class TestOffered:
    def test_only_strategies_and_stops_enabled_for_research(self):
        assert ui.research_strategies({}) == ["STRAT-000", "STRAT-001", "STRAT-002"]
        assert "STRAT-004" in ui.research_strategies(research("STRAT-004", "STRAT-001"))
        assert ui.research_strategies(research("STRAT-003")) == []  # needs a model
        assert ui.research_overlays(research("OVL-REGIME")) == ["OVL-REGIME"]


def pump(win, until, seconds=20.0):
    end = time.time() + seconds
    while time.time() < end:
        win.update()
        if until():
            return True
        time.sleep(0.02)
    return False


def open_window(root, run_fn=None, settings=None):  # noqa: F811
    win = ui.BacktestWindow(
        root, settings or research("STRAT-004", "OVL-REGIME"), ["AAA", "BBB"], run_fn
    )
    win.withdraw()
    win.rate_var.set("1.25")
    return win


class TestWindow:
    def test_wrong_inputs_are_explained_and_nothing_runs(self, root):  # noqa: F811
        calls = []
        win = open_window(root, run_fn=lambda c, **kw: calls.append(c))
        win.end_var.set("2025-07-01")
        assert not win.start()
        assert "end by 2025-05-06" in win.status_var.get()
        win.end_var.set("2025-01-01")
        win.rate_var.set("")
        assert not win.start() and "rate" in win.status_var.get()
        win.rate_var.set("1.25")
        for c in win.coin_on.values():
            c.set(False)
        assert not win.start() and "coin" in win.status_var.get()
        win.coin_on["AAA"].set(True)
        win.param_vars["exit_days"].set("70")
        assert (
            not win.start() and "fewer than the breakout days" in win.status_var.get()
        )
        assert calls == []
        win.destroy()

    def test_a_run_shows_its_results(self, root, lab):  # noqa: F811
        def fake(config, stop=None, progress=None):
            progress("Reading candles")
            return runs.run(config, loader=loader, venue=venue, stop=stop)

        win = open_window(root, run_fn=fake)
        win.end_var.set("2025-01-01")
        win.param_vars["entry_days"].set("20")
        win.param_vars["exit_days"].set("10")
        assert win.start()
        assert pump(win, lambda: win.result is not None)
        rows = [
            win.summary.tree.item(i, "values") for i in win.summary.tree.get_children()
        ]
        assert [r[0] for r in rows] == [
            "This strategy",
            "Buy and hold",
            "Cash",
            "Random entries (median of 200)",
        ]
        assert win.per_coin.tree.get_children()
        assert "Logged as an exploratory run." in win.notes_var.get()
        assert win.status_var.get() == "Done."
        assert runs.list_runs()
        win.destroy()

    def test_stop_ends_a_run_without_saving(self, root, lab):  # noqa: F811
        started = threading.Event()

        def slow(config, stop=None, progress=None):
            started.set()
            stop.wait(10)
            raise runs.Stopped("stopped")

        win = open_window(root, run_fn=slow)
        win.end_var.set("2025-01-01")
        assert win.start()
        assert pump(win, started.is_set)
        win.stop()
        assert pump(win, lambda: "Stopped" in win.status_var.get())
        assert runs.list_runs() == []
        win.destroy()

    def test_the_words_state_facts_only(self, root, lab):  # noqa: F811
        win = open_window(root)
        texts = []

        def walk(w):
            for child in w.winfo_children():
                try:
                    texts.append(str(child.cget("text")))
                except Exception:
                    pass
                walk(child)

        walk(win)
        record = runs.run(config(), loader=loader, venue=venue, save=False)
        texts.append(ui.notes(record))
        texts += [str(v) for row in ui.summary_rows(record) for v in row]
        texts += list(ui.SUMMARY_HEADINGS.values()) + list(ui.COMPARE_HEADINGS.values())
        for text in texts:
            for banned in BANNED:
                assert banned not in text, (banned, text)
        win.destroy()


class TestCompare:
    def test_the_saved_runs_are_listed_and_searchable(self, root, lab):  # noqa: F811
        a = runs.run(config(), loader=loader, venue=venue, now=1_800_000_000)
        b = runs.run(
            config(coins=["AAA"]), loader=loader, venue=venue, now=1_800_000_100
        )
        win = ui.CompareWindow(root)
        win.withdraw()
        rows = [win.table.tree.item(i, "values") for i in win.table.tree.get_children()]
        assert len(rows) == 2
        win.search.var.set("BBB")
        win.search.now()
        rows = [win.table.tree.item(i, "values") for i in win.table.tree.get_children()]
        assert len(rows) == 1 and "BBB" in rows[0][3]
        assert {a["id"], b["id"]} == {r["id"] for r in runs.list_runs()}
        win.destroy()


class TestStrategyWindow:
    def test_the_strategy_window_opens_both_with_its_current_ticks(
        self, root, folder
    ):  # noqa: F811
        win = ssui.StrategySettingsWindow(
            root,
            manager_factory=lambda: manager(folder),
            messagebox=Box(),
            coins_factory=lambda: ["AAA"],
        )
        win.withdraw()
        win.research_on["STRAT-004"].set(True)  # ticked, not yet saved
        backtest = win.open_backtest()
        backtest.withdraw()
        assert "STRAT-004" in backtest.strategies
        assert backtest.coins == ["AAA"]
        compare = win.open_compare()
        compare.withdraw()
        assert isinstance(compare, ui.CompareWindow)
        win.destroy()
