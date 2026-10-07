"""Shared pieces for the STRAT-003 tests and the fixture recorder (FDS-MDL Phase 3).

* ``CRAFTED``: a hand-made pattern model whose timeframes behave differently on
  purpose: always active with different bands, always inactive (4hour, 12hour: two
  placeholders, so the runner's remap drops one and shifts later bounds), and active
  only for some bars (1day), so the number of inactive timeframes changes over time.
  ``CRAFTED_ALL_ACTIVE``: every timeframe always active (all seven bounds kept).
* ``publish_files``: publish model files into the per-test store with a manifest.
* ``thinker_decisions_at``: decisions at bar closes (time = the close, price = the
  closing bar's close, two sweeps: the runner's steady state).
* ``strategy_signals``: STRAT-003's signals at the same times, on the same bars.
"""

import os
from datetime import datetime, timezone

import pandas as pd

import model_store
import pattern_model

ONES = "1.0"


def _tf(threshold, memories):
    n = len(memories.split("~"))
    ones = " ".join([ONES] * n)
    return (threshold, memories, ones, ones, ones)


# fields per memory: "<body %> <close move %>{}<high move %>{}<low move %>"
CRAFTED = {
    "1hour": _tf("1000000000.0", "0.0 0.1{}0.3{}-0.3"),
    "2hour": _tf("1000000000.0", "0.0 0.1{}0.5{}-0.4"),
    "4hour": _tf("0.0", "12345.0 0.0{}1.0{}-1.0"),
    "8hour": _tf("1000000000.0", "0.0 0.0{}0.8{}-0.7"),
    "12hour": _tf("0.0", "12345.0 0.0{}1.0{}-1.0"),
    "1day": _tf("150.0", "0.5 0.2{}1.2{}-1.1"),
    "1week": _tf("1000000000.0", "0.0 0.0{}2.0{}-2.0"),
}
# every timeframe always active, each with its own band: all seven bounds kept, so the
# gap pass reaches its last pairs and 1week is compared with its own bound
CRAFTED_ALL_ACTIVE = {
    tf: _tf("1000000000.0", f"0.0 0.0{{}}{high}{{}}-{low}")
    for tf, high, low in (
        ("1hour", "0.3", "0.3"),
        ("2hour", "0.5", "0.4"),
        ("4hour", "0.6", "0.6"),
        ("8hour", "0.8", "0.7"),
        ("12hour", "1.0", "0.9"),
        ("1day", "1.2", "1.1"),
        ("1week", "2.0", "2.0"),
    )
}
SCENARIOS = (("crafted-strat003", CRAFTED), ("crafted-all-active", CRAFTED_ALL_ACTIVE))


def write_files(folder, model=CRAFTED):
    os.makedirs(folder, exist_ok=True)
    for tf, texts in model.items():
        for kind, text in zip(pattern_model.FILE_KINDS, texts):
            with open(
                os.path.join(folder, f"{kind}_{tf}.txt"), "w", encoding="utf-8"
            ) as f:
                f.write(text)


def publish_files(
    folder, model_id, coin="BTC", train_end="2024-01-01T00:00:00Z", **overrides
):
    """Publish the model files in ``folder`` as ``model_id`` (a minimal manifest, with
    any ``overrides`` of its fields, e.g. validation or params)."""
    manifest = {
        "manifest_version": model_store.MANIFEST_VERSION,
        "model_id": model_id,
        "trainer_path": "app/tests/helpers_strat003.py",
        "trainer_git_commit": None,
        "upstream_commit": "ba62130",
        "symbol": f"{coin}USDT",
        "coin": coin,
        "timeframes": list(pattern_model.TIMEFRAMES),
        "train_start": "2023-01-01T00:00:00Z",
        "train_end": train_end,
        "candle_file_sha256": {},
        "params": {},
        "seed": 0,
        "created_at": "2026-10-06T00:00:00Z",
        "validation_metrics": {},
        "files": model_store.folder_file_hashes(folder),
    }
    manifest.update(overrides)
    model_store.publish(folder, manifest, trainer_root=None)
    return manifest


def stamp_trained(folder):
    """The training stamp the runner needs to step a coin (fresh: now)."""
    with open(
        os.path.join(folder, "trainer_last_training_time.txt"), "w", encoding="utf-8"
    ) as f:
        f.write(str(int(datetime.now(timezone.utc).timestamp())))


def thinker_decisions_at(hourly, close_times):
    """Decisions at bar closes: time = the close (epoch s), price = the close of the
    hourly bar that ends then, two sweeps each."""
    by_close = {
        int(t.timestamp()) + 3600: float(c)
        for t, c in zip(hourly["open_time"], hourly["close"])
    }
    return [
        {"time": int(t), "price": by_close[int(t)], "sweeps": 2} for t in close_times
    ]


def strategy_signals(strategy, frame, close_times, bar_seconds):
    """STRAT-003's signal at each close time, on ``frame`` (the run's bars)."""
    strategy.set_timeframe(bar_seconds)
    opens = {int(t.timestamp()): i for i, t in enumerate(frame["open_time"])}
    out = []
    for t in close_times:
        i = opens[int(t) - bar_seconds]
        out.append(strategy.on_bar(frame.iloc[: i + 1]))
    return out


def sides_of(signal):
    """The per-timeframe sides a STRAT-003 signal reports, in timeframe order."""
    names = {1.0: "long", -1.0: "short", 0.0: "none"}
    return [names[signal.indicators[f"side_{tf}"]] for tf in pattern_model.TIMEFRAMES]


def hourly_from_rows(rows):
    """Cache-like hourly frame from ``[[open_time_s, o, h, l, c, v], ...]``."""
    return pd.DataFrame(
        {
            "open_time": [pd.Timestamp(r[0], unit="s", tz="UTC") for r in rows],
            "open": [r[1] for r in rows],
            "high": [r[2] for r in rows],
            "low": [r[3] for r in rows],
            "close": [r[4] for r in rows],
            "volume": [r[5] for r in rows],
        }
    )
