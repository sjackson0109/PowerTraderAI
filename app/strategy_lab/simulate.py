"""
One load of candles, any number of accounts (FDS-SR-001 section 5.10).

``load_universe`` reads each coin's candles once, and each series an entry gate declared
(``context_needs``) once, through the exchange layer and its cache
(``market_data.candles.exchange_candles``: the primary exchange first; offline, the cache
only). ``Simulation`` builds one ``TradeTable`` per coin from it, and replays the same
trades in one shared account per size (``signal_fusion.evaluation.replay``), marked at
every close of the strategy's timeframe.

**Within the bar.** Every replay is also given each coin's lows and highs, so each
result carries the intrabar figures beside the close-based ones: the drawdown and the
first halt with every open position valued at its bar's low, from a peak that takes the
earlier bars' highs (``replay``'s module docstring says how, and what the bound means
with several coins). The trader checks its value on every pass, so a fall that recovers
by the close can halt it. The owner chose this measure for future registered
evaluations (2026-11-12); in a replay the figures decide nothing.

**Gaps.** A series with a gap longer than a day (an exchange halt) is used from after its
last such gap (``after_long_gaps``), so no trade or lookback spans months with no market.

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
from market_data.timeframes import candle_timeframe_seconds
from signal_fusion.evaluation.replay import Account, Costs, Paths, replay
from strategy_lab.candidates import RunnerSpec, Trade, TradeTable

ACCOUNTS_GBP = (50.0, 500.0, 10_000.0)  # FDS-SR-001 section 5.10
MAX_GAP_S = 24 * 3600  # a longer gap ends the earlier part of a series (model lab's)

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


def after_long_gaps(
    frame: pd.DataFrame, bar_seconds: int
) -> Tuple[pd.DataFrame, Optional[Dict[str, Any]]]:
    """``frame`` from the first bar after its last gap longer than ``MAX_GAP_S``, and
    the cut for the run's record (None when there is no such gap).

    A gap of up to 24 hours is kept: there is no bar in it, so no entry is made there,
    and an open trade carries on at the next bar. A longer gap (an exchange halt, a
    delisting and relisting) ends the earlier part, as in the model lab
    (``model_lab.series``): otherwise a trade, or an indicator's lookback, would run
    straight across months with no market."""
    if len(frame) < 2:
        return frame, None
    times = frame["open_time"]
    missing_s = times.diff().dt.total_seconds().to_numpy() - float(bar_seconds)
    long_gaps = np.flatnonzero(missing_s > MAX_GAP_S)
    if not len(long_gaps):
        return frame, None
    k = int(long_gaps[-1])  # the first bar after the last long gap
    kept = frame.iloc[k:].reset_index(drop=True)
    kept.attrs = dict(frame.attrs)
    cut = {
        "earlier_last_bar": times.iloc[k - 1].isoformat(),
        "kept_from": times.iloc[k].isoformat(),
        "bars_dropped": k,
    }
    return kept, cut


def _series(loader: Loader, symbol: str, tf: str, start, end, **kw):
    """One series read through ``loader``, with ``after_long_gaps`` applied, and its
    source record (the loader's attributes, plus the cut when there was one)."""
    frame, cut = after_long_gaps(
        loader(symbol, tf, start, end, **kw), candle_timeframe_seconds(tf)
    )
    source = dict(frame.attrs)
    if cut is not None:
        source["cut_at_long_gap"] = cut
    return frame, source


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
    """Each coin's candles, and each declared context series, read once. A series with
    a gap longer than a day is used from after its last such gap
    (``after_long_gaps``), and the run's sources record the cut."""
    frames: Dict[str, pd.DataFrame] = {}
    sources: Dict[str, Any] = {}
    kw = dict(cache_dir=cache_dir, offline=offline)
    for coin in coins:
        frame, source = _series(loader, f"{coin}-USD", spec.timeframe, start, end, **kw)
        frames[coin] = frame
        sources[f"{coin}:{spec.timeframe}"] = source
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
                    series, sources[f"{coin}:{tf}"] = _series(
                        loader, f"{coin}-USD", tf, begin, end, **kw
                    )
                universe.own.setdefault(coin, {})[("self", tf)] = series
        else:
            series, sources[f"{reference}:{tf}"] = _series(
                loader, f"{reference}-USD", tf, begin, end, **kw
            )
            universe.shared[(reference, tf)] = series
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

    def lows(self) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        """Each coin's (close times, lows), for the intrabar figures; a coin whose
        candles have no lows is left out (valued at its close)."""
        out = {coin: table.lows() for coin, table in self.tables.items()}
        return {coin: v for coin, v in out.items() if v is not None}

    def highs(self) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
        """Each coin's (close times, highs), for the intrabar figures' peak; a coin
        whose candles have no highs is left out (valued at its close)."""
        out = {coin: table.highs() for coin, table in self.tables.items()}
        return {coin: v for coin, v in out.items() if v is not None}

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
        every close of its timeframe, and within each bar at its low, from a peak that
        takes the earlier bars' highs (the intrabar figures)."""
        if "lows" not in kw:
            kw["lows"] = self.lows()
            if "highs" not in kw:
                kw["highs"] = self.highs()
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
