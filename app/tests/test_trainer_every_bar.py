"""The pattern trainer learns from every bar of its window, newest included
(deviation 11), over the window chosen (``--window``).

All candles are synthetic (helpers_candles) and read from the cache offline, under
the isolation guard (app/conftest.py).
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import helpers_candles as hc  # noqa: E402
import pt_pattern_trainer as ppt  # noqa: E402
from market_data import candles  # noqa: E402

PAIR = "BTCUSDT"
END = datetime(2026, 11, 2, tzinfo=timezone.utc)  # a Monday


def seed(hourly):
    hc.seed_cache(candles.cache_dir_default(), PAIR, hc.all_timeframes(hourly))


def train(tmp_path, start, end=END, logs=None, offline_run=True, **kwargs):
    folder = tmp_path / "coin"
    folder.mkdir(exist_ok=True)
    return ppt.train(
        "BTC",
        str(folder),
        start,
        end,
        offline=offline_run,
        log=(logs.append if logs is not None else lambda *a: None),
        **kwargs,
    )


def newest_open(summary, tf):
    return pd.Timestamp(summary["candles"][tf]["last_open"])


# --- the window -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "window, days", [("30d", 30), ("3m", 90), ("6m", 180), ("12m", 365), ("3y", 1095)]
)
def test_each_window_is_that_long_before_train_end(window, days):
    cfg = ppt.parse_args(
        ["BTC", "--window", window, "--train-end", END.isoformat()], environ={}
    )
    assert cfg["train_end"] - cfg["train_start"] == timedelta(days=days)
    assert (cfg["window"], cfg["sources"]["window"]) == (window, "command line")
    assert cfg["sources"]["train_start"] == f"window {window}"


def test_the_whole_history_starts_before_any_coin_was_listed():
    cfg = ppt.parse_args(["BTC", "--window", "all"], environ={})
    assert cfg["train_start"] == ppt.HISTORY_START


def test_the_window_comes_from_the_command_line_then_the_environment_then_3y():
    env = {ppt.ENV_TRAIN_WINDOW: "6m"}
    end = ["--train-end", END.isoformat()]
    assert ppt.parse_args(["BTC", *end], environ={})["window"] == "3y"
    cfg = ppt.parse_args(["BTC", *end], environ=env)
    assert (cfg["window"], cfg["sources"]["window"]) == ("6m", ppt.ENV_TRAIN_WINDOW)
    assert (
        ppt.parse_args(["BTC", "--window", "30d", *end], environ=env)["window"] == "30d"
    )
    # an explicit train_start wins over any window
    start = (END - timedelta(days=10)).isoformat()
    cfg = ppt.parse_args(["BTC", "--train-start", start, *end], environ=env)
    assert cfg["train_end"] - cfg["train_start"] == timedelta(days=10)


def test_an_unknown_window_is_refused():
    with pytest.raises(ppt.UsageError, match="window"):
        ppt.parse_args(["BTC", "--window", "2y"], environ={})


# --- every bar, newest included -------------------------------------------------------


def test_a_3_year_window_trains_on_its_newest_bars(tmp_path, monkeypatch):
    """Over three years every pass walks to the last bar that closed before
    train_end, and the published model is that fit."""
    monkeypatch.setattr(ppt, "TF_CHOICES", ["1hour", "1day"])  # two timeframes: faster
    start = END - ppt.DEFAULT_WINDOW
    hours = int((END - start) / timedelta(hours=1))
    seed(hc.synthetic_hourly(hours, start, seed=11))
    summary = train(tmp_path, start)

    assert newest_open(summary, "1h") == pd.Timestamp(END) - pd.Timedelta(hours=1)
    for tf_choice, data in summary["timeframes"].items():
        for p in data["passes"]:
            assert p["first_bar"] == 9 and p["last_bar"] == p["bars_used"] - 1, (
                tf_choice,
                p,
            )
            assert p["bars_used"] == p["bars_in_window"], (tf_choice, p)
            assert p["steps"] == p["bars_used"] - 9, (tf_choice, p)
    hourly = summary["timeframes"]["1hour"]["passes"]
    assert [p["bars_used"] for p in hourly] == [hours]


def test_the_1hour_timeframe_walks_its_bars_once_and_the_others_twice():
    assert ppt.passes_for("1hour") == [(0, "1hour")]
    assert ppt.passes_for("1day") == [(0, "1hour"), (1, "1day")]
    assert ppt.passes_for("1day", upstream_rows=True) == [
        (0, "1hour"),
        (1, "1day"),
        (2, "1day"),
    ]


def test_a_coin_younger_than_the_window_trains_on_all_its_history(
    tmp_path, monkeypatch
):
    """HYPE-like: listed eight weeks before train_end, trained over 12 months. It
    trains on every bar it has, without an error, and says how much of the window
    it has."""
    from test_pattern_trainer import FakeKlines

    monkeypatch.setattr(ppt, "TF_CHOICES", ["1hour", "1day", "1week"])
    listed = END - timedelta(weeks=8)
    hourly = hc.synthetic_hourly(8 * 168, listed, seed=12)
    # online, as the hub trains: the exchange has no bars before the listing
    hc.fake_layer(monkeypatch, FakeKlines({PAIR: hc.all_timeframes(hourly)}))
    logs = []
    start = END - timedelta(days=ppt.WINDOWS["12m"])
    summary = train(tmp_path, start, logs=logs, offline_run=False)

    hourly = summary["candles"]["1h"]
    assert hourly["bars"] == 8 * 168
    assert pd.Timestamp(hourly["first_open"]) == pd.Timestamp(listed)
    assert hourly["missing_at_start"] == (365 * 24) - 8 * 168
    for data in summary["timeframes"].values():
        for p in data["passes"]:
            assert p.get("skipped") or p["last_bar"] == p["bars_used"] - 1, p
    assert summary["timeframes"]["1hour"]["memories"] > 0
    line = next(m for m in logs if m.startswith(f"{PAIR} 1h:"))
    assert line == (
        f"{PAIR} 1h: {8 * 168} bars, {hourly['first_open']} .. {hourly['last_open']}; "
        f"the window opens {hourly['missing_at_start']} bar(s) earlier"
    )


def test_a_timeframe_with_too_few_bars_is_skipped_not_an_error(tmp_path, monkeypatch):
    """Eight weeks hold 8 weekly bars: the weekly timeframe's own pass is skipped
    and recorded; its pass 0 on the hourly bars still trains it."""
    monkeypatch.setattr(ppt, "TF_CHOICES", ["1hour", "1week"])
    seed(hc.synthetic_hourly(8 * 168, END - timedelta(weeks=8), seed=13))
    summary = train(tmp_path, END - timedelta(weeks=8))
    weekly = summary["timeframes"]["1week"]["passes"]
    assert weekly[0]["last_bar"] == weekly[0]["bars_used"] - 1
    assert weekly[1]["skipped"] == "fewer than 10 bars"
    assert summary["timeframes"]["1week"]["memories"] > 0


def test_pass_0_is_walked_once_and_copied_into_every_timeframe(tmp_path, monkeypatch):
    """The same walk in every timeframe: walked once, and every timeframe starts its
    own pass from the same memories."""
    walked = []
    real = ppt.run_pass

    def spy(files, tf_choice, restarted_yet, bars, log, upstream_rows=False):
        walked.append((tf_choice, restarted_yet))
        return real(files, tf_choice, restarted_yet, bars, log, upstream_rows)

    monkeypatch.setattr(ppt, "run_pass", spy)
    seed(hc.synthetic_hourly(1680, END - timedelta(hours=1680), seed=14))
    summary = train(tmp_path, END - timedelta(hours=1680))
    assert walked.count(("1hour", 0)) == 1
    assert [w for w in walked if w[1] == 0] == [("1hour", 0)]
    first = summary["timeframes"]["1hour"]["passes"][0]
    for tf_choice in ppt.TF_CHOICES[1:]:
        assert summary["timeframes"][tf_choice]["passes"][0] == {
            **first,
            "data_tf": "1hour",
        }
