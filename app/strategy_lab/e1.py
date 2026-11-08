"""
FDS-SR-001's first declared evaluation, E1 (sections 6.0 to 6.6; milestone M5c),
approved for registration and execution by the owner on 2026-11-08.

**What is declared** (``declaration``), before any result exists:

* **Three families** (section 6.2, decision E-D11), each corrected on its own by Holm at
  5%, with members fixed at the freeze:
  - **S, strategies alone** (K = 4): S1 STRAT-004 and S2 STRAT-005 against REF-RANDOM;
    S3 and S4 their economic tests (FDS-SIG-004 F3's requirements).
  - **G, the regime gate** (K = 3): STRAT-001, STRAT-004 and STRAT-005 with OVL-REGIME,
    against R3 at the gate's per-coin veto counts.
  - **M, models with strategies** (K = 2): STRAT-004 and STRAT-005 with
    ``pv.linear.t1.PV.q50``, against R3 at the model's per-coin veto counts.
* **Accounts** (E-D5): £10,000 decides; £500 and £50 are sensitivity runs on the same
  candles, trades and periods, each with its own minimum entries, sell rounding, cash
  and halt level.
* **Currency** (E-D6): one GBP-to-USD rate, read once at registration from a published
  reference rate and frozen in the record; never read during the replay.
* **Costs** (E-D10): 0.50% taker plus 0.05% slippage a fill decide. 1.20% taker and a
  hypothetical 0.60% maker rate are shown, with the same slippage. The orders stay market
  orders: the maker scenario does not mean a market order would be filled at a maker rate.
* **Windows** (E-D7): candles from 2020-01-01 for warm-up; the trades whose entry fills
  from 2021-01-01 are scored, to the development end, 2025-05-06. No bar opening on or
  after 2025-05-06 is read (``development_loader``): the lockbox stays closed.

**What is run** (``evaluate``): the nine members, then everything shown, which never
decides: section 6.3's figures for every cell, account and coin; the exploratory cells
(Benjamini-Hochberg at q = 0.10, never a pass); section 6.4's robustness trials, with PBO
over the parameter variants. Each scored cell is logged as a trial as soon as it is
scored. ``member_line`` words each verdict (section 6.6): only an economic line may say
"profitable", and every line ends "Development only: not evidence for enabling anything."

**The rules that decide, fixed here:**

* REF-RANDOM (``strategy_lab.baselines``): random entries replayed through the strategy's
  own exits, same waits in a random order, B = 10,000 as 10 runs of 1,000; p = (1 + #{draw
  >= the strategy}) / (B + 1) on return per capital-day.
* R3 (``strategy_lab.models``): per coin, as many random vetoes as the gate or model made
  among the trades it could assess and its own path could take; 10 runs of 1,000.
* The economic test: FDS-SIG-004's F3 at £10,000 and 0.50% (``findings.f3``): at least 100
  trades and 30 in each half, otherwise "Not assessable"; the day-block bootstrap of return
  per capital-day above 0 is the member; a profit in each half, a profit without the most
  profitable coin and a drawdown below the 8% halt level are its conditions.
* Block length (section 6.0): L = 28 x 2^k days, k the smallest integer >= 0 for which at
  most 1% of the family's scored trades last longer than L / 2 days (``block_length``).
* "Too few trades to tell" (FDS-MH-001's convention): a trading member that does not pass,
  whose smallest detectable edge, (z at 1 - 0.05/K plus z at 0.8) x the random draws'
  standard deviation, is above 50% of the random median's size.
"""

from __future__ import annotations

import functools
import hashlib
import math
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from model_lab import stats
from signal_fusion import labels as lb
from signal_fusion import meta
from signal_fusion.evaluation import baselines as sfb
from signal_fusion.evaluation import bootstrap as bs
from signal_fusion.evaluation import findings as fd
from signal_fusion.evaluation.replay import DAY_S, Account, Costs, Paths
from strategy_lab import baselines as bl
from strategy_lab import experiment
from strategy_lab import models as md
from strategy_lab.candidates import RunnerSpec, Trade
from strategy_lab.simulate import Simulation, Universe, load_universe, usd_accounts
from strategy_lab.windows import DEVELOPMENT, HISTORY_START, LOCKBOX, ReservedPeriod

EXPERIMENT_ID = "SR1-E1"
APPROVED = "2026-11-08"

# the market ---------------------------------------------------------------------------------
# FDS-MH-001 batch PV-1's 13 coins, as FDS-SIG-004's development run read them; BNB and
# HYPE have no bars before 2025-05-06 and are left out, with the reason recorded
COINS: Tuple[str, ...] = (
    "BTC", "ETH", "XRP", "BNB", "DOGE", "SOL", "ZEC", "DASH", "HYPE",
    "ADA", "AVAX", "LINK", "LTC",
)  # fmt: skip
REFERENCE = "BTC"  # the regime breakdown's reference coin (section 6.3)
DEV_START, DEV_END = DEVELOPMENT
DEV_START_S = int(DEV_START.timestamp())
DEV_END_S = int(DEV_END.timestamp())
LAST_S = DEV_END_S - 1  # the last scored second: the day before the lockbox

# costs and accounts ------------------------------------------------------------------------
FEE = 0.005
ALLOWANCE = 0.0005
FEE_SOURCE = (
    "the owner's account taker rate on Coinbase, 0.50% (E-D10; FDS-MH-001 section 7, "
    "from the check window on 2026-11-05)"
)
FEE_SCENARIOS: Tuple[Tuple[str, float, str], ...] = (
    ("taker 1.20%", 0.012, "Coinbase's published taker rate"),
    (
        "maker 0.60% (hypothetical)",
        0.006,
        "a limit-order scenario only: the orders stay market orders, which are not "
        "filled at a maker rate",
    ),
)
ACCOUNTS_GBP: Tuple[float, ...] = (10_000.0, 500.0, 50.0)
DECIDING_GBP = 10_000.0
HALT_PCT = 8.0

# tests ---------------------------------------------------------------------------------------
HOLM_ALPHA = 0.05
BH_Q = 0.10
POWER = 0.8
TOO_FEW = 0.5
RUNS = 10
PER_RUN = 1000  # the members' baselines: B = 10,000
SHOWN_PER_RUN = 100  # shown cells' baselines: B = 1,000
PBO_BLOCKS = 16
BASE_BLOCK_DAYS = 28
LONG_SHARE = 0.01

# strategies, the gate and the models -------------------------------------------------------
STRATEGIES: Dict[str, RunnerSpec] = {
    "STRAT-004": RunnerSpec("STRAT-004", {}, (), "1d"),
    "STRAT-005": RunnerSpec("STRAT-005", {}, (), "1d"),
    "STRAT-001": RunnerSpec("STRAT-001", {}, (), "1h"),
    "STRAT-000": RunnerSpec("STRAT-000", {}, (), "1h"),
    "STRAT-002": RunnerSpec("STRAT-002", {}, (), "4h"),
}
GATE: Dict[str, Any] = {"id": "OVL-REGIME", "params": {}}
MODEL_BATCH = "20261107-175558"  # FDS-MH-001 batch PV-1
MODEL_PV = "pv.linear.t1.PV.q50"
MODEL_P = "pv.linear.t1.P.q50"
MODEL_Q = 0.5
# as docs/dev/RUN-LOG-sig4-1.md recorded them
MODEL_SHA256 = {
    MODEL_P: "fab539dda03b3f5c7020d3ca8986bfe6268a5a6418e4ed8a5cf3201ce7aad62e",
    MODEL_PV: "ce72439610a93fb2e6ad4fa28915417c82bf2ff8f1b9957a98291ecf4dc25d03",
}


@dataclass(frozen=True)
class Member:
    """One declared, deciding test."""

    id: str
    family: str
    strategy: str
    layer: Optional[str]  # None, "OVL-REGIME" or a lab model's key
    test: str  # "random", "economic" or "r3"
    kind: str  # its trial kind
    seed: int
    question: str


MEMBERS: Tuple[Member, ...] = (
    Member(
        "S1", "S", "STRAT-004", None, "random", "strategy", 910_000,
        "Does STRAT-004 time its entries better than random entries with its own exits?",
    ),
    Member(
        "S2", "S", "STRAT-005", None, "random", "strategy", 920_000,
        "Does STRAT-005 time its entries better than random entries with its own exits?",
    ),
    Member(
        "S3", "S", "STRAT-004", None, "economic", "strategy", 970_000,
        "Is STRAT-004 profitable after fees at £10,000 and 0.50% + 0.05%?",
    ),
    Member(
        "S4", "S", "STRAT-005", None, "economic", "strategy", 971_000,
        "Is STRAT-005 profitable after fees at £10,000 and 0.50% + 0.05%?",
    ),
    Member(
        "G1", "G", "STRAT-001", "OVL-REGIME", "r3", "gate", 960_000,
        "Does the regime gate add value to STRAT-001 over random vetoes?",
    ),
    Member(
        "G2", "G", "STRAT-004", "OVL-REGIME", "r3", "gate", 961_000,
        "Does the regime gate add value to STRAT-004 over random vetoes?",
    ),
    Member(
        "G3", "G", "STRAT-005", "OVL-REGIME", "r3", "gate", 962_000,
        "Does the regime gate add value to STRAT-005 over random vetoes?",
    ),
    Member(
        "M1", "M", "STRAT-004", MODEL_PV, "r3", "model", 963_000,
        "Does the PV model's veto improve STRAT-004's entries over random vetoes?",
    ),
    Member(
        "M2", "M", "STRAT-005", MODEL_PV, "r3", "model", 964_000,
        "Does the PV model's veto improve STRAT-005's entries over random vetoes?",
    ),
)  # fmt: skip
FAMILIES: Dict[str, Tuple[str, int]] = {
    "S": ("Strategies alone", 4),
    "G": ("The regime gate", 3),
    "M": ("Models with strategies", 2),
}

# the shown cells' seeds: each a range of its own (``seed_ranges``)
SHOWN_SEEDS: Dict[str, int] = {
    "random STRAT-000": 930_000,
    "random STRAT-001": 940_000,
    "random STRAT-002": 950_000,
    "r3 STRAT-000 + OVL-REGIME": 965_000,
    "r3 STRAT-002 + OVL-REGIME": 965_100,
    "r3 STRAT-004 + P": 965_200,
    "r3 STRAT-005 + P": 965_300,
    "r3 STRAT-001 + PV": 965_400,
    "r3 STRAT-001 + P": 965_500,
    "r3 STRAT-004 + F_PV": 965_600,
    "r3 STRAT-004 + F_P": 965_700,
    "r3 STRAT-005 + F_PV": 965_800,
    "r3 STRAT-005 + F_P": 965_900,
    "paired STRAT-004 PV vs P": 972_000,
    "paired STRAT-005 PV vs P": 972_100,
    "calibration STRAT-004 F_PV": 974_000,
    "calibration STRAT-005 F_PV": 974_100,
    "random STRAT-004 at £500": 990_000,
    "random STRAT-004 at £50": 991_000,
    "random STRAT-005 at £500": 992_000,
    "random STRAT-005 at £50": 993_000,
}
VARIANT_SEED = 1_000_000  # robustness variant i draws from VARIANT_SEED + 1000 i


@dataclass(frozen=True)
class Variant:
    """A robustness trial (section 6.4): shown, never deciding."""

    name: str
    strategy: str
    params: Mapping[str, Any]
    overlays: Tuple[Mapping[str, Any], ...]
    timeframe: str
    coins: Optional[str]  # None: every coin; "BTC+ETH"; "listed_by_2021"
    pbo_set: Optional[str]

    def spec(self) -> RunnerSpec:
        return RunnerSpec(
            self.strategy,
            dict(self.params),
            tuple(dict(o) for o in self.overlays),
            self.timeframe,
        )


def _gate(days: int) -> Tuple[Mapping[str, Any], ...]:
    return ({"id": "OVL-REGIME", "params": {"sma_days": days}},)


_P4 = "STRAT-004 parameters"
_P5 = "STRAT-005 decision interval"
VARIANTS: Tuple[Variant, ...] = (
    Variant("STRAT-004 entry 20 / exit 10", "STRAT-004", {"entry_days": 20, "exit_days": 10}, (), "1d", None, _P4),
    Variant("STRAT-004 entry 55 / exit 10", "STRAT-004", {"entry_days": 55, "exit_days": 10}, (), "1d", None, _P4),
    Variant("STRAT-004 entry 100 / exit 10", "STRAT-004", {"entry_days": 100, "exit_days": 10}, (), "1d", None, _P4),
    Variant("STRAT-004 entry 100 / exit 20", "STRAT-004", {"entry_days": 100, "exit_days": 20}, (), "1d", None, _P4),
    Variant("STRAT-005 every 28 days", "STRAT-005", {"rebalance_days": 28}, (), "1d", None, _P5),
    Variant("STRAT-004 + OVL-REGIME 100 days", "STRAT-004", {}, _gate(100), "1d", None, "OVL-REGIME with STRAT-004"),
    Variant("STRAT-004 + OVL-REGIME 300 days", "STRAT-004", {}, _gate(300), "1d", None, "OVL-REGIME with STRAT-004"),
    Variant("STRAT-005 + OVL-REGIME 100 days", "STRAT-005", {}, _gate(100), "1d", None, "OVL-REGIME with STRAT-005"),
    Variant("STRAT-005 + OVL-REGIME 300 days", "STRAT-005", {}, _gate(300), "1d", None, "OVL-REGIME with STRAT-005"),
    Variant("STRAT-001 + OVL-REGIME 100 days", "STRAT-001", {}, _gate(100), "1h", None, "OVL-REGIME with STRAT-001"),
    Variant("STRAT-001 + OVL-REGIME 300 days", "STRAT-001", {}, _gate(300), "1h", None, "OVL-REGIME with STRAT-001"),
    Variant("STRAT-004 on 12h candles", "STRAT-004", {}, (), "12h", None, None),
    Variant("STRAT-004 on 4h candles", "STRAT-004", {}, (), "4h", None, None),
    Variant("STRAT-005 on 12h candles", "STRAT-005", {}, (), "12h", None, None),
    Variant("STRAT-005 on 4h candles", "STRAT-005", {}, (), "4h", None, None),
    Variant("STRAT-004, BTC and ETH only", "STRAT-004", {}, (), "1d", "BTC+ETH", None),
    Variant("STRAT-005, BTC and ETH only", "STRAT-005", {}, (), "1d", "BTC+ETH", None),
    Variant("STRAT-004, coins with bars from 2021-01-01", "STRAT-004", {}, (), "1d", "listed_by_2021", None),
    Variant("STRAT-005, coins with bars from 2021-01-01", "STRAT-005", {}, (), "1d", "listed_by_2021", None),
)  # fmt: skip
# the main cells each parameter set's PBO includes beside its variants
PBO_MAIN = {
    _P4: "STRAT-004",
    _P5: "STRAT-005",
    "OVL-REGIME with STRAT-004": "G2",
    "OVL-REGIME with STRAT-005": "G3",
    "OVL-REGIME with STRAT-001": "G1",
}
NOT_RUN = {
    "STRAT-004 entry 20 / exit 20": "its exit_days must be below its entry_days",
    "exchanges": (
        "Kraken, second in the Settings order, serves only its latest 720 bars of a "
        "series: they do not reach the development period, and reading them would read "
        "the reserved months"
    ),
    "the volatility shrink": (
        "it needs FDS-SIG-004's hourly volatility estimate per trade, which E1 does not "
        "build; recorded for a later declared run"
    ),
}


class E1Error(RuntimeError):
    """E1 cannot be run as declared."""


# --- the declaration -----------------------------------------------------------------------


def seed_ranges() -> Dict[str, Tuple[int, int]]:
    """Every seed range E1 draws from, [first, last]: none may overlap."""
    out: Dict[str, Tuple[int, int]] = {}
    for m in MEMBERS:
        width = RUNS * PER_RUN if m.test == "random" else RUNS
        out[m.id] = (m.seed, m.seed + width - 1)
    for name, seed in SHOWN_SEEDS.items():
        width = RUNS * SHOWN_PER_RUN if name.startswith("random") else RUNS
        out[name] = (seed, seed + width - 1)
    for i, v in enumerate(VARIANTS):
        seed = VARIANT_SEED + 1000 * i
        out[v.name] = (seed, seed + RUNS * SHOWN_PER_RUN - 1)
    return out


def check_declaration() -> None:
    """The families' sizes, the members' tests and the seeds, as declared."""
    for family, (_name, k) in FAMILIES.items():
        n = sum(1 for m in MEMBERS if m.family == family)
        if n != k:
            raise E1Error(f"family {family} has {n} members, {k} declared")
    if len({m.id for m in MEMBERS}) != len(MEMBERS):
        raise E1Error("member ids repeat")
    spans = sorted(seed_ranges().values())
    for (a, b), (c, _d) in zip(spans, spans[1:]):
        if c <= b:
            raise E1Error(f"seed ranges overlap at {c}")
    for v in VARIANTS:
        p = dict(v.params)
        if p.get("exit_days", 0) >= p.get("entry_days", 10**9):
            raise E1Error(f"{v.name}: exit_days must be below entry_days")


def family_k(family: str) -> int:
    return FAMILIES[family][1]


def declaration(
    rate: Mapping[str, Any],
    venue: Mapping[str, Any],
    series_sha256: Mapping[str, str],
    coins_kept: Sequence[str],
    left_out: Mapping[str, str],
    exchange_order: Sequence[str],
    listed_by_2021: Sequence[str],
    probabilities_sha256: Mapping[str, str],
    served_by: Mapping[str, str],
) -> Dict[str, Any]:
    """E1's record, frozen by ``experiment.freeze`` before anything is scored.
    ``served_by`` names the exchange whose cache gave each series (the exchange layer
    chooses it: the first in Settings order that holds the range)."""
    check_declaration()
    gbp_usd = float(rate["gbp_usd"])
    default = Account()
    return {
        "approved": APPROVED,
        "authority": (
            "registration and execution of the declared development experiments only; "
            "no paper or live activation, no promotion, the lockbox stays closed"
        ),
        "family": {
            f: {
                "name": name,
                "members": [m.id for m in MEMBERS if m.family == f],
                "k": k,
                "correction": "Holm",
                "alpha": HOLM_ALPHA,
            }
            for f, (name, k) in FAMILIES.items()
        },
        "members": [asdict(m) for m in MEMBERS],
        "strategy": {
            **{
                sid: experiment.strategy_record(sid, spec.params, (), spec.timeframe)
                for sid, spec in STRATEGIES.items()
            },
            "gate": experiment.strategy_record("STRAT-004", {}, (GATE,), "1d")[
                "overlays"
            ][0],
        },
        "models": {
            "batch": MODEL_BATCH,
            "keys": {"PV": MODEL_PV, "P": MODEL_P},
            "sha256": dict(probabilities_sha256),
            "threshold": (
                f"q = {MODEL_Q}: a trade is vetoed when the model's probability at its "
                "decision hour is below the 0.5-quantile of every probability the model "
                "gave before the decision's calendar month, all coins pooled; not "
                f"assessable before {md.MIN_HISTORY} probabilities exist "
                "(strategy_lab.models.forecast_filter)"
            ),
            "strategy_specific": (
                "F_P and F_PV refitted on each strategy's own candidate trades "
                "(strategy_lab.models.meta_filter), labels at 0.50% + 0.05%, pooled "
                "payoffs, FDS-MH-001's development folds; not assessable below 200 "
                "events or 200 non-events (shown only)"
            ),
        },
        "market": {
            "exchange_order": list(exchange_order),
            "served_by": dict(sorted(served_by.items())),
            "coins": list(COINS),
            "coins_with_development_bars": list(coins_kept),
            "left_out": dict(left_out),
            "listed_by_2021": list(listed_by_2021),
            "timeframes": sorted(
                {s.timeframe for s in STRATEGIES.values()}
                | {v.timeframe for v in VARIANTS}
            ),
            "offline": True,
            "series_sha256": dict(series_sha256),
            "candles": (
                "read once per (coin, timeframe) from the exchange layer's cache, from "
                "2020-01-01 or the coin's first cached bar, to 2025-05-06 (exclusive)"
            ),
        },
        "windows": {
            "history_from": HISTORY_START.date().isoformat(),
            "development": [DEV_START.date().isoformat(), DEV_END.date().isoformat()],
            "scored": "trades whose entry fills from 2021-01-01 to 2025-05-06",
            "lockbox": [LOCKBOX[0].date().isoformat(), LOCKBOX[1].date().isoformat()],
            "lockbox_read": False,
            "folds": [list(f) for f in md.development_folds()],
        },
        "costs": {
            "fee": FEE,
            "fee_source": FEE_SOURCE,
            "allowance": ALLOWANCE,
            "applied": "to every entry and exit fill, once (the replay's m(f, e))",
            "proportional": "no fixed fee an order (an assumption)",
            "scenarios": [
                {"name": n, "fee": f, "allowance": ALLOWANCE, "note": note}
                for n, f, note in FEE_SCENARIOS
            ],
            "minimum_usd": dict(venue.get("minimum_usd") or {}),
            "base_increment": dict(venue.get("base_increment") or {}),
            "venue_unknown": dict(venue.get("unknown") or {}),
            "venue_read_at": venue.get("read_at"),
            "venue_note": "today's Coinbase product data; past values are not recorded",
        },
        "accounts": {
            "gbp": list(ACCOUNTS_GBP),
            "deciding_gbp": DECIDING_GBP,
            "gbp_usd": gbp_usd,
            "rate": dict(rate),
            "usd": {str(k): v for k, v in usd_accounts(ACCOUNTS_GBP, gbp_usd).items()},
            "sizing": {
                "start_allocation_pct": default.start_pct,
                "max_coin_pct": default.max_coin_pct,
                "min_order_margin_pct": default.margin_pct,
                "halt_pct": HALT_PCT,
                "halt": "reported, not modelled",
            },
        },
        "baselines": {
            "REF-RANDOM": (
                "random entries replayed through the strategy's own exits, the same "
                "waits per coin in a random order (strategy_lab.baselines); draw b "
                "seeded seed + b; members 10 runs of 1,000, shown cells 10 runs of 100"
            ),
            "R3": (
                "per coin, as many random vetoes as the gate or model made among the "
                "trades it could assess and its path could take; run r seeded seed + r; "
                "members 10 runs of 1,000, shown cells 10 runs of 100"
            ),
            "REF-HOLD": "each coin bought once at its first decision bar, held to the end",
            "REF-CASH": "no trades",
        },
        "tests": {
            "holm_alpha": HOLM_ALPHA,
            "exploratory": f"Benjamini-Hochberg at q = {BH_Q}, shown, never a pass",
            "statistic": "return per capital-day: summed net / summed (amount x days held)",
            "random_p": "(1 + #{draw >= value}) / (B + 1), pooled; each run's p shown",
            "economic": "FDS-SIG-004 F3 (signal_fusion.evaluation.findings.f3)",
            "bootstrap": "day blocks, circular, all coins together, 10 runs of 1,000",
            "block_rule": "L = 28 x 2^k days: at most 1% of the family's trades longer than L / 2",
            "too_few": (
                "a trading member that does not pass, whose smallest detectable edge is "
                "above 50% of |the random median|"
            ),
            "power": POWER,
            "seeds": {m.id: m.seed for m in MEMBERS},
            "shown_seeds": dict(SHOWN_SEEDS),
            "variant_seed": VARIANT_SEED,
        },
        "robustness": {
            "variants": [
                {**asdict(v), "params": dict(v.params), "overlays": list(v.overlays)}
                for v in VARIANTS
            ],
            "pbo": {
                "blocks": PBO_BLOCKS,
                "sets": sorted({v.pbo_set for v in VARIANTS if v.pbo_set}),
                "main": dict(PBO_MAIN),
            },
            "not_run": dict(NOT_RUN),
        },
        "execution": (
            "market orders: an entry fills at the next bar's open after the decision, an "
            "exit at the next open after the exit decision; a trade open at the end is "
            "closed at the last close"
        ),
    }


# --- the candles --------------------------------------------------------------------------


Loader = Callable[..., pd.DataFrame]


def _utc(t) -> pd.Timestamp:
    ts = pd.Timestamp(t)
    return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")


@functools.lru_cache(maxsize=1)
def settings_exchanges() -> Tuple[str, ...]:
    """The exchanges in Settings order, primary first: the exchange layer's, as the
    candle loader reads them."""
    from market_data.candles import _exchange_manager

    return tuple(_exchange_manager().exchange_names())


def first_cached(
    symbol: str,
    tf: str,
    cache_dir: Optional[str] = None,
    exchanges: Optional[Sequence[str]] = None,
) -> Optional[pd.Timestamp]:
    """The first bar of ``symbol`` and ``tf`` in the cache of the first exchange, in
    Settings order, whose cache holds the series."""
    from market_data.candles import _read_cache, cache_path

    for name in settings_exchanges() if exchanges is None else exchanges:
        frame = _read_cache(cache_path(symbol, tf, cache_dir, name))
        if not frame.empty:
            return _utc(frame["open_time"].iloc[0])
    return None


def served_by(data: "Data") -> Dict[str, str]:
    """The exchange that gave each series, as the exchange layer recorded it."""
    out: Dict[str, str] = {}
    for u in data.universes.values():
        for key, attrs in u.sources.items():
            out[key] = str((attrs or {}).get("exchange") or "")
    return dict(sorted(out.items()))


def development_loader(
    base: Optional[Loader] = None,
    first: Optional[Callable[[str, str], Optional[pd.Timestamp]]] = None,
    offline: bool = True,
) -> Loader:
    """A candle loader that reads each (coin, timeframe, period) once, from 2020-01-01 or
    the coin's first cached bar, and refuses anything reaching the reserved months."""
    if base is None:
        from market_data.candles import exchange_candles as base
    first = first or first_cached
    memo: Dict[tuple, pd.DataFrame] = {}

    def load(symbol, tf, start, end, cache_dir=None, offline_=None, **_kw):
        a = max(_utc(start), HISTORY_START)
        b = _utc(end)
        if b > DEV_END:
            raise ReservedPeriod(
                f"{symbol} {tf}: E1 reads nothing after {DEV_END.date()}"
            )
        listed = first(symbol, tf)
        if listed is None:
            raise E1Error(f"{symbol} {tf}: no cached bars")
        a = max(a, listed)
        if not a < b:
            raise E1Error(f"{symbol} {tf}: no bars before {DEV_END.date()}")
        key = (symbol, tf, a, b)
        if key not in memo:
            frame = base(symbol, tf, a, b, cache_dir=cache_dir, offline=offline)
            if len(frame) and _utc(frame["open_time"].max()) >= DEV_END:
                raise ReservedPeriod(
                    f"{symbol} {tf}: a bar opens in the reserved months"
                )
            memo[key] = frame
        return memo[key]

    load.memo = memo  # type: ignore[attr-defined]
    return load


def development_universe(
    coins: Sequence[str], timeframe: str, loader: Loader
) -> Tuple[Universe, Dict[str, str]]:
    """Every coin with development bars at ``timeframe``, with the gate's context (BTC's
    daily bars); the coins left out, with the reason."""
    kept: List[str] = []
    left: Dict[str, str] = {}
    for coin in coins:
        try:
            frame = loader(f"{coin}-USD", timeframe, HISTORY_START, DEV_END)
        except ReservedPeriod:
            raise
        except Exception as exc:  # recorded per coin, never silently
            left[coin] = str(exc)
            continue
        if len(frame) < 2:
            left[coin] = "fewer than 2 development bars"
            continue
        kept.append(coin)
    spec = RunnerSpec("STRAT-004", {}, (GATE,), timeframe)
    start = HISTORY_START.date().isoformat()  # load_universe localises a plain date
    return load_universe(kept, spec, start, DEV_END, loader=loader), left


def frame_sha256(frame: pd.DataFrame) -> str:
    """The SHA-256 of a frame's bars (open time in ms, then the prices and volume)."""
    f = frame[["open_time", "open", "high", "low", "close", "volume"]].copy()
    f["open_time"] = (
        pd.to_datetime(f["open_time"], utc=True) - pd.Timestamp(0, tz="UTC")
    ) // pd.Timedelta(milliseconds=1)
    text = f.to_csv(index=False, lineterminator="\n", float_format="%.12g")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def universe_sha256(universe: Universe) -> Dict[str, str]:
    out = {
        f"{coin}:{universe.timeframe}": frame_sha256(frame)
        for coin, frame in universe.frames.items()
    }
    for (ref, tf), frame in universe.shared.items():
        out[f"{ref}:{tf}"] = frame_sha256(frame)
    return out


# --- costs, accounts and trades ---------------------------------------------------------------


def costs_for(record: Mapping[str, Any], fee: float = FEE) -> Costs:
    c = record["costs"]
    return Costs(
        fee=float(fee),
        allowance=float(c["allowance"]),
        minimum_usd={k: float(v) for k, v in (c.get("minimum_usd") or {}).items()},
        base_increment={
            k: float(v) for k, v in (c.get("base_increment") or {}).items()
        },
    )


def accounts_for(record: Mapping[str, Any]) -> Dict[float, Account]:
    usd = record["accounts"]["usd"]
    return {
        g: Account(start=float(usd[str(g)]), halt_pct=HALT_PCT) for g in ACCOUNTS_GBP
    }


def scored(sim: Simulation, coins: Optional[Sequence[str]] = None) -> List[Trade]:
    """The candidate trades whose entry fills in the development period."""
    keep = None if coins is None else set(coins)
    return [
        t
        for t in sim.candidates()
        if t.entry_s >= DEV_START_S and (keep is None or t.coin in keep)
    ]


def taken(trades: Sequence[Trade], path: Paths) -> List[Trade]:
    return [trades[i] for i, *_ in path.detail]


def path_rows(trades: Sequence[Trade], path: Paths) -> List[Tuple[int, float, float]]:
    """(entry time, net, capital-days) of path 0's trades."""
    return [(trades[i].entry_s, net, days) for i, _a, net, days in path.detail]


def block_length(trade_days: Sequence[float]) -> int:
    """Section 6.0: L = 28 x 2^k days, k the smallest integer >= 0 for which at most 1% of
    the trades last longer than L / 2 days."""
    d = np.asarray(list(trade_days), dtype=float)
    length = BASE_BLOCK_DAYS
    if not len(d):
        return length
    while np.mean(d > length / 2.0) > LONG_SHARE:
        length *= 2
    return length


def gate_filter(plain: Sequence[Trade], gated: Simulation) -> md.Filter:
    """OVL-REGIME as a veto on the strategy's own candidate trades: a trade is vetoed when
    the gated runner, flat, would not have entered on its decision bar. The gate only
    removes entries, so every trade it keeps is the same trade; a difference is an error.
    """
    kept = {(t.coin, t.decided): t for t in scored(gated)}
    keys = {(t.coin, t.decided) for t in plain}
    extra = sorted(k for k in kept if k not in keys)
    if extra:
        raise E1Error(f"the gate made trades the strategy does not: {extra[:3]}")
    veto = np.zeros(len(plain), dtype=bool)
    for i, t in enumerate(plain):
        g = kept.get((t.coin, t.decided))
        if g is None:
            veto[i] = True
        elif (g.entry_s, g.exit_s, g.entry_price, g.exit_price) != (
            t.entry_s,
            t.exit_s,
            t.entry_price,
            t.exit_price,
        ):
            raise E1Error(f"the gate changed {t.coin}'s trade from bar {t.decided}")
    n = len(plain)
    return md.Filter(
        "OVL-REGIME",
        veto,
        np.ones(n, dtype=bool),
        np.full(n, np.nan),
        {"rule": "the gated runner's own entries", "vetoed": int(veto.sum())},
    )


# --- the tests ------------------------------------------------------------------------------


def _summary(value: float, draws: np.ndarray, k: int) -> Dict[str, Any]:
    d = np.atleast_2d(np.asarray(draws, dtype=float))
    median = float(np.median(d))
    edge = fd.smallest_detectable(d, k, HOLM_ALPHA, POWER)
    per_run = [sfb.upper_p(value, row) for row in d]
    return {
        "value": float(value),
        "p": sfb.upper_p(value, d),
        "runs": per_run,
        "spread": float(max(per_run) - min(per_run)) if per_run else 0.0,
        "median": median,
        "percentiles": [float(x) for x in np.percentile(d, [5, 25, 75, 95])],
        "share_at_or_above": float(np.mean(d >= value)),
        "smallest_detectable": edge,
        "too_few": bool(not np.isfinite(edge) or edge > TOO_FEW * abs(median)),
        "draws": int(d.size),
        "k": int(k),
    }


def random_test(
    sim: Simulation,
    trades: Sequence[Trade],
    path: Paths,
    costs: Costs,
    account: Account,
    seed: int,
    per_run: int,
    k: int,
) -> Dict[str, Any]:
    """The strategy's path against REF-RANDOM (its own exits), on return per capital-day."""
    mine = taken(trades, path)
    if not mine:
        return {"assessable": False, "reason": "the path made no trades"}
    from_s = DEV_START_S - sim.spec.bar_seconds  # the bar whose close is 2021-01-01
    draws = bl.random_draws(sim, mine, seed, RUNS * per_run, from_s)
    rp = bl.replay_draws(sim, draws.draws, costs, account)
    out = _summary(float(path.rpcd[0]), rp.rpcd.reshape(RUNS, per_run), k)
    out.update(
        {
            "assessable": True,
            "seed": int(seed),
            "trades": len(mine),
            "net_usd": float(path.net[0]),
            "median_net_usd": float(np.median(rp.net)),
            "entries_wanted": int(draws.wanted),
            "entries_reached_median": float(np.median(draws.reached)),
        }
    )
    return out


def r3_test(
    sim: Simulation,
    trades: Sequence[Trade],
    filt: md.Filter,
    costs: Costs,
    account: Account,
    seed: int,
    per_run: int,
    k: int,
) -> Tuple[Dict[str, Any], Paths]:
    """The filter's path against R3 at its per-coin veto counts."""
    path = md.cell(sim, trades, costs, account, filt, detail=True)
    cand = [i for i in path.eligible() if filt.assessable[i]]
    vetoed = [i for i, s in enumerate(path.status) if s == "vetoed"]
    counts = sfb.veto_counts([t.coin for t in trades], cand, vetoed)
    if not trades or not cand:
        return {
            "assessable": False,
            "reason": "no trade the filter could assess was open to the path",
            "veto_counts": counts,
        }, path
    values = []
    for run in range(RUNS):
        v = md.random_vetoes(trades, filt, cand, seed, run, per_run)
        values.append(sim.replay(trades, costs, account, veto=v).rpcd)
    out = _summary(float(path.rpcd[0]), np.vstack(values), k)
    out.update(
        {
            "assessable": True,
            "seed": int(seed),
            "veto_counts": counts,
            "vetoed": int(len(vetoed)),
            "candidates": int(len(cand)),
            "assessed": int(np.sum(filt.assessable)),
            "trades": int(path.trades[0]),
            "net_usd": float(path.net[0]),
        }
    )
    return out, path


def economic_test(
    path: Paths, trades: Sequence[Trade], seed: int, block: int, k: int
) -> Dict[str, Any]:
    """FDS-SIG-004's F3 for the path, with the bootstrap's smallest detectable return."""
    out = fd.f3(
        path,
        [t.entry_s for t in trades],
        [t.coin for t in trades],
        DEV_START_S,
        LAST_S,
        seed,
        HALT_PCT,
        block,
    )
    rows = path_rows(trades, path)
    if rows:
        sums = bs.day_sums(
            [r[0] for r in rows], [[r[1] for r in rows], [r[2] for r in rows]],
            DEV_START_S, LAST_S,
        )  # fmt: skip
        draws = bs.Bootstrap(sums.days, seed, block).draws(sums, bs.ratio(0, 1))
        out["smallest_detectable"] = fd.smallest_detectable(draws, k, HOLM_ALPHA, POWER)
    else:
        out["smallest_detectable"] = float("nan")
    out["block_days"] = int(block)
    return out


def auc(score, label) -> Optional[float]:
    """The probability that a random event outscores a random non-event (ties half)."""
    s = np.asarray(score, dtype=float)
    y = np.asarray(label, dtype=int)
    ok = np.isfinite(s) & (y >= 0)
    s, y = s[ok], y[ok]
    pos, neg = int(np.sum(y == 1)), int(np.sum(y == 0))
    if not pos or not neg:
        return None
    ranks = pd.Series(s).rank(method="average").to_numpy()
    return float((ranks[y == 1].sum() - pos * (pos + 1) / 2.0) / (pos * neg))


# --- figures (section 6.3) ------------------------------------------------------------------


class Regimes:
    """Each trade's market context at its decision (section 6.3): BTC above or below its
    200-day average; that average rising or falling over 30 days; the coin's 30-day
    volatility; the year. From daily bars closed by the decision."""

    def __init__(self, daily: Mapping[str, pd.DataFrame], reference: str = REFERENCE):
        self._close_s: Dict[str, np.ndarray] = {}
        self._close: Dict[str, np.ndarray] = {}
        for coin, frame in daily.items():
            closes_at = pd.to_datetime(frame["open_time"], utc=True) + pd.Timedelta(
                days=1
            )
            self._close_s[coin] = (
                (closes_at - pd.Timestamp(0, tz="UTC")) // pd.Timedelta(seconds=1)
            ).to_numpy(dtype=np.int64)
            self._close[coin] = frame["close"].to_numpy(dtype=float)
        self.reference = reference

    def _last(self, coin: str, t: int) -> int:
        if coin not in self._close_s:
            return -1
        return int(np.searchsorted(self._close_s[coin], int(t), side="right")) - 1

    def tags(self, trade: Trade) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "year": str(pd.Timestamp(trade.entry_s, unit="s", tz="UTC").year)
        }
        k = self._last(self.reference, trade.entry_s)
        c = self._close.get(self.reference)
        if c is not None and k >= 199:
            sma = float(c[k - 199 : k + 1].mean())
            out["btc_trend"] = "above" if c[k] > sma else "below"
            if k >= 229:
                before = float(c[k - 229 : k - 29].mean())
                out["btc_average"] = "rising" if sma > before else "falling"
        j = self._last(trade.coin, trade.entry_s)
        own = self._close.get(trade.coin)
        if own is not None and j >= 30:
            r = np.diff(np.log(own[j - 30 : j + 1]))
            out["volatility"] = float(np.std(r) * math.sqrt(365.0))
        return out


def _breakdown(rows, tags: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Trades, net and return per capital-day by year, trend, average and volatility."""
    out: Dict[str, Dict[str, Any]] = {}
    vols = [t["volatility"] for t in tags if "volatility" in t]
    cuts = np.quantile(vols, [1 / 3, 2 / 3]) if len(vols) >= 3 else None
    for (_i, _amount, net, days), tag in zip(rows, tags):
        groups = {
            "year": tag["year"],
            "btc_trend": tag.get("btc_trend", "unknown"),
            "btc_average": tag.get("btc_average", "unknown"),
        }
        if cuts is not None and "volatility" in tag:
            v = tag["volatility"]
            groups["volatility"] = (
                "low" if v <= cuts[0] else ("middle" if v <= cuts[1] else "high")
            )
        else:
            groups["volatility"] = "unknown"
        for dim, bucket in groups.items():
            cell = out.setdefault(dim, {}).setdefault(
                bucket, {"trades": 0, "net_usd": 0.0, "capital_days": 0.0}
            )
            cell["trades"] += 1
            cell["net_usd"] += float(net)
            cell["capital_days"] += float(days)
    for dim in out.values():
        for cell in dim.values():
            cd = cell["capital_days"]
            cell["rpcd"] = cell["net_usd"] / cd if cd > 0 else 0.0
    if cuts is not None:
        out.setdefault("volatility", {})["cuts"] = [float(x) for x in cuts]
    return out


def figures(
    trades: Sequence[Trade],
    path: Paths,
    costs: Costs,
    account: Account,
    gbp_usd: float,
    regimes: Optional[Regimes] = None,
) -> Dict[str, Any]:
    """Section 6.3's figures for path 0 of a ``replay(..., detail=True)``."""
    rows = path.detail
    mine = taken(trades, path)
    n = len(rows)
    amount = np.array([r[1] for r in rows], dtype=float)
    net = np.array([r[2] for r in rows], dtype=float)
    days = np.array([r[3] for r in rows], dtype=float)
    held = np.array([(t.exit_s - t.entry_s) / DAY_S for t in mine], dtype=float)
    total = float(net.sum())
    window = (DEV_END_S - DEV_START_S) / DAY_S
    roe = total / account.start
    first_day, last_day = DEV_START_S // DAY_S, LAST_S // DAY_S
    middle = first_day + (last_day - first_day + 1) // 2
    second = np.array([t.entry_s // DAY_S >= middle for t in mine], dtype=bool)
    by_year: Dict[str, Dict[str, float]] = {}
    by_coin: Dict[str, Dict[str, float]] = {}
    for t, x, d in zip(mine, net, days):
        y = str(pd.Timestamp(t.entry_s, unit="s", tz="UTC").year)
        for table, key in ((by_year, y), (by_coin, t.coin)):
            cell = table.setdefault(
                key, {"trades": 0, "net_usd": 0.0, "capital_days": 0.0}
            )
            cell["trades"] += 1
            cell["net_usd"] += float(x)
            cell["capital_days"] += float(d)
    for table in (by_year, by_coin):
        for cell in table.values():
            cd = cell["capital_days"]
            cell["rpcd"] = cell["net_usd"] / cd if cd > 0 else 0.0
    floors = {c: costs.floor(c, account.margin_pct) for c in {t.coin for t in mine}}
    raised = sum(
        1
        for t, a in zip(mine, amount)
        if floors[t.coin] and abs(a - floors[t.coin]) <= 1e-6 * floors[t.coin]
    )
    stepped = sum(1 for t in mine if (costs.base_increment.get(t.coin) or 0) > 0)
    curve = path.curve
    dd = fd.drawdown_details(curve[0], curve[1]) if curve is not None else {}
    recovery = (
        (dd["recovered_s"] - dd["start_s"]) / DAY_S
        if dd.get("recovered_s") is not None
        else None
    )
    out = {
        "trades": n,
        "net_usd": total,
        "net_gbp": total / gbp_usd,
        "rpcd": float(path.rpcd[0]),
        "return_on_account": roe,
        "annualised": (1 + roe) ** (365.0 / window) - 1 if roe > -1 else float("nan"),
        "max_drawdown": float(path.max_drawdown[0]),
        "max_drawdown_usd": float(path.max_drawdown_usd[0]),
        "drawdown": dd,
        "recovery_days": recovery,
        "trades_by_half": [int(np.sum(~second)), int(np.sum(second))],
        "net_by_half": [float(net[~second].sum()), float(net[second].sum())],
        "by_year": by_year,
        "by_coin": by_coin,
        "holding_days_median": float(np.median(held)) if n else None,
        "holding_days_p90": float(np.percentile(held, 90)) if n else None,
        "win_rate": float(np.mean(net > 0)) if n else None,
        "largest_loss_usd": float(net.min()) if n else None,
        "time_in_market": float(path.time_in_market[0]),
        "mean_committed": float(path.mean_committed[0]),
        "peak_committed": float(path.peak_committed[0]),
        "entries_raised_to_minimum": int(raised),
        "sells_rounded_to_step": int(stepped),
        "skipped_cash": int(path.skipped_cash[0]),
        "skipped_minimum": int(path.skipped_minimum[0]),
        "unsold_remainder_usd": (
            float(path.dust_usd[0]) if path.dust_usd is not None else 0.0
        ),
        "final_equity_usd": float(path.final_equity[0]),
        "halt": {
            "reached_s": int(path.halt_s[0]),
            "exposure_usd": (
                float(path.halt_exposure[0]) if path.halt_exposure is not None else 0.0
            ),
            "further_loss_30d_usd": (
                float(path.halt_further_loss[0])
                if path.halt_further_loss is not None
                else 0.0
            ),
        },
    }
    if regimes is not None:
        out["by_regime"] = _breakdown(rows, [regimes.tags(t) for t in mine])
    return out


def compact(f: Mapping[str, Any]) -> Dict[str, Any]:
    """The few figures a table row needs."""
    keys = (
        "trades", "net_usd", "net_gbp", "rpcd", "return_on_account", "max_drawdown",
        "time_in_market", "mean_committed", "skipped_cash", "skipped_minimum",
        "entries_raised_to_minimum", "unsold_remainder_usd",
    )  # fmt: skip
    return {k: f.get(k) for k in keys}


def pbo_blocks(trades: Sequence[Trade], path: Paths) -> Tuple[List[float], List[float]]:
    """A path's net and capital-days in each of the 16 development blocks."""
    net = np.zeros(PBO_BLOCKS)
    held = np.zeros(PBO_BLOCKS)
    rows = path.detail
    if rows:
        b = stats.block_of(
            [trades[i].entry_s for i, *_ in rows], DEV_START_S, DEV_END_S, PBO_BLOCKS
        )
        for (_i, _a, x, d), k in zip(rows, b):
            net[k] += x
            held[k] += d
    return net.tolist(), held.tolist()


# --- verdict lines (section 6.6) --------------------------------------------------------------

DEV_ONLY = "Development only: not evidence for enabling anything."


def _pct(x: Optional[float], digits: int = 4) -> str:
    if x is None or not np.isfinite(x):
        return "n/a"
    return f"{x:+.{digits}%}"


def member_line(member: Member, result: Mapping[str, Any], passed: bool) -> str:
    """The member's verdict, worded by section 6.6, with its caveat in the line."""
    k = family_k(member.family)
    if member.test == "economic":
        rep = result["report"]
        if not result["requirements"]["trades"]:
            text = (
                f"Not assessable: {rep['trades']} trades ({rep['trades_by_half'][0]} and "
                f"{rep['trades_by_half'][1]} by half; at least 100, and 30 in each "
                "half, are needed)"
            )
            return fd.check_wording(f"{text}. {DEV_ONLY}", True)
        detail = (
            f"net ${rep['net_usd']:+,.2f} on £10,000, return per capital-day "
            f"{_pct(rep['rpcd'])}, {rep['trades']} trades, maximum drawdown "
            f"{rep.get('max_drawdown', float('nan')):.2%}, p = {result['test']['p']:.4f} "
            f"(Holm over {k}), smallest detectable return per capital-day "
            f"{_pct(result.get('smallest_detectable'))}"
        )
        if passed:
            text = (
                "Profitable after fees at £10,000 with 0.50% taker and 0.05% slippage "
                f"a fill ({detail})"
            )
        else:
            text = (
                f"Not shown to be profitable after fees: {result['failed']} ({detail})"
            )
        return fd.check_wording(f"{text}. {DEV_ONLY}", True)
    if not result.get("assessable", True):
        return fd.check_wording(
            f"Not assessable: {result['reason']}. {DEV_ONLY}", False
        )
    against = "random entries" if member.test == "random" else "random vetoes"
    stats_text = (
        f"return per capital-day {_pct(result['value'])} against a random median of "
        f"{_pct(result['median'])}, p = {result['p']:.4f} (Holm over {k}, B = "
        f"{result['draws']:,}), {result.get('trades', 0)} trades"
    )
    if passed:
        if member.test == "random":
            head = "Beats random entries"
        elif member.layer == "OVL-REGIME":
            head = "The gate adds value over random vetoes"
        else:
            head = "The model adds value over random vetoes"
        text = f"{head} ({stats_text})"
        if result.get("net_usd", 0.0) <= 0:
            text += (
                f"; the path still loses money after fees (net "
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


# --- the evaluation ---------------------------------------------------------------------------


def _log(progress: Callable[[str], None], message: str) -> None:
    progress(message)


def _trial(
    member: str, kind: str, coins: Sequence[str], summary: Mapping[str, Any], log: bool
) -> None:
    if log:
        experiment.log_trial(
            EXPERIMENT_ID,
            member,
            kind,
            DEV_START.date().isoformat(),
            DEV_END.date().isoformat(),
            coins,
            summary,
        )


@dataclass
class Data:
    """The candles of one evaluation, read once, and the strategies' simulations."""

    universes: Dict[str, Universe]
    left_out: Dict[str, Dict[str, str]]
    sims: Dict[Tuple[str, str], Simulation]  # (name, timeframe) -> simulation

    def sim(self, spec: RunnerSpec) -> Simulation:
        key = (repr(spec), spec.timeframe)
        if key not in self.sims:
            self.sims[key] = Simulation(self.universes[spec.timeframe], spec)
        return self.sims[key]

    def series_sha256(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for u in self.universes.values():
            out.update(universe_sha256(u))
        return dict(sorted(out.items()))


def load_data(loader: Loader, timeframes: Optional[Sequence[str]] = None) -> Data:
    tfs = sorted(
        set(timeframes)
        if timeframes is not None
        else {s.timeframe for s in STRATEGIES.values()}
        | {v.timeframe for v in VARIANTS}
    )
    universes: Dict[str, Universe] = {}
    left: Dict[str, Dict[str, str]] = {}
    for tf in tfs:
        universes[tf], left[tf] = development_universe(COINS, tf, loader)
    return Data(universes, left, {})


def listed_by_2021(data: Data) -> List[str]:
    """The coins whose first daily bar opens on or before 2021-01-01."""
    out = []
    for coin, frame in data.universes["1d"].frames.items():
        if len(frame) and _utc(frame["open_time"].iloc[0]) <= DEV_START:
            out.append(coin)
    return sorted(out)


def _coins_of(variant: Variant, record: Mapping[str, Any]) -> Optional[List[str]]:
    if variant.coins is None:
        return None
    if variant.coins == "BTC+ETH":
        return ["BTC", "ETH"]
    if variant.coins == "listed_by_2021":
        return list(record["market"]["listed_by_2021"])
    raise E1Error(f"unknown coin set {variant.coins!r}")


def decision_features(
    trades: Sequence[Trade], data: Data, names: Sequence[str]
) -> np.ndarray:
    """Each trade's model_lab features at its decision hour, from the 1h candles."""
    from model_lab import features as ft
    from model_lab import series as series_mod

    hourly = data.universes["1h"]
    series = {}
    for coin, frame in hourly.frames.items():
        attrs = frame.attrs or {}
        series[coin] = series_mod.from_frame(
            coin,
            attrs.get("exchange", ""),
            attrs.get("pair", f"{coin}-USD"),
            frame,
        )
    btc = series.get("BTC")
    tables = {c: ft.build(s, btc) for c, s in series.items()}
    matrices = {c: t.matrix(names) for c, t in tables.items()}
    x = np.full((len(trades), len(names)), np.nan)
    for i, t in enumerate(trades):
        table = tables.get(t.coin)
        if table is None:
            continue
        k = int(table.grid.positions([t.entry_s])[0])
        if k >= 0:
            x[i] = matrices[t.coin][k]
    return x


def climatology(label: np.ndarray, exit_s: np.ndarray, folds, signal_s) -> np.ndarray:
    """Each trade's base rate: the events' share among the labelled trades done by its
    fold's start."""
    out = np.full(len(label), np.nan)
    for a, b in folds:
        here = (signal_s >= a) & (signal_s < b)
        train = (label >= 0) & (exit_s <= a)
        if train.any():
            out[here] = float(np.mean(label[train] == 1))
    return out


def evaluate(
    record: Mapping[str, Any],
    loader: Loader,
    probabilities: Callable[[str], Mapping[str, Tuple[Any, Any]]],
    progress: Callable[[str], None] = lambda _m: None,
    log_trials: bool = True,
    data: Optional[Data] = None,
) -> Dict[str, Any]:
    """Run the frozen declaration ``record`` (see the module docstring)."""
    check_declaration()
    gbp_usd = float(record["accounts"]["gbp_usd"])
    costs = costs_for(record)
    accounts = accounts_for(record)
    deciding = accounts[DECIDING_GBP]
    data = data or load_data(loader)
    now_sha = data.series_sha256()
    frozen_sha = record["market"]["series_sha256"]
    if now_sha != frozen_sha:
        moved = sorted(
            k
            for k in set(now_sha) | set(frozen_sha)
            if now_sha.get(k) != frozen_sha.get(k)
        )
        raise E1Error(f"the candles differ from the frozen ones: {moved[:5]}")
    regimes = Regimes({**data.universes["1d"].frames}, REFERENCE)
    coins_1d = sorted(data.universes["1d"].frames)
    out: Dict[str, Any] = {
        "experiment": EXPERIMENT_ID,
        "record_sha256": record.get("sha256"),
        "gbp_usd": gbp_usd,
        "accounts_usd": {str(g): a.start for g, a in accounts.items()},
        "coins": {tf: sorted(u.frames) for tf, u in data.universes.items()},
        "left_out": data.left_out,
    }

    # --- the strategies' trades -------------------------------------------------------
    _log(progress, "candidate trades")
    trades: Dict[str, List[Trade]] = {}
    gated: Dict[str, Simulation] = {}
    for sid, spec in STRATEGIES.items():
        trades[sid] = scored(data.sim(spec))
        gated[sid] = data.sim(
            RunnerSpec(sid, dict(spec.params), (GATE,), spec.timeframe)
        )
        _log(progress, f"{sid}: {len(trades[sid])} candidate trades")
    paths: Dict[str, Paths] = {}
    gate_filters: Dict[str, md.Filter] = {}
    for sid, spec in STRATEGIES.items():
        paths[sid] = data.sim(spec).replay(trades[sid], costs, deciding, detail=True)
        gate_filters[sid] = gate_filter(trades[sid], gated[sid])

    # --- family S ------------------------------------------------------------------------
    _log(progress, "family S")
    s_days = [
        (t.exit_s - t.entry_s) / DAY_S
        for sid in ("STRAT-004", "STRAT-005")
        for t in taken(trades[sid], paths[sid])
    ]
    block_s = block_length(s_days)
    results: Dict[str, Dict[str, Any]] = {}
    for m in MEMBERS:
        if m.family != "S":
            continue
        sim = data.sim(STRATEGIES[m.strategy])
        if m.test == "random":
            r = random_test(
                sim, trades[m.strategy], paths[m.strategy], costs, deciding,
                m.seed, PER_RUN, family_k("S"),
            )  # fmt: skip
            summary = {"p": r.get("p"), "value": r.get("value")}
        else:
            r = economic_test(
                paths[m.strategy], trades[m.strategy], m.seed, block_s, family_k("S")
            )
            summary = {"p": r["test"]["p"], "net_usd": r["report"]["net_usd"]}
        results[m.id] = r
        _trial(m.id, m.kind, coins_1d, summary, log_trials)
        _log(progress, f"{m.id} p = {summary['p']}")

    # --- family G ------------------------------------------------------------------------
    _log(progress, "family G")
    gate_paths: Dict[str, Paths] = {}
    for m in MEMBERS:
        if m.family != "G":
            continue
        sid = m.strategy
        filt = gate_filters[sid]
        r, gpath = r3_test(
            data.sim(STRATEGIES[sid]), trades[sid], filt, costs, deciding,
            m.seed, PER_RUN, family_k("G"),
        )  # fmt: skip
        gate_paths[sid] = gpath
        results[m.id] = r
        _trial(m.id, m.kind, sorted(data.universes[STRATEGIES[sid].timeframe].frames),
               {"p": r.get("p"), "vetoed": r.get("vetoed")}, log_trials)  # fmt: skip
        _log(progress, f"{m.id} p = {r.get('p')}")

    # --- family M ------------------------------------------------------------------------
    _log(progress, "family M")
    probs_pv = probabilities(MODEL_PV)
    probs_p = probabilities(MODEL_P)
    for coin, (close_s, _p) in {**probs_pv, **probs_p}.items():
        if len(close_s) and int(np.max(close_s)) > DEV_END_S:
            raise ReservedPeriod(
                f"{coin}: a probability is dated after the development end"
            )
    model_filters: Dict[Tuple[str, str], md.Filter] = {}
    model_paths: Dict[Tuple[str, str], Paths] = {}
    for m in MEMBERS:
        if m.family != "M":
            continue
        sid = m.strategy
        filt = md.forecast_filter(trades[sid], probs_pv, MODEL_Q, MODEL_PV)
        model_filters[(sid, "PV")] = filt
        r, mpath = r3_test(
            data.sim(STRATEGIES[sid]), trades[sid], filt, costs, deciding,
            m.seed, PER_RUN, family_k("M"),
        )  # fmt: skip
        model_paths[(sid, "PV")] = mpath
        results[m.id] = r
        _trial(
            m.id,
            m.kind,
            coins_1d,
            {"p": r.get("p"), "vetoed": r.get("vetoed")},
            log_trials,
        )
        _log(progress, f"{m.id} p = {r.get('p')}")

    # --- Holm within each family, verdicts ----------------------------------------------
    verdicts: Dict[str, Dict[str, Any]] = {}
    for family in FAMILIES:
        members = [m for m in MEMBERS if m.family == family]
        ps = []
        for m in members:
            r = results[m.id]
            ps.append(r["test"]["p"] if m.test == "economic" else r.get("p", 1.0))
        holm = stats.holm(ps, HOLM_ALPHA)
        for m, p, h in zip(members, ps, holm):
            r = results[m.id]
            if m.test == "economic":
                passed = fd.f3_passes(r, h)
                r["failed"] = fd.f3_failed(r, h)
                kind = "economic"
                outcome = (
                    "not_assessable" if not r["requirements"]["trades"]
                    else ("pass" if passed else "fail")
                )  # fmt: skip
            else:
                passed = bool(h and r.get("assessable", True))
                kind = "trading"
                outcome = (
                    "not_assessable" if not r.get("assessable", True)
                    else "pass" if passed
                    else "too_few" if r["too_few"]
                    else "fail"
                )  # fmt: skip
            verdicts[m.id] = {
                "family": family,
                "p": p,
                "holm_pass": bool(h),
                "passed": bool(passed),
                "outcome": outcome,
                "kind": kind,
                "line": member_line(m, r, passed),
            }
    out["block_days"] = {"S": block_s}
    out["members"] = results
    out["verdicts"] = verdicts

    # --- shown: every cell at every account, with REF-HOLD and REF-CASH ---------------
    _log(progress, "figures at every account")
    cells: Dict[str, Dict[str, Any]] = {}
    for sid, spec in STRATEGIES.items():
        sim = data.sim(spec)
        hold = bl.hold_trades(sim, DEV_START_S - spec.bar_seconds)
        row: Dict[str, Any] = {
            "timeframe": spec.timeframe,
            "candidates": len(trades[sid]),
        }
        for g, acct in accounts.items():
            p = (
                paths[sid]
                if g == DECIDING_GBP
                else sim.replay(trades[sid], costs, acct, detail=True)
            )
            h = sim.replay(hold, costs, acct, detail=True)
            row[f"£{g:,.0f}"] = {
                "strategy": figures(trades[sid], p, costs, acct, gbp_usd, regimes),
                "ref_hold": figures(hold, h, costs, acct, gbp_usd),
                "ref_cash": {"net_usd": 0.0, "rpcd": 0.0, "trades": 0},
            }
            gf = gate_filters.get(sid)
            if gf is not None:
                gp = (
                    gate_paths[sid] if g == DECIDING_GBP and sid in gate_paths
                    else md.cell(sim, trades[sid], costs, acct, gf, detail=True)
                )  # fmt: skip
                row[f"£{g:,.0f}"]["with_gate"] = figures(
                    trades[sid], gp, costs, acct, gbp_usd, regimes
                )
        for name, fee, _note in FEE_SCENARIOS:
            c = Costs(fee, costs.allowance, costs.minimum_usd, costs.base_increment)
            row.setdefault("fees", {})[name] = compact(
                figures(
                    trades[sid],
                    sim.replay(trades[sid], c, deciding, detail=True),
                    c,
                    deciding,
                    gbp_usd,
                )
            )
        cells[sid] = row
    # the model paths at every account
    for (sid, key), filt in model_filters.items():
        sim = data.sim(STRATEGIES[sid])
        for g, acct in accounts.items():
            mp = (
                model_paths[(sid, key)]
                if g == DECIDING_GBP
                else md.cell(sim, trades[sid], costs, acct, filt, detail=True)
            )
            cells[sid][f"£{g:,.0f}"][f"with_{key}"] = figures(
                trades[sid], mp, costs, acct, gbp_usd, regimes
            )
    out["cells"] = cells

    # REF-RANDOM at the sensitivity accounts, for S1 and S2's strategies (shown)
    for sid in ("STRAT-004", "STRAT-005"):
        sim = data.sim(STRATEGIES[sid])
        for g in ACCOUNTS_GBP:
            if g == DECIDING_GBP:
                continue
            acct = accounts[g]
            p = sim.replay(trades[sid], costs, acct, detail=True)
            name = f"random {sid} at £{g:,.0f}"
            r = random_test(
                sim, trades[sid], p, costs, acct, SHOWN_SEEDS[name], SHOWN_PER_RUN, 1
            )
            cells[sid][f"£{g:,.0f}"]["ref_random"] = r
            _trial(name, "strategy", coins_1d, {"p": r.get("p")}, log_trials)

    # --- exploratory cells (BH at q = 0.10, never a pass) -----------------------------
    _log(progress, "exploratory cells")
    exploratory: Dict[str, Dict[str, Any]] = {}
    for sid in ("STRAT-000", "STRAT-001", "STRAT-002"):
        name = f"random {sid}"
        sim = data.sim(STRATEGIES[sid])
        r = random_test(
            sim,
            trades[sid],
            paths[sid],
            costs,
            deciding,
            SHOWN_SEEDS[name],
            SHOWN_PER_RUN,
            1,
        )
        exploratory[f"{sid} vs REF-RANDOM"] = {"kind": "trading", **r}
        _trial(name, "strategy", sorted(sim.tables), {"p": r.get("p")}, log_trials)
        _log(progress, f"{name} p = {r.get('p')}")
    for sid in ("STRAT-000", "STRAT-002"):
        name = f"r3 {sid} + OVL-REGIME"
        sim = data.sim(STRATEGIES[sid])
        r, gp = r3_test(
            sim,
            trades[sid],
            gate_filters[sid],
            costs,
            deciding,
            SHOWN_SEEDS[name],
            SHOWN_PER_RUN,
            1,
        )
        exploratory[f"{sid} + OVL-REGIME vs R3"] = {"kind": "trading", **r}
        gate_paths[sid] = gp
        _trial(name, "gate", sorted(sim.tables), {"p": r.get("p")}, log_trials)
    for sid, key, probs in (
        ("STRAT-004", "P", probs_p),
        ("STRAT-005", "P", probs_p),
        ("STRAT-001", "PV", probs_pv),
        ("STRAT-001", "P", probs_p),
    ):
        name = f"r3 {sid} + {key}"
        sim = data.sim(STRATEGIES[sid])
        filt = md.forecast_filter(
            trades[sid], probs, MODEL_Q, MODEL_PV if key == "PV" else MODEL_P
        )
        model_filters[(sid, key)] = filt
        r, mp = r3_test(
            sim, trades[sid], filt, costs, deciding, SHOWN_SEEDS[name], SHOWN_PER_RUN, 1
        )
        model_paths[(sid, key)] = mp
        exploratory[f"{sid} + {key} model vs R3"] = {"kind": "trading", **r}
        _trial(name, "model", sorted(sim.tables), {"p": r.get("p")}, log_trials)
        _log(progress, f"{name} p = {r.get('p')}")
    for sid in ("STRAT-004", "STRAT-005"):
        name = f"paired {sid} PV vs P"
        a = path_rows(trades[sid], model_paths[(sid, "PV")])
        b = path_rows(trades[sid], model_paths[(sid, "P")])
        block = block_length([(t.exit_s - t.entry_s) / DAY_S for t in trades[sid]])
        r = fd.paired_paths(a, b, DEV_START_S, LAST_S, SHOWN_SEEDS[name], block)
        exploratory[f"{sid}: PV model vs P model"] = {"kind": "trading", **r}
        _trial(name, "model", coins_1d, {"p": r.get("p")}, log_trials)

    # strategy-specific meta-models, where there are enough events
    prediction: Dict[str, Dict[str, Any]] = {}
    from model_lab import features as ft

    folds = list(md.development_folds())
    for sid in ("STRAT-004", "STRAT-005"):
        tr = trades[sid]
        gross, label = lb.label_rows(md.label_trades(tr), FEE)
        signal_s = np.array([t.entry_s for t in tr], dtype=np.int64)
        exit_s = np.array([t.exit_s for t in tr], dtype=np.int64)
        in_folds = np.zeros(len(tr), dtype=bool)
        for a, b in folds:
            in_folds |= (signal_s >= a) & (signal_s < b)
        events = int(np.sum((label == 1) & in_folds))
        non_events = int(np.sum((label == 0) & in_folds))
        for key, probs in (("PV", probs_pv), ("P", probs_p)):
            filt = model_filters[(sid, key)]
            prediction[f"{sid} {key} model"] = {
                "auc": auc(filt.p, label),
                "rows": int(np.sum(np.isfinite(filt.p) & (label >= 0))),
                "base_rate": (
                    float(np.mean(label[label >= 0] == 1))
                    if np.any(label >= 0)
                    else None
                ),
                "note": "the model forecasts a T1 barrier outcome, not this strategy's trade",
            }
        if events < md.MIN_EVENTS or non_events < md.MIN_EVENTS:
            for key in ("F_PV", "F_P"):
                exploratory[f"{sid} + {key} vs R3"] = {
                    "kind": "trading",
                    "assessable": False,
                    "reason": f"{events} events and {non_events} non-events in the folds; 200 of each are needed",
                }
            continue
        _log(progress, f"{sid}: meta-models on {len(tr)} trades")
        for key, names in (("F_PV", ft.P + ft.V), ("F_P", ft.P)):
            x = decision_features(tr, data, names)
            filt = md.meta_filter(tr, x, folds, FEE, key)
            name = f"r3 {sid} + {key}"
            if not filt.enough:
                exploratory[f"{sid} + {key} vs R3"] = {
                    "kind": "trading", "assessable": False,
                    "reason": f"{filt.detail['events']} events and {filt.detail['non_events']} non-events scored; 200 of each are needed",
                }  # fmt: skip
                continue
            sim = data.sim(STRATEGIES[sid])
            r, _mp = r3_test(
                sim, tr, filt, costs, deciding, SHOWN_SEEDS[name], SHOWN_PER_RUN, 1
            )
            exploratory[f"{sid} + {key} vs R3"] = {
                "kind": "trading",
                **r,
                "events": filt.detail["events"],
            }
            _trial(name, "model", coins_1d, {"p": r.get("p")}, log_trials)
            if key == "F_PV":
                wf = meta.walk_forward(x, label, signal_s, exit_s, folds)
                ok = np.isfinite(wf.calibrated) & (label >= 0)
                if ok.sum() >= 2:
                    cname = f"calibration {sid} F_PV"
                    c = fd.calibration(
                        label[ok], wf.calibrated[ok], wf.climatology[ok], signal_s[ok],
                        SHOWN_SEEDS[cname], 1,
                        block_length([(t.exit_s - t.entry_s) / DAY_S for t in tr]),
                    )  # fmt: skip
                    prediction[f"{sid} F_PV"] = {
                        "calibration": c,
                        "auc": auc(wf.calibrated, label),
                    }
                    exploratory[f"Calibration of {sid}'s F_PV"] = {
                        "kind": "prediction", "p": c["skill"]["p"], "outcome": c["outcome"],
                    }  # fmt: skip
                    _trial(
                        cname,
                        "calibration",
                        coins_1d,
                        {"p": c["skill"]["p"]},
                        log_trials,
                    )
    ps = [(k, v["p"]) for k, v in exploratory.items() if v.get("p") is not None]
    flags = stats.benjamini_hochberg([p for _k, p in ps], BH_Q) if ps else []
    for (k, _p), f in zip(ps, flags):
        exploratory[k]["bh_flag"] = bool(f)
    out["exploratory"] = exploratory
    out["prediction"] = prediction

    # --- robustness (section 6.4), with PBO -------------------------------------------
    _log(progress, "robustness")
    robust: Dict[str, Dict[str, Any]] = {}
    blocks: Dict[str, Dict[str, Tuple[List[float], List[float]]]] = {}
    for i, v in enumerate(VARIANTS):
        spec = v.spec()
        sim = data.sim(spec)
        coins = _coins_of(v, record)
        tr = scored(sim, coins)
        p = sim.replay(tr, costs, deciding, detail=True)
        r = random_test(
            sim, tr, p, costs, deciding, VARIANT_SEED + 1000 * i, SHOWN_PER_RUN, 1
        )
        robust[v.name] = {
            "figures": compact(figures(tr, p, costs, deciding, gbp_usd)),
            "ref_random": {
                k: r.get(k) for k in ("p", "median", "value", "draws", "assessable")
            },
            "coins": sorted({t.coin for t in tr}),
        }
        kind = "gate" if v.overlays else "strategy"
        _trial(
            f"robust {v.name}",
            kind,
            sorted({t.coin for t in tr}),
            {"net_usd": float(p.net[0])},
            log_trials,
        )
        _log(progress, f"robust {v.name}: net {float(p.net[0]):+.2f}")
        if v.pbo_set:
            blocks.setdefault(v.pbo_set, {})[v.name] = pbo_blocks(tr, p)
    main_paths = {
        "STRAT-004": (trades["STRAT-004"], paths["STRAT-004"]),
        "STRAT-005": (trades["STRAT-005"], paths["STRAT-005"]),
        "G1": (trades["STRAT-001"], gate_paths["STRAT-001"]),
        "G2": (trades["STRAT-004"], gate_paths["STRAT-004"]),
        "G3": (trades["STRAT-005"], gate_paths["STRAT-005"]),
    }
    pbo: Dict[str, Any] = {}
    for name, members in sorted(blocks.items()):
        tr, p = main_paths[PBO_MAIN[name]]
        members = {f"{PBO_MAIN[name]} (default)": pbo_blocks(tr, p), **members}
        nets = [m[0] for m in members.values()]
        held = [m[1] for m in members.values()]
        pbo[name] = {"contestants": list(members), "pbo": stats.pbo(nets, held)}
    out["robustness"] = {"variants": robust, "pbo": pbo, "not_run": dict(NOT_RUN)}
    out["trial_counts"] = experiment.trial_counts() if log_trials else {}
    return out


def evidence_lines(result: Mapping[str, Any], coins: int) -> List[Any]:
    """The members' verdicts as ``strategy_lab.evidence`` lines, for "Model evidence..."."""
    from strategy_lab.evidence import Line

    period = (
        f"2021-01-01 to 2025-05-06, {coins} coins, 0.50% taker + 0.05% slippage, "
        "£10,000 (E1)"
    )
    recorded = f"{APPROVED}, development only"
    lines = []
    for m in MEMBERS:
        v = result["verdicts"][m.id]
        if m.layer is None:
            model = "No model: the strategy alone"
        elif m.layer == "OVL-REGIME":
            model = "The regime gate (OVL-REGIME) against random vetoes"
        else:
            model = f"The PV model ({m.layer}) against random vetoes"
        if m.test == "random":
            model = "The strategy against random entries with its own exits"
        lines.append(Line(m.strategy, model, v["kind"], v["line"], period, recorded))
    return lines
