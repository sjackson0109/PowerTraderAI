"""
Today's venue rules per coin (FDS-SR-001 section 5.10): the minimum order and the step a
market sell is rounded down to, through the exchange layer (the exchanges in Settings,
primary first; unauthenticated product data). Past values are not recorded anywhere, so
an evaluation records the ones it used.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Optional, Sequence


@dataclass(frozen=True)
class VenueRules:
    minimum_usd: Dict[str, float]
    base_increment: Dict[str, float]
    unknown: Dict[str, str]  # coin -> what could not be read

    def as_record(self) -> dict:
        return {
            "minimum_usd": dict(self.minimum_usd),
            "base_increment": dict(self.base_increment),
            "unknown": dict(self.unknown),
        }


def venue_rules(
    coins: Sequence[str], manager_factory: Optional[Callable[[], object]] = None
) -> VenueRules:
    """Each coin's minimum order and sell step, or what could not be read."""
    if manager_factory is None:
        from pt_multi_exchange import market_exchanges

        manager_factory = market_exchanges
    manager = manager_factory()
    minimum: Dict[str, float] = {}
    step: Dict[str, float] = {}
    unknown: Dict[str, str] = {}
    for coin in coins:
        symbol = f"{coin}-USD"
        missing = []
        try:
            m = manager.min_order_usd(symbol)
        except Exception:
            m = None
        if m:
            minimum[coin] = float(m)
        else:
            missing.append("minimum order")
        try:
            s = manager.lot_increment(symbol)
        except Exception:
            s = None
        if s:
            step[coin] = float(s)
        else:
            missing.append("sell step")
        if missing:
            unknown[coin] = " and ".join(missing)
    return VenueRules(minimum, step, unknown)
