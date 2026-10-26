"""The neural runner gets real recent candles, cannot stall on one coin, writes its
signal counts where the trader and the hub read them, and says TRAINING while a
coin trains. The trader ignores signal files the runner has stopped updating.

Everything runs under the isolation guard (app/conftest.py); no network: the
exchange layer's candles and quotes are fakes.
"""

import json
import os
import sys
import time
import types
from unittest import mock

import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import pt_data_provider  # noqa: E402
import pt_hub  # noqa: E402
import pt_multi_exchange  # noqa: E402
from market_data import runner_history  # noqa: E402

# the real one: the isolation guard replaces it in every test
REAL_MARKET_EXCHANGES = pt_multi_exchange.market_exchanges
from pt_exchange_abstraction import MarketNotFound, PriceQuote, Sourced  # noqa: E402

HOUR = 3600
NOW = 1_760_000_000 + 1800  # half way through an hour bar


def kline(open_s, o, h, lo, c):
    """One bar as the exchange layer gives it: [open ms, o, h, l, c, volume]."""
    return [open_s * 1000, float(o), float(h), float(lo), float(c), 1.5]


class FakeSource:
    """The exchange layer's candles (``market_exchanges().candles``): the closed
    bars in the range asked for, as served by ``exchange``."""

    def __init__(self, rows=None, error=None, exchange="coinbase"):
        self.rows, self.error, self.exchange, self.calls = (
            rows or [],
            error,
            exchange,
            [],
        )

    def __call__(self, symbol, tf, start_ms, end_ms, now_ms):
        self.calls.append((symbol, tf, start_ms, end_ms, now_ms))
        if self.error:
            raise self.error
        bars = [r for r in self.rows if start_ms <= r[0] <= end_ms]
        return Sourced(bars, self.exchange, symbol, primary=True)


def hour_rows():
    forming = NOW - NOW % HOUR
    return [
        kline(forming - 2 * HOUR, 100, 103, 99, 102),
        kline(forming - HOUR, 102, 106, 101, 105),
    ]


def test_recent_candles_are_newest_first_in_the_runners_row_order():
    fake = FakeSource(hour_rows())
    candles = runner_history.RecentCandles(source=fake, clock=lambda: NOW)
    rows = json.loads(candles.history_text("BTC-USDT", "1hour"))
    forming = NOW - NOW % HOUR
    # [time_s, open, close, high, low, volume, turnover]; row 0 stands for the
    # forming bar: flat at the last close
    assert rows[0] == [forming, 105.0, 105.0, 105.0, 105.0, 0.0, 0.0]
    assert rows[1] == [forming - HOUR, 102.0, 105.0, 106.0, 101.0, 1.5, 0.0]
    assert rows[2][0] == forming - 2 * HOUR
    start, end = (forming - 3 * HOUR) * 1000, (forming - HOUR) * 1000
    assert fake.calls == [("BTC-USD", "1h", start, end, NOW * 1000)]
    assert candles.last_source[("BTC-USD", "1h")] == "coinbase"


def test_recent_candles_are_reused_for_a_short_while():
    fake = FakeSource(hour_rows())
    clock = [NOW]
    candles = runner_history.RecentCandles(source=fake, ttl=30, clock=lambda: clock[0])
    first = candles.history_text("BTC", "1hour")
    clock[0] += 10
    assert candles.history_text("BTCUSDT", "1h") == first
    assert len(fake.calls) == 1
    clock[0] += 30
    candles.history_text("BTC", "1hour")
    assert len(fake.calls) == 2


def test_weekly_bars_open_on_monday():
    fake = FakeSource([])
    candles = runner_history.RecentCandles(
        source=fake, clock=lambda: NOW, listing=lambda pair: None  # no network
    )
    with pytest.raises(Exception):
        candles.history_text("ETH", "1week")  # no closed bar in the fake
    symbol, tf, start_ms, _, _ = fake.calls[0]
    assert (symbol, tf) == ("ETH-USD", "1w")
    assert time.gmtime(start_ms // 1000).tm_wday == 0  # Monday 00:00 UTC
    assert start_ms // 1000 % 86400 == 0


def test_a_coin_no_exchange_lists_is_a_missing_market():
    gone = MarketNotFound("No exchange has a market for HYPE-USD")
    candles = runner_history.RecentCandles(
        source=FakeSource(error=gone), clock=lambda: NOW
    )
    with pytest.raises(MarketNotFound, match="No exchange has a market for HYPE-USD"):
        candles.history_text("HYPE-USDT", "1hour")


def test_the_data_provider_serves_history_from_the_exchange_layer(monkeypatch):
    provider = pt_data_provider.DataProvider.__new__(pt_data_provider.DataProvider)
    provider.initialized = False  # its own connection is not needed
    provider.multi_exchange = None
    shared = runner_history.RecentCandles(
        source=FakeSource(hour_rows()), clock=lambda: NOW
    )
    monkeypatch.setattr(runner_history, "_shared", shared)
    rows = json.loads(provider.get_historical_data("BTC-USDT", "1hour"))
    assert len(rows) == 3 and rows[1][2] == 105.0


# --- the runner -------------------------------------------------------------------


class TextProvider:
    """A data provider answering with fixed history text (or raising)."""

    def __init__(self, text=None, error=None):
        self.text, self.error, self.calls = text, error, 0

    def is_available(self):
        return True

    def get_provider_info(self):
        return "fake"

    def get_historical_data(self, coin, tf, **kwargs):
        self.calls += 1
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


def history_text():
    return runner_history.RecentCandles(
        source=FakeSource(hour_rows()), clock=lambda: NOW
    ).history_text("BTC", "1hour")


def test_the_runner_reads_the_last_closed_bar(runner, monkeypatch):
    monkeypatch.setattr(runner, "data_provider", TextProvider(history_text()))
    t, o, c = runner._last_closed_bar("BTC-USDT", "1hour")
    assert (int(t), o, c) == (NOW - NOW % HOUR - HOUR, 102.0, 105.0)


def test_one_candle_is_not_enough_and_does_not_hang(runner, monkeypatch):
    provider = TextProvider("[[1760000000000, 5.0, 5.0, 5.0, 5.0, 1000]]")
    monkeypatch.setattr(runner, "data_provider", provider)
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    with pytest.raises(runner.CoinDataError, match="only 1 candle"):
        runner._last_closed_bar("BTC-USDT", "1hour")
    assert provider.calls == runner._HISTORY_ATTEMPTS


def test_a_failing_source_is_retried_briefly_then_skipped(runner, monkeypatch):
    provider = TextProvider(error=RuntimeError("timeout"))
    monkeypatch.setattr(runner, "data_provider", provider)
    sleeps = []
    monkeypatch.setattr(runner.time, "sleep", sleeps.append)
    with pytest.raises(runner.CoinDataError, match="timeout"):
        runner._history_rows("BTC-USDT", "4hour")
    assert provider.calls == runner._HISTORY_ATTEMPTS
    assert len(sleeps) == runner._HISTORY_ATTEMPTS - 1


def test_the_current_price_is_the_exchanges_best_ask(runner, monkeypatch):
    asked = []
    monkeypatch.setattr(runner, "current_ask", lambda s: asked.append(s) or 106.0)
    assert runner._current_price("BNB") == 106.0
    assert asked == ["BNB-USD"]

    def no_quote(symbol):
        raise RuntimeError("no exchange in Settings gave a price for BNB-USD")

    monkeypatch.setattr(runner, "current_ask", no_quote)
    with pytest.raises(runner.CoinDataError, match="no current price for BNB"):
        runner._current_price("BNB")


def read_counts(folder):
    out = {}
    for name in (
        "long_dca_signal.txt",
        "short_dca_signal.txt",
        "signals_dca_spread.txt",
        "signals_dca_single.txt",
    ):
        with open(os.path.join(folder, name), encoding="utf-8") as f:
            out[name] = f.read()
    return out


def test_signal_counts_go_where_the_trader_and_hub_read_them(runner):
    folder = runner.coin_folder("BTC")
    os.makedirs(folder, exist_ok=True)
    runner._write_signal_counts("BTC", 4, 1)
    assert read_counts(folder) == {
        "long_dca_signal.txt": "4",
        "short_dca_signal.txt": "1",
        "signals_dca_spread.txt": "4",
        "signals_dca_single.txt": "1",
    }
    import pt_trader

    with mock.patch.object(pt_trader, "base_paths", {"BTC": folder}):
        assert pt_trader.CryptoAPITrading._read_long_dca_signal("BTC") == 4
        assert pt_trader.CryptoAPITrading._read_short_dca_signal("BTC") == 1
    assert pt_hub.read_short_signal(folder) == 1
    runner._write_signal_counts("NOFOLDER", 3, 0)  # never raises


def test_the_trader_ignores_counts_the_runner_stopped_updating(runner):
    import pt_trader

    folder = runner.coin_folder("ETH")
    os.makedirs(folder, exist_ok=True)
    runner._write_signal_counts("ETH", 5, 0)
    old = time.time() - pt_trader.SIGNAL_MAX_AGE_SECONDS - 60
    for name in ("long_dca_signal.txt", "short_dca_signal.txt"):
        os.utime(os.path.join(folder, name), (old, old))
    with mock.patch.object(pt_trader, "base_paths", {"ETH": folder}):
        assert pt_trader.CryptoAPITrading._read_long_dca_signal("ETH") == 0
        # an unknown short count blocks a new trade (the gate needs short == 0)
        assert pt_trader.CryptoAPITrading._read_short_dca_signal("ETH") is None


def test_an_untrained_coin_closes_its_gate_and_says_training(runner):
    folder = runner.coin_folder("SOL")
    os.makedirs(folder, exist_ok=True)
    runner._write_signal_counts("SOL", 6, 0)  # left over from before
    with open(os.path.join(folder, "trainer_status.json"), "w") as f:
        json.dump({"state": "TRAINING"}, f)
    runner.step_coin("SOL")
    assert read_counts(folder)["long_dca_signal.txt"] == "0"
    assert "TRAINING - no signals until the new model is saved" in (
        runner.display_cache["SOL"]
    )
    os.remove(os.path.join(folder, "trainer_status.json"))
    runner.step_coin("SOL")
    assert "NOT TRAINED" in runner.display_cache["SOL"]


def test_a_coin_waiting_for_data_is_labelled_and_its_gate_closed(runner):
    folder = runner.coin_folder("XRP")
    os.makedirs(folder, exist_ok=True)
    runner._write_signal_counts("XRP", 5, 0)
    runner._note_coin_error("XRP", runner.CoinDataError("no 1hour price history"))
    assert runner.display_cache["XRP"].startswith("XRP  (WAITING FOR PRICE DATA")
    assert read_counts(folder)["long_dca_signal.txt"] == "0"


def test_init_does_not_hang_when_the_source_is_down(runner, monkeypatch, capsys):
    monkeypatch.setattr(runner, "data_provider", TextProvider(error=OSError("down")))
    monkeypatch.setattr(runner.time, "sleep", lambda s: None)
    runner.init_coin("DOGE")
    assert runner.states["DOGE"]["tf_times"] == [0.0] * len(runner.tf_choices)
    assert "DOGE: no 1hour price history" in capsys.readouterr().out


class StopLoop(BaseException):
    """Ends the runner's endless main loop from a test."""


def test_one_coins_error_does_not_stop_the_runner(runner, monkeypatch, capsys):
    stepped = []

    def step(sym):
        stepped.append(sym)
        if sym == "ZEC":
            raise FileNotFoundError("memories_1hour.txt")

    monkeypatch.setattr(runner, "CURRENT_COINS", ["ZEC", "XRP"])
    monkeypatch.setattr(runner, "init_coin", lambda sym: None)
    monkeypatch.setattr(runner, "step_coin", step)
    monkeypatch.setattr(runner, "_sync_coins_from_settings", lambda: None)
    monkeypatch.setattr(runner.sys, "argv", ["pt_thinker.py"])
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        if len(sleeps) == 2:
            raise StopLoop()

    monkeypatch.setattr(runner.time, "sleep", sleep)
    with pytest.raises(StopLoop):
        runner.main()
    assert stepped == ["ZEC", "XRP", "ZEC", "XRP"]  # two full passes
    out = capsys.readouterr().out
    assert out.count("ZEC: skipped this pass - FileNotFoundError") == 1
    assert "Error in main loop" not in out
    assert runner.display_cache["ZEC"].startswith("ZEC  (ERROR - FileNotFoundError")


# --- the hub --------------------------------------------------------------------


def test_a_stopped_trainer_is_not_left_marked_training(tmp_path):
    folder = str(tmp_path)
    path = os.path.join(folder, "trainer_status.json")
    with open(path, "w") as f:
        json.dump({"state": "TRAINING"}, f)
    hub = types.SimpleNamespace(coin_folders={"BTC": folder})
    pt_hub.PowerTraderHub._mark_training_ended(hub, "BTC", 1)
    with open(path) as f:
        assert json.load(f)["state"] == "STOPPED"
    # a finished status is left alone
    with open(path, "w") as f:
        json.dump({"state": "FINISHED"}, f)
    pt_hub.PowerTraderHub._mark_training_ended(hub, "BTC", 1)
    with open(path) as f:
        assert json.load(f)["state"] == "FINISHED"


def test_recent_candles_are_fetched_again_once_the_bar_closes():
    forming = NOW - NOW % HOUR
    fake = FakeSource(hour_rows())
    clock = [forming + HOUR - 10]
    candles = runner_history.RecentCandles(source=fake, ttl=30, clock=lambda: clock[0])
    candles.history_text("BTC", "1hour")
    clock[0] = forming + HOUR + 5  # inside the ttl, but the bar has closed
    with pytest.raises(Exception):  # the fake has no bar for the hour just closed
        candles.history_text("BTC", "1hour")
    assert len(fake.calls) == 2


def test_the_gate_is_closed_while_the_counts_change(runner, monkeypatch):
    written = []

    def replace(path, text):
        written.append((os.path.basename(path), text))

    monkeypatch.setattr(runner, "_replace_text", replace)
    runner._write_signal_counts("BTC", 5, 0)
    assert written[:3] == [
        ("long_dca_signal.txt", "0"),
        ("short_dca_signal.txt", "0"),
        ("long_dca_signal.txt", "5"),
    ]

    written.clear()

    def short_fails(path, text):
        if path.endswith("short_dca_signal.txt"):
            raise OSError("disk full")
        replace(path, text)

    monkeypatch.setattr(runner, "_replace_text", short_fails)
    runner._write_signal_counts("BTC", 5, 0)
    assert written == [("long_dca_signal.txt", "0")]  # long stays 0


def test_a_signal_file_is_replaced_whole(runner, tmp_path):
    folder = tmp_path / "coin"
    folder.mkdir()
    path = str(folder / "long_dca_signal.txt")
    runner._replace_text(path, "4")
    runner._replace_text(path, "2")
    with open(path) as f:
        assert f.read() == "2"
    assert os.listdir(folder) == ["long_dca_signal.txt"]  # no temp file left


class StopStep(Exception):
    pass


def test_a_new_model_starts_from_placeholders(runner, monkeypatch):
    st = runner.states["BTC"] = runner.new_coin_state()
    st.update(
        model_id="old",
        low_bound_prices=[123.0] * 7,
        bounds_version=3,
        last_display_bounds_version=3,
        tf_choice_index=4,
        tf_times=["t"] * 7,
    )
    runner._ready_coins.add("BTC")
    monkeypatch.setattr(runner, "_coin_is_trained", lambda sym: True)
    monkeypatch.setattr(runner, "_model_verified", lambda sym: True)
    monkeypatch.setitem(runner._verified_models, "BTC", (None, {"model_id": "new"}))

    def stop(coin, tf):
        raise StopStep(tf)

    monkeypatch.setattr(runner, "_last_closed_bar", stop)
    with pytest.raises(StopStep, match="1hour"):  # the sweep starts again at 1hour
        runner.step_coin("BTC")
    st = runner.states["BTC"]
    assert st["model_id"] == "new"
    assert st["low_bound_prices"] == [0.01] * 7
    assert (st["bounds_version"], st["last_display_bounds_version"]) == (0, -1)
    assert st["tf_times"] == ["t"] * 7
    assert "BTC" not in runner._ready_coins


def test_a_held_coin_forgets_its_predictions(runner):
    os.makedirs(runner.coin_folder("SOL"), exist_ok=True)
    st = runner.states["SOL"] = runner.new_coin_state()
    st.update(low_bound_prices=[5.0] * 7, bounds_version=2, tf_times=["x"] * 7)
    runner.step_coin("SOL")  # no training stamp: held
    st = runner.states["SOL"]
    assert st["low_bound_prices"] == [0.01] * 7 and st["bounds_version"] == 0
    assert st["tf_times"] == ["x"] * 7


def test_the_runner_takes_current_prices_from_the_shared_exchange_manager(
    runner, monkeypatch, capsys
):
    """#144 removed pt_multi_exchange.multi_exchange_manager (built at import), and
    the runner's import of it failed on every price: "Multi-exchange system not
    available, using legacy Robinhood". It now asks the shared manager's quotes
    (market_exchanges: public prices, no credentials, nothing written), primary
    exchange first; there is no Robinhood fallback (FDS-MX-001 decision D4)."""
    import pt_multi_exchange

    class Manager:
        initialized = False

        def initialize(
            self, user_region=None, with_credentials=False, save_defaults=True
        ):
            self.initialized, self.with_credentials = True, with_credentials
            self.save_defaults = save_defaults
            return True

        def quote(self, symbol):
            return Sourced(PriceQuote(123.0, 123.45, None), "coinbase", symbol, True)

    monkeypatch.setattr(pt_multi_exchange, "_shared", None)
    monkeypatch.setattr(pt_multi_exchange, "market_exchanges", REAL_MARKET_EXCHANGES)
    monkeypatch.setattr(pt_multi_exchange, "MultiExchangeManager", Manager)
    assert runner.current_ask("BTC-USD") == 123.45
    manager = pt_multi_exchange.shared_manager()
    assert manager is pt_multi_exchange.shared_manager()  # one per process
    assert manager.with_credentials is False  # market data reads no credentials
    assert manager.save_defaults is False  # and writes no settings
    out = capsys.readouterr().out
    assert "not available" not in out and "legacy Robinhood" not in out
