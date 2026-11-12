"""An exploratory backtest at each of the programme's account sizes (PTAI-RD-001 WP 2.6).

* The same trades are replayed at £50, £200, £500 and £10,000, and each account is
  reported separately: its results, its return, buy-and-hold, its drawdowns and
  recovery, and its period returns.
* The run's own account and the same size in the list agree.
* An account too small for the venue's minimum orders does not take the trades the
  largest account takes, and says so.

Synthetic candles and a fake venue: no network."""

from __future__ import annotations

import pytest
from test_strategy_backtest_window import config, lab, loader, venue  # noqa: F401

from research_stats import periods
from strategy_lab import runs
from strategy_lab.venue import VenueRules


def test_every_account_size_is_reported_separately(lab):  # noqa: F811
    record = runs.run(config(), loader=loader, venue=venue, save=False)
    accounts = record["accounts"]
    assert [a["account_gbp"] for a in accounts] == [50.0, 200.0, 500.0, 10_000.0]
    assert [a["account_usd"] for a in accounts] == [62.5, 250.0, 625.0, 12_500.0]
    for a in accounts:
        s = a["strategy_result"]
        assert a["return"] == pytest.approx(s["net_usd"] / a["account_usd"])
        assert a["trades_taken"] == s["trades"]
        assert set(a["periods"]) == set(periods.PERIODS) | {
            "annual_growth",
            "target_annual",
        }
        assert a["drawdowns"]["max_drawdown"] >= 0.0
    assert accounts[-1]["same_trades_as_largest"] is True


def test_the_runs_own_account_matches_its_size_in_the_list(lab):  # noqa: F811
    record = runs.run(config(), loader=loader, venue=venue, save=False)
    own = next(a for a in record["accounts"] if a["account_gbp"] == 500.0)
    assert own["strategy_result"] == record["strategy_result"]
    assert own["buy_and_hold"]["net_usd"] == pytest.approx(
        record["buy_and_hold"]["net_usd"]
    )
    assert record["drawdowns"]["max_drawdown"] == pytest.approx(
        own["drawdowns"]["max_drawdown"]
    )


def test_a_small_account_cannot_take_every_trade_the_largest_takes(lab):  # noqa: F811
    def dear(coins):
        return VenueRules({c: 40.0 for c in coins}, {}, {})

    record = runs.run(config(), loader=loader, venue=dear, save=False)
    small, largest = record["accounts"][0], record["accounts"][-1]
    assert small["same_trades_as_largest"] is False
    assert small["trades_taken"] < largest["trades_taken"]
    s = small["strategy_result"]
    assert s["skipped_cash"] + s["skipped_minimum"] > 0
