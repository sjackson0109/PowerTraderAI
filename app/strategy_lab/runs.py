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
   cash and random entries replayed through the strategy's own exits;
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
from signal_fusion.evaluation.replay import Account, Costs, Paths
from strategy_lab import baselines as bl
from strategy_lab import experiment
from strategy_lab.candidates import RunnerSpec, Trade
from strategy_lab.simulate import Simulation, load_universe
from strategy_lab.venue import VenueRules, venue_rules
from strategy_lab.windows import HISTORY_START, development_only

CURVE_POINTS = 400


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
    draws: int = 200  # random-entry draws
    seed: int = 700_000

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
        # within the bar: open positions at their bar's low (shown only)
        "intrabar_max_drawdown": None if low_dd is None else float(low_dd[p]),
        "intrabar_halt_reached": (
            None
            if low_halt is None or int(low_halt[p]) < 0
            else datetime.fromtimestamp(int(low_halt[p]), tz=timezone.utc).isoformat()
        ),
    }


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
    progress("Reading candles")
    universe = load_universe(
        list(config.coins), spec, _warmup_start(spec, a), b, loader=loader
    )
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
    progress("Replaying the account")
    path = sim.replay(trades, costs, account, detail=True)
    taken: List[Trade] = [trades[i] for i, *_ in path.detail]
    check()
    hold = sim.replay(bl.hold_trades(sim, start_s), costs, account)
    progress(f"Replaying {config.draws} random-entry draws")
    draws = bl.random_draws(sim, taken, config.seed, int(config.draws), start_s)
    rand = bl.replay_draws(sim, draws.draws, costs, account) if config.draws else None
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
        "curve": _curve(path),
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
