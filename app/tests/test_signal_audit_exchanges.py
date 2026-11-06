"""The coin ranking's market data, for every exchange (owner, 2026-11-06: no
single-exchange logic): each connector's ``spot_markets`` and ``daily_quote_volume``
read from answers shaped as the exchange sends them, kept byte for byte as evidence; and
the round's exchange chosen from Settings order (the primary first), passing over any
that cannot list markets, state quote volume or serve the round's history.

No request leaves the machine: ``requests.get`` is replaced.
"""

import json
import os
import sys

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_exchanges  # noqa: E402
from pt_exchange_abstraction import ExchangeManager, ExchangeType  # noqa: E402
from signal_audit import ranking  # noqa: E402

DAY = 86_400_000
D0 = 1_762_387_200_000  # 2025-11-06 00:00 UTC, ms


class Answer:
    def __init__(self, payload, status=200):
        self.status_code = status
        self.headers = {}
        self.content = json.dumps(payload).encode("utf-8")

    def json(self):
        return json.loads(self.content)


class Routes:
    def __init__(self, **routes):
        self.routes = routes
        self.calls = []

    def __call__(self, url, params=None, timeout=None):
        self.calls.append((url, dict(params or {})))
        for text, answer in self.routes.items():
            if text.replace("__", "/") in url:
                return Answer(answer(params or {}) if callable(answer) else answer)
        raise AssertionError(f"unexpected request {url}")


@pytest.fixture
def get(monkeypatch):
    def install(**routes):
        fake = Routes(**routes)
        monkeypatch.setattr(pt_exchanges.requests, "get", fake)
        return fake

    return install


def test_binance_lists_its_usdt_markets_and_states_field_7(get):
    info = {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "permissions": ["SPOT"],
            },
            {
                "symbol": "OLDUSDT",
                "status": "BREAK",
                "baseAsset": "OLD",
                "quoteAsset": "USDT",
                "permissionSets": [["SPOT", "LEVERAGED"]],
            },
            {
                "symbol": "ETHBTC",
                "status": "TRADING",
                "baseAsset": "ETH",
                "quoteAsset": "BTC",
            },
        ]
    }

    def kline(t, qv):
        return [
            t,
            "1",
            "2",
            "0.5",
            "1.5",
            "10",
            t + DAY - 1,
            str(qv),
            5,
            "4",
            "6",
            "0",
        ]

    fake = get(
        **{
            "api__v3__exchangeInfo": info,
            "api__v3__klines": [kline(D0, 1000.5), kline(D0 + DAY, 2000.25)],
        }
    )
    conn = pt_exchanges.BinanceExchange("", "")
    listing = conn.spot_markets()
    assert listing.exchange == "binance" and listing.quote == "USDT"
    assert [
        (m.pair, m.coin, m.status, m.trading, m.leveraged) for m in listing.markets
    ] == [
        ("BTCUSDT", "BTC", "TRADING", True, None),
        ("OLDUSDT", "OLD", "BREAK", False, True),
    ]
    assert listing.answers[0].body == json.dumps(info).encode("utf-8")
    dq = conn.daily_quote_volume("BTCUSDT", D0, D0 + DAY)
    assert dq.days == ((D0, 1000.5), (D0 + DAY, 2000.25))
    assert "field 7" in dq.measure and dq.answers[0].sha256
    assert fake.calls[-1][1]["interval"] == "1d"


def test_kucoin_states_turnover_and_sets_no_leveraged_mark(get):
    symbols = {
        "code": "200000",
        "data": [
            {
                "symbol": "BTC-USDT",
                "baseCurrency": "BTC",
                "quoteCurrency": "USDT",
                "enableTrading": True,
                "market": "USDS",
            },
            {
                "symbol": "BTC3L-USDT",
                "baseCurrency": "BTC3L",
                "quoteCurrency": "USDT",
                "enableTrading": True,
                "market": "ETF",
            },
            {
                "symbol": "ETH-BTC",
                "baseCurrency": "ETH",
                "quoteCurrency": "BTC",
                "enableTrading": True,
            },
        ],
    }
    candles = {
        "code": "200000",
        "data": [
            [str((D0 + DAY) // 1000), "1", "1.5", "2", "0.5", "10", "15.5"],
            [str(D0 // 1000), "1", "1.5", "2", "0.5", "10", "12.25"],
        ],
    }
    get(**{"api__v2__symbols": symbols, "api__v1__market__candles": candles})
    conn = pt_exchanges.KuCoinExchange("", "")
    listing = conn.spot_markets()
    # KuCoin marks no leveraged tokens: none is claimed (the ranking's ticker rule
    # applies to every exchange alike)
    assert [(m.pair, m.leveraged) for m in listing.markets] == [
        ("BTC-USDT", None),
        ("BTC3L-USDT", None),
    ]
    dq = conn.daily_quote_volume("BTC-USDT", D0, D0 + DAY)
    assert dq.days == ((D0, 12.25), (D0 + DAY, 15.5)) and "turnover" in dq.measure


def test_kraken_states_vwap_times_volume(get):
    pairs = {
        "error": [],
        "result": {
            "XXBTZUSD": {"altname": "XBTUSD", "wsname": "XBT/USD", "status": "online"},
            "XDGUSD": {
                "altname": "XDGUSD",
                "wsname": "XDG/USD",
                "status": "cancel_only",
            },
            "XETHXXBT": {"altname": "ETHXBT", "wsname": "ETH/XBT", "status": "online"},
        },
    }
    ohlc = {
        "error": [],
        "result": {
            "XXBTZUSD": [
                [D0 // 1000, "1", "2", "0.5", "1.5", "1.25", "100", 7],
            ],
            "last": 0,
        },
    }
    get(**{"AssetPairs": pairs, "OHLC": ohlc})
    conn = pt_exchanges.KrakenExchange("", "")
    listing = conn.spot_markets()
    assert [(m.pair, m.coin, m.trading) for m in listing.markets] == [
        ("XBTUSD", "BTC", True),
        ("XDGUSD", "DOGE", False),
    ]
    dq = conn.daily_quote_volume("XBTUSD", D0, D0)
    assert dq.days == ((D0, 125.0),) and "vwap x volume" in dq.measure


def test_coinbase_lists_its_usd_products_but_states_no_quote_volume(get):
    products = [
        {
            "id": "BTC-USD",
            "base_currency": "BTC",
            "quote_currency": "USD",
            "status": "online",
            "trading_disabled": False,
        },
        {
            "id": "OLD-USD",
            "base_currency": "OLD",
            "quote_currency": "USD",
            "status": "delisted",
            "trading_disabled": True,
        },
        {
            "id": "ETH-EUR",
            "base_currency": "ETH",
            "quote_currency": "EUR",
            "status": "online",
        },
    ]
    get(**{"products": products})
    conn = pt_exchanges.CoinbaseExchange("", "")
    listing = conn.spot_markets()
    assert [(m.pair, m.trading) for m in listing.markets] == [
        ("BTC-USD", True),
        ("OLD-USD", False),
    ]
    assert conn.daily_quote_volume("BTC-USD", D0, D0) is None


def _manager(*names):
    manager = ExchangeManager()
    for name in names:
        cls = {
            "coinbase": pt_exchanges.CoinbaseExchange,
            "kraken": pt_exchanges.KrakenExchange,
            "kucoin": pt_exchanges.KuCoinExchange,
            "binance": pt_exchanges.BinanceExchange,
        }[name]
        manager.exchanges[ExchangeType(name)] = cls("", "")
    return manager


def test_the_rounds_exchange_is_the_first_in_settings_that_can_serve_it():
    manager = _manager("coinbase", "kraken", "kucoin", "binance")
    need = {"1h": 24 * 300, "4h": 6 * 300}
    choice = ranking.choose_exchange(
        manager, ["coinbase", "kraken", "kucoin", "binance"], need
    )
    assert choice.exchange == "kucoin"
    answers = {c["exchange"]: c["answer"] for c in choice.considered}
    assert answers["coinbase"] == "states no daily quote volume"
    assert "serves its latest 720 bars" in answers["kraken"]
    assert answers["kucoin"] == "chosen" and "binance" not in answers
    # another order in Settings, another exchange: nothing is fixed to one
    assert (
        ranking.choose_exchange(manager, ["binance", "kucoin"], need).exchange
        == "binance"
    )
    # an exchange not connected is passed over and recorded
    gone = ranking.choose_exchange(_manager("binance"), ["kucoin", "binance"], need)
    assert gone.exchange == "binance"
    assert gone.considered[0] == {"exchange": "kucoin", "answer": "not connected"}
    # Kraken serves a short round (its 720 bars cover it)
    assert (
        ranking.choose_exchange(manager, ["kraken"], {"1h": 700, "4h": 100}).exchange
        == "kraken"
    )
    # none can: no exchange chosen, every answer recorded
    none = ranking.choose_exchange(_manager("coinbase"), ["coinbase"], need)
    assert (
        none.exchange is None
        and none.considered[0]["answer"] == "states no daily quote volume"
    )


def test_no_audit_module_names_an_exchange():
    """The audit's logic is the same for every exchange: none of its modules names one
    (the connectors do)."""
    import re

    names = re.compile(r"binance|coinbase|kraken|kucoin|robinhood", re.IGNORECASE)
    folder = os.path.join(APP_DIR, "signal_audit")
    for name in os.listdir(folder):
        if name.endswith(".py"):
            text = open(os.path.join(folder, name), encoding="utf-8").read()
            assert not names.search(text), name
