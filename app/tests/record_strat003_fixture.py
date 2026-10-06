"""Record the STRAT-003 reproduction fixture from the real neural runner (FDS-MDL 6.2,
acceptance 7).

Not part of the suite (the name does not match ``test_*.py``). Run it explicitly, under
the guard app/tests/conftest.py loads, with the output path in PT_RECORD_STRAT003
(PowerShell):

    $env:PT_RECORD_STRAT003 = '<scratch>\\strat003_thinker_record.json'
    python -m pytest app/tests/record_strat003_fixture.py -p no:cacheprovider -q

For each model in ``helpers_strat003.SCENARIOS`` (two always-inactive timeframes, and
all seven active) it publishes the model as BTC's in the per-test home and runs the real
``pt_thinker.step_coin`` (helpers_thinker: fixture bars behind a fake data provider) at
every hourly close of the last ten days of four weeks of synthetic bars (two sweeps
each: the steady state). It writes the bars, the runner's source blob, the bars the
runner was served at each decision (the same in every scenario) and, per scenario, the
model files and, per decision, what the runner recorded: the sides, the bounds it kept
and its LONG/SHORT counts. app/tests/test_model_strategy.py
checks STRAT-003 against it.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
for _path in (APP_DIR, TESTS_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import helpers_candles as hc  # noqa: E402
import helpers_strat003 as h3  # noqa: E402
import helpers_thinker as hth  # noqa: E402
import helpers_trainer as ht  # noqa: E402
import pattern_model  # noqa: E402
import pt_paths  # noqa: E402

START = datetime(2024, 1, 1, tzinfo=timezone.utc)  # a Monday
HOURS = 4 * 168
DECISION_HOURS = 240
SEED = 11


def test_record(monkeypatch, tmp_path, isolated_user_dirs):
    out = os.environ.get("PT_RECORD_STRAT003")
    if not out:
        pytest.skip("set PT_RECORD_STRAT003 to the fixture path to write")
    monkeypatch.chdir(tmp_path)
    ht.guard_trainer_children(monkeypatch, tmp_path)
    hourly = hc.synthetic_hourly(HOURS, START, seed=SEED)
    frames = hc.all_timeframes(hourly)
    folder = pt_paths.neural_dir()  # BTC's coin folder, as the runner resolves it
    end = START + timedelta(hours=HOURS)
    closes = [
        int((end - timedelta(hours=k)).timestamp())
        for k in range(DECISION_HOURS, -1, -1)
    ]
    decisions = h3.thinker_decisions_at(hourly, closes)
    scenarios = []
    served = None
    for model_id, model in h3.SCENARIOS:
        h3.write_files(folder, model)
        h3.publish_files(folder, model_id)
        h3.stamp_trained(folder)
        records, output, code = hth.run_thinker(
            str(tmp_path / f"drive-{model_id}"),
            "BTC",
            hth.bars_from_frames(frames),
            decisions,
        )
        assert code == 0, output[-3000:]
        assert f"Model for BTC: {model_id}" in output
        model_files = {}
        for name in pattern_model.model_file_names():
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                model_files[name] = f.read()
        recorded = [
            {
                "time": r["time"],
                "price": r["price"],
                "tf_sides": r["tf_sides"],
                "low_bound_prices": r["low_bound_prices"],
                "high_bound_prices": r["high_bound_prices"],
                "longs": int(r["signals_dca_spread.txt"]),
                "shorts": int(r["signals_dca_single.txt"]),
            }
            for r in records
        ]
        sides = [s for d in recorded for s in d["tf_sides"]]
        assert sides.count("long") and sides.count("short"), model_id
        # the bars served depend on the decision times only: the same in every scenario
        served_now = [r["served"] for r in records]
        assert served is None or served_now == served
        served = served_now
        scenarios.append(
            {"model_id": model_id, "model_files": model_files, "decisions": recorded}
        )
    blob = subprocess.run(
        ["git", "-C", APP_DIR, "hash-object", "pt_thinker.py"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    fixture = {
        "description": __doc__.split("\n\n")[0],
        "recorded_with": "app/tests/record_strat003_fixture.py",
        "thinker_blob": blob,
        "seed": SEED,
        "hourly": [
            [int(t.timestamp()), o, hi, lo, c, v]
            for t, o, hi, lo, c, v in zip(
                hourly["open_time"],
                hourly["open"],
                hourly["high"],
                hourly["low"],
                hourly["close"],
                hourly["volume"],
            )
        ],
        "served": served,  # per decision: {timeframe: [open s, open, high, low, close]}
        "scenarios": scenarios,
    }
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(fixture, f, indent=None, separators=(",", ":"))
        f.write("\n")
