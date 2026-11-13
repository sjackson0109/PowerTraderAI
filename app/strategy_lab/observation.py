"""
Paper-trading observation segments and their reconciliation (FDS-SR-001 section 5.11).

**A segment** starts when the owner presses "Start an observation" (Settings > Paper
trading > Observation...). It freezes a snapshot of every setting that decides a paper
trade (``snapshot``): the strategy, its parameters, overlays and timeframe; the coins
and the paper-trading coins; sizing and risk; the entry checks; the LLM signal mode and
the LLM signals ticked for trading, which can confirm or veto an entry (``llm_gate``);
the enabled exchanges in the order the exchange layer asks them, which decide the quote,
fee, minimum and candles (``trading_config.json``); and the legacy engine's levels. Its
SHA-256 is kept with it, and so is the SHA-256 of each file on the trading path
(``code_hashes``), under ``<hub>/paper/observations/<id>.json``.

**A changed setting or program file ends it** (``check``): whenever the window opens or
reconciles, the snapshot is compared with the settings files and the program files with
their SHA-256s; if any deciding value changed, the segment ends at the time the changed
file was last written, with the keys or files that changed. Only what the segment froze
is compared: a segment started before a value was frozen is not ended because its record
lacks it, and its file is not rewritten to add it. A new segment starts only when the
owner presses the button again.

**Reconcile** (``reconcile``) replays the segment's closed candles, for the coins its
paper trader could open trades in (``replay_coins``), through the same strategy
(``strategy_lab.candidates``) and compares the trades it would make with the paper
trades, trade by trade:

* **matched**: the paper entry and exit fill in the bars the replay's do (the delay
  within the bar is reported, not hidden);
* **timing**: within 3 bars of them, but not in the same bar;
* **open**: paper still holds the trade, and so does the replay at its last bar;
* **exit_missed**: paper still holds a trade the replay has exited;
* **missed**: the replay trades and paper did not (the reason is not recorded);
* **extra**: paper traded and the replay did not;
* **pending**: paper entered, or exited, after the newest closed bar, which the replay
  needs before it can decide that trade;
* **duplicate**: a second ENTRY buy in a coin before the first one's exit;
* **different**: a segment row whose strategy fields (id, version, parameter SHA-256,
  timeframe, overlays) differ from the frozen strategy's. Such a row is never paired.

For each paired trade, per side: the paper fill against the replay's open (paper's
slippage), the paper fill's delay after the replay's, and the fee paper charged.

A segment is operational evidence: does paper do what the backtest says? It is not a
registered forward confirmation (FDS-SR-001 section 5.11).
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd

from market_data.candles import exchange_candles
from strategies.catalogue import create, get_entry
from strategy_lab.candidates import RunnerSpec, Trade, TradeTable

CONFIG_SECTIONS = ("strategy", "risk", "paper", "signal_fusion")
# llm.signal_mode and llm.signal_use: an LLM signal can confirm or veto an entry
LLM_KEYS = ("signal_mode", "signal_use")
GUI_KEYS = (
    "coins",
    "paper_coins_mode",
    "paper_coins",
    "start_allocation_pct",
    "max_coin_allocation_pct",
    "min_order_margin_pct",
    "trade_start_level",
    "dca_levels",
    "dca_multiplier",
    "max_dca_buys_per_24h",
    "pm_start_pct_no_dca",
    "pm_start_pct_with_dca",
    "trailing_gap_pct",
)
NEAR_BARS = 3
RESULT_KINDS = (
    "matched",
    "timing",
    "missed",
    "extra",
    "open",
    "exit_missed",
    "pending",
    "duplicate",
    "different",
)
# What the trader writes on each trade row about the strategy that placed it
STRATEGY_FIELDS = (
    "strategy_id",
    "strategy_version",
    "strategy_params_sha256",
    "strategy_timeframe",
    "strategy_overlays",
)

# The trading path: the files a paper order's decision, size, quote, fee and placement
# run through (pt_trader and what it imports for them). The owner's app runs from the
# checkout, so a merge can change them mid-segment; any change ends it. The folders are
# taken whole, their files of these kinds (not their sub-folders: signal_fusion's
# evaluation is offline research).
CODE_FILES = (
    "pt_trader.py",  # the trader loop and its orders
    "signal_engine.py",  # each bar's decision
    "trading_mode.py",  # the paper book, its quotes and fees
    "pt_settings_manager.py",  # the paper quote-age and price-fallback defaults
    "pt_paper_trading.py",
    "paper_coins.py",
    "position_sizing.py",
    "pt_risk.py",
    "risk_state.py",
    "llm_gate.py",  # an LLM signal's confirm or veto
    "pt_exchange_abstraction.py",  # the exchange layer
    "pt_exchanges.py",
    "pt_multi_exchange.py",
)
CODE_FOLDERS = (
    ("strategies", (".py", ".json")),  # strategies, overlays, runner, the catalogue
    ("market_data", (".py",)),  # candles and listings
    ("signal_fusion", (".py",)),  # the entry assessment
)
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ObservationError(RuntimeError):
    """A segment cannot be started, ended or reconciled."""


def folder(hub_dir: str) -> str:
    return os.path.join(hub_dir, "paper", "observations")


def _section(config: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    value = config.get(name)
    return value if isinstance(value, Mapping) else {}


def snapshot(
    config: Mapping[str, Any],
    gui: Mapping[str, Any],
    exchanges: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """The settings that decide a paper trade. ``exchanges``: the enabled exchanges in
    the order the exchange layer asks them, primary first; None leaves them out."""
    llm = _section(config, "llm")
    snap: Dict[str, Any] = {
        "config": {
            "trading.mode": _section(config, "trading").get("mode"),
            **{f"llm.{k}": llm.get(k) for k in LLM_KEYS},
            **{k: config.get(k) for k in CONFIG_SECTIONS},
        },
        "gui": {k: gui.get(k) for k in GUI_KEYS},
    }
    if exchanges is not None:
        snap["exchanges"] = [str(e) for e in exchanges]
    return snap


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def digest(snap: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(snap).encode("utf-8")).hexdigest()


def code_hashes(root: Optional[str] = None) -> Dict[str, Optional[str]]:
    """The SHA-256 of each trading-path file under ``root`` (the program folder), with
    LF line endings as model_lab's batches hash theirs; None for a file that is
    missing."""
    root = root or APP_DIR
    names = set(CODE_FILES)
    for sub, kinds in CODE_FOLDERS:
        try:
            listed = os.listdir(os.path.join(root, sub))
        except OSError:
            continue
        names.update(f"{sub}/{n}" for n in listed if n.endswith(kinds))
    out: Dict[str, Optional[str]] = {}
    for name in sorted(names):
        try:
            with open(os.path.join(root, *name.split("/")), "rb") as f:
                out[name] = hashlib.sha256(f.read().replace(b"\r\n", b"\n")).hexdigest()
        except OSError:
            out[name] = None
    return out


def _iso(t: float) -> str:
    return datetime.fromtimestamp(float(t), tz=timezone.utc).isoformat()


def segments(hub_dir: str) -> List[Dict[str, Any]]:
    """Every segment, oldest first."""
    out = []
    base = folder(hub_dir)
    if not os.path.isdir(base):
        return out
    for name in sorted(os.listdir(base)):
        if name.endswith(".json"):
            try:
                with open(os.path.join(base, name), encoding="utf-8") as f:
                    out.append(json.load(f))
            except (OSError, ValueError):
                continue
    return out


def open_segment(hub_dir: str) -> Optional[Dict[str, Any]]:
    live = [s for s in segments(hub_dir) if not s.get("ended_at")]
    return live[-1] if live else None


def _write(hub_dir: str, segment: Mapping[str, Any]) -> None:
    base = folder(hub_dir)
    os.makedirs(base, exist_ok=True)
    path = os.path.join(base, f"{segment['id']}.json")
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(segment, f, indent=2, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def start(
    hub_dir: str,
    config: Mapping[str, Any],
    gui: Mapping[str, Any],
    now: Optional[float] = None,
    exchanges: Optional[Sequence[str]] = None,
    code_root: Optional[str] = None,
) -> Dict[str, Any]:
    """Start a segment with today's deciding settings and trading-path files."""
    if open_segment(hub_dir) is not None:
        raise ObservationError("an observation is already running")
    now = now or time.time()
    snap = snapshot(config, gui, exchanges)
    segment = {
        "id": datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y%m%d-%H%M%S"),
        "started_at": _iso(now),
        "started_s": int(now),
        "snapshot": snap,
        "sha256": digest(snap),
        "code": code_hashes(code_root),
        "ended_at": None,
        "end_reason": None,
    }
    _write(hub_dir, segment)
    return segment


def end(hub_dir: str, reason: str, when: Optional[float] = None) -> Dict[str, Any]:
    segment = open_segment(hub_dir)
    if segment is None:
        raise ObservationError("no observation is running")
    when = when or time.time()
    segment.update(ended_at=_iso(when), ended_s=int(when), end_reason=reason)
    _write(hub_dir, segment)
    return segment


def _changed(old: Mapping[str, Any], new: Mapping[str, Any]) -> List[str]:
    """The keys frozen in ``old`` whose values differ in ``new``. A key ``old`` lacks
    (its segment started before that value was frozen) is not compared, nor are the
    exchanges when either side lacks them."""
    out = []
    for part in ("config", "gui"):
        a, b = old.get(part) or {}, new.get(part) or {}
        for key in sorted(a):
            if _canonical(a.get(key)) != _canonical(b.get(key)):
                out.append(key)
    if "exchanges" in old and "exchanges" in new:
        if _canonical(old["exchanges"]) != _canonical(new["exchanges"]):
            out.append("exchanges")
    return out


def _first_written(root: str, names: Sequence[str]) -> Optional[float]:
    """When the first of these files was last written; None when none exists."""
    times = []
    for name in names:
        try:
            times.append(os.path.getmtime(os.path.join(root, *name.split("/"))))
        except OSError:
            continue
    return min(times) if times else None


def check(
    hub_dir: str,
    config: Mapping[str, Any],
    gui: Mapping[str, Any],
    changed_at: Optional[float] = None,
    exchanges: Optional[Sequence[str]] = None,
    code_root: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """End the running segment if a deciding setting or a trading-path file changed;
    the ended segment, or None. ``changed_at`` is when the settings files were last
    written; a changed program file is dated by its own time. ``exchanges=None`` (not
    read) compares no exchanges; a segment that recorded no program files compares
    none."""
    segment = open_segment(hub_dir)
    if segment is None:
        return None
    keys = _changed(segment.get("snapshot") or {}, snapshot(config, gui, exchanges))
    frozen_code = segment.get("code")
    root = code_root or APP_DIR
    files: List[str] = []
    if isinstance(frozen_code, Mapping):
        now_code = code_hashes(root)
        files = sorted(
            n
            for n in set(frozen_code) | set(now_code)
            if frozen_code.get(n) != now_code.get(n)
        )
    if not keys and not files:
        return None
    times, reasons = [], []
    if keys:
        times.append(float(changed_at or time.time()))
        reasons.append("settings changed: " + ", ".join(keys))
    if files:
        times.append(_first_written(root, files) or time.time())
        reasons.append("program files changed: " + ", ".join(files))
    when = max(min(times), float(segment["started_s"]))
    return end(hub_dir, "; ".join(reasons), when)


# --- reconciliation ----------------------------------------------------------------------


@dataclass(frozen=True)
class PaperTrade:
    coin: str
    entry_s: int
    entry_price: float
    entry_fee: Optional[float]
    exit_s: Optional[int]
    exit_price: Optional[float]
    exit_fee: Optional[float]
    second_entry: bool = False  # an ENTRY buy while the coin's trade was still open


@dataclass(frozen=True)
class Row:
    coin: str
    result: str  # one of RESULT_KINDS
    replay_entry_s: Optional[int]
    paper_entry_s: Optional[int]
    replay_exit_s: Optional[int]  # None while the replay still holds the trade
    paper_exit_s: Optional[int]
    fill_vs_open: Optional[float]  # paper's entry fill against the replay's open
    fee_rate_paid: Optional[float]  # paper's entry fee, a fraction
    exit_fill_vs_open: Optional[float] = None  # paper's exit fill against the replay's
    exit_fee_rate_paid: Optional[float] = None  # paper's exit fee, a fraction
    entry_delay_s: Optional[int] = None  # paper's entry fill after the replay's
    exit_delay_s: Optional[int] = None  # paper's exit fill after the replay's
    differs: Tuple[str, ...] = ()  # the row's STRATEGY_FIELDS that differ


def _seconds(ts: Any) -> Optional[int]:
    """A trade row's time: epoch seconds as the trader writes them (``time.time()``),
    or ISO text."""
    if ts is None or isinstance(ts, bool):
        return None
    if isinstance(ts, (int, float)):
        return int(ts)
    try:
        return int(float(ts))
    except (TypeError, ValueError):
        try:
            return int(pd.Timestamp(ts).timestamp())
        except (TypeError, ValueError):
            return None


def _coin(row: Mapping[str, Any]) -> str:
    return str(row.get("symbol", "")).split("-")[0].upper()


def differing_fields(
    row: Mapping[str, Any], frozen: Mapping[str, Any]
) -> Tuple[str, ...]:
    """The strategy fields ``row`` records that differ from ``frozen``
    (``strategy_fields``). A field the row does not record is not compared."""
    return tuple(
        k
        for k in STRATEGY_FIELDS
        if k in row and _canonical(row[k]) != _canonical(frozen.get(k))
    )


def paper_trades(
    rows: Sequence[Mapping[str, Any]],
    start_s: int,
    end_s: int,
    frozen: Optional[Mapping[str, Any]] = None,
) -> List[PaperTrade]:
    """The catalogue strategy's paper trades (ENTRY buys and EXIT sells) in [start, end).

    Every ENTRY buy is kept: one made while the coin's trade is still open is a trade of
    its own, marked ``second_entry``. A trade's exit is its EXIT sells up to the one that
    ends it (``closes_position``; a row without it ends the trade, as the trader reads
    it): the first sell's time, their price weighted by quantity, their fees together.
    With ``frozen`` (``strategy_fields``), a row whose strategy fields differ is left
    out."""
    open_: Dict[str, Dict[str, Any]] = {}
    out: List[PaperTrade] = []
    for row in rows:
        when = _seconds(row.get("ts"))
        if when is None or not start_s <= when < end_s:
            continue
        if frozen is not None and differing_fields(row, frozen):
            continue
        coin = _coin(row)
        side, tag = str(row.get("side", "")).lower(), str(row.get("tag", ""))
        if side == "buy" and tag == "ENTRY":
            if coin in open_:
                out.append(
                    PaperTrade(
                        coin,
                        when,
                        _fill([row]),
                        _fee_rate([row]),
                        None,
                        None,
                        None,
                        True,
                    )
                )
            else:
                open_[coin] = {"buy": row, "s": when, "sells": []}
        elif side == "sell" and tag.startswith("EXIT") and coin in open_:
            trade = open_[coin]
            trade["sells"].append((when, row))
            if row.get("closes_position") is not False:
                del open_[coin]
                sells = [r for _, r in trade["sells"]]
                out.append(
                    PaperTrade(
                        coin,
                        trade["s"],
                        _fill([trade["buy"]]),
                        _fee_rate([trade["buy"]]),
                        trade["sells"][0][0],
                        _fill(sells),
                        _fee_rate(sells),
                    )
                )
    for coin, trade in open_.items():
        buy = trade["buy"]
        out.append(
            PaperTrade(
                coin, trade["s"], _fill([buy]), _fee_rate([buy]), None, None, None
            )
        )
    return sorted(out, key=lambda t: (t.entry_s, t.coin))


def _fill(rows: Sequence[Mapping[str, Any]]) -> float:
    """The rows' price, weighted by quantity when there are several."""
    if len(rows) > 1:
        try:
            qty = sum(float(r.get("qty")) for r in rows)
            if qty > 0:
                return (
                    sum(float(r.get("qty")) * float(r.get("price")) for r in rows) / qty
                )
        except (TypeError, ValueError):
            pass
    return float(rows[0].get("price") or 0.0)


def _fee_rate(rows: Sequence[Mapping[str, Any]]) -> Optional[float]:
    """The rows' fees over their value, a fraction."""
    try:
        notional = sum(float(r.get("qty")) * float(r.get("price")) for r in rows)
        fees = sum(float(r.get("fees_usd")) for r in rows)
        return fees / notional if notional > 0 else None
    except (TypeError, ValueError):
        return None


def spec_of(snapshot_: Mapping[str, Any]) -> RunnerSpec:
    """The strategy the segment froze, as a ``RunnerSpec``."""
    from strategies.settings import read_strategy_settings

    s = read_strategy_settings(
        {"strategy": (snapshot_.get("config") or {}).get("strategy") or {}}
    )
    if s.problem:
        raise ObservationError(f"the frozen strategy settings are refused: {s.problem}")
    if s.is_legacy:
        raise ObservationError(
            "the neural levels have no replay: reconciling needs a rule-based strategy"
        )
    return RunnerSpec(
        s.active_id, dict(s.params), tuple(dict(o) for o in s.overlays), s.timeframe
    )


def strategy_fields(spec: RunnerSpec) -> Dict[str, Any]:
    """The strategy fields the trader writes on each trade row it places under ``spec``
    (``pt_trader``'s ``_strategy_fields``): the id, its version, the SHA-256 of every
    parameter (defaults filled in), the timeframe, and each overlay's id and version."""
    params = dict(create(spec.strategy_id, **dict(spec.params)).params)
    canonical = json.dumps(
        params, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return {
        "strategy_id": spec.strategy_id,
        "strategy_version": get_entry(spec.strategy_id)["version"],
        "strategy_params_sha256": hashlib.sha256(canonical).hexdigest(),
        "strategy_timeframe": spec.timeframe,
        "strategy_overlays": [
            {"id": o["id"], "version": get_entry(o["id"])["version"]}
            for o in spec.overlays
        ],
    }


def replay_coins(snapshot_: Mapping[str, Any]) -> List[str]:
    """The coins the segment's trader could open trades in, as the trader chooses them:
    in paper mode the paper-trading coins (``paper_coins.entry_coins``), in live mode
    the coins in Settings."""
    import paper_coins

    gui = snapshot_.get("gui") or {}
    coins = paper_coins.normalise(gui.get("coins"))
    mode = str((snapshot_.get("config") or {}).get("trading.mode") or "").lower()
    if mode.strip() == "live":
        return coins
    return paper_coins.entry_coins(gui, coins)


def replay_trades(
    spec: RunnerSpec,
    candles: Mapping[str, pd.DataFrame],
    start_s: int,
    end_s: int,
    context: Optional[Mapping[str, Mapping[Tuple[str, str], pd.DataFrame]]] = None,
):
    """Per coin, the trades the strategy makes one after another (flat after each exit),
    from entries decided in [start, end)."""
    out = {}
    for coin, frame in candles.items():
        table = TradeTable(coin, frame, spec, (context or {}).get(coin))
        trades, free_s = [], start_s
        for t in table.candidates():
            if t.entry_s < free_s or t.entry_s >= end_s:
                continue
            trades.append(t)
            free_s = t.exit_s
        out[coin] = trades
    return out


def reconcile(
    segment: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    candles: Mapping[str, pd.DataFrame],
    end_s: Optional[int] = None,
    context=None,
) -> List[Row]:
    """The segment's paper trades against the replay's, trade by trade; and every
    segment row whose strategy fields differ from the frozen strategy's."""
    spec = spec_of(segment["snapshot"])
    start_s = int(segment["started_s"])
    end_s = int(end_s or segment.get("ended_s") or time.time())
    bar = spec.bar_seconds
    frozen = strategy_fields(spec)
    replayed = replay_trades(spec, candles, start_s, end_s, context)
    out = _differing_rows(rows, start_s, end_s, frozen)
    paper: List[PaperTrade] = []
    for p in paper_trades(rows, start_s, end_s, frozen):
        if p.second_entry:
            out.append(
                Row(p.coin, "duplicate", None, p.entry_s, None, None, None, p.entry_fee)
            )
        else:
            paper.append(p)
    used: set = set()
    for coin in sorted(replayed):
        for t in replayed[coin]:
            best = None
            for k, p in enumerate(paper):
                if k in used or p.coin != coin:
                    continue
                gap = abs(p.entry_s - t.entry_s) // bar
                if gap <= NEAR_BARS and (best is None or gap < best[0]):
                    best = (gap, k)
            if best is None:
                exit_s = None if t.forced else t.exit_s
                out.append(
                    Row(coin, "missed", t.entry_s, None, exit_s, None, None, None)
                )
                continue
            used.add(best[1])
            out.append(_paired(t, paper[best[1]], bar))
    # the replay decides a bar at its close, so an entry after the newest closed bar
    # cannot be replayed yet
    newest = {
        coin: int(pd.Timestamp(frame["open_time"].iloc[-1]).timestamp()) + bar
        for coin, frame in candles.items()
        if len(frame)
    }
    for k, p in enumerate(paper):
        if k not in used:
            late = p.coin in newest and p.entry_s >= newest[p.coin]
            out.append(
                Row(
                    p.coin,
                    "pending" if late else "extra",
                    None,
                    p.entry_s,
                    None,
                    p.exit_s,
                    None,
                    p.entry_fee,
                    exit_fee_rate_paid=p.exit_fee,
                )
            )
    return sorted(
        out,
        key=lambda r: (
            r.replay_entry_s or r.paper_entry_s or r.paper_exit_s or 0,
            r.coin,
        ),
    )


def _ratio(paper: Optional[float], replay: Optional[float]) -> Optional[float]:
    return paper / replay - 1.0 if paper is not None and replay else None


def _paired(t: Trade, p: PaperTrade, bar: int) -> Row:
    """A replayed trade and the paper trade paired with it. A forced replay trade is
    still open at the newest closed bar: it has no exit yet."""
    replay_exit = None if t.forced else t.exit_s
    if p.exit_s is None:
        result = "open" if t.forced else "exit_missed"
    elif replay_exit is None:
        # paper exited; the replay holds the trade to the newest closed bar's close
        result = "pending" if p.exit_s >= t.exit_s else "timing"
    else:
        same_entry = t.entry_s <= p.entry_s < t.entry_s + bar
        same_exit = replay_exit <= p.exit_s < replay_exit + bar
        result = "matched" if same_entry and same_exit else "timing"
    paired_exit = p.exit_s is not None and replay_exit is not None
    return Row(
        t.coin,
        result,
        t.entry_s,
        p.entry_s,
        replay_exit,
        p.exit_s,
        _ratio(p.entry_price, t.entry_price),
        p.entry_fee,
        exit_fill_vs_open=_ratio(p.exit_price, t.exit_price) if paired_exit else None,
        exit_fee_rate_paid=p.exit_fee,
        entry_delay_s=p.entry_s - t.entry_s,
        exit_delay_s=p.exit_s - replay_exit if paired_exit else None,
    )


def _differing_rows(
    rows: Sequence[Mapping[str, Any]],
    start_s: int,
    end_s: int,
    frozen: Mapping[str, Any],
) -> List[Row]:
    """Every row in [start, end), whatever its tag, whose strategy fields differ from
    ``frozen``: a buy as an entry, a sell as an exit."""
    out = []
    for row in rows:
        when = _seconds(row.get("ts"))
        if when is None or not start_s <= when < end_s:
            continue
        fields = differing_fields(row, frozen)
        if not fields:
            continue
        buy = str(row.get("side", "")).lower() == "buy"
        fee = _fee_rate([row])
        out.append(
            Row(
                _coin(row),
                "different",
                None,
                when if buy else None,
                None,
                None if buy else when,
                None,
                fee if buy else None,
                exit_fee_rate_paid=None if buy else fee,
                differs=fields,
            )
        )
    return out


def load_candles(
    spec: RunnerSpec,
    coins: Sequence[str],
    start_s: int,
    end_s: int,
    loader: Callable[..., pd.DataFrame] = exchange_candles,
):
    """The segment's closed candles, from far enough back for the warm-up, through the
    exchange layer and its cache; and each coin's context for an entry gate."""
    from strategy_lab.simulate import load_universe
    from strategy_lab.runs import _warmup_start

    start = pd.Timestamp(start_s, unit="s", tz="UTC")
    end = pd.Timestamp(end_s, unit="s", tz="UTC")
    universe = load_universe(
        list(coins), spec, _warmup_start(spec, start), end, loader=loader
    )
    return universe.frames, {c: universe.context_for(c) for c in universe.frames}


def summary(rows: Sequence[Row]) -> Dict[str, int]:
    out = dict.fromkeys(RESULT_KINDS, 0)
    for r in rows:
        out[r.result] += 1
    return out


def as_dicts(rows: Sequence[Row]) -> List[Dict[str, Any]]:
    return [asdict(r) for r in rows]
