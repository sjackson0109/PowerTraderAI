"""
Walk-forward (FDS-MH-001 section 5.4): the fold calendar, and each contestant's
decision at every stream hour, made only from what was known then.

* **Calendar.** Fold 1 starts ``warmup_months`` (12) after the batch's start. Each fold
  is ``fold_months`` (3) long, on the same dates for every coin. The lockbox is the
  last ``lockbox_months`` (18) of the window, long enough for R2 to be drawn on its
  hours (at least twice its shortest move, 2 x 160 days); the last fold ends where it
  starts, so it may be shorter. An hour belongs to the fold its bar opens and closes
  in, as the trainer's held-out hours do (``model_gate.hourly_signals``).
* **Stream.** For each coin, the hours from fold 1's start to the lockbox's, joined end
  to end. Nothing in a run reads a bar of the lockbox.
* **Fits.** A trained contestant is fitted at the start of each fold on every bar before
  it (an expanding window from the batch's start); that fit, frozen, decides the fold's
  hours. A pooled contestant fits once per fold on all coins, a per-coin one once per
  coin per fold. An untrained rule has nothing to fit: it decides every hour from the
  bars before it.
* **Joining late.** A coin joins an untrained contestant's stream once it has
  ``RULE_HISTORY_DAYS`` complete UTC days (the longest rule's look-back, the same for
  every rule, so they are compared on the same hours). It joins a trained contestant's
  stream at the first fold that starts ``history_days`` after the coin's first bar.
  Hours before a coin joins are undecided.
* **Decisions** are one value per stream hour: 1 enter if flat, 0 don't, -1 undecided
  (no entry is made there, by the contestant or by its random entries). A trained
  contestant whose fits give probabilities of their target (amendment 1) also has one
  per stream hour; nothing in a decision reads them. Batch PV-1's contestants join at
  their first decided hour, their first common row (section 7a).
"""

from __future__ import annotations

import calendar as _calendar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from model_lab.series import DAY_S, HOUR_S, Series, epoch, iso

RULE_HISTORY_DAYS = 100  # the longest rule's look-back, in complete UTC days
WARMUP_MONTHS = 12  # from the batch's start to fold 1
FOLD_MONTHS = 3
LOCKBOX_MONTHS = 18  # owner, 2026-11-06 (FDS-MH-001 D11)

Progress = Callable[[str, int, int], None]


class Stopped(Exception):
    """The run was asked to stop."""


def add_months(epoch_s: int, months: int) -> int:
    """``epoch_s`` moved by whole calendar months (the day clamped to the month's
    length), at the same time of day."""
    t = datetime.fromtimestamp(int(epoch_s), tz=timezone.utc)
    index = t.year * 12 + (t.month - 1) + int(months)
    year, month = divmod(index, 12)
    day = min(t.day, _calendar.monthrange(year, month + 1)[1])
    return int(t.replace(year=year, month=month + 1, day=day).timestamp())


@dataclass(frozen=True)
class Calendar:
    start_s: int  # the batch's start
    end_s: int  # the batch's end: the last closed hour when it was frozen
    folds: Tuple[Tuple[int, int], ...]  # (start, end) of each fold
    lockbox: Tuple[int, int]
    warmup_months: int
    fold_months: int
    lockbox_months: int

    @property
    def stream(self) -> Tuple[int, int]:
        return self.folds[0][0], self.lockbox[0]

    def fold_index(self, open_s: np.ndarray) -> np.ndarray:
        """Each bar's fold (bars open on the hour, so a bar opening at or after a
        fold's start closes by its end exactly when it opens before it)."""
        starts = np.array([a for a, _ in self.folds], dtype=np.int64)
        return np.searchsorted(starts, np.asarray(open_s, dtype=np.int64), "right") - 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": iso(self.start_s),
            "end": iso(self.end_s),
            "warmup_months": self.warmup_months,
            "fold_months": self.fold_months,
            "lockbox_months": self.lockbox_months,
            "folds": [[iso(a), iso(b)] for a, b in self.folds],
            "lockbox": [iso(self.lockbox[0]), iso(self.lockbox[1])],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Calendar":
        return cls(
            epoch(data["start"]),
            epoch(data["end"]),
            tuple((epoch(a), epoch(b)) for a, b in data["folds"]),
            (epoch(data["lockbox"][0]), epoch(data["lockbox"][1])),
            int(data["warmup_months"]),
            int(data["fold_months"]),
            int(data["lockbox_months"]),
        )


def make_calendar(
    start,
    end,
    warmup_months: int = WARMUP_MONTHS,
    fold_months: int = FOLD_MONTHS,
    lockbox_months: int = LOCKBOX_MONTHS,
) -> Calendar:
    start_s = epoch(start)
    end_s = (epoch(end) // HOUR_S) * HOUR_S
    lock = add_months(end_s, -int(lockbox_months))
    first = add_months(start_s, int(warmup_months))
    if not first < lock:
        raise ValueError(
            f"the window {iso(start_s)} .. {iso(end_s)} is too short for "
            f"{warmup_months} months before the first fold and {lockbox_months} "
            "locked at the end"
        )
    folds: List[Tuple[int, int]] = []
    a = first
    k = 1
    while a < lock:
        b = min(add_months(first, k * int(fold_months)), lock)
        folds.append((a, b))
        a, k = b, k + 1
    return Calendar(
        start_s,
        end_s,
        tuple(folds),
        (lock, end_s),
        int(warmup_months),
        int(fold_months),
        int(lockbox_months),
    )


@dataclass(eq=False)
class LabData:
    """What contestants may read: every coin's series, cut at the lockbox's start, the
    trade rules, and where the trainer reads its candles."""

    series: Dict[str, Series]
    rules: Any  # model_gate.TradeRules
    start_s: int
    cache_dir: Optional[str] = None
    offline: bool = False
    seed: int = 0  # the fits' seed
    context: str = "BTC"  # the coin read for BTC's figures
    # the batch's coins' fees (entry_gate.Fees), for the trained contestants' targets
    fees: Dict[str, Any] = field(default_factory=dict)
    # features and labels built once per run (``features.table``, ``targets.labels``)
    cache: Dict[Any, Any] = field(default_factory=dict)


@dataclass(frozen=True, eq=False)
class Stream:
    """One coin's stream hours: each bar's close time and close, and its fold."""

    coin: str
    close_s: np.ndarray
    price: np.ndarray
    fold: np.ndarray
    first_open_s: int  # the coin's first bar in the whole series

    def __len__(self) -> int:
        return int(len(self.close_s))


def make_stream(
    series: Series, cal: Calendar, first_open_s: Optional[int] = None
) -> Stream:
    """The coin's stream from ``series``. ``first_open_s`` is the coin's first bar in
    the whole series (default: ``series``' own first bar): a coin listed after the
    lockbox starts has no bar before it, and so an empty stream."""
    a, b = cal.stream
    part = series.between(a, b)
    if first_open_s is None:
        first_open_s = series.first_open_s if len(series) else b
    return Stream(
        series.coin,
        part.close_s,
        part.close,
        cal.fold_index(part.open_s),
        int(first_open_s),
    )


@dataclass(eq=False)
class Decisions:
    """One contestant's decisions on one coin's stream."""

    coin: str
    join: int  # the first stream position the coin is in this contestant's stream
    values: np.ndarray  # int8 per position: 1, 0 or -1 (all -1 before ``join``)
    longs: Optional[List[Optional[int]]] = None  # the pattern model's long counts
    fits: List[Dict[str, Any]] = field(default_factory=list)
    # a trained contestant's probability of its target per position (NaN where
    # undecided), when its fits give one (amendment 1); entries never read it
    probs: Optional[np.ndarray] = None

    def ones(self) -> List[int]:
        return np.nonzero(self.values == 1)[0].tolist()

    def decided(self) -> List[int]:
        return np.nonzero(self.values != -1)[0].tolist()


def rule_join(stream: Stream, days: Optional[int] = None) -> int:
    """The first position at which the coin has ``days`` (default
    ``RULE_HISTORY_DAYS``) complete UTC days."""
    days = RULE_HISTORY_DAYS if days is None else days
    first_day = -(-stream.first_open_s // DAY_S) * DAY_S  # the first whole day's start
    return int(np.searchsorted(stream.close_s, first_day + days * DAY_S, "left"))


def usable_folds(stream: Stream, cal: Calendar, days: int) -> List[int]:
    """The folds at whose start the coin has ``days`` of bars."""
    return [
        f
        for f, (a, _b) in enumerate(cal.folds)
        if a - stream.first_open_s >= days * DAY_S
    ]


def decide(
    contestant,
    data: LabData,
    cal: Calendar,
    streams: Dict[str, Stream],
    progress: Optional[Progress] = None,
    stop: Optional[Callable[[], bool]] = None,
) -> Dict[str, Decisions]:
    """``contestant``'s decisions on every coin's stream (module docstring)."""
    coins = sorted(streams)
    out: Dict[str, Decisions] = {}
    if not contestant.trained:
        fitted = contestant.fit(data, cal.folds[0][0])
        for coin in coins:
            s = streams[coin]
            join = rule_join(s)
            values = np.full(len(s), -1, dtype=np.int8)
            if join < len(s):
                values[join:] = fitted.entries(coin, s.close_s[join:])
            out[coin] = Decisions(coin, join, values)
        return out

    usable = {c: usable_folds(streams[c], cal, contestant.history_days) for c in coins}
    for coin in coins:
        s = streams[coin]
        first = usable[coin][0] if usable[coin] else len(cal.folds)
        at = np.nonzero(s.fold >= first)[0]
        join = int(at[0]) if len(at) else len(s)
        out[coin] = Decisions(
            coin,
            join,
            np.full(len(s), -1, dtype=np.int8),
            [None] * len(s) if contestant.neural_dca else None,
        )
    total = (
        len(cal.folds) if contestant.pooled else sum(len(u) for u in usable.values())
    )
    done = 0
    for f, (a, _b) in enumerate(cal.folds):
        fold_coins = [c for c in coins if f in usable[c]]
        if not fold_coins:
            continue
        pooled_fit = None
        for coin in fold_coins:
            if stop is not None and stop():
                raise Stopped()
            if contestant.pooled:
                if pooled_fit is None:
                    pooled_fit = contestant.fit(data, a)
                    done += 1
                fitted = pooled_fit
            else:
                fitted = contestant.fit(data, a, coin)
                done += 1
            s = streams[coin]
            where = np.nonzero(s.fold == f)[0]
            d = out[coin]
            if len(where):
                if contestant.neural_dca:
                    longs, values = fitted.counts_and_entries(coin, s.close_s[where])
                    for k, n in zip(where.tolist(), longs):
                        d.longs[k] = n
                else:
                    values = fitted.entries(coin, s.close_s[where])
                d.values[where] = values
                probs = fitted.probabilities(coin, s.close_s[where])
                if probs is not None:
                    if d.probs is None:
                        d.probs = np.full(len(s), np.nan)
                    d.probs[where] = probs
            record = getattr(fitted, "record", None)
            if record is not None:
                d.fits.append({"fold": f + 1, **record(coin)})
            if progress is not None:
                progress("fits", done, total)
    if getattr(contestant, "join_on_first_decided", False):
        # batch PV-1: a coin joins at its first common row (section 7a)
        for d in out.values():
            decided = np.nonzero(d.values != -1)[0]
            d.join = int(decided[0]) if len(decided) else len(d.values)
    return out
