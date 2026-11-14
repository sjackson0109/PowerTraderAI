"""The account drawdown stop: its levels (Settings > Risk), the peak kept across
restarts (risk_state), and the trader's use of both."""

from __future__ import annotations

import json
import os
from unittest import mock

import pytest

import pt_settings_manager as psm
import risk_state
import trading_mode as tm
from pt_risk import RiskLimits, RiskManager
from pt_settings_manager import SettingsManager

# --- the levels in settings ------------------------------------------------------------


def test_the_levels_have_defaults_in_the_settings_manager(tmp_path):
    m = SettingsManager("pt_config.json", str(tmp_path))
    assert m.get(psm.DRAWDOWN_WARNING_KEY) == 3.0
    assert m.get(psm.DRAWDOWN_CRITICAL_KEY) == 5.0
    assert m.get(psm.EMERGENCY_DRAWDOWN_KEY) == 8.0


def test_a_level_out_of_range_in_the_file_is_repaired(tmp_path):
    with open(tmp_path / "pt_config.json", "w", encoding="utf-8") as f:
        json.dump({"risk": {"drawdown_warning_pct": 0, "drawdown_critical_pct": 99}}, f)
    m = SettingsManager("pt_config.json", str(tmp_path))
    assert m.get(psm.DRAWDOWN_WARNING_KEY) == 3.0
    assert m.get(psm.DRAWDOWN_CRITICAL_KEY) == 5.0


def test_set_risk_saves_levels_in_order_and_keeps_other_keys(tmp_path):
    m = SettingsManager("pt_config.json", str(tmp_path))
    m.set_section("risk", {"emergency_drawdown_pct": 8.0, "other": "kept"})
    assert m.set_risk({"drawdown_warning_pct": 1.5, "drawdown_critical_pct": 4})
    risk = SettingsManager("pt_config.json", str(tmp_path)).get("risk")
    assert risk == {
        "drawdown_warning_pct": 1.5,
        "drawdown_critical_pct": 4,
        "emergency_drawdown_pct": 8.0,
        "other": "kept",
    }


@pytest.mark.parametrize(
    "values",
    [
        {"drawdown_warning_pct": 5.0, "drawdown_critical_pct": 5.0},
        {"drawdown_critical_pct": 9.0},  # above the 8% stop
        {"emergency_drawdown_pct": 4.0},  # below the 5% critical level
        {"drawdown_warning_pct": "3"},
        {"emergency_drawdown_pct": 51},
    ],
)
def test_set_risk_refuses_a_level_out_of_range_or_order(tmp_path, values):
    m = SettingsManager("pt_config.json", str(tmp_path))
    assert not m.set_risk(values)
    assert not os.path.exists(tmp_path / "pt_config.json")
    assert m.get("risk")["drawdown_warning_pct"] == 3.0


def test_the_problem_says_which_level_is_wrong():
    assert psm.drawdown_levels_problem(3, 5, 8) == ""
    assert psm.drawdown_levels_problem(5, 3, 8) == "Warning must be below Critical"
    assert (
        psm.drawdown_levels_problem(3, 8, 8) == "Critical must be below Emergency stop"
    )
    assert "from 1 to 50" in psm.drawdown_levels_problem(3, 5, 0.5)


def test_the_trader_reads_the_levels_and_falls_back_on_a_bad_pair():
    read = tm.read_drawdown_levels
    assert read({}) == tm.DrawdownLevels(3.0, 5.0, 8.0)
    saved = {"risk": {"drawdown_warning_pct": 2, "drawdown_critical_pct": 6.5}}
    assert read(saved) == tm.DrawdownLevels(2.0, 6.5, 8.0)
    tm._drawdown_logged.clear()
    for bad in (
        {"drawdown_warning_pct": 6, "drawdown_critical_pct": 5},  # not in order
        {"drawdown_warning_pct": 3, "drawdown_critical_pct": 9},  # above the stop
        {"drawdown_warning_pct": "x"},
        {"drawdown_critical_pct": True},
    ):
        with mock.patch.object(tm.logger, "warning") as warn:
            assert read({"risk": bad}) == tm.DrawdownLevels(3.0, 5.0, 8.0), bad
            warn.assert_called_once()
        with mock.patch.object(tm.logger, "warning") as warn:
            read({"risk": bad})  # the same problem is logged once, not every check
            warn.assert_not_called()
    # a bad pair never moves the stop
    odd = {"risk": {"drawdown_warning_pct": 9, "emergency_drawdown_pct": 12}}
    assert read(odd).emergency_pct == 12.0


def test_risk_manager_levels_come_from_settings_not_constants():
    rm = RiskManager(RiskLimits())
    assert rm.risk_thresholds["portfolio_drawdown"] == {
        "warning": psm.DEFAULT_DRAWDOWN_WARNING_PCT / 100.0,
        "critical": psm.DEFAULT_DRAWDOWN_CRITICAL_PCT / 100.0,
        "emergency": psm.DEFAULT_EMERGENCY_DRAWDOWN_PCT / 100.0,
    }
    rm.set_drawdown_levels(1, 2.5, 10)
    assert rm.risk_thresholds["portfolio_drawdown"] == {
        "warning": 0.01,
        "critical": 0.025,
        "emergency": 0.1,
    }


# --- the trader's drawdown check ------------------------------------------------------


def adapter(settings=None, state_dir=None):
    import pt_trader

    return pt_trader._TraderRiskAdapter(
        settings_source=settings if settings is not None else {},
        state_dir=state_dir,
    )


def test_the_trader_warns_at_the_saved_warning_and_critical_levels():
    """Acceptance: the warning and critical levels come from settings."""
    settings = {"risk": {"drawdown_warning_pct": 1, "drawdown_critical_pct": 2}}
    a = adapter(settings)
    a.peak_value = 1000.0
    assert a.check_emergency_conditions(995.0)["warnings"] == []
    assert a.check_emergency_conditions(985.0)["warnings"] == [
        "Account drawdown 1.5% (warning level)"
    ]
    assert a.check_emergency_conditions(975.0)["warnings"] == [
        "Account drawdown 2.5% (critical level)"
    ]
    assert a.manager.risk_thresholds["portfolio_drawdown"]["critical"] == 0.02
    # changed while the trader runs: the next check uses the new levels
    settings["risk"] = {"drawdown_warning_pct": 4, "drawdown_critical_pct": 6}
    assert a.check_emergency_conditions(975.0)["warnings"] == []
    assert a.check_emergency_conditions(955.0)["warnings"] == [
        "Account drawdown 4.5% (warning level)"
    ]


def test_the_stop_reason_names_a_fractional_stop_as_saved():
    a = adapter({"risk": {"emergency_drawdown_pct": 7.5}})
    a.peak_value = 1000.0
    status = a.check_emergency_conditions(920.0)
    assert status["emergency_stop"]
    assert status["reason"] == "Account drawdown 8.0% reached the 7.5% emergency limit"


# --- the peak, kept across restarts ---------------------------------------------------


def test_the_peak_is_kept_across_a_restart(tmp_path):
    books = str(tmp_path)
    first = adapter(state_dir=books)
    assert first.peak_value == 0.0
    for value in (1000.0, 1200.0, 1100.0):
        first.update_portfolio_value(value)
    assert first.peak_value == 1200.0
    restarted = adapter(state_dir=books)  # a new trader process
    assert restarted.peak_value == 1200.0
    # measured from the kept peak, not from the first value after the restart
    assert restarted.check_emergency_conditions(1150.0)["warnings"] == [
        "Account drawdown 4.2% (warning level)"
    ]
    assert risk_state.current(books).peak_value == 1200.0


def test_without_a_books_folder_nothing_is_written():
    a = adapter()
    with mock.patch.object(risk_state, "write_state") as write:
        a.update_portfolio_value(500.0)
    assert a.peak_value == 500.0
    write.assert_not_called()


def test_reset_peak_applies_once_while_running_and_at_start(tmp_path):
    books = str(tmp_path)
    running = adapter(state_dir=books)
    running.update_portfolio_value(1000.0)
    risk_state.request_peak_reset(books, 900.0, now=1e10)
    running.update_portfolio_value(880.0)  # the next check applies it
    assert running.peak_value == 900.0
    running.update_portfolio_value(950.0)  # and the peak rises again after it
    assert running.peak_value == 950.0
    restarted = adapter(state_dir=books)  # the old request is not applied again
    assert restarted.peak_value == 950.0

    risk_state.request_peak_reset(books, 700.0, now=2e10)  # while stopped
    assert risk_state.current(books).peak_value == 700.0  # what the hub shows
    assert adapter(state_dir=books).peak_value == 700.0  # applied at start


def test_requests_are_applied_by_rule():
    state = {"peak_value": 10.0, "peak_reset_ts": 5.0}
    assert risk_state.apply_requests(state, {}) == state
    old = {"reset_peak": {"ts": 4.0, "value": 3.0}}
    assert risk_state.apply_requests(state, old) == state
    for bad in ({"ts": 9.0, "value": 0}, {"ts": 9.0, "value": "x"}, "nope"):
        assert risk_state.apply_requests(state, {"reset_peak": bad}) == state
    new = risk_state.apply_requests(state, {"reset_peak": {"ts": 9.0, "value": 3.0}})
    assert new == {"peak_value": 3.0, "peak_ts": 9.0, "peak_reset_ts": 9.0}
    with pytest.raises(ValueError):
        risk_state.request_peak_reset("unused", 0.0)


def test_an_unreadable_request_file_asks_for_nothing(tmp_path):
    books = str(tmp_path)
    risk_state.write_state(books, {"peak_value": 50.0})
    with open(risk_state.requests_path(books), "w", encoding="utf-8") as f:
        f.write("{not json")
    assert risk_state.current(books).peak_value == 50.0
    assert adapter(state_dir=books).peak_value == 50.0


def test_a_peak_reset_without_a_value_clears_the_peak(tmp_path):
    books = str(tmp_path)
    risk_state.write_state(books, {"peak_value": 10_000.0, "peak_ts": 5.0})
    risk_state.request_peak_reset(books, None, now=9.0)
    assert risk_state.current(books).peak_value == 0.0
    a = adapter(state_dir=books)
    assert a.peak_value == 0.0
    a.update_portfolio_value(1_000.0)  # the next account value is the peak
    assert a.peak_value == 1_000.0 == risk_state.current(books).peak_value


# --- the halt, kept across restarts ---------------------------------------------------


def test_a_resume_clears_only_the_halt_it_was_asked_for_after():
    halted = risk_state.halted_state({"peak_value": 10.0}, "why", 9.0, now=100.0)
    assert halted == {
        "peak_value": 10.0,
        "halted": True,
        "halt_reason": "why",
        "halted_ts": 100.0,
        "halt_value": 9.0,
    }
    before = {"resume": {"ts": 99.0}}  # pressed before this halt began
    assert risk_state.apply_requests(halted, before) == halted
    resumed = risk_state.apply_requests(halted, {"resume": {"ts": 101.0}})
    assert resumed == {"peak_value": 10.0, "resumed_ts": 101.0}
    # a later halt is not cleared by that resume
    again = risk_state.halted_state(resumed, "again", None, now=200.0)
    assert risk_state.apply_requests(again, {"resume": {"ts": 101.0}})["halted"]


def test_an_unreadable_state_file_is_a_halt(tmp_path):
    books = str(tmp_path)
    with open(risk_state.state_path(books), "w", encoding="utf-8") as f:
        f.write("{damaged")
    view = risk_state.current(books)
    assert view.halted and view.halt_reason == risk_state.UNREADABLE_REASON
    assert adapter(state_dir=books).is_trading_halted()
    risk_state.request_resume(books)  # after the file was damaged: clears it
    assert not risk_state.current(books).halted
    resumed = adapter(state_dir=books)
    assert not resumed.is_trading_halted()
    assert risk_state.read_state(books)["resumed_ts"] > 0  # rewritten, readable


def test_the_view_shows_the_halt(tmp_path):
    books = str(tmp_path)
    assert not risk_state.current(books).halted
    risk_state.write_state(
        books, risk_state.halted_state({"peak_value": 50.0}, "Stop", 45.0, now=7.0)
    )
    view = risk_state.current(books)
    assert (view.halted, view.halt_reason, view.halted_ts, view.halt_value) == (
        True,
        "Stop",
        7.0,
        45.0,
    )
    assert risk_state.current(None) == risk_state.RiskView(0.0, 0.0)


def test_the_view_shows_what_the_value_leaves_out_and_why_buys_wait(tmp_path):
    books = str(tmp_path)
    risk_state.write_state(books, {"peak_value": 50.0})  # a file from before
    view = risk_state.current(books)
    assert (view.not_counted, view.buys_waiting, view.buys_waiting_ts) == ((), "", 0.0)
    risk_state.write_state(
        books,
        {
            "peak_value": 50.0,
            "not_counted": [
                {"asset": "GBP", "quantity": 1250.0, "why": "no USD price"},
                {"asset": "", "quantity": 1.0},  # unusable entries are skipped
                "XRP",
            ],
            "buys_waiting": "no account value",
            "buys_waiting_ts": 9.0,
        },
    )
    view = risk_state.current(books)
    assert view.not_counted == (("GBP", 1250.0, "no USD price"),)
    assert (view.buys_waiting, view.buys_waiting_ts) == ("no account value", 9.0)
    assert view.peak_value == 50.0


def test_a_peak_reset_clears_the_last_balances(tmp_path):
    state = {
        "peak_value": 10.0,
        "last_balances": {"USD": 6.0, "BTC": 0.04},
        "last_balances_ts": 5.0,
        "balance_changes": [{"ts": 4.0, "kind": "loss", "value": -1.0}],
    }
    after = risk_state.apply_requests(state, {"reset_peak": {"ts": 9.0, "value": 8.0}})
    assert "last_balances" not in after and "last_balances_ts" not in after
    assert after["peak_value"] == 8.0
    assert after["balance_changes"] == state["balance_changes"]  # kept, as facts
    cleared = risk_state.apply_requests(
        state, {"reset_peak": {"ts": 9.0, "value": None}}
    )
    assert "last_balances" not in cleared  # a Paper Account save clears them too
    # a reset applied before is not applied again
    again = dict(after, last_balances={"USD": 7.0}, last_balances_ts=10.0)
    assert (
        risk_state.apply_requests(again, {"reset_peak": {"ts": 9.0, "value": 8.0}})
        == again
    )


from helpers import PaperTraderCase  # noqa: E402


class StopRun(BaseException):
    """Ends the trader's endless loop in a test (run() catches Exception)."""


class HaltAcrossRestartTests(PaperTraderCase):
    """Acceptance: after an emergency stop, a restart buys nothing until Resume, and
    still manages what is held (sells go through)."""

    def started(self, account_value=None):
        trader = self.trader()
        trader._last_good_account_snapshot["total_account_value"] = account_value
        return trader

    def run_once(self, trader):
        """run() until it reaches manage_trades (which a halt no longer stops)."""
        with mock.patch.object(
            trader, "manage_trades", side_effect=StopRun
        ) as manage, mock.patch.object(self.pt_trader.time, "sleep"):
            try:
                trader.run()
            except StopRun:
                pass
        return manage.called

    def test_a_restart_after_an_emergency_stop_buys_nothing_until_resume(self):
        books = os.path.join(self.tmp.name, "paper")
        first = self.started(account_value=900.0)
        first.risk_manager.update_portfolio_value(1000.0)  # the peak, kept
        self.assertTrue(self.run_once(first))  # 10% drawdown: halted, still managing
        self.assertTrue(first.risk_manager.is_trading_halted())
        view = risk_state.current(books)
        self.assertTrue(view.halted)
        self.assertEqual(
            view.halt_reason, "Account drawdown 10.0% reached the 8% emergency limit"
        )
        self.assertEqual(view.halt_value, 900.0)

        # a restart, even with the account back above the peak, buys nothing;
        # it still manages what is held, so a sell goes through
        restarted = self.started(account_value=1100.0)
        self.assertTrue(restarted.risk_manager.is_trading_halted())
        self.assertEqual(restarted.risk_manager.halt_reason, view.halt_reason)
        self.assertTrue(self.run_once(restarted))
        refused = restarted._risk_check("BTC-USD", "buy", 0.001, 100.0)
        self.assertFalse(refused)
        self.assertTrue(restarted._risk_check("BTC-USD", "sell", 0.001, 100.0))
        self.assertTrue(risk_state.current(books).halted)  # still halted

        risk_state.request_resume(books)  # Resume trading in Settings > Risk
        resumed = self.started()
        self.assertFalse(resumed.risk_manager.is_trading_halted())
        self.assertTrue(self.run_once(resumed))  # it trades again
        self.assertFalse(risk_state.current(books).halted)
        # the halted restart still watched the account: 1100 was its new peak
        self.assertEqual(risk_state.current(books).peak_value, 1100.0)

    def test_a_halt_that_cannot_be_saved_is_reported(self):
        trader = self.started(account_value=900.0)
        trader.risk_manager.update_portfolio_value(1000.0)
        with mock.patch.object(
            risk_state, "write_state", side_effect=OSError("disk full")
        ), mock.patch("builtins.print") as said:
            self.assertTrue(self.run_once(trader))
        self.assertTrue(trader.risk_manager.is_trading_halted())
        self.assertIn("The halt could not be saved", str(said.call_args_list))
