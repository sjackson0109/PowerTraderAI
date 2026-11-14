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

**Any trades through the same book** (``replay_trades``): the replay above takes each
member's trades, so the book's own and a random baseline's go through the same account,
slices, minimums and skips; ``replay_draws`` replays many draws at once, as
``baselines.replay_draws`` does for one strategy.

**Random entries for the book** (REF-RANDOM-E, ``random_draws``): for each (coin,
member) slice, as many random entries as the book's path took in that slice, on that
coin's decision bars, each exited by that member's own rule and midline ratchet: per
member, REF-RANDOM's draws (``baselines.random_draws``, same waits in a random order)
on that member's trades in the book. Member k of ``lookbacks`` (in order) draws its
draw b with ``random.Random(seed + k * count + b)``, so no two members share a seed.
**Matched holding** (``matched_draws``) is the same with ``baselines.matched_draws``:
random entries per slice, each held as long as one of that slice's trades; reported
only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np

from signal_fusion.evaluation.replay import Account, Costs, Opportunity, Paths, replay
from strategy_lab import baselines as bl
from strategy_lab import sizing
from strategy_lab.candidates import RunnerSpec, Trade
from strategy_lab.simulate import Simulation, Universe

DAY_S = 86_400
LOOKBACKS = (20, 30, 60, 90, 150, 250, 360)  # the paper's members of 20 days or more
SEP = "~"

ByMember = Mapping[int, Sequence[Trade]]


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
class BookDraws:
    """Each draw's trades by member; the book's own entries in each slice
    (``<coin>~<days>``); the entries each draw reached; and, for matched holding, the
    book's trades each draw could not place."""

    draws: List[Dict[int, List[Trade]]]
    wanted: Dict[str, int]
    reached: List[int]
    dropped: Optional[List[int]] = None


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

    def _coins(self, coins: Optional[Sequence[str]]) -> List[str]:
        if coins is None:
            return self.coins
        unknown = sorted(set(coins) - set(self.coins))
        if unknown:
            raise ValueError(f"not in the ensemble's universe: {unknown}")
        if not coins:
            raise ValueError("the book needs at least one coin")
        return sorted(set(coins))

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

    @staticmethod
    def slices(by_member: ByMember) -> List[Tuple[int, Trade]]:
        """Each (member, trade) of ``by_member``, in the order the book replays them:
        the opportunity index of a path's ``detail``."""
        return [(int(n), t) for n, trades in by_member.items() for t in trades]

    def taken(self, by_member: ByMember, path: Paths) -> Dict[int, List[Trade]]:
        """Path 0's trades, by member, of a ``replay_trades(by_member, ...,
        detail=True)`` (or a ``replay`` of the same trades)."""
        order = self.slices(by_member)
        out: Dict[int, List[Trade]] = {int(n): [] for n in by_member}
        for i, *_ in path.detail:
            n, t = order[i]
            out[n].append(t)
        return out

    def replay_trades(
        self,
        by_member: ByMember,
        costs: Costs,
        account_usd: float,
        policy=None,
        detail: bool = False,
        veto: Optional[np.ndarray] = None,
        coins: Optional[Sequence[str]] = None,
    ) -> Paths:
        """``by_member``'s trades (``{days: trades}``) in one account, each member's
        with 1/M of a coin's allocation of 1/N (M the members given, N the coins), as
        the module docstring says. ``veto`` (paths, n), over ``slices(by_member)``,
        replays many paths at once; ``coins`` (all by default) are the book's N coins,
        and every trade must be on one of them."""
        keep = self._coins(coins)
        chosen = [int(n) for n in by_member]
        if not chosen:
            raise ValueError("the book needs at least one member")
        share = 1.0 / len(chosen)
        policy = policy or sizing.Fixed()
        opps: List[Opportunity] = []
        scales: List[float] = []
        for n in chosen:
            trades = list(by_member[n])
            if any(t.coin not in keep for t in trades):
                raise ValueError(f"member {n} has trades on coins outside the book")
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
        keys = [_key(c, n) for c in keep for n in chosen]
        coin_of = {_key(c, n): c for c in keep for n in chosen}
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
        pct = 100.0 / len(keep)
        account = Account(start=float(account_usd), start_pct=pct, max_coin_pct=pct)
        first = next(iter(self.sims.values()))
        scale = None
        if opps:
            rows = 1 if veto is None else int(np.asarray(veto).shape[0])
            scale = np.tile(np.array(scales), (rows, 1))
        return replay(
            opps,
            self._series("prices"),
            book_costs,
            account,
            veto=veto,
            scale=scale,
            mark_s=DAY_S,
            end_s=first.end_s(),
            lows=self._series("lows"),
            highs=self._series("highs"),
            detail=detail,
        )

    def replay(
        self,
        costs: Costs,
        account_usd: float,
        policy=None,
        from_s: Optional[int] = None,
        detail: bool = False,
        members: Optional[Sequence[int]] = None,
        coins: Optional[Sequence[str]] = None,
    ) -> Paths:
        """The members in ``members`` (all by default), each with 1/M of a coin's
        allocation of 1/N, in one account (module docstring); on ``coins`` (all by
        default)."""
        chosen = list(members or self.lookbacks)
        keep = set(self._coins(coins))
        by_member = self.trades(from_s)
        picked = {n: [t for t in by_member[n] if t.coin in keep] for n in chosen}
        return self.replay_trades(
            picked, costs, account_usd, policy, detail, coins=sorted(keep)
        )

    def replay_draws(
        self,
        draws: Sequence[ByMember],
        costs: Costs,
        account_usd: float,
        policy=None,
        chunk: int = 200,
        coins: Optional[Sequence[str]] = None,
    ) -> Paths:
        """Every draw (``{days: trades}``) as one path of the book: ``chunk`` at a
        time over the union of their (member, trade)s, each path vetoing those that
        are not its own. The replay checks the cash before a path's veto, so a path's
        ``skipped_cash`` also counts other draws' entries it could not have funded
        (and ``vetoed`` counts them all): a draw's own skips come from replaying it
        alone (``replay_trades``). Its trades, net, capital-days, drawdowns and
        minimum skips are its own."""
        parts: List[Paths] = []
        members = [int(n) for n in draws[0]] if draws else list(self.lookbacks)
        for a in range(0, len(draws), chunk):
            group = draws[a : a + chunk]
            union: Dict[int, Dict[Trade, None]] = {n: {} for n in members}
            for d in group:
                for n in members:
                    for t in d.get(n, ()):
                        union[n].setdefault(t, None)
            by_member = {n: list(union[n]) for n in members}
            index = {pair: i for i, pair in enumerate(self.slices(by_member))}
            veto = np.ones((len(group), len(index)), dtype=bool)
            for p, d in enumerate(group):
                for n in members:
                    for t in d.get(n, ()):
                        veto[p, index[(n, t)]] = False
            parts.append(
                self.replay_trades(
                    by_member, costs, account_usd, policy, veto=veto, coins=coins
                )
            )
        return bl._concat(parts)

    def _per_member(self, taken: ByMember, seed: int, count: int, draw) -> BookDraws:
        per = {}
        for n in taken:
            k = self.lookbacks.index(int(n))
            per[int(n)] = draw(self.sims[int(n)], list(taken[n]), seed + k * count)
        wanted = {
            _key(c, int(n)): sum(1 for t in taken[n] if t.coin == c)
            for n in taken
            for c in self.coins
        }
        draws = [{n: per[n].draws[b] for n in per} for b in range(int(count))]
        reached = [sum(len(d[n]) for n in d) for d in draws]
        return BookDraws(draws, wanted, reached)

    def random_draws(
        self,
        taken: ByMember,
        seed: int,
        count: int,
        from_s: Optional[int] = None,
    ) -> BookDraws:
        """REF-RANDOM-E: ``count`` draws of random entries for the book whose path took
        ``taken`` (``{days: trades}``), deciding from ``from_s`` when given (module
        docstring)."""
        return self._per_member(
            taken,
            seed,
            count,
            lambda sim, mine, s: bl.random_draws(sim, mine, s, count, from_s),
        )

    def matched_draws(
        self,
        taken: ByMember,
        seed: int,
        count: int,
        from_s: Optional[int] = None,
    ) -> BookDraws:
        """``count`` matched-holding draws for the book whose path took ``taken``: per
        slice, random entries each held as long as one of that slice's trades
        (``baselines.matched_draws``); reported only."""
        made = {}

        def draw(sim, mine, s):
            made[sim] = bl.matched_draws(sim, mine, s, count, from_s)
            return made[sim]

        out = self._per_member(taken, seed, count, draw)
        out.dropped = [
            sum(m.dropped[b] for m in made.values()) for b in range(int(count))
        ]
        return out

    def hold_trades(
        self, from_s: Optional[int], coins: Optional[Sequence[str]] = None
    ) -> List[Trade]:
        """The equal-weight hold's trades: each coin bought once, at the open after its
        first decision bar at or after ``from_s``, held to the last close."""
        first = next(iter(self.sims.values()))
        keep = set(self._coins(coins))
        return [t for t in bl.hold_trades(first, from_s) if t.coin in keep]

    def hold(
        self,
        costs: Costs,
        account_usd: float,
        from_s: Optional[int],
        detail: bool = False,
        coins: Optional[Sequence[str]] = None,
    ) -> Paths:
        """Equal-weight buy-and-hold of the coins (``coins``, all by default): 1/N each,
        from the first decision bar at or after ``from_s`` to the last close."""
        first = next(iter(self.sims.values()))
        keep = self._coins(coins)
        pct = 100.0 / len(keep)
        account = Account(start=float(account_usd), start_pct=pct, max_coin_pct=pct)
        return first.replay(
            self.hold_trades(from_s, keep), costs, account, detail=detail
        )


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
