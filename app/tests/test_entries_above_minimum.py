"""One entry per coin per signal (owner, 2026-11-04).

An entry raised to the exchange's minimum order was exactly the minimum. Bought at the
ask, it was worth a little less at the bid, so the trader took it for a remainder too
small to sell (dust), counted the coin as not held, and the next cycle bought it again.
Now:

* the entry keeps room above the minimum: minimum x (1 + spread + round-trip fee +
  margin), the margin being Settings' ``min_order_margin_pct`` (default 2%, 0-20);
* an open trade is never dust. Dust is what a sell left, or a holding the ledger has
  no trade for.

Everything runs under the isolation guard (app/conftest.py); no network.
"""

from __future__ import annotations

import json
import os
from unittest import mock

import pytest
from helpers import PaperTraderCase

import position_sizing as ps
import trading_mode as tm

# --- the rule ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "minimum, spread, fee, margin, floor",
    [
        (1.0, 0.0, 0.0, 0.0, 1.0),  # no room: the old rule
        (1.0, 0.0, 0.0, 2.0, 1.02),  # the default margin
        (1.0, 0.002, 0.024, 2.0, 1.046),  # spread 0.2%, 1.2% taker each way
        (5.0, 0.001, 0.002, 0.0, 5.015),
        (None, 0.01, 0.01, 2.0, None),  # no minimum stated: no floor
        (0.0, 0.01, 0.01, 2.0, None),
    ],
)
def test_the_smallest_entry_is_the_minimum_plus_spread_fees_and_margin(
    minimum, spread, fee, margin, floor
):
    assert ps.minimum_entry_usd(minimum, spread, fee, margin) == pytest.approx(floor)


def test_an_entry_below_the_floor_is_raised_to_it_and_one_above_is_kept():
    # 1% of $50 is $0.50: raised to $1 x (1 + 0.002 + 0.024 + 0.02)
    assert ps.entry_usd(50, 1.0, 1.0, 0.002, 0.024, 2.0) == pytest.approx(1.046)
    # $1.01 is above the minimum but below the floor: raised too
    assert ps.entry_usd(101, 1.0, 1.0, 0.002, 0.024, 2.0) == pytest.approx(1.046)
    assert ps.entry_usd(10_000, 1.0, 1.0, 0.002, 0.024, 2.0) == pytest.approx(100.0)


def test_the_spread_is_what_the_ask_is_above_the_bid_as_a_fraction_of_the_bid():
    assert ps.quote_spread(100.1, 99.9) == pytest.approx(0.2 / 99.9)
    # unknown or crossed prices leave no room
    for ask, bid in ((None, 99.9), (100.1, 0.0), (99.0, 100.0), ("x", 1.0)):
        assert ps.quote_spread(ask, bid) == 0.0


def test_a_position_at_the_floor_is_still_worth_the_minimum_at_the_bid():
    """The point of the room: bought at the ask with a 0.2% spread, a $1 entry was
    worth $0.998 at the bid; one at the floor is worth more than $1 even after a
    market sell's fee."""
    ask, bid, taker = 100.1, 99.9, 0.006
    old = 1.0 / ask * bid
    assert old < 1.0
    floor = ps.minimum_entry_usd(1.0, ps.quote_spread(ask, bid), 2 * taker, 2.0)
    assert floor / ask * bid * (1 - taker) > 1.0


@pytest.mark.parametrize(
    "value, valid",
    [(0, True), (2.0, True), (20, True), (20.5, False), (-1, False)]
    + [(None, False), ("2", False), (True, False)],
)
def test_the_margin_is_a_number_from_0_to_20(value, valid):
    assert ps.valid_min_order_margin_pct(value) is valid


def test_the_validator_passes_the_margin_to_the_trader():
    """The trader reads only the settings the validator returns."""
    from pt_validation import InputValidator, ValidationError

    assert InputValidator.validate_config_data({"min_order_margin_pct": 0}) == {
        "min_order_margin_pct": 0.0
    }
    with pytest.raises(ValidationError):
        InputValidator.validate_config_data({"min_order_margin_pct": 25})


# --- the trader ----------------------------------------------------------------------


class SmallPaperAccount(PaperTraderCase):
    """A legacy-mode paper trader on a $50 book, BTC only, bid 99.9 / ask 100.1, and
    exchanges in Settings whose minimum order is $1: 1% of the account is $0.50. The
    long signal is 3, the entry level: the neural DCA levels start at 4."""

    SETTINGS = {"trading": {"mode": "paper"}, "strategy": {"engine": "legacy_neural"}}

    def setUp(self):
        super().setUp()
        sleep = mock.patch.object(self.pt_trader.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        self.one_coin("BTC")
        self.folder = os.path.join(self.tmp.name, "neural")
        os.makedirs(self.folder)
        for p in (
            mock.patch.object(self.pt_trader, "base_paths", {"BTC": self.folder}),
            mock.patch.object(self.pt_trader, "main_dir", self.folder),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.quotes.bid, self.quotes.ask = 99.9, 100.1
        self.markets.minimum = 1.0
        book = os.path.join(self.tmp.name, "paper", "paper_account.json")
        os.makedirs(os.path.dirname(book), exist_ok=True)
        with open(book, "w", encoding="utf-8") as f:  # the trader loads this book
            json.dump(
                {"initial_balance": "50", "cash_balance": "50", "positions": {}}, f
            )

    def signal(self, long_level: int) -> None:
        for name, value in (
            ("long_dca_signal.txt", str(long_level)),
            ("short_dca_signal.txt", "0"),
        ):
            with open(os.path.join(self.folder, name), "w") as f:
                f.write(value)

    def buys(self) -> list:
        orders = tm.get_paper_exchange().account.orders.values()
        return [o for o in orders if o.side.value == "buy" and o.is_filled]

    def btc_held(self) -> float:
        return float(tm.get_paper_exchange().get_balance().get("BTC", 0.0))

    def test_a_coin_at_the_minimum_order_is_entered_once_per_signal(self):
        trader = self.trader(dict(self.SETTINGS))
        self.signal(3)
        for _ in range(3):
            trader.manage_trades()
        self.assertEqual(len(self.buys()), 1)
        # bought with room: worth more than the minimum at the bid
        self.assertGreater(self.btc_held() * self.quotes.bid, 1.0)
        self.assertEqual(len(self.ledger_rows()), 1)

    def test_an_entry_of_exactly_the_minimum_is_still_held(self):
        """With no room at all (the old rule) the position is worth less than the
        minimum at the bid, but it is the open trade: held, not bought again."""
        trader = self.trader(dict(self.SETTINGS))
        self.signal(3)
        with mock.patch.object(self.pt_trader, "MIN_ORDER_MARGIN_PCT", 0.0), mock.patch(
            "position_sizing.quote_spread", return_value=0.0
        ), mock.patch.object(trader, "_trading_fees", return_value=None):
            trader.manage_trades()
            self.assertLess(self.btc_held() * self.quotes.bid, 1.0)
            trader.manage_trades()
            trader.manage_trades()
        self.assertEqual(len(self.buys()), 1)
        self.assertEqual(
            trader._held_symbols(trader.get_holdings(), {"BTC-USD": self.quotes.bid}),
            ["BTC-USD"],
        )

    def test_an_open_trade_worth_less_than_the_minimum_is_managed(self):
        """An open trade the price (or a new minimum) took below the minimum order is
        not dust: it stops a new entry, and its exit is still tried."""
        trader = self.trader(dict(self.SETTINGS))
        self.signal(3)
        trader.manage_trades()
        self.markets.minimum = 1_000.0
        trader._dust_minimums.clear()
        self.assertFalse(trader._is_dust("BTC-USD", self.btc_held(), self.quotes.bid))
        trader.trailing_pm["BTC"] = {
            "active": True,
            "line": 120.0,
            "peak": 121.0,
            "was_above": True,
            "settings_sig": (
                float(trader.trailing_gap_pct),
                float(trader.pm_start_pct_no_dca),
                float(trader.pm_start_pct_with_dca),
            ),
        }
        with mock.patch.object(trader, "place_sell_order", return_value=None) as sell:
            trader.manage_trades()
        sell.assert_called_once()  # the trailing line's sell: not skipped as dust
        self.assertEqual(len(self.buys()), 1)

    def test_a_remainder_left_by_a_sell_is_still_dust(self):
        """A sell that ends the trade but leaves a remainder too small to sell (a
        quantity rounded down to the exchange's step): the ledger keeps the remainder,
        but it is not a trade, so a new entry is made."""
        trader = self.trader(dict(self.SETTINGS))
        self.signal(3)
        trader.manage_trades()
        bought = self.btc_held()
        remainder = 0.000001  # ~$0.0001
        trader.place_sell_order(
            "exit", "sell", "market", "BTC-USD", round(bought - remainder, 8)
        )
        self.assertAlmostEqual(self.btc_held(), remainder, places=8)
        (sell,) = [r for r in self.ledger_rows() if r["side"] == "sell"]
        self.assertTrue(sell["closes_position"])
        self.assertGreater(trader._pnl_ledger["open_positions"]["BTC"]["qty"], 0.0)

        self.assertTrue(trader._is_dust("BTC-USD", self.btc_held(), self.quotes.bid))
        trader.manage_trades()  # the signal is still on: a new trade
        self.assertEqual(len(self.buys()), 2)
        self.assertFalse(trader._is_dust("BTC-USD", self.btc_held(), self.quotes.bid))

    def test_after_a_restart_a_remainder_is_still_dust_and_a_trade_still_open(self):
        self.signal(3)
        self.trader(dict(self.SETTINGS)).manage_trades()
        trader = self.trader(dict(self.SETTINGS))  # rebuilt from the books
        self.assertTrue(trader._open_trade("BTC"))
        bought = self.btc_held()
        trader.place_sell_order(
            "exit", "sell", "market", "BTC-USD", round(bought - 0.000001, 8)
        )
        restarted = self.trader(dict(self.SETTINGS))
        self.assertFalse(restarted._open_trade("BTC"))
        self.assertTrue(restarted._is_dust("BTC-USD", self.btc_held(), self.quotes.bid))

    def keep_settings_globals(self) -> None:
        """Put back afterwards every global a settings reload sets."""
        names = (
            "crypto_symbols main_dir base_paths TRADE_START_LEVEL START_ALLOC_PCT "
            "MAX_COIN_PCT MIN_ORDER_MARGIN_PCT DCA_MULTIPLIER DCA_LEVELS "
            "MAX_DCA_BUYS_PER_24H TRAILING_GAP_PCT PM_START_PCT_NO_DCA "
            "PM_START_PCT_WITH_DCA _last_settings_mtime"
        ).split()
        for name in names:
            p = mock.patch.object(self.pt_trader, name, getattr(self.pt_trader, name))
            p.start()
            self.addCleanup(p.stop)

    def test_a_saved_margin_reaches_the_trader_through_the_settings_file(self):
        """gui_settings.json as Settings saves it, read the way the trader reads it
        (the path check, then InputValidator.validate_config_data, which passes on
        only the keys it knows): the entry has the saved margin, a change is used
        from the next cycle, and an out-of-range value is refused (the last good
        settings stay)."""
        import pt_paths

        self.keep_settings_globals()
        path = pt_paths.gui_settings_file()
        for p in (
            mock.patch.object(self.pt_trader, "_GUI_SETTINGS_PATH", path),
            mock.patch.dict(self.pt_trader._gui_settings_cache, {"mtime": None}),
        ):
            p.start()
            self.addCleanup(p.stop)

        def save(margin, mtime):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "coins": ["BTC"],
                        "main_neural_dir": self.folder,
                        "min_order_margin_pct": margin,
                    },
                    f,
                )
            os.utime(path, (mtime, mtime))

        save(7.5, 1_000_000)
        trader = self.trader(dict(self.SETTINGS))
        self.signal(3)
        trader.manage_trades()  # reads the settings file first
        self.assertEqual(self.pt_trader.MIN_ORDER_MARGIN_PCT, 7.5)
        (buy,) = self.buys()
        fees = trader._trading_fees("BTC-USD")
        room = 0.2 / 99.9 + 2 * fees.taker + 0.075
        bought = float(buy.filled_quantity * buy.filled_price)  # 8-decimal quantity
        self.assertAlmostEqual(bought, 1 + room, places=6)

        save(0, 1_000_100)  # changed in Settings: used from the next cycle
        trader.manage_trades()
        self.assertEqual(self.pt_trader.MIN_ORDER_MARGIN_PCT, 0.0)

        save(25, 1_000_200)  # out of range: the file is refused, 0 stays
        with self.assertLogs(level="ERROR"):
            trader.manage_trades()
        self.assertEqual(self.pt_trader.MIN_ORDER_MARGIN_PCT, 0.0)

    def test_the_margin_comes_from_settings(self):
        trader = self.trader(dict(self.SETTINGS))
        self.signal(3)
        gui = {"mtime": 1.0, "coins": ["BTC"], "min_order_margin_pct": 10.0}
        self.keep_settings_globals()
        with mock.patch.object(self.pt_trader, "_load_gui_settings", lambda: gui):
            self.pt_trader._refresh_paths_and_symbols()
            self.assertEqual(self.pt_trader.MIN_ORDER_MARGIN_PCT, 10.0)
            amount, floor = trader._entry_size("BTC-USD", 50.0, 100.1, 99.9)
            fees = trader._trading_fees("BTC-USD")
            room = 0.2 / 99.9 + (2 * fees.taker if fees else 0.0) + 0.10
            self.assertAlmostEqual(amount, 1.0 + room)
            self.assertAlmostEqual(floor, amount)

            for bad, mtime in ((25.0, 2.0), ("x", 3.0), (None, 4.0)):
                gui.update(mtime=mtime, min_order_margin_pct=bad)
                with self.assertLogs(level="WARNING"):
                    self.pt_trader._refresh_paths_and_symbols()
                self.assertEqual(self.pt_trader.MIN_ORDER_MARGIN_PCT, 2.0)
            gui.update(mtime=5.0, min_order_margin_pct=0.0)  # 0 is a margin too
            self.pt_trader._refresh_paths_and_symbols()
            self.assertEqual(self.pt_trader.MIN_ORDER_MARGIN_PCT, 0.0)
