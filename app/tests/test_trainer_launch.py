"""FDS-108a review item 2: the hub runs the program folder's trainer for every
coin, with the coin's neural folder under the user data folder as its working
directory, and a trainer script saved in Settings is used by the next launch
without a restart. ``subprocess.Popen`` is patched: no process is started."""

import ast
import io
import os
import sys
import tkinter as tk
from tkinter import ttk
from unittest import mock

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_hub  # noqa: E402
import pt_paths  # noqa: E402

TRAINER = os.path.join(pt_paths.program_dir(), "pt_trainer.py")
# Another trainer script shipped in the program folder (what a user could type
# into Settings); only its path is checked, it is never run.
STANDALONE = os.path.join(pt_paths.program_dir(), "pt_trainer_standalone.py")


class Var:
    """Stands in for the Trainers tab's coin selector (a tk.StringVar)."""

    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeTrainerProcess:
    """What the patched Popen returns: still running when the hub checks right
    after the launch, finished when the log reader asks next."""

    def __init__(self, args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.pid = 4242
        self.returncode = None
        self.stdout = io.StringIO("")
        self._polls = 0

    def poll(self):
        self._polls += 1
        if self._polls > 1:
            self.returncode = 0
        return self.returncode


class Launches(list):
    """The fake processes, in launch order; ``errors``: error boxes shown."""

    def __init__(self):
        super().__init__()
        self.errors = []


@pytest.fixture
def launches(monkeypatch, tmp_path):
    """Trainer launches through a patched Popen. The CWD is a temp folder, so
    a script name resolved against the CWD (instead of the program folder)
    would not be found."""
    monkeypatch.chdir(tmp_path)
    started = Launches()

    def popen(args, **kwargs):
        proc = FakeTrainerProcess(args, **kwargs)
        started.append(proc)
        return proc

    monkeypatch.setattr(pt_hub.subprocess, "Popen", popen)
    monkeypatch.setattr(
        pt_hub.messagebox, "showerror", lambda *args, **kwargs: started.errors.append(args)
    )
    return started


def make_hub(coins=("BTC", "ETH"), root=False):
    """A PowerTraderHub without its main window: the path set-up of __init__
    (the same calls) plus what start_trainer_for_selected_coin uses. With
    ``root`` it is also a real, hidden Tk root, so the real Settings window can
    be opened on it."""
    hub = pt_hub.PowerTraderHub.__new__(pt_hub.PowerTraderHub)
    if root:
        tk.Tk.__init__(hub)
        hub.withdraw()
    else:
        hub.tk = None  # a missing attribute raises AttributeError (no Tk recursion)
        hub.after = lambda *args, **kwargs: None
    hub.settings = hub._load_settings()
    hub.settings["coins"] = list(coins)
    hub.project_dir = pt_paths.program_dir()
    hub.settings["main_neural_dir"] = pt_paths.neural_dir(hub.settings.get("main_neural_dir"))
    hub.hub_dir = pt_paths.hub_dir_for(hub.settings.get("hub_data_dir"))
    hub.coins = list(coins)
    hub._ensure_alt_coin_folders_and_trainer_on_startup()
    hub.coin_folders = pt_hub.build_coin_folders(hub.settings["main_neural_dir"], hub.coins)
    hub.proc_neural = pt_hub.ProcInfo(name="Neural Runner", path="")
    hub._refresh_trainer_path()
    hub.trainers = {}
    hub.trainer_coin_var = Var()
    hub.status = mock.Mock()
    hub._multi_exchange = None  # read by refresh_exchange_settings on Settings save
    return hub


def launch(hub, coin, launches):
    """Start training ``coin`` through the hub's own method; return the launch."""
    count = len(launches)
    hub.trainer_coin_var.set(coin)
    hub.start_trainer_for_selected_coin()
    assert launches.errors == []
    assert len(launches) == count + 1, f"no trainer was started for {coin}"
    hub.trainers[coin].thread.join(timeout=5)  # the log reader saw the exit
    return launches[-1]


def assert_in_user_data(path, home):
    """``path`` is in the user data folder (inside POWERTRADER_HOME), never in
    the program/install folder."""
    data = pt_paths.data_dir()
    assert os.path.commonpath([data, os.path.abspath(home)]) == os.path.abspath(home)
    assert os.path.commonpath([os.path.abspath(path), data]) == data, path
    assert not pt_paths.is_inside_program_dir(path), path


@pytest.mark.parametrize("coin, sub", [("BTC", ()), ("ETH", ("ETH",))])
def test_every_coin_runs_the_program_folder_trainer_in_its_user_data_folder(
    coin, sub, launches, isolated_user_dirs
):
    hub = make_hub()
    folder = os.path.join(pt_paths.models_dir(), *sub)
    stale = os.path.join(folder, "memories_1hour.txt")
    with open(stale, "w", encoding="utf-8") as f:
        f.write("old")

    call = launch(hub, coin, launches)

    assert call.args == [sys.executable, "-u", "-W", "ignore", TRAINER, coin]
    assert os.path.isfile(TRAINER)
    assert hub.proc_trainer_path == TRAINER
    assert call.kwargs["cwd"] == folder
    assert_in_user_data(call.kwargs["cwd"], isolated_user_dirs["home"])
    assert call.kwargs["env"]["POWERTRADER_HUB_DIR"] == pt_paths.hub_dir()
    # old training files are cleared from the coin folder; no trainer is copied in
    assert not os.path.exists(stale)
    assert [n for n in os.listdir(folder) if n.endswith(".py")] == []


def trainer_results_expression():
    """The expression ``NeuralTrainer.train`` assigns to ``results_file`` and
    opens for writing, read from app/pt_trainer.py (training is not run)."""
    with open(TRAINER, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=TRAINER)
    trainer = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "NeuralTrainer"
    )
    train = next(
        n for n in trainer.body if isinstance(n, ast.FunctionDef) and n.name == "train"
    )
    assigned = [
        n.value
        for n in ast.walk(train)
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "results_file" for t in n.targets)
    ]
    opened = [
        n
        for n in ast.walk(train)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "open"
        and n.args
        and isinstance(n.args[0], ast.Name)
        and n.args[0].id == "results_file"
    ]
    assert len(assigned) == 1, "results_file should be assigned once"
    assert [ast.literal_eval(n.args[1]) for n in opened] == ["w"]
    return assigned[0]


def test_the_trainer_writes_its_results_to_the_user_data_folder(isolated_user_dirs):
    expression = trainer_results_expression()
    assert ast.unparse(expression.func) == "pt_paths.data_file"
    code = compile(ast.Expression(expression), TRAINER, "eval")
    for coin in ("BTC", "ETH"):
        # the trainer's own expression, evaluated for this coin
        written = eval(code, {"pt_paths": pt_paths}, {"coin": coin})
        expected = pt_paths.data_file("training_results", f"{coin.lower()}_training_results.json")
        assert written == expected
        assert_in_user_data(written, isolated_user_dirs["home"])


# --- Settings save -> next launch, without a restart ------------------------------------------


@pytest.fixture
def root_hub():
    try:
        hub = make_hub(root=True)
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    yield hub
    hub.destroy()


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
        w for w in widgets(win) if isinstance(w, ttk.Label) and str(w.cget("text")) == label
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
        w for w in widgets(win) if isinstance(w, ttk.Button) and str(w.cget("text")) == text
    ).invoke()


def test_a_trainer_script_saved_in_settings_is_used_by_the_next_launch(
    root_hub, launches, isolated_user_dirs, monkeypatch
):
    hub = root_hub
    monkeypatch.setattr(pt_hub, "API_SERVER_AVAILABLE", False)
    saved = mock.Mock()
    monkeypatch.setattr(pt_hub.messagebox, "showinfo", saved)

    assert launch(hub, "BTC", launches).args[4] == TRAINER

    win = open_settings(hub)
    type_into(win, "pt_trainer.py path:", "pt_trainer_standalone.py")
    type_into(win, "Coins (comma):", "BTC,ETH,SOL")
    press(win, "Save")

    assert launches.errors == []
    assert saved.call_args[0][0] == "Saved"
    assert hub._load_settings()["script_neural_trainer"] == "pt_trainer_standalone.py"
    assert hub.proc_trainer_path == STANDALONE
    assert os.path.isfile(STANDALONE)

    # same hub, no restart: the next launches use the saved script
    for coin, folder in (
        ("BTC", pt_paths.models_dir()),
        ("SOL", os.path.join(pt_paths.models_dir(), "SOL")),  # coin added in the same save
    ):
        call = launch(hub, coin, launches)
        assert call.args == [sys.executable, "-u", "-W", "ignore", STANDALONE, coin]
        assert call.kwargs["cwd"] == folder
        assert_in_user_data(call.kwargs["cwd"], isolated_user_dirs["home"])
