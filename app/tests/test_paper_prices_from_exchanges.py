"""Paper trading prices from the exchanges in Settings, primary first (FDS-MX-001
phase B), and a paper book with no size limit of its own (decision D7).

Everything runs under the isolation guard (app/conftest.py); no network.
"""

import os
import sys
from unittest import mock

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_multi_exchange  # noqa: E402

# the real one: the isolation guard replaces it in every test
REAL_MARKET_EXCHANGES = pt_multi_exchange.market_exchanges
import trading_mode as tm  # noqa: E402
from helpers import PaperTraderCase  # noqa: E402


def test_the_market_data_connection_writes_no_settings(monkeypatch):
    """Reading prices never creates the user's exchange settings: with no
    trading_config.json, the region's defaults are used in memory."""
    monkeypatch.setattr(pt_multi_exchange, "_shared", None)
    monkeypatch.setattr(pt_multi_exchange, "market_exchanges", REAL_MARKET_EXCHANGES)
    monkeypatch.delenv("POWERTRADER_USER_REGION", raising=False)
    with mock.patch.object(pt_multi_exchange.ExchangeManager, "add_exchange") as add:
        add.return_value = True
        manager = pt_multi_exchange.market_exchanges()
    assert not os.path.exists(manager.config_manager.config_file)
    assert manager.config_manager.config.user_region == "GLOBAL"
    assert add.called  # the region's default exchanges were connected
    assert pt_multi_exchange.market_exchanges() is manager  # connected once


class PaperFills(PaperTraderCase):
    def test_a_fill_records_the_exchange_whose_quote_priced_it(self):
        self.quotes.exchange = "kraken"
        result = tm.get_paper_exchange().place_order("BTC-USD", "buy", 0.5)
        assert (result.status, result.price_source) == ("filled", "live")
        assert result.price_exchange == "kraken"
        assert result.price == pytest.approx(101.0)

    def test_the_paper_book_sets_no_size_limit_of_its_own(self):
        """A buy worth a quarter of the $10,000 book fills; the book used to refuse
        anything over 10%. One worth more than the cash is still refused."""
        book = tm.get_paper_exchange()
        quarter = book.place_order("BTC-USD", "buy", 25.0)  # 25 x $101
        assert quarter.status == "filled"
        too_much = book.place_order("BTC-USD", "buy", 1_000.0)
        assert too_much.status == "rejected"

    def test_without_a_quote_the_paper_book_pauses(self):
        self.quotes.reachable = False
        result = tm.get_paper_exchange().place_order("BTC-USD", "buy", 0.5)
        assert (result.status, result.reason) == ("rejected", tm.PRICE_UNAVAILABLE)
