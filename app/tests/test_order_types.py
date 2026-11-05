"""Order Management's order types, carried out (order_management_execution; owner,
2026-11-05).

* Paper: each type (Market, Limit, Stop-Limit, Trailing Stop, OCO, Bracket) fills
  the paper account (the saved book) when its price is reached, paying the fees
  ``trading_fees()`` gives, and its fill is in the trade history with its fee.
* An OCO or Bracket order is cancelled with all its legs; one leg filling cancels
  the other.
* Nothing is created or carried out while trading is halted (Settings > Risk).
* The orders PowerTrader manages are kept in the database: a new executor (the app
  started again) carries on with them.
* Live: a kind the broker's connector places as its own order goes to the exchange
  and is followed there; any other is managed, and a market order is placed when
  its price is reached.

A temporary order database and hub folder, under the isolation guard; prices and
fees come from stubs, and no request leaves the machine.
"""

import json
import os
import sys
import time
from decimal import Decimal
from types import SimpleNamespace

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

pytest.importorskip("sqlalchemy")

import order_management_execution as ome  # noqa: E402
import trading_mode as tm  # noqa: E402
from pt_exchange_abstraction import OrderResult, TradingFees  # noqa: E402

FEES = TradingFees(maker=0.004, taker=0.006, exchange="coinbase", source="exchange")


class Prices:
    """The market: one bid and ask per coin, read by the monitor's quote and the
    paper account's price feed alike."""

    def __init__(self, **coins):
        self.coins = {c: tuple(v) for c, v in coins.items()}

    def set(self, coin, bid, ask):
        self.coins[coin] = (bid, ask)

    def feed(self, base):
        if base not in self.coins:
            return None
        bid, ask = self.coins[base]
        now = time.time()
        return tm.Quote(bid, ask, now, now, exchange="coinbase", pair=f"{base}-USD")

    def quote(self, settings, coin):
        if coin not in self.coins:
            return None
        bid, ask = self.coins[coin]
        return ome.Quote(bid, ask, "coinbase")


@pytest.fixture
def db(tmp_path):
    from order_management_db import OrderManagementDB

    d = OrderManagementDB(f"sqlite:///{tmp_path / 'orders.db'}")
    yield d
    d.close()


def paper_settings():
    return tm.TradingSettings(tm.TradingMode.PAPER, None, True)


class World:
    """A hub folder, the market, the trading settings, a halt and an executor."""

    def __init__(self, db, tmp_path, prices, settings=None, live=None, cash="10000"):
        self.db = db
        self.hub = str(tmp_path / "hub")
        self.prices = prices
        self.settings = settings or paper_settings()
        self.halted = ""
        self.live = live
        self.book = tm.paper_book_path(self.hub)
        if cash is not None:
            tm.write_paper_book(
                self.book,
                tm.PaperBook(
                    Decimal("10000"),
                    Decimal(cash),
                    {"ETH": (Decimal("5"), Decimal("3000"))},
                ),
            )
        self.executor = self.make()

    def paper(self, path):
        return tm.PaperExchange(
            state_path=path,
            price_feed=self.prices.feed,
            fee_feed=lambda base, exchange: FEES,
            settings_source={},
        )

    def make(self):
        return ome.OrderExecutor(
            self.db,
            hub_dir=self.hub,
            trading=lambda: self.settings,
            paper=self.paper,
            live=(lambda s: self.live) if self.live is not None else None,
            quote=self.prices.quote,
            halt=lambda folder: self.halted,
            atr=lambda coin, exchange: 100.0,
        )

    def place(self, kind, coin="BTC", side="buy", qty="0.1", **fields):
        """Create and send an order, as the dialog does; prices as numbers."""
        for key, value in fields.items():
            if key not in ("trail_mode", "atr") and value is not None:
                fields[key] = Decimal(str(value))
        spec = ome.OrderSpec(
            kind=kind,
            coin=coin,
            side=side,
            quantity=Decimal(qty),
            exchange="coinbase",
            pair=f"{coin}-USD",
            **fields,
        )
        order_id = self.executor.create(spec)
        self.executor.submit(order_id)
        return order_id

    def item(self, order_id):
        return self.executor.item(order_id)

    def book_now(self):
        return tm.read_paper_book(self.book)

    def history(self):
        path = os.path.join(self.hub, "paper", "trade_history.jsonl")
        if not os.path.exists(path):
            return []
        with open(path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]


@pytest.fixture
def world(db, tmp_path):
    return World(db, tmp_path, Prices(BTC=(60000.0, 60010.0), ETH=(3000.0, 3001.0)))


def statuses(item):
    return {leg.role: leg.status for leg in item.legs}


# ---- each type fills the paper account and the trade history ----


def test_a_market_buy_fills_at_the_ask_with_the_taker_fee(world):
    oid = world.place(ome.MARKET, qty="0.1")
    assert world.item(oid).status == "filled"
    book = world.book_now()
    fee = 0.1 * 60010.0 * 0.006
    assert float(book.cash_balance) == pytest.approx(10000 - 6001.0 - fee)
    assert book.positions["BTC"][0] == Decimal("0.1")
    (row,) = world.history()
    assert (row["side"], row["tag"], row["symbol"], row["qty"]) == (
        "buy",
        "MANUAL",
        "BTC-USD",
        0.1,
    )
    assert row["price"] == 60010.0
    assert row["fees_usd"] == pytest.approx(fee)
    assert (row["fee_type"], row["fee_rate"], row["fee_exchange"]) == (
        "taker",
        0.006,
        "coinbase",
    )
    assert row["price_source"] == "live" and row["order_management_id"] == oid


def test_a_limit_buy_waits_then_fills_at_its_price_with_the_maker_fee(world):
    oid = world.place(ome.LIMIT, qty="0.1", price=59000)
    assert world.item(oid).status == "submitted"
    assert world.history() == []
    world.prices.set("BTC", 58800.0, 58900.0)  # the ask fell through the limit
    world.executor.check()
    assert world.item(oid).status == "filled"
    (row,) = world.history()
    assert row["price"] == 59000.0  # its own price, not the ask
    assert row["fee_type"] == "maker" and row["fees_usd"] == pytest.approx(
        0.1 * 59000 * 0.004
    )
    assert float(world.book_now().cash_balance) == pytest.approx(
        10000 - 5900 - 5900 * 0.004
    )


def test_a_limit_the_market_has_reached_fills_at_once_at_the_market(world):
    oid = world.place(ome.LIMIT, qty="0.1", price=61000)  # above the ask
    assert world.item(oid).status == "filled"
    (row,) = world.history()
    assert row["price"] == 60010.0 and row["fee_type"] == "taker"


def test_a_stop_limit_sell_works_its_limit_once_the_stop_is_reached(world):
    oid = world.place(
        ome.STOP_LIMIT, coin="ETH", side="sell", qty="1", stop_price=2900, price=2850
    )
    item = world.item(oid)
    assert (item.status, item.state) == ("submitted", "working")
    world.prices.set("ETH", 2800.0, 2801.0)  # gaps through the stop and the limit
    world.executor.check()
    item = world.item(oid)
    assert (item.status, item.state) == ("submitted", "triggered")
    assert "Stop reached" in item.note
    world.prices.set("ETH", 2860.0, 2861.0)  # back up to the limit
    world.executor.check()
    assert world.item(oid).status == "filled"
    (row,) = world.history()
    assert (row["side"], row["price"], row["fee_type"]) == ("sell", 2850.0, "maker")
    assert world.book_now().positions["ETH"][0] == Decimal("4")
    # the paper book's cost of ETH was 3,000: the loss and the fee
    assert row["realized_profit_usd"] == pytest.approx((2850 - 3000) - 2850 * 0.004)
    assert row["closes_position"] is False  # 4 ETH are still held


def test_a_trailing_stop_follows_the_best_bid_and_sells_at_the_market(world):
    oid = world.place(
        ome.TRAILING_STOP,
        coin="ETH",
        side="sell",
        qty="5",
        trail_mode=ome.PERCENT,
        trail_value=2,
    )
    item = world.item(oid)
    assert item.best_price == 3000.0 and item.stop == pytest.approx(2940.0)
    world.prices.set("ETH", 3200.0, 3201.0)
    world.executor.check()
    item = world.item(oid)
    assert item.best_price == 3200.0 and item.stop == pytest.approx(3136.0)
    world.prices.set("ETH", 3150.0, 3151.0)  # above the stop: it waits
    world.executor.check()
    assert world.item(oid).status == "submitted"
    world.prices.set("ETH", 3130.0, 3131.0)
    world.executor.check()
    assert world.item(oid).status == "filled"
    (row,) = world.history()
    assert (row["price"], row["fee_type"], row["closes_position"]) == (
        3130.0,
        "taker",
        True,
    )
    assert "ETH" not in world.book_now().positions


def test_a_trailing_stop_in_atr_multiples(world):
    oid = world.place(
        ome.TRAILING_STOP,
        coin="ETH",
        side="sell",
        qty="1",
        trail_mode=ome.ATR,
        trail_value=1.5,
        atr=100.0,
    )
    item = world.item(oid)
    assert item.stop == pytest.approx(3000.0 - 150.0)  # 1.5 x ATR 100
    world.prices.set("ETH", 2849.0, 2850.0)
    world.executor.check()
    assert world.item(oid).status == "filled"


def test_an_oco_sell_fills_one_side_and_cancels_the_other(world):
    oid = world.place(
        ome.OCO, coin="ETH", side="sell", qty="2", take_profit=3300, stop_price=2800
    )
    group = world.item(oid)
    assert group.order_type == "oco" and statuses(group) == {
        "take_profit": "submitted",
        "stop": "submitted",
    }
    world.prices.set("ETH", 3310.0, 3311.0)
    world.executor.check()
    group = world.item(oid)
    assert group.status == "filled"
    assert statuses(group) == {"take_profit": "filled", "stop": "cancelled"}
    (row,) = world.history()
    assert (row["price"], row["fee_type"]) == (3300.0, "maker")
    world.prices.set("ETH", 2700.0, 2701.0)  # the stop is gone: nothing more
    world.executor.check()
    assert len(world.history()) == 1


def test_a_bracket_buys_then_its_stop_sells_and_its_take_profit_is_cancelled(world):
    oid = world.place(
        ome.BRACKET,
        coin="BTC",
        side="buy",
        qty="0.05",
        take_profit=63000,
        stop_price=58000,
    )
    group = world.item(oid)
    assert statuses(group) == {
        "entry": "filled",
        "take_profit": "submitted",
        "stop": "submitted",
    }
    assert world.book_now().positions["BTC"][0] == Decimal("0.05")
    world.prices.set("BTC", 57900.0, 57910.0)
    world.executor.check()
    group = world.item(oid)
    assert group.status == "filled"
    assert statuses(group) == {
        "entry": "filled",
        "take_profit": "cancelled",
        "stop": "filled",
    }
    buy, sell = world.history()
    assert (buy["side"], sell["side"], sell["price"]) == ("buy", "sell", 57900.0)
    assert "BTC" not in world.book_now().positions


def test_a_bracket_with_a_limit_entry_waits_for_it(world):
    oid = world.place(
        ome.BRACKET,
        side="buy",
        qty="0.05",
        price=59000,
        take_profit=62000,
        stop_price=58000,
    )
    group = world.item(oid)
    assert group.leg("entry").status == "submitted"
    assert group.leg("take_profit").state == "waiting"
    world.prices.set("BTC", 57000.0, 57010.0)  # below the stop too: the entry first
    world.executor.check()
    group = world.item(oid)
    assert group.leg("entry").status == "filled"
    assert group.leg("stop").status in ("submitted", "filled")


def test_a_buy_the_paper_cash_cannot_cover_is_rejected_with_the_reason(
    world, db, tmp_path
):
    poor = World(db, tmp_path / "poor", world.prices, cash="100")
    oid = poor.place(ome.MARKET, qty="0.1")
    item = poor.item(oid)
    assert item.status == "rejected" and "less than" in item.note
    assert poor.history() == []


def test_a_market_order_with_no_price_is_rejected_not_kept(world):
    oid = world.place(ome.MARKET, coin="SOL", qty="1")
    item = world.item(oid)
    assert item.status == "rejected" and "not kept for later" in item.note
    world.prices.set("SOL", 150.0, 150.1)
    world.executor.check()
    assert world.item(oid).status == "rejected" and world.history() == []


def test_a_stop_with_no_live_price_waits_for_one(world):
    oid = world.place(
        ome.OCO, coin="ETH", side="sell", qty="1", take_profit=3300, stop_price=2800
    )
    del world.prices.coins["ETH"]
    world.executor.check()
    group = world.item(oid)
    assert group.status == "submitted" and "No price for ETH" in group.note
    world.prices.set("ETH", 2790.0, 2791.0)
    world.executor.check()
    assert world.item(oid).status == "filled"


def test_an_unreadable_paper_book_is_never_overwritten(world):
    with open(world.book, "w", encoding="utf-8") as f:
        f.write("{not json")
    oid = world.place(ome.MARKET, qty="0.1")
    assert world.item(oid).status != "filled"
    assert "Paper Account" in world.item(oid).note
    with open(world.book, encoding="utf-8") as f:
        assert f.read() == "{not json"


# ---- cancelling ----


@pytest.mark.parametrize("which", ["group", "take_profit", "stop"])
def test_cancelling_an_oco_or_any_of_its_legs_cancels_them_all(world, which):
    oid = world.place(
        ome.OCO, coin="ETH", side="sell", qty="1", take_profit=3300, stop_price=2800
    )
    group = world.item(oid)
    target = group.id if which == "group" else group.leg(which).id
    assert world.executor.cancel(target) == (True, "")
    group = world.item(oid)
    assert group.status == "cancelled"
    assert set(statuses(group).values()) == {"cancelled"}
    world.prices.set("ETH", 3400.0, 3401.0)
    world.executor.check()
    assert world.history() == []


def test_cancelling_a_bracket_cancels_its_waiting_exits(world):
    oid = world.place(
        ome.BRACKET,
        side="buy",
        qty="0.05",
        price=59000,
        take_profit=62000,
        stop_price=58000,
    )
    assert world.executor.cancel(oid) == (True, "")
    group = world.item(oid)
    assert group.status == "cancelled" and set(statuses(group).values()) == {
        "cancelled"
    }


# ---- a halt stops trading ----


def test_no_order_is_created_while_trading_is_halted(world):
    world.halted = "Account drawdown 25%"
    with pytest.raises(ValueError, match="Trading is halted.*drawdown 25%"):
        world.place(ome.MARKET, qty="0.1")


def test_an_open_order_waits_while_trading_is_halted(world):
    oid = world.place(ome.LIMIT, qty="0.1", price=59000)
    world.halted = "Emergency stop"
    world.prices.set("BTC", 58000.0, 58010.0)
    world.executor.check()
    item = world.item(oid)
    assert item.status == "submitted" and "halted" in item.note
    world.halted = ""
    world.executor.check()
    assert world.item(oid).status == "filled"


# ---- a restart carries on ----


def test_a_new_executor_carries_on_with_the_saved_orders(world):
    oid = world.place(
        ome.TRAILING_STOP,
        coin="ETH",
        side="sell",
        qty="1",
        trail_mode=ome.PERCENT,
        trail_value=5,
    )
    world.prices.set("ETH", 3500.0, 3501.0)
    world.executor.check()
    again = world.make()  # the app started again
    item = again.item(oid)
    assert item.best_price == 3500.0 and item.stop == pytest.approx(3325.0)
    world.prices.set("ETH", 3300.0, 3301.0)
    again.check()
    assert again.item(oid).status == "filled"


def test_an_order_not_sent_before_the_app_stopped_is_not_sent_later(world, db):
    from datetime import datetime, timedelta

    from order_management_models import ManagedOrder

    spec = ome.OrderSpec(
        kind=ome.MARKET, coin="BTC", side="buy", quantity=Decimal("0.1")
    )
    oid = world.executor.create(spec)  # never submitted
    with db.get_session() as s:
        m = s.query(ManagedOrder).one()
        m.updated_at = datetime.utcnow() - timedelta(hours=3)
    world.make().check()
    item = world.item(oid)
    assert item.status == "expired" and "Not sent" in item.note
    assert world.history() == []


def test_orders_of_another_account_are_left_alone(world):
    oid = world.place(ome.LIMIT, qty="0.1", price=59000)
    world.settings = tm.TradingSettings(tm.TradingMode.LIVE, "coinbase", False, False)
    world.prices.set("BTC", 58000.0, 58010.0)
    world.executor.check()
    assert world.item(oid).status == "submitted"


# ---- modify ----


def test_modify_changes_a_managed_orders_prices(world):
    oid = world.place(
        ome.OCO, coin="ETH", side="sell", qty="1", take_profit=3300, stop_price=2800
    )
    assert (
        world.executor.modify(oid, take_profit=Decimal("3400"), quantity=Decimal("2"))
        == ""
    )
    group = world.item(oid)
    assert group.leg("take_profit").price == 3400.0
    assert {leg.quantity for leg in group.legs} == {2.0}
    world.prices.set("ETH", 3350.0, 3351.0)  # the old take-profit: nothing
    world.executor.check()
    assert world.item(oid).status == "submitted"


def test_modify_refuses_a_stop_the_market_has_passed(world):
    oid = world.place(
        ome.STOP_LIMIT, coin="ETH", side="sell", qty="1", stop_price=2900, price=2850
    )
    problem = world.executor.modify(oid, stop_price=Decimal("3100"))
    assert "below the bid" in problem
    assert world.item(oid).stop == 2900.0


# ---- live: the exchange's own orders, or managed ----


class FakeBroker:
    """A live connector that holds limit, stop-limit and OCO orders, but no
    trailing stops: every request is recorded, nothing is sent."""

    def __init__(self, kinds=("limit", "stop_limit", "oco")):
        self.kinds = frozenset(kinds)
        self.calls = []
        self.status = {}
        self.n = 0

    def native_order_kinds(self):
        return self.kinds

    def supports_native_order(self, request):
        return request.kind in self.kinds

    def place_native_order(self, request):
        self.calls.append(("native", request))
        self.n += 1
        legs = {}
        if request.kind == "oco":
            legs = {"take_profit": f"L{self.n}a", "stop": f"L{self.n}b"}
        oid = f"N{self.n}"
        self.status[oid] = "new"
        for leg in legs.values():
            self.status[leg] = "new"
        return OrderResult(
            oid, request.symbol, request.side, 0.0, 0.0, "new", "fake", 0, legs=legs
        )

    def native_order_status(self, order_id):
        state = self.status[order_id]
        filled = state == "filled"
        return OrderResult(
            order_id,
            "BTC-USD",
            "buy",
            0.1 if filled else 0.0,
            60000.0 if filled else 0.0,
            state,
            "fake",
            0,
            fee=3.6 if filled else None,
        )

    def cancel_native_order(self, order_id):
        self.calls.append(("cancel", order_id))
        self.status[order_id] = "canceled"
        return True

    def quote(self, symbol):
        return None

    def trading_fees(self, symbol):
        return FEES


class FakeTarget:
    def __init__(self, broker):
        self.exchange = broker
        self.key = "live:coinbase"
        self.preview = False
        self.orders = []

    def place_order(self, symbol, side, amount, price=None, *, client_order_id=None):
        self.orders.append((symbol, side, amount, client_order_id))
        oid = f"M{len(self.orders)}"
        self.exchange.status[oid] = "filled"
        return OrderResult(oid, symbol, side, 0.0, 0.0, "pending", "fake", 0)


@pytest.fixture
def live_world(db, tmp_path):
    broker = FakeBroker()
    w = World(
        db,
        tmp_path,
        Prices(BTC=(60000.0, 60010.0)),
        settings=tm.TradingSettings(tm.TradingMode.LIVE, "coinbase", False, False),
        live=FakeTarget(broker),
        cash=None,
    )
    w.executor._connectors["coinbase"] = broker
    return w


def test_a_live_limit_is_placed_on_the_exchange_and_followed_there(live_world):
    w = live_world
    oid = w.place(ome.LIMIT, qty="0.1", price=59000)
    ((kind, request),) = w.live.exchange.calls
    assert (request.kind, request.side, request.price, request.amount) == (
        "limit",
        "buy",
        59000.0,
        0.1,
    )
    item = w.item(oid)
    assert (item.handling, item.exchange_order_id, item.status) == (
        "exchange",
        "N1",
        "submitted",
    )
    w.live.exchange.status["N1"] = "filled"
    w.executor.check()
    assert w.item(oid).status == "filled"
    (row,) = [
        json.loads(line)
        for line in open(os.path.join(w.hub, "live", "coinbase", "trade_history.jsonl"))
    ]
    assert (row["tag"], row["price"], row["fees_usd"], row["order_id"]) == (
        "MANUAL",
        60000.0,
        3.6,
        "N1",
    )


def test_a_live_trailing_stop_the_exchange_lacks_is_managed(live_world):
    w = live_world
    w.prices.set("BTC", 60000.0, 60010.0)
    oid = w.place(
        ome.TRAILING_STOP, side="sell", qty="0.1", trail_mode=ome.PERCENT, trail_value=1
    )
    assert w.item(oid).handling == "powertrader" and w.live.exchange.calls == []
    w.prices.set("BTC", 59300.0, 59310.0)  # 1% under the best bid
    w.executor.check()
    assert w.live.orders == [
        ("BTC-USD", "sell", 0.1, w.item(oid).client_id[:30] + "-m")
    ]
    w.executor.check()  # the market order is followed until it fills
    assert w.item(oid).status == "filled"


def test_a_live_oco_is_one_exchange_order_and_cancels_as_one(live_world):
    w = live_world
    oid = w.place(ome.OCO, side="sell", qty="0.1", take_profit=62000, stop_price=58000)
    ((kind, request),) = w.live.exchange.calls
    assert (request.kind, request.price, request.stop_price) == (
        "oco",
        62000.0,
        58000.0,
    )
    group = w.item(oid)
    assert group.exchange_order_id == "N1"
    assert {l.role: l.exchange_order_id for l in group.legs} == {
        "take_profit": "L1a",
        "stop": "L1b",
    }
    assert w.executor.cancel(oid) == (True, "")
    assert w.live.exchange.calls[-1] == ("cancel", "N1")  # the list, once
    assert set(statuses(w.item(oid)).values()) == {"cancelled"}


def test_a_live_oco_leg_filling_on_the_exchange_fills_the_group(live_world):
    w = live_world
    oid = w.place(ome.OCO, side="sell", qty="0.1", take_profit=62000, stop_price=58000)
    w.live.exchange.status["L1b"] = "filled"
    w.live.exchange.status["L1a"] = "expired"
    w.executor.check()
    group = w.item(oid)
    assert group.status == "filled"
    assert statuses(group) == {"take_profit": "cancelled", "stop": "filled"}


def test_preview_mode_places_nothing(live_world):
    w = live_world
    w.settings = tm.TradingSettings(tm.TradingMode.LIVE, "coinbase", False, True)
    with pytest.raises(ValueError, match="preview"):
        w.place(ome.LIMIT, qty="0.1", price=59000)


def test_the_dialog_says_how_each_type_is_carried_out():
    broker = FakeBroker()
    spec = lambda kind, **kw: ome.OrderSpec(
        kind=kind, coin="BTC", side="sell", quantity=Decimal("1"), **kw
    )
    assert ome.handling_text(spec(ome.MARKET), False, None, "") == (
        "Fills at once in the paper account, at the market."
    )
    for kind in (ome.LIMIT, ome.STOP_LIMIT, ome.TRAILING_STOP, ome.OCO, ome.BRACKET):
        assert ome.MANAGED_TEXT in ome.handling_text(spec(kind), False, None, "")
    assert ome.handling_text(spec(ome.LIMIT), True, broker, "Coinbase") == (
        "Placed on Coinbase as its own order."
    )
    trail = spec(ome.TRAILING_STOP, trail_mode=ome.PERCENT, trail_value=Decimal("2"))
    assert ome.handling_text(trail, True, broker, "Coinbase") == (
        f"On Coinbase: {ome.MANAGED_TEXT}."
    )
    assert ome.MANAGED_TEXT in ome.handling_text(
        spec(ome.BRACKET), True, broker, "Coinbase"
    )
