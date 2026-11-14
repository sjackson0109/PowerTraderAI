"""
Exploratory backtests from Settings > Strategy, "Run a backtest..." (FDS-SR-001
section 5.8). An exploratory run is never evidence: it is logged as a trial of kind
"exploration", with the months it read, so that later declared tests can count it.

``run(config)``:

1. refuses any period that reaches the reserved months (``windows.development_only``);
2. reads each coin's candles once, from far enough back for the strategy's warm-up,
   through the exchange layer and its cache;
3. takes the strategy's trades decided in the period and replays them in one account of
   the chosen size, with today's venue minimums and sell steps, against buy-and-hold,
   cash and random entries replayed through the strategy's own exits, with its
   daily, weekly, monthly and annual returns (``research_stats.periods``); as many
   random entries again, each held as long as one of the strategy's trades
   (``baselines.matched_draws``), are reported beside them and scored by nothing;
   then the same trades and buy-and-hold at each of ``ACCOUNTS_GBP`` (``accounts``):
   each account's results, its drawdowns and recovery (``research_stats.drawdowns``),
   its period returns, and whether it took the same trades as the largest account
   (an account too small for the venue's minimum orders, or short of cash, does not);
   with a sizing policy (``RunConfig.sizing``, ``strategy_lab.sizing``) each of the
   strategy's trades, and each random entry, is scaled at its decision, and the run
   records the same trades at the account's own size and the same scales replayed in
   random orders; for STRAT-007, with ``RunConfig.ensemble``, the ensemble of its
   lookbacks too (``strategy_lab.ensemble``), each member alone and an equal-weight
   buy-and-hold;
4. logs the trial and saves the run under ``<data dir>/strategy_lab/runs/<id>/run.json``.

``stop`` (a threading.Event) is checked between the stages; a stopped run saves nothing.
"""

from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from market_data.candles import exchange_candles
from research_stats import drawdowns, periods
from signal_fusion.evaluation.replay import Account, Costs, Paths
from strategy_lab import baselines as bl
from strategy_lab import ensemble as ens_mod
from strategy_lab import experiment, sizing
from strategy_lab.candidates import RunnerSpec, Trade
from strategy_lab.simulate import Simulation, load_universe
from strategy_lab.venue import VenueRules, venue_rules
from strategy_lab.windows import HISTORY_START, development_only

CURVE_POINTS = 400
# the programme's account sizes, each reported separately (PTAI-RD-001 WP 2.6), smallest
# first; the largest is the one the others' trades are compared with
ACCOUNTS_GBP = (50.0, 200.0, 500.0, 10_000.0)
ENSEMBLE_STRATEGY = "STRAT-007"


class Stopped(Exception):
    """The run was asked to stop."""


@dataclass(frozen=True)
class RunConfig:
    strategy_id: str
    params: Mapping[str, Any]
    overlays: Sequence[Mapping[str, Any]]
    timeframe: str
    coins: Sequence[str]
    start: str
    end: str
    account_gbp: float
    gbp_usd: float
    fee: float  # taker, a fraction a side
    allowance: float = 0.0005  # slippage a fill
    draws: int = 200  # random-entry draws, and as many matched-holding draws
    seed: int = 700_000
    # the sizing policy's record (``strategy_lab.sizing``); None: the account's own
    sizing: Optional[Mapping[str, Any]] = None
    # STRAT-007 only: also replay its ensemble of lookbacks (``strategy_lab.ensemble``)
    ensemble: bool = False

    def spec(self) -> RunnerSpec:
        return RunnerSpec(
            self.strategy_id,
            dict(self.params),
            tuple(dict(o) for o in self.overlays),
            self.timeframe,
        )


def runs_dir() -> str:
    return os.path.join(experiment.lab_dir(), "runs")


def _seconds(t) -> int:
    return int(pd.Timestamp(t).timestamp())


def _warmup_start(spec: RunnerSpec, start: pd.Timestamp) -> pd.Timestamp:
    runner = spec.build()
    bars = max(runner.lookback_bars, runner.strategy.warmup_bars) + 2
    back = pd.Timedelta(seconds=bars * spec.bar_seconds)
    for _ref, tf, need in runner.context_needs():
        back = max(back, pd.Timedelta(days=int(need) + 2))
    return max(HISTORY_START, start - back)


def _figures(paths: Paths, p: int = 0) -> Dict[str, Any]:
    rpcd = paths.rpcd
    low_dd, low_halt = paths.intrabar_max_drawdown, paths.intrabar_halt_s
    return {
        "net_usd": float(paths.net[p]),
        "return_per_capital_day": float(rpcd[p]),
        "max_drawdown": float(paths.max_drawdown[p]),
        "final_equity": float(paths.final_equity[p]),
        "trades": int(paths.trades[p]),
        "time_in_market": float(paths.time_in_market[p]),
        "mean_committed": float(paths.mean_committed[p]),
        "peak_committed": float(paths.peak_committed[p]),
        "skipped_cash": int(paths.skipped_cash[p]),
        "skipped_minimum": int(paths.skipped_minimum[p]),
        "skipped_cooldown": (
            int(paths.skipped_cooldown[p]) if paths.skipped_cooldown is not None else 0
        ),
        "unsold_remainder_usd": (
            float(paths.dust_usd[p]) if paths.dust_usd is not None else 0.0
        ),
        "halt_reached": (
            None
            if int(paths.halt_s[p]) < 0
            else datetime.fromtimestamp(
                int(paths.halt_s[p]), tz=timezone.utc
            ).isoformat()
        ),
        "halt_exposure_usd": (
            float(paths.halt_exposure[p]) if paths.halt_exposure is not None else 0.0
        ),
        # within the bar: open positions at their bar's low, from a peak at the earlier
        # bars' highs (shown only)
        "intrabar_max_drawdown": None if low_dd is None else float(low_dd[p]),
        "intrabar_halt_reached": (
            None
            if low_halt is None or int(low_halt[p]) < 0
            else datetime.fromtimestamp(int(low_halt[p]), tz=timezone.utc).isoformat()
        ),
    }


def _period_summaries(curve) -> Optional[Dict[str, Any]]:
    """Each period's summary, the annual growth and the 10% objective, without the
    rows (the run's own account keeps those)."""
    if curve is None:
        return None
    full = periods.report(*curve)
    out: Dict[str, Any] = {p: full[p]["summary"] for p in periods.PERIODS}
    out["annual_growth"] = full["annual_growth"]
    out["target_annual"] = full["target_annual"]
    return out


def _accounts(
    sim: Simulation,
    trades: Sequence[Trade],
    hold: Sequence[Trade],
    costs: Costs,
    gbp_usd: float,
    **kw,
) -> List[Dict[str, Any]]:
    """``trades`` and buy-and-hold at each of ``ACCOUNTS_GBP`` (module docstring);
    ``kw`` (a sizing ``scale``) goes to the strategy's replays."""
    usd = {g: round(g * float(gbp_usd), 2) for g in ACCOUNTS_GBP}
    paths = sim.accounts(usd, costs, trades, detail=True, **kw)
    holds = sim.accounts(usd, costs, hold)
    largest = sorted(i for i, *_ in paths[ACCOUNTS_GBP[-1]].detail)
    out = []
    for g in ACCOUNTS_GBP:
        path = paths[g]
        taken = sorted(i for i, *_ in path.detail)
        figures = _figures(path)
        out.append(
            {
                "account_gbp": g,
                "account_usd": usd[g],
                "strategy_result": figures,
                "return": figures["net_usd"] / usd[g],
                "buy_and_hold": {
                    "net_usd": float(holds[g].net[0]),
                    "return": float(holds[g].net[0]) / usd[g],
                },
                "trades_taken": len(taken),
                "same_trades_as_largest": taken == largest,
                "drawdowns": (
                    drawdowns.report(*path.curve) if path.curve is not None else None
                ),
                "periods": _period_summaries(path.curve),
            }
        )
    return out


def _sizing_checks(
    sim: Simulation,
    trades: Sequence[Trade],
    costs: Costs,
    account: Account,
    sized: sizing.Sizing,
    path: Paths,
    config: RunConfig,
) -> Dict[str, Any]:
    """A sizing policy's scales, the same trades at the account's own size, and the
    same scales in random orders (``sizing.random_orders``): the share of orders whose
    largest drawdown, and whose net, were at or below the policy's."""
    plain = sim.replay(trades, costs, account)
    out: Dict[str, Any] = {
        **sized.summary(),
        "fixed_result": {
            "net_usd": float(plain.net[0]),
            "max_drawdown": float(plain.max_drawdown[0]),
            "trades": int(plain.trades[0]),
        },
        "random_order": None,
    }
    draws = int(config.draws)
    if draws and len(trades):
        orders = sizing.random_orders(sized.scale, draws, config.seed + 1)
        rand = sim.replay(trades, costs, account, scale=orders)
        out["random_order"] = {
            "draws": draws,
            "median_max_drawdown": float(np.median(rand.max_drawdown)),
            "share_drawdown_at_or_below": float(
                np.mean(rand.max_drawdown <= path.max_drawdown[0] + 1e-12)
            ),
            "median_net_usd": float(np.median(rand.net)),
            "share_net_at_or_above": float(np.mean(rand.net >= path.net[0] - 1e-9)),
        }
    return out


def _curve(paths: Paths) -> List[List[float]]:
    if paths.curve is None:
        return []
    hours, equity = paths.curve
    if not len(hours):
        return []
    idx = np.unique(
        np.linspace(0, len(hours) - 1, min(CURVE_POINTS, len(hours))).astype(int)
    )
    return [[int(hours[i]), float(equity[i])] for i in idx]


def run(
    config: RunConfig,
    *,
    loader: Callable[..., pd.DataFrame] = exchange_candles,
    venue: Callable[[Sequence[str]], VenueRules] = venue_rules,
    stop: Optional[threading.Event] = None,
    progress: Callable[[str], None] = lambda _m: None,
    now: Optional[float] = None,
    save: bool = True,
) -> Dict[str, Any]:
    """One exploratory run (see the module docstring); its saved record."""
    stop = stop or threading.Event()

    def check() -> None:
        if stop.is_set():
            raise Stopped("stopped")

    a, b = development_only(config.start, config.end)
    if not config.gbp_usd > 0:
        raise ValueError("state the GBP-to-USD rate")
    if not config.coins:
        raise ValueError("choose at least one coin")
    spec = config.spec()
    if config.ensemble and config.strategy_id != ENSEMBLE_STRATEGY:
        raise ValueError(f"the ensemble is of {ENSEMBLE_STRATEGY}'s members")
    first = _warmup_start(spec, a)
    if config.ensemble:  # the longest member's channel
        back = pd.Timedelta(days=ens_mod.warmup_days())
        first = max(HISTORY_START, min(first, a - back))
    progress("Reading candles")
    universe = load_universe(list(config.coins), spec, first, b, loader=loader)
    check()
    progress("Finding the strategy's trades")
    sim = Simulation(universe, spec)
    start_s = _seconds(a)
    trades = [t for t in sim.candidates() if t.entry_s >= start_s]
    check()
    progress("Reading minimum orders")
    rules = venue(list(config.coins))
    costs = Costs(
        fee=float(config.fee),
        allowance=float(config.allowance),
        minimum_usd=rules.minimum_usd,
        base_increment=rules.base_increment,
    )
    usd = round(float(config.account_gbp) * float(config.gbp_usd), 2)
    account = Account(start=usd)
    policy = sizing.from_record(config.sizing)
    sized = policy.scales(sim, trades)
    fixed = isinstance(policy, sizing.Fixed)
    kw = {} if fixed else {"scale": sized.scale[None, :]}
    progress("Replaying the account")
    path = sim.replay(trades, costs, account, detail=True, **kw)
    taken: List[Trade] = [trades[i] for i, *_ in path.detail]
    check()
    hold_trades = bl.hold_trades(sim, start_s)
    hold = sim.replay(hold_trades, costs, account)
    progress("Replaying each account size")
    accounts = _accounts(sim, trades, hold_trades, costs, config.gbp_usd, **kw)
    check()
    progress(f"Replaying {config.draws} random-entry draws")
    draws = bl.random_draws(sim, taken, config.seed, int(config.draws), start_s)
    rand = (
        bl.replay_draws(
            sim, draws.draws, costs, account, policy=None if fixed else policy
        )
        if config.draws
        else None
    )
    check()
    # random entries held as long as the strategy's trades: reported only (the owner's
    # decision of 2026-11-13); their seeds follow the random entries' own
    progress(f"Replaying {config.draws} draws held as long as the strategy's trades")
    matched_seed = int(config.seed) + int(config.draws)
    matched = bl.matched_draws(sim, taken, matched_seed, int(config.draws), start_s)
    matched_paths = (
        bl.replay_draws(
            sim, matched.draws, costs, account, policy=None if fixed else policy
        )
        if config.draws
        else None
    )
    check()
    ensemble_part = None
    if config.ensemble:
        progress("Replaying the ensemble")
        group = ens_mod.Ensemble(universe)
        ensemble_part = ens_mod.report(group, costs, usd, policy, start_s)
        check()
    sizing_part: Dict[str, Any] = {"policy": policy.record()}
    if not fixed:
        progress("Replaying the sizes in random orders")
        sizing_part.update(
            _sizing_checks(sim, trades, costs, account, sized, path, config)
        )
        check()

    per_coin: Dict[str, Dict[str, Any]] = {}
    for i, amount, net, days in path.detail:
        row = per_coin.setdefault(trades[i].coin, {"trades": 0, "net_usd": 0.0})
        row["trades"] += 1
        row["net_usd"] += float(net)
    held_days = [(t.exit_s - t.entry_s) / 86_400 for t in taken]
    mine = float(path.rpcd[0])
    random_part = None
    if rand is not None and len(rand.net):
        random_part = {
            "draws": int(len(rand.net)),
            "median_net_usd": float(np.median(rand.net)),
            "median_return_per_capital_day": float(np.median(rand.rpcd)),
            "share_at_or_above": float(np.mean(rand.rpcd >= mine)),
            "entries_wanted": draws.wanted,
            "entries_reached_median": float(np.median(draws.reached)),
        }
    matched_part = None
    if matched_paths is not None and len(matched_paths.net):
        m = matched_paths
        matched_part = {
            "draws": int(len(m.net)),
            "seed": matched_seed,  # draw b: seed + b
            "median_net_usd": float(np.median(m.net)),
            "median_return_per_capital_day": float(np.median(m.rpcd)),
            "share_at_or_above": float(np.mean(m.rpcd >= mine)),
            "median_max_drawdown": float(np.median(m.max_drawdown)),
            "share_drawdown_at_or_below": float(
                np.mean(m.max_drawdown <= path.max_drawdown[0] + 1e-12)
            ),
            "trades_wanted": matched.wanted,
            # the strategy's trades a draw had no room for, over all the draws
            "trades_dropped": int(sum(matched.dropped)),
            "draws_short": int(sum(1 for d in matched.dropped if d)),
        }
    when = datetime.fromtimestamp(now or time.time(), tz=timezone.utc)
    run_id = f"{when.strftime('%Y%m%d-%H%M%S')}-{config.strategy_id}"
    record = {
        "id": run_id,
        "kind": "exploration",
        "ran_at": when.isoformat(),
        "config": {**asdict(config), "params": dict(config.params)},
        "strategy": experiment.strategy_record(
            config.strategy_id, config.params, config.overlays, config.timeframe
        ),
        "period": [a.isoformat(), b.isoformat()],
        "account_usd": usd,
        "venue": rules.as_record(),
        "sources": universe.sources,
        "strategy_result": _figures(path),
        "holding_days": {
            "median": float(np.median(held_days)) if held_days else None,
            "p90": float(np.percentile(held_days, 90)) if held_days else None,
        },
        "per_coin": per_coin,
        "buy_and_hold": _figures(hold),
        "cash": {"net_usd": 0.0, "return_per_capital_day": 0.0},
        "random_entries": random_part,
        # random entries held as long as the strategy's trades: reported only, and
        # absent from runs saved before it was recorded
        "matched_holding": matched_part,
        "curve": _curve(path),
        # daily, weekly, monthly and annual returns from the whole curve (WP 2.6)
        "periods": (periods.report(*path.curve) if path.curve is not None else None),
        "drawdowns": (
            drawdowns.report(*path.curve) if path.curve is not None else None
        ),
        # the same trades at each of the programme's account sizes (WP 2.6)
        "accounts": accounts,
        # how each trade was sized (WP 4.2), against the account's own sizing and the
        # same sizes in random orders
        "sizing": sizing_part,
        # STRAT-007's ensemble of lookbacks, when asked for (backlog 3.1)
        "ensemble": ensemble_part,
    }
    if save:
        run_id, folder = _claim_folder(run_id)
        record["id"] = run_id
        experiment.log_trial(
            run_id,
            "run",
            "exploration",
            a.date().isoformat(),
            b.date().isoformat(),
            config.coins,
            {"net_usd": record["strategy_result"]["net_usd"]},
            now=now,
        )
        with open(
            os.path.join(folder, "run.json"), "w", encoding="utf-8", newline="\n"
        ) as f:
            json.dump(record, f, indent=2, sort_keys=True, default=str)
            f.write("\n")
    return record


def _claim_folder(run_id: str) -> Tuple[str, str]:
    """A new folder for a run: ``run_id``, or ``run_id-2``, ``-3``, ... when a run of
    the same strategy was saved in the same second (parallel research jobs can). The
    folder's creation is the claim, so two processes never get the same one."""
    base = runs_dir()
    os.makedirs(base, exist_ok=True)
    n = 1
    while True:
        rid = run_id if n == 1 else f"{run_id}-{n}"
        folder = os.path.join(base, rid)
        try:
            os.mkdir(folder)
            return rid, folder
        except FileExistsError:
            n += 1


def list_runs() -> List[Dict[str, Any]]:
    """Every saved run's record, newest first."""
    out = []
    folder = runs_dir()
    if not os.path.isdir(folder):
        return out
    for name in sorted(os.listdir(folder), reverse=True):
        path = os.path.join(folder, name, "run.json")
        try:
            with open(path, encoding="utf-8") as f:
                out.append(json.load(f))
        except (OSError, ValueError):
            continue
    return out
