"""The auto-retrain schedule: it survives a restart, the Training tab says when the
next retrain starts, and Settings > Training turns it on or off and sets its hours.

Everything runs under the isolation guard (app/conftest.py); no network.
"""

import os
import sys
import time
import types

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_hub  # noqa: E402

Hub = pt_hub.PowerTraderHub
HOUR = 3600.0


def schedule_hub(last_times=None, running=(), enabled=True, hours=6):
    """A hub with the scheduling methods and a recording ``after``."""
    queued = {}

    def after(ms, callback):
        timer = f"after#{len(queued)}"
        queued[timer] = (ms, callback)
        return timer

    hub = types.SimpleNamespace(
        settings={
            "training_auto_enabled": enabled,
            "training_auto_interval_hours": hours,
        },
        master=types.SimpleNamespace(after=after),
        after_cancel=lambda timer: queued.pop(timer, None),
        auto_retrain_timers={},
        auto_retrain_due={},
        coins=["BTC", "ETH", "ZEC"],
        last_training_times=dict(last_times or {}),
        trainers={},
        queued=queued,
    )
    for name in (
        "_auto_retrain_hours",
        "_schedule_auto_retrain",
        "_cancel_auto_retrain",
        "cancel_all_auto_retrains",
        "_resume_auto_retrains",
        "_trainer_status_text",
    ):
        setattr(hub, name, lambda *a, _f=getattr(Hub, name), **k: _f(hub, *a, **k))
    hub._is_trainer_running = lambda coin: coin in running
    return hub


def delay_s(hub, coin):
    ms, _ = hub.queued[hub.auto_retrain_timers[coin]]
    return ms / 1000.0


# --- the schedule survives a restart --------------------------------------------


def test_a_restart_sets_each_trained_coins_retrain_from_its_saved_time():
    now = time.time()
    hub = schedule_hub({"BTC": now - 2 * HOUR, "ETH": now - 5.5 * HOUR})
    hub._resume_auto_retrains()
    assert set(hub.auto_retrain_timers) == {"BTC", "ETH"}  # ZEC was never trained
    assert delay_s(hub, "BTC") == pytest.approx(4 * HOUR, abs=5)
    assert delay_s(hub, "ETH") == pytest.approx(0.5 * HOUR, abs=5)
    assert hub.auto_retrain_due["BTC"] == pytest.approx(now + 4 * HOUR, abs=5)


def test_a_coin_that_fell_due_while_the_hub_was_closed_retrains_a_minute_after_start():
    hub = schedule_hub({"BTC": time.time() - 30 * HOUR})
    hub._resume_auto_retrains()
    assert delay_s(hub, "BTC") == pytest.approx(pt_hub.OVERDUE_RETRAIN_DELAY_S, abs=1)


def test_a_coin_training_now_is_left_to_schedule_itself_when_it_finishes():
    hub = schedule_hub({"BTC": time.time() - HOUR}, running=("BTC",))
    hub._resume_auto_retrains()
    assert hub.auto_retrain_timers == {}


def test_auto_retrain_turned_off_cancels_every_timer():
    hub = schedule_hub({"BTC": time.time() - HOUR})
    hub._resume_auto_retrains()
    assert hub.auto_retrain_timers
    hub.settings["training_auto_enabled"] = False
    hub._resume_auto_retrains()
    assert hub.auto_retrain_timers == {} and hub.auto_retrain_due == {}
    assert hub.queued == {}  # the Tk timers were cancelled too


def test_a_new_interval_moves_each_retrain():
    now = time.time()
    hub = schedule_hub({"BTC": now - 2 * HOUR})
    hub._resume_auto_retrains()
    hub.settings["training_auto_interval_hours"] = 12
    hub._resume_auto_retrains()
    assert delay_s(hub, "BTC") == pytest.approx(10 * HOUR, abs=5)
    assert len(hub.queued) == 1  # the 6-hour timer was cancelled


@pytest.mark.parametrize("hours", [0, -3, "x", float("nan")])
def test_no_usable_interval_means_no_retrain(hours):
    hub = schedule_hub({"BTC": time.time() - HOUR}, hours=hours)
    hub._resume_auto_retrains()
    assert hub.auto_retrain_timers == {}


def test_a_retrain_that_fires_clears_its_time():
    hub = schedule_hub({"BTC": time.time() - HOUR})
    hub._resume_auto_retrains()
    _, retrain = hub.queued[hub.auto_retrain_timers["BTC"]]
    hub.coins = []  # removed: the retrain itself does nothing
    retrain()
    assert hub.auto_retrain_due == {} and hub.auto_retrain_timers == {}


# --- the Training tab's line ------------------------------------------------------


def test_with_no_trainer_running_the_line_says_when_the_next_retrain_starts():
    now = time.time()
    hub = schedule_hub()
    hub.auto_retrain_due = {"ETH": now + 3 * HOUR, "BTC": now + HOUR}
    text = hub._trainer_status_text([])
    assert text == f"idle until {pt_hub._clock(now + HOUR)} (next: BTC, +1 more)"


def test_one_waiting_coin_has_no_count():
    due = time.time() + HOUR
    hub = schedule_hub()
    hub.auto_retrain_due = {"BTC": due}
    assert (
        hub._trainer_status_text([]) == f"idle until {pt_hub._clock(due)} (next: BTC)"
    )


def test_running_trainers_come_first_then_the_next_retrain():
    now = time.time()
    hub = schedule_hub()
    hub.auto_retrain_due = {"ETH": now + HOUR, "BTC": now + 2 * HOUR}
    text = hub._trainer_status_text(["BTC"])
    assert text == f"running: BTC · next: ETH at {pt_hub._clock(now + HOUR)}"
    assert hub._trainer_status_text(["BTC", "ETH"]) == "running: BTC, ETH"


def test_nothing_running_or_scheduled():
    assert schedule_hub()._trainer_status_text([]) == "(no trainers running)"
    assert (
        schedule_hub(enabled=False)._trainer_status_text([])
        == "(no trainers running; auto-retrain off)"
    )


def test_a_time_on_another_day_carries_its_date():
    at = time.mktime((2025, 3, 1, 14, 32, 10, 0, 0, -1))
    assert pt_hub._clock(at) == "01 Mar 14:32:10"  # not today
    soon = time.time() + 1
    assert pt_hub._clock(soon) == time.strftime("%H:%M:%S", time.localtime(soon))


def test_the_trained_for_tooltip_gives_the_coins_next_retrain():
    due = time.time() + 4 * HOUR
    hub = types.SimpleNamespace(
        _training_status={"ZEC": "✅"},
        last_training_times={"ZEC": time.time() - 2 * HOUR},
        settings={"training_auto_enabled": True, "training_auto_interval_hours": 6},
        auto_retrain_due={"ZEC": due},
        _training_signal_info={},
        _signals_engine="catalogue",
    )
    tip = Hub._coin_tooltip(hub, "ZEC", "age")
    assert f"Next auto-retrain: {pt_hub._clock(due)}." in tip


# --- the real hub -------------------------------------------------------------------


@pytest.fixture
def hub_with_saved_times(monkeypatch):
    import helpers_trainer as ht

    now = time.time()

    def saved_times(self):
        coins = list(self.coins)
        self.last_training_times = {coins[0]: now - 2 * HOUR}
        if len(coins) > 1:
            self.last_training_times[coins[-1]] = now - 30 * HOUR

    monkeypatch.setattr(Hub, "_load_existing_training_times", saved_times)
    monkeypatch.setattr(pt_hub, "API_SERVER_AVAILABLE", False)
    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    yield hub
    ht.close_hub(hub)


def test_the_hub_sets_the_retrain_timers_when_it_starts(hub_with_saved_times):
    hub = hub_with_saved_times
    assert set(hub.auto_retrain_timers) == set(hub.last_training_times)
    pending = hub.tk.splitlist(hub.tk.call("after", "info"))
    for timer in hub.auto_retrain_timers.values():
        assert timer in pending
    first = hub.coins[0]
    assert hub.auto_retrain_due[first] == pytest.approx(
        hub.last_training_times[first] + 6 * HOUR, abs=5
    )
    hub._tick()
    assert str(hub.trainer_status_lbl.cget("text")).startswith("idle until ")


def test_settings_training_turns_auto_retrain_off_and_sets_its_hours(
    hub_with_saved_times,
):
    from test_trainer_launch import open_settings, press, type_into, widgets
    from tkinter import ttk

    hub = hub_with_saved_times
    first = hub.coins[0]
    win = open_settings(hub)
    type_into(win, "Retrain every (hours):", "12")
    press(win, "Save")
    assert hub.settings["training_auto_interval_hours"] == 12.0
    assert hub.auto_retrain_due[first] == pytest.approx(
        hub.last_training_times[first] + 12 * HOUR, abs=5
    )

    win = open_settings(hub)
    (box,) = [
        w
        for w in widgets(win)
        if isinstance(w, ttk.Checkbutton)
        and str(w.cget("text")) == "Retrain each trained coin automatically"
    ]
    box.invoke()  # untick
    press(win, "Save")
    assert hub.settings["training_auto_enabled"] is False
    assert hub.auto_retrain_timers == {} and hub.auto_retrain_due == {}


@pytest.mark.parametrize("hours", ["0", "0.5", "400", "six"])
def test_settings_refuses_retrain_hours_out_of_range(hub_with_saved_times, hours):
    from test_trainer_launch import open_settings, press, type_into

    hub = hub_with_saved_times
    win = open_settings(hub)
    type_into(win, "Retrain every (hours):", hours)
    press(win, "Save")
    assert hub.settings.get("training_auto_interval_hours", 6) == 6
    assert any(d[0] == "showerror" for d in hub.test_dialogs)
    win.destroy()


def test_settings_opens_with_a_stored_interval_that_is_not_a_number(
    hub_with_saved_times,
):
    from test_trainer_launch import open_settings, widgets
    from tkinter import ttk

    hub = hub_with_saved_times
    hub.settings["training_auto_interval_hours"] = "x"
    win = open_settings(hub)
    (label,) = [
        w
        for w in widgets(win)
        if isinstance(w, ttk.Label) and str(w.cget("text")) == "Retrain every (hours):"
    ]
    row = int(label.grid_info()["row"])
    (entry,) = [
        w
        for w in label.master.winfo_children()
        if isinstance(w, ttk.Entry) and int(w.grid_info().get("row", -1)) == row
    ]
    assert entry.get() == "6"
    win.destroy()
