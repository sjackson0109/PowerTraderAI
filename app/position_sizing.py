"""How big a trade is (owner, 2026-10-24). Read by the trader, and by the hub for its
Settings hints and the Account panel's DCA counts.

* An entry is ``start_allocation_pct`` of the account value (default 1%). An amount
  below the exchange's minimum order is raised to that minimum (the broker's when
  trading live; in paper trading, the primary exchange's, else another enabled
  exchange's), with room for the spread, a market buy's and sell's fees and
  ``min_order_margin_pct`` (default 2%): a buy at the ask is worth less at the bid,
  and one raised to exactly the minimum was then worth less than it, taken for a
  remainder too small to sell, and bought again.
* A coin may use at most ``max_coin_allocation_pct`` of the account (default 10%). A
  DCA buy that would take the coin past that budget is skipped, so the DCA ladder ends
  there instead of repeating its last level for ever. Each DCA buy is the position's
  current value times the DCA multiplier, so with the default 2.0 every DCA roughly
  triples what the coin holds.

The upstream defaults were a 0.005% entry and a fixed $0.50 floor. On an account
under $10,000 every entry was the floor, and $0.50 is below many exchanges' minimum
order.
"""

from typing import Any, Optional

DEFAULT_START_ALLOCATION_PCT = 1.0
DEFAULT_MAX_COIN_ALLOCATION_PCT = 10.0
UPSTREAM_START_ALLOCATION_PCT = 0.005
# Room above the minimum order an entry raised to it keeps, besides the spread and fees
DEFAULT_MIN_ORDER_MARGIN_PCT = 2.0
MIN_ORDER_MARGIN_RANGE = (0.0, 20.0)

# gui_settings.json records which defaults it was written with (see migrate_settings)
DEFAULTS_VERSION_KEY = "allocation_defaults_version"
DEFAULTS_VERSION = 2


def migrate_settings(saved: dict) -> bool:
    """Replace upstream's 0.005% entry with the new default, once. Settings saves every
    field, so 0.005% in a file written before the new defaults is the old default, not
    a choice; after this the file carries the version, and any value is the user's.
    Returns True when ``saved`` changed (it should then be written back)."""
    if saved.get(DEFAULTS_VERSION_KEY) is not None:
        return False
    try:
        old = float(saved.get("start_allocation_pct"))
    except (TypeError, ValueError):
        old = None
    if old == UPSTREAM_START_ALLOCATION_PCT:
        saved["start_allocation_pct"] = DEFAULT_START_ALLOCATION_PCT
    saved[DEFAULTS_VERSION_KEY] = DEFAULTS_VERSION
    return True


def valid_min_order_margin_pct(value: Any) -> bool:
    """Whether ``value`` is a usable ``min_order_margin_pct``: a number from 0 to 20."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    low, high = MIN_ORDER_MARGIN_RANGE
    return low <= value <= high


def quote_spread(ask: Any, bid: Any) -> float:
    """How far the ask is above the bid, as a fraction of the bid ((ask - bid) / bid):
    what a coin bought at the ask loses when valued at the bid. 0 when either price
    is not known."""
    try:
        ask, bid = float(ask), float(bid)
    except (TypeError, ValueError):
        return 0.0
    if not (bid > 0.0 and ask > bid):
        return 0.0
    return (ask - bid) / bid


def minimum_entry_usd(
    minimum_usd: Optional[float],
    spread: float = 0.0,
    round_trip_fee: float = 0.0,
    margin_pct: float = DEFAULT_MIN_ORDER_MARGIN_PCT,
) -> Optional[float]:
    """The smallest entry still worth the exchange's minimum order (``minimum_usd``)
    when valued at the bid after its fees: minimum x (1 + spread + round-trip fee +
    margin). ``spread`` is (ask - bid) / bid and ``round_trip_fee`` the buy's and the
    sell's fee rates added together, both fractions; ``margin_pct`` is a percentage.
    None when there is no minimum."""
    if not minimum_usd:
        return None
    room = max(0.0, float(spread)) + max(0.0, float(round_trip_fee))
    return float(minimum_usd) * (1.0 + room + max(0.0, float(margin_pct)) / 100.0)


def entry_usd(
    account_value: float,
    start_pct: float,
    minimum_usd: Optional[float] = None,
    spread: float = 0.0,
    round_trip_fee: float = 0.0,
    margin_pct: float = DEFAULT_MIN_ORDER_MARGIN_PCT,
) -> float:
    """The amount for a new trade: ``start_pct`` of the account value, raised to the
    exchange's minimum order (``minimum_usd``) with room for the spread, the fees and
    the margin (``minimum_entry_usd``) when it is below that."""
    amount = max(0.0, float(account_value)) * max(0.0, float(start_pct)) / 100.0
    floor = minimum_entry_usd(minimum_usd, spread, round_trip_fee, margin_pct)
    if floor and amount < floor:
        amount = floor
    return amount


def coin_budget_usd(account_value: float, max_coin_pct: float) -> float:
    """The most one coin may hold, at cost: ``max_coin_pct`` of the account value."""
    return max(0.0, float(account_value)) * max(0.0, float(max_coin_pct)) / 100.0


def dca_fits_budget(
    invested_usd: float, dca_usd: float, account_value: float, max_coin_pct: float
) -> bool:
    """Whether a DCA buy of ``dca_usd`` keeps the coin (``invested_usd`` at cost so far)
    within its budget."""
    budget = coin_budget_usd(account_value, max_coin_pct)
    return float(invested_usd) + float(dca_usd) <= budget + 1e-9


def dca_levels_affordable(
    account_value: float,
    start_pct: float,
    max_coin_pct: float,
    dca_multiplier: float,
    coins: int = 1,
) -> int:
    """How many DCA buys each of ``coins`` coins can make before one more would pass
    its budget or, all coins together, the account. An estimate: each DCA multiplies a
    coin's cost by (1 + multiplier), as if the price had not moved."""
    entry = entry_usd(account_value, start_pct)
    factor = 1.0 + max(0.0, float(dca_multiplier))
    if entry <= 0.0 or factor <= 1.0:
        return 0
    budget = coin_budget_usd(account_value, max_coin_pct)
    total = max(0.0, float(account_value))
    coins = max(1, int(coins))
    levels, cost = 0, entry
    while cost * factor <= budget + 1e-9 and coins * cost * factor <= total + 1e-9:
        cost *= factor
        levels += 1
    return levels
