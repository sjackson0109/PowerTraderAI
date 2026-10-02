"""Rule-based strategies: one interface for the backtester and the live/paper trader."""

from strategies.base import Action, Signal, Strategy, StrategyError  # noqa: F401
from strategies.catalogue import (  # noqa: F401
    CATALOGUE,
    CatalogueError,
    ParamError,
    create,
    get_entry,
    list_ids,
    register,
)
