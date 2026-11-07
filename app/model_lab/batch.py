"""
Batches (FDS-MH-001 section 5.8): freeze, run, the trial log, the results and the
report.

**Freeze** (``freeze``). A batch is its contestants, coins, window, trade rules, fees,
seeds, number of draws, fold and lockbox dates and pass rule. It is frozen and saved
(``batch.json``) before any of its results exist, with each series' exchange, pair and
SHA-256, the SHA-256 of the code it runs, and the record's own SHA-256 (over its
canonical JSON without that field).

**Run** (``run``). A batch whose file, code or candles are not the ones it was frozen
with is refused. The series are cut at the lockbox's start, so nothing in a run reads
the lockbox. Each coin's trade table is replayed once (``replay``), every contestant
decides walk-forward (``walkforward``), and each tested contestant is scored against
B draws of R1 and of R2 (``baselines``). A run can be stopped: the batch keeps its
frozen record, its status says it was stopped, and the trials it scored stay logged.
The same batch on the same cached candles gives the same results.

**Scores** are over a contestant's trades on every coin and fold. Return per day held
after fees (profit over capital-days) decides; the rest is shown: total profit, mean
return per trade, worst drawdown, trades and time in a trade, by coin, in rising and
falling markets (BTC's close above or below its close 90 days earlier, at the entry
hour), and at half and double the fee rate (the contestant's own schedule, replayed).

**p-values and the pass rule** (``stats``). p1 and p2 are the contestant's p-values
against R1 and R2; R2 is compared with the contestant's trades on the coins that take
part in it. Its p is the larger, because it must beat both (a batch with no coin long
enough for R2 gives p2 = 1). Benjamini-Hochberg at q = 0.10 over the batch's K p-values
is the screen, shown only. A finalist passes Holm at 5% and every one of:

* total profit after fees above 0, and at least 100 trades pooled;
* worst drawdown no worse than R1's median;
* a trained or pattern contestant: return per day held and total profit both above the
  batch's best untrained rule's, on the hours both cover;
* the batch's probability of backtest overfitting at most 0.5 (16 time blocks).

**Verdicts.** "Worse than random entries" when its lower-tail p (against both) is at
most 0.05/K; a finalist "Passed; final check not run" (the lockbox is opened later, once
per finalist), or, when its lockbox months were seen before, "Passed; its lockbox was
seen before, so a final check would not be unseen evidence"; "Better than random entries
here, not by enough to pass" past the screen; "Too few trades to tell" when the smallest
detectable edge (at the Holm level, 80% power, the larger spread of R1 and R2) is above
half of R1's median; otherwise "No better than random entries".

**Earlier looks** (``catalogue.LOOKS``). A batch records, when frozen, each contestant's
earlier looks and those that cover any of its lockbox (``lockbox_seen``). A contestant
with any is never given "Beats random entries".

**Amendment 1.** A batch file records ``spec_version`` (the version its batch was
declared under: "1" for batch 1, "1.1" otherwise), ``declared`` (``catalogue.DECLARED``)
and ``libraries``; a batch with a trained contestant is refused when scikit-learn's
version has changed. A trial line carries ``kind`` ("trading" here; a line without one is
"trading"). The draws are also reported as 10 runs of consecutive draws (``runs.json``),
which changes no p-value. Trained contestants' probabilities are saved apart
(``probabilities/<key>.npz``); the placebo's variants 2 to 5 are fitted for them only.
None of this changes ``results.json`` for a contestant that existed before.

**Files.** Under ``<data dir>/model_lab`` (``pt_paths.data_dir``): ``trials.jsonl``, one
line per trial scored, and ``batches/<id>/`` with ``batch.json``, ``status.json``,
``results.json``, ``runs.json``, ``report.md`` and ``probabilities/``.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import entry_gate
import model_gate
from model_lab import baselines, catalogue, stats, walkforward
from model_lab import series as series_mod
from model_lab.replay import Trade, TradeTable, schedule
from model_lab.series import DAY_S, Series, SeriesError, epoch, iso
from model_lab.walkforward import (
    Calendar,
    Decisions,
    LabData,
    Stopped,
    Stream,
    decide,
    make_calendar,
    make_stream,
)

DRAWS = 10_000  # B
SEEDS = {"r1": 300000, "r2": 400000, "fits": 0}
PASS_RULE = {
    "screen_q": 0.10,
    "holm_alpha": 0.05,
    "min_trades": 100,
    "pbo_max": 0.5,
    "pbo_blocks": 16,
    "too_few": 0.5,
    "power": 0.8,
}
NEURAL_DCA_DRAWS = 1000  # the pattern model's neural DCA line: as many as the gate's
MARKET_DAYS = 90  # rising or falling: BTC's close against its close this long before
CONTEXT = "BTC"
CODE = (
    "model_gate.py",
    "entry_gate.py",
    "pt_pattern_trainer.py",
    "pattern_model.py",
    "position_sizing.py",
    "market_data/resample.py",
)

VERDICTS = {
    "beats": "Beats random entries",
    "passed": "Passed; final check not run",
    "passed_seen": "Passed; its lockbox was seen before, so a final check would not be "
    "unseen evidence",
    "screen": "Better than random entries here, not by enough to pass",
    "no_better": "No better than random entries",
    "too_few": "Too few trades to tell: this test could only see an edge above {edge}",
    "worse": "Worse than random entries",
    "no_entries": "Made no entries",
    "reference": "Reference only, not tested",
    "forecast_only": "Forecast scores only, not tested here",
}
TRIAL_KINDS = ("trading", "forecast", "decision", "calibration", "sizing")
RUNS = 10  # amendment 1: the draws are also reported as 10 runs


class BatchError(RuntimeError):
    """A batch cannot be frozen or run."""


# --- files ------------------------------------------------------------------------------


def lab_dir() -> str:
    import pt_paths

    return os.path.join(pt_paths.data_dir(), "model_lab")


def batch_dir(batch_id: str) -> str:
    return os.path.join(lab_dir(), "batches", batch_id)


def trials_path() -> str:
    return os.path.join(lab_dir(), "trials.jsonl")


def _canonical(record: Mapping[str, Any]) -> bytes:
    return json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _seal(record: Dict[str, Any]) -> Dict[str, Any]:
    body = {k: v for k, v in record.items() if k != "sha256"}
    return {**body, "sha256": hashlib.sha256(_canonical(body)).hexdigest()}


def _write_json(path: str, data: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def _write_text(path: str, text: str) -> None:
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


def code_hashes() -> Dict[str, str]:
    """SHA-256 (LF line endings) of the code a batch runs: this package and what it
    replays and fits with."""
    app = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    names = sorted(
        os.path.relpath(p, app).replace("\\", "/")
        for p in glob.glob(os.path.join(app, "model_lab", "*.py"))
    ) + list(CODE)
    out = {}
    for name in names:
        with open(os.path.join(app, name), "rb") as f:
            out[name] = hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()
    return out


def read_batch(batch_id: str) -> Dict[str, Any]:
    """The frozen record; BatchError when it is missing or has changed."""
    path = os.path.join(batch_dir(batch_id), "batch.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError) as exc:
        raise BatchError(f"batch {batch_id}: cannot read its file ({exc})") from exc
    if not isinstance(record, dict) or _seal(record).get("sha256") != record.get(
        "sha256"
    ):
        raise BatchError(f"batch {batch_id}: its file has changed since it was frozen")
    return record


def write_status(batch_id: str, state: str, **extra: Any) -> Dict[str, Any]:
    status = {"batch": batch_id, "state": state, **extra}
    _write_json(os.path.join(batch_dir(batch_id), "status.json"), status)
    return status


def read_status(batch_id: str) -> Optional[Dict[str, Any]]:
    try:
        with open(
            os.path.join(batch_dir(batch_id), "status.json"), encoding="utf-8"
        ) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def read_results(batch_id: str) -> Optional[Dict[str, Any]]:
    try:
        with open(
            os.path.join(batch_dir(batch_id), "results.json"), encoding="utf-8"
        ) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def batch_ids() -> List[str]:
    folder = os.path.join(lab_dir(), "batches")
    try:
        return sorted(
            n for n in os.listdir(folder) if os.path.isdir(os.path.join(folder, n))
        )
    except OSError:
        return []


def trial_count() -> int:
    """The number of distinct trials logged."""
    return sum(trial_counts().values())


def trial_counts() -> Dict[str, int]:
    """The number of distinct trials logged, by kind (amendment 1): a line without a
    ``kind`` is a "trading" trial."""
    seen: Dict[str, set] = {}
    try:
        with open(trials_path(), "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line)
                    kind = entry.get("kind") or "trading"
                    seen.setdefault(kind, set()).add(entry["trial"])
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
    except OSError:
        return {}
    return {kind: len(trials) for kind, trials in seen.items()}


def log_trial(line: Mapping[str, Any]) -> None:
    """Log one scored analysis as a trial (amendment 1): FDS-SIG-004's forecast,
    decision, calibration and sizing analyses use this too."""
    kind = line.get("kind") or "trading"
    if kind not in TRIAL_KINDS:
        raise ValueError(f"unknown kind of trial {kind!r}")
    _log_trial({**line, "kind": kind})


def libraries() -> Dict[str, Optional[str]]:
    """The versions of the libraries a batch fits with."""
    out: Dict[str, Optional[str]] = {}
    for name, module in (
        ("numpy", "numpy"),
        ("pandas", "pandas"),
        ("scikit-learn", "sklearn"),
    ):
        try:
            out[name] = __import__(module).__version__
        except ImportError:
            out[name] = None
    return out


def _log_trial(line: Dict[str, Any]) -> None:
    os.makedirs(lab_dir(), exist_ok=True)
    with open(trials_path(), "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(line, sort_keys=True, ensure_ascii=False) + "\n")


# --- freeze -----------------------------------------------------------------------------


def _not_trading(coin: str) -> Optional[str]:
    """Why the coin's market is recorded as not trading (market_status.json in its
    folder), or None."""
    import pt_paths
    from market_data import listing

    try:
        with open(pt_paths.gui_settings_file(), "r", encoding="utf-8") as f:
            configured = (json.load(f) or {}).get("main_neural_dir")
    except (OSError, ValueError, AttributeError):
        configured = None
    root = pt_paths.neural_dir(configured)
    folder = root if coin == "BTC" else os.path.join(root, coin)
    return listing.not_trading_reason(folder)


def _new_id(now_s: int) -> str:
    base = datetime.fromtimestamp(now_s, tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    candidate, n = base, 1
    while os.path.exists(batch_dir(candidate)):
        n += 1
        candidate = f"{base}-{n}"
    return candidate


def freeze(
    coins: Sequence[str],
    start,
    contestants: Sequence[str],
    end=None,
    fees: Optional[Any] = None,
    rules: Optional[model_gate.TradeRules] = None,
    cache_dir: Optional[str] = None,
    offline: bool = False,
    manager=None,
    exchanges: Optional[Sequence[str]] = None,
    draws: int = DRAWS,
    seeds: Optional[Mapping[str, int]] = None,
    months: Tuple[int, int, int] = (
        walkforward.WARMUP_MONTHS,
        walkforward.FOLD_MONTHS,
        walkforward.LOCKBOX_MONTHS,
    ),
    min_shift_days: int = baselines.MIN_SHIFT_DAYS,
    why: Optional[Mapping[str, str]] = None,
    status_of: Optional[Callable[[str], Optional[str]]] = None,
    now=None,
    declared: Optional[str] = None,
) -> str:
    """Freeze a batch and save it; its id. ``fees`` is a mapping or a function from a
    coin to its ``entry_gate.Fees`` (default ``entry_gate.trading_fees``); ``why`` says
    why each coin is in it; ``end`` defaults to the last closed hour. ``declared`` names
    a declared batch (``catalogue.DECLARED``): its contestants must be exactly that
    batch's, and its spec version is recorded (amendment 1)."""
    if declared is not None:
        if declared not in catalogue.DECLARED:
            raise BatchError(f"no declared batch {declared!r}")
        version, members = catalogue.DECLARED[declared]
        if list(contestants) != list(members):
            raise BatchError(
                f"batch {declared}'s contestants are declared: " + ", ".join(members)
            )
    else:
        version = catalogue.SPEC_VERSION
    coins = [str(c).upper() for c in coins]
    if not coins:
        raise BatchError("a batch needs at least one coin")
    if len(set(coins)) != len(coins):
        raise BatchError("a coin is listed twice")
    known = catalogue.by_key()
    chosen = []
    for key in contestants:
        if key not in known:
            raise BatchError(f"no contestant {key!r} in the catalogue")
        if key in chosen:
            raise BatchError(f"contestant {key} is listed twice")
        chosen.append(key)
    if not chosen:
        raise BatchError("a batch needs at least one contestant")
    now_s = epoch(now) if now is not None else int(time.time())
    end_s = (epoch(end) if end is not None else now_s) // 3600 * 3600
    try:
        cal = make_calendar(start, end_s, *months)
    except ValueError as exc:
        raise BatchError(str(exc)) from exc
    loaded: Dict[str, Series] = {}
    for coin in coins + ([CONTEXT] if CONTEXT not in coins else []):
        try:
            loaded[coin] = series_mod.load(
                coin, cal.start_s, cal.end_s, cache_dir, offline, manager, exchanges
            )
        except SeriesError as exc:
            raise BatchError(f"no candles for {coin}: {exc}") from exc
    if fees is None:
        fee_of: Callable[[str], Any] = entry_gate.trading_fees
    elif callable(fees):
        fee_of = fees
    else:
        fee_of = lambda c: fees.get(c)  # noqa: E731
    fee_record = {}
    for coin in coins:
        f = fee_of(coin)
        if f is None:
            raise BatchError(f"no fee rate for {coin}: no exchange states one")
        fee_record[coin] = f.to_dict()
    rules = rules if rules is not None else model_gate.read_trade_rules()
    status_of = status_of or _not_trading
    series_record = {}
    for coin, s in loaded.items():
        entry = s.to_dict()
        if coin not in coins:
            entry["context"] = "read for BTC's figures only"
        else:
            reason = (why or {}).get(coin) or "chosen for the batch"
            try:
                stopped = status_of(coin)
            except Exception:
                stopped = None
            if stopped:
                reason += (
                    f"; its market is recorded as not trading ({stopped}), and its "
                    "history is still served"
                )
            entry["why"] = reason
        series_record[coin] = entry
    batch_id = _new_id(now_s)
    record = _seal(
        {
            "id": batch_id,
            "frozen_at": iso(now_s),
            "coins": coins,
            "contestants": [
                {
                    **known[k].to_dict(),
                    "looks": [look.to_dict() for look in catalogue.looks(k)],
                    "lockbox_seen": [
                        look.to_dict() for look in catalogue.seen_in(k, *cal.lockbox)
                    ],
                }
                for k in chosen
            ],
            "calendar": cal.to_dict(),
            "series": series_record,
            "rules": rules.to_dict(),
            "neural_dca": "off for every contestant; the pattern model is also shown "
            "with it on",
            "fees": fee_record,
            "seeds": dict(seeds or SEEDS),
            "draws": int(draws),
            "min_shift_days": int(min_shift_days),
            "pass_rule": dict(PASS_RULE),
            "cache_dir": cache_dir,
            "offline": bool(offline),
            "code": code_hashes(),
            "declared": declared,
            "spec_version": version,
            "libraries": libraries(),
        }
    )
    _write_json(os.path.join(batch_dir(batch_id), "batch.json"), record)
    write_status(batch_id, "frozen")
    return batch_id


# --- scores -----------------------------------------------------------------------------


def figures(trades: Sequence[Trade]) -> Dict[str, Any]:
    s = entry_gate.score(trades)
    return {
        "trades": s.entries,
        "per_day": s.per_day,
        "profit": sum(t.net for t in trades) if trades else 0.0,
        "mean_return": s.mean_return,
        "capital_return": s.capital_return,
        "drawdown": s.drawdown,
        "hit_rate": s.hit_rate,
    }


def baseline_summary(b: Optional[entry_gate.Baseline], value: Optional[float]):
    if b is None:
        return None
    entries = sorted(b.entries)
    return {
        "kind": b.kind,
        "runs": b.runs,
        "seed": b.seed,
        "median": b.median(),
        "spread": b.spread(),
        "at_95": b.at(95.0),
        "median_drawdown": b.median_drawdown(),
        "rank": None if value is None else b.rank(value),
        "p": None if value is None else stats.p_upper(value, b.values),
        "p_lower": None if value is None else stats.p_lower(value, b.values),
        "entries_median": stats.median(entries),
        "entries_low": entries[0],
        "entries_high": entries[-1],
    }


def _hours_in_trade(plans, streams) -> Dict[str, Any]:
    held = 0
    total = 0
    for p in plans:
        s = streams[p.coin]
        if p.start >= len(s):
            continue
        total += int(s.close_s[-1] - s.close_s[p.start])
        for i, t in p.entries:
            held += int(s.close_s[t.end] - s.close_s[i])
    return {"share": (held / total) if total else None, "stream_days": total / DAY_S}


def _markets(plans, streams, btc: Series) -> Dict[str, Any]:
    rising: List[Trade] = []
    falling: List[Trade] = []
    for p in plans:
        s = streams[p.coin]
        for i, t in p.entries:
            at = int(s.close_s[i])
            now, then = btc.close_at(at), btc.close_at(at - MARKET_DAYS * DAY_S)
            if now is None or then is None:
                continue
            (rising if now > then else falling).append(t)
    return {"rising": figures(rising), "falling": figures(falling)}


def _scaled(fees: entry_gate.Fees, factor: float) -> entry_gate.Fees:
    return entry_gate.Fees(
        fees.rate * factor, fees.order_type, fees.exchange, fees.source, fees.slippage
    )


def _on_shared(a: Mapping[str, Decisions], b: Mapping[str, Decisions], tables):
    """Both contestants' trades on the hours both cover: on each coin both have, from
    the later of their first positions."""
    ta: List[Trade] = []
    tb: List[Trade] = []
    for coin in sorted(set(a) & set(b)):
        start = max(a[coin].join, b[coin].join)
        if start >= len(tables[coin]):
            continue
        ta += [t for _i, t in schedule(a[coin].ones(), tables[coin], start)]
        tb += [t for _i, t in schedule(b[coin].ones(), tables[coin], start)]
    return figures(ta), figures(tb)


def verdict_code(
    worse: bool, finalist: bool, lockbox_seen: bool, screen: bool, too_few: bool
) -> str:
    """A tested contestant's verdict (the module docstring), before its final check.
    One whose lockbox months were seen before is never a plain finalist."""
    if worse:
        return "worse"
    if finalist:
        return "passed_seen" if lockbox_seen else "passed"
    if screen:
        return "screen"
    return "too_few" if too_few else "no_better"


def verdict_text(code: str, edge: Optional[float] = None) -> str:
    text = VERDICTS[code]
    if code == "too_few":
        text = text.format(edge=f"{edge:+.3%} a day")
    return text


# --- run --------------------------------------------------------------------------------


def run(
    batch_id: str,
    progress: Optional[Callable[[str, int, int], None]] = None,
    stop: Optional[Callable[[], bool]] = None,
    manager=None,
) -> Optional[Dict[str, Any]]:
    """Run a frozen batch; its results, or None when it was stopped. Raises BatchError
    when the batch is refused."""
    record = read_batch(batch_id)
    if record.get("code") != code_hashes():
        raise BatchError(
            f"batch {batch_id}: the code it runs has changed since it was frozen; "
            "freeze a new batch"
        )
    frozen_libraries = record.get("libraries")
    trained = any(c.get("family") in ("linear", "trees") for c in record["contestants"])
    if (
        frozen_libraries
        and trained
        and frozen_libraries.get("scikit-learn") != libraries().get("scikit-learn")
    ):
        raise BatchError(
            f"batch {batch_id}: scikit-learn has changed since it was frozen; freeze a "
            "new batch"
        )
    started = time.time()
    seconds: Dict[str, float] = {}
    write_status(batch_id, "running", started_at=iso(int(started)))
    try:
        results, runs = _run(record, progress, stop, manager, seconds)
    except Stopped:
        write_status(
            batch_id,
            "stopped",
            started_at=iso(int(started)),
            stopped_at=iso(int(time.time())),
            seconds=seconds,
        )
        return None
    except BatchError as exc:
        write_status(batch_id, "refused", error=str(exc))
        raise
    except Exception as exc:
        write_status(batch_id, "failed", error=f"{type(exc).__name__}: {exc}")
        raise
    folder = batch_dir(batch_id)
    _write_json(os.path.join(folder, "results.json"), results)
    if runs:
        _write_json(os.path.join(folder, "runs.json"), runs)
    _write_text(os.path.join(folder, "report.md"), report(record, results, runs))
    write_status(
        batch_id,
        "done",
        started_at=iso(int(started)),
        finished_at=iso(int(time.time())),
        seconds={k: round(v, 1) for k, v in seconds.items()},
    )
    return results


def _timed(seconds: Dict[str, float], name: str, t0: float) -> None:
    seconds[name] = seconds.get(name, 0.0) + time.time() - t0


def _run(record, progress, stop, manager, seconds) -> Dict[str, Any]:
    batch_id = record["id"]
    cal = Calendar.from_dict(record["calendar"])
    lock = cal.lockbox[0]
    coins = list(record["coins"])
    rules = model_gate.trade_rules(record["rules"])
    seeds = record["seeds"]
    draws = int(record["draws"])
    rule = record["pass_rule"]
    min_shift = baselines.min_shift_hours(record["min_shift_days"])

    t0 = time.time()
    full: Dict[str, Series] = {}
    names = sorted(record["series"])
    for n, coin in enumerate(names):
        if stop is not None and stop():
            raise Stopped()
        try:
            full[coin] = series_mod.load_frozen(
                record["series"][coin],
                cal.end_s,
                record.get("cache_dir"),
                bool(record.get("offline")),
                manager,
            )
        except SeriesError as exc:
            raise BatchError(f"batch {batch_id}: {exc}") from exc
        if progress is not None:
            progress("series", n + 1, len(names))
    _timed(seconds, "series", t0)
    # the lockbox is not read: every series ends at its start
    data = LabData(
        {c: s.cut(lock) for c, s in full.items()},
        rules,
        cal.start_s,
        record.get("cache_dir"),
        bool(record.get("offline")),
        int(seeds["fits"]),
        CONTEXT,
    )
    # a coin listed after the lockbox starts has an empty stream: it never joins
    streams: Dict[str, Stream] = {
        c: make_stream(data.series[c], cal, full[c].first_open_s) for c in coins
    }
    fees = {c: entry_gate.Fees.from_dict(record["fees"][c]) for c in coins}
    data.fees = dict(fees)  # the trained contestants' targets and pooled coins

    t0 = time.time()
    tables: Dict[str, TradeTable] = {}
    for n, coin in enumerate(coins):
        s = streams[coin]
        tables[coin] = TradeTable(s.close_s, s.price, rules, fees[coin])
        tables[coin].fill(stop)
        if stop is not None and stop():
            raise Stopped()
        if progress is not None:
            progress("trades", n + 1, len(coins))
    _timed(seconds, "trade_cache", t0)

    known = catalogue.by_key()
    contestants = [known[c["key"]] for c in record["contestants"]]
    tested = [c for c in contestants if c.tested]
    k = len(tested)
    decisions: Dict[str, Dict[str, Decisions]] = {}
    out: Dict[str, Dict[str, Any]] = {}
    runs: Dict[str, Any] = {}
    for n, contestant in enumerate(contestants):
        t0 = time.time()
        decisions[contestant.key] = decide(
            contestant, data, cal, streams, progress, stop
        )
        _timed(seconds, "fits" if contestant.trained else "rules", t0)
        frozen = next(c for c in record["contestants"] if c["key"] == contestant.key)
        if getattr(contestant, "forecast_only", False):
            # the placebo's variants 2 to 5: fitted for their probabilities only
            d = decisions[contestant.key]
            out[contestant.key] = {
                **contestant.to_dict(),
                "verdict": "forecast_only",
                "verdict_text": verdict_text("forecast_only"),
                "fits": {c: d[c].fits for c in sorted(d) if d[c].fits},
                "looks": frozen["looks"],
                "lockbox_seen": frozen["lockbox_seen"],
            }
            if progress is not None:
                progress("contestants", n + 1, len(contestants))
            continue
        t0 = time.time()
        out[contestant.key] = _score(
            contestant,
            decisions[contestant.key],
            tables,
            streams,
            data,
            fees,
            rules,
            seeds,
            draws,
            min_shift,
            k,
            rule,
            stop,
        )
        _timed(seconds, "draws", t0)
        split = out[contestant.key].pop("_runs", None)
        if split:
            runs[contestant.key] = split
        out[contestant.key]["looks"] = frozen["looks"]
        out[contestant.key]["lockbox_seen"] = frozen["lockbox_seen"]
        if contestant.tested:
            r = out[contestant.key]
            log_trial(
                {
                    "trial": f"{batch_id}/{contestant.key}",
                    "kind": "trading",
                    "batch": batch_id,
                    "batch_sha256": record["sha256"],
                    "contestant": contestant.key,
                    "family": contestant.family,
                    "params": contestant.to_dict()["params"],
                    "trades": r["score"]["trades"],
                    "per_day": r["score"]["per_day"],
                    "p_r1": r["p_r1"],
                    "p_r2": r["p_r2"],
                    "p": r["p"],
                    "logged_at": iso(int(time.time())),
                }
            )
        if progress is not None:
            progress("contestants", n + 1, len(contestants))

    t0 = time.time()
    batch = _judge(contestants, decisions, out, tables, streams, rule, cal)
    _timed(seconds, "judge", t0)
    results = {
        "batch": batch_id,
        "batch_sha256": record["sha256"],
        "k": k,
        **batch,
        "contestants": out,
        "order": [c.key for c in contestants],
        "streams": {
            c: {
                "hours": len(streams[c]),
                "first": iso(int(streams[c].close_s[0])) if len(streams[c]) else None,
                "last": iso(int(streams[c].close_s[-1])) if len(streams[c]) else None,
            }
            for c in coins
        },
    }
    saved = save_probabilities(batch_id, decisions, streams)
    if saved:
        results["probabilities"] = saved
    return results, runs


def save_probabilities(batch_id: str, decisions, streams) -> List[str]:
    """Each trained contestant's probabilities per stream hour (amendment 1), for
    FDS-SIG-004's forecast scores: ``probabilities/<key>.npz`` in the batch's folder,
    with ``<coin>__close_s`` and ``<coin>__p`` for every coin. The contestants saved."""
    import numpy as np

    saved = []
    folder = os.path.join(batch_dir(batch_id), "probabilities")
    for key, by_coin in decisions.items():
        if not any(d.probs is not None for d in by_coin.values()):
            continue
        arrays = {}
        for coin, d in sorted(by_coin.items()):
            probs = d.probs if d.probs is not None else np.full(len(d.values), np.nan)
            arrays[f"{coin}__close_s"] = np.asarray(
                streams[coin].close_s, dtype=np.int64
            )
            arrays[f"{coin}__p"] = np.asarray(probs, dtype=float)
        os.makedirs(folder, exist_ok=True)
        np.savez_compressed(os.path.join(folder, f"{key}.npz"), **arrays)
        saved.append(key)
    return saved


def read_probabilities(batch_id: str, key: str) -> Dict[str, Tuple[Any, Any]]:
    """A contestant's saved probabilities: coin -> (close times, probabilities)."""
    import numpy as np

    path = os.path.join(batch_dir(batch_id), "probabilities", f"{key}.npz")
    with np.load(path) as z:
        coins = sorted({name.split("__")[0] for name in z.files})
        return {c: (z[f"{c}__close_s"], z[f"{c}__p"]) for c in coins}


def ten_runs(b: Optional[entry_gate.Baseline], value: Optional[float]):
    """The baseline's draws as 10 runs of consecutive draws (amendment 1): each run's
    p, and the pooled p, which is the p-value from all of them. A draw with no score is
    left out, as in every baseline."""
    import numpy as np

    if b is None or value is None:
        return None
    values = list(b.values)
    parts = np.array_split(np.asarray(values, dtype=float), RUNS)
    rows = []
    exceed = 0
    for part in parts:
        count = int(np.sum(part >= value))
        exceed += count
        rows.append(
            {
                "draws": int(len(part)),
                "exceed": count,
                "p": (1 + count) / (len(part) + 1),
            }
        )
    ps = [r["p"] for r in rows]
    return {
        "runs": rows,
        "pooled_p": (1 + exceed) / (len(values) + 1),
        "spread": max(ps) - min(ps),
    }


def _score(
    contestant,
    decisions: Dict[str, Decisions],
    tables,
    streams,
    data: LabData,
    fees,
    rules,
    seeds,
    draws: int,
    min_shift: int,
    k: int,
    rule,
    stop,
) -> Dict[str, Any]:
    coins = sorted(decisions)
    plans = [baselines.plan(decisions[c], tables[c]) for c in coins]
    own = baselines.own_trades(plans)
    score = figures(own)
    value = score["per_day"]
    result: Dict[str, Any] = {
        **contestant.to_dict(),
        "score": score,
        "time_in_trade": _hours_in_trade(plans, streams),
        "coins": {
            p.coin: {
                "joined": (
                    iso(int(streams[p.coin].close_s[p.start]))
                    if p.start < len(streams[p.coin])
                    else None
                ),
                "decided_hours": len(p.decided),
                "signal_hours": len(p.ones),
                **figures([t for _i, t in p.entries]),
            }
            for p in plans
        },
        "markets": _markets(plans, streams, data.series[CONTEXT]),
        "fees": {},
    }
    for name, factor in (("half", 0.5), ("double", 2.0)):
        trades: List[Trade] = []
        for c in coins:
            s = streams[c]
            table = TradeTable(s.close_s, s.price, rules, _scaled(fees[c], factor))
            trades += [
                t for _i, t in schedule(decisions[c].ones(), table, decisions[c].join)
            ]
        result["fees"][name] = {"factor": factor, **figures(trades)}
    if any(d.fits for d in decisions.values()):
        result["fits"] = {c: decisions[c].fits for c in coins if decisions[c].fits}
    if contestant.neural_dca:
        result["neural_dca"] = _neural_dca(decisions, streams, rules, fees, seeds, stop)
    if not contestant.tested:
        result.update({"p_r1": None, "p_r2": None, "p": None, "verdict": "reference"})
        result["verdict_text"] = verdict_text("reference")
        return result

    r1 = baselines.draws(baselines.R1, plans, draws, int(seeds["r1"]), min_shift, stop)
    part, short = baselines.r2_coins(plans, min_shift)
    r2 = (
        baselines.draws(
            baselines.R2,
            [p for p in plans if p.coin in part],
            draws,
            int(seeds["r2"]),
            min_shift,
            stop,
        )
        if part
        else None
    )
    value2 = figures(baselines.own_trades(plans, part))["per_day"] if part else None
    s1 = baseline_summary(r1, value)
    s2 = baseline_summary(r2, value2)
    if s2 is not None:
        s2.update({"coins": part, "own_per_day": value2})
    p1 = s1["p"] if s1 and s1["p"] is not None else 1.0
    p2 = s2["p"] if s2 and s2["p"] is not None else 1.0
    low1 = s1["p_lower"] if s1 and s1["p_lower"] is not None else 1.0
    low2 = s2["p_lower"] if s2 and s2["p_lower"] is not None else 1.0
    spreads = [x["spread"] for x in (s1, s2) if x is not None]
    edge = (
        stats.smallest_edge(max(spreads), k, rule["holm_alpha"], rule["power"])
        if spreads
        else None
    )
    too_few = edge is None or s1 is None or edge > rule["too_few"] * abs(s1["median"])
    result["_runs"] = {"r1": ten_runs(r1, value), "r2": ten_runs(r2, value2)}
    result.update(
        {
            "r1": s1,
            "r2": s2,
            "r2_left_out": short,
            "p_r1": p1,
            "p_r2": p2,
            "p": max(p1, p2),
            "p_lower": max(low1, low2),
            "smallest_edge": edge,
            "too_few": bool(too_few),
        }
    )
    return result


def _neural_dca(decisions, streams, rules, fees, seeds, stop) -> Dict[str, Any]:
    """The pattern model with neural DCA on (its DCA reads its own long counts), against
    R1 whose DCA reads the same counts, as the entry gate replays it. Shown only."""
    plans = []
    for c in sorted(decisions):
        d = decisions[c]
        s = streams[c]
        table = TradeTable(s.close_s, s.price, rules, fees[c], longs=d.longs)
        plans.append(baselines.plan(d, table))
    own = figures(baselines.own_trades(plans))
    r1 = baselines.draws(
        baselines.R1, plans, NEURAL_DCA_DRAWS, int(seeds["r1"]), 0, stop
    )
    return {"score": own, "r1": baseline_summary(r1, own["per_day"])}


def _judge(contestants, decisions, out, tables, streams, rule, cal) -> Dict[str, Any]:
    # every tested contestant is one of the K, one with no entries at p = 1
    tested = [c for c in contestants if c.tested]
    keys = [c.key for c in tested]
    ps = [out[key]["p"] for key in keys]
    screen = stats.benjamini_hochberg(ps, rule["screen_q"]) if ps else []
    holm = stats.holm(ps, rule["holm_alpha"]) if ps else []
    # the probability of backtest overfitting, over the tested contestants
    blocks = int(rule["pbo_blocks"])
    a, b = cal.stream
    nets, helds = [], []
    for key in keys:
        net = [0.0] * blocks
        held = [0.0] * blocks
        for coin, d in decisions[key].items():
            plan = baselines.plan(d, tables[coin])
            if not plan.entries:
                continue
            at = stats.block_of(
                [int(streams[coin].close_s[i]) for i, _t in plan.entries], a, b, blocks
            )
            for (i, t), blk in zip(plan.entries, at.tolist()):
                net[blk] += t.net
                held[blk] += t.capital_days
        nets.append(net)
        helds.append(held)
    pbo = stats.pbo(nets, helds)
    rules_ = [c for c in tested if c.family == "rule"]
    k = len(tested)
    for c in contestants:
        r = out[c.key]
        if not c.tested:
            continue
        if not r["score"]["trades"]:
            r.update(
                {
                    "screen": False,
                    "holm": False,
                    "finalist": False,
                    "verdict": "no_entries",
                }
            )
            r["verdict_text"] = verdict_text("no_entries")
            continue
        j = keys.index(c.key)
        conditions = {
            "profit_above_0": r["score"]["profit"] > 0,
            "trades": r["score"]["trades"] >= rule["min_trades"],
            "drawdown": (
                r["r1"] is not None
                and r["score"]["drawdown"] is not None
                and r["score"]["drawdown"] >= r["r1"]["median_drawdown"]
            ),
            "pbo": pbo is not None and pbo <= rule["pbo_max"],
        }
        if c.family not in ("rule", "reference") and rules_:
            best = None
            for other in rules_:
                mine, theirs = _on_shared(
                    decisions[c.key], decisions[other.key], tables
                )
                if theirs["per_day"] is None:
                    continue
                if best is None or theirs["per_day"] > best[2]["per_day"]:
                    best = (other.key, mine, theirs)
            if best is not None:
                key, mine, theirs = best
                r["best_rule"] = {"key": key, "own": mine, "rule": theirs}
                conditions["above_best_rule"] = (
                    mine["per_day"] is not None
                    and mine["per_day"] > theirs["per_day"]
                    and mine["profit"] > theirs["profit"]
                )
            else:
                conditions["above_best_rule"] = True
        finalist = holm[j] and all(conditions.values())
        code = verdict_code(
            r["p_lower"] <= rule["holm_alpha"] / max(1, k),
            finalist,
            bool(r["lockbox_seen"]),
            screen[j],
            r["too_few"],
        )
        r.update(
            {
                "screen": screen[j],
                "holm": holm[j],
                "conditions": conditions,
                "finalist": finalist,
                "verdict": code,
                "verdict_text": verdict_text(code, r.get("smallest_edge")),
            }
        )
    return {"pbo": pbo, "pbo_blocks": blocks, "tested": keys}


# --- the report -------------------------------------------------------------------------


def _pct(value: Optional[float], digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:+.{digits}%}"


def _day(value: Optional[float]) -> str:
    return "n/a" if value is None else f"{value:+.3%} a day"


def _num(value: Optional[float], digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def report(
    record: Mapping[str, Any],
    results: Mapping[str, Any],
    runs: Optional[Mapping[str, Any]] = None,
) -> str:
    """The batch's report, in Markdown: facts only."""
    cal = record["calendar"]
    runs = runs or {}
    declared = record.get("declared")
    lines = [
        f"# Model lab batch {record['id']}",
        "",
        f"- Frozen {record['frozen_at']}; batch file SHA-256 `{record['sha256']}`.",
        f"- Spec version {record.get('spec_version', '1')}"
        + (f"; declared as {declared}" if declared else "")
        + ".",
        f"- Window {cal['start']} to {cal['end']}; {len(cal['folds'])} folds of "
        f"{cal['fold_months']} months from {cal['folds'][0][0]} to {cal['lockbox'][0]}; "
        f"the last {cal['lockbox_months']} months ({cal['lockbox'][0]} to "
        f"{cal['lockbox'][1]}) are locked and were not read.",
        f"- {results['k']} contestants tested; {record['draws']} draws of each random "
        f"baseline (seeds from {record['seeds']['r1']} and {record['seeds']['r2']}); "
        f"probability of backtest overfitting {_num(results['pbo'])} over "
        f"{results['pbo_blocks']} blocks.",
        "- Trade rules: "
        + json.dumps(record["rules"], sort_keys=True)
        + "; neural DCA "
        + record["neural_dca"]
        + ".",
        "",
        "## Series",
        "",
        "| Coin | Exchange | Pair | First bar | Last bar | Bars | SHA-256 | Fee a side | Why |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for coin, s in sorted(record["series"].items()):
        fee = record["fees"].get(coin)
        lines.append(
            f"| {coin} | {s['exchange']} | {s['pair']} | {s['first_open']} | "
            f"{s['last_open']} | {s['bars']} | `{s['sha256'][:16]}` | "
            + (f"{fee['rate']:.2%} + {fee['slippage']:.2%} slippage" if fee else "-")
            + f" | {s.get('why') or s.get('context') or ''} |"
        )
    lines += [
        "",
        "## Contestants",
        "",
        "| Contestant | Trades | Return per day held | R1 median | R1 percentile | "
        "R2 percentile | p | Smallest detectable edge | Verdict | Total profit | "
        "Worst drawdown | Time in a trade |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for key in results["order"]:
        r = results["contestants"][key]
        if r.get("verdict") == "forecast_only":
            lines.append(
                f"| {r['description']} (`{key}`) | - | - | - | - | - | - | - | "
                f"{r['verdict_text']} | - | - | - |"
            )
            continue
        r1, r2 = r.get("r1"), r.get("r2")
        lines.append(
            f"| {r['description']} (`{key}`) | {r['score']['trades']} | "
            f"{_day(r['score']['per_day'])} | {_day(r1['median']) if r1 else 'n/a'} | "
            f"{_num(r1['rank'], 1) if r1 else 'n/a'} | "
            f"{_num(r2['rank'], 1) if r2 else 'n/a'} | {_num(r.get('p'), 4)} | "
            f"{_day(r.get('smallest_edge'))} | {r['verdict_text']} | "
            f"{_num(r['score']['profit'], 2)} | {_pct(r['score']['drawdown'])} | "
            f"{_pct(r['time_in_trade']['share'], 0)} |"
        )
    for key in results["order"]:
        r = results["contestants"][key]
        lines += ["", f"### {r['description']} (`{key}`)", ""]
        lines.append("Parameters: " + json.dumps(r["params"], sort_keys=True) + ".")
        lines.append("")
        if r.get("verdict") == "forecast_only":
            lines.append(
                "- Fitted for its probabilities only, which are saved with the batch; "
                "its trades are not scored and it is not one of the K."
            )
            continue
        split = runs.get(key) or {}
        for name in ("r1", "r2"):
            s = split.get(name)
            if s:
                ps = [x["p"] for x in s["runs"]]
                lines.append(
                    f"- {name.upper()} as {len(ps)} runs of "
                    f"{s['runs'][0]['draws']} draws: p from {min(ps):.4f} to "
                    f"{max(ps):.4f}; pooled {s['pooled_p']:.4f}."
                )
        lines.append("| Coin | Joined | Trades | Return per day held | Total profit |")
        lines.append("|---|---|---|---|---|")
        for coin, c in sorted(r["coins"].items()):
            lines.append(
                f"| {coin} | {c['joined'] or 'never'} | {c['trades']} | "
                f"{_day(c['per_day'])} | {_num(c['profit'], 2)} |"
            )
        m = r["markets"]
        lines.append("")
        lines.append(
            f"- Rising markets: {m['rising']['trades']} trades, "
            f"{_day(m['rising']['per_day'])}; falling: {m['falling']['trades']} trades, "
            f"{_day(m['falling']['per_day'])}."
        )
        for name in ("half", "double"):
            f = r["fees"][name]
            lines.append(
                f"- At {name} the fee rate: {f['trades']} trades, {_day(f['per_day'])}, "
                f"total profit {_num(f['profit'], 2)}."
            )
        if r.get("r2_left_out"):
            lines.append(
                "- Not in R2 (stream shorter than twice the shortest move): "
                + ", ".join(r["r2_left_out"])
                + "."
            )
        if r.get("best_rule"):
            b = r["best_rule"]
            lines.append(
                f"- On the hours both cover, against the best untrained rule "
                f"(`{b['key']}`): {_day(b['own']['per_day'])} against "
                f"{_day(b['rule']['per_day'])}; total profit {_num(b['own']['profit'], 2)} "
                f"against {_num(b['rule']['profit'], 2)}."
            )
        if r.get("conditions"):
            lines.append(
                "- Pass conditions: "
                + ", ".join(
                    f"{k} {'yes' if v else 'no'}"
                    for k, v in sorted(r["conditions"].items())
                )
                + f"; Holm {'yes' if r['holm'] else 'no'}; screen "
                f"{'yes' if r['screen'] else 'no'}."
            )
        for look in r.get("looks") or []:
            lines.append(
                f"- An earlier look at its results: {look['start']} to {look['end']}, "
                f"{look['coins']}, on {look['when']}: {look['what']}."
            )
        if r.get("lockbox_seen"):
            lines.append(
                "- Its lockbox months were seen before (the looks from "
                + ", ".join(sorted({look["start"] for look in r["lockbox_seen"]}))
                + "), so a final check is shown and is not unseen evidence."
            )
        n = r.get("neural_dca")
        if n:
            nr1 = n["r1"]
            lines.append(
                f"- With neural DCA on (shown only): {n['score']['trades']} trades, "
                f"{_day(n['score']['per_day'])}"
                + (
                    f"; random entries with the same waits {_day(nr1['median'])} "
                    f"(median of {nr1['runs']}), percentile {_num(nr1['rank'], 1)}."
                    if nr1
                    else "."
                )
            )
    return "\n".join(lines) + "\n"
