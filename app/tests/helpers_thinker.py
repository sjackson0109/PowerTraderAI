"""Drive the real neural runner (``app/pt_thinker.py``) on fixture bars (FDS-MDL).

The thinker cannot run on live data today: its data provider returns one synthetic
candle (#141). ``run_thinker`` runs ``pt_thinker.step_coin`` in a child process with:

* a fake ``pt_data_provider`` (installed in ``sys.modules`` before the import) whose
  ``get_historical_data(coin, tf)`` answers like KuCoin did for upstream: rows newest
  first, ``[time, open, close, high, low, volume, turnover]``, row 0 the forming bar and
  row 1 the last closed one. Row 1 is the timeframe's last bar that closed strictly
  before the decision time (FDS-MDL Phase 3 cadence, owner decision 2026-10-06: the
  live thinker's last evaluation inside bar t);
* ``robinhood_current_ask`` replaced by the decision's price, and ``time.sleep`` by a
  no-op (the thinker only sleeps while retrying).

The child is started like a trainer child in the tests: the caller's guard
(helpers_trainer.guard_trainer_children) blocks the network, and POWERTRADER_HOME is the
per-test home. After each decision's sweeps the child records the coin's state.
"""

import json
import os
import subprocess
import sys

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)

TIMEFRAMES = ("1hour", "2hour", "4hour", "8hour", "12hour", "1day", "1week")
STEP_SECONDS = {
    "1hour": 3600,
    "2hour": 7200,
    "4hour": 14400,
    "8hour": 28800,
    "12hour": 43200,
    "1day": 86400,
    "1week": 604800,
}
STATE_KEYS = (
    "high_tf_prices",
    "low_tf_prices",
    "perfects",
    "training_issues",
    "tf_sides",
    "messages",
    "margins",
    "low_bound_prices",
    "high_bound_prices",
    "tf_choice_index",
)

DRIVER = r"""
import json
import os
import sys
import types

scenario_path, out_path = sys.argv[1], sys.argv[2]
with open(scenario_path, encoding="utf-8") as f:
    scenario = json.load(f)
sys.path.insert(0, scenario["app_dir"])
STEP = scenario["step_seconds"]
BARS = {tf: [tuple(b) for b in rows] for tf, rows in scenario["bars"].items()}
NOW = {"t": None, "price": None}
SERVED = {}


def last_closed(tf, now):
    best = None
    for bar in BARS[tf]:
        if bar[0] + STEP[tf] < now:  # closed strictly before the decision time
            best = bar
        else:
            break
    return best


def row(values):
    return "[" + ", ".join(values) + "]"


class FakeProvider:
    def is_available(self):
        return True

    def get_provider_info(self):
        return "FIXTURE BARS (thinker driver)"

    def get_historical_data(self, coin, tf, *args, **kwargs):
        bar = last_closed(tf, NOW["t"])
        if bar is None:
            raise SystemExit("no closed %s bar before %s" % (tf, NOW["t"]))
        SERVED[tf] = list(bar)
        t, o, h, lo, c = bar
        forming = [str(int(t + STEP[tf])), repr(c), repr(c), repr(c), repr(c), "0.0", "0.0"]
        closed = [str(int(t)), repr(o), repr(c), repr(h), repr(lo), "0.0", "0.0"]
        return "[" + row(forming) + ", " + row(closed) + "]"


module = types.ModuleType("pt_data_provider")
module.get_data_provider = lambda: FakeProvider()
sys.modules["pt_data_provider"] = module

import pt_thinker  # noqa: E402

pt_thinker.time.sleep = lambda seconds: None
pt_thinker.robinhood_current_ask = lambda symbol: NOW["price"]

coin = scenario["coin"]
records = []
# as pt_thinker.main() does before stepping: init_coin reads each timeframe's last bar time
first = scenario["decisions"][0]
NOW["t"], NOW["price"] = first["time"], first["price"]
pt_thinker.init_coin(coin)
SERVED.clear()  # a record shows what its own decision fetched
os.chdir(scenario["home"])
for decision in scenario["decisions"]:
    for path, text in decision.get("append", []):  # a file changed between decisions
        with open(path, "a", encoding="utf-8") as f:
            f.write(text)
    NOW["t"], NOW["price"] = decision["time"], decision["price"]
    for _ in range(decision.get("sweeps", 1) * len(pt_thinker.tf_choices)):
        pt_thinker.step_coin(coin)
    os.chdir(scenario["home"])
    st = pt_thinker.states.get(coin, {})
    # a snapshot: the thinker mutates these lists in place on later steps
    record = json.loads(json.dumps({k: st.get(k) for k in scenario["state_keys"]}))
    record["time"] = decision["time"]
    record["price"] = decision["price"]
    record["served"] = {tf: SERVED.get(tf) for tf in pt_thinker.tf_choices}
    folder = pt_thinker.coin_folder(coin)
    for name in ("signals_dca_spread.txt", "signals_dca_single.txt"):
        try:
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                record[name] = f.read()
        except OSError:
            record[name] = None
    records.append(record)
    SERVED.clear()
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(records, f)
"""


def bars_from_frames(frames):
    """{trainer timeframe: [[open_time_s, open, high, low, close], ...]} from candle
    frames keyed by candle timeframe (1h ... 1w)."""
    candle_tf = {
        "1hour": "1h",
        "2hour": "2h",
        "4hour": "4h",
        "8hour": "8h",
        "12hour": "12h",
        "1day": "1d",
        "1week": "1w",
    }
    out = {}
    for choice, tf in candle_tf.items():
        f = frames[tf]
        out[choice] = [
            [int(t.timestamp()), o, h, lo, c]
            for t, o, h, lo, c in zip(
                f["open_time"],
                f["open"].tolist(),
                f["high"].tolist(),
                f["low"].tolist(),
                f["close"].tolist(),
            )
        ]
    return out


def run_thinker(work_dir, coin, bars, decisions, timeout=600):
    """Run the thinker for ``coin`` over ``decisions`` ([{time, price, sweeps, append}];
    ``append``: [[path, text]] appended before that decision's sweeps) on ``bars``;
    returns (records, stdout, exit code)."""
    os.makedirs(work_dir, exist_ok=True)
    scenario = {
        "app_dir": APP_DIR,
        "home": os.environ["POWERTRADER_HOME"],
        "coin": coin,
        "bars": bars,
        "step_seconds": STEP_SECONDS,
        "decisions": decisions,
        "state_keys": list(STATE_KEYS),
    }
    scenario_path = os.path.join(work_dir, "scenario.json")
    out_path = os.path.join(work_dir, "records.json")
    driver_path = os.path.join(work_dir, "drive_thinker.py")
    with open(scenario_path, "w", encoding="utf-8") as f:
        json.dump(scenario, f)
    with open(driver_path, "w", encoding="utf-8") as f:
        f.write(DRIVER)
    proc = subprocess.run(
        [sys.executable, driver_path, scenario_path, out_path],
        cwd=work_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    records = None
    if os.path.isfile(out_path):
        with open(out_path, encoding="utf-8") as f:
            records = json.load(f)
    return records, proc.stdout + proc.stderr, proc.returncode
