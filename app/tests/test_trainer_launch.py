"""FDS-108a review item 2 and #136: the hub runs the program folder's trainer for
every coin, with the coin's neural folder under the user data folder as its
working directory; a trainer script saved in Settings is used by the next launch
without a restart; and a launch runs to completion.

Every test builds the hub with its real ``__init__`` and starts real processes
through ``start_trainer_for_selected_coin`` (helpers_trainer). The children load
a guard that blocks the network and records what each child saw: its command
line, working folder and environment."""

import os
import sys
import time
from tkinter import ttk

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
for _path in (APP_DIR, TESTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import helpers_trainer as ht  # noqa: E402
import pt_hub  # noqa: E402
import pt_paths  # noqa: E402

TRAINER = os.path.join(
    pt_paths.program_dir(), pt_hub.DEFAULT_SETTINGS["script_neural_trainer"]
)
# Another trainer script shipped in the program folder (what a user could type
# into Settings).
STANDALONE = os.path.join(pt_paths.program_dir(), "pt_trainer_standalone.py")


@pytest.fixture
def records(monkeypatch, tmp_path, isolated_user_dirs):
    """Folder the guarded trainer processes write their records to. The CWD is
    a temp folder, so a script name resolved against the CWD (instead of the
    program folder) would not be found."""
    monkeypatch.chdir(tmp_path)
    return ht.guard_trainer_children(monkeypatch, tmp_path)


@pytest.fixture
def real_hub(monkeypatch, records):
    hub = ht.build_real_hub(monkeypatch)
    yield hub
    ht.close_hub(hub)
    assert hub.test_callback_errors == []


def launched(hub, coin, records, timeout=120):
    """Start training ``coin`` through the hub and wait for the process to end.
    Returns the record the process wrote about itself."""
    count = len(ht.child_records(records))
    lp = ht.launch(hub, coin)
    if lp is not None:
        ht.wait(lp, timeout=timeout)
    deadline = time.time() + timeout
    while time.time() < deadline and not ht.child_errors(records):
        done = [r for r in ht.child_records(records)[count:] if r.get("final")]
        if done:
            assert len(done) == 1, done
            return done[0]
        time.sleep(0.1)
    pytest.fail(
        f"no record from a guarded trainer process for {coin}: "
        f"{ht.child_errors(records)}"
    )


def assert_in_user_data(path, home):
    """``path`` is in the user data folder (inside POWERTRADER_HOME), never in
    the program/install folder."""
    data = pt_paths.data_dir()
    assert os.path.commonpath([data, os.path.abspath(home)]) == os.path.abspath(home)
    assert os.path.commonpath([os.path.abspath(path), data]) == data, path
    assert not pt_paths.is_inside_program_dir(path), path


def assert_launch(record, script, coin, folder, home):
    """The process saw exactly the hub's command line, folder and environment."""
    assert os.path.normcase(record["orig_argv"][0]) == os.path.normcase(sys.executable)
    assert record["orig_argv"][1:] == ["-u", "-W", "ignore", script, coin]
    assert os.path.normcase(record["cwd_at_start"]) == os.path.normcase(folder)
    assert_in_user_data(record["cwd_at_start"], home)
    assert record["env"]["POWERTRADER_HOME"] == home
    assert record["env"]["POWERTRADER_HUB_DIR"] == pt_paths.hub_dir()
    assert record["env"]["PYTHON_KEYRING_BACKEND"] == ht.FAIL_KEYRING
    assert record["credential_env"] == []


def test_every_coin_runs_the_program_folder_trainer_in_its_user_data_folder(
    real_hub, records, isolated_user_dirs
):
    hub = real_hub
    home = isolated_user_dirs["home"]
    assert pt_hub.DEFAULT_SETTINGS["script_neural_trainer"] == "pt_trainer.py"
    assert hub.proc_trainer_path == TRAINER  # set by __init__ (_refresh_trainer_path)
    assert os.path.isfile(TRAINER)

    for coin, sub in (("BTC", ()), ("ETH", ("ETH",))):
        folder = os.path.join(pt_paths.models_dir(), *sub)
        stale = os.path.join(folder, "memories_1hour.txt")
        with open(stale, "w", encoding="utf-8") as f:
            f.write("old")

        record = launched(hub, coin, records)

        assert_launch(record, TRAINER, coin, folder, home)
        # old training files are cleared from the coin folder; no trainer is copied in
        assert not os.path.exists(stale)
        assert [n for n in os.listdir(folder) if n.endswith(".py")] == []
    assert hub.test_dialogs == []


def test_a_launch_runs_to_completion_with_the_ticker_served_from_a_fixture(
    real_hub, records, isolated_user_dirs, monkeypatch
):
    """The real trainer runs to completion as the hub starts it, with the
    network blocked. The only market data it gets is the Binance price ticker,
    answered with the last close of a recorded ETH candle file (the real
    DataProvider turns that one price into one candle). Its model files land in
    the coin's neural folder and its summary in the user data folder; no file
    in the program folder, and no trainer output anywhere in the install
    folder, changes (bytecode writing is disabled in the child)."""
    hub = real_hub
    monkeypatch.setenv(
        "PT_TEST_TICKER_CSV", os.path.join(ht.FIXTURES_DIR, "ETHUSDT_1h.csv")
    )
    before = ht.program_folder_state()

    lp = ht.launch(hub, "ETH")
    assert lp is not None, (
        ht.child_errors(records) or "the hub did not keep the process"
    )
    code, lines = ht.wait(lp)

    assert code == 0, lines[-20:]
    folder = os.path.join(pt_paths.models_dir(), "ETH")
    assert sorted(ht.model_files(folder)) == ht.expected_model_file_names()
    assert os.path.isfile(os.path.join(folder, "trainer_last_training_time.txt"))
    assert os.path.isfile(
        os.path.join(
            pt_paths.data_dir(), "training_results", "eth_training_results.json"
        )
    )
    (record,) = [r for r in ht.child_records(records) if r.get("final")]
    assert_launch(record, TRAINER, "ETH", folder, isolated_user_dirs["home"])
    assert record["blocked"] == []  # no network was attempted
    assert ht.program_folder_state() == before
    assert hub.test_dialogs == []


# --- Settings save -> next launch, without a restart ------------------------------------------


def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)


def open_settings(hub):
    """Open the real Settings window on ``hub``; return its Toplevel."""
    before = {str(w) for w in hub.winfo_children()}
    hub.open_settings_dialog()
    (win,) = [w for w in hub.winfo_children() if str(w) not in before]
    win.withdraw()
    return win


def type_into(win, label, value):
    """Replace the text of the Settings field on the row labelled ``label``."""
    lbl = next(
        w
        for w in widgets(win)
        if isinstance(w, ttk.Label) and str(w.cget("text")) == label
    )
    row = int(lbl.grid_info()["row"])
    entry = next(
        w
        for w in lbl.master.winfo_children()
        if isinstance(w, ttk.Entry) and int(w.grid_info().get("row", -1)) == row
    )
    entry.delete(0, "end")
    entry.insert(0, value)


def press(win, text):
    next(
        w
        for w in widgets(win)
        if isinstance(w, ttk.Button) and str(w.cget("text")) == text
    ).invoke()


def test_a_trainer_script_saved_in_settings_is_used_by_the_next_launch(
    real_hub, records, isolated_user_dirs
):
    hub = real_hub
    home = isolated_user_dirs["home"]

    assert launched(hub, "BTC", records)["orig_argv"][4] == TRAINER

    win = open_settings(hub)
    type_into(win, "pt_trainer.py path:", "pt_trainer_standalone.py")
    type_into(win, "Coins (comma):", "BTC,ETH,SOL")
    press(win, "Save")

    assert [d for d in hub.test_dialogs if d[0] != "showinfo"] == []
    assert [d[1][0] for d in hub.test_dialogs if d[0] == "showinfo"] == ["Saved"]
    assert hub._load_settings()["script_neural_trainer"] == "pt_trainer_standalone.py"
    assert hub.proc_trainer_path == STANDALONE
    assert os.path.isfile(STANDALONE)

    # same hub, no restart: the next launches use the saved script
    for coin, folder in (
        ("BTC", pt_paths.models_dir()),
        (
            "SOL",
            os.path.join(pt_paths.models_dir(), "SOL"),
        ),  # coin added in the same save
    ):
        assert_launch(launched(hub, coin, records), STANDALONE, coin, folder, home)
