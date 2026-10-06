"""Run the vendored upstream trainer (``fixtures/upstream_ba62130_pt_trainer.py.txt``)
as an oracle for the port in ``app/pt_pattern_trainer.py`` (FDS-MDL Phase 1).

The fixture is upstream's ``pt_trainer.py`` at commit ``ba62130`` with LF line
endings; with CRLF line endings it is git blob ``0369182``, upstream's own blob
(``upstream_blob_ok`` checks this, so the file cannot drift unnoticed).

Upstream reads KuCoin through ``kucoin.client.Market``. ``UPSTREAM_SITE`` is a
``sitecustomize.py`` for the child process that replaces that module with a fake
serving fixture klines, freezes ``time.time`` (one second after ``train_end``, so
every timeframe has one still-forming bar opening at ``train_end``, as upstream saw
live), makes ``time.sleep`` a no-op and blocks the network. It records every call.
"""

import hashlib
import json
import os
import subprocess
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
UPSTREAM_FIXTURE = os.path.join(
    TESTS_DIR, "fixtures", "upstream_ba62130_pt_trainer.py.txt"
)
UPSTREAM_LF_BLOB = "5359562154914599c0d798812e2823edc40f5d41"
KUCOIN_PAGE_MAX = 1500

UPSTREAM_SITE = r'''"""sitecustomize for the upstream trainer oracle (app/tests/helpers_upstream.py)."""
import os
import sys


def _die(code, message):
    try:
        with open(os.environ["PT_TEST_UPSTREAM_RECORD"] + ".error", "w") as f:
            f.write(message)
    finally:
        os._exit(code)


if os.environ.get("PT_TEST_UPSTREAM_CHILD") == "1":
    try:
        import atexit
        import json
        import socket
        import time
        import types

        def _no_network(*args, **kwargs):
            raise OSError("network blocked in the upstream oracle")

        for _name in ("connect", "connect_ex", "sendto", "sendmsg"):
            if hasattr(socket.socket, _name):
                setattr(socket.socket, _name, _no_network)
        for _name in ("create_connection", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
            setattr(socket, _name, _no_network)
        sys.dont_write_bytecode = True

        _frozen = float(os.environ["PT_TEST_FROZEN_TIME"])
        time.time = lambda: _frozen
        time.sleep = lambda seconds: None

        with open(os.environ["PT_TEST_KLINES_JSON"], encoding="utf-8") as f:
            _klines = json.load(f)
        _calls = []

        class Market:
            """kucoin.client.Market: klines newest first, at most 1500 per call,
            open time in [startAt, endAt)."""

            def __init__(self, *args, **kwargs):
                pass

            def get_kline(self, symbol, kline_type, startAt=None, endAt=None, **kwargs):
                rows = [r for r in _klines[kline_type] if startAt <= int(r[0]) < endAt]
                rows = [list(r) for r in rows[-1500:]][::-1]
                _calls.append(["kline", symbol, kline_type, startAt, endAt, len(rows)])
                return rows

            def get_ticker(self, symbol):
                _calls.append(["ticker", symbol])
                return {"symbol": symbol, "price": "1.0"}

        _client = types.ModuleType("kucoin.client")
        _client.Market = Market
        _package = types.ModuleType("kucoin")
        _package.__path__ = []
        _package.client = _client
        sys.modules["kucoin"] = _package
        sys.modules["kucoin.client"] = _client

        def _write():
            with open(os.environ["PT_TEST_UPSTREAM_RECORD"], "w", encoding="utf-8") as f:
                json.dump({"calls": _calls}, f)

        atexit.register(_write)
    except BaseException:
        import traceback

        _die(97, traceback.format_exc())
'''


def git_blob(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def upstream_source() -> bytes:
    """The fixture with LF line endings (git may check it out with CRLF)."""
    with open(UPSTREAM_FIXTURE, "rb") as f:
        return f.read().replace(b"\r\n", b"\n")


def upstream_blob_ok(expected_crlf_blob: str) -> bool:
    lf = upstream_source()
    return (
        git_blob(lf) == UPSTREAM_LF_BLOB
        and git_blob(lf.replace(b"\n", b"\r\n")) == expected_crlf_blob
    )


def kucoin_rows(frame, forming_open_s):
    """KuCoin kline rows (strings, oldest first) for a candle frame, plus a still-
    forming bar opening at ``forming_open_s``. Prices are the exact floats the candle
    layer reads (``repr`` round-trips)."""
    rows = [
        [str(int(t.timestamp())), repr(o), repr(c), repr(h), repr(lo), repr(v), "0"]
        for t, o, c, h, lo, v in zip(
            frame["open_time"],
            frame["open"].tolist(),
            frame["close"].tolist(),
            frame["high"].tolist(),
            frame["low"].tolist(),
            frame["volume"].tolist(),
        )
    ]
    last_close = rows[-1][2]
    rows.append(
        [
            str(int(forming_open_s)),
            last_close,
            last_close,
            last_close,
            last_close,
            "0",
            "0",
        ]
    )
    return rows


def run_upstream(work_dir, klines, frozen_time, coin="BTC", timeout=900):
    """Run the upstream trainer for ``coin`` in ``work_dir`` on ``klines``
    ({kucoin timeframe: rows}). Returns (exit code, record, run folder, log path)."""
    work_dir = str(work_dir)
    site_dir = os.path.join(work_dir, "_site")
    run_dir = os.path.join(work_dir, "run")
    os.makedirs(site_dir)
    os.makedirs(run_dir)
    with open(os.path.join(site_dir, "sitecustomize.py"), "w", encoding="utf-8") as f:
        f.write(UPSTREAM_SITE)
    with open(os.path.join(run_dir, "pt_trainer.py"), "wb") as f:
        f.write(upstream_source())
    klines_path = os.path.join(work_dir, "klines.json")
    with open(klines_path, "w", encoding="utf-8") as f:
        json.dump(klines, f)
    record_path = os.path.join(work_dir, "record.json")
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("POWERTRADER_") or k == "POWERTRADER_HOME"
    }
    env.update(
        PYTHONPATH=site_dir,
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONHASHSEED="0",
        PYTHON_KEYRING_BACKEND="keyring.backends.fail.Keyring",
        PT_TEST_UPSTREAM_CHILD="1",
        PT_TEST_FROZEN_TIME=repr(float(frozen_time)),
        PT_TEST_KLINES_JSON=klines_path,
        PT_TEST_UPSTREAM_RECORD=record_path,
    )
    log_path = os.path.join(work_dir, "upstream.log")
    with open(log_path, "w", encoding="utf-8", errors="replace") as log:
        proc = subprocess.run(
            [sys.executable, "pt_trainer.py", coin],
            cwd=run_dir,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    record = None
    if os.path.isfile(record_path):
        with open(record_path, encoding="utf-8") as f:
            record = json.load(f)
    if os.path.isfile(record_path + ".error"):
        with open(record_path + ".error", encoding="utf-8") as f:
            record = {"error": f.read()}
    return proc.returncode, record, run_dir, log_path
