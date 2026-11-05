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
