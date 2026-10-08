"""Shared helpers for tests that start the trainer through the real hub (#136).

* ``build_real_hub`` runs the real ``PowerTraderHub.__init__``. Only Tk's window
  is hidden, the optional heavy features are switched off through their module
  flags (their tabs become placeholder labels; the exchange system and the API
  server are not started), the paper-mode price fetch is a no-op, and message
  boxes are recorded instead of shown. Nothing replicates ``__init__``.
* ``guard_trainer_children`` puts a ``sitecustomize.py`` on ``PYTHONPATH``, so
  every Python process the hub starts loads it first. It blocks Python-level TCP
  connects, UDP sends and name resolution, writes a record of what the child
  saw (command line, folder, environment, requests), and can serve fixture
  data: the Binance price ticker from a candle CSV, or (as a counterfactual
  only) a candle provider. It fails closed: a child without an absolute
  ``POWERTRADER_HOME`` or the "fail" keyring backend ends with exit code 98,
  any error in the guard ends it with 97, and both write an error file, so a
  test that finds no record knows the guard did not run.
"""

import fnmatch
import gc
import glob
import hashlib
import json
import os
import socket
import time

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
FIXTURES_DIR = os.path.join(TESTS_DIR, "fixtures")
FAIL_KEYRING = "keyring.backends.fail.Keyring"

# Module flags of pt_hub that switch on tabs or services which start threads,
# timers, servers or network feeds.
HEAVY_FLAGS = (
    "EXCHANGE_SUPPORT_AVAILABLE",
    "ORDER_MANAGEMENT_AVAILABLE",
    "LLM_RESEARCH_AVAILABLE",
    "API_SERVER_AVAILABLE",
    "HOLDINGS_MANAGEMENT_AVAILABLE",
    "PORTFOLIO_ANALYTICS_AVAILABLE",
    "ADVANCED_ORDER_AVAILABLE",
    "MARKET_DATA_GUI_AVAILABLE",
    "PORTFOLIO_OPTIMIZER_AVAILABLE",
    "BACKTESTING_FRAMEWORK_AVAILABLE",
    "PERFORMANCE_ATTRIBUTION_AVAILABLE",
    "INSTITUTIONAL_TRADING_AVAILABLE",
)

DIALOGS = ("showerror", "showinfo", "showwarning", "askyesno", "askokcancel")

# The model files the thinker reads (the hub clears these, among others, from a
# coin folder before training: pt_hub.py, start_trainer_for_selected_coin).
MODEL_FILE_PATTERNS = (
    "memories_*.txt",
    "memory_weights_*.txt",
    "neural_perfect_threshold_*.txt",
)
# Everything a trainer run can write, wherever it writes it.
TRAINER_OUTPUT_PATTERNS = MODEL_FILE_PATTERNS + (
    "trainer_last_training_time.txt",
    "trainer_status.json",
    "*_training_results.json",
)
TIMEFRAMES = ("1hour", "2hour", "4hour", "8hour", "12hour", "1day", "1week")
MODEL_FILE_KINDS = (
    "neural_perfect_threshold",
    "memories",
    "memory_weights",
    "memory_weights_high",
    "memory_weights_low",
)

CHILD_SITE = r'''"""sitecustomize for trainer processes started by tests (app/tests/helpers_trainer.py).
Fails closed: 98 without an absolute POWERTRADER_HOME or the "fail" keyring
backend, 97 on any error here; both write child-<pid>-error.txt."""
import os
import sys


def _die(code, message):
    try:
        with open(
            os.path.join(
                os.environ.get("PT_TEST_CHILD_RECORD_DIR", "."),
                "child-%d-error.txt" % os.getpid(),
            ),
            "w",
            encoding="utf-8",
        ) as f:
            f.write(message)
    finally:
        os._exit(code)


if os.environ.get("PT_TEST_TRAINER_CHILD") == "1":
    if not os.path.isabs(os.environ.get("POWERTRADER_HOME", "")):
        _die(98, "POWERTRADER_HOME is not an absolute path")
    if os.environ.get("PYTHON_KEYRING_BACKEND") != "keyring.backends.fail.Keyring":
        _die(98, "PYTHON_KEYRING_BACKEND is not the fail backend")
    try:
        import atexit
        import json
        import socket
        import time

        _blocked = []
        _served = []
        # the pattern trainer's inputs (pt_pattern_trainer.TRAINER_ENV), not credentials
        _TRAINER_ENV = (
            "POWERTRADER_TRAIN_START",
            "POWERTRADER_TRAIN_END",
            "POWERTRADER_TRAIN_SEED",
            "POWERTRADER_CANDLES_OFFLINE",
        )

        def _no_network(*args, **kwargs):
            _blocked.append(repr(args)[:200])
            raise OSError("network blocked in a trainer test process")

        for _name in ("connect", "connect_ex", "sendto", "sendmsg"):
            if hasattr(socket.socket, _name):
                setattr(socket.socket, _name, _no_network)
        for _name in (
            "create_connection",
            "getaddrinfo",
            "gethostbyname",
            "gethostbyname_ex",
        ):
            setattr(socket, _name, _no_network)
        sys.dont_write_bytecode = True

        _record_path = os.path.join(
            os.environ["PT_TEST_CHILD_RECORD_DIR"],
            "child-%d-%d.json" % (os.getpid(), time.time_ns()),
        )
        _record = {
            "pid": os.getpid(),
            "started": time.time(),
            "cwd_at_start": os.getcwd(),
            "env": {
                k: os.environ.get(k)
                for k in (
                    "POWERTRADER_HOME",
                    "POWERTRADER_HUB_DIR",
                    "PYTHON_KEYRING_BACKEND",
                    "PYTHONHASHSEED",
                ) + _TRAINER_ENV
            },
            "credential_env": sorted(
                k for k in os.environ
                if k.startswith("POWERTRADER_")
                and k not in ("POWERTRADER_HOME", "POWERTRADER_HUB_DIR") + _TRAINER_ENV
            ),
            "seed": os.environ.get("PT_TEST_SEED"),
            "ticker_csv": os.path.basename(os.environ.get("PT_TEST_TICKER_CSV", "")),
            "ticker_window": os.environ.get("PT_TEST_TICKER_WINDOW"),
            "candles_provider": os.environ.get("PT_TEST_CANDLES_PROVIDER") == "1",
        }

        def _write(final):
            _record["final"] = final
            _record["orig_argv"] = list(getattr(sys, "orig_argv", []))
            _record["argv"] = list(sys.argv)
            _record["cwd_at_exit"] = os.getcwd()
            _record["served"] = list(_served)
            _record["blocked"] = list(_blocked)
            tmp = _record_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(_record, f, indent=1)
            os.replace(tmp, _record_path)

        def _rows():
            import csv

            with open(os.environ["PT_TEST_TICKER_CSV"], newline="", encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            window = os.environ.get("PT_TEST_TICKER_WINDOW")
            if window:
                lo, hi = (int(x) if x else None for x in window.split(":"))
                rows = rows[lo:hi]
            if not rows:
                raise ValueError("empty fixture window")
            return rows

        if os.environ.get("PT_TEST_TICKER_CSV"):
            _price = _rows()[-1]["close"]
            _record["ticker_price"] = _price
            import requests

            class _TickerResponse:
                status_code = 200

                def __init__(self, symbol):
                    self._symbol = symbol

                def json(self):
                    return {"symbol": self._symbol, "price": _price}

                def raise_for_status(self):
                    return None

            def _get(url, *args, **kwargs):
                marker = "/api/v3/ticker/price?symbol="
                if marker not in str(url):
                    _blocked.append(str(url)[:200])
                    raise OSError("unexpected request in a trainer test process: %s" % url)
                _served.append(str(url))
                return _TickerResponse(str(url).split(marker, 1)[1])

            requests.get = _get

        if os.environ.get("PT_TEST_CANDLES_PROVIDER") == "1":
            # Counterfactual only: candles in the list form the trainer parses,
            # instead of the real DataProvider (which returns one candle as a str).
            import types

            _candles = [
                [int(r["open_time_ms"]), float(r["open"]), float(r["high"]),
                 float(r["low"]), float(r["close"]), float(r["volume"])]
                for r in _rows()
            ]

            class _CandleProvider:
                def is_available(self):
                    return True

                def get_provider_info(self):
                    return "FIXTURE CANDLES (counterfactual)"

                def get_kline_data(self, symbol, timeframe, limit=None, **kwargs):
                    _served.append("candles:%s:%s:%s" % (symbol, timeframe, limit))
                    if timeframe != "1h":
                        return None
                    return [list(c) for c in _candles[-(limit or len(_candles)):]]

            _module = types.ModuleType("pt_data_provider")
            _module.get_data_provider = lambda: _CandleProvider()
            sys.modules["pt_data_provider"] = _module

        if os.environ.get("PT_TEST_SEED") is not None:
            import random

            random.seed(int(os.environ["PT_TEST_SEED"]))

        _write(False)
        atexit.register(_write, True)
    except BaseException:
        import traceback

        _die(97, traceback.format_exc())
'''


def _no_network(*args, **kwargs):
    raise OSError("network blocked in trainer tests")


def guard_trainer_children(monkeypatch, tmp_path):
    """Make every Python child process load CHILD_SITE; block the network in
    this process too. Returns the folder the children write their records to."""
    site_dir = tmp_path / "child_site"
    site_dir.mkdir()
    (site_dir / "sitecustomize.py").write_text(CHILD_SITE, encoding="utf-8")
    records = tmp_path / "child_records"
    records.mkdir()
    for key in [k for k in os.environ if k.startswith("POWERTRADER_")]:
        if key != "POWERTRADER_HOME":
            monkeypatch.delenv(key)  # no credential or folder override reaches a child
    # the pattern trainer reads the candle cache only; a test seeds it
    monkeypatch.setenv("POWERTRADER_CANDLES_OFFLINE", "1")
    for key in (
        "PT_TEST_TICKER_CSV",
        "PT_TEST_TICKER_WINDOW",
        "PT_TEST_SEED",
        "PT_TEST_CANDLES_PROVIDER",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PYTHONPATH", str(site_dir))
    monkeypatch.setenv("PT_TEST_TRAINER_CHILD", "1")
    monkeypatch.setenv("PT_TEST_CHILD_RECORD_DIR", str(records))
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    # a second fence behind the socket block
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
        monkeypatch.setenv(key, "http://127.0.0.1:9")
    for key in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(key, raising=False)
    for name in ("connect", "connect_ex", "sendto", "sendmsg"):
        if hasattr(socket.socket, name):  # no sendmsg on Windows
            monkeypatch.setattr(socket.socket, name, _no_network)
    for name in (
        "create_connection",
        "getaddrinfo",
        "gethostbyname",
        "gethostbyname_ex",
    ):
        monkeypatch.setattr(socket, name, _no_network)
    return records


def configure_trainer(script=None, allow_mock=None):
    """Write the user's settings files under POWERTRADER_HOME, as a user would:
    ``script_neural_trainer`` in gui_settings.json (read by the hub at start-up)
    and ``allow_mock_trainer`` in pt_config.json (read at every launch)."""
    import pt_paths

    for path, key, value in (
        (pt_paths.gui_settings_file(), "script_neural_trainer", script),
        (pt_paths.settings_file(), "allow_mock_trainer", allow_mock),
    ):
        if value is None:
            continue
        data = {}
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        data[key] = value
        pt_paths.write_private_text(path, json.dumps(data, indent=2))


def child_records(records_dir):
    """Records written by guarded children, oldest first."""
    out = []
    for path in glob.glob(os.path.join(str(records_dir), "child-*.json")):
        with open(path, encoding="utf-8") as f:
            out.append(json.load(f))
    return sorted(out, key=lambda r: r["started"])


def child_errors(records_dir):
    """Messages of guards that failed closed (exit code 97 or 98)."""
    out = []
    for path in sorted(glob.glob(os.path.join(str(records_dir), "child-*-error.txt"))):
        with open(path, encoding="utf-8") as f:
            out.append(f.read())
    return out


def build_real_hub(monkeypatch):
    """A PowerTraderHub built by its real ``__init__``, with a hidden window.
    Skips only when Tk itself cannot start; any other error fails the test."""
    import tkinter as tk

    import pt_hub

    for flag in HEAVY_FLAGS:
        monkeypatch.setattr(pt_hub, flag, False)
    monkeypatch.setattr(pt_hub, "fetch_binance_btc_price", lambda *a, **k: None)
    dialogs = []
    for name in DIALOGS:
        monkeypatch.setattr(
            pt_hub.messagebox,
            name,
            lambda *a, _name=name, **k: dialogs.append((_name, a)),
        )
    real_init = tk.Tk.__init__
    roots = []

    def hidden_init(self, *args, **kwargs):
        real_init(self, *args, **kwargs)
        roots.append(self)
        self.withdraw()

    monkeypatch.setattr(tk.Tk, "__init__", hidden_init)
    # On Windows, Tk sometimes fails to read init.tcl or tk.tcl when a root is
    # created right after a hub that started a child process. Creating the root
    # is the first thing __init__ does, so a root that failed to start leaves
    # nothing behind and can be retried.
    for attempt in range(10):
        try:
            hub = pt_hub.PowerTraderHub()
            break
        except tk.TclError as exc:
            if roots:  # Tk started: this is an error in __init__ itself
                for root in roots:
                    try:
                        root.destroy()
                    except tk.TclError:
                        pass
                raise
            startup = "Can't find a usable" in str(exc) and ".tcl" in str(exc)
            if not startup or attempt == 9:
                pytest.skip(f"Tk not available (attempt {attempt + 1}): {exc}")
            gc.collect()
            time.sleep(1.0)
    hub.test_tk_attempts = attempt + 1
    hub.test_dialogs = dialogs
    # Defensive: the tests process no Tk events, so only a widget command that
    # raises (the Settings Save button catches its own errors) would land here.
    hub.test_callback_errors = []
    hub.report_callback_exception = (
        lambda exc, val, tb: hub.test_callback_errors.append(val)
    )
    return hub


def close_hub(hub):
    """Stop any trainer the hub still runs, then destroy its Tk root."""
    for lp in list(getattr(hub, "trainers", {}).values()):
        proc = lp.info.proc
        if proc is not None and proc.poll() is None:
            proc.kill()
        if proc is not None:
            proc.wait(timeout=60)
        if lp.thread is not None:
            lp.thread.join(timeout=10)
        if proc is not None and proc.stdout is not None:
            proc.stdout.close()
    hub.destroy()
    gc.collect()


def launch(hub, coin):
    """Start training ``coin`` through the hub's own method (as the Trainers
    tab does). Returns the hub's new LogProc, or None if the hub did not keep
    the process (it drops one that exits within its 0.5 s start-up check and
    leaves any earlier process for the coin in place)."""
    previous = hub.trainers.get(coin)
    hub.trainer_coin_var.set(coin)
    hub.start_trainer_for_selected_coin()
    current = hub.trainers.get(coin)
    return None if current is previous else current


def wait(lp, timeout=240):
    """Wait for a trainer the hub started; return (exit code, output lines)."""
    code = lp.info.proc.wait(timeout=timeout)
    lp.thread.join(timeout=10)
    lines = []
    while not lp.log_q.empty():
        lines.append(lp.log_q.get_nowait())
    return code, lines


def model_files(folder):
    """{file name: SHA-256} of the model files in a coin folder."""
    out = {}
    for pattern in MODEL_FILE_PATTERNS:
        for path in glob.glob(os.path.join(folder, pattern)):
            with open(path, "rb") as f:
                out[os.path.basename(path)] = hashlib.sha256(f.read()).hexdigest()
    return dict(sorted(out.items()))


def expected_model_file_names():
    return sorted(f"{kind}_{tf}.txt" for kind in MODEL_FILE_KINDS for tf in TIMEFRAMES)


SNAPSHOT_SKIP = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    ".pytest_cache",
    "node_modules",
}


def tree_snapshot(root, patterns=None):
    """{path: (size, mtime_ns)} of the files under ``root``, excluding git data,
    virtual environments and bytecode caches; only names matching one of
    ``patterns`` when given."""
    state = {}
    for folder, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SNAPSHOT_SKIP]
        for name in files:
            if patterns and not any(fnmatch.fnmatch(name, p) for p in patterns):
                continue
            path = os.path.join(folder, name)
            st = os.stat(path)
            state[path] = (st.st_size, st.st_mtime_ns)
    return state


def snapshot_changes(before, after):
    """(added, changed, removed) paths between two tree snapshots."""
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(p for p in set(before) & set(after) if before[p] != after[p])
    return added, changed, removed


def program_folder_state():
    """What a trainer run must never change: every file in the program folder
    (app/), and every trainer output file anywhere in the install folder (the
    pre-FDS-108a trainers wrote summaries to <repo>/data and app/data)."""
    import pt_paths

    return {
        "program_dir": tree_snapshot(pt_paths.program_dir()),
        "trainer_outputs": tree_snapshot(
            pt_paths.install_dir(), TRAINER_OUTPUT_PATTERNS
        ),
    }
