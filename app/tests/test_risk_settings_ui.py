"""Settings > Risk: the window, and its row in Settings.

The window runs under the isolation guard (app/conftest.py) with a hidden root, and
saves to a pt_config.json in a temporary folder.
"""

from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import ttk

import pytest

import risk_settings_ui as ui
import risk_state
import trading_mode as tm
from pt_settings_manager import SettingsManager

# --- the window ------------------------------------------------------------------------


@pytest.fixture
def root():
    last = None
    for _ in range(5):  # Tk on Windows sometimes fails to read init.tcl at first
        try:
            r = tk.Tk()
            break
        except tk.TclError as exc:
            last = exc
    else:
        pytest.skip(f"Tk cannot start: {last}")
    r.withdraw()
    yield r
    r.destroy()


class Box:
    """A messagebox that answers ``yes`` and records what it was shown."""

    def __init__(self, yes=True):
        self.yes = yes
        self.errors = []
        self.asked = []

    def showerror(self, title, message, **_):
        self.errors.append(message)

    def askyesno(self, title, message, **_):
        self.asked.append((title, message))
        return self.yes


@pytest.fixture
def folder(tmp_path):
    return str(tmp_path / "config")


@pytest.fixture
def books(tmp_path):
    path = tmp_path / "paper"
    path.mkdir()
    return str(path)


def manager(folder):
    return SettingsManager("pt_config.json", folder)


def settings_path(folder):
    return os.path.join(folder, "pt_config.json")


def on_disk(folder):
    path = settings_path(folder)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("risk", {})


def open_window(root, folder, books=None, account=None, box=None):
    calls = []
    win = ui.RiskSettingsWindow(
        root,
        books_dir=books,
        account_value=lambda: account,
        manager_factory=lambda: manager(folder),
        on_saved=lambda: calls.append("saved"),
        messagebox=box or Box(),
    )
    win.withdraw()
    win.saved_calls = calls
    return win


def texts(win):
    out = []
    for w in widgets(win):
        if isinstance(w, ttk.Label):
            var = str(w.cget("textvariable"))
            out.append(str(w.getvar(var)) if var else str(w.cget("text")))
    return out


def widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from widgets(child)


def test_a_new_install_shows_the_default_levels_and_no_peak(root, folder):
    win = open_window(root, folder)
    assert {k: v.get() for k, v in win.vars.items()} == {
        "drawdown_warning_pct": "3",
        "drawdown_critical_pct": "5",
        "emergency_drawdown_pct": "8",
    }
    assert win.peak_var.get() == "none recorded yet"
    assert win.account_var.get() == "not reported yet"
    assert win.drawdown_var.get() == ""
    assert all(h.get() == "" for h in win.hints.values())
    shown = texts(win)
    for label in ("Warning %:", "Critical %:", "Emergency stop %:"):
        assert label in shown
    win.destroy()


def test_the_peak_the_drawdown_and_each_level_in_dollars(root, folder, books):
    risk_state.write_state(books, {"peak_value": 10_000.0, "peak_ts": 1.7e9})
    win = open_window(root, folder, books, account=9_500.0)
    assert win.peak_var.get().startswith("$10,000.00, seen ")
    assert win.account_var.get() == "$9,500.00, as last reported by the trader"
    assert win.drawdown_var.get() == "5.00%"
    assert {k: v.get() for k, v in win.hints.items()} == {
        "drawdown_warning_pct": "at $9,700.00 ($300.00 below the peak)",
        "drawdown_critical_pct": "at $9,500.00 ($500.00 below the peak)",
        "emergency_drawdown_pct": "at $9,200.00 ($800.00 below the peak)",
    }
    win.vars["emergency_drawdown_pct"].set("12.5%")
    assert win.hints["emergency_drawdown_pct"].get() == (
        "at $8,750.00 ($1,250.00 below the peak)"
    )
    win.vars["emergency_drawdown_pct"].set("x")
    assert win.hints["emergency_drawdown_pct"].get() == ""
    win.destroy()


def test_save_writes_what_the_trader_reads(root, folder):
    win = open_window(root, folder)
    win.vars["drawdown_warning_pct"].set("2")
    win.vars["drawdown_critical_pct"].set("4.5")
    win.vars["emergency_drawdown_pct"].set("6%")
    assert win.save()
    assert win.saved_calls == ["saved"]
    assert on_disk(folder) == {
        "drawdown_warning_pct": 2.0,
        "drawdown_critical_pct": 4.5,
        "emergency_drawdown_pct": 6.0,
    }
    assert tm.read_drawdown_levels(settings_path(folder)) == tm.DrawdownLevels(
        2.0, 4.5, 6.0
    )
    again = open_window(root, folder)  # shows what was saved
    assert again.vars["drawdown_critical_pct"].get() == "4.5"
    again.destroy()


@pytest.mark.parametrize(
    "warning, critical, emergency, wrong",
    [
        ("5", "5", "8", {"drawdown_warning_pct": "Must be below Critical %."}),
        ("3", "9", "8", {"drawdown_critical_pct": "Must be below Emergency stop %."}),
        ("3", "5", "60", {"emergency_drawdown_pct": "Must be a number from 1 to 50."}),
        ("0.1", "5", "8", {"drawdown_warning_pct": "Must be a number from 0.5 to 50."}),
        (
            "abc",
            "",
            "8",
            {
                "drawdown_warning_pct": "Must be a number from 0.5 to 50.",
                "drawdown_critical_pct": "Must be a number from 0.5 to 50.",
            },
        ),
    ],
)
def test_a_wrong_level_is_refused_beside_its_field_and_nothing_is_saved(
    root, folder, warning, critical, emergency, wrong
):
    box = Box()
    win = open_window(root, folder, box=box)
    win.vars["drawdown_warning_pct"].set(warning)
    win.vars["drawdown_critical_pct"].set(critical)
    win.vars["emergency_drawdown_pct"].set(emergency)
    assert not win.save()
    shown = {k: v.get() for k, v in win.errors.items() if v.get()}
    assert shown == wrong
    for key in win.vars:  # only a field with a problem shows one
        assert bool(win._error_labels[key].winfo_manager()) == (key in wrong)
    assert win.status_var.get() == ui.FIX_TEXT and box.errors == []
    assert on_disk(folder) == {} and win.saved_calls == []
    win.destroy()


def test_an_error_goes_when_its_field_is_corrected(root, folder):
    win = open_window(root, folder)
    win.vars["emergency_drawdown_pct"].set("0")
    assert not win.save()
    assert win.errors["emergency_drawdown_pct"].get()
    win.vars["emergency_drawdown_pct"].set("9")
    assert win.errors["emergency_drawdown_pct"].get() == ""
    assert not win._error_labels["emergency_drawdown_pct"].winfo_manager()
    assert win.save()
    assert on_disk(folder)["emergency_drawdown_pct"] == 9.0


def test_the_window_says_when_changes_apply(root, folder):
    win = open_window(root, folder)
    shown = texts(win)
    assert "When changes apply" in shown and ui.APPLY_TEXT in shown
    assert "next cycle" in ui.APPLY_TEXT and "no restart" in ui.APPLY_TEXT
    win.destroy()


def test_the_words_say_a_halt_stops_buying_only():
    """A halt refuses buys and the trader keeps running: exits, stops and the
    trailing margin still sell, and Resume trading needs no restart."""
    (stop_help,) = [
        level[-1] for level in ui.LEVELS if level[0] == "emergency_drawdown_pct"
    ]
    for text in (stop_help, ui.APPLY_TEXT):
        assert "stops trading" not in text and "has stopped" not in text
        assert "buy" in text
    assert "still sell" in stop_help
    assert "next pass" in ui.APPLY_TEXT


def test_the_words_name_no_spec_key_or_data_provider(root, folder):
    win = limits_window(root, folder)
    for text in texts(win) + [ui.APPLY_TEXT, ui.FIX_TEXT]:
        for banned in ("FDS", "_pct", "pt_config", "json", "Binance", "KuCoin"):
            assert banned not in text, (banned, text)
    win.destroy()


def test_reset_peak_sets_the_peak_to_the_account_value_after_asking(
    root, folder, books
):
    risk_state.write_state(books, {"peak_value": 10_000.0, "peak_ts": 1.7e9})
    box = Box(yes=False)
    win = open_window(root, folder, books, account=9_000.0, box=box)
    assert not win.reset_peak()  # "No": nothing changes
    assert risk_state.current(books).peak_value == 10_000.0
    assert "$9,000.00" in box.asked[0][1]
    box.yes = True
    assert win.reset_peak()
    assert risk_state.current(books).peak_value == 9_000.0
    assert win.peak_var.get().startswith("$9,000.00, seen ")
    assert win.drawdown_var.get() == "0.00%"
    win.destroy()


def test_holdings_left_out_of_the_account_value_are_listed(root, folder, books):
    risk_state.write_state(
        books,
        {
            "peak_value": 10_000.0,
            "not_counted": [
                {"asset": "GBP", "quantity": 1250.0, "why": "no USD price"},
                {
                    "asset": "BTC",
                    "quantity": 0.04,
                    "why": "no price for over 10 minutes",
                },
            ],
        },
    )
    win = open_window(root, folder, books, account=6_000.0)
    assert win.not_counted_var.get() == (
        "Not counted in the account value: GBP 1,250.00 (no USD price), "
        "BTC 0.04 (no price for over 10 minutes)."
    )
    assert win.not_counted_var.get() in texts(win)
    win.destroy()


def test_buys_waiting_is_shown_with_why(root, folder, books):
    risk_state.write_state(
        books,
        {
            "buys_waiting": "no account value for over 10 minutes (the balances "
            "could not be read)",
            "buys_waiting_ts": 1.7e9,
        },
    )
    win = open_window(root, folder, books)
    assert win.waiting_var.get().startswith(
        "Buys are waiting: no account value for over 10 minutes (the balances "
        "could not be read), since "
    )
    assert win.waiting_var.get().endswith(". Sells still go through.")
    win.destroy()


def test_with_everything_counted_and_no_wait_neither_line_shows(root, folder, books):
    risk_state.write_state(books, {"peak_value": 10_000.0})  # an older file
    win = open_window(root, folder, books, account=9_500.0)
    assert win.not_counted_var.get() == "" and win.waiting_var.get() == ""
    win.destroy()


def test_reset_peak_needs_an_account_value(root, folder, books):
    box = Box()
    win = open_window(root, folder, books, account=None, box=box)
    assert not win.reset_peak()
    assert box.asked == [] and box.errors
    assert not os.path.exists(risk_state.requests_path(books))
    win.destroy()


def test_the_emergency_stop_saved_in_the_window_is_what_the_trader_uses(root, folder):
    """Acceptance: the stop % changed in the Risk window is the trader's stop."""
    import pt_trader

    adapter = pt_trader._TraderRiskAdapter(settings_source=settings_path(folder))
    adapter.peak_value = 1000.0
    assert not adapter.check_emergency_conditions(950.0)["emergency_stop"]  # 5% < 8%
    win = open_window(root, folder)
    win.vars["drawdown_warning_pct"].set("1")
    win.vars["drawdown_critical_pct"].set("2")
    win.vars["emergency_drawdown_pct"].set("4")
    assert win.save()
    status = adapter.check_emergency_conditions(950.0)  # the same, running trader
    assert status["emergency_stop"]
    assert status["reason"] == "Account drawdown 5.0% reached the 4% emergency limit"


# --- the window in the hub ----------------------------------------------------------


@pytest.fixture
def hub(monkeypatch):
    import helpers_trainer as ht
    import pt_hub

    hub = ht.build_real_hub(monkeypatch)  # skips when Tk cannot start
    monkeypatch.setattr(pt_hub, "API_SERVER_AVAILABLE", False)
    yield hub
    ht.close_hub(hub)


def test_settings_opens_the_risk_window_next_to_strategy(hub):
    from test_settings_window import label_texts, widgets_of
    from test_trainer_launch import open_settings, press

    win = open_settings(hub)
    buttons = [
        str(w.cget("text")) for w in widgets_of(win) if isinstance(w, ttk.Button)
    ]
    assert buttons.index("Risk...") == buttons.index("Strategy...") + 1
    line = "Buying stops at a 8% drawdown from the peak; warnings at 3% and 5%"
    assert line in label_texts(win)
    press(win, "Risk...")
    risk_win = hub._risk_settings_win
    assert isinstance(risk_win, ui.RiskSettingsWindow)
    assert risk_win.title() == "Risk"
    risk_win.withdraw()
    press(win, "Risk...")  # raises the open one rather than opening another
    assert hub._risk_settings_win is risk_win
    risk_win.withdraw()

    risk_win.vars["emergency_drawdown_pct"].set("10")
    assert risk_win.save()
    assert (
        "Buying stops at a 10% drawdown from the peak; warnings at 3% and 5%"
        in label_texts(win)
    )
    assert tm.read_drawdown_levels().emergency_pct == 10.0  # pt_config.json
    win.destroy()


def test_the_hub_shows_the_peak_of_the_books_it_shows(hub):
    hub._last_total_account_value = 4_800.0
    risk_state.write_state(hub._books_dir, {"peak_value": 5_000.0})
    win = hub.open_risk_settings()
    win.withdraw()
    assert win.peak_var.get() == "$5,000.00"
    assert win.drawdown_var.get() == "4.00%"
    win.destroy()


# --- the halt in the window and the hub -----------------------------------------------


def halt(books, reason="Account drawdown 9.0% reached the 8% emergency limit"):
    risk_state.write_state(
        books,
        risk_state.halted_state(
            {"peak_value": 10_000.0, "peak_ts": 1.7e9}, reason, 9_100.0, now=1.7e9 + 60
        ),
    )


def test_without_a_halt_resume_cannot_be_pressed(root, folder, books):
    win = open_window(root, folder, books)
    assert win.halt_var.get() == "Trading is not halted."
    assert win.resume_button.instate(["disabled"])
    assert not win.resume()
    win.destroy()


def test_resume_trading_clears_the_halt_after_asking(root, folder, books):
    halt(books)
    box = Box(yes=False)
    changed = []
    win = ui.RiskSettingsWindow(
        root,
        books_dir=books,
        account_value=lambda: 9_600.0,
        manager_factory=lambda: manager(folder),
        on_changed=lambda: changed.append("changed"),
        messagebox=box,
    )
    win.withdraw()
    text = win.halt_var.get()
    assert text.startswith(
        "Buying is halted: Account drawdown 9.0% reached the 8% emergency limit "
        "\u00b7 since "
    )
    assert text.endswith(", account value $9,100.00. Sells still go through.")
    assert win.resume_button.instate(["!disabled"])

    assert not win.resume()  # "No": still halted
    assert risk_state.current(books).halted and changed == []
    title, message = box.asked[0]
    assert title == "Resume trading?" and "buys again from its next pass" in message
    assert "emergency stop" not in message.split("\n\n")[-1]  # 4% < 8%: no warning

    box.yes = True
    assert win.resume()
    assert not risk_state.current(books).halted
    assert win.halt_var.get() == "Trading is not halted."
    assert win.resume_button.instate(["disabled"])
    assert win.status_var.get().startswith("Buying resumes at the trader's next")
    assert changed == ["changed"]
    win.destroy()


def test_resume_says_when_the_drawdown_is_still_past_the_stop(root, folder, books):
    halt(books)
    box = Box(yes=False)
    win = open_window(root, folder, books, account=9_100.0, box=box)
    win.resume()
    assert box.asked[0][1].endswith(
        "The account is 9.00% below its peak, at or above the 8% emergency stop: the "
        "trader halts buying again at its first check, unless the peak is reset or the "
        "stop is raised first."
    )
    win.destroy()


def test_the_hub_shows_a_halt_banner_until_trading_is_resumed(hub, monkeypatch):
    from risk_settings_ui import HaltBanner

    hub._refresh_halt_banner()
    assert hub._halt_banner is None
    halt(hub._books_dir)
    hub._refresh_halt_banner()
    banner = hub._halt_banner
    assert isinstance(banner, HaltBanner)
    assert hub.pack_slaves()[0] is banner  # above everything
    assert banner.reason_var.get().startswith(
        "Account drawdown 9.0% reached the 8% emergency limit \u00b7 since "
    )
    texts = [str(w.cget("text")) for w in banner.winfo_children() if "text" in w.keys()]
    assert "BUYING HALTED" in texts and "Risk..." in texts
    assert hub._risk_summary().startswith("Buying is halted. Buying stops at a 8%")

    win = hub.open_risk_settings()
    win.withdraw()
    monkeypatch.setattr(win, "_box", Box(yes=True))
    assert win.resume()
    assert hub._halt_banner is None  # gone at once, not at the next tick
    assert not hub._risk_summary().startswith("Buying is halted")
    win.destroy()


def test_saving_the_paper_account_clears_the_paper_peak(hub):
    risk_state.write_state(hub._books_dir, {"peak_value": 10_000.0})
    halt(hub._books_dir)
    hub._on_paper_account_saved()
    view = risk_state.current(hub._books_dir)
    assert view.peak_value == 0.0  # measured from the new book's first value
    assert view.halted  # a halt stays until Resume trading


# --- the position and DCA limits ------------------------------------------------------

LIMITS_SAVED = {
    "start_allocation_pct": 1.0,
    "min_order_margin_pct": 2.0,
    "max_coin_allocation_pct": 10.0,
    "dca_multiplier": 2.0,
    "max_dca_buys_per_24h": 2,
}


def limits_window(root, folder, limits=None, account=10_000.0, box=None):
    written = []
    win = ui.RiskSettingsWindow(
        root,
        account_value=lambda: account,
        limits=dict(LIMITS_SAVED, **(limits or {})),
        save_limits=written.append,
        manager_factory=lambda: manager(folder),
        messagebox=box or Box(),
    )
    win.withdraw()
    win.written = written
    return win


def test_the_limits_show_as_saved_with_their_dollar_amounts(root, folder):
    win = limits_window(root, folder, {"start_allocation_pct": 1.5})
    assert {k: win.vars[k].get() for k in LIMITS_SAVED} == {
        "start_allocation_pct": "1.5",
        "min_order_margin_pct": "2",
        "max_coin_allocation_pct": "10",
        "dca_multiplier": "2",
        "max_dca_buys_per_24h": "2",
    }
    assert win.hints["start_allocation_pct"].get() == (
        "≈ $150.00 per entry, at least the exchange minimum"
    )
    assert win.hints["max_coin_allocation_pct"].get() == (
        "≈ $1,000.00 per coin with DCA; no DCA buy past it"
    )
    shown = texts(win)
    labels = [t for t in shown if t.endswith(":")]
    # Minimum order margin % is beside Start allocation %
    i = labels.index("Start allocation %:")
    assert labels[i : i + 5] == [
        "Start allocation %:",
        "Minimum order margin %:",
        "Max per coin %:",
        "DCA multiplier:",
        "Max DCA buys / coin (rolling 24h):",
    ]
    assert (
        "When an entry is raised to the exchange's minimum order, it is raised by "
        "this much more, so the position stays above the minimum when valued at the "
        "bid after fees. 0 to 20, default 2."
    ) in shown
    win.destroy()


def test_no_account_value_shows_no_dollar_amounts(root, folder):
    win = limits_window(root, folder, account=None)
    assert win.hints["start_allocation_pct"].get() == ""
    assert win.hints["max_coin_allocation_pct"].get() == ""
    win.destroy()


def test_save_writes_the_limits_with_the_types_the_trader_reads(root, folder):
    win = limits_window(root, folder)
    win.vars["start_allocation_pct"].set("2.5%")
    win.vars["min_order_margin_pct"].set("0")
    win.vars["max_coin_allocation_pct"].set("15")
    win.vars["dca_multiplier"].set("1.5")
    win.vars["max_dca_buys_per_24h"].set("0")
    assert win.save()
    assert win.written == [
        {
            "start_allocation_pct": 2.5,
            "min_order_margin_pct": 0.0,
            "max_coin_allocation_pct": 15.0,
            "dca_multiplier": 1.5,
            "max_dca_buys_per_24h": 0,
        }
    ]
    assert isinstance(win.written[0]["max_dca_buys_per_24h"], int)


@pytest.mark.parametrize(
    "key, typed, said",
    [
        (
            "start_allocation_pct",
            "0",
            "Start allocation % must be a number from 0.0001 to 100.",
        ),
        (
            "start_allocation_pct",
            "",
            "Start allocation % must be a number from 0.0001 to 100.",
        ),
        (
            "min_order_margin_pct",
            "21",
            "Minimum order margin % must be a number from 0 to 20.",
        ),
        (
            "min_order_margin_pct",
            "-1",
            "Minimum order margin % must be a number from 0 to 20.",
        ),
        (
            "max_coin_allocation_pct",
            "101",
            "Max per coin % must be a number from 0.1 to 100.",
        ),
        ("dca_multiplier", "0", "DCA multiplier must be a number from 0.1 to 10."),
        ("dca_multiplier", "two", "DCA multiplier must be a number from 0.1 to 10."),
        (
            "max_dca_buys_per_24h",
            "2.5",
            "Max DCA buys / coin (rolling 24h) must be a whole number from 0 to 100.",
        ),
    ],
)
def test_a_wrong_limit_is_refused_and_nothing_is_saved(root, folder, key, typed, said):
    box = Box()
    win = limits_window(root, folder, box=box)
    win.vars[key].set(typed)
    assert not win.save()
    name = [spec[1] for spec in ui.LIMITS if spec[0] == key][0].rstrip(":")
    assert f"{name} m{win.errors[key].get()[1:]}" == said  # beside the field
    assert {k for k, v in win.errors.items() if v.get()} == {key}
    assert win.written == [] and on_disk(folder) == {}  # the levels are not saved
    win.destroy()


def test_the_hub_default_margin_sits_beside_start_allocation():
    import pt_hub

    keys = list(pt_hub.DEFAULT_SETTINGS)
    i = keys.index("start_allocation_pct")
    assert keys[i + 1] == "min_order_margin_pct"
    assert pt_hub.DEFAULT_SETTINGS["min_order_margin_pct"] == 2.0
    assert set(pt_hub.RISK_LIMIT_KEYS) == set(LIMITS_SAVED)
    assert [spec[0] for spec in ui.LIMITS] == list(pt_hub.RISK_LIMIT_KEYS)


def test_limits_saved_in_the_hub_are_what_the_trader_reads(hub, monkeypatch):
    """Acceptance: the moved controls work as before: same keys, same file, read by
    the running trader's settings reload."""
    import pt_paths
    import pt_trader

    win = hub.open_risk_settings()
    win.withdraw()
    win.vars["start_allocation_pct"].set("3")
    win.vars["max_coin_allocation_pct"].set("20")
    win.vars["dca_multiplier"].set("1.5")
    win.vars["max_dca_buys_per_24h"].set("4")
    assert win.save()
    saved = hub._load_settings()
    assert {k: saved[k] for k in LIMITS_SAVED} == {
        "start_allocation_pct": 3.0,
        "min_order_margin_pct": 2.0,
        "max_coin_allocation_pct": 20.0,
        "dca_multiplier": 1.5,
        "max_dca_buys_per_24h": 4,
    }

    monkeypatch.setattr(pt_trader, "_GUI_SETTINGS_PATH", pt_paths.gui_settings_file())
    monkeypatch.setattr(
        pt_trader,
        "_gui_settings_cache",
        dict(pt_trader._gui_settings_cache, mtime=None),
    )
    monkeypatch.setattr(pt_trader, "_last_settings_mtime", None)
    for name in (
        "crypto_symbols",
        "main_dir",
        "base_paths",
        "TRADE_START_LEVEL",
        "START_ALLOC_PCT",
        "MAX_COIN_PCT",
        "DCA_MULTIPLIER",
        "DCA_LEVELS",
        "MAX_DCA_BUYS_PER_24H",
        "TRAILING_GAP_PCT",
        "PM_START_PCT_NO_DCA",
        "PM_START_PCT_WITH_DCA",
    ):
        monkeypatch.setattr(pt_trader, name, getattr(pt_trader, name))
    pt_trader._refresh_paths_and_symbols()
    assert (
        pt_trader.START_ALLOC_PCT,
        pt_trader.MAX_COIN_PCT,
        pt_trader.DCA_MULTIPLIER,
        pt_trader.MAX_DCA_BUYS_PER_24H,
    ) == (3.0, 20.0, 1.5, 4)
