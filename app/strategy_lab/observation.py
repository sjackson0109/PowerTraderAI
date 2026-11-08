"""
Paper-trading observation segments and their reconciliation (FDS-SR-001 section 5.11).

**A segment** starts when the owner presses "Start an observation" (Settings > Paper
trading > Observation...). It freezes a snapshot of every setting that decides a paper
trade (``snapshot``): the strategy, its parameters, overlays and timeframe; the coins
and the paper-trading coins; sizing and risk; the entry checks; and the legacy engine's
levels. Its SHA-256 is kept with it, under ``<hub>/paper/observations/<id>.json``.

**A changed setting ends it** (``check``): whenever the window opens or reconciles, the
snapshot is compared with the settings files; if any deciding value changed, the segment
ends at the time the changed file was last written, with the keys that changed. A new
segment starts only when the owner presses the button again.

**Reconcile** (``reconcile``) replays the segment's closed candles through the same
strategy (``strategy_lab.candidates``) and compares the trades it would make with the
paper trades, trade by trade:

* **matched**: the paper entry and exit fill in the bars the replay's do;
* **timing**: within 3 bars of them, but not in the same bar;
* **missed**: the replay trades and paper did not (the reason is not recorded);
* **extra**: paper traded and the replay did not.

For each matched or timing trade: the paper fill against the replay's open (paper's
slippage) and the fee paper charged, per side.

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
from strategy_lab.candidates import RunnerSpec, TradeTable

CONFIG_SECTIONS = ("strategy", "risk", "paper", "signal_fusion")
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


class ObservationError(RuntimeError):
    """A segment cannot be started, ended or reconciled."""


def folder(hub_dir: str) -> str:
    return os.path.join(hub_dir, "paper", "observations")


def snapshot(config: Mapping[str, Any], gui: Mapping[str, Any]) -> Dict[str, Any]:
    """The settings that decide a paper trade."""
    trading = (
        config.get("trading") if isinstance(config.get("trading"), Mapping) else {}
    )
    return {
        "config": {
            "trading.mode": (trading or {}).get("mode"),
            **{k: config.get(k) for k in CONFIG_SECTIONS},
        },
        "gui": {k: gui.get(k) for k in GUI_KEYS},
    }


def digest(snap: Mapping[str, Any]) -> str:
    text = json.dumps(snap, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
) -> Dict[str, Any]:
    """Start a segment with today's deciding settings."""
    if open_segment(hub_dir) is not None:
        raise ObservationError("an observation is already running")
    now = now or time.time()
    snap = snapshot(config, gui)
    segment = {
        "id": datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y%m%d-%H%M%S"),
        "started_at": _iso(now),
        "started_s": int(now),
        "snapshot": snap,
        "sha256": digest(snap),
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
    out = []
    for part in ("config", "gui"):
        a, b = old.get(part) or {}, new.get(part) or {}
        for key in sorted(set(a) | set(b)):
            if json.dumps(a.get(key), sort_keys=True, default=str) != json.dumps(
                b.get(key), sort_keys=True, default=str
            ):
                out.append(key)
    return out


def check(
    hub_dir: str,
    config: Mapping[str, Any],
    gui: Mapping[str, Any],
    changed_at: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """End the running segment if a deciding setting changed; the ended segment, or
    None. ``changed_at`` is when the settings file was last written."""
    segment = open_segment(hub_dir)
    if segment is None:
        return None
    snap = snapshot(config, gui)
    if digest(snap) == segment["sha256"]:
        return None
    keys = _changed(segment["snapshot"], snap)
    when = max(float(changed_at or time.time()), float(segment["started_s"]))
    return end(hub_dir, "settings changed: " + ", ".join(keys), when)


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


@dataclass(frozen=True)
class Row:
    coin: str
    result: str  # matched, timing, missed or extra
    replay_entry_s: Optional[int]
    paper_entry_s: Optional[int]
    replay_exit_s: Optional[int]
    paper_exit_s: Optional[int]
    fill_vs_open: Optional[float]  # paper's entry fill against the replay's open
    fee_rate_paid: Optional[float]  # paper's fee per side, a fraction


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


def paper_trades(
    rows: Sequence[Mapping[str, Any]], start_s: int, end_s: int
) -> List[PaperTrade]:
    """The catalogue strategy's paper trades (ENTRY buys and EXIT sells) in [start, end)."""
    open_: Dict[str, Dict[str, Any]] = {}
    out: List[PaperTrade] = []
    for row in rows:
        when = _seconds(row.get("ts"))
        if when is None or not start_s <= when < end_s:
            continue
        coin = str(row.get("symbol", "")).split("-")[0].upper()
        side, tag = str(row.get("side", "")).lower(), str(row.get("tag", ""))
        if side == "buy" and tag == "ENTRY":
            open_[coin] = row | {"_s": when}
        elif side == "sell" and tag.startswith("EXIT") and coin in open_:
            buy = open_.pop(coin)
            out.append(
                PaperTrade(
                    coin,
                    buy["_s"],
                    float(buy.get("price") or 0.0),
                    _fee_rate(buy),
                    when,
                    float(row.get("price") or 0.0),
                    _fee_rate(row),
                )
            )
    for coin, buy in open_.items():
        out.append(
            PaperTrade(
                coin,
                buy["_s"],
                float(buy.get("price") or 0.0),
                _fee_rate(buy),
                None,
                None,
                None,
            )
        )
    return sorted(out, key=lambda t: (t.entry_s, t.coin))


def _fee_rate(row: Mapping[str, Any]) -> Optional[float]:
    try:
        notional = float(row.get("qty")) * float(row.get("price"))
        return float(row.get("fees_usd")) / notional if notional > 0 else None
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
    """The segment's paper trades against the replay's, trade by trade."""
    spec = spec_of(segment["snapshot"])
    start_s = int(segment["started_s"])
    end_s = int(end_s or segment.get("ended_s") or time.time())
    bar = spec.bar_seconds
    replayed = replay_trades(spec, candles, start_s, end_s, context)
    paper = paper_trades(rows, start_s, end_s)
    used: set = set()
    out: List[Row] = []
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
                out.append(
                    Row(coin, "missed", t.entry_s, None, t.exit_s, None, None, None)
                )
                continue
            used.add(best[1])
            p = paper[best[1]]
            same_entry = t.entry_s <= p.entry_s < t.entry_s + bar
            same_exit = p.exit_s is not None and t.exit_s <= p.exit_s < t.exit_s + bar
            out.append(
                Row(
                    coin,
                    "matched" if same_entry and same_exit else "timing",
                    t.entry_s,
                    p.entry_s,
                    t.exit_s,
                    p.exit_s,
                    p.entry_price / t.entry_price - 1.0 if t.entry_price else None,
                    p.entry_fee,
                )
            )
    for k, p in enumerate(paper):
        if k not in used:
            out.append(
                Row(p.coin, "extra", None, p.entry_s, None, p.exit_s, None, p.entry_fee)
            )
    return sorted(out, key=lambda r: (r.replay_entry_s or r.paper_entry_s or 0, r.coin))


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
    out = {"matched": 0, "timing": 0, "missed": 0, "extra": 0}
    for r in rows:
        out[r.result] += 1
    return out


def as_dicts(rows: Sequence[Row]) -> List[Dict[str, Any]]:
    return [asdict(r) for r in rows]
