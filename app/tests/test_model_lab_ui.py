"""FDS-MH-001 phase D: Settings > Training, "Compare models..." (section 5.9).

* Every batch the window freezes ends on 2026-11-06, so its walk-forward ends at
  2025-05-06 and its held-back months are exactly FDS-SR-001's lockbox.
* Wrong choices are explained and nothing is frozen. The declared batches are ticked by
  their buttons and frozen as declared batches, in their declared order.
* A batch runs off the Tk thread with progress, and its results are shown, one row per
  model, with each row's coins, markets and fee lines. Stop, or closing the window,
  stops it.
* The window lists every saved batch, the newest first, with its state, ticks the last
  batch's choices, and shows the trial count. Its words state facts only.
* Settings > Training opens it, and raises the open one.

Synthetic candles read offline from the candle cache: no network."""

from __future__ import annotations

import gc
import threading
import time
from tkinter import ttk

import pandas as pd
import pytest
from test_model_lab import FEES, RULES_ONLY, START, layer, seed_1h, walk  # noqa: F401
from test_strategy_settings_ui import root  # noqa: F401

import model_lab_ui as ui
from model_lab import batch, catalogue, walkforward
from strategy_lab.windows import LOCKBOX

BANNED = (
    "FDS",
    "STRAT-",
    "OVL-",
    "Binance",
    "KuCoin",
    "Coinbase",
    "Kraken",
    "lockbox",
    "contestant",
    "R1",
    "R2",
    "Holm",
    "rule.",
    "linear.",
    "trees.",
    "pv.",
)
DAYS = 420


@pytest.fixture(autouse=True)
def collect_tk_garbage():
    """A closed window's Tk variables are collected here, on the Tk thread. Collected
    later on a worker thread, each would wait on a test's Tk interpreter that is gone.
    """
    yield
    gc.collect()


def pump(win, until, timeout=60.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        win.update()
        if until():
            return True
        time.sleep(0.02)
    return False


def small_freeze(seen=None):
    """A freeze_fn for the fixture candles: the window's end is checked, then a short
    window is frozen (the real END needs years of bars)."""

    def freeze(coins, start, keys, end=None, declared=None):
        if seen is not None:
            seen.update(coins=coins, start=start, keys=keys, end=end, declared=declared)
        assert end == ui.END
        return batch.freeze(
            coins,
            START,
            keys,
            end=START + pd.Timedelta(days=DAYS),
            fees={c: FEES for c in coins},
            offline=True,
            draws=200,
            months=(4, 2, 2),
            min_shift_days=30,
            now=START + pd.Timedelta(days=DAYS, hours=5),
            declared=declared,
        )

    return freeze


def seed(coins=("BTC", "ETH")):
    for k, coin in enumerate(coins):
        seed_1h(coin, walk(24 * DAYS, seed=10 + k))


def open_window(root, coins=("BTC", "ETH"), **kw):  # noqa: F811
    win = ui.CompareModelsWindow(root, list(coins), **kw)
    win.withdraw()
    return win


def tick_only(win, keys):
    for key, var in win.model_on.items():
        var.set(key in keys)


def rows_of(win):
    tree = win.table.tree
    return [tree.item(i, "values") for i in tree.get_children()]


class TestWindowDates:
    def test_every_batch_ends_where_the_held_back_months_end(self):
        cal = walkforward.make_calendar(ui.DEFAULT_START, ui.END)
        lock = (int(LOCKBOX[0].timestamp()), int(LOCKBOX[1].timestamp()))
        assert tuple(cal.lockbox) == lock
        assert cal.folds[-1][1] == lock[0]  # the walk-forward ends at 2025-05-06
        assert ui.latest_start() == pd.Timestamp("2024-05-06", tz="UTC")

    def test_a_start_too_late_for_a_first_fold_is_refused(self):
        with pytest.raises(ValueError, match="Start before 2024-05-06"):
            ui.parse_start("2024-05-06")
        assert ui.parse_start("2024-05-05") == pd.Timestamp("2024-05-05", tz="UTC")
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            ui.parse_start("soon")


class TestChoices:
    def test_wrong_choices_are_explained_and_nothing_is_frozen(
        self, root
    ):  # noqa: F811
        calls = []
        win = open_window(root, freeze_fn=lambda *a, **k: calls.append(a))
        for var in win.coin_on.values():
            var.set(False)
        assert not win.start() and "coin" in win.status_var.get()
        win.coin_on["BTC"].set(True)
        win.other_var.set("BT-C")
        assert not win.start() and "not a coin symbol" in win.status_var.get()
        win.other_var.set("")
        win.start_var.set("2024-09-01")
        assert not win.start() and "Start before" in win.status_var.get()
        win.start_var.set("2020-01-01")
        tick_only(win, ["ref.always"])  # the reference is not tested
        assert not win.start() and "tested" in win.status_var.get()
        tick_only(win, [])
        assert not win.start() and "tested" in win.status_var.get()
        assert calls == []
        win.destroy()

    def test_typed_coins_join_the_ticked_ones_once(self):
        assert ui.parse_coins(["BTC"], "eth, sol btc;doge") == [
            "BTC",
            "ETH",
            "SOL",
            "DOGE",
        ]

    def test_the_declared_batches_are_ticked_and_frozen_as_declared(
        self, root
    ):  # noqa: F811
        seen = {}

        def freeze(coins, start, keys, end=None, declared=None):
            seen.update(keys=keys, end=end, declared=declared, coins=coins)
            raise batch.BatchError("no candles for BTC: offline")

        win = open_window(root, freeze_fn=freeze)
        win.tick_declared("pv-1")
        assert win.start()
        assert pump(win, lambda: "could not run" in win.status_var.get())
        assert seen["declared"] == "pv-1"
        assert seen["keys"] == list(catalogue.BATCH_PV_1)
        assert seen["end"] == ui.END
        assert "no candles for BTC" in win.status_var.get()

        win.tick_declared("batch-1")
        win.model_on["pv.linear.t1.P.q50"].set(True)  # one more: not a declared batch
        assert win.start()
        assert pump(win, lambda: not win.jobs.busy)
        assert seen["declared"] is None
        order = [k for k, _t in ui.contestant_choices()]
        assert seen["keys"] == sorted(seen["keys"], key=order.index)
        assert set(seen["keys"]) == set(catalogue.BATCH_1) | {"pv.linear.t1.P.q50"}
        win.destroy()

    def test_every_model_in_the_catalogue_is_offered(self):
        keys = [k for k, _t in ui.contestant_choices()]
        assert keys == [c.key for c in catalogue.catalogue()]
        texts = dict(ui.contestant_choices())
        assert texts["ref.always"].endswith("(shown for reference, not tested)")
        assert texts["pv.linear.t1.PVp2.q50"].endswith(
            "(its probabilities only, not tested)"
        )


class TestRun:
    def test_a_batch_runs_and_its_results_are_shown(self, root):  # noqa: F811
        seed()
        seen = {}
        win = open_window(root, freeze_fn=small_freeze(seen))
        tick_only(win, RULES_ONLY)
        assert win.start()
        assert pump(win, lambda: win.status_var.get() == "Done.", timeout=180)
        assert seen["coins"] == ["BTC", "ETH"] and seen["declared"] is None
        rows = rows_of(win)
        assert len(rows) == len(RULES_ONLY)
        assert rows[0][0] == "Enter whenever flat"
        assert rows[0][1] == "Reference only, not tested"
        assert "held back and were not read" in win.summary_var.get()
        assert "Fee a side for every coin: 0.50% plus 0.05% slippage." in (
            win.summary_var.get()
        )
        assert win.trials_var.get() == (
            f"Trials logged so far: {len(RULES_ONLY) - 1} "
            f"(trading {len(RULES_ONLY) - 1})."
        )
        assert win.batch_var.get().endswith("(done)")
        win.table.tree.selection_set("rule.sma20")
        win.update()
        detail = win.detail_var.get()
        assert detail.startswith("Daily close above its 20-day average:")
        assert "BTC: scored from" in detail and "ETH: scored from" in detail
        assert "At half the fee rate" in detail and "Rising markets" in detail
        win.destroy()

    def test_progress_is_shown_and_stop_ends_the_run(self, root):  # noqa: F811
        started = threading.Event()

        def slow(batch_id, progress=None, stop=None):
            progress("fits", 1, 4)
            started.set()
            while not stop():
                time.sleep(0.01)
            return None

        win = open_window(root, freeze_fn=lambda *a, **k: "b1", run_fn=slow)
        assert win.start()
        assert pump(win, lambda: "Fitting models: 1 of 4" in win.status_var.get())
        win.stop()
        assert pump(win, lambda: "Stopped" in win.status_var.get())
        assert "frozen record, marked as stopped" in win.status_var.get()
        win.destroy()

    def test_closing_the_window_stops_a_running_batch(self, root):  # noqa: F811
        started, ended = threading.Event(), threading.Event()

        def slow(batch_id, progress=None, stop=None):
            started.set()
            deadline = time.monotonic() + 10
            while not stop() and time.monotonic() < deadline:
                time.sleep(0.01)
            ended.set()

        win = open_window(root, freeze_fn=lambda *a, **k: "b1", run_fn=slow)
        assert win.start()
        assert pump(win, started.is_set)
        win.destroy()
        assert ended.wait(5)

    def test_a_real_batch_stopped_is_marked_as_stopped(self, root):  # noqa: F811
        seed()

        def stop_at_once(batch_id, progress=None, stop=None):
            return batch.run(batch_id, progress=progress, stop=lambda: True)

        win = open_window(root, freeze_fn=small_freeze(), run_fn=stop_at_once)
        tick_only(win, RULES_ONLY)
        assert win.start()
        assert pump(win, lambda: "Stopped" in win.status_var.get(), timeout=120)
        assert win.batch_var.get().endswith("(stopped)")
        assert "did not finish" in win.summary_var.get()
        assert rows_of(win) == []
        win.destroy()


class TestSavedBatches:
    def test_saved_batches_are_listed_newest_first_and_the_last_choices_ticked(
        self, root  # noqa: F811
    ):
        seed(("BTC", "ETH", "SOL"))
        older = small_freeze()(["BTC", "ETH"], START, RULES_ONLY, end=ui.END)
        newer = batch.freeze(
            ["BTC", "SOL"],
            START,
            ["ref.always", "rule.sma50"],
            end=START + pd.Timedelta(days=DAYS),
            fees={c: FEES for c in ("BTC", "SOL")},
            offline=True,
            draws=200,
            months=(4, 2, 2),
            min_shift_days=30,
            now=START + pd.Timedelta(days=DAYS, hours=6),
        )
        win = open_window(root, coins=("BTC", "ETH"))
        labels = list(win.batch_combo.cget("values"))
        assert labels == [f"{newer} (frozen, not run)", f"{older} (frozen, not run)"]
        assert {k for k, v in win.model_on.items() if v.get()} == {
            "ref.always",
            "rule.sma50",
        }
        assert win.coin_on["BTC"].get() and not win.coin_on["ETH"].get()
        assert win.other_var.get() == "SOL"
        assert win.start_var.get() == START.date().isoformat()
        assert "did not finish" in win.summary_var.get()
        win.batch_var.set(labels[1])
        win._on_batch()
        assert "Coins: BTC, ETH." in win.summary_var.get()
        win.destroy()

    def test_with_no_batch_batch_1_is_ticked(self, root):  # noqa: F811
        win = open_window(root)
        assert {k for k, v in win.model_on.items() if v.get()} == set(catalogue.BATCH_1)
        assert win.summary_var.get() == "No batch has been run yet."
        assert win.trials_var.get() == "Trials logged so far: none."
        win.destroy()


class TestWords:
    def test_the_words_state_facts_only(self, root):  # noqa: F811
        seed()
        win = open_window(root, freeze_fn=small_freeze())
        tick_only(win, RULES_ONLY)
        assert win.start()
        assert pump(win, lambda: win.status_var.get() == "Done.", timeout=180)
        texts = []

        def walk_widgets(w):
            for child in w.winfo_children():
                if "text" in child.keys():  # not an entry's textvariable
                    texts.append(str(child.cget("text")))
                walk_widgets(child)

        walk_widgets(win)
        texts += [win.summary_var.get(), win.trials_var.get(), win.status_var.get()]
        texts += [str(v) for row in rows_of(win) for v in row]
        for key in win.shown["contestants"]:
            texts.append(ui.detail_text(win.shown["contestants"][key]))
        texts += list(ui.HEADINGS.values()) + list(ui.STATES.values())
        texts += [t for _k, t in ui.contestant_choices()] + [ui.CANDLES_TEXT]
        texts += list(win.batch_combo.cget("values"))
        for text in texts:
            for banned in BANNED:
                assert banned not in text, (banned, text)
        win.destroy()


@pytest.fixture
def hub(monkeypatch):
    import helpers_trainer as ht
    import pt_hub

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    monkeypatch.setattr(pt_hub, "API_SERVER_AVAILABLE", False)
    yield hub
    ht.close_hub(hub)


def test_settings_training_opens_compare_models(hub):
    from test_trainer_launch import open_settings, press, widgets

    win = open_settings(hub)
    texts = [
        str(w.cget("text"))
        for w in widgets(win)
        if isinstance(w, (ttk.Label, ttk.Button)) and "text" in w.keys()
    ]
    assert "Compare models..." in texts
    press(win, "Compare models...")
    models = hub._compare_models_window
    assert isinstance(models, ui.CompareModelsWindow)
    models.withdraw()
    assert models.coins == [c for c in hub.coins if c]
    press(win, "Compare models...")  # raises the open one rather than opening another
    assert hub._compare_models_window is models
    models.destroy()
    win.destroy()
