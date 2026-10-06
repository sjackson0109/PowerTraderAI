"""FDS-MDL Phase 1 item 6: the old stub trainers carry a ``MOCK - DO NOT USE FOR
DECISIONS`` header, and the hub refuses to launch a marked script unless
``allow_mock_trainer`` is JSON ``true`` in pt_config.json (default false). The hub
tests build the real hub (helpers_trainer) and press nothing but its own methods."""

import os
import sys

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
for _path in (APP_DIR, TESTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import helpers_trainer as ht  # noqa: E402
import pt_hub  # noqa: E402
import pt_paths  # noqa: E402
import pt_settings_manager  # noqa: E402
import trading_mode  # noqa: E402
import trainer_guard  # noqa: E402

STUBS = [
    os.path.join(APP_DIR, *parts)
    for parts in [("pt_trainer.py",), ("pt_trainer_standalone.py",)]
    + [
        (coin, name)
        for name in ("pt_trainer.py", "pt_trainer_standalone.py")
        for coin in ("BNB", "BTC", "DOGE", "ETH", "XRP")
    ]
]
MOCK = os.path.join(pt_paths.program_dir(), "pt_trainer.py")
HEADER = (
    '# MOCK - DO NOT USE FOR DECISIONS (FDS-MDL): sleep-loop "training", formula '
    "accuracy, nothing learned from market data. See docs/dev/TRAINER-AUDIT.md."
)


# --- the marker and the defaults -----------------------------------------------------------


def test_every_stub_trainer_carries_the_mock_header_on_line_2():
    assert len(STUBS) == 12
    for path in STUBS:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        assert lines[0] == "#!/usr/bin/env python3", path
        assert lines[1] == HEADER, path
        assert trainer_guard.is_mock_trainer(path), path


def test_the_default_trainer_is_the_real_one_and_mocks_are_off_by_default():
    real = os.path.join(APP_DIR, trainer_guard.REAL_TRAINER)
    assert not trainer_guard.is_mock_trainer(real)
    assert (
        pt_hub.DEFAULT_SETTINGS["script_neural_trainer"] == trainer_guard.REAL_TRAINER
    )
    defaults = pt_settings_manager.DEFAULT_SETTINGS
    assert defaults["script_neural_trainer"] == trainer_guard.REAL_TRAINER
    assert defaults["allow_mock_trainer"] is False
    assert trainer_guard.read_allow_mock_trainer() is False  # no settings file
    assert not trainer_guard.is_mock_trainer(os.path.join(APP_DIR, "missing.py"))


@pytest.mark.parametrize(
    "value, allowed",
    [
        (True, True),
        (False, False),
        (None, False),
        ("true", False),
        (1, False),
        ("yes", False),
        ({"x": 1}, False),
    ],
)
def test_only_json_true_allows_a_mock(value, allowed):
    if value is not None:
        ht.configure_trainer(allow_mock=value)
    assert trainer_guard.read_allow_mock_trainer() is allowed
    assert (
        trainer_guard.read_allow_mock_trainer({"allow_mock_trainer": value}) is allowed
    )


def test_the_setting_is_read_from_the_trading_settings_file():
    assert pt_paths.settings_file() == trading_mode.default_settings_path()
    message = trainer_guard.refusal_message(MOCK)
    assert MOCK in message
    assert trainer_guard.REAL_TRAINER in message
    assert pt_paths.settings_file() in message
    assert '"allow_mock_trainer": true' in message


# --- the hub ------------------------------------------------------------------------------


@pytest.fixture
def records(monkeypatch, tmp_path, isolated_user_dirs):
    monkeypatch.chdir(tmp_path)
    return ht.guard_trainer_children(monkeypatch, tmp_path)


@pytest.fixture
def mock_hub(monkeypatch, records):
    """A real hub whose saved trainer script is the root mock (gui_settings.json),
    with no allow_mock_trainer setting."""
    ht.configure_trainer(script="pt_trainer.py")
    hub = ht.build_real_hub(monkeypatch)
    hub.test_neural_stops = []
    monkeypatch.setattr(hub, "stop_neural", lambda: hub.test_neural_stops.append(1))
    yield hub
    ht.close_hub(hub)
    assert hub.test_callback_errors == []


def refusals(hub):
    return [d for d in hub.test_dialogs if d[0] == "showerror"]


def test_a_mock_trainer_is_refused_before_anything_is_stopped_or_deleted(
    mock_hub, records
):
    hub = mock_hub
    assert hub.proc_trainer_path == MOCK
    stale = os.path.join(hub.coin_folders["BTC"], "memories_1hour.txt")
    with open(stale, "w", encoding="utf-8") as f:
        f.write("old")

    assert ht.launch(hub, "BTC") is None

    assert refusals(hub) == [
        ("showerror", ("Mock trainer refused", trainer_guard.refusal_message(MOCK)))
    ]
    assert hub.status.cget("text") == "Training refused for BTC: mock trainer"
    assert hub.test_neural_stops == []  # the neural runner is left alone
    with open(stale, encoding="utf-8") as f:
        assert f.read() == "old"  # nothing deleted
    assert ht.child_records(records) == [] and ht.child_errors(records) == []
    assert "BTC" not in hub.trainers


def test_allowing_mocks_takes_effect_at_the_next_launch_without_a_restart(
    mock_hub, records
):
    hub = mock_hub
    assert ht.launch(hub, "BTC") is None
    assert len(refusals(hub)) == 1

    ht.configure_trainer(allow_mock=True)
    lp = ht.launch(hub, "BTC")
    if lp is not None:
        ht.wait(lp, timeout=120)

    assert len(refusals(hub)) == 1  # no second refusal
    assert hub.test_neural_stops == [1]
    (record,) = [r for r in ht.child_records(records) if r.get("final")]
    assert record["orig_argv"][1:] == ["-u", "-W", "ignore", MOCK, "BTC"]


def test_a_string_true_still_refuses(mock_hub, records):
    ht.configure_trainer(allow_mock="true")
    assert ht.launch(mock_hub, "BTC") is None
    assert len(refusals(mock_hub)) == 1
    assert ht.child_records(records) == []


def test_train_all_shows_one_refusal_and_starts_nothing(mock_hub, records):
    hub = mock_hub
    assert len(hub.coins) > 1
    hub.train_all_coins()
    assert refusals(hub) == [
        ("showerror", ("Mock trainer refused", trainer_guard.refusal_message(MOCK)))
    ]
    assert hub.status.cget("text") == "Training refused for all coins: mock trainer"
    assert hub.trainers == {}
    assert ht.child_records(records) == []


def scheduled_retrain(hub, monkeypatch, coin):
    """Schedule ``coin``'s auto-retrain and return the callback the hub queued
    (``after`` is recorded instead of run; the tests process no Tk events)."""
    queued = []
    monkeypatch.setattr(
        hub, "after", lambda ms, func=None, *args: queued.append(func) or "after#0"
    )
    hub._schedule_auto_retrain(coin)
    (retrain,) = queued
    return retrain


def test_an_unattended_retrain_of_a_refused_mock_starts_nothing_and_asks_nothing(
    mock_hub, records, monkeypatch
):
    hub = mock_hub
    scheduled_retrain(hub, monkeypatch, "BTC")()
    assert hub.test_dialogs == []
    assert (
        hub.status.cget("text") == "Auto-retrain skipped for BTC: mock trainer refused"
    )
    assert hub.trainers == {} and hub.test_neural_stops == []
    assert ht.child_records(records) == []
    assert "BTC" not in hub.auto_retrain_timers


def test_an_unattended_retrain_starts_an_allowed_trainer(
    mock_hub, records, monkeypatch
):
    hub = mock_hub
    ht.configure_trainer(allow_mock=True)
    scheduled_retrain(hub, monkeypatch, "BTC")()
    lp = hub.trainers.get("BTC")
    assert lp is not None, ht.child_errors(records)
    assert hub.status.cget("text") == "Auto-retraining BTC (stale data)"
    ht.wait(lp, timeout=120)
    assert hub.test_dialogs == []


def test_an_unattended_retrain_that_starts_nothing_does_not_claim_it_did(
    mock_hub, records, monkeypatch, tmp_path
):
    hub = mock_hub
    hub.proc_trainer_path = str(tmp_path / "missing_trainer.py")
    scheduled_retrain(hub, monkeypatch, "BTC")()
    assert [d[1][0] for d in hub.test_dialogs] == ["Missing trainer"]
    assert hub.status.cget("text") != "Auto-retraining BTC (stale data)"
    assert hub.trainers == {}


def test_an_unattended_retrain_while_the_coin_trains_does_not_claim_a_new_run(
    mock_hub, records, monkeypatch
):
    hub = mock_hub
    ht.configure_trainer(allow_mock=True)
    running = ht.launch(hub, "BTC")
    assert running is not None, ht.child_errors(records)
    hub.status.config(text="manual run")
    scheduled_retrain(hub, monkeypatch, "BTC")()
    assert hub.trainers["BTC"] is running
    assert hub.status.cget("text") == "manual run"
    ht.wait(running, timeout=120)
