"""Training a coin no longer stops the Neural Runner, the hub says why a process
ended, trained coins are shown as trained, and retraining asks first.

Everything runs under the isolation guard (app/conftest.py); no network.
"""

import json
import os
import queue
import subprocess
import sys
import threading
import types
from unittest import mock

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_hub  # noqa: E402

Hub = pt_hub.PowerTraderHub


class Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class RunningProc:
    pid = 4242
    stdout = None

    def poll(self):
        return None


def training_hub(folder):
    trainer = os.path.join(folder, "pt_trainer.py")
    with open(trainer, "w", encoding="utf-8") as f:
        f.write("# stand-in\n")
    return types.SimpleNamespace(
        trainer_coin_var=Var("BTC"),
        coins=["BTC"],
        coin_folders={"BTC": folder},
        settings={"main_neural_dir": folder},
        proc_trainer_path=trainer,
        trainers={},
        hub_dir=folder,
        proc_neural=types.SimpleNamespace(proc=RunningProc()),
        runner_log_q=queue.Queue(),
        status=mock.Mock(),
        after=mock.Mock(),
        _reader_thread=mock.Mock(),
        stop_neural=mock.Mock(side_effect=AssertionError("runner stopped")),
        _trainer_launch_allowed=lambda coin: True,
    )


def drain(q):
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


def test_training_a_coin_keeps_the_runner_running(tmp_path):
    folder = str(tmp_path)
    stamp = os.path.join(folder, "trainer_last_training_time.txt")
    with open(stamp, "w", encoding="utf-8") as f:
        f.write("1")
    hub = training_hub(folder)
    with mock.patch.object(
        pt_hub.subprocess, "Popen", return_value=RunningProc()
    ), mock.patch.object(pt_hub.time, "sleep"):
        Hub.start_trainer_for_selected_coin(hub)
    hub.stop_neural.assert_not_called()
    assert "BTC" in hub.trainers
    # the old stamp is gone, so the runner skips BTC until the new model is saved
    assert not os.path.exists(stamp)
    assert drain(hub.runner_log_q) == [
        "[RUNNER] [training BTC: the runner skips BTC until its new model is saved]"
    ]


def test_stopping_the_runner_says_why():
    hub = types.SimpleNamespace(
        proc_neural=types.SimpleNamespace(proc=RunningProc()),
        runner_log_q=queue.Queue(),
        _stop_process=mock.Mock(),
    )
    Hub.stop_neural(hub)
    Hub.stop_neural(hub, reason="stopped: the hub is closing")
    assert drain(hub.runner_log_q) == [
        "[RUNNER] [stopped with the ■ button]",
        "[RUNNER] [stopped: the hub is closing]",
    ]


def test_the_log_shows_the_exit_code():
    hub = types.SimpleNamespace(_exit_note=Hub._exit_note)
    q = queue.Queue()
    for code in (0, 3):
        proc = subprocess.Popen(
            [sys.executable, "-c", f"print('hi'); raise SystemExit({code})"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        Hub._reader_thread(hub, proc, q, "[X] ")
        assert drain(q) == ["[X] hi", f"[X] [process exited, code {code}]"]


def test_a_stop_the_hub_asked_for_is_not_reported_as_a_crash():
    hub = types.SimpleNamespace(_exit_note=Hub._exit_note)
    hub._note_stop_requested = lambda proc: Hub._note_stop_requested(hub, proc)
    q = queue.Queue()
    proc = subprocess.Popen(
        [sys.executable, "-c", "raise SystemExit(1)"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    hub._note_stop_requested(proc)
    Hub._reader_thread(hub, proc, q, "[X] ")
    assert drain(q) == ["[X] [process exited, code 1 - stopped from the hub]"]
    assert hub._stop_requested_pids == set()  # a reused pid is not mislabelled


def test_stopping_the_trader_says_why():
    hub = types.SimpleNamespace(
        proc_trader=types.SimpleNamespace(proc=RunningProc()),
        trader_log_q=queue.Queue(),
        _stop_process=mock.Mock(),
    )
    Hub.stop_trader(hub)
    assert drain(hub.trader_log_q) == ["[TRADER] [stopped with the ■ button]"]
    hub._stop_process.assert_called_once_with(hub.proc_trader)


def test_a_trained_coin_is_shown_as_trained():
    import ui_theme

    hub = types.SimpleNamespace(_is_recently_trained=lambda coin, hours_threshold: True)
    assert Hub._get_status_border_color(hub, "✅", "BTC") == pt_hub.STATUS_GREEN
    assert Hub._get_status_border_color(hub, "●", "BTC") == pt_hub.STATUS_AMBER
    idle = ui_theme.active_palette()["MUTED"]  # the dark or the paper grey
    assert Hub._get_status_border_color(hub, "❌", "BTC") == idle


def click_hub(trained, running=False, allowed=True):
    return types.SimpleNamespace(
        _is_trainer_running=lambda coin: running,
        _trainer_launch_allowed=lambda coin: allowed,
        _coin_is_trained=lambda coin: trained,
        _get_training_hours=lambda coin: "0.5h",
        train_coin_var=Var(),
        trainer_coin_var=Var(),
        train_selected_coin=mock.Mock(),
        stop_trainer_for_selected_coin=mock.Mock(),
    )


@pytest.mark.parametrize("answer", [False, True])
def test_retraining_a_trained_coin_asks_first(answer):
    hub = click_hub(trained=True)
    with mock.patch.object(pt_hub.messagebox, "askyesno", return_value=answer) as ask:
        Hub._make_coin_click_handler(hub, "BTC")()
    assert "deletes its current model files" in ask.call_args.args[1]
    assert hub.train_selected_coin.called is answer


def test_a_refused_trainer_is_reported_before_asking_to_retrain():
    hub = click_hub(trained=True, allowed=False)
    with mock.patch.object(pt_hub.messagebox, "askyesno") as ask:
        Hub._make_coin_click_handler(hub, "BTC")()
    ask.assert_not_called()  # no "Retrain?" for a run that cannot start
    hub.train_selected_coin.assert_not_called()


def test_an_untrained_coin_trains_without_asking():
    hub = click_hub(trained=False)
    with mock.patch.object(pt_hub.messagebox, "askyesno") as ask:
        Hub._make_coin_click_handler(hub, "BTC")()
    ask.assert_not_called()
    hub.train_selected_coin.assert_called_once()


@pytest.mark.parametrize("answer", [False, True])
def test_stopping_a_training_asks_first(answer):
    hub = click_hub(trained=False, running=True)
    with mock.patch.object(pt_hub.messagebox, "askyesno", return_value=answer):
        Hub._make_coin_click_handler(hub, "BTC")()
    assert hub.stop_trainer_for_selected_coin.called is answer


def test_train_all_asks_before_replacing_models():
    hub = types.SimpleNamespace(
        coins=["ZEC", "BTC"],
        _trainer_launch_allowed=lambda coin: True,
        _coin_is_trained=lambda coin: coin == "BTC",
        trainer_coin_var=Var(),
        start_trainer_for_selected_coin=mock.Mock(),
    )
    with mock.patch.object(pt_hub.messagebox, "askyesno", return_value=False) as ask:
        Hub.train_all_coins(hub)
    assert "current models of BTC" in ask.call_args.args[1]
    hub.start_trainer_for_selected_coin.assert_not_called()
    with mock.patch.object(pt_hub.messagebox, "askyesno", return_value=True):
        Hub.train_all_coins(hub)
    assert hub.start_trainer_for_selected_coin.call_count == 2


def os_error(winerror):
    err = PermissionError(13, "file in use")
    err.winerror = winerror
    return err


def test_a_read_only_or_locked_file_is_not_retried(tmp_path):
    folder = str(tmp_path)
    with open(os.path.join(folder, "memories_1hour.txt"), "w") as f:
        f.write("old")
    hub = training_hub(folder)
    calls = []

    def remove(path):
        calls.append(path)
        raise os_error(5)  # access denied: waiting cannot help

    # time.sleep is the process's: count only this thread's waits, not those of a
    # background thread an earlier test left running
    here, waits = threading.current_thread(), []

    def sleep(seconds):
        if threading.current_thread() is here:
            waits.append(seconds)

    with mock.patch.object(pt_hub.os, "remove", side_effect=remove), mock.patch.object(
        pt_hub.subprocess, "Popen", return_value=RunningProc()
    ), mock.patch.object(pt_hub.time, "sleep", side_effect=sleep):
        Hub.start_trainer_for_selected_coin(hub)
    assert len(calls) == 1
    assert waits == []


def test_a_file_briefly_open_elsewhere_is_deleted_on_a_retry(tmp_path):
    folder = str(tmp_path)
    path = os.path.join(folder, "memories_1hour.txt")
    with open(path, "w") as f:
        f.write("old")
    hub = training_hub(folder)
    real_remove = os.remove
    calls = []

    def remove(p):
        calls.append(p)
        if len(calls) == 1:
            raise os_error(32)  # sharing violation: the runner is reading it
        real_remove(p)

    with mock.patch.object(pt_hub.os, "remove", side_effect=remove), mock.patch.object(
        pt_hub.subprocess, "Popen", return_value=RunningProc()
    ), mock.patch.object(pt_hub.time, "sleep"):
        Hub.start_trainer_for_selected_coin(hub)
    assert len(calls) == 2 and not os.path.exists(path)


def test_the_stop_button_clears_the_training_mark(tmp_path):
    folder = str(tmp_path)
    status = os.path.join(folder, "trainer_status.json")
    with open(status, "w") as f:
        json.dump({"state": "TRAINING"}, f)
    proc = mock.Mock(pid=7)
    proc.poll.return_value = None
    proc.wait.return_value = 1
    hub = types.SimpleNamespace(
        trainers={"BTC": types.SimpleNamespace(info=types.SimpleNamespace(proc=proc))},
        coin_folders={"BTC": folder},
        status=mock.Mock(),
        _exit_code=Hub._exit_code,
    )
    hub._mark_training_ended = lambda coin, code: Hub._mark_training_ended(
        hub, coin, code
    )
    hub._note_stop_requested = lambda proc: Hub._note_stop_requested(hub, proc)
    Hub.stop_all_trainers(hub)
    proc.terminate.assert_called_once()
    assert hub._stop_requested_pids == {7}  # its exit line will say the hub stopped it
    assert hub.trainers == {}
    with open(status) as f:
        assert json.load(f) == {
            "state": "STOPPED",
            "exit_code": 1,
            "timestamp": mock.ANY,
        }


# --- a coin removed from the coin list (#146) ------------------------------------------


def test_a_coin_not_in_the_coin_list_is_not_trained_in_btcs_folder(tmp_path):
    """A removed coin has no folder of its own. The hub fell back to the root, which
    is BTC's folder, deleted BTC's model files and trained the coin there."""
    folder = str(tmp_path)  # the root: BTC's folder
    model = os.path.join(folder, "memories_1hour.txt")
    with open(model, "w", encoding="utf-8") as f:
        f.write("BTC's model")
    hub = training_hub(folder)
    hub.trainer_coin_var = Var("DOGE")  # no longer in the coin list
    with mock.patch.object(
        pt_hub.subprocess, "Popen", side_effect=AssertionError("trainer started")
    ):
        Hub.start_trainer_for_selected_coin(hub)
    assert hub.trainers == {}
    with open(model, encoding="utf-8") as f:
        assert f.read() == "BTC's model"
    hub.status.config.assert_called_once_with(
        text="Training refused for DOGE: it is not in Coins in Settings"
    )


def test_removing_a_coin_cancels_its_auto_retrain(monkeypatch):
    import helpers_trainer as ht

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    try:
        coins = list(hub.coins)
        keep, drop = coins[0], coins[-1]
        assert keep != drop
        hub.settings["training_auto_enabled"] = True
        for coin in (keep, drop):
            hub._schedule_auto_retrain(coin)
        dropped = hub.auto_retrain_timers[drop]
        hub.settings["coins"] = [c for c in coins if c != drop]
        hub._refresh_coin_dependent_ui(coins)
        assert drop not in hub.auto_retrain_timers
        assert keep in hub.auto_retrain_timers
        assert dropped not in hub.tk.splitlist(hub.tk.call("after", "info"))
    finally:
        ht.close_hub(hub)


def test_a_retrain_that_fires_after_its_coin_was_removed_does_nothing():
    scheduled = {}

    def after(ms, callback):
        scheduled["callback"] = callback
        return "after#1"

    hub = types.SimpleNamespace(
        settings={"training_auto_enabled": True, "training_auto_interval_hours": 6},
        master=types.SimpleNamespace(after=after),
        auto_retrain_timers={},
        coins=["ETH", "ZEC"],
        trainers={},
        trainer_coin_var=Var("ETH"),
        start_trainer_for_selected_coin=mock.Mock(),
        _mock_trainer_refused=lambda: False,
        status=mock.Mock(),
    )
    hub._cancel_auto_retrain = lambda coin: Hub._cancel_auto_retrain(hub, coin)
    Hub._schedule_auto_retrain(hub, "ZEC")
    hub.coins = ["ETH"]  # ZEC removed, its timer somehow not cancelled
    scheduled["callback"]()
    hub.start_trainer_for_selected_coin.assert_not_called()
    assert hub.trainer_coin_var.get() == "ETH"
