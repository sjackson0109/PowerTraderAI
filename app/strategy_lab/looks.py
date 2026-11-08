"""
Earlier looks at strategies' results (FDS-SR-001 section 6.1), recorded in code like
FDS-MH-001's ``LOOKS``: adding one is a reviewed change, with the months and coins it
covered and where it is written up.

* A **strategy** look read the strategy's own trades. A strategy whose final-check
  months were seen cannot have that check counted as unseen evidence.
* A **related** look read a related entry signal under other exits (the lab's rule
  contestants): recorded beside a strategy, never treated as a look at it.

Exploratory runs from Settings are recorded in the trial log instead, with their months.
"""

from __future__ import annotations

from typing import List, Tuple

from model_lab.catalogue import Look, seen_in
from model_lab.series import epoch

STRATEGY_LOOKS: Tuple[Look, ...] = (
    Look(
        "STRAT-001",
        "2023-01-01",
        "2026-10-01",
        "BTC, ETH (Binance, 1h and 4h)",
        "2026-10-02",
        "strategy batch 1's backtest, in-sample and out-of-sample "
        "(docs/dev/BACKTEST-REPORT-batch-1.md)",
    ),
    Look(
        "STRAT-002",
        "2023-01-01",
        "2026-10-01",
        "BTC, ETH (Binance, 1h and 4h)",
        "2026-10-02",
        "strategy batch 1's backtest, in-sample and out-of-sample "
        "(docs/dev/BACKTEST-REPORT-batch-1.md)",
    ),
    Look(
        "STRAT-001",
        "2021-01-01",
        "2025-05-06",
        "11 coins (Coinbase, 1h)",
        "2026-11-07",
        "FDS-SIG-004's development run (docs/dev/SIG4-REPORT-dev.md)",
    ),
)

_PHASE_B = (
    "FDS-MH-001's phase B timing run (batch 20261106-143033): the lab's rule "
    "contestant under the legacy exits, walk-forward only (docs/dev/RUN-LOG-mh-1.md)"
)

# related entry signals: (strategy, the lab contestant, the look)
RELATED: Tuple[Tuple[str, Look], ...] = (
    (
        "STRAT-004",
        Look(
            "rule.high20",
            "2021-01-01",
            "2025-05-06",
            "13 coins",
            "2026-11-06",
            _PHASE_B,
        ),
    ),
    (
        "STRAT-005",
        Look(
            "rule.mom14", "2021-01-01", "2025-05-06", "13 coins", "2026-11-06", _PHASE_B
        ),
    ),
)


def seen(strategy_id: str, start, end) -> List[Look]:
    """The strategy looks at ``strategy_id`` that cover any of [start, end)."""
    return seen_in(strategy_id, epoch(start), epoch(end), STRATEGY_LOOKS)


def related(strategy_id: str) -> List[Look]:
    """Looks at related entry signals, recorded beside ``strategy_id``."""
    return [look for sid, look in RELATED if sid == strategy_id]
