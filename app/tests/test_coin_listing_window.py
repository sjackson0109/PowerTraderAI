"""A coin listed after the training window starts trains on the bars it has, run
after run; a coin whose market stopped trading gets no training, no signals and no
buys.

The first case is HYPE's: its candle cache starts at its listing, so every later run
asked Binance for the months before it, got an empty page, and crashed comparing an
untyped empty frame with a timestamp.

Everything runs under the isolation guard (app/conftest.py); no network: candles,
exchange information and quotes all come from fakes.
"""

import json
import os
import sys
import time
import urllib.error
from datetime import datetime, timedelta, timezone
from unittest import mock

import pandas as pd
import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import helpers_candles as hc  # noqa: E402
import pt_data_provider  # noqa: E402
import pt_pattern_trainer as ppt  # noqa: E402
import trading_mode as tm  # noqa: E402
from helpers import PaperTraderCase  # noqa: E402
from market_data import candles, listing, runner_history  # noqa: E402
from market_data.candles import CandleDataError  # noqa: E402
from pt_exchange_abstraction import MarketNotFound, Sourced  # noqa: E402

EPOCH = pd.Timestamp("1970-01-01", tz="UTC")
LISTED = datetime(2024, 3, 4, tzinfo=timezone.utc)  # a Monday


def binance_rows(frame, start_ms, end_ms):
    """Klines rows for the bars of ``frame`` opening in [start_ms, end_ms], the way
    the public endpoint answers: an empty list for a range with no bars."""
    ms = (frame["open_time"] - EPOCH) // pd.Timedelta(milliseconds=1)
    keep = ms >= start_ms
    if end_ms is not None:
        keep &= ms <= end_ms
    rows = frame[keep]
    return [
        [int(t), o, h, lo, c, v]
        for t, o, h, lo, c, v in zip(
            ms[keep],
            rows["open"].tolist(),
            rows["high"].tolist(),
            rows["low"].tolist(),
            rows["close"].tolist(),
            rows["volume"].tolist(),
        )
    ]


class Exchange:
    """Stands in for candles.BinanceKlines over ``{pair: {tf: frame}}``."""

    def __init__(self, frames_by_pair):
        self.frames = frames_by_pair
        self.calls = []
        self.requests_made = 0

    def fetch(self, symbol, tf, start_ms, end_ms=None):
        self.requests_made += 1
        self.calls.append((symbol, tf, start_ms, end_ms))
        frame = self.frames.get(symbol, {}).get(tf)
        return [] if frame is None else binance_rows(frame, start_ms, end_ms)


def status_is(code):
    return lambda pair: listing.PairStatus(pair, code, "" if code else "test: unknown")


# --- the candle cache: an empty page is a page with no bars, not a crash -------------


def test_a_range_before_the_listing_is_an_empty_page_not_a_crash(tmp_path):
    hourly = hc.synthetic_hourly(400, LISTED, seed=2)
    fake = Exchange({"NEWUSDT": {"1h": hourly}})
    start, end = LISTED - timedelta(days=60), LISTED + timedelta(hours=400)

    first = candles.get_candles(
        "NEWUSDT", "1h", start, end, cache_dir=str(tmp_path), fetcher=fake
    )
    # the cache now starts at the listing: the next call asks for the months before it
    second = candles.get_candles(
        "NEWUSDT", "1h", start, end, cache_dir=str(tmp_path), fetcher=fake
    )

    assert fake.calls[-1][2] == (pd.Timestamp(start) - EPOCH) // pd.Timedelta(
        milliseconds=1
    )
    assert (
        binance_rows(hourly, fake.calls[-1][2], fake.calls[-1][3]) == []
    )  # empty page
    pd.testing.assert_frame_equal(first, second)
    assert len(second) == 400 and second["open_time"].iloc[0] == pd.Timestamp(LISTED)


def test_a_range_after_the_last_bar_is_an_empty_page_not_a_crash(tmp_path):
    hourly = hc.synthetic_hourly(300, LISTED, seed=4)  # the pair stopped after 300 h
    fake = Exchange({"GONEUSDT": {"1h": hourly}})
    end = LISTED + timedelta(hours=500)

    first = candles.get_candles(
        "GONEUSDT", "1h", LISTED, end, cache_dir=str(tmp_path), fetcher=fake
    )
    second = candles.get_candles(
        "GONEUSDT", "1h", LISTED, end, cache_dir=str(tmp_path), fetcher=fake
    )

    pd.testing.assert_frame_equal(first, second)
    assert len(second) == 300


def test_an_empty_page_has_a_timestamp_column():
    empty = candles._frame_from_klines([])
    assert str(empty["open_time"].dtype) == "datetime64[ns, UTC]"
    assert candles._closed_only(empty, "1h", pd.Timestamp.now(tz="UTC")).empty


# --- the trainer: a late listing trains again; a market that stopped is refused -----


def load_all(loader):
    for choice in ppt.TF_CHOICES:
        loader.bars(choice)
    return loader.reports


def test_a_pair_listed_late_trains_again_from_its_cache(tmp_path, monkeypatch):
    """HYPE's crash: the second online run over a cache that starts at the listing."""
    start = LISTED - timedelta(weeks=4)
    end = LISTED + timedelta(weeks=8)
    hourly = hc.synthetic_hourly(8 * 168, LISTED, seed=3)
    fake = Exchange({"NEWUSDT": hc.all_timeframes(hourly)})
    monkeypatch.setattr(candles, "BinanceKlines", lambda *a, **k: fake)

    first = load_all(
        ppt.BarLoader("NEWUSDT", start, end, False, cache_dir=str(tmp_path))
    )
    second = load_all(
        ppt.BarLoader("NEWUSDT", start, end, False, cache_dir=str(tmp_path))
    )

    assert first == second
    for tf, report in second.items():
        assert report["missing_at_start"] > 0 and report["missing_at_end"] == 0, tf
        assert pd.Timestamp(report["first_open"]) == pd.Timestamp(LISTED), tf


def live_window():
    """A training window ending at the last whole hour, as the hub's default run."""
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    return end - timedelta(weeks=6), end


def test_a_live_run_whose_bars_stop_early_is_refused(tmp_path, monkeypatch):
    start, end = live_window()
    hourly = hc.synthetic_hourly(6 * 168 - 72, start, seed=5)  # stops 3 days early
    fake = Exchange({"GONEUSDT": hc.all_timeframes(hourly)})
    monkeypatch.setattr(candles, "BinanceKlines", lambda *a, **k: fake)

    closed = ppt.BarLoader(
        "GONEUSDT",
        start,
        end,
        False,
        cache_dir=str(tmp_path),
        status_of=status_is("BREAK"),
    )
    with pytest.raises(
        ppt.MarketClosedError, match="GONEUSDT is BREAK, not trading"
    ) as e:
        closed.bars("1hour")
    assert e.value.confirmed and "no longer trades" in str(e.value)

    # Binance says it trades, or cannot be asked: refused, but not "no longer trades"
    for code, said in ((listing.TRADING, "trading"), (None, "status unknown")):
        loader = ppt.BarLoader(
            "GONEUSDT",
            start,
            end,
            False,
            cache_dir=str(tmp_path),
            status_of=status_is(code),
        )
        with pytest.raises(
            ppt.MarketClosedError, match=f"no 1h bars after .*{said}"
        ) as e:
            loader.bars("1hour")
        assert not e.value.confirmed and "Try again later" in str(e.value)


def test_a_pair_binance_does_not_list_is_refused_cleanly(tmp_path, monkeypatch):
    class Unknown:
        requests_made = 0

        def fetch(self, symbol, tf, start_ms, end_ms=None):
            error = candles.CandleFetchError(f"klines HTTP 400 for {symbol} {tf}")
            error.__cause__ = urllib.error.HTTPError("u", 400, "Bad Request", {}, None)
            raise error

    monkeypatch.setattr(candles, "BinanceKlines", lambda *a, **k: Unknown())
    loader = ppt.BarLoader(
        "NOPEUSDT", LISTED, LISTED + timedelta(weeks=2), False, cache_dir=str(tmp_path)
    )
    with pytest.raises(ppt.MarketClosedError, match="no spot market NOPEUSDT") as e:
        loader.bars("1hour")
    assert e.value.confirmed


def test_a_live_run_missing_only_the_last_bar_or_two_is_not_refused(
    tmp_path, monkeypatch
):
    start, end = live_window()
    hourly = hc.synthetic_hourly(6 * 168 - 2, start, seed=6)
    monkeypatch.setattr(
        candles, "BinanceKlines", lambda *a, **k: Exchange({"LATEUSDT": {"1h": hourly}})
    )
    asked = []
    loader = ppt.BarLoader(
        "LATEUSDT", start, end, False, cache_dir=str(tmp_path), status_of=asked.append
    )
    loader.bars("1hour")
    assert loader.reports["1h"]["missing_at_end"] == 2 and asked == []


def test_an_older_window_with_a_short_tail_is_reported_not_refused(
    tmp_path, monkeypatch
):
    hourly = hc.synthetic_hourly(300, LISTED, seed=7)
    monkeypatch.setattr(
        candles, "BinanceKlines", lambda *a, **k: Exchange({"OLDUSDT": {"1h": hourly}})
    )
    loader = ppt.BarLoader(
        "OLDUSDT", LISTED, LISTED + timedelta(hours=400), False, cache_dir=str(tmp_path)
    )
    loader.bars("1hour")
    assert loader.reports["1h"]["missing_at_end"] == 100


def run_main(
    monkeypatch, folder, train, start="2024-01-01T00:00:00Z", end="2024-03-01T00:00:00Z"
):
    os.makedirs(folder, exist_ok=True)
    monkeypatch.chdir(folder)
    monkeypatch.setattr(ppt, "train", train)
    return ppt.main(["GONE", "--train-start", start, "--train-end", end])


def test_a_confirmed_closure_is_refused_and_recorded(tmp_path, monkeypatch, capsys):
    def closed(coin, *a, **k):
        raise ppt.MarketClosedError(
            "GONEUSDT", "Binance spot GONEUSDT is BREAK, not trading"
        )

    folder = tmp_path / "GONE"
    assert run_main(monkeypatch, folder, closed) == 1

    out = capsys.readouterr().out
    assert "training refused for GONE" in out and "Traceback" not in out
    assert (
        listing.not_trading_reason(str(folder))
        == "Binance spot GONEUSDT is BREAK, not trading"
    )
    with open(folder / "trainer_status.json", encoding="utf-8") as f:
        assert json.load(f)["state"] == "ERROR"


def test_an_unconfirmed_closure_is_refused_but_not_recorded(tmp_path, monkeypatch):
    def stopped(coin, *a, **k):
        raise ppt.MarketClosedError(
            "GONEUSDT", "no bars (Binance: trading)", confirmed=False
        )

    folder = tmp_path / "GONE"
    assert run_main(monkeypatch, folder, stopped) == 1
    assert listing.read_market_status(str(folder)) is None


def test_a_live_run_that_finishes_records_its_market_trading(tmp_path, monkeypatch):
    """A successful live run clears a "not trading" record from an earlier refusal."""
    folder = tmp_path / "GONE"
    listing.write_market_status(
        str(folder), "GONEUSDT", False, "an earlier refused run"
    )
    monkeypatch.setattr(ppt, "provenance", lambda *a, **k: "model-1")
    end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    iso = "%Y-%m-%dT%H:%M:%SZ"
    code = run_main(
        monkeypatch,
        folder,
        lambda *a, **k: {"timeframes": {}},
        start=(end - timedelta(weeks=4)).strftime(iso),
        end=end.strftime(iso),
    )
    assert code == 0
    assert listing.read_market_status(str(folder))["trading"] is True


# --- the exchange-information check -------------------------------------------------


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class Opener:
    def __init__(self, answer):
        self.answer, self.urls = answer, []

    def __call__(self, url, timeout=None):
        self.urls.append(url)
        if isinstance(self.answer, Exception):
            raise self.answer
        return FakeResponse(self.answer)


def info(pair, status):
    return {"symbols": [{"symbol": pair, "status": status}]}


def test_the_status_of_a_pair_comes_from_exchange_information():
    trading = listing.ListingChecker(opener=Opener(info("BTCUSDT", "TRADING")))
    assert trading.status("BTC-USDT").trading is True
    halted = listing.ListingChecker(opener=Opener(info("HYPEUSDT", "BREAK"))).status(
        "HYPEUSDT"
    )
    assert halted.trading is False
    assert halted.describe() == "Binance spot HYPEUSDT is BREAK, not trading"

    invalid = urllib.error.HTTPError("u", 400, "Bad Request", {}, None)
    gone = listing.ListingChecker(opener=Opener(invalid)).status("OLDUSDT")
    assert (gone.status, gone.trading) == (listing.NOT_LISTED, False)
    assert gone.describe() == "Binance has no spot market OLDUSDT"


def test_an_unreachable_endpoint_gives_no_verdict_and_is_asked_again_soon():
    clock = [1000.0]
    opener = Opener(urllib.error.URLError("offline"))
    checker = listing.ListingChecker(
        opener=opener, clock=lambda: clock[0], retry_ttl=300
    )
    assert checker.status("BTCUSDT").trading is None
    clock[0] += 100
    checker.status("BTCUSDT")
    assert len(opener.urls) == 1  # cached briefly
    clock[0] += 300
    checker.status("BTCUSDT")
    assert len(opener.urls) == 2


def test_a_known_status_is_kept_for_an_hour():
    clock = [0.0]
    opener = Opener(info("BTCUSDT", "TRADING"))
    checker = listing.ListingChecker(opener=opener, clock=lambda: clock[0], ttl=3600)
    checker.status("BTCUSDT")
    clock[0] += 3599
    checker.status("BTCUSDT")
    assert len(opener.urls) == 1
    clock[0] += 2
    checker.status("BTCUSDT")
    assert len(opener.urls) == 2


def test_the_market_verdict_file_round_trips(tmp_path):
    assert listing.not_trading_reason(str(tmp_path)) is None  # no file: no verdict
    listing.write_market_status(str(tmp_path), "hypeusdt", False, "delisted")
    assert listing.not_trading_reason(str(tmp_path)) == "delisted"
    listing.write_market_status(str(tmp_path), "HYPEUSDT", True, "bars arrive")
    assert listing.not_trading_reason(str(tmp_path)) is None
    (tmp_path / listing.MARKET_STATUS_FILE).write_text("not json", encoding="utf-8")
    assert listing.not_trading_reason(str(tmp_path)) is None


# --- the runner: bars that stopped arriving from a closed market --------------------

HOUR = 3600
NOW = 1_760_000_000 + 1800  # half way through an hour bar


def kline(open_s, close):
    return [open_s * 1000, str(close), str(close), str(close), str(close), "1", 0, "1"]


class Klines:
    """The exchange layer's candles: fixed bars, served by "fake"."""

    def __init__(self, rows):
        self.rows = rows

    def __call__(self, symbol, tf, start_ms, end_ms, now_ms):
        bars = [r for r in self.rows if start_ms <= r[0] <= end_ms]
        return Sourced(bars, "fake", symbol, primary=True)


def test_bars_that_stopped_from_a_closed_market_are_a_missing_market():
    forming = NOW - NOW % HOUR
    stale = [kline(forming - 3 * HOUR, 5.0)]  # nothing for the last two hours
    candles_ = runner_history.RecentCandles(
        source=Klines(stale), clock=lambda: NOW, listing=status_is("BREAK")
    )
    with pytest.raises(MarketNotFound, match="HYPEUSDT is BREAK, not trading"):
        candles_.history_text("HYPE", "1hour")

    gone = runner_history.RecentCandles(
        source=Klines([]), clock=lambda: NOW, listing=status_is(listing.NOT_LISTED)
    )
    with pytest.raises(MarketNotFound, match="no spot market HYPEUSDT"):
        gone.history_text("HYPE", "1hour")


def test_bars_that_stopped_while_binance_says_trading_or_cannot_say_are_waited_for():
    """No verdict means no signals from stale bars either: wait for the bar."""
    forming = NOW - NOW % HOUR
    stale = [kline(forming - 4 * HOUR, 5.0), kline(forming - 3 * HOUR, 5.5)]
    for status in (status_is(listing.TRADING), status_is(None)):
        stopped = runner_history.RecentCandles(
            source=Klines(stale), clock=lambda: NOW, listing=status
        )
        with pytest.raises(
            CandleDataError, match="no 1h candle for BTC-USD on fake since"
        ):
            stopped.history_text("BTC", "1hour")


def test_a_gap_in_a_trading_market_is_only_waiting_for_data():
    asked = []

    def trading(pair):
        asked.append(pair)
        return listing.PairStatus(pair, listing.TRADING)

    empty = runner_history.RecentCandles(
        source=Klines([]), clock=lambda: NOW, listing=trading
    )
    with pytest.raises(CandleDataError):
        empty.history_text("BTC", "1hour")
    assert asked == ["BTCUSDT"]

    forming = NOW - NOW % HOUR
    fresh = [kline(forming - 2 * HOUR, 5.0), kline(forming - HOUR, 6.0)]
    ok = runner_history.RecentCandles(
        source=Klines(fresh), clock=lambda: NOW, listing=trading
    )
    assert json.loads(ok.history_text("BTC", "1hour"))[1][2] == 6.0
    assert asked == ["BTCUSDT"]  # the last closed bar is there: nothing to ask


class TextProvider:
    def __init__(self, text=None, error=None):
        self.text, self.error = text, error

    def is_available(self):
        return True

    def get_provider_info(self):
        return "fake"

    def get_historical_data(self, coin, tf, **kwargs):
        if self.error:
            raise self.error
        return self.text


@pytest.fixture
def runner():
    cwd = os.getcwd()
    sys.modules.pop("pt_thinker", None)
    with mock.patch.object(
        pt_data_provider, "get_data_provider", return_value=TextProvider()
    ):
        import pt_thinker
    yield pt_thinker
    os.chdir(cwd)
    sys.modules.pop("pt_thinker", None)


def test_the_runner_records_a_closed_market_and_a_trading_one(runner, monkeypatch):
    runner._mark_unavailable("HYPE", "Binance spot HYPEUSDT is BREAK, not trading")
    folder = runner.coin_folder("HYPE")
    assert (
        listing.not_trading_reason(folder)
        == "Binance spot HYPEUSDT is BREAK, not trading"
    )

    forming = NOW - NOW % HOUR
    text = json.dumps([kline(forming, 6.0)[:6], kline(forming - HOUR, 5.0)[:6]])
    monkeypatch.setattr(runner, "data_provider", TextProvider(text))
    runner._history_rows("ETH-USDT", "1hour")
    assert listing.read_market_status(runner.coin_folder("ETH"))["trading"] is True


def bars_text():
    forming = NOW - NOW % HOUR
    return json.dumps([kline(forming, 6.0)[:6], kline(forming - HOUR, 5.0)[:6]])


def test_bars_arriving_clear_a_not_trading_record_another_process_wrote(
    runner, monkeypatch
):
    """The runner compares the file, not a memory of its own last write: a refused
    training run's "not trading" is corrected once the runner receives the bars."""
    monkeypatch.setattr(runner, "data_provider", TextProvider(bars_text()))
    runner._history_rows("ETH-USDT", "1hour")  # recorded trading
    folder = runner.coin_folder("ETH")
    listing.write_market_status(folder, "ETHUSDT", False, "a refused training run")
    runner._history_rows("ETH-USDT", "1hour")
    assert listing.read_market_status(folder)["trading"] is True


def test_a_verdict_write_the_trader_blocked_is_written_on_the_next_call(
    runner, monkeypatch
):
    real_replace = os.replace
    held = {"count": 0}

    def busy(src, dst):  # Windows: the trader has the file open
        if dst.endswith(listing.MARKET_STATUS_FILE) and held["count"] < 5:
            held["count"] += 1
            raise PermissionError("in use")
        return real_replace(src, dst)

    monkeypatch.setattr(listing.time, "sleep", lambda s: None)
    monkeypatch.setattr(listing.os, "replace", busy)
    runner._mark_unavailable("HYPE", "Binance spot HYPEUSDT is BREAK, not trading")
    folder = runner.coin_folder("HYPE")
    assert listing.read_market_status(folder) is None  # five tries, all blocked
    assert not os.path.exists(
        os.path.join(folder, listing.MARKET_STATUS_FILE + ".writing")
    )
    runner._mark_unavailable("HYPE", "Binance spot HYPEUSDT is BREAK, not trading")
    assert (
        listing.not_trading_reason(folder)
        == "Binance spot HYPEUSDT is BREAK, not trading"
    )


def test_a_skipped_coin_is_checked_again_after_an_hour(runner, monkeypatch):
    clock = [1_000_000.0]
    monkeypatch.setattr(runner.time, "time", lambda: clock[0])
    verdict = {"code": "BREAK"}
    monkeypatch.setattr(
        listing, "pair_status", lambda pair: listing.PairStatus(pair, verdict["code"])
    )
    runner._mark_unavailable("HYPE", "Binance spot HYPEUSDT is BREAK, not trading")

    clock[0] += 60
    assert runner._recheck_unavailable("HYPE") is False  # not yet an hour
    clock[0] += runner.UNAVAILABLE_RECHECK_SECONDS
    assert runner._recheck_unavailable("HYPE") is False  # still closed
    assert "HYPE" in runner.UNAVAILABLE_COINS
    verdict["code"] = listing.TRADING
    clock[0] += runner.UNAVAILABLE_RECHECK_SECONDS
    assert runner._recheck_unavailable("HYPE") is True
    assert "HYPE" not in runner.UNAVAILABLE_COINS


def test_an_untrained_coin_whose_market_closed_is_skipped(runner, monkeypatch):
    """No bars are fetched for an untrained coin, so Binance is asked directly: a
    held coin must not keep getting DCA buys after a delisting."""
    monkeypatch.setattr(
        listing, "pair_status", lambda pair: listing.PairStatus(pair, "BREAK")
    )
    os.makedirs(runner.coin_folder("SOL"), exist_ok=True)
    with pytest.raises(runner.CoinUnavailable, match="SOLUSDT is BREAK"):
        runner.step_coin("SOL")


def test_tests_never_ask_binance_for_a_market_status():
    """The isolation guard answers the shared check with "unknown"."""
    status = listing.pair_status("BTCUSDT")
    assert status.trading is None and "tests" in status.detail


# --- the trader: no buys in a coin whose market is not trading ----------------------


class NoBuysInAClosedMarket(PaperTraderCase):
    SETTINGS = {"trading": {"mode": "paper"}, "strategy": {"engine": "legacy_neural"}}

    def setUp(self):
        super().setUp()
        sleep = mock.patch.object(self.pt_trader.time, "sleep")
        sleep.start()
        self.addCleanup(sleep.stop)
        self.folder = os.path.join(self.tmp.name, "neural")
        os.makedirs(self.folder)
        patches = (
            mock.patch.object(self.pt_trader, "base_paths", {"BTC": self.folder}),
            mock.patch.object(self.pt_trader, "main_dir", self.folder),
        )
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def held_and_down(self):
        """A trader holding BTC bought at ~100, now quoted ~90 (past every DCA level
        up to -10%)."""
        trader = self.trader(dict(self.SETTINGS))
        self.quotes.bid, self.quotes.ask = 99.95, 100.05
        trader.place_buy_order("id", "buy", "market", "BTC-USD", 50.0, tag="ENTRY")
        trader.cost_basis = trader.calculate_cost_basis()  # as its next pass would
        self.quotes.bid, self.quotes.ask = 89.95, 90.05
        tm._quote_cache.clear()
        return trader

    def dca_rows(self):
        return [r for r in self.ledger_rows() if r.get("tag") == "DCA"]

    def test_a_held_coin_gets_a_dca_buy_while_its_market_trades(self):
        trader = self.held_and_down()
        trader.manage_trades()
        self.assertEqual(len(self.dca_rows()), 1)

    def test_a_held_coin_whose_market_closed_gets_no_dca_buy(self):
        trader = self.held_and_down()
        listing.write_market_status(
            self.folder, "BTCUSDT", False, "Binance spot BTCUSDT is BREAK, not trading"
        )
        with mock.patch("builtins.print") as printed:
            trader.manage_trades()
            trader.manage_trades()
        self.assertEqual(self.dca_rows(), [])
        said = [str(c) for c in printed.call_args_list if "No buys in BTC" in str(c)]
        self.assertEqual(len(said), 1)  # said once, not every pass

    def long_signal(self):
        for name, value in (
            ("long_dca_signal.txt", "7"),
            ("short_dca_signal.txt", "0"),
        ):
            with open(os.path.join(self.folder, name), "w") as f:
                f.write(value)

    def test_a_coin_with_a_long_signal_gets_an_entry_while_its_market_trades(self):
        trader = self.trader(dict(self.SETTINGS))
        self.long_signal()
        trader.manage_trades()
        self.assertEqual(len(tm.get_paper_exchange().account.orders), 1)

    def test_a_strategy_entry_is_not_even_considered_in_a_closed_market(self):
        """Catalogue mode: the guard comes before the strategy is asked."""
        listing.write_market_status(self.folder, "BTCUSDT", False, "delisted")
        trader = self.trader({"trading": {"mode": "paper"}})
        with mock.patch.object(
            trader.signal_engine, "decide", return_value=None
        ) as decide:
            trader.manage_trades()
        self.assertNotIn(mock.call("BTC", None), decide.call_args_list)
        self.assertEqual(tm.get_paper_exchange().account.orders, {})

    def test_a_strategy_entry_is_considered_while_the_market_trades(self):
        trader = self.trader({"trading": {"mode": "paper"}})
        with mock.patch.object(
            trader.signal_engine, "decide", return_value=None
        ) as decide:
            trader.manage_trades()
        self.assertIn(mock.call("BTC", None), decide.call_args_list)

    def test_a_held_coin_can_still_be_sold_when_its_market_closed(self):
        trader = self.held_and_down()
        listing.write_market_status(self.folder, "BTCUSDT", False, "delisted")
        qty = tm.get_paper_exchange().get_balance()["BTC"]
        trader.place_sell_order("id", "sell", "market", "BTC-USD", qty, tag="EXIT")
        self.assertNotIn("BTC", tm.get_paper_exchange().get_balance())

    def test_a_coin_whose_market_closed_gets_no_entry(self):
        listing.write_market_status(self.folder, "BTCUSDT", False, "delisted")
        trader = self.trader(dict(self.SETTINGS))
        self.long_signal()
        trader.manage_trades()
        self.assertEqual(tm.get_paper_exchange().account.orders, {})
        self.assertEqual(self.ledger_rows(), [])
