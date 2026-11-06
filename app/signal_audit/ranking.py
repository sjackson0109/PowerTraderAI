"""
Coin selection (FDS-SIG-001 section 10.1), for any exchange: the same rules on every
exchange whose connector lists its spot markets and states daily quote volume (owner,
2026-11-06: no single-exchange logic).

* **The exchange.** The round's coins are ranked, history-checked and later fetched on
  one exchange: the first in Settings order (the primary exchange first) whose connector
  lists its spot markets (``spot_markets``), states daily quote volume
  (``daily_quote_volume``) and serves the candle history the round needs
  (``max_history_bars``). Every exchange passed over is recorded with the reason.
* **Universe.** Every market that exchange lists against the quote currency the app's
  dollar markets use there (USDT, USD), in any status, at the ranking fetch.
* **Ranking.** By 30-day quote volume: the sum of the daily quote volumes of the 30 UTC
  days ending on the ranking date (the last opening at 00:00 on it), as the exchange
  states them (``DailyQuoteVolume.measure`` says which fields). A market with fewer days
  sums the days it has.
* **Exclusions** (registered lists, each excluded symbol recorded with its reason):
  stablecoins and fiat- or commodity-pegged tokens; wrapped or staking-derivative
  tokens; leveraged tokens: a base asset that is a listed base plus one of the
  registered suffixes (UP, DOWN, BULL, BEAR), or one the exchange marks as leveraged.
  An ordinary ticker that merely ends in those letters (JUP) is not excluded, because
  its stem (J) is not a listed base.
* **History.** An eligible coin's 1h candles on that exchange have at most 0.1% of bars
  missing and no gap longer than 24 hours over the span the round needs. A coin that
  fails is replaced by the next eligible coin by rank, and the replacement recorded.
* **Count.** The top 10 eligible coins.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence

import numpy as np

DAY_MS = 86_400_000
HOUR_S = 3600
RANKING_DAYS = 30
COUNT = 10
MAX_MISSING_SHARE = 0.001
MAX_GAP_HOURS = 24

# The registered exclusion lists' proposed defaults (FDS-SIG-001 section 10.1 gives
# examples; the registration lists every excluded symbol with its reason).
STABLE_OR_PEGGED = (
    # US dollar stablecoins
    "USDT",
    "USDC",
    "FDUSD",
    "TUSD",
    "USDP",
    "DAI",
    "BUSD",
    "PYUSD",
    "USDD",
    "USDE",
    "USD1",
    "RLUSD",
    "GUSD",
    "FRAX",
    "LUSD",
    "UST",
    "USTC",
    "XUSD",
    "BFUSD",
    "USDS",
    "SUSD",
    "CUSD",
    # fiat and fiat-pegged tokens
    "EUR",
    "EURI",
    "AEUR",
    "EURC",
    "EURT",
    "GBP",
    "AUD",
    "BRL",
    "TRY",
    "ARS",
    "MXN",
    "JPY",
    "IDRT",
    "BIDR",
    "BKRW",
    "TRYB",
    "ZAR",
    "UAH",
    "NGN",
    "PLN",
    "RON",
    "CZK",
    # commodity-pegged tokens
    "PAXG",
    "XAUT",
)
WRAPPED_OR_STAKING = (
    "WBTC",
    "WBETH",
    "BETH",
    "STETH",
    "WSTETH",
    "CBETH",
    "RETH",
    "WETH",
    "BNSOL",
    "CBBTC",
    "WBNB",
    "WSOL",
    "JITOSOL",
    "MSOL",
    "BBSOL",
    "SOLVBTC",
    "LBTC",
    "TBTC",
)
LEVERAGED_SUFFIXES = ("UP", "DOWN", "BULL", "BEAR")


@dataclass(frozen=True)
class Exclusions:
    stable_or_pegged: Sequence[str] = STABLE_OR_PEGGED
    wrapped_or_staking: Sequence[str] = WRAPPED_OR_STAKING
    leveraged_suffixes: Sequence[str] = LEVERAGED_SUFFIXES

    def to_dict(self) -> Dict[str, List[str]]:
        return {
            "stable_or_pegged": list(self.stable_or_pegged),
            "wrapped_or_staking": list(self.wrapped_or_staking),
            "leveraged_suffixes": list(self.leveraged_suffixes),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Sequence[str]]) -> "Exclusions":
        return cls(
            tuple(data["stable_or_pegged"]),
            tuple(data["wrapped_or_staking"]),
            tuple(data["leveraged_suffixes"]),
        )

    def reason(self, market, listed_bases: Iterable[str]) -> Optional[str]:
        """Why a listed market is excluded, or None."""
        base = market.base.upper()
        coin = market.coin.upper()
        if base in self.stable_or_pegged or coin in self.stable_or_pegged:
            return "stablecoin, or a fiat- or commodity-pegged token"
        if base in self.wrapped_or_staking or coin in self.wrapped_or_staking:
            return "wrapped or staking-derivative token"
        if market.leveraged:
            return "leveraged token (marked by the exchange)"
        bases = {b.upper() for b in listed_bases}
        for suffix in self.leveraged_suffixes:
            if base.endswith(suffix) and len(base) > len(suffix):
                stem = base[: -len(suffix)]
                if stem in bases:
                    return f"leveraged token ({stem} plus {suffix})"
        return None


# --- the exchange ---------------------------------------------------------------------


@dataclass(frozen=True)
class ExchangeChoice:
    exchange: Optional[str]
    considered: List[Dict[str, str]]  # each exchange in Settings order, and its answer


def choose_exchange(
    manager, names: Sequence[str], bars_needed: Mapping[str, int]
) -> ExchangeChoice:
    """The first exchange in ``names`` (Settings order, the primary first) whose
    connector lists spot markets, states daily quote volume and serves at least
    ``bars_needed[tf]`` of its latest bars on each timeframe."""
    from pt_exchange_abstraction import AbstractExchange

    considered = []
    chosen = None
    for name in names:
        connector = _connector(manager, name)
        if connector is None:
            considered.append({"exchange": name, "answer": "not connected"})
            continue
        kind = type(connector)
        if kind.spot_markets is AbstractExchange.spot_markets:
            considered.append({"exchange": name, "answer": "lists no spot markets"})
            continue
        if kind.daily_quote_volume is AbstractExchange.daily_quote_volume:
            considered.append(
                {"exchange": name, "answer": "states no daily quote volume"}
            )
            continue
        short = [
            f"{tf}: serves its latest {connector.max_history_bars(tf)} bars, the round "
            f"needs {need}"
            for tf, need in bars_needed.items()
            if connector.max_history_bars(tf) is not None
            and connector.max_history_bars(tf) < need
        ]
        if short:
            considered.append({"exchange": name, "answer": "; ".join(short)})
            continue
        considered.append({"exchange": name, "answer": "chosen"})
        chosen = name
        break
    return ExchangeChoice(chosen, considered)


def _connector(manager, name: str):
    for exchange_type, exchange in manager.exchanges.items():
        if exchange_type.value == name:
            return exchange
    return None


# --- ranking --------------------------------------------------------------------------


def ranking_days(ranking_date: str) -> List[int]:
    """The open times (ms) of the 30 UTC days ending on ``ranking_date``
    (YYYY-MM-DD)."""
    day = datetime.strptime(ranking_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    last = int(day.timestamp()) * 1000
    return [last - k * DAY_MS for k in range(RANKING_DAYS - 1, -1, -1)]


@dataclass
class Ranked:
    rank: int
    coin: str
    pair: str
    status: str
    quote_volume_30d: float
    days: int
    included: bool
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def rank_markets(
    listing,
    volumes: Mapping[str, Any],
    ranking_date: str,
    exclusions: Exclusions,
) -> List[Ranked]:
    """Every listed market ranked by 30-day quote volume (largest first; ties by
    pair name), each included or excluded with its reason. ``volumes`` maps a pair to
    its ``DailyQuoteVolume`` (None or absent: no volume stated, ranked as 0)."""
    days = set(ranking_days(ranking_date))
    bases = [m.base for m in listing.markets]
    rows = []
    for m in listing.markets:
        dq = volumes.get(m.pair)
        in_span = [(t, v) for t, v in (dq.days if dq else ()) if t in days]
        total = float(sum(v for _t, v in in_span))
        reason = exclusions.reason(m, bases)
        rows.append([m, total, len(in_span), reason])
    rows.sort(key=lambda r: (-r[1], r[0].pair))
    return [
        Ranked(
            i + 1,
            m.coin.upper(),
            m.pair,
            m.status,
            total,
            n,
            reason is None,
            reason or "",
        )
        for i, (m, total, n, reason) in enumerate(rows)
    ]


# --- history ---------------------------------------------------------------------------


@dataclass(frozen=True)
class History:
    ok: bool
    bars: int
    expected: int
    missing: int
    missing_share: float
    longest_gap_hours: int
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return dict(self.__dict__)


def check_history(
    open_s: np.ndarray,
    span_start_s: int,
    span_end_s: int,
    max_missing_share: float = MAX_MISSING_SHARE,
    max_gap_hours: int = MAX_GAP_HOURS,
) -> History:
    """The 1h continuity rule over [span_start_s, span_end_s): at most 0.1% of the
    hourly bars missing and no gap longer than 24 hours (a gap: consecutive missing
    bars; the span's ends count, so a coin listed after the span starts fails)."""
    first = -(-int(span_start_s) // HOUR_S) * HOUR_S
    grid = np.arange(first, int(span_end_s), HOUR_S, dtype=np.int64)
    have = np.isin(grid, np.asarray(open_s, dtype=np.int64))
    expected = int(len(grid))
    missing = int((~have).sum())
    longest = 0
    run = 0
    for present in have.tolist():
        run = 0 if present else run + 1
        longest = max(longest, run)
    share = missing / expected if expected else 1.0
    problems = []
    if not expected:
        problems.append("the span holds no hour")
    if share > max_missing_share:
        problems.append(f"{missing} of {expected} hourly bars missing ({share:.3%})")
    if longest > max_gap_hours:
        problems.append(f"a gap of {longest} hours")
    return History(
        not problems,
        int(have.sum()),
        expected,
        missing,
        share,
        longest,
        "; ".join(problems),
    )


@dataclass
class Selection:
    coins: List[str]
    replacements: List[Dict[str, Any]]  # each coin that failed and who replaced it
    history: Dict[str, Dict[str, Any]]  # every coin checked
    considered_down_to: int  # the last rank considered


def select_coins(
    ranked: Sequence[Ranked],
    history_of: Callable[[Ranked], History],
    count: int = COUNT,
) -> Selection:
    """The top ``count`` included coins that pass the history rule, in rank order. The
    intended coins are the first ``count`` included ones; each that fails is replaced,
    in rank order, by the next included coin beyond them that passes."""
    included = [r for r in ranked if r.included]
    coins: List[str] = []
    history: Dict[str, Dict[str, Any]] = {}
    last_rank = 0
    for r in included:
        if len(coins) >= count:
            break
        h = history_of(r)
        history[r.coin] = {"pair": r.pair, "rank": r.rank, **h.to_dict()}
        last_rank = r.rank
        if h.ok:
            coins.append(r.coin)
    intended = [r.coin for r in included[:count]]
    failed = [c for c in intended if c in history and not history[c]["ok"]]
    extra = [c for c in coins if c not in intended]
    replacements = []
    for i, coin in enumerate(failed):
        replacements.append(
            {
                "failed": coin,
                "rank": history[coin]["rank"],
                "reason": history[coin]["reason"],
                "replaced_by": extra[i] if i < len(extra) else None,
            }
        )
    return Selection(coins, replacements, history, last_rank)


# --- evidence --------------------------------------------------------------------------


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_raw_answers(path: str, answers: Sequence[Any]) -> Dict[str, Any]:
    """Every raw answer, gzip-compressed as JSON lines ({url, params, status, sha256,
    body}), in the order fetched. Returns each answer's SHA-256 and the file's."""
    lines = []
    for a in answers:
        lines.append(
            json.dumps(
                {
                    "url": a.url,
                    "params": [list(p) for p in a.params],
                    "status": a.status,
                    "sha256": a.sha256,
                    "body": a.body.decode("utf-8", errors="replace"),
                },
                sort_keys=True,
            )
        )
    data = ("\n".join(lines) + "\n").encode("utf-8")
    # no time stamp and no file name in the header: the same answers, the same bytes
    with open(path, "wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as f:
            f.write(data)
    with open(path, "rb") as f:
        file_sha = sha256_bytes(f.read())
    return {
        "file": path,
        "file_sha256": file_sha,
        "answers": [
            {
                "url": a.url,
                "params": [list(p) for p in a.params],
                "status": a.status,
                "sha256": a.sha256,
            }
            for a in answers
        ],
    }


def read_raw_answers(path: str) -> List[Dict[str, Any]]:
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def verify_raw_answers(path: str, record: Mapping[str, Any]) -> List[str]:
    """What does not match the recorded SHA-256s (empty when everything does)."""
    problems = []
    with open(path, "rb") as f:
        if sha256_bytes(f.read()) != record["file_sha256"]:
            problems.append(f"{path}: the file's SHA-256 differs from the record")
    answers = read_raw_answers(path)
    if len(answers) != len(record["answers"]):
        problems.append(
            f"{path}: {len(answers)} answers, {len(record['answers'])} recorded"
        )
    for got, want in zip(answers, record["answers"]):
        body_sha = sha256_bytes(got["body"].encode("utf-8"))
        if got["sha256"] != want["sha256"] or body_sha != want["sha256"]:
            problems.append(f"{got['url']} {got['params']}: SHA-256 differs")
    return problems
