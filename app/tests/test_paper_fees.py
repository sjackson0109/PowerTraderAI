"""Paper fills pay trading fees (owner, 2026-11-04).

Every paper fill pays a fee at the rate of the exchange whose quote priced it, from
the exchange layer's ``trading_fees()``: the taker rate for a market order, the maker
rate for a limit order. Without rates from the layer, that exchange's stored standard
rates are used, and without any exchange the paper account's own rate, each with a
logged warning. The fee comes out of the paper cash, is in the cost basis and the
realised profit, and is recorded on each trade (amount in USD, rate, maker or taker,
whose rates and from where), so Trade History shows it.

Everything runs under the isolation guard (app/conftest.py); no network.
"""

from __future__ import annotations

import json
import logging
import os
import time
import types
import unittest
from decimal import Decimal
from unittest import mock

import pytest
from helpers import PaperTraderCase

import pt_exchange_abstraction as pea
import trade_history_view
import trading_mode as tm
from pt_exchange_abstraction import Sourced, TradingFees

KRAKEN = TradingFees(maker=0.0025, taker=0.004, exchange="kraken", source="exchange")


def quote(bid=99.0, ask=101.0, exchange="kraken"):
    now = time.time()
    return tm.Quote(bid=bid, ask=ask, quote_ts=now, fetched_ts=now, exchange=exchange)


class FeeFeed:
    """A fee feed that records what it was asked: (coin, exchange)."""

    def __init__(self, fees=KRAKEN):
        self.fees = fees
        self.asked = []

    def __call__(self, base, exchange):
        self.asked.append((base, exchange))
        if isinstance(self.fees, Exception):
            raise self.fees
        return self.fees


class PaperExchangeFees(unittest.TestCase):
    def setUp(self):
        pea._default_fees_warned.clear()
        self.addCleanup(pea._default_fees_warned.clear)

    def make(self, fees=KRAKEN, exchange="kraken", **kwargs):
        self.feed = FeeFeed(fees)
        return tm.PaperExchange(
            price_feed=lambda base: quote(exchange=exchange),
            fee_feed=self.feed,
            **kwargs,
        )

    def test_a_market_buy_pays_the_taker_rate_of_the_exchange_that_priced_it(self):
        ex = self.make()
        result = ex.place_order("BTC-USD", "buy", 0.5)
        self.assertEqual(self.feed.asked, [("BTC", "kraken")])
        self.assertEqual(result.status, "filled")
        self.assertAlmostEqual(result.filled_value, 50.5)
        self.assertAlmostEqual(result.fee, 50.5 * 0.004)
        self.assertEqual(
            (
                result.fee_currency,
                result.fee_rate,
                result.fee_type,
                result.fee_exchange,
                result.fee_source,
            ),
            ("USD", 0.004, "taker", "kraken", "exchange"),
        )
        # the fee came out of the cash, on top of the coin's price
        self.assertAlmostEqual(ex.get_balance()["USD"], 10_000 - 50.5 * 1.004)

    def test_a_market_sell_pays_it_out_of_the_proceeds(self):
        ex = self.make()
        ex.place_order("BTC-USD", "buy", 0.5)
        result = ex.place_order("BTC-USD", "sell", 0.5)
        self.assertAlmostEqual(result.filled_value, 49.5)
        self.assertAlmostEqual(result.fee, 49.5 * 0.004)
        self.assertAlmostEqual(
            ex.get_balance()["USD"], 10_000 - 50.5 * 1.004 + 49.5 * 0.996
        )
        # the order status the trader polls says the same
        again = ex.get_order_status(result.order_id)
        self.assertEqual((again.fee, again.fee_type), (result.fee, "taker"))

    def test_a_limit_order_is_counted_as_a_maker_order(self):
        ex = self.make()
        ex.get_quote("BTC-USD")  # the exchange that last priced the coin: Kraken
        result = ex.place_order("BTC-USD", "buy", 0.5, price=100.0)
        order = ex.account.orders[result.order_id]
        self.assertEqual(order.commission_rate, Decimal("0.0025"))
        self.assertEqual((result.fee_type, result.fee_rate), ("maker", 0.0025))
        # a limit order waits: no fill, no fee yet
        self.assertEqual(result.status, "pending")
        self.assertIsNone(result.fee)
        self.assertIsNone(result.filled_value)

    def test_without_the_exchanges_rates_its_standard_rates_are_used(self):
        ex = self.make(fees=None, exchange="coinbase")
        with self.assertLogs("pt_exchange_abstraction", level="WARNING") as logs:
            result = ex.place_order("BTC-USD", "buy", 0.5)
        self.assertEqual(
            logs.output,
            [
                "WARNING:pt_exchange_abstraction:Coinbase trading fees could not be "
                "read from the exchange; using its standard rates: maker 0.60%, "
                "taker 1.20%"
            ],
        )
        self.assertEqual((result.fee_rate, result.fee_source), (0.012, "default"))
        self.assertAlmostEqual(result.fee, 50.5 * 0.012)

    def test_a_feed_that_fails_or_answers_nonsense_is_no_answer(self):
        for answer in (RuntimeError("boom"), mock.Mock(), TradingFees(2, 2, "x", "y")):
            ex = self.make(fees=answer, exchange="kucoin")
            result = ex.place_order("BTC-USD", "buy", 0.5)
            self.assertEqual((result.fee_rate, result.fee_source), (0.001, "default"))

    def test_with_no_exchange_at_all_the_paper_accounts_own_rate_is_used(self):
        """A simulated price has no exchange, and the exchange layer gave nothing."""
        ex = self.make(fees=None, exchange="")
        with self.assertLogs("trading_mode", level="WARNING") as logs:
            result = ex.place_order("BTC-USD", "buy", 0.5)
        self.assertIn(
            "No trading fees for BTC from the exchanges in Settings; paper fills pay "
            "0.10%",
            logs.output[-1],
        )
        self.assertEqual(self.feed.asked, [("BTC", "")])
        self.assertEqual(
            (result.fee_rate, result.fee_source, result.fee_exchange),
            (0.001, "paper", ""),
        )
        self.assertAlmostEqual(result.fee, 50.5 * 0.001)

    def test_rates_are_reused_for_an_hour(self):
        now = [1_000_000.0]
        ex = self.make(clock=lambda: now[0], settings_source={})
        with mock.patch.object(tm, "classify_quote", return_value="live"):
            ex.place_order("BTC-USD", "buy", 0.1)
            ex.place_order("BTC-USD", "buy", 0.1)
            self.assertEqual(len(self.feed.asked), 1)
            now[0] += 3_601.0
            ex.place_order("BTC-USD", "buy", 0.1)
        self.assertEqual(len(self.feed.asked), 2)

    def test_the_rates_a_coin_would_pay_are_those_of_its_last_quote(self):
        ex = self.make()
        self.assertEqual(ex.trading_fees("BTC-USD"), KRAKEN)  # before any quote
        self.assertEqual(self.feed.asked, [("BTC", "")])  # primary first
        ex.get_market_data("BTC-USD")
        self.assertEqual(ex.trading_fees("BTC-USD"), KRAKEN)
        self.assertEqual(self.feed.asked[-1], ("BTC", "kraken"))


class FeesFromTheExchangeLayer(unittest.TestCase):
    def setUp(self):
        pea._default_fees_warned.clear()
        self.addCleanup(pea._default_fees_warned.clear)

    def test_the_exchange_that_priced_the_fill_is_asked(self):
        answer = Sourced(KRAKEN, exchange="kraken", pair="XBTUSD", primary=False)
        with mock.patch.object(tm, "_layer_fees", return_value=answer) as layer:
            self.assertEqual(tm.fetch_trading_fees("BTC", "kraken"), KRAKEN)
        layer.assert_called_once_with("BTC", "kraken")

    def test_the_layer_is_asked_for_that_one_exchange_or_primary_first(self):
        manager = mock.Mock()
        manager.trading_fees.return_value = None
        with mock.patch("pt_multi_exchange.market_exchanges", return_value=manager):
            tm._layer_fees("BTC", "kraken")
            tm._layer_fees("BTC", "")
        self.assertEqual(
            manager.trading_fees.call_args_list,
            [mock.call("BTC", only="kraken"), mock.call("BTC", only=None)],
        )

    def test_when_the_layer_cannot_be_asked_the_standard_rates_are_used(self):
        with mock.patch.object(tm, "_layer_fees", side_effect=RuntimeError("down")):
            fees = tm.fetch_trading_fees("BTC", "binance")
            self.assertEqual(fees, TradingFees(0.001, 0.001, "binance", "default"))
            self.assertIsNone(tm.fetch_trading_fees("BTC", ""))
        with mock.patch.object(tm, "_layer_fees", return_value=None):
            self.assertEqual(tm.fetch_trading_fees("BTC", "kraken").source, "default")

    def test_the_process_wide_paper_exchange_asks_the_exchange_layer(self):
        """The process-wide paper exchange asks the exchange layer for fees."""
        tm.reset_paper_exchange()
        self.addCleanup(tm.reset_paper_exchange)
        self.assertIs(tm.get_paper_exchange()._fee_feed, tm.fetch_trading_fees)
        ex = tm.configure_paper_exchange(price_feed=None)
        self.assertIs(ex._fee_feed, tm.fetch_trading_fees)


class TraderPaysPaperFees(PaperTraderCase):
    """The trader on a $10,000 paper book, bid 99 / ask 101 from Coinbase, whose
    taker rate is 0.6%."""

    SETTINGS = {"trading": {"mode": "paper"}, "strategy": {"engine": "legacy_neural"}}

    def setUp(self):
        super().setUp()
        sleep = mock.patch.object(self.pt_trader.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        self.one_coin("BTC")
        self.fees.maker, self.fees.taker = 0.004, 0.006
        self.folder = os.path.join(self.tmp.name, "neural")
        os.makedirs(self.folder)
        for p in (
            mock.patch.object(self.pt_trader, "base_paths", {"BTC": self.folder}),
            mock.patch.object(self.pt_trader, "main_dir", self.folder),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.signal(0)

    def signal(self, long_level: int) -> None:
        for name, value in (
            ("long_dca_signal.txt", str(long_level)),
            ("short_dca_signal.txt", "0"),
        ):
            with open(os.path.join(self.folder, name), "w") as f:
                f.write(value)

    def buy_then_sell(self, trader):
        buy = trader.place_buy_order("id", "buy", "market", "BTC-USD", 100.0)
        sell = trader.place_sell_order(
            "id2", "sell", "market", "BTC-USD", buy["quantity"]
        )
        return buy, sell

    def test_every_paper_trade_records_its_fee(self):
        trader = self.trader(dict(self.SETTINGS))
        buy, _ = self.buy_then_sell(trader)
        qty = buy["quantity"]
        rows = self.ledger_rows()
        self.assertEqual([r["side"] for r in rows], ["buy", "sell"])
        for row, price in zip(rows, (101.0, 99.0)):
            self.assertAlmostEqual(row["fees_usd"], qty * price * 0.006)
            self.assertGreater(row["fees_usd"], 0.0)
            self.assertEqual(
                {k: row[k] for k in ("fee_currency", "fee_rate", "fee_type")},
                {"fee_currency": "USD", "fee_rate": 0.006, "fee_type": "taker"},
            )
            self.assertEqual(
                (row["fee_exchange"], row["fee_source"]), ("coinbase", "exchange")
            )
        # asked once, for the exchange whose quote priced the fills
        self.assertEqual(self.fees.asked, [("BTC", "coinbase")])

    def test_trade_history_shows_the_fee_not_na(self):
        """Even a $1 trade's fee (Kraken's 0.4%: $0.004) shows, not N/A or $0.00."""
        import pt_hub

        self.fees.taker = 0.004
        trader = self.trader(dict(self.SETTINGS))
        buy = trader.place_buy_order("id", "buy", "market", "BTC-USD", 1.0)
        trader.place_sell_order("id2", "sell", "market", "BTC-USD", buy["quantity"])
        view = types.SimpleNamespace(
            _money=pt_hub._fmt_money, _price=pt_hub._fmt_price, _pct=str
        )
        view._fee = lambda v: trade_history_view.TradeHistoryView._fee(view, v)
        fee_cell = trade_history_view.COLUMNS.index("fees")
        for row in self.ledger_rows():
            trade = trade_history_view.trade_of(row)
            self.assertAlmostEqual(trade.fees, row["fees_usd"])
            cell = trade_history_view.TradeHistoryView.cells(view, trade)[fee_cell]
            self.assertNotIn(cell, ("N/A", "$0.00"))
            self.assertTrue(cell.startswith("$0.00"), cell)  # e.g. $0.004

    def test_fees_are_in_the_cost_basis_and_the_realised_profit(self):
        trader = self.trader(dict(self.SETTINGS))
        buy = trader.place_buy_order("id", "buy", "market", "BTC-USD", 100.0)
        qty = buy["quantity"]
        cost = qty * 101.0 * 1.006
        self.assertAlmostEqual(trader.calculate_cost_basis()["BTC"], 101.0 * 1.006)
        position = trader._pnl_ledger["open_positions"]["BTC"]
        self.assertAlmostEqual(position["usd_cost"], cost)

        trader.place_sell_order("id2", "sell", "market", "BTC-USD", qty)
        proceeds = qty * 99.0 * 0.994
        realised = proceeds - cost
        sell = self.ledger_rows()[-1]
        self.assertAlmostEqual(sell["realized_profit_usd"], realised)
        self.assertAlmostEqual(
            trader._pnl_ledger["total_realized_profit_usd"], realised
        )
        with open(trader.pnl_ledger_path, encoding="utf-8") as f:
            saved = json.load(f)  # what the hub's Realized figure reads
        self.assertAlmostEqual(saved["total_realized_profit_usd"], realised)
        # the paper cash has paid both fees
        cash = tm.get_paper_exchange().get_balance()["USD"]
        self.assertAlmostEqual(cash, 10_000 + realised)

    def test_the_account_value_includes_the_fees(self):
        trader = self.trader(dict(self.SETTINGS))
        buy = trader.place_buy_order("id", "buy", "market", "BTC-USD", 100.0)
        qty = buy["quantity"]
        trader.manage_trades()
        with open(trader.trader_status_path, encoding="utf-8") as f:
            account = json.load(f)["account"]
        cash = 10_000 - qty * 101.0 * 1.006
        self.assertAlmostEqual(account["buying_power"], cash)
        self.assertAlmostEqual(account["total_account_value"], cash + qty * 99.0)

    def test_a_paper_run_charges_a_fee_on_every_trade(self):
        """Neural entry, then the trailing line's sell: each row has a fee."""
        trader = self.trader(dict(self.SETTINGS))
        self.signal(3)
        trader.manage_trades()  # the entry
        self.signal(0)
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
        trader.manage_trades()  # the sell
        rows = self.ledger_rows()
        self.assertEqual([r["side"] for r in rows], ["buy", "sell"])
        for row in rows:
            self.assertGreater(row["fees_usd"], 0.0)

    def test_the_entry_has_room_for_the_paper_fees(self):
        """The fee rates the trader sizes an entry with are those the fill pays."""
        trader = self.trader(dict(self.SETTINGS))
        self.markets.minimum = 1_000.0
        fees = trader._trading_fees("BTC-USD")
        self.assertEqual((fees.taker, fees.source), (0.006, "exchange"))
        amount, floor = trader._entry_size("BTC-USD", 10_000.0, 101.0, 99.0)
        self.assertAlmostEqual(amount, 1_000.0 * (1 + 2 / 99.0 + 0.012 + 0.02))
        self.assertEqual(amount, floor)


@pytest.mark.parametrize(
    "fees, rate, source",
    [
        (None, 0.012, "default"),
        (TradingFees(0, 0.002, "coinbase", "exchange"), 0.002, "exchange"),
    ],
)
def test_the_rate_a_fill_pays_is_what_its_order_records(fees, rate, source):
    pea._default_fees_warned.clear()
    ex = tm.PaperExchange(
        price_feed=lambda base: quote(exchange="coinbase"),
        fee_feed=lambda base, exchange: fees,
    )
    logging.disable(logging.WARNING)
    try:
        result = ex.place_order("ETH-USD", "buy", 1.0)
    finally:
        logging.disable(logging.NOTSET)
    order = ex.account.orders[result.order_id]
    assert float(order.commission_rate) == pytest.approx(rate)
    assert float(order.commission) == pytest.approx(101.0 * rate)
    assert (order.fee_type, order.fee_source) == ("taker", source)
