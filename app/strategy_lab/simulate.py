"""
One load of candles, any number of accounts (FDS-SR-001 section 5.10).

``load_universe`` reads each coin's candles once, and each series an entry gate declared
(``context_needs``) once, through the exchange layer and its cache
(``market_data.candles.exchange_candles``: the primary exchange first; offline, the cache
only). ``Simulation`` builds one ``TradeTable`` per coin from it, and replays the same
trades in one shared account per size (``signal_fusion.evaluation.replay``), marked at
every close of the strategy's timeframe.

**Accounts in pounds.** The pairs are quoted in US dollars, so an account given in GBP is
converted at one GBP-to-USD rate, which the caller states (``usd_accounts``) and every
result records. Nothing reads a rate live.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from market_data.candles import exchange_candles, to_utc
from signal_fusion.evaluation.replay import Account, Costs, Paths, replay
from strategy_lab.candidates import RunnerSpec, Trade, TradeTable

ACCOUNTS_GBP = (50.0, 500.0, 10_000.0)  # FDS-SR-001 section 5.10

Loader = Callable[..., pd.DataFrame]


def usd_accounts(gbp: Sequence[float], gbp_usd: float) -> Dict[float, float]:
    """``{pounds: dollars}`` at the stated rate (FDS-SR-001 E-D6: one declared rate)."""
    rate = float(gbp_usd)
    if not rate > 0:
        raise ValueError(f"the GBP-to-USD rate must be above 0, got {gbp_usd!r}")
    return {float(a): round(float(a) * rate, 2) for a in gbp}


@dataclass
class Universe:
    """The candles of one evaluation: per coin, and per declared reference series."""

    timeframe: str
    frames: Dict[str, pd.DataFrame]
    # (reference, timeframe) -> frame; "self" references are per coin
    shared: Dict[Tuple[str, str], pd.DataFrame] = field(default_factory=dict)
    own: Dict[str, Dict[Tuple[str, str], pd.DataFrame]] = field(default_factory=dict)
    sources: Dict[str, Any] = field(default_factory=dict)

    def context_for(self, coin: str) -> Dict[Tuple[str, str], pd.DataFrame]:
        out = dict(self.shared)
        out.update(self.own.get(coin, {}))
        return out


def load_universe(
    coins: Sequence[str],
    spec: RunnerSpec,
    start,
    end,
    *,
    cache_dir: Optional[str] = None,
    offline: bool = False,
    loader: Loader = exchange_candles,
) -> Universe:
    """Each coin's candles, and each declared context series, read once."""
    frames: Dict[str, pd.DataFrame] = {}
    sources: Dict[str, Any] = {}
    for coin in coins:
        frame = loader(
            f"{coin}-USD",
            spec.timeframe,
            start,
            end,
            cache_dir=cache_dir,
            offline=offline,
        )
        frames[coin] = frame
        sources[f"{coin}:{spec.timeframe}"] = dict(frame.attrs)
    universe = Universe(spec.timeframe, frames, sources=sources)
    needs = spec.build().context_needs()
    for reference, tf, bars in needs:
        back = pd.Timedelta(days=int(bars) + 2) if tf == "1d" else pd.Timedelta(0)
        begin = to_utc(start) - back
        if reference == "self":
            for coin in coins:
                if tf == spec.timeframe:
                    series = frames[coin]
                else:
                    series = loader(
                        f"{coin}-USD",
                        tf,
                        begin,
                        end,
                        cache_dir=cache_dir,
                        offline=offline,
                    )
                    sources[f"{coin}:{tf}"] = dict(series.attrs)
                universe.own.setdefault(coin, {})[("self", tf)] = series
        else:
            series = loader(
                f"{reference}-USD", tf, begin, end, cache_dir=cache_dir, offline=offline
            )
            universe.shared[(reference, tf)] = series
            sources[f"{reference}:{tf}"] = dict(series.attrs)
    return universe


class Simulation:
    """A strategy's trades on every coin of a ``Universe``, replayed per account."""

    def __init__(self, universe: Universe, spec: RunnerSpec) -> None:
        if universe.timeframe != spec.timeframe:
            raise ValueError("the universe and the strategy have different timeframes")
        self.universe = universe
        self.spec = spec
        self.tables: Dict[str, TradeTable] = {
            coin: TradeTable(coin, frame, spec, universe.context_for(coin))
            for coin, frame in universe.frames.items()
            if len(frame) >= 2
        }

    def candidates(self) -> List[Trade]:
        """Every coin's candidate trades, by entry time."""
        out = [t for table in self.tables.values() for t in table.candidates()]
        return sorted(out, key=lambda t: (t.entry_s, t.coin))

    def prices(self) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        return {coin: table.prices() for coin, table in self.tables.items()}

    def end_s(self) -> int:
        return max(int(table.prices()[0][-1]) for table in self.tables.values())

    def replay(
        self,
        trades: Sequence[Trade],
        costs: Costs,
        account: Account,
        **kw,
    ) -> Paths:
        """``trades`` in one shared account, with the strategy's cooldown, marked at
        every close of its timeframe."""
        return replay(
            [t.opportunity() for t in trades],
            self.prices(),
            costs,
            account,
            mark_s=self.spec.bar_seconds,
            cooldown=self.spec.cooldown(),
            end_s=self.end_s(),
            **kw,
        )

    def accounts(
        self,
        sizes_usd: Mapping[Any, float],
        costs: Costs,
        trades: Optional[Sequence[Trade]] = None,
        **kw,
    ) -> Dict[Any, Paths]:
        """The same trades (the candidates by default) at each account size: the
        candles and the trades are computed once, whatever the number of accounts."""
        trades = self.candidates() if trades is None else trades
        return {
            label: self.replay(trades, costs, Account(start=float(usd)), **kw)
            for label, usd in sizes_usd.items()
        }
