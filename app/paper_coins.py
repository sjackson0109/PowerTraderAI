"""
Which coins paper trading may open new trades in (Settings > Paper trading).

Two choices, saved in gui_settings.json:

- ``paper_coins_mode = "inherit"`` (the default): the coins in Settings.
- ``paper_coins_mode = "override"``: the coins in ``paper_coins``, a chosen set of the
  coins in Settings. A coin that is not in Settings is not traded: the trader has no
  prices for it.

This limits new entries only. A position already held is still managed (its exits,
and in the legacy engine its DCA buys), so taking a coin off the list never strands
it. Live trading always uses the coins in Settings.
"""

from __future__ import annotations

from typing import Any, Iterable, List, Mapping, Optional

MODE_KEY = "paper_coins_mode"
COINS_KEY = "paper_coins"
INHERIT = "inherit"
OVERRIDE = "override"
MODES = (INHERIT, OVERRIDE)


def normalise(coins: Optional[Iterable[Any]]) -> List[str]:
    """Upper-case coin symbols, blanks and repeats removed, order kept."""
    out: List[str] = []
    for coin in coins or ():
        symbol = str(coin).strip().upper()
        if symbol and symbol not in out:
            out.append(symbol)
    return out


def mode(settings: Optional[Mapping[str, Any]]) -> str:
    """The saved choice; anything but ``override`` inherits the coins in Settings."""
    value = str((settings or {}).get(MODE_KEY) or INHERIT).strip().lower()
    return value if value in MODES else INHERIT


def chosen(settings: Optional[Mapping[str, Any]]) -> List[str]:
    """The coins saved for the override, whichever choice is active."""
    raw = (settings or {}).get(COINS_KEY)
    return normalise(raw if isinstance(raw, (list, tuple)) else ())


def entry_coins(
    settings: Optional[Mapping[str, Any]], coins: Optional[Iterable[Any]]
) -> List[str]:
    """The coins in ``coins`` (the coins in Settings, in their order) that paper
    trading may open new trades in."""
    main = normalise(coins)
    if mode(settings) != OVERRIDE:
        return main
    picked = set(chosen(settings))
    return [coin for coin in main if coin in picked]
