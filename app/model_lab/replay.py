"""
The fixed strategy's trades (FDS-MH-001 section 5.3).

Every trade is replayed with ``model_gate.replay`` and the batch's trade rules
(``model_gate.trade_rules``): the trader's exits, DCA and sizing, the 24-hour DCA cap,
the per-coin budget, and the fee and slippage on every fill. Each coin trades a
``model_gate.ACCOUNT``-unit account, not compounded. A trade still open when its stream
ends is sold at the last close, its exit fee included.

**Neural DCA is off** for every contestant: the replay is given no long counts, so a
DCA buy is made only at the stage's hard level. With it off, a trade depends only on its
entry hour, so a coin's trade from each stream hour is replayed once (``TradeTable``)
and every contestant and every random draw reuses it. The pattern model is also shown
with neural DCA on, from its own long counts (a table of its own).

Each coin holds one trade at a time (``schedule``). A trade that ends at an hour's
close leaves that hour free for the next entry.
"""

from __future__ import annotations

import bisect
from typing import Callable, List, Optional, Sequence, Tuple

import entry_gate
import model_gate

Trade = entry_gate.Trade


class TradeTable:
    """A coin's trades from every hour of its stream: ``trade(i)`` is the trade an
    entry at the close of hour ``i`` makes, replayed the first time it is asked for."""

    def __init__(
        self,
        close_s: Sequence[int],
        price: Sequence[float],
        rules: model_gate.TradeRules,
        fees: entry_gate.Fees,
        longs: Optional[Sequence[Optional[int]]] = None,
    ):
        n = len(price)
        self.hours = model_gate.Hours(
            tuple(int(t) for t in close_s),
            tuple(float(p) for p in price),
            tuple(longs) if longs is not None else (None,) * n,
            (None,) * n,
        )
        self.rules = rules
        self.fees = fees
        self._trades: List[Optional[Trade]] = [None] * n

    def __len__(self) -> int:
        return len(self._trades)

    def trade(self, i: int) -> Trade:
        t = self._trades[i]
        if t is None:
            t = model_gate.replay(i, self.hours, self.rules, self.fees)
            self._trades[i] = t
        return t

    def fill(self, stop: Optional[Callable[[], bool]] = None) -> int:
        """Replay every hour's trade now; the number replayed (fewer when ``stop``
        said so)."""
        for i in range(len(self._trades)):
            if stop is not None and i % 2000 == 0 and stop():
                return i
            self.trade(i)
        return len(self._trades)

    def replayed(self) -> int:
        return sum(1 for t in self._trades if t is not None)


def schedule(
    ones: Sequence[int], table: TradeTable, start: int = 0
) -> List[Tuple[int, Trade]]:
    """The trades of an entry signal held one at a time: an entry at each hour of
    ``ones`` (ascending) from ``start`` on, while no trade is open."""
    out: List[Tuple[int, Trade]] = []
    free = start
    k = bisect.bisect_left(ones, free)
    while k < len(ones):
        i = ones[k]
        t = table.trade(i)
        out.append((i, t))
        free = max(t.end, i + 1)
        k = bisect.bisect_left(ones, free, k + 1)
    return out
