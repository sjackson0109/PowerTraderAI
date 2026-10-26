"""The pattern trainer, its cache readers and its models use one exchange's candles
(FDS-MX-001 phase F): the first in Settings order that can serve the whole training
window; the model records it; the STRAT-003 strategy and the backtest read it; the
runner warns when the bars it reads come from another exchange.

Everything runs under the isolation guard (app/conftest.py); no network.
"""

import os
import sys
import types
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import helpers_candles as hc  # noqa: E402
import pt_pattern_trainer as ppt  # noqa: E402
from market_data import candles  # noqa: E402
from pt_exchange_abstraction import ExchangeManager, ExchangeType  # noqa: E402

START = datetime(2024, 1, 1, tzinfo=timezone.utc)  # a Monday
HOURS = 24 * 7 * 4
END = START + timedelta(hours=HOURS)


class Bars:
    """One exchange's bars for every trainer timeframe of one coin."""

    def __init__(self, frames, pair):
        self.frames, self.pair, self.calls = frames, pair, []

    def fetch(self, symbol, tf, start_ms, end_ms=None):
        self.calls.append((symbol, tf))
        frame = self.frames.get(tf)
        if frame is None or symbol != self.pair:
            return []
        epoch = pd.Timestamp("1970-01-01", tz="UTC")
        ms = ((frame["open_time"] - epoch) // pd.Timedelta(milliseconds=1)).tolist()
        rows = []
        for t, o, h, lo, c, v in zip(
            ms,
            frame["open"],
            frame["high"],
            frame["low"],
            frame["close"],
            frame["volume"],
        ):
            if t >= start_ms and (end_ms is None or t <= end_ms):
                rows.append([t, o, h, lo, c, v])
        return rows


class ShortMemory(hc.FakeConnector):
    """An exchange that serves only its latest few bars (as Kraken's 720)."""

    def max_history_bars(self, tf):
        return 10


def two_exchanges(monkeypatch, frames):
    """Kraken (primary, recent bars only) and Coinbase, both with the coin."""
    manager = ExchangeManager()
    kraken = Bars(frames, "XBTCUSD")
    coinbase = Bars(frames, "BTC-USD")
    manager.exchanges[ExchangeType("kraken")] = ShortMemory(kraken, "X{}USD")
    manager.exchanges[ExchangeType("coinbase")] = hc.FakeConnector(coinbase, "{}-USD")
    manager.primary_exchange = ExchangeType("kraken")
    monkeypatch.setattr(candles, "_exchange_manager", lambda: manager)
    return kraken, coinbase


@pytest.fixture
def frames():
    return hc.all_timeframes(hc.synthetic_hourly(HOURS, START, seed=3))


def test_the_flat_cache_moves_once_into_binances_folder(tmp_path):
    (tmp_path / "BTCUSDT_1h.csv").write_text("open_time_ms,open\n", encoding="utf-8")
    (tmp_path / "binance").mkdir()
    (tmp_path / "binance" / "ETHUSDT_1h.csv").write_text("kept", encoding="utf-8")
    (tmp_path / "ETHUSDT_1h.csv").write_text("older", encoding="utf-8")
    candles.move_flat_cache(str(tmp_path))
    assert (tmp_path / "binance" / "BTCUSDT_1h.csv").is_file()
    assert not (tmp_path / "BTCUSDT_1h.csv").exists()
    # a file already in binance/ is kept; the flat one stays where it was
    assert (tmp_path / "binance" / "ETHUSDT_1h.csv").read_text(
        encoding="utf-8"
    ) == "kept"
    assert (tmp_path / "ETHUSDT_1h.csv").is_file()


def test_training_passes_over_an_exchange_that_cannot_reach_back(
    tmp_path, monkeypatch, frames
):
    kraken, coinbase = two_exchanges(monkeypatch, frames)
    loader = ppt.BarLoader("BTC", START, END, False, cache_dir=str(tmp_path))
    loader.bars("1hour")
    assert (loader.exchange, loader.pair) == ("coinbase", "BTC-USD")
    assert kraken.calls == []  # never asked: it cannot serve four weeks back
    assert os.path.isfile(
        candles.cache_path("BTC-USD", "1h", str(tmp_path), "coinbase")
    )


def test_every_timeframe_comes_from_the_exchange_chosen_first(
    tmp_path, monkeypatch, frames
):
    kraken, coinbase = two_exchanges(monkeypatch, frames)
    loader = ppt.BarLoader("BTC", START, END, False, cache_dir=str(tmp_path))
    loader.bars("1hour")
    loader.bars("1week")
    assert {tf for _, tf in coinbase.calls} >= {"1h", "1w"}
    assert kraken.calls == []


def test_exchanges_narrows_the_trainers_choice(tmp_path, monkeypatch, frames):
    two_exchanges(monkeypatch, frames)
    with pytest.raises(ppt.TrainerError):
        ppt.BarLoader(
            "BTC", START, END, False, cache_dir=str(tmp_path), exchanges=["kraken"]
        ).bars("1hour")


def test_the_trainer_cli_takes_an_exchange():
    now = datetime(2025, 1, 1, tzinfo=timezone.utc)
    cfg = ppt.parse_args(["ETH", "--exchange", "Coinbase"], environ={}, now=now)
    assert cfg["exchanges"] == ["coinbase"]
    assert ppt.parse_args(["ETH"], environ={}, now=now)["exchanges"] is None


def test_the_model_strategy_reads_its_models_exchange(tmp_path, monkeypatch):
    from strategies import model_strategy

    folder = tmp_path / "candles"
    hc.seed_cache(
        str(folder), "BTC-USD", {"1h": hc.synthetic_hourly(48, START)}, "coinbase"
    )
    monkeypatch.setattr(
        model_strategy.pt_paths, "cache_dir", lambda create=True: str(tmp_path)
    )
    assert set(model_strategy.cached_bars("BTC-USD", "coinbase")) == {"1h"}
    assert model_strategy.cached_bars("BTC-USD", "kraken") == {}


def test_a_model_from_before_phase_f_reads_binance_bars():
    import pt_thinker

    assert pt_thinker._model_exchange({"symbol": "BTCUSDT"}) == "binance"
    assert pt_thinker._model_exchange({"exchange": "kraken"}) == "kraken"


def test_the_runner_warns_once_when_its_bars_come_from_another_exchange(
    monkeypatch, capsys
):
    import pt_thinker
    from market_data import runner_history

    shared = types.SimpleNamespace(last_source={("BTC-USD", "1h"): "coinbase"})
    monkeypatch.setattr(runner_history, "_shared", shared)
    monkeypatch.setattr(pt_thinker, "_EXCHANGE_WARNED", set())
    manifest = {"symbol": "BTCUSDT", "model_id": "m"}  # trained before phase F
    monkeypatch.setitem(pt_thinker._verified_models, "BTC", ((), manifest))
    pt_thinker._check_bars_exchange("BTC", "BTC-USDT", "1hour")
    pt_thinker._check_bars_exchange("BTC", "BTC-USDT", "1hour")
    out = capsys.readouterr().out
    assert out.count("WARNING: BTC: the model was trained on binance bars") == 1
    assert "the runner now reads coinbase bars. Retrain BTC to match." in out
    shared.last_source[("BTC-USD", "1h")] = "binance"
    monkeypatch.setattr(pt_thinker, "_EXCHANGE_WARNED", set())
    pt_thinker._check_bars_exchange("BTC", "BTC-USDT", "1hour")
    assert "WARNING" not in capsys.readouterr().out


def test_a_models_backtest_reads_the_models_exchange(monkeypatch):
    from backtest import cli

    probe = types.SimpleNamespace(
        strategy=types.SimpleNamespace(
            model_symbol="BTC-USD", model_exchange="coinbase"
        )
    )
    monkeypatch.setattr(cli, "build_runner", lambda *a, **k: probe.strategy and probe)
    asked = []

    def stop(symbol, tf, start, end, **kwargs):
        asked.append(kwargs.get("exchanges"))
        raise SystemExit("stop here")

    monkeypatch.setattr(cli, "exchange_candles", stop)
    args = cli.build_parser().parse_args(
        ["--strategy", "STRAT-003", "--symbol", "BTCUSDT", "--start", "2025-01-01",
         "--end", "2025-02-01"]
    )  # fmt: skip
    with pytest.raises(SystemExit):
        cli.run(args)
    assert asked == [["coinbase"]]
    args.exchange = "kraken"
    with pytest.raises(ValueError, match="trained on coinbase bars"):
        cli.run(args)
