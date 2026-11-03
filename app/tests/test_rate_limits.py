"""Each exchange's requests are kept to its published limit, across every PowerTrader
process on the computer (rate_limits.py), and every connector request waits for a
slot. Runs under the isolation guard (app/conftest.py); no network."""

import bisect
import json
import os
import re
import subprocess
import sys
import textwrap

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_exchanges  # noqa: E402
import rate_limits  # noqa: E402
from pt_exchange_abstraction import AbstractExchange  # noqa: E402
from pt_multi_exchange import ExchangeConfigManager  # noqa: E402


@pytest.fixture
def pacing(monkeypatch):
    """Pacing on (app/conftest.py switches it off), with no overrides cached."""
    monkeypatch.setattr(rate_limits, "ENABLED", True)
    monkeypatch.setattr(rate_limits, "_overrides", {})
    monkeypatch.setattr(rate_limits, "_overrides_read", (0.0, None))
    monkeypatch.setattr(rate_limits, "_local", {})


class Clock:
    def __init__(self):
        self.now = 1_000_000.0
        self.slept = []

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += seconds


def busiest(times, seconds=1.0):
    times = sorted(times)
    return max(bisect.bisect_left(times, t + seconds) - i for i, t in enumerate(times))


def test_a_limit_is_a_number_of_requests_in_a_window():
    assert rate_limits.window(10) == (10, 1.0)
    assert rate_limits.window(66.5) == (66, 1.0)
    assert rate_limits.window(0.5) == (1, 2.0)


def test_requests_wait_once_the_window_is_full(pacing):
    clock = Clock()
    times = []
    for _ in range(25):
        rate_limits.wait("coinbase", 10, clock=clock.time, sleep=clock.sleep)
        times.append(clock.now)
    assert busiest(times) == 10
    assert clock.now - 1_000_000.0 >= 2.0  # 25 requests at 10 a second
    assert os.listdir(rate_limits.state_dir())  # shared through the folder


def test_a_limit_below_one_a_second_spaces_every_request(pacing):
    clock = Clock()
    rate_limits.wait("slow", 0.5, clock=clock.time, sleep=clock.sleep)
    rate_limits.wait("slow", 0.5, clock=clock.time, sleep=clock.sleep)
    assert sum(clock.slept) == pytest.approx(2.0 + rate_limits.MARGIN, abs=0.01)


def test_each_exchange_has_its_own_window(pacing):
    clock = Clock()
    for _ in range(10):
        rate_limits.wait("coinbase", 10, clock=clock.time, sleep=clock.sleep)
    rate_limits.wait("kraken", 1, clock=clock.time, sleep=clock.sleep)
    assert clock.slept == []


def test_switched_off_nothing_waits(monkeypatch):
    monkeypatch.setattr(rate_limits, "ENABLED", False)
    clock = Clock()
    for _ in range(50):
        rate_limits.wait("coinbase", 10, clock=clock.time, sleep=clock.sleep)
    assert clock.slept == []


def test_processes_on_one_computer_share_the_limit(tmp_path):
    """Three processes asking as fast as they can, together, stay at 20 a second."""
    out = tmp_path / "times"
    script = textwrap.dedent(f"""
        import sys, time
        sys.path.insert(0, {APP_DIR!r})
        import rate_limits
        stamps = []
        for _ in range(20):
            rate_limits.wait("sharedtest", 20)
            stamps.append(time.time())
        with open(sys.argv[1], "w") as f:
            f.write(" ".join(map(str, stamps)))
        """)
    env = dict(os.environ)  # the guard's POWERTRADER_HOME: one shared state folder
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", script, str(out) + str(i)], env=env, cwd=APP_DIR
        )
        for i in range(3)
    ]
    for p in procs:
        assert p.wait(timeout=120) == 0
    times = []
    for i in range(3):
        times += [float(t) for t in open(str(out) + str(i)).read().split()]
    assert len(times) == 60
    assert busiest(times) <= 20
    assert max(times) - min(times) >= 1.9  # 60 requests at 20 a second


def test_without_a_usable_folder_a_process_paces_itself(pacing, monkeypatch, tmp_path):
    blocker = tmp_path / "not-a-folder"
    blocker.write_text("x")
    monkeypatch.setattr(rate_limits, "state_dir", lambda: str(blocker / "sub"))
    clock = Clock()
    times = []
    for _ in range(15):
        rate_limits.wait("coinbase", 10, clock=clock.time, sleep=clock.sleep)
        times.append(clock.now)
    assert busiest(times) == 10 and clock.slept


def test_configure_exchange_apis_sets_another_figure(pacing):
    manager = ExchangeConfigManager()
    assert rate_limits.limit_for("coinbase", 10.0) == 10.0
    assert manager.set_requests_per_second("coinbase", 4.0)
    with open(manager.config_file, encoding="utf-8") as f:
        saved = {e["exchange_type"]: e for e in json.load(f)["exchanges"]}
    assert saved["coinbase"]["requests_per_second"] == 4.0
    assert "requests_per_second" not in saved.get("kraken", {})
    rate_limits._overrides_read = (0.0, None)
    assert rate_limits.limit_for("coinbase", 10.0) == 4.0
    assert manager.set_requests_per_second("coinbase", None)
    rate_limits._overrides_read = (0.0, None)
    assert rate_limits.limit_for("coinbase", 10.0) == 10.0


@pytest.mark.parametrize("value", [0, -1, "fast", None, True, 5000, float("nan")])
def test_a_figure_that_is_not_a_rate_is_not_used(value):
    assert rate_limits.valid_rate(value) is None


def test_each_exchange_carries_its_published_figure():
    assert rate_limits.published_rate("coinbase") == (10.0, True)
    assert rate_limits.published_rate("kraken") == (1.0, True)
    assert rate_limits.published_rate("kucoin") == (66.0, True)
    assert rate_limits.published_rate("binance") == (10.0, True)
    assert rate_limits.published_rate("gate") == (
        AbstractExchange.requests_per_second,
        False,
    )


def test_every_connector_request_waits_for_a_slot():
    """In pt_exchanges, each HTTP call is preceded by the wait (or goes through
    _public_get with its exchange), so a new connector cannot skip it."""
    with open(pt_exchanges.__file__, encoding="utf-8") as f:
        lines = f.read().splitlines()
    calls = [
        i
        for i, line in enumerate(lines)
        if re.search(r"\brequests\.(get|post|request|put|delete)\(", line)
    ]
    assert calls
    for i in calls:
        if "def _public_get" in "\n".join(lines[max(0, i - 15) : i]):
            assert "exchange.wait_for_request_slot()" in lines[i - 1]
            continue
        assert lines[i - 1].strip() == "self.wait_for_request_slot()", (
            i + 1,
            lines[i],
        )
    # connectors call _public_get_for(self, ...); only that wrapper calls _public_get
    direct = [
        line
        for line in lines
        if "_public_get(" in line
        and "def _public_get(" not in line
        and "return _public_get(url, exchange=exchange" not in line
    ]
    assert direct == []


def test_public_get_waits_before_every_attempt(monkeypatch):
    waits = []

    class Exchange:
        def wait_for_request_slot(self):
            waits.append(1)

    class Response:
        def __init__(self, status):
            self.status_code = status
            self.headers = {"Retry-After": "0"}

    answers = iter([Response(429), Response(429), Response(200)])
    monkeypatch.setattr(pt_exchanges.requests, "get", lambda *a, **k: next(answers))
    monkeypatch.setattr(pt_exchanges.time, "sleep", lambda s: None)
    assert (
        pt_exchanges._public_get(
            "https://example.invalid", exchange=Exchange()
        ).status_code
        == 200
    )
    assert len(waits) == 3


def test_a_connector_waits_under_its_own_name(monkeypatch):
    asked = []
    monkeypatch.setattr(
        rate_limits, "wait", lambda name, rate: asked.append((name, rate))
    )
    pt_exchanges.CoinbaseExchange("", "").wait_for_request_slot()
    pt_exchanges.KrakenExchange("", "").wait_for_request_slot()
    assert asked == [("coinbase", 10.0), ("kraken", 1.0)]


# --- Configure Exchange APIs: Requests per second ---------------------------------------


@pytest.fixture
def setup_window(monkeypatch, tmp_path):
    import tkinter as tk
    from unittest import mock

    import exchange_config_gui

    last = None
    for _ in range(5):  # Tk on Windows sometimes fails to read init.tcl at first
        try:
            root = tk.Tk()
            break
        except tk.TclError as exc:
            last = exc
    else:
        pytest.skip(f"Tk cannot start: {last}")
    root.withdraw()
    manager = ExchangeConfigManager(str(tmp_path))
    manager.create_default_config("EU")
    monkeypatch.setattr(exchange_config_gui, "ExchangeConfigManager", lambda: manager)
    dialogs = mock.MagicMock()
    for name in ("showerror", "showinfo", "showwarning", "askyesno"):
        monkeypatch.setattr(
            exchange_config_gui.messagebox, name, getattr(dialogs, name)
        )
    gui = exchange_config_gui.ExchangeConfigGUI(root)
    gui.window.withdraw()
    gui.dialogs, gui.manager = dialogs, manager
    yield gui
    gui.window.destroy()
    root.destroy()


def select(gui, name):
    gui.exchange_var.set(name)
    gui.on_exchange_selected()


def saved_rate(manager, name):
    for ex in manager.load_config().exchanges:
        if ex.exchange_type == name:
            return ex.requests_per_second
    return "absent"


def test_the_setup_window_shows_the_published_limit(setup_window):
    select(setup_window, "coinbase")
    assert setup_window.rate_var.get() == "10"
    assert setup_window.rate_hint_var.get().startswith(
        "Coinbase's published limit: 10 a second."
    )
    select(setup_window, "gate")
    assert setup_window.rate_var.get() == "5"
    assert setup_window.rate_hint_var.get().startswith(
        "PowerTrader's default for Gate.io: 5 a second."
    )


def test_a_saved_limit_is_used_and_can_go_back_to_the_published_one(setup_window):
    select(setup_window, "coinbase")
    setup_window.rate_var.set("4")
    assert setup_window.save_rate_limit()
    assert saved_rate(setup_window.manager, "coinbase") == 4.0
    assert "Saved here: 4 a second." in setup_window.rate_hint_var.get()
    assert setup_window.rate_var.get() == "4"
    assert setup_window.reset_rate_limit()
    assert saved_rate(setup_window.manager, "coinbase") is None
    assert setup_window.rate_var.get() == "10"


def test_a_limit_is_saved_without_any_api_key(setup_window):
    select(setup_window, "kraken")  # no key saved: public prices need none
    setup_window.rate_var.set("2")
    assert setup_window.save_rate_limit()
    assert saved_rate(setup_window.manager, "kraken") == 2.0
    setup_window.dialogs.showerror.assert_not_called()


@pytest.mark.parametrize("typed", ["0", "-3", "fast", "5000"])
def test_a_figure_that_is_not_a_rate_is_refused(setup_window, typed):
    select(setup_window, "coinbase")
    setup_window.rate_var.set(typed)
    assert not setup_window.save_rate_limit()
    assert saved_rate(setup_window.manager, "coinbase") is None
    setup_window.dialogs.showerror.assert_called_once()


# --- a closed hub stops asking the exchanges ----------------------------------------------


def test_the_hubs_exchange_check_ends_when_the_hub_is_destroyed(monkeypatch):
    """The hub's background exchange status check stops with the hub, so a closed
    hub never sends requests again (it used to poll every 30 s for good)."""
    import threading

    import helpers_trainer as ht
    import pt_hub

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    asked = []
    hub._multi_exchange = object()  # connected
    monkeypatch.setattr(hub, "_primary_exchange", lambda: "coinbase")
    monkeypatch.setattr(
        hub,
        "_exchange_status_once",
        lambda primary, trading=None: asked.append(primary) or ("ok", "", "ok"),
    )
    worker = threading.Thread(target=hub._check_exchange_status_worker, daemon=True)
    worker.start()
    deadline = pt_hub.time.time() + 10
    while not asked and pt_hub.time.time() < deadline:
        pt_hub.time.sleep(0.01)
    assert asked == ["coinbase"]
    ht.close_hub(hub)
    worker.join(timeout=5)
    assert not worker.is_alive()
    assert asked == ["coinbase"]
