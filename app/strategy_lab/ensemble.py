"""
The Donchian ensemble of Zarattini, Pagani and Barbon (2025) for research replays
(PTAI-RD-001 backlog 3.1; research catalogue entry ``breakout.zarattini-ensemble``).

**Members.** One STRAT-007 per lookback in ``LOOKBACKS``, each with OVL-MIDLINE on the
same days (``member_spec``): a new closing high of n days enters, a close below the
channel's midline, ratcheted so it never moves down, exits. The paper's 5- and 10-day
members are left out: at this account's fees their 15 to 29 round trips a year cost
more than the paper's edge (B §3). Members are daily, long-only and use closes only.

**One share each.** The paper holds the average of its members' positions. Here each
member holds its own slice of the coin's allocation: a coin's allocation is 1/N of the
account (N coins), and each of the M members' trades is 1/M of it, times the sizing
policy's scale (``strategy_lab.sizing``, applied at entry). All members long with
scale 1 is the coin's whole allocation, so the book never holds more than the account,
where the paper sizes up to 200%. Each member's entry and exit is its own order, with
its own fees and the venue's minimum (a slice below the minimum is skipped, never
raised), as a trader holding the slices would pay. The paper re-sizes daily inside a
20% band; this sizes once at entry, so no trades are added (B §12). Without that
re-sizing, slices that have gained leave less cash than a new slice's share of the
account, and such an entry is skipped (``skipped_cash``), as it would be for a trader
holding the slices.

**In the replay** each (coin, member) is its own book entry, ``<coin>~<days>``, marked
at the coin's closes (and lows and highs, for the intrabar drawdown), with the
coin's minimum and sell step. The figures
are ``replay``'s, against each member alone (the coin's whole allocation) and an
equal-weight buy-and-hold of the same coins.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from signal_fusion.evaluation.replay import Account, Costs, Opportunity, Paths, replay
from strategy_lab import baselines as bl
from strategy_lab import sizing
from strategy_lab.candidates import RunnerSpec, Trade
from strategy_lab.simulate import Simulation, Universe

DAY_S = 86_400
LOOKBACKS = (20, 30, 60, 90, 150, 250, 360)  # the paper's members of 20 days or more
SEP = "~"


def member_spec(days: int) -> RunnerSpec:
    """One member: STRAT-007 and OVL-MIDLINE on ``days``."""
    return RunnerSpec(
        "STRAT-007",
        {"channel_days": int(days)},
        ({"id": "OVL-MIDLINE", "params": {"days": int(days)}},),
        "1d",
    )


def warmup_days(lookbacks: Sequence[int] = LOOKBACKS) -> int:
    """The days of candles the longest member needs before its first decision."""
    return int(max(lookbacks)) + 2


def _key(coin: str, days: int) -> str:
    return f"{coin}{SEP}{days}"


@dataclass
class Ensemble:
    """The members on one universe of daily candles (module docstring)."""

    universe: Universe
    lookbacks: Sequence[int] = LOOKBACKS
    sims: Dict[int, Simulation] = field(init=False)

    def __post_init__(self) -> None:
        if self.universe.timeframe != "1d":
            raise ValueError("the ensemble runs on daily candles")
        days = sorted({int(n) for n in self.lookbacks})
        if not days or days[0] < 20:
            raise ValueError("members are of 20 days or more")
        self.lookbacks = tuple(days)
        self.sims = {n: Simulation(self.universe, member_spec(n)) for n in days}

    @property
    def coins(self) -> List[str]:
        return sorted(self.universe.frames)

    def trades(self, from_s: Optional[int] = None) -> Dict[int, List[Trade]]:
        """Each member's trades entered at or after ``from_s``."""
        out = {}
        for n, sim in self.sims.items():
            out[n] = [
                t for t in sim.candidates() if from_s is None or t.entry_s >= from_s
            ]
        return out

    def _series(self, method: str) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        """The coins' series (``prices``, ``lows`` or ``highs``) under every member's
        key."""
        first = next(iter(self.sims.values()))
        per_coin = getattr(first, method)()
        return {_key(coin, n): v for coin, v in per_coin.items() for n in self.sims}

    def replay(
        self,
        costs: Costs,
        account_usd: float,
        policy=None,
        from_s: Optional[int] = None,
        detail: bool = False,
        members: Optional[Sequence[int]] = None,
    ) -> Paths:
        """The members in ``members`` (all by default), each with 1/M of a coin's
        allocation of 1/N, in one account (module docstring)."""
        chosen = list(members or self.lookbacks)
        share = 1.0 / len(chosen)
        policy = policy or sizing.Fixed()
        by_member = self.trades(from_s)
        opps: List[Opportunity] = []
        scales: List[float] = []
        for n in chosen:
            trades = by_member[n]
            s = policy.scales(self.sims[n], trades).scale
            for t, sc in zip(trades, s):
                opps.append(
                    Opportunity(
                        _key(t.coin, n),
                        t.entry_s,
                        t.exit_s,
                        t.entry_price,
                        t.exit_price,
                    )
                )
                scales.append(float(sc) * share)
        keys = [_key(c, n) for c in self.coins for n in chosen]
        coin_of = {_key(c, n): c for c in self.coins for n in chosen}
        book_costs = Costs(
            fee=costs.fee,
            allowance=costs.allowance,
            minimum_usd={
                k: costs.minimum_usd[coin_of[k]]
                for k in keys
                if coin_of[k] in costs.minimum_usd
            },
            base_increment={
                k: costs.base_increment[coin_of[k]]
                for k in keys
                if coin_of[k] in costs.base_increment
            },
        )
        pct = 100.0 / len(self.coins)
        account = Account(start=float(account_usd), start_pct=pct, max_coin_pct=pct)
        first = next(iter(self.sims.values()))
        return replay(
            opps,
            self._series("prices"),
            book_costs,
            account,
            scale=np.array(scales)[None, :] if opps else None,
            mark_s=DAY_S,
            end_s=first.end_s(),
            lows=self._series("lows"),
            highs=self._series("highs"),
            detail=detail,
        )

    def hold(self, costs: Costs, account_usd: float, from_s: Optional[int]) -> Paths:
        """Equal-weight buy-and-hold of the coins: 1/N each, from the first decision
        bar at or after ``from_s`` to the last close."""
        first = next(iter(self.sims.values()))
        pct = 100.0 / len(self.coins)
        account = Account(start=float(account_usd), start_pct=pct, max_coin_pct=pct)
        return first.replay(bl.hold_trades(first, from_s), costs, account)


def report(
    ens: Ensemble,
    costs: Costs,
    account_usd: float,
    policy=None,
    from_s: Optional[int] = None,
) -> Dict[str, Any]:
    """The ensemble, each member alone (with the coin's whole allocation), and an
    equal-weight buy-and-hold, as figures (``strategy_lab.runs._figures``)."""
    from strategy_lab.runs import _figures  # runs imports this module

    policy = policy or sizing.Fixed()
    book = ens.replay(costs, account_usd, policy, from_s, detail=True)
    years = _years(ens, from_s)
    members = {}
    for n in ens.lookbacks:
        alone = ens.replay(costs, account_usd, policy, from_s, members=[n])
        members[str(n)] = {
            **_figures(alone),
            "trades_per_coin_year": (
                int(alone.trades[0]) / (len(ens.coins) * years) if years else None
            ),
        }
    return {
        "lookbacks": list(ens.lookbacks),
        "coins": ens.coins,
        "policy": policy.record(),
        "ensemble": _figures(book),
        "members": members,
        "equal_weight_hold": _figures(ens.hold(costs, account_usd, from_s)),
    }


def _years(ens: Ensemble, from_s: Optional[int]) -> float:
    first = next(iter(ens.sims.values()))
    end = first.end_s()
    start = from_s
    if start is None:
        start = min(int(t.prices()[0][0]) for t in first.tables.values())
    return max(0.0, (end - start) / (365 * DAY_S))
