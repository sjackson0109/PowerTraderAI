"""
FDS-SR-001's second declared evaluation, SR1-E2: the Donchian ensemble's book
(``strategy_lab.ensemble``), approved for registration and one development run by the
owner on 2026-11-14 (decision D5 of ``docs/dev/ptai-rd-001/E2-ensemble-registration-
draft.md``, with D1 to D4 as answered). Research only: nothing in trading reads it.

**What is declared** (``declaration``), before any result exists:

* **The book:** STRAT-007 with OVL-MIDLINE on 20, 30, 60, 90, 150, 250 and 360 days;
  each coin 1/N of the account and each member 1/7 of that, sized once at entry; an
  entry the cash cannot fund is skipped and counted.
* **Coins** (D2): BTC, ETH, XRP, BNB, DOGE, SOL, ZEC, DASH and HYPE, each series from the
  first exchange in Settings order whose cache holds it, recorded per series.
* **One family, B** (K = 2, Holm at 5%):
  - **B1:** the book's return per capital-day against REF-RANDOM-E
    (``Ensemble.random_draws``): per (coin, member) slice, as many random entries as
    that slice took, on that coin's decision bars, each exited by that member's own
    rule and ratchet, replayed through the same book. B = 200 a run, 10 seeded runs,
    pooled: p = (1 + #{draws >= book}) / (B + 1).
  - **B2:** F3 for the book (``book_f3``) at £10,000 and 0.50% taker + 0.05% a fill:
    (1) at least 100 trades and 30 in each half (halves at the window's middle day, by
    entry day), else "Not assessable"; (2) return per capital-day above 0 by
    ``research_stats.resampling.rpcd_test`` at its default (studentised, blocks x1.5:
    O3) on the book's daily marks, 10 seeded runs of 2,000, pooled: the family member;
    (3) a net profit in each half; (4) a net profit without the most profitable coin,
    every member's trades on it summed as they occurred; (5) D1: the book's maximum
    drawdown below the equal-weight hold's, both by the O12 rule (each position at its
    bar's low, from a peak at the earlier bars' highs: the replay's intrabar figures).
    The trader's 8% halt is reported, not modelled.
* **Shown, deciding nothing** (Benjamini-Hochberg at q = 0.10 over the shown p-values):
  the hold comparison (D3; ``hold_comparison``); matched holding (O19, reported only,
  with no p-value); each member alone; the book volatility-sized at 25%, 50% and 75% a
  year (D4: the book's own sizing decides); PBO across the seven members and the book;
  robustness (fees at 1.20%, BTC and ETH only, the coins with bars from 2021-01-01, the
  second exchange in Settings order, £500 and £50).
* **Power** (``power`` in the results), reported before the verdicts: each member's
  smallest detectable effect at Holm's level and 80% power, and the hold comparison's,
  on these months and projected to the lockbox's 18 months. A trading member that does
  not pass and could not have seen an effect of half the random median's size reads
  "Too few trades to tell" (E1's convention).
* **Windows:** candles from 2020-01-01 for warm-up; trades whose entry fills from
  2021-01-01 are scored, to 2025-05-06; no bar opening on or after 2025-05-06 is read
  (``development_loader``, E1's): the lockbox stays closed.

The declared design is hashed (``design_sha256``) and the hash is written here
(``DESIGN_SHA256``): a changed member, seed or rule is refused (``check_declaration``)
rather than run as if it were the approved one.

**What is run** (``evaluate``): B1 and B2, then everything shown. Each scored cell is
logged as a trial as soon as it is scored, in the strategy lab's trial log and the
programme ledger (``log_trial``). ``member_line`` words each verdict (section 6.6): only
the economic line may say "profitable", and every line ends "Development only: not
evidence for enabling anything."
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from model_lab.batch import _canonical
from signal_fusion.evaluation import findings as fd
from signal_fusion.evaluation.replay import Account, Costs, Paths
from strategy_lab import e1
from strategy_lab import ensemble as ens_mod
from strategy_lab import experiment, sizing
from strategy_lab.candidates import Trade
from strategy_lab.simulate import Universe, load_universe, usd_accounts
from strategy_lab.windows import DEVELOPMENT, HISTORY_START, LOCKBOX, ReservedPeriod

EXPERIMENT_ID = "SR1-E2"
APPROVED = "2026-11-14"

# the market (D2) -------------------------------------------------------------------------
COINS: Tuple[str, ...] = (
    "BTC", "ETH", "XRP", "BNB", "DOGE", "SOL", "ZEC", "DASH", "HYPE",
)  # fmt: skip
DAY_S = 86_400
DEV_START, DEV_END = DEVELOPMENT
DEV_START_S = int(DEV_START.timestamp())
DEV_END_S = int(DEV_END.timestamp())
LAST_S = DEV_END_S - 1  # the last scored second: the day before the lockbox
DECIDE_FROM_S = DEV_START_S - DAY_S  # the decision bar whose close is 2021-01-01
FIRST_DAY = DEV_START_S // DAY_S
DEV_DAYS = LAST_S // DAY_S - FIRST_DAY + 1
LOCKBOX_DAYS = int((LOCKBOX[1] - LOCKBOX[0]) / pd.Timedelta(days=1))

# costs and accounts --------------------------------------------------------------------
FEE = 0.005
ALLOWANCE = 0.0005
FEE_SOURCE = (
    "the owner's account taker rate on Coinbase, 0.50% (E1's E-D10, from the check "
    "window on 2026-11-05), as the registration's section 4 sets"
)
ACCOUNTS_GBP: Tuple[float, ...] = (10_000.0, 500.0, 50.0)
DECIDING_GBP = 10_000.0
HALT_PCT = 8.0

# tests ---------------------------------------------------------------------------------
HOLM_ALPHA = 0.05
BH_Q = 0.10
POWER = 0.8
TOO_FEW = 0.5
RUNS = 10
PER_RUN = 200  # REF-RANDOM-E and matched holding: 2,000 draws
BOOTSTRAP_DRAWS = 2000  # each run of rpcd_test and mean_test (their default)
PBO_BLOCKS = 16
TARGETS: Tuple[float, ...] = (0.25, 0.50, 0.75)  # D4: shown only
SIZING_FEATURE = "volatility.ewma"
D1_RULE = (
    "the book's maximum drawdown below the equal-weight hold's maximum drawdown, both "
    "with each open position at its bar's low, from a peak at the highest high of the "
    "earlier bars (the replay's intrabar figures, with lows and highs: O12); the "
    "trader's 8% halt is reported, not modelled (D1)"
)


@dataclass(frozen=True)
class Member:
    """One declared, deciding test."""

    id: str
    family: str
    test: str  # "random" or "economic"
    kind: str  # its trial kind
    seed: int
    question: str


MEMBERS: Tuple[Member, ...] = (
    Member(
        "B1", "B", "random", "strategy", 2_000_000,
        "Does the ensemble's book time its entries better than random entries with "
        "each member's own exits?",
    ),
    Member(
        "B2", "B", "economic", "strategy", 2_100_000,
        "Is the ensemble's book profitable after fees at £10,000 and 0.50% + 0.05%?",
    ),
)  # fmt: skip
FAMILY: Dict[str, Tuple[str, int]] = {"B": ("The ensemble's book", 2)}
K = FAMILY["B"][1]


@dataclass(frozen=True)
class Variant:
    """A robustness run (FDS-SR-001 section 6.4): shown, never deciding."""

    name: str
    fee: Optional[float] = None
    coins: Optional[str] = None  # "BTC+ETH" or "listed_by_2021"
    exchange: Optional[str] = None  # "second": the second exchange in Settings order
    account_gbp: Optional[float] = None


VARIANTS: Tuple[Variant, ...] = (
    Variant("fees at 1.20%", fee=0.012),
    Variant("BTC and ETH only", coins="BTC+ETH"),
    Variant("coins with bars from 2021-01-01", coins="listed_by_2021"),
    Variant("the second exchange in Settings order", exchange="second"),
    Variant("£500", account_gbp=500.0),
    Variant("£50", account_gbp=50.0),
)
VARIANT_NOTES = {
    "fees at 1.20%": "Coinbase's published taker rate, with the same slippage",
    "the second exchange in Settings order": (
        "the coins its cache holds development bars for, at the same fees and "
        "minimums"
    ),
    "£500": (
        "each slice is 1/7 of a coin's 1/N of the account: the skips show how many "
        "fell below the venue's minimums"
    ),
    "£50": (
        "each slice is 1/7 of a coin's 1/N of the account: the skips show how many "
        "fell below the venue's minimums"
    ),
}

# the shown cells' seeds, each a range of its own (``seed_ranges``)
SHOWN_SEEDS: Dict[str, int] = {
    "hold comparison": 2_200_000,
    "matched holding": 2_300_000,
    **{
        f"member {n} alone": 2_400_000 + 100 * k
        for k, n in enumerate(ens_mod.LOOKBACKS)
    },
    **{f"volatility {t:.0%}": 2_500_000 + 100 * k for k, t in enumerate(TARGETS)},
    **{f"robust {v.name}": 2_600_000 + 100 * i for i, v in enumerate(VARIANTS)},
}

# the earlier looks at these months for this book (FDS-SR-001 section 6.1), recorded
# before the run
EARLIER_RUNS: Tuple[Mapping[str, Any], ...] = (
    {
        "pr": 291,
        "what": (
            "the ensemble exploration of 2026-11-13: the book, each member alone and "
            "volatility sizing at 25% a year, on these nine coins and months"
        ),
        "report": "docs/dev/ENSEMBLE-SIZING-EXPLORATION-dev.md",
    },
    {
        "pr": 300,
        "what": "O18's runs at 50% and 75% a year, of STRAT-004 and of this book",
        "report": "docs/dev/ENSEMBLE-SIZING-EXPLORATION-dev.md, section 4",
    },
    {
        "pr": 257,
        "what": (
            "the nine-coin comparison: STRAT-004 and others, not STRAT-007, on the "
            "same months and coins"
        ),
        "report": "docs/dev/COMPARISON-9-COINS-REPORT-dev.md",
    },
)
EXPOSURE_LOG = "docs/dev/compare-ensemble/trials.jsonl"
EXPOSURE_TRIAL_LINES = 84
EXPOSURE_EXPLORATIONS = 38
CODE_EXTRA = {
    "packages": ["research_stats", "feature_library"],
    "files": ["research_engine/ledger.py"],
}

# the SHA-256 of ``design()`` as approved on 2026-11-14
DESIGN_SHA256 = "7f7d4474d624ac59f7db5ca1193a1de475dafa0bb183c714b4f92b2447d46c9a"


class E2Error(RuntimeError):
    """SR1-E2 cannot be run as declared."""


# --- the declaration -----------------------------------------------------------------------


def design() -> Dict[str, Any]:
    """Every declared choice that does not depend on the data: what ``DESIGN_SHA256``
    seals. The bootstrap's method and block scale are read from the library, so a
    changed default is a changed design."""
    from research_stats import resampling

    return {
        "experiment": EXPERIMENT_ID,
        "approved": APPROVED,
        "coins": list(COINS),
        "lookbacks": [int(n) for n in ens_mod.LOOKBACKS],
        "members": [asdict(m) for m in MEMBERS],
        "family": {f: [name, k] for f, (name, k) in FAMILY.items()},
        "windows": [
            HISTORY_START.isoformat(), DEV_START.isoformat(), DEV_END.isoformat(),
        ],  # fmt: skip
        "fee": FEE,
        "allowance": ALLOWANCE,
        "accounts_gbp": list(ACCOUNTS_GBP),
        "deciding_gbp": DECIDING_GBP,
        "halt_pct": HALT_PCT,
        "holm_alpha": HOLM_ALPHA,
        "bh_q": BH_Q,
        "power": POWER,
        "too_few": TOO_FEW,
        "runs": RUNS,
        "per_run": PER_RUN,
        "bootstrap_draws": BOOTSTRAP_DRAWS,
        "bootstrap": {
            "method": resampling.DEFAULT_METHOD,
            "block_scale": resampling.DEFAULT_BLOCK_SCALE,
        },
        "pbo_blocks": PBO_BLOCKS,
        "targets": list(TARGETS),
        "sizing_feature": SIZING_FEATURE,
        "variants": [asdict(v) for v in VARIANTS],
        "shown_seeds": dict(SHOWN_SEEDS),
        "drawdown_rule": D1_RULE,
    }


def design_sha256() -> str:
    return hashlib.sha256(_canonical(design())).hexdigest()


def seed_ranges() -> Dict[str, Tuple[int, int]]:
    """Every seed range SR1-E2 draws from, [first, last]: none may overlap."""
    slots = len(ens_mod.LOOKBACKS) * RUNS * PER_RUN  # one range per member slot
    out: Dict[str, Tuple[int, int]] = {}
    for m in MEMBERS:
        width = slots if m.test == "random" else RUNS
        out[m.id] = (m.seed, m.seed + width - 1)
    for name, seed in SHOWN_SEEDS.items():
        width = slots if name == "matched holding" else RUNS
        out[name] = (seed, seed + width - 1)
    return out


def check_declaration() -> None:
    """The family's size, the seeds, and the design as the owner approved it."""
    for family, (_name, k) in FAMILY.items():
        n = sum(1 for m in MEMBERS if m.family == family)
        if n != k:
            raise E2Error(f"family {family} has {n} members, {k} declared")
    if len({m.id for m in MEMBERS}) != len(MEMBERS):
        raise E2Error("member ids repeat")
    spans = sorted(seed_ranges().values())
    for (_a, b), (c, _d) in zip(spans, spans[1:]):
        if c <= b:
            raise E2Error(f"seed ranges overlap at {c}")
    got = design_sha256()
    if got != DESIGN_SHA256:
        raise E2Error(
            f"the declaration differs from the one the owner approved on {APPROVED} "
            f"(its SHA-256 is {got}, not {DESIGN_SHA256}): a changed member, seed or "
            "rule is a new registration"
        )


def exposures_record(path: str) -> Dict[str, Any]:
    """The exploration sandbox's trial log, as the registration counts it: its lines,
    its explorations and its SHA-256. Refused when the counts are not the declared
    ones."""
    with open(path, "rb") as f:
        raw = f.read()
    lines = [x for x in raw.decode("utf-8").splitlines() if x.strip()]
    kinds = [json.loads(x).get("kind") for x in lines]
    out = {
        "file": EXPOSURE_LOG,
        "lines": len(lines),
        "explorations": sum(1 for k in kinds if k == "exploration"),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    if (out["lines"], out["explorations"]) != (
        EXPOSURE_TRIAL_LINES,
        EXPOSURE_EXPLORATIONS,
    ):
        raise E2Error(
            f"the earlier exposures' trial log should hold {EXPOSURE_TRIAL_LINES} lines, "
            f"{EXPOSURE_EXPLORATIONS} of them explorations, as the registration says; "
            f"{path} holds {out['lines']} and {out['explorations']}"
        )
    return out


def members_record(lookbacks: Sequence[int] = ens_mod.LOOKBACKS) -> Dict[str, Any]:
    """Each member as a record holds a strategy (``experiment.strategy_record``)."""
    out = {}
    for n in lookbacks:
        spec = ens_mod.member_spec(n)
        out[str(int(n))] = experiment.strategy_record(
            spec.strategy_id, spec.params, spec.overlays, spec.timeframe
        )
    return out


def declaration(
    rate: Mapping[str, Any],
    venue: Mapping[str, Any],
    series_sha256: Mapping[str, str],
    coins_kept: Sequence[str],
    left_out: Mapping[str, str],
    exchange_order: Sequence[str],
    listed_by_2021: Sequence[str],
    served_by: Mapping[str, str],
    exposures: Mapping[str, Any],
    second: Optional[Mapping[str, Any]] = None,
    fees_read: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """SR1-E2's record, frozen by ``experiment.freeze`` before anything is scored.
    ``served_by`` names the exchange whose cache gave each series; ``second`` the
    second exchange in Settings order, the coins it has development bars for and those
    it has not; ``exposures`` the exploration's trial log (``exposures_record``);
    ``fees_read`` what the exchange layer gives as each coin's fee rates, beside the
    declared 0.50%."""
    check_declaration()
    gbp_usd = float(rate["gbp_usd"])
    lookbacks = [int(n) for n in ens_mod.LOOKBACKS]
    return {
        "approved": APPROVED,
        "authority": (
            "the work in the registration's section 8, its rehearsal, the freeze and one "
            "development run (D5); no paper or live activation, no promotion, the "
            "lockbox stays closed (O5)"
        ),
        "registration": "docs/dev/ptai-rd-001/E2-ensemble-registration-draft.md",
        "decisions": {
            "D1": D1_RULE,
            "D2": "the nine coins of the exploration, each series from the first "
            "exchange in Settings order whose cache holds it",
            "D3": "the comparison with the equal-weight hold is shown, not a member: K = 2",
            "D4": "the book's own sizing decides; volatility-sized books are shown only",
            "D5": "build, rehearse on synthetic candles, freeze, one development run",
        },
        "design_sha256": DESIGN_SHA256,
        "code_extra": dict(CODE_EXTRA),
        "family": {
            f: {
                "name": name,
                "members": [m.id for m in MEMBERS if m.family == f],
                "k": k,
                "correction": "Holm",
                "alpha": HOLM_ALPHA,
            }
            for f, (name, k) in FAMILY.items()
        },
        "members": [asdict(m) for m in MEMBERS],
        "strategy": {
            "book": (
                "each coin 1/N of the account and each member 1/M of that (M = 7), "
                "sized once at entry and never re-sized; a slice below the venue's "
                "minimum is skipped, never raised; an entry the cash cannot fund is "
                "skipped and counted (strategy_lab.ensemble)"
            ),
            "lookbacks": lookbacks,
            "members": members_record(lookbacks),
            "sizing": sizing.Fixed().record(),
        },
        "market": {
            "exchange_order": list(exchange_order),
            "served_by": dict(sorted(served_by.items())),
            "coins": list(COINS),
            "coins_with_development_bars": list(coins_kept),
            "left_out": dict(left_out),
            "listed_by_2021": list(listed_by_2021),
            "second_exchange": dict(second) if second is not None else None,
            "timeframe": "1d",
            "offline": True,
            "series_sha256": dict(series_sha256),
            "candles": (
                "read once per coin from the exchange layer's cache, from 2020-01-01 or "
                "the coin's first cached bar, to 2025-05-06 (exclusive); a series with "
                "a gap longer than a day is used from after its last such gap "
                "(market_data.gaps)"
            ),
        },
        "windows": {
            "history_from": HISTORY_START.date().isoformat(),
            "development": [DEV_START.date().isoformat(), DEV_END.date().isoformat()],
            "scored": "trades whose entry fills from 2021-01-01 to 2025-05-06",
            "halves": "at the window's middle day, by entry day",
            "lockbox": [LOCKBOX[0].date().isoformat(), LOCKBOX[1].date().isoformat()],
            "lockbox_read": False,
        },
        "costs": {
            "fee": FEE,
            "fee_source": FEE_SOURCE,
            "allowance": ALLOWANCE,
            "applied": "to every entry and exit fill, once (the replay's m(f, e))",
            "proportional": "no fixed fee an order (an assumption)",
            "exchange_layer_fees": dict(fees_read or {}),
            "minimum_usd": dict(venue.get("minimum_usd") or {}),
            "base_increment": dict(venue.get("base_increment") or {}),
            "venue_unknown": dict(venue.get("unknown") or {}),
            "venue_read_at": venue.get("read_at"),
            "venue_source": venue.get("source"),
            "venue_note": "today's values; past values are not recorded",
        },
        "accounts": {
            "gbp": list(ACCOUNTS_GBP),
            "deciding_gbp": DECIDING_GBP,
            "gbp_usd": gbp_usd,
            "rate": dict(rate),
            "usd": {str(k): v for k, v in usd_accounts(ACCOUNTS_GBP, gbp_usd).items()},
            "halt_pct": HALT_PCT,
            "halt": "reported, not modelled",
        },
        "baselines": {
            "REF-RANDOM-E": (
                "per (coin, member) slice, as many random entries as the book's path "
                "took there, on that coin's decision bars, the same waits in a random "
                "order, each exited by the member's own rule and ratchet, replayed "
                "through the same book (strategy_lab.ensemble.Ensemble.random_draws); "
                "member k's draw b seeded seed + 2,000 k + b; 10 runs of 200"
            ),
            "matched holding": (
                "per slice, random entries each held as long as one of the slice's "
                "trades (Ensemble.matched_draws), through the same book; reported only "
                "(O19)"
            ),
            "equal-weight hold": (
                "each coin 1/N of the account, bought once at the open after its first "
                "decision bar from 2020-12-31 (entering from 2021-01-01), held to the end"
            ),
            "REF-CASH": "no trades",
        },
        "tests": {
            "holm_alpha": HOLM_ALPHA,
            "exploratory": f"Benjamini-Hochberg at q = {BH_Q}, shown, never a pass",
            "statistic": "return per capital-day: summed net / summed (amount x days held)",
            "random_p": "(1 + #{draw >= value}) / (B + 1), pooled over 10 runs; each run's p shown",
            "economic": {
                "requirements": [
                    "at least 100 trades and 30 in each half, else Not assessable",
                    "return per capital-day above 0: the family member",
                    "a net profit in each half",
                    "a net profit without the most profitable coin, every member's "
                    "trades on it summed as they occurred",
                    "the drawdown requirement",
                ],
                "bootstrap": (
                    "research_stats.resampling.rpcd_test at its default (studentised, "
                    "the chosen block length x1.5: O3) on the book's daily marks "
                    "(research_stats.resampling.daily_marks), 10 runs of 2,000 seeded "
                    "seed + r, pooled: p = (1 + the runs' draws at or above) / (20,000 + 1)"
                ),
                "drawdown": D1_RULE,
            },
            "hold_comparison": (
                "research_stats.resampling.mean_test on the daily log-return difference "
                "(book less hold), 10 runs of 2,000 seeded seed + r, pooled; the mean "
                "and interval annualised x 365; shown (D3)"
            ),
            "too_few": (
                "a trading member that does not pass, whose smallest detectable edge, "
                "(z at 1 - 0.05/K + z at 0.8) x the random draws' standard deviation, "
                "is above 50% of |the random median|"
            ),
            "power": POWER,
            "seeds": {m.id: m.seed for m in MEMBERS},
            "shown_seeds": dict(SHOWN_SEEDS),
            "seed_ranges": {k: list(v) for k, v in seed_ranges().items()},
        },
        "sizing": {
            "deciding": "the book's own (D4)",
            "shown": [
                sizing.VolatilityTarget(target=t, feature=SIZING_FEATURE).record()
                for t in TARGETS
            ],
        },
        "robustness": {
            "variants": [asdict(v) for v in VARIANTS],
            "notes": dict(VARIANT_NOTES),
            "pbo": {
                "blocks": PBO_BLOCKS,
                "contestants": [f"member {n} alone" for n in lookbacks] + ["the book"],
                "scored": "each block's marked profit over its capital-days",
            },
        },
        "earlier_exposures": {
            "runs": [dict(x) for x in EARLIER_RUNS],
            "trial_log": dict(exposures),
        },
        "execution": (
            "market orders: an entry fills at the next bar's open after the decision, an "
            "exit at the next open after the exit decision; a trade open at the end is "
            "closed at the last close"
        ),
    }


# --- the candles -------------------------------------------------------------------------------


Loader = Callable[..., pd.DataFrame]


def development_loader(
    base: Optional[Loader] = None,
    first: Optional[Callable[[str, str], Optional[pd.Timestamp]]] = None,
    exchanges: Optional[Sequence[str]] = None,
) -> Loader:
    """E1's development loader (``e1.development_loader``: each series read once, from
    2020-01-01 or the coin's first cached bar, nothing reaching the reserved months),
    on the caches of ``exchanges`` only when given (the second exchange's run), else of
    the exchanges in Settings order."""
    names = list(exchanges) if exchanges is not None else None
    if base is None:

        def base(symbol, tf, a, b, cache_dir=None, offline=True):
            from market_data import candles

            return candles.exchange_candles(
                symbol, tf, a, b, cache_dir=cache_dir, offline=offline, exchanges=names
            )

    if first is None:

        def first(symbol, tf):
            return e1.first_cached(symbol, tf, exchanges=names)

    return e1.development_loader(base, first, offline=True)


def development_universe(
    coins: Sequence[str], loader: Loader
) -> Tuple[Universe, Dict[str, str]]:
    """Every coin with development bars, as daily candles; the coins left out, with
    the reason."""
    kept: List[str] = []
    left: Dict[str, str] = {}
    for coin in coins:
        try:
            frame = loader(f"{coin}-USD", "1d", HISTORY_START, DEV_END)
        except ReservedPeriod:
            raise
        except Exception as exc:  # recorded per coin, never silently
            left[coin] = str(exc)
            continue
        if len(frame) < 2:
            left[coin] = "fewer than 2 development bars"
            continue
        kept.append(coin)
    spec = ens_mod.member_spec(ens_mod.LOOKBACKS[0])
    start = HISTORY_START.date().isoformat()  # load_universe localises a plain date
    return load_universe(kept, spec, start, DEV_END, loader=loader), left


@dataclass
class Data:
    """The candles of the run, read once: the main series and the second exchange's."""

    universe: Universe
    left_out: Dict[str, str]
    second: Optional[Universe] = None
    second_left_out: Dict[str, str] = field(default_factory=dict)
    second_exchange: Optional[str] = None

    def series_sha256(self) -> Dict[str, str]:
        out = dict(e1.universe_sha256(self.universe))
        if self.second is not None:
            for key, value in e1.universe_sha256(self.second).items():
                out[f"{key}@{self.second_exchange}"] = value
        return dict(sorted(out.items()))


def load_data(
    loader: Loader,
    second_loader: Optional[Loader] = None,
    second_exchange: Optional[str] = None,
) -> Data:
    universe, left = development_universe(COINS, loader)
    data = Data(universe, left)
    if second_loader is not None:
        data.second, data.second_left_out = development_universe(COINS, second_loader)
        data.second_exchange = second_exchange
    return data


def served_by(universe: Universe) -> Dict[str, str]:
    """The exchange that gave each series, as the exchange layer recorded it."""
    return {
        key: str((attrs or {}).get("exchange") or "")
        for key, attrs in sorted(universe.sources.items())
    }


def listed_by_2021(universe: Universe) -> List[str]:
    """The coins whose first daily bar opens on or before 2021-01-01."""
    return sorted(
        coin
        for coin, frame in universe.frames.items()
        if len(frame) and e1._utc(frame["open_time"].iloc[0]) <= DEV_START
    )


def daily_closes(universe: Universe) -> Dict[str, Dict[int, float]]:
    """Each coin's close on each UTC day (the bar opening that day)."""
    out: Dict[str, Dict[int, float]] = {}
    for coin, frame in universe.frames.items():
        opens = pd.to_datetime(frame["open_time"], utc=True)
        days = ((opens - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(days=1)).tolist()
        out[coin] = dict(zip(days, frame["close"].astype(float).tolist()))
    return out


# --- the statistics --------------------------------------------------------------------------


def book_marks(path: Paths, slices: Sequence[Tuple[int, Trade]], closes) -> Any:
    """Path 0's trades marked at each UTC day's close of the development window
    (``research_stats.resampling.daily_marks``); ``slices`` is the replay's order of
    (member, trade)."""
    from research_stats import resampling

    rows = []
    for i, amount, net, _days in path.detail:
        t = slices[i][1]
        rows.append(
            {
                "coin": t.coin,
                "entry_s": t.entry_s,
                "exit_s": t.exit_s,
                "amount": amount,
                "entry_price": t.entry_price,
                "net": net,
            }
        )
    return resampling.daily_marks(rows, closes, FIRST_DAY, DEV_DAYS)


def _pooled(results: Sequence[Any], seed: int, scale: float = 1.0) -> Dict[str, Any]:
    """Ten seeded runs of one resampling test, pooled: each run's p is (1 + its draws
    at or above) / (its draws + 1), so the pooled p is (1 + all of them) / (all draws
    + 1). The interval shown is the median of the runs' bounds; each run's is kept.
    ``scale`` multiplies the estimate and the intervals (365 for a yearly figure)."""
    above = sum(int(round(r.p_value * (r.draws + 1))) - 1 for r in results)
    draws = sum(int(r.draws) for r in results)
    runs = [
        {
            "seed": seed + k,
            "p": float(r.p_value),
            "interval": [float(r.interval[0]) * scale, float(r.interval[1]) * scale],
            "draws": int(r.draws),
        }
        for k, r in enumerate(results)
    ]
    ps = [x["p"] for x in runs]
    return {
        "p": (1 + above) / (draws + 1),
        "draws": draws,
        "runs": runs,
        "spread": float(max(ps) - min(ps)) if ps else 0.0,
        "interval": [
            float(np.median([x["interval"][0] for x in runs])),
            float(np.median([x["interval"][1] for x in runs])),
        ],
        "level": float(results[0].level),
        "mean_block": float(results[0].mean_block),
        "days": int(results[0].days),
        "method": results[0].method,
    }


def rpcd_runs(marks, seed: int) -> Dict[str, Any]:
    """``rpcd_test`` at its default, 10 runs of 2,000 seeded ``seed + r``, pooled; with
    the long-run standard error its studentised test uses (for the power figures)."""
    from research_stats import resampling

    if marks.days < 2 or not np.sum(marks.capital) > 0:
        return {
            "p": 1.0,
            "assessable": False,
            "reason": "no capital was in the market",
            "runs": [],
            "draws": 0,
        }
    results = [
        resampling.rpcd_test(marks, draws=BOOTSTRAP_DRAWS, seed=seed + r)
        for r in range(RUNS)
    ]
    out = _pooled(results, seed)
    theta = float(results[0].theta)
    z = marks.pnl - theta * marks.capital
    lrv = float(resampling.bartlett_lrv(z, out["mean_block"])[0])
    out.update(
        {
            "assessable": True,
            "theta": theta,
            "se": math.sqrt(marks.days * lrv) / float(np.sum(marks.capital)),
        }
    )
    return out


def detectable(se: float, k: int = 1, scale: float = 1.0) -> float:
    """The smallest true effect a one-sided test at 5% / ``k`` finds with 80% power,
    for an estimate with standard error ``se`` (``research_stats.power``); ``scale``
    projects the standard error to another span at the same daily spread (the square
    root of this span's days over that one's)."""
    from research_stats import power

    if se is None or not np.isfinite(se) or se <= 0:
        return float("nan")
    return power.minimum_detectable(float(se) * scale, HOLM_ALPHA / max(1, k), POWER)


def _mean_test():
    from research_stats import resampling

    test = getattr(resampling, "mean_test", None)
    if test is None:
        raise E2Error(
            "research_stats.resampling.mean_test is not in this tree: the hold "
            "comparison needs it"
        )
    return test


def daily_log_difference(
    book_curve: Tuple[np.ndarray, np.ndarray], hold_curve: Tuple[np.ndarray, np.ndarray]
) -> Tuple[np.ndarray, np.ndarray]:
    """The daily log returns of the book less the hold's, on the marks both curves
    have in the development window: (the marks each return ends at, the differences)."""
    tb, eb = (np.asarray(v) for v in book_curve)
    th, eh = (np.asarray(v) for v in hold_curve)
    common = np.intersect1d(tb, th)
    common = common[(common >= DEV_START_S) & (common <= DEV_END_S)]
    vb = eb[np.searchsorted(tb, common)].astype(float)
    vh = eh[np.searchsorted(th, common)].astype(float)
    x = np.diff(np.log(vb)) - np.diff(np.log(vh))
    return common[1:], x


def hold_comparison(book_curve, hold_curve, seed: int) -> Dict[str, Any]:
    """The book against the equal-weight hold (D3, shown): ``mean_test`` on the daily
    log-return difference, 10 runs of 2,000 seeded ``seed + r``, pooled; the mean and
    intervals annualised x 365; with the smallest yearly lead detectable on these
    months and on the lockbox's."""
    from research_stats import resampling

    test = _mean_test()
    _t, x = daily_log_difference(book_curve, hold_curve)
    if len(x) < 2:
        return {"assessable": False, "reason": "fewer than two common days", "p": None}
    results = [test(x, draws=BOOTSTRAP_DRAWS, seed=seed + r) for r in range(RUNS)]
    out = _pooled(results, seed, scale=365.0)
    mean = float(np.mean(x))
    lrv = float(resampling.bartlett_lrv(x - mean, out["mean_block"])[0])
    se = math.sqrt(lrv / len(x))
    out.update(
        {
            "assessable": True,
            "annualised_mean": 365.0 * mean,
            "days": int(len(x)),
            "share_days_ahead": float(np.mean(x > 0)),
            "power": {
                "se_daily": se,
                "smallest_detectable_yearly": 365.0 * detectable(se),
                "smallest_detectable_yearly_lockbox": 365.0
                * detectable(se, 1, math.sqrt(len(x) / LOCKBOX_DAYS)),
            },
        }
    )
    return out


def _below_hold(path: Paths, hold: Paths) -> Tuple[float, float]:
    if path.intrabar_max_drawdown is None or hold.intrabar_max_drawdown is None:
        raise E2Error(
            "D1 compares drawdowns at the bars' lows: replay both with lows and highs"
        )
    return float(path.intrabar_max_drawdown[0]), float(hold.intrabar_max_drawdown[0])


def book_f3(
    path: Paths,
    slices: Sequence[Tuple[int, Trade]],
    closes,
    hold: Paths,
    seed: int,
    k: int = K,
) -> Dict[str, Any]:
    """F3 for the book (module docstring, B2): path 0 of a ``replay_trades(...,
    detail=True)``, ``slices`` its order of (member, trade), ``closes`` each coin's
    daily closes, ``hold`` the equal-weight hold's path (with its intrabar figures)."""
    rows = path.detail
    trades = [slices[i][1] for i, *_ in rows]
    t = np.array([x.entry_s for x in trades], dtype=np.int64)
    net = np.array([r[2] for r in rows], dtype=float)
    days = np.array([r[3] for r in rows], dtype=float)
    amount = np.array([r[1] for r in rows], dtype=float)
    n = len(rows)
    first_day, last_day = DEV_START_S // DAY_S, LAST_S // DAY_S
    middle = first_day + (last_day - first_day + 1) // 2
    second = (t // DAY_S) >= middle if n else np.zeros(0, dtype=bool)
    halves_n = [int(np.sum(~second)), int(np.sum(second))]
    halves_net = [float(net[~second].sum()), float(net[second].sum())]
    by_coin: Dict[str, float] = {}
    for x, v in zip(trades, net):  # every member's trades on a coin, as they occurred
        by_coin[x.coin] = by_coin.get(x.coin, 0.0) + float(v)
    best = max(by_coin, key=by_coin.get) if by_coin else None
    without_best = float(sum(v for c, v in by_coin.items() if c != best))
    book_dd, hold_dd = _below_hold(path, hold)
    marks = book_marks(path, slices, closes)
    test = rpcd_runs(marks, seed)
    total = float(net.sum())
    window = (LAST_S - DEV_START_S) / DAY_S
    roe = total / path.start
    req = {
        "trades": n >= fd.F3_MIN_TRADES and min(halves_n) >= fd.F3_MIN_HALF,
        "profit": test["p"],  # its pass is decided in the Holm family
        "stable": all(h > 0 for h in halves_net),
        "not_one_coin": without_best > 0,
        "below_hold": book_dd < hold_dd,
    }
    returns = net / amount if n else np.zeros(0)
    halt_low = path.intrabar_halt_s
    se = test.get("se", float("nan"))
    return {
        "requirements": req,
        "test": test,
        "smallest_detectable": detectable(se, k),
        "smallest_detectable_lockbox": detectable(
            se, k, math.sqrt(DEV_DAYS / LOCKBOX_DAYS)
        ),
        "report": {
            "net_usd": total,
            "return_on_equity": roe,
            "annualised": (1 + roe) ** (365.0 / window) - 1 if roe > -1 else math.nan,
            "rpcd": total / float(days.sum()) if days.sum() > 0 else 0.0,
            "marked_rpcd": marks.rpcd(),
            "capital_days": float(days.sum()),
            "trades": n,
            "trades_by_half": halves_n,
            "net_by_half": halves_net,
            "net_by_coin": by_coin,
            "best_coin": best,
            "without_best_coin": without_best,
            "win_rate": float(np.mean(net > 0)) if n else math.nan,
            "median_return": float(np.median(returns)) if n else math.nan,
            "largest_loss_usd": float(net.min()) if n else math.nan,
            "time_in_market": float(path.time_in_market[0]),
            "mean_committed": float(path.mean_committed[0]),
            "peak_committed": float(path.peak_committed[0]),
            "max_drawdown": float(path.max_drawdown[0]),
            "hold_max_drawdown": float(hold.max_drawdown[0]),
            "intrabar_max_drawdown": book_dd,
            "hold_intrabar_max_drawdown": hold_dd,
            "halt_pct": HALT_PCT,
            "halt_reached_s": int(path.halt_s[0]),
            "intrabar_halt_reached_s": (
                int(halt_low[0]) if halt_low is not None else -1
            ),
        },
    }


def book_passes(result: Mapping[str, Any], holm_pass: bool) -> bool:
    r = result["requirements"]
    return bool(
        r["trades"]
        and holm_pass
        and r["stable"]
        and r["not_one_coin"]
        and r["below_hold"]
    )


def book_failures(result: Mapping[str, Any], holm_pass: bool) -> List[str]:
    """Every requirement the book did not meet, each worded as a failure: F3's own
    words for the first four (``findings.f3_failures``), then D1's."""
    shim = {
        **result,
        "requirements": {**result["requirements"], "within_halt": True},
    }
    out = fd.f3_failures(shim, holm_pass, HALT_PCT)
    r, rep = result["requirements"], result["report"]
    if not r["below_hold"]:
        out.append(
            "failed the requirement for a maximum drawdown below the equal-weight "
            f"hold's ({rep['intrabar_max_drawdown']:.2%} against "
            f"{rep['hold_intrabar_max_drawdown']:.2%}, each at the bars' lows from a "
            "peak at the earlier bars' highs)"
        )
    return out


# --- verdict lines (section 6.6) ----------------------------------------------------------------

DEV_ONLY = e1.DEV_ONLY
_pct = e1._pct


def p_text(p: float) -> str:
    """A p-value to 4 decimals, or to 2 significant figures below 0.001: a pooled p of
    1 / 20,001 reads 0.000050, never 0.0000."""
    p = float(p)
    if not p > 0:
        return f"{p:.4f}"
    return f"{p:.{max(4, 1 - math.floor(math.log10(p)))}f}"


def _day(s: Optional[int]) -> Optional[str]:
    if s is None or int(s) < 0:
        return None
    return datetime.fromtimestamp(int(s), tz=timezone.utc).strftime("%Y-%m-%d")


def halt_sentence(report: Mapping[str, Any]) -> str:
    """The trader's halt, reported (D1): when the book first reached it, at the bars'
    lows, and what that means for trading it."""
    when = _day(report.get("intrabar_halt_reached_s"))
    if when is None:
        when = _day(report.get("halt_reached_s"))
    if when is None:
        return f"The book never reached the trader's {HALT_PCT:g}% halt."
    return (
        f"The book reached the trader's {HALT_PCT:g}% halt on {when}: trading it would "
        "need the halt changed."
    )


def member_line(
    member: Member,
    result: Mapping[str, Any],
    passed: bool,
    holm_pass: Optional[bool] = None,
) -> str:
    """The member's verdict, worded by section 6.6, with its caveat in the line. The
    economic line names each unmet requirement as a failure and always reports the
    halt. ``holm_pass`` is the economic member's bootstrap after Holm; without it, it
    follows from the bootstrap's p at 5% / K."""
    k = FAMILY[member.family][1]
    if member.test == "economic":
        rep = result["report"]
        halt = halt_sentence(rep)
        if not result["requirements"]["trades"]:
            text = (
                f"Not assessable: {rep['trades']} trades ({rep['trades_by_half'][0]} and "
                f"{rep['trades_by_half'][1]} by half; at least 100, and 30 in each "
                "half, are needed)"
            )
            return fd.check_wording(f"{text}. {halt} {DEV_ONLY}", True)
        drawdown = (
            f"maximum drawdown {rep['intrabar_max_drawdown']:.2%} at the bars' lows, "
            f"against the equal-weight hold's {rep['hold_intrabar_max_drawdown']:.2%}"
        )
        if passed:
            text = (
                "Profitable after fees at £10,000 with 0.50% taker and 0.05% slippage "
                f"a fill (net ${rep['net_usd']:+,.2f} on £10,000, return per capital-day "
                f"{_pct(rep['rpcd'])}, {rep['trades']} trades, {drawdown}, p = "
                f"{p_text(result['test']['p'])} (Holm over {k}), smallest detectable "
                f"return per capital-day {_pct(result.get('smallest_detectable'))})."
            )
            return fd.check_wording(f"{text} {halt} {DEV_ONLY}", True)
        if holm_pass is None:
            holm_pass = bool(result["test"]["p"] <= HOLM_ALPHA / k)
        failures = book_failures(result, holm_pass)
        text = "Not shown to be profitable after fees. The book " + ", and ".join(
            failures
        )
        text += "."
        if holm_pass:
            text += (
                f" Its bootstrap test of return per capital-day passed Holm over {k} "
                f"(p = {p_text(result['test']['p'])}), but that is one of the five "
                "requirements, and a pass needs all five."
            )
        text += (
            f" Figures: net ${rep['net_usd']:+,.2f} on £10,000, return per capital-day "
            f"{_pct(rep['rpcd'])}, {rep['trades']} trades, {drawdown}, smallest "
            f"detectable return per capital-day {_pct(result.get('smallest_detectable'))}."
        )
        return fd.check_wording(f"{text} {halt} {DEV_ONLY}", True)
    if not result.get("assessable", True):
        return fd.check_wording(
            f"Not assessable: {result['reason']}. {DEV_ONLY}", False
        )
    against = "random entries with each member's own exits"
    stats_text = (
        f"return per capital-day {_pct(result['value'])} against a random median of "
        f"{_pct(result['median'])}, p = {p_text(result['p'])} (Holm over {k}, B = "
        f"{result['draws']:,}), {result.get('trades', 0)} trades"
    )
    if passed:
        text = f"Beats {against} ({stats_text})"
        if result.get("net_usd", 0.0) <= 0:
            text += (
                f"; the book still loses money after fees (net "
                f"${result.get('net_usd', 0.0):+,.2f})"
            )
    elif result["too_few"]:
        text = (
            f"Too few trades to tell: this test could only see an edge above "
            f"{_pct(result['smallest_detectable'])} a capital-day ({stats_text})"
        )
    else:
        text = (
            f"No better than {against} ({stats_text}; smallest detectable edge "
            f"{_pct(result['smallest_detectable'])} a capital-day)"
        )
    return fd.check_wording(f"{text}. {DEV_ONLY}", False)


# --- trials ----------------------------------------------------------------------------------


def _candidates(record: Mapping[str, Any]) -> List[Dict[str, Any]]:
    from research_engine import ledger

    out = []
    for _n, r in sorted(
        ((record.get("strategy") or {}).get("members") or {}).items(),
        key=lambda kv: int(kv[0]),
    ):
        out.append(
            {
                "id": r.get("id"),
                "version": r.get("version"),
                "params_sha256": r.get("params_sha256"),
                "timeframe": r.get("timeframe"),
                "overlays": [
                    {
                        "id": o.get("id"),
                        "version": o.get("version"),
                        "params_sha256": ledger._params_sha256(o.get("params") or {}),
                    }
                    for o in r.get("overlays") or []
                ],
            }
        )
    return out


def _exposure_lines(record: Mapping[str, Any]) -> List[str]:
    exp = record.get("earlier_exposures") or {}
    out = [f"PR #{x.get('pr')}: {x.get('what')}" for x in exp.get("runs") or []]
    log = exp.get("trial_log") or {}
    if log:
        out.append(
            f"{log.get('file')}: {log.get('lines')} lines, {log.get('explorations')} "
            f"explorations (SHA-256 {log.get('sha256')})"
        )
    return out


def log_trial(
    record: Mapping[str, Any],
    member: str,
    kind: str,
    coins: Sequence[str],
    summary: Mapping[str, Any],
    seeds: Sequence[int] = (),
    family: Optional[str] = None,
) -> Dict[str, Any]:
    """One scored cell, as soon as it is scored: in the strategy lab's trial log
    (``experiment.log_trial``) and the programme ledger (``research_engine.ledger``),
    under the strategy-lab trial's id, so the ledger's ``sync`` does not count it
    twice."""
    from research_engine import ledger

    line = experiment.log_trial(
        EXPERIMENT_ID,
        member,
        kind,
        DEV_START.date().isoformat(),
        DEV_END.date().isoformat(),
        coins,
        summary,
    )
    exchanges = sorted(
        {v for v in ((record.get("market") or {}).get("served_by") or {}).values() if v}
    )
    ledger.append(
        ledger.entry(
            trial_id=f"strategy_lab:{line['trial']}",
            source="strategy_lab",
            source_trial=line["trial"],
            experiment_id=EXPERIMENT_ID,
            member=member,
            kind="declared",
            analysis=kind,
            family=family,
            candidates=_candidates(record),
            months={"start": line["start"], "end": line["end"]},
            coins=list(line["coins"]),
            exchange=", ".join(exchanges) or None,
            seeds=[int(s) for s in seeds],
            code_hash=record.get("sha256"),
            earlier_exposures=_exposure_lines(record),
            outcome={"summary": dict(summary)},
            counted_in=EXPERIMENT_ID,
            logged_at=line["logged_at"],
        )
    )
    return line


# --- the evaluation ----------------------------------------------------------------------------


def _accounts_usd(record: Mapping[str, Any]) -> Dict[float, float]:
    usd = record["accounts"]["usd"]
    return {g: float(usd[str(g)]) for g in ACCOUNTS_GBP}


def book_figures(
    slices: Sequence[Tuple[int, Trade]],
    path: Paths,
    costs: Costs,
    account_usd: float,
    gbp_usd: float,
) -> Dict[str, Any]:
    """E1's figures for path 0 (``e1.figures``: by year, by coin, halves, holding,
    capital, skips, drawdowns and the halt), with the trades by member."""
    trades = [t for _n, t in slices]
    out = e1.figures(trades, path, costs, Account(start=float(account_usd)), gbp_usd)
    by_member: Dict[str, Dict[str, float]] = {}
    for i, _amount, net, days in path.detail:
        cell = by_member.setdefault(
            str(slices[i][0]), {"trades": 0, "net_usd": 0.0, "capital_days": 0.0}
        )
        cell["trades"] += 1
        cell["net_usd"] += float(net)
        cell["capital_days"] += float(days)
    for cell in by_member.values():
        cd = cell["capital_days"]
        cell["rpcd"] = cell["net_usd"] / cd if cd > 0 else 0.0
    out["by_member"] = by_member
    return out


def _hold_figures(ens, costs, usd, gbp_usd, coins=None) -> Tuple[Dict[str, Any], Paths]:
    trades = ens.hold_trades(DECIDE_FROM_S, coins)
    path = ens.hold(costs, usd, DECIDE_FROM_S, detail=True, coins=coins)
    return e1.figures(trades, path, costs, Account(start=float(usd)), gbp_usd), path


def _compact(f: Mapping[str, Any]) -> Dict[str, Any]:
    out = e1.compact(f)
    out["intrabar_max_drawdown"] = f.get("intrabar_max_drawdown")
    out["halt_intrabar_reached_s"] = (f.get("halt") or {}).get("intrabar_reached_s")
    return out


def _blocks(marks) -> Tuple[List[float], List[float]]:
    """The marked profit and capital-days in each of the 16 equal blocks of days."""
    edges = np.linspace(0, marks.days, PBO_BLOCKS + 1).astype(int)
    pnl = [float(marks.pnl[a:b].sum()) for a, b in zip(edges, edges[1:])]
    cap = [float(marks.capital[a:b].sum()) for a, b in zip(edges, edges[1:])]
    return pnl, cap


def _coins_of(variant: Variant, record: Mapping[str, Any]) -> Optional[List[str]]:
    if variant.coins is None:
        return None
    if variant.coins == "BTC+ETH":
        return ["BTC", "ETH"]
    if variant.coins == "listed_by_2021":
        return list(record["market"]["listed_by_2021"])
    raise E2Error(f"unknown coin set {variant.coins!r}")


def evaluate(
    record: Mapping[str, Any],
    data: Data,
    progress: Callable[[str], None] = lambda _m: None,
    log_trials: bool = True,
) -> Dict[str, Any]:
    """Run the frozen declaration ``record`` (see the module docstring)."""
    from research_stats import multiple, overfitting

    check_declaration()
    if record.get("design_sha256") != DESIGN_SHA256:
        raise E2Error("the record was not frozen from the approved declaration")
    now_sha = data.series_sha256()
    frozen_sha = record["market"]["series_sha256"]
    if now_sha != frozen_sha:
        moved = sorted(
            k
            for k in set(now_sha) | set(frozen_sha)
            if now_sha.get(k) != frozen_sha.get(k)
        )
        raise E2Error(f"the candles differ from the frozen ones: {moved[:5]}")
    gbp_usd = float(record["accounts"]["gbp_usd"])
    costs = e1.costs_for(record)
    usd = _accounts_usd(record)
    deciding = usd[DECIDING_GBP]
    lookbacks = tuple(int(n) for n in record["strategy"]["lookbacks"])
    progress("the members' trades")
    ens = ens_mod.Ensemble(data.universe, lookbacks=lookbacks)
    coins = ens.coins
    closes = daily_closes(data.universe)
    by_member = ens.trades(DEV_START_S)
    order = ens.slices(by_member)
    path = ens.replay_trades(by_member, costs, deciding, detail=True)
    taken = ens.taken(by_member, path)
    hold_fig, hold = _hold_figures(ens, costs, deciding, gbp_usd)
    out: Dict[str, Any] = {
        "experiment": EXPERIMENT_ID,
        "record_sha256": record.get("sha256"),
        "gbp_usd": gbp_usd,
        "accounts_usd": {str(g): v for g, v in usd.items()},
        "coins": coins,
        "left_out": dict(data.left_out),
        "candidates": {str(n): len(v) for n, v in by_member.items()},
    }
    progress(f"the book: {int(path.trades[0])} trades, net {float(path.net[0]):+,.2f}")

    def trial(name, kind, summary, seeds=(), family=None, on=coins):
        if log_trials:
            log_trial(record, name, kind, on, summary, seeds, family)

    # --- B1: REF-RANDOM-E ---------------------------------------------------------------
    b1_m, b2_m = MEMBERS
    progress("B1: random entries for the book")
    count = RUNS * PER_RUN
    if path.trades[0] > 0:
        draws = ens.random_draws(taken, b1_m.seed, count, DECIDE_FROM_S)
        rp = ens.replay_draws(draws.draws, costs, deciding)
        b1 = e1._summary(float(path.rpcd[0]), rp.rpcd.reshape(RUNS, PER_RUN), K)
        b1.update(
            {
                "assessable": True,
                "seed": b1_m.seed,
                "trades": int(path.trades[0]),
                "net_usd": float(path.net[0]),
                "median_net_usd": float(np.median(rp.net)),
                "median_max_drawdown": float(np.median(rp.max_drawdown)),
                "entries_wanted": int(sum(draws.wanted.values())),
                "entries_wanted_by_slice": dict(draws.wanted),
                "entries_reached_median": float(np.median(draws.reached)),
                "draws_short": int(
                    sum(1 for r in draws.reached if r < sum(draws.wanted.values()))
                ),
            }
        )
    else:
        b1 = {"assessable": False, "reason": "the book made no trades", "p": 1.0}
    trial("B1", b1_m.kind, {"p": b1.get("p"), "value": b1.get("value")},
          [b1_m.seed], "B")  # fmt: skip
    progress(f"B1 p = {b1.get('p')}")

    # --- B2: F3 for the book --------------------------------------------------------------
    progress("B2: the book's economics")
    b2 = book_f3(path, order, closes, hold, b2_m.seed)
    trial("B2", b2_m.kind, {"p": b2["test"]["p"], "net_usd": b2["report"]["net_usd"]},
          [b2_m.seed], "B")  # fmt: skip
    progress(f"B2 p = {b2['test']['p']}")

    # --- Holm, verdicts --------------------------------------------------------------------
    ps = [float(b1.get("p", 1.0)), float(b2["test"]["p"])]
    holm = multiple.holm(ps, HOLM_ALPHA)
    adjusted = multiple.holm_adjusted(ps)
    verdicts: Dict[str, Dict[str, Any]] = {}
    for m, r, p, h, adj in zip(MEMBERS, (b1, b2), ps, holm, adjusted):
        if m.test == "economic":
            passed = book_passes(r, h)
            failures = [] if passed else book_failures(r, h)
            outcome = (
                "not_assessable" if not r["requirements"]["trades"]
                else ("pass" if passed else "fail")
            )  # fmt: skip
            kind = "economic"
        else:
            passed = bool(h and r.get("assessable", True))
            failures = []
            outcome = (
                "not_assessable" if not r.get("assessable", True)
                else "pass" if passed
                else "too_few" if r["too_few"]
                else "fail"
            )  # fmt: skip
            kind = "trading"
        verdicts[m.id] = {
            "family": m.family,
            "p": p,
            "holm_adjusted_p": adj,
            "holm_pass": bool(h),
            "passed": bool(passed),
            "outcome": outcome,
            "kind": kind,
            "failures": failures,
            "line": member_line(m, r, passed, holm_pass=bool(h)),
        }
    out["members"] = {"B1": b1, "B2": b2}
    out["verdicts"] = verdicts
    out["finalist"] = all(v["passed"] for v in verdicts.values())
    out["halt"] = {
        "level_pct": HALT_PCT,
        "book_reached_s": int(path.halt_s[0]),
        "book_intrabar_reached_s": b2["report"]["intrabar_halt_reached_s"],
        "hold_reached_s": int(hold.halt_s[0]),
        "hold_intrabar_reached_s": (
            int(hold.intrabar_halt_s[0]) if hold.intrabar_halt_s is not None else -1
        ),
        "sentence": halt_sentence(b2["report"]),
    }

    # --- the book's figures, and the hold's ----------------------------------------------
    out["book"] = book_figures(order, path, costs, deciding, gbp_usd)
    out["equal_weight_hold"] = hold_fig
    years = (LAST_S - DEV_START_S) / (365 * DAY_S)

    # --- shown: the hold comparison (D3) ----------------------------------------------------
    progress("the hold comparison")
    seed = SHOWN_SEEDS["hold comparison"]
    comparison = hold_comparison(path.curve, hold.curve, seed)
    trial("hold comparison", "strategy",
          {"p": comparison.get("p"), "annualised_mean": comparison.get("annualised_mean")},
          [seed])  # fmt: skip
    out["hold_comparison"] = comparison
    shown: Dict[str, Dict[str, Any]] = {"hold comparison": comparison}

    # --- shown: matched holding (O19, reported only) ------------------------------------------
    progress("matched holding")
    seed = SHOWN_SEEDS["matched holding"]
    matched: Dict[str, Any] = {"assessable": False, "reason": "the book made no trades"}
    if path.trades[0] > 0:
        md = ens.matched_draws(taken, seed, count, DECIDE_FROM_S)
        mp = ens.replay_draws(md.draws, costs, deciding)
        rpcd = mp.rpcd.reshape(RUNS, PER_RUN)
        mine = float(path.rpcd[0])
        low = mp.intrabar_max_drawdown
        matched = {
            "assessable": True,
            "seed": seed,
            "draws": int(mp.rpcd.size),
            "median_rpcd": float(np.median(mp.rpcd)),
            "share_at_or_above": float(np.mean(mp.rpcd >= mine)),
            "share_at_or_above_runs": [float(np.mean(r >= mine)) for r in rpcd],
            "median_net_usd": float(np.median(mp.net)),
            "median_max_drawdown": float(np.median(mp.max_drawdown)),
            "median_intrabar_max_drawdown": (
                float(np.median(low)) if low is not None else None
            ),
            "share_drawdown_at_or_below": (
                float(np.mean(low <= b2["report"]["intrabar_max_drawdown"] + 1e-12))
                if low is not None
                else None
            ),
            "trades_wanted": int(sum(md.wanted.values())),
            "trades_dropped": int(sum(md.dropped or [])),
            "draws_short": int(sum(1 for d in md.dropped or [] if d)),
        }
        trial("matched holding", "strategy",
              {"share_at_or_above": matched["share_at_or_above"]}, [seed])  # fmt: skip
    out["matched_holding"] = matched

    # --- shown: each member alone ---------------------------------------------------------
    progress("each member alone")
    book_marks_ = book_marks(path, order, closes)
    pbo_values = {"the book": _blocks(book_marks_)}
    alone: Dict[str, Dict[str, Any]] = {}
    for n in lookbacks:
        name = f"member {n} alone"
        seed = SHOWN_SEEDS[name]
        one = {n: by_member[n]}
        slices_n = ens.slices(one)
        p_n = ens.replay_trades(one, costs, deciding, detail=True)
        marks = book_marks(p_n, slices_n, closes)
        test = rpcd_runs(marks, seed)
        f = book_figures(slices_n, p_n, costs, deciding, gbp_usd)
        alone[str(n)] = {
            "figures": _compact(f),
            "by_coin": f["by_coin"],
            "trades_per_coin_year": int(p_n.trades[0]) / (len(coins) * years),
            "below_hold": (
                f["intrabar_max_drawdown"] < hold_fig["intrabar_max_drawdown"]
                if f["intrabar_max_drawdown"] is not None
                else None
            ),
            "rpcd_test": test,
            "p": test["p"],
        }
        pbo_values[name] = _blocks(marks)
        shown[name] = alone[str(n)]
        trial(name, "strategy", {"p": test["p"], "net_usd": float(p_n.net[0])}, [seed])
        progress(f"{name}: net {float(p_n.net[0]):+,.2f}, p = {test['p']:.4f}")
    out["members_alone"] = alone

    # --- shown: volatility-sized books (D4) ------------------------------------------------
    progress("volatility-sized books")
    sized: Dict[str, Dict[str, Any]] = {}
    for t in TARGETS:
        name = f"volatility {t:.0%}"
        seed = SHOWN_SEEDS[name]
        policy = sizing.VolatilityTarget(target=t, feature=SIZING_FEATURE)
        p_t = ens.replay_trades(by_member, costs, deciding, policy, detail=True)
        scales = {n: policy.scales(ens.sims[n], by_member[n]) for n in lookbacks}
        flat = np.concatenate([np.zeros(0)] + [scales[n].scale for n in lookbacks])
        marks = book_marks(p_t, order, closes)
        test = rpcd_runs(marks, seed)
        f = book_figures(order, p_t, costs, deciding, gbp_usd)
        sized[name] = {
            "policy": policy.record(),
            "figures": _compact(f),
            "mean_scale": float(flat.mean()) if len(flat) else None,
            "unsized": int(sum(scales[n].unsized for n in lookbacks)),
            "below_hold": (
                f["intrabar_max_drawdown"] < hold_fig["intrabar_max_drawdown"]
                if f["intrabar_max_drawdown"] is not None
                else None
            ),
            "rpcd_test": test,
            "p": test["p"],
        }
        shown[name] = sized[name]
        trial(name, "sizing", {"p": test["p"], "net_usd": float(p_t.net[0])}, [seed])
        progress(f"{name}: net {float(p_t.net[0]):+,.2f}")
    out["sizing"] = sized

    # --- shown: PBO across the seven members and the book --------------------------------------
    values = [v[0] for v in pbo_values.values()]
    weights = [v[1] for v in pbo_values.values()]
    out["pbo"] = {
        "contestants": list(pbo_values),
        "blocks": PBO_BLOCKS,
        "pbo": overfitting.pbo(values, weights),
    }

    # --- shown: robustness ---------------------------------------------------------------------
    progress("robustness")
    robust: Dict[str, Dict[str, Any]] = {}
    for v in VARIANTS:
        name = f"robust {v.name}"
        seed = SHOWN_SEEDS[name]
        group, use_coins, acct = ens, _coins_of(v, record), deciding
        c = costs
        group_closes = closes
        if v.fee is not None:
            c = Costs(v.fee, costs.allowance, costs.minimum_usd, costs.base_increment)
        if v.account_gbp is not None:
            acct = usd[v.account_gbp]
        if v.exchange == "second":
            if data.second is None or not data.second.frames:
                robust[v.name] = {
                    "run": False,
                    "reason": (
                        "no second exchange in Settings"
                        if data.second is None
                        else f"{data.second_exchange}'s cache has no development bars "
                        "for these coins"
                    ),
                    "left_out": dict(data.second_left_out),
                }
                continue
            group = ens_mod.Ensemble(data.second, lookbacks=lookbacks)
            group_closes = daily_closes(data.second)
        keep = set(use_coins or group.coins) & set(group.coins)
        if not keep:
            robust[v.name] = {"run": False, "reason": "none of its coins has bars"}
            continue
        mine = {
            n: [t for t in trades if t.coin in keep]
            for n, trades in group.trades(DEV_START_S).items()
        }
        slices_v = group.slices(mine)
        p_v = group.replay_trades(mine, c, acct, detail=True, coins=sorted(keep))
        h_fig, _h = _hold_figures(group, c, acct, gbp_usd, sorted(keep))
        f = book_figures(slices_v, p_v, c, acct, gbp_usd)
        marks = book_marks(p_v, slices_v, group_closes)
        test = rpcd_runs(marks, seed)
        robust[v.name] = {
            "run": True,
            "coins": sorted(keep),
            "account_usd": acct,
            "fee": c.fee,
            "figures": _compact(f),
            "hold": _compact(h_fig),
            "below_hold": (
                f["intrabar_max_drawdown"] < h_fig["intrabar_max_drawdown"]
                if f["intrabar_max_drawdown"] is not None
                and h_fig["intrabar_max_drawdown"] is not None
                else None
            ),
            "rpcd_test": test,
            "p": test["p"],
        }
        if v.exchange == "second":
            robust[v.name]["exchange"] = data.second_exchange
            robust[v.name]["left_out"] = dict(data.second_left_out)
        shown[name] = robust[v.name]
        trial(name, "strategy", {"p": test["p"], "net_usd": float(p_v.net[0])}, [seed],
              on=sorted(keep))  # fmt: skip
        progress(f"{name}: net {float(p_v.net[0]):+,.2f}, {int(p_v.trades[0])} trades")
    out["robustness"] = robust

    # --- Benjamini-Hochberg over the shown p-values ----------------------------------------------
    pairs = [(k, v["p"]) for k, v in shown.items() if v.get("p") is not None]
    flags = multiple.benjamini_hochberg([p for _k, p in pairs], BH_Q) if pairs else []
    out["shown_p"] = {
        k: {"p": float(p), "bh_flag": bool(f)} for (k, p), f in zip(pairs, flags)
    }

    # --- power, reported before the verdicts ---------------------------------------------------
    out["power"] = {
        "B1": {
            "smallest_detectable": b1.get("smallest_detectable"),
            "random_median": b1.get("median"),
            "too_few": b1.get("too_few"),
            "trades": b1.get("trades"),
            "lockbox_trades_projected": (
                b1.get("trades", 0) * LOCKBOX_DAYS / DEV_DAYS
                if b1.get("trades")
                else None
            ),
        },
        "B2": {
            "smallest_detectable": b2.get("smallest_detectable"),
            "smallest_detectable_lockbox": b2.get("smallest_detectable_lockbox"),
            "se": b2["test"].get("se"),
        },
        "hold comparison": comparison.get("power"),
        "alpha": HOLM_ALPHA,
        "k": K,
        "power": POWER,
        "development_days": DEV_DAYS,
        "lockbox_days": LOCKBOX_DAYS,
    }
    out["trial_counts"] = experiment.trial_counts() if log_trials else {}
    return out


def evidence_lines(result: Mapping[str, Any]) -> List[Any]:
    """B1's and B2's verdicts as ``strategy_lab.evidence`` lines, for "Model
    evidence..."."""
    from strategy_lab.evidence import Line

    period = (
        f"2021-01-01 to 2025-05-06, {len(result['coins'])} coins, 0.50% taker + 0.05% "
        "slippage, £10,000 (E2)"
    )
    recorded = f"{APPROVED}, development only"
    model = {
        "B1": "The ensemble of 7 channels (20 to 360 days) against random entries with "
        "each member's own exits",
        "B2": "The ensemble of 7 channels (20 to 360 days)",
    }
    return [
        Line(
            "STRAT-007",
            model[m.id],
            result["verdicts"][m.id]["kind"],
            result["verdicts"][m.id]["line"],
            period,
            recorded,
        )
        for m in MEMBERS
    ]
