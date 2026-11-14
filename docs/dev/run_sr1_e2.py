"""
SR1-E2, the registered development evaluation of the Donchian ensemble, frozen and run in
a sandbox on the owner's approval of 2026-11-14 (D5; ``strategy_lab/e2.py`` declares and
evaluates it).

Run it only inside a sandbox: POWERTRADER_HOME, APPDATA and LOCALAPPDATA pointed at
scratch folders (outside the real user folders), a keyring that fails
(PYTHON_KEYRING_BACKEND=keyring.backends.fail.Keyring), no keys. The sandbox's candle
cache must be cut at 2025-05-06 00:00 UTC (as E1's ``cache_cut.json``), and the loader
refuses any bar from the reserved months regardless.

    python run_sr1_e2.py <app dir> <out dir> freeze <rate file> [--venue <file>]
                                                    [--exposures <trials.jsonl>]
    python run_sr1_e2.py <app dir> <out dir> run
    python run_sr1_e2.py <app dir> <out dir> rehearse

* ``freeze``: reads the GBP-to-USD rate from ``<rate file>`` (a ``rate.json`` as E1's
  driver writes it: the Bank of England's rate, checked against the ECB's; refused
  unless the check agreed); reads the candles once, offline, through the exchanges in
  Settings order, and the second exchange's on its own; today's venue rules (Coinbase's
  public product data through the exchange layer, or ``--venue``'s file) and what the
  exchange layer gives as each coin's fee rates; counts the exploration's trial log
  (``docs/dev/compare-ensemble/trials.jsonl``, or ``--exposures``); refuses a sandbox
  whose trial log or ledger already holds an SR1-E2 trial; and freezes SR1-E2
  (``strategy_lab.experiment.freeze``). Nothing is scored.
* ``run``: verifies the frozen record (its seal, the code, the libraries and the
  candles), runs ``strategy_lab.e2.evaluate``, and writes ``results.json``, the
  evidence lines and the report.
* ``rehearse``: the same pipeline on synthetic candles, venue rules and rate, in a
  separate sandbox whose folder name holds "rehearsal": it reads no real candles, and
  shows that every step runs and how long it takes.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

KEYRING = "keyring.backends.fail.Keyring"


def log(msg: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {msg}", flush=True)


def _under(path: str, folder: str) -> bool:
    try:
        a, b = os.path.normcase(os.path.realpath(path)), os.path.normcase(
            os.path.realpath(folder)
        )
        return os.path.commonpath([a, b]) == b
    except ValueError:  # different drives
        return False


def sandbox_problem(env=None) -> Optional[str]:
    """Why this is not a sandbox, or None: each of POWERTRADER_HOME, APPDATA and
    LOCALAPPDATA set and outside the real user folders (a scratch folder under the
    system's temp folder counts as outside), and a keyring that fails."""
    env = os.environ if env is None else env
    profile = env.get("USERPROFILE") or os.path.expanduser("~")
    roaming = os.path.join(profile, "AppData", "Roaming")
    local = os.path.join(profile, "AppData", "Local")
    temp = tempfile.gettempdir()
    for name in ("POWERTRADER_HOME", "APPDATA", "LOCALAPPDATA"):
        value = env.get(name)
        if not value:
            return f"{name} is not set"
        if _under(value, roaming) or (_under(value, local) and not _under(value, temp)):
            return f"{name} points at the real user folders ({value})"
    if env.get("PYTHON_KEYRING_BACKEND") != KEYRING:
        return f"PYTHON_KEYRING_BACKEND is not {KEYRING}"
    return None


def _setup(app: str) -> None:
    problem = sandbox_problem()
    if problem:
        raise SystemExit(f"{problem}: run this only inside a sandbox")
    if app not in sys.path:
        sys.path.insert(0, app)


def _plain(x):
    """JSON-safe: arrays to lists, numpy numbers to Python ones, NaN to None."""
    import numpy as np

    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_plain(v) for v in x]
    if isinstance(x, np.ndarray):
        return [_plain(v) for v in x.tolist()]
    if isinstance(x, (np.floating, float)):
        v = float(x)
        return None if not math.isfinite(v) else v
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.bool_):
        return bool(x)
    return x


def _write(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(_plain(data), f, indent=1, sort_keys=True, ensure_ascii=False)
        f.write("\n")


def _sha_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _repo() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# --- freezing ------------------------------------------------------------------------------


def read_rate(path: str) -> Dict[str, Any]:
    """The rate file's record, with its SHA-256; refused unless it was verified."""
    with open(path, encoding="utf-8") as f:
        rate = json.load(f)
    value = float(rate.get("gbp_usd") or 0)
    if not value > 0:
        raise SystemExit(f"{path}: no GBP-to-USD rate")
    if not (rate.get("verification") or {}).get("agrees"):
        raise SystemExit(f"{path}: the rate was not checked against a second source")
    return {**rate, "file_sha256": _sha_file(path)}


def _fees_read(coins: List[str]) -> Dict[str, Any]:
    """What the exchange layer gives as each coin's fee rates (no credentials are
    read): shown beside the declared 0.50%."""
    from pt_multi_exchange import market_exchanges

    out: Dict[str, Any] = {}
    try:
        manager = market_exchanges()
    except Exception as exc:  # recorded, never silently
        return {"error": str(exc)}
    for coin in coins:
        try:
            got = manager.trading_fees(f"{coin}-USD")
        except Exception as exc:
            out[coin] = {"error": str(exc)}
            continue
        if got is None:
            out[coin] = {"error": "no exchange gave fee rates"}
            continue
        fees = got.value
        out[coin] = {
            "exchange": got.exchange,
            "pair": got.pair,
            "taker": float(fees.taker),
            "maker": float(fees.maker),
            "source": fees.source,
        }
    return out


def _sandbox_state() -> Dict[str, Any]:
    """The sandbox's own trial log and ledger at the freeze; refused when either holds
    an SR1-E2 trial already."""
    from research_engine import ledger
    from strategy_lab import e2, experiment

    lines = experiment.trials()
    entries = ledger.entries()
    if any(str(x.get("trial", "")).startswith(e2.EXPERIMENT_ID + "/") for x in lines):
        raise SystemExit("the sandbox's trial log already holds an SR1-E2 trial")
    if any(e.get("experiment_id") == e2.EXPERIMENT_ID for e in entries):
        raise SystemExit("the sandbox's ledger already holds an SR1-E2 trial")
    path = experiment.trials_path()
    return {
        "trial_log_lines": len(lines),
        "trial_log_sha256": _sha_file(path) if os.path.exists(path) else None,
        "ledger_entries": len(entries),
    }


def _second(order: List[str]):
    return order[1] if len(order) > 1 else None


def _load(order: List[str], second: Optional[str]):
    from strategy_lab import e2

    loader = e2.development_loader()
    second_loader = (
        e2.development_loader(exchanges=[second]) if second is not None else None
    )
    return e2.load_data(loader, second_loader, second)


def _market(data, order):
    from strategy_lab import e2

    second = None
    if data.second_exchange is not None:
        second = {
            "exchange": data.second_exchange,
            "coins": sorted(data.second.frames),
            "left_out": dict(data.second_left_out),
            "served_by": e2.served_by(data.second),
        }
    return {
        "series_sha256": data.series_sha256(),
        "coins_kept": sorted(data.universe.frames),
        "left_out": dict(data.left_out),
        "exchange_order": list(order),
        "listed_by_2021": e2.listed_by_2021(data.universe),
        "served_by": e2.served_by(data.universe),
        "second": second,
    }


def freeze(out: str, rate_path: str, venue_path=None, exposures_path=None):
    from strategy_lab import e1, e2, experiment
    from strategy_lab.venue import venue_rules

    rate = read_rate(rate_path)
    exposures = e2.exposures_record(
        exposures_path or os.path.join(_repo(), *e2.EXPOSURE_LOG.split("/"))
    )
    state = _sandbox_state()
    order = list(e1.settings_exchanges())
    log(f"candles (Settings order {order})")
    data = _load(order, _second(order))
    market = _market(data, order)
    log(f"{len(market['series_sha256'])} series; coins {market['coins_kept']}")
    log(f"served by {sorted(set(market['served_by'].values()))}")
    if venue_path:
        with open(venue_path, encoding="utf-8") as f:
            venue = json.load(f)
        venue["source"] = (
            f"{os.path.basename(venue_path)} (SHA-256 {_sha_file(venue_path)})"
        )
    else:
        log("venue rules")
        venue = venue_rules(market["coins_kept"]).as_record()
        venue["read_at"] = datetime.now(timezone.utc).isoformat()
        venue["source"] = "the exchange layer's public product data, primary first"
    log("fee rates from the exchange layer")
    fees = _fees_read(market["coins_kept"])
    record = e2.declaration(
        rate,
        venue,
        market["series_sha256"],
        market["coins_kept"],
        market["left_out"],
        market["exchange_order"],
        market["listed_by_2021"],
        market["served_by"],
        exposures,
        market["second"],
        fees,
    )
    record["earlier_exposures"]["sandbox_at_freeze"] = state
    frozen = experiment.freeze(e2.EXPERIMENT_ID, record)
    _write(os.path.join(out, "experiment.json"), frozen)
    log(f"frozen {e2.EXPERIMENT_ID} {frozen['sha256']} at {frozen['frozen_at']}")
    return frozen


# --- running ---------------------------------------------------------------------------------


def _finish(out: str, record, result, started: float) -> None:
    from strategy_lab import e2, evidence

    result["seconds"] = round(time.time() - started, 1)
    _write(os.path.join(out, "results.json"), result)
    from sr1_e2_report import report

    text = report(record, _plain(result))
    with open(
        os.path.join(out, "SR1-E2-REPORT-dev.md"), "w", encoding="utf-8", newline="\n"
    ) as f:
        f.write(text)
    sealed = evidence.write_results(e2.EXPERIMENT_ID, e2.evidence_lines(result))
    _write(os.path.join(out, "evidence.json"), sealed)
    log(f"done in {result['seconds']} s")


def run(out: str) -> None:
    from strategy_lab import e1, e2, experiment

    record = experiment.verify(e2.EXPERIMENT_ID)
    log(f"verified {e2.EXPERIMENT_ID} {record['sha256']}")
    if list(e1.settings_exchanges()) != list(record["market"]["exchange_order"]):
        raise SystemExit("the exchanges in Settings are not the frozen order")
    started = time.time()
    second = (record["market"].get("second_exchange") or {}).get("exchange")
    data = _load(record["market"]["exchange_order"], second)
    experiment.verify(e2.EXPERIMENT_ID, data.series_sha256())
    log("candles verified")
    result = e2.evaluate(record, data, progress=log)
    _finish(out, record, result, started)


# --- the rehearsal (synthetic) -----------------------------------------------------------------

# each coin's first synthetic bar and the exchange whose "cache" holds it
_LISTED = {
    "BTC": ("2020-01-01", "coinbase"), "ETH": ("2020-01-01", "coinbase"),
    "XRP": ("2023-07-14", "coinbase"), "BNB": ("2020-01-01", "kucoin"),
    "DOGE": ("2021-06-04", "coinbase"), "SOL": ("2021-06-18", "coinbase"),
    "ZEC": ("2020-12-09", "coinbase"), "DASH": ("2020-01-01", "coinbase"),
    "HYPE": ("2024-12-05", "kucoin"),
}  # fmt: skip
_SECOND = {"BTC", "ETH", "DOGE", "SOL"}  # the synthetic second exchange's coins


def _synthetic():
    """Daily bars per coin and exchange: random walks with slow trends, so the members
    trade; the second exchange's are the first's with small differences."""
    import numpy as np
    import pandas as pd

    from strategy_lab import e2

    frames = {}
    for k, (coin, (listed, exchange)) in enumerate(sorted(_LISTED.items())):
        start = pd.Timestamp(listed, tz="UTC")
        days = int((e2.DEV_END - start) / pd.Timedelta(days=1))
        rng = np.random.default_rng(2000 + k)
        trend = np.repeat(rng.normal(0.0, 0.006, days // 60 + 1), 60)[:days]
        r = trend + rng.normal(0.0005, 0.035, days)
        close = 40.0 * (k + 1) * np.exp(np.cumsum(r))
        open_ = np.r_[close[0], close[:-1]]
        wick = np.abs(rng.normal(0, 0.012, days))
        frame = pd.DataFrame(
            {
                "open_time": pd.date_range(start, periods=days, freq="D"),
                "open": open_,
                "high": np.maximum(open_, close) * (1 + wick),
                "low": np.minimum(open_, close) * (1 - wick),
                "close": close,
                "volume": rng.uniform(10, 100, days),
            }
        )
        frames[(coin, exchange)] = frame
        if coin in _SECOND:
            other = frame.copy()
            jitter = 1 + rng.normal(0, 0.001, days)
            for col in ("open", "high", "low", "close"):
                other[col] = other[col] * jitter
            other["high"] = other[["open", "high", "close"]].max(axis=1)
            other["low"] = other[["open", "low", "close"]].min(axis=1)
            frames[(coin, "kraken")] = other
    return frames


def rehearse(out: str) -> None:
    import pandas as pd

    from strategy_lab import e2, experiment

    if "rehearsal" not in os.environ["POWERTRADER_HOME"].lower():
        raise SystemExit(
            "rehearse only in a sandbox whose folder name holds 'rehearsal'"
        )
    frames = _synthetic()
    order = ["coinbase", "kraken", "kucoin"]

    def base_for(names):
        def base(symbol, tf, a, b, cache_dir=None, offline=True):
            coin = symbol.split("-")[0]
            for name in names:
                f = frames.get((coin, name))
                if f is not None and len(f) and f["open_time"].iloc[0] <= a:
                    g = f[(f["open_time"] >= a) & (f["open_time"] < b)]
                    g = g.reset_index(drop=True)
                    g.attrs = {"exchange": name, "pair": symbol}
                    return g
            raise RuntimeError(f"no cache covers {symbol} from {a}")

        return base

    def first_for(names):
        def first(symbol, tf):
            coin = symbol.split("-")[0]
            for name in names:
                f = frames.get((coin, name))
                if f is not None and len(f):
                    return pd.Timestamp(f["open_time"].iloc[0])
            return None

        return first

    started = time.time()
    loader = e2.development_loader(base_for(order), first_for(order))
    second_loader = e2.development_loader(base_for(["kraken"]), first_for(["kraken"]))
    data = e2.load_data(loader, second_loader, "kraken")
    market = _market(data, order)
    exposures = e2.exposures_record(os.path.join(_repo(), *e2.EXPOSURE_LOG.split("/")))
    kept = market["coins_kept"]
    record = e2.declaration(
        {"gbp_usd": 1.30, "source": "synthetic (rehearsal)"},
        {
            "minimum_usd": {c: 1.0 for c in kept},
            "base_increment": {c: 1e-8 for c in kept},
            "unknown": {},
            "read_at": "synthetic",
            "source": "synthetic (rehearsal)",
        },
        market["series_sha256"],
        kept,
        market["left_out"],
        order,
        market["listed_by_2021"],
        market["served_by"],
        exposures,
        market["second"],
        {c: {"taker": 0.012, "source": "synthetic"} for c in kept},
    )
    record["earlier_exposures"]["sandbox_at_freeze"] = _sandbox_state()
    frozen = experiment.freeze(e2.EXPERIMENT_ID, record)
    _write(os.path.join(out, "experiment.json"), frozen)
    log(f"rehearsal frozen in {time.time() - started:.0f} s")
    result = e2.evaluate(frozen, data, progress=log)
    result["rehearsal"] = "synthetic candles, venue rules, fees and rate"
    _finish(out, frozen, result, started)


def main(argv: List[str]) -> int:
    app, out, step = argv[1], argv[2], argv[3]
    _setup(app)
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(out, exist_ok=True)
    if step == "freeze":
        if len(argv) < 5:
            raise SystemExit("freeze needs the rate file")
        rest = argv[5:]
        opts = dict(zip(rest[::2], rest[1::2]))
        unknown = sorted(set(opts) - {"--venue", "--exposures"})
        if unknown or len(rest) % 2:
            raise SystemExit(f"unknown options {unknown or rest}")
        freeze(out, argv[4], opts.get("--venue"), opts.get("--exposures"))
    elif step == "run":
        run(out)
    elif step == "rehearse":
        rehearse(out)
    else:
        raise SystemExit(f"unknown step {step!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
