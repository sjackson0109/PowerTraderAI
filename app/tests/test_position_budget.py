"""How big a trade is (owner, 2026-10-24): an entry is Start allocation % of the account
(default 1%, was 0.005%), raised to the exchange's minimum order (the fixed $0.50 floor
is gone); a coin may use at most Max per coin % of the account (default 10%), and a DCA
buy that would pass that budget is skipped.

Everything runs under the isolation guard (app/conftest.py); no network.
"""

import json
import os
import sys
import types
from decimal import Decimal
from unittest import mock

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import position_sizing as ps  # noqa: E402
import pt_paths  # noqa: E402
import trading_mode as tm  # noqa: E402
from helpers import PaperTraderCase  # noqa: E402

# --- the rules -------------------------------------------------------------------------


def test_the_new_defaults():
    assert (ps.DEFAULT_START_ALLOCATION_PCT, ps.DEFAULT_MAX_COIN_ALLOCATION_PCT) == (
        1.0,
        10.0,
    )


@pytest.mark.parametrize(
    "account, pct, minimum, entry",
    [
        (10_000, 1.0, None, 100.0),
        (50, 1.0, None, 0.50),  # no fixed floor any more
        (50, 1.0, 5.0, 5.0),  # raised to the exchange minimum
        (10_000, 1.0, 5.0, 100.0),  # already above it
        (10_000, 0.0, None, 0.0),
    ],
)
def test_an_entry_is_start_allocation_raised_to_the_exchange_minimum(
    account, pct, minimum, entry
):
    assert ps.entry_usd(account, pct, minimum) == pytest.approx(entry)


def test_a_dca_buy_must_keep_the_coin_within_its_budget():
    # $10,000 at 10%: $1,000 per coin
    assert ps.dca_fits_budget(295, 560, 10_000, 10.0)  # $855
    assert ps.dca_fits_budget(400, 600, 10_000, 10.0)  # exactly $1,000
    assert not ps.dca_fits_budget(855, 1_710, 10_000, 10.0)  # $2,565


def test_the_account_panel_counts_dca_levels_within_the_budget():
    """1% entry, x2 DCA (each one triples the cost): 1% -> 3% -> 9%; a third (27%)
    would pass the 10% budget."""
    assert ps.dca_levels_affordable(10_000, 1.0, 10.0, 2.0, coins=1) == 2
    assert ps.dca_levels_affordable(10_000, 1.0, 10.0, 2.0, coins=8) == 2
    # with no budget to speak of, the account is the limit: 8 coins at 1% -> 8%, 24%, 72%
    assert ps.dca_levels_affordable(10_000, 1.0, 100.0, 2.0, coins=8) == 2
    assert ps.dca_levels_affordable(10_000, 1.0, 10.0, 0.0) == 0  # DCA buys nothing


@pytest.mark.parametrize(
    "saved, migrated",
    [
        ({"start_allocation_pct": 0.005}, 1.0),  # upstream's default: replaced
        ({"start_allocation_pct": 2.5}, 2.5),  # the user's choice: kept
        ({}, None),  # nothing saved: the default applies
    ],
)
def test_upstreams_saved_default_is_replaced_once(saved, migrated):
    assert ps.migrate_settings(saved)
    assert saved.get("start_allocation_pct") == migrated
    assert saved[ps.DEFAULTS_VERSION_KEY] == ps.DEFAULTS_VERSION
    # once the file carries the version, a 0.005% saved later is a choice
    saved["start_allocation_pct"] = 0.005
    assert not ps.migrate_settings(saved)
    assert saved["start_allocation_pct"] == 0.005


# --- the exchange minimum ---------------------------------------------------------------


class _Response:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_the_paper_book_reads_binances_public_minimum_order(monkeypatch):
    urls = []

    def opener(url, timeout=None):
        urls.append(url)
        return _Response(
            {
                "symbols": [
                    {
                        "filters": [
                            {"filterType": "LOT_SIZE", "minQty": "0.00001"},
                            {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
                        ]
                    }
                ]
            }
        )

    monkeypatch.setattr(tm, "_min_notional_cache", {})
    monkeypatch.setattr(tm.urllib.request, "urlopen", opener)
    assert tm.fetch_public_min_notional("ETH") == 5.0
    assert tm.fetch_public_min_notional("ETH") == 5.0  # kept for the process
    assert urls == ["https://api.binance.com/api/v3/exchangeInfo?symbol=ETHUSDT"]
    book = tm.PaperExchange(
        price_feed=tm.fetch_public_quote,
        minimum_feed=tm._minimum_feed_for(tm.fetch_public_quote),
    )
    assert book.min_order_usd("ETH-USD") == 5.0


def test_an_unreadable_minimum_is_no_minimum_and_is_tried_again(monkeypatch):
    calls = []

    def opener(url, timeout=None):
        calls.append(url)
        raise OSError("offline")

    monkeypatch.setattr(tm, "_min_notional_cache", {})
    monkeypatch.setattr(tm.urllib.request, "urlopen", opener)
    assert tm.fetch_public_min_notional("BTC") is None
    assert tm.fetch_public_min_notional("BTC") is None
    assert len(calls) == 2
    # a book on any other price feed (a test's) asks no one
    assert (
        tm.PaperExchange(price_feed=lambda base: None).min_order_usd("BTC-USD") is None
    )


def test_binance_live_reads_its_symbol_filter():
    from pt_exchanges import BinanceExchange

    exchange = BinanceExchange.__new__(BinanceExchange)  # no credentials needed here
    exchange._convert_symbol = lambda symbol: "BTCUSDT"
    exchange._get_symbol_filters = lambda symbol: {"minNotional": Decimal("5")}
    assert exchange.min_order_usd("BTC-USD") == 5.0
    exchange._get_symbol_filters = lambda symbol: {"minNotional": Decimal("0")}
    assert exchange.min_order_usd("BTC-USD") is None
    exchange._get_symbol_filters = mock.Mock(side_effect=ConnectionError("offline"))
    assert exchange.min_order_usd("BTC-USD") is None


# --- the hub: the saved 0.005% is replaced once ---------------------------------------


def test_the_hub_replaces_upstreams_saved_default_once():
    import pt_hub

    path = pt_paths.gui_settings_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"coins": ["BTC"], "start_allocation_pct": 0.005}, f)
    settings = pt_hub.PowerTraderHub._load_settings(types.SimpleNamespace())
    assert settings["start_allocation_pct"] == 1.0
    assert settings["max_coin_allocation_pct"] == 10.0
    with open(path, encoding="utf-8") as f:
        saved = json.load(f)  # written back, so the trader reads it too
    assert saved["start_allocation_pct"] == 1.0
    assert saved[ps.DEFAULTS_VERSION_KEY] == ps.DEFAULTS_VERSION
    # a 0.005% the user saves later is kept
    saved["start_allocation_pct"] = 0.005
    with open(path, "w", encoding="utf-8") as f:
        json.dump(saved, f)
    settings = pt_hub.PowerTraderHub._load_settings(types.SimpleNamespace())
    assert settings["start_allocation_pct"] == 0.005


def test_the_trader_accepts_allocations_above_one_percent():
    """The validator capped start_allocation_pct at 1.0, and the trader ignores the
    whole settings file when a value is out of range."""
    from pt_validation import InputValidator

    checked = InputValidator.validate_config_data(
        {"start_allocation_pct": 2.5, "max_coin_allocation_pct": 20.0}
    )
    assert checked == {"start_allocation_pct": 2.5, "max_coin_allocation_pct": 20.0}


# --- the trader -------------------------------------------------------------------------


class TraderSizing(PaperTraderCase):
    """A legacy-mode paper trader on a $10,000 book, with a fake Binance at ~100."""

    SETTINGS = {"trading": {"mode": "paper"}, "strategy": {"engine": "legacy_neural"}}

    def setUp(self):
        super().setUp()
        sleep = mock.patch.object(self.pt_trader.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        self.folder = os.path.join(self.tmp.name, "neural")
        os.makedirs(self.folder)
        for p in (
            mock.patch.object(self.pt_trader, "base_paths", {"BTC": self.folder}),
            mock.patch.object(self.pt_trader, "main_dir", self.folder),
        ):
            p.start()
            self.addCleanup(p.stop)
        self.binance.bid, self.binance.ask = 99.95, 100.05

    def long_signal(self):
        for name, value in (
            ("long_dca_signal.txt", "7"),
            ("short_dca_signal.txt", "0"),
        ):
            with open(os.path.join(self.folder, name), "w") as f:
                f.write(value)

    def entry_usd(self):
        (order,) = tm.get_paper_exchange().account.orders.values()
        return float(order.filled_quantity * order.filled_price)

    def test_an_entry_is_one_percent_of_the_account(self):
        trader = self.trader(dict(self.SETTINGS))
        self.long_signal()
        trader.manage_trades()
        assert self.entry_usd() == pytest.approx(100.0, rel=0.01)  # was $0.50

    def test_an_entry_below_the_exchange_minimum_is_raised_to_it(self):
        self.binance.min_notional = 250.0  # Binance's NOTIONAL filter for BTCUSDT
        trader = self.trader(dict(self.SETTINGS))
        self.long_signal()
        trader.manage_trades()
        assert self.entry_usd() == pytest.approx(250.0, rel=0.01)
        assert any("exchangeInfo?symbol=BTCUSDT" in url for url in self.binance.urls)

    def test_only_a_positive_finite_number_is_an_exchange_minimum(self):
        trader = self.trader(dict(self.SETTINGS))
        exchange = trader._target.exchange
        for answer, minimum in (
            (5, 5.0),
            (2.5, 2.5),
            (None, None),
            (0, None),
            (-1, None),
            (float("nan"), None),
            (float("inf"), None),
            (True, None),
            ("5", None),
            (mock.Mock(), None),
        ):
            with mock.patch.object(exchange, "min_order_usd", return_value=answer):
                assert trader._minimum_order_usd("BTC-USD") == minimum, answer
        with mock.patch.object(exchange, "min_order_usd", side_effect=OSError):
            assert trader._minimum_order_usd("BTC-USD") is None

    def test_a_small_account_trades_at_the_exchange_minimum(self):
        """1% of $50 is $0.50, under Binance's $5 minimum: the entry is $5. The old
        risk gate refused any order over 1% of the account, so it refused this one."""
        book = os.path.join(self.tmp.name, "paper", "paper_account.json")
        os.makedirs(os.path.dirname(book), exist_ok=True)
        with open(book, "w", encoding="utf-8") as f:  # the trader loads this book
            json.dump(
                {"initial_balance": "50", "cash_balance": "50", "positions": {}}, f
            )
        trader = self.trader(dict(self.SETTINGS))
        self.long_signal()
        trader.manage_trades()
        assert self.entry_usd() == pytest.approx(5.0, rel=0.01)

    def test_a_position_worth_more_than_one_percent_can_be_sold(self):
        """The old risk gate capped sells at 1% of the account too: a 1% entry that
        gained anything could not be sold."""
        trader = self.trader(dict(self.SETTINGS))
        trader.place_buy_order("id", "buy", "market", "BTC-USD", 300.0, tag="ENTRY")
        qty = tm.get_paper_exchange().get_balance()["BTC"]
        trader.place_sell_order("id", "sell", "market", "BTC-USD", qty, tag="EXIT")
        assert "BTC" not in tm.get_paper_exchange().get_balance()

    def test_a_buy_past_the_coins_budget_is_refused_by_the_risk_gate(self):
        trader = self.trader(dict(self.SETTINGS))
        with mock.patch("builtins.print") as printed:
            trader.place_buy_order("id", "buy", "market", "BTC-USD", 1_500.0)
        assert tm.get_paper_exchange().account.orders == {}
        said = " ".join(str(c) for c in printed.call_args_list)
        assert "at most $1,000.00 per buy" in said

    def held_and_down(self):
        """Holding $50 of BTC bought at ~100, now quoted ~90: past the -2.5%, -5% and
        -10% DCA levels; the next DCA buy is about $90 (twice the position's value)."""
        trader = self.trader(dict(self.SETTINGS))
        trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0, tag="ENTRY")
        trader.cost_basis = trader.calculate_cost_basis()  # as its next pass would
        self.binance.bid, self.binance.ask = 89.95, 90.05
        tm._quote_cache.clear()
        return trader

    def dca_rows(self):
        return [r for r in self.ledger_rows() if r.get("tag") == "DCA"]

    def test_a_dca_buy_within_the_coins_budget_is_placed(self):
        trader = self.held_and_down()
        trader.manage_trades()  # $50 + ~$90 is well within $1,000 (10%)
        assert len(self.dca_rows()) == 1

    def test_a_dca_buy_past_the_coins_budget_is_skipped_and_says_why(self):
        trader = self.held_and_down()
        with mock.patch.object(self.pt_trader, "MAX_COIN_PCT", 1.0), mock.patch(
            "builtins.print"
        ) as printed:
            trader.manage_trades()  # budget $100: $50 + ~$90 would pass it
        assert self.dca_rows() == []
        said = [str(c) for c in printed.call_args_list if "past its budget" in str(c)]
        assert said and "Max per coin 1%" in said[0]
