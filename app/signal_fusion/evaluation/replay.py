"""
The portfolio replay (FDS-SIG-004 section 6.0): a strategy's trades in one shared
account, following the trader's rules, for many paths at once.

**Opportunities.** A strategy's entries, with their fills and exits (``Opportunity``),
from the backtester's logic per coin: a signal on bar t's close fills at bar t + 1's open,
and the trade exits on the strategy's own EXIT, at the next open. STRAT-001 fires once per
fresh cross, and a coin is flat at every fresh cross, so every path faces the same
opportunities; a path differs only in which it vetoes or shrinks.

**At each opportunity, in time order** (exits at the same time come first):

1. the coin must be flat: one trade per coin. An entry that fills at the same open as the
   coin's own exit was decided while the position was still open, so it is not taken
   (the backtester ignores ENTER while long); exits first still free cash for other coins;
2. the amount is the trader's own (``position_sizing.entry_usd``): Start allocation % of the
   account's value, raised to the minimum entry (the venue's minimum order with room for a
   spread of 2 x the allowance, two taker fees and the margin) when it is below it;
3. the coin budget (Max per coin %), the minimum entry always allowed above it;
4. an amount above the free cash is skipped and counted as ineligible in that path;
5. then the path's veto, its scale, and the minimum check: a scaled amount below the
   minimum entry is skipped, never raised.

**Costs** are the backtester's: the entry fee comes out of the amount spent, and the exit
fee out of the proceeds, with the allowance as slippage on both fills, so a trade's net
return is (1 + r_g) m(f, e) - 1, m(f, e) = (1 - f)^2 (1 - e) / (1 + e).

**Equity** is marked at every hourly close (cash plus open positions at their coin's last
close), and the maximum drawdown is taken from that curve. The account's value at an
opportunity is its equity then. **Capital-days** are each trade's amount times the days
held.

**The drawdown halt is reported, not modelled.** Resuming after a halt is the owner's
action, which a replay cannot know. Each path reports when its drawdown first reached the
emergency level. With ``halt_ends`` the path ends there instead: nothing opens or closes
after it, and open positions are marked at that hour.

With ``size_fraction`` the amount is that share of the free cash instead (one coin at
100% reproduces ``backtest.engine.run_backtest``'s trades).

**Extensions for FDS-SR-001** (section 5.10). Each is off unless asked for, so a call
without them replays exactly as before:

* ``mark_s`` marks equity on another grid than the hour, e.g. at every daily close.
* ``cooldown`` applies OVL-COOLDOWN's rule per path: an entry decided less than its bars
  after the coin's (or, with ``global_``, any coin's) last exit fill is skipped, longer
  after a loss (the exit fill below the entry fill).
* ``Costs.base_increment``: a sell is sized in coins, rounded down to the coin's
  increment (Coinbase sizes a market sell so; a market buy is sized in dollars). The
  remainder cannot be sold: it stays in the account, marked at the coin's close, and is
  never realised in a trade's net. Each path reports its value at the end (``dust_usd``).
* Each path reports the value of its positions open when the halt level was first
  reached (``halt_exposure``) and their largest further fall in the next 30 days
  (``halt_further_loss``): a halted trader manages nothing.

**Within the bar** (``lows``, off unless given). The marks above are closes, but the
trader checks its value, at the bid, on every pass, so it can halt on a fall that has
recovered by the close. With ``lows`` (each coin's close times and lows, as ``prices``
gives its closes) each path also reports the intrabar figures, beside the close-based
ones and never in their place:

* in each marking interval, the account is valued with every position held through it
  (those held before the fills at the interval's end) at the lowest price its coin
  reached there: the lowest low of the coin's bars that close in the interval, or the
  close at its end if that is lower; cash is unchanged. Positions are valued as the
  marks value them, at the raw price with no fee, and an unsold remainder with them;
* the fall is taken from the peak at the previous mark (the close-marked peak, as
  ``max_drawdown``'s): a low comes before the close that ends its interval;
* ``intrabar_max_drawdown`` (and ``_usd``) is the largest of those falls and of the
  close-based ones, so it is never below ``max_drawdown``; ``intrabar_halt_s`` is the
  end of the first interval in which it reached the halt level (the level was reached
  at some time within that interval), or -1. The level is ``Account.halt_pct``, as for
  ``halt_s``: the trader's emergency stop (``risk.emergency_drawdown_pct``, 8% by
  default), reached at a fall of at least that share of the peak. When ``halt_s`` is
  set, ``intrabar_halt_s`` is set too and is never after it.

For a long-only book, valuing each position at its interval's low gives a lower bound
on the account's worst value in the interval. With several coins, whose lows can come
at different times, the sum is a conservative bound, not the path the account took. The
bound concerns the trough only: the peak is the close-marked one, and a trader that
checks on every pass can see a higher peak between closes. These figures are reported
and decide nothing: no entry, exit or end of a path depends on them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Mapping, Optional, Sequence, Tuple

import numpy as np

import position_sizing

DAY_S = 86400
HOUR_S = 3600


@dataclass(frozen=True)
class Opportunity:
    coin: str
    entry_s: int  # the fill time: the open of the bar after the signal
    exit_s: int  # the exit's fill time
    entry_price: float  # the raw open at the entry fill, before slippage
    exit_price: float  # the raw open (or close, at the end) at the exit fill
    assessable: bool = True  # the filter could assess it (an eligible p̂)

    @property
    def gross(self) -> float:
        return self.exit_price / self.entry_price - 1.0

    @property
    def days(self) -> float:
        return (self.exit_s - self.entry_s) / DAY_S


@dataclass(frozen=True)
class Account:
    start: float = 10_000.0  # the default paper balance (trading_mode.py)
    start_pct: float = position_sizing.DEFAULT_START_ALLOCATION_PCT
    max_coin_pct: float = position_sizing.DEFAULT_MAX_COIN_ALLOCATION_PCT
    margin_pct: float = position_sizing.DEFAULT_MIN_ORDER_MARGIN_PCT
    halt_pct: float = 8.0  # risk.emergency_drawdown_pct's default


@dataclass(frozen=True)
class Costs:
    fee: float  # taker, a fraction a side
    allowance: float = 0.0005  # e: slippage a fill
    minimum_usd: Mapping[str, float] = field(default_factory=dict)  # per coin
    # per coin: the step a sell's quantity is rounded down to (none: not rounded)
    base_increment: Mapping[str, float] = field(default_factory=dict)

    def multiplier(self) -> float:
        """m(f, e)."""
        f, e = self.fee, self.allowance
        return (1.0 - f) ** 2 * (1.0 - e) / (1.0 + e)

    def floor(self, coin: str, margin_pct: float) -> Optional[float]:
        """The coin's minimum entry, or None when no minimum is known."""
        return position_sizing.minimum_entry_usd(
            self.minimum_usd.get(coin),
            2.0 * self.allowance,
            2.0 * self.fee,
            margin_pct,
        )


@dataclass(frozen=True)
class Cooldown:
    """OVL-COOLDOWN's rule, in bars of ``bar_s`` seconds (the strategy's bar)."""

    bars_after_exit: int
    bars_after_loss: int
    global_: bool
    bar_s: int


HALT_WATCH_S = 30 * DAY_S


@dataclass
class Paths:
    """Each path's results (arrays over paths)."""

    net: np.ndarray
    capital_days: np.ndarray
    trades: np.ndarray
    skipped_cash: np.ndarray
    skipped_minimum: np.ndarray
    vetoed: np.ndarray
    max_drawdown: np.ndarray  # the largest fall from a peak, a fraction of it
    max_drawdown_usd: np.ndarray
    halt_s: np.ndarray  # when the drawdown first reached the halt level, or -1
    final_equity: np.ndarray
    time_in_market: np.ndarray  # the share of hours with an open position
    mean_committed: np.ndarray  # mean capital in open positions, a share of equity
    peak_committed: np.ndarray
    start: float
    # path 0's trades, when asked for: (opportunity index, amount, net, capital-days)
    detail: List[Tuple[int, float, float, float]] = field(default_factory=list)
    curve: Optional[Tuple[np.ndarray, np.ndarray]] = None  # path 0's (hours, equity)
    # path 0's outcome at each opportunity, when asked for: "taken", "vetoed",
    # "not_flat", "no_cash", "below_minimum" or "ended" (after a halt ended the path)
    status: List[str] = field(default_factory=list)
    # FDS-SR-001 section 5.10 (zeros when not asked for)
    skipped_cooldown: Optional[np.ndarray] = None
    dust_usd: Optional[np.ndarray] = None
    halt_exposure: Optional[np.ndarray] = None
    halt_further_loss: Optional[np.ndarray] = None
    # within the bar, with ``lows`` (None without them; see the module docstring)
    intrabar_max_drawdown: Optional[np.ndarray] = None  # never below max_drawdown
    intrabar_max_drawdown_usd: Optional[np.ndarray] = None
    intrabar_halt_s: Optional[np.ndarray] = None  # the interval's end, or -1

    def eligible(self) -> List[int]:
        """Path 0's eligible opportunities: flat, with the cash there (taken or vetoed)."""
        return [i for i, s in enumerate(self.status) if s in ("taken", "vetoed")]

    @property
    def rpcd(self) -> np.ndarray:
        """Return per capital-day; 0 for a path with no trades."""
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(self.capital_days > 0, self.net / self.capital_days, 0.0)


def _prices(prices: Mapping[str, Tuple[Sequence[int], Sequence[float]]], coins, hours):
    """Each coin's last close at or before each hour: (hours, coins)."""
    out = np.full((len(hours), len(coins)), np.nan)
    for j, c in enumerate(coins):
        t, p = prices[c]
        t = np.asarray(t, dtype=np.int64)
        p = np.asarray(p, dtype=float)
        k = np.searchsorted(t, hours, side="right") - 1
        ok = k >= 0
        out[ok, j] = p[k[ok]]
    return out


def _lows(
    lows: Mapping[str, Tuple[Sequence[int], Sequence[float]]],
    coins,
    hours: np.ndarray,
    mark_s: int,
) -> np.ndarray:
    """Each coin's lowest low among its bars that close in each marking interval,
    (hours[h] - mark_s, hours[h]]: (hours, coins); NaN where none closes in it, or for
    a coin with no lows."""
    out = np.full((len(hours), len(coins)), np.nan)
    for j, c in enumerate(coins):
        if c not in lows:
            continue
        t, p = lows[c]
        t = np.asarray(t, dtype=np.int64)
        p = np.asarray(p, dtype=float)
        upto = np.searchsorted(t, hours, side="right")  # bars closed by each mark
        since = np.searchsorted(t, hours - mark_s, side="right")  # by the one before
        some = upto > since
        if some.any():
            # the intervals follow one another (the marks are mark_s apart), so each
            # one's bars end where the next one's begin
            out[some, j] = np.fmin.reduceat(p[: upto[some][-1]], since[some])
    return out


def replay(
    opps: Sequence[Opportunity],
    prices: Mapping[str, Tuple[Sequence[int], Sequence[float]]],
    costs: Costs,
    account: Account = Account(),
    veto: Optional[np.ndarray] = None,
    scale: Optional[np.ndarray] = None,
    paths: int = 1,
    size_fraction: Optional[float] = None,
    halt_ends: bool = False,
    detail: bool = False,
    end_s: Optional[int] = None,
    mark_s: int = HOUR_S,
    cooldown: Optional[Cooldown] = None,
    lows: Optional[Mapping[str, Tuple[Sequence[int], Sequence[float]]]] = None,
) -> Paths:
    """Replay the opportunities on ``paths`` paths. ``veto`` (paths, n) is True where a
    path vetoes an opportunity; ``scale`` (paths, n) is its scale (at most 1). ``prices``
    gives each coin's hourly (close times, closes) for marking. ``end_s`` ends the curve
    (default: the last exit). ``lows`` gives each coin's (close times, lows) for the
    intrabar figures; without it they are None."""
    n = len(opps)
    if veto is not None:
        paths = veto.shape[0]
    elif scale is not None:
        paths = scale.shape[0]
    veto = np.zeros((paths, n), dtype=bool) if veto is None else np.asarray(veto, bool)
    scale = np.ones((paths, n)) if scale is None else np.asarray(scale, dtype=float)
    if np.any(scale > 1.0 + 1e-12):
        raise ValueError("a scale is at most 1: nothing makes an entry larger")
    coins = sorted({o.coin for o in opps})
    col = {c: j for j, c in enumerate(coins)}
    f, e = costs.fee, costs.allowance
    floors = {c: costs.floor(c, account.margin_pct) for c in coins}

    # the marking grid (hourly unless ``mark_s`` says otherwise), first entry to end
    if n:
        first = min(o.entry_s for o in opps)
        last = end_s if end_s is not None else max(o.exit_s for o in opps)
        hours = np.arange(first // mark_s * mark_s, last + mark_s, mark_s)
    else:
        hours = np.zeros(0, dtype=np.int64)
    marks = _prices(prices, coins, hours) if n else np.zeros((0, 0))
    intrabar = lows is not None
    low_marks = _lows(lows, coins, hours, mark_s) if (intrabar and n) else None

    cash = np.full(paths, float(account.start))
    qty = np.zeros((paths, len(coins)))
    spent = np.zeros((paths, len(coins)))
    holding = np.full((paths, len(coins)), -1, dtype=np.int64)  # opportunity held
    net = np.zeros(paths)
    held = np.zeros(paths)
    trades = np.zeros(paths, dtype=np.int64)
    skipped_cash = np.zeros(paths, dtype=np.int64)
    skipped_min = np.zeros(paths, dtype=np.int64)
    vetoed = np.zeros(paths, dtype=np.int64)
    peak = np.full(paths, float(account.start))
    mdd = np.zeros(paths)
    mdd_usd = np.zeros(paths)
    halt_s = np.full(paths, -1, dtype=np.int64)
    alive = np.ones(paths, dtype=bool)
    in_market = np.zeros(paths)
    committed_sum = np.zeros(paths)
    committed_peak = np.zeros(paths)
    detail_rows: List[Tuple[int, float, float, float]] = []
    curve_equity = np.zeros(len(hours)) if detail else None
    status = ["ended"] * n if detail else []
    increments = np.array([float(costs.base_increment.get(c) or 0.0) for c in coins])
    exited = np.full((paths, len(coins)), -1, dtype=np.int64)  # the last exit fill
    dust = np.zeros((paths, len(coins)))  # unsellable remainders, in coins
    skipped_cool = np.zeros(paths, dtype=np.int64)
    keys = 1 if (cooldown is not None and cooldown.global_) else len(coins)
    last_exit = np.full((paths, max(keys, 1)), np.iinfo(np.int64).min // 2, np.int64)
    last_loss = np.zeros((paths, max(keys, 1)), dtype=bool)
    halt_qty = np.zeros((paths, len(coins)))
    halt_value = np.zeros(paths)
    halt_low = np.zeros(paths)
    in_mdd = np.zeros(paths)  # within the bar (with ``lows``)
    in_mdd_usd = np.zeros(paths)
    in_halt_s = np.full(paths, -1, dtype=np.int64)

    # events: (time, 0 = exit, 1 = entry, opportunity)
    events = sorted(
        [(o.exit_s, 0, i) for i, o in enumerate(opps)]
        + [(o.entry_s, 1, i) for i, o in enumerate(opps)]
    )
    ev = 0
    last_close = np.full(len(coins), np.nan)

    def equity_now() -> np.ndarray:
        value = np.nan_to_num((qty + dust) * last_close[None, :], nan=0.0)
        return cash + value.sum(axis=1)

    for h, t in enumerate(hours.tolist()):
        if len(coins):
            row = marks[h]
            last_close = np.where(np.isfinite(row), row, last_close)
        if low_marks is not None:
            # the positions held through the interval (before this mark's fills), each
            # at its coin's lowest price in it, from the peak at the previous mark
            worst = np.fmin(low_marks[h], last_close)
            low_value = cash + np.nan_to_num(
                (qty + dust) * worst[None, :], nan=0.0
            ).sum(axis=1)
            low_fall = np.where(peak > 0, (peak - low_value) / peak, 0.0)
            low_fall_usd = peak - low_value
        while ev < len(events) and events[ev][0] <= t:
            when, kind, i = events[ev]
            ev += 1
            o = opps[i]
            j = col[o.coin]
            if kind == 0:  # an exit: the paths holding this opportunity's trade
                mine = (holding[:, j] == i) & alive
                if mine.any():
                    sold = qty[mine, j]
                    if increments[j] > 0:  # a sell is sized in whole increments
                        sold = np.floor(sold / increments[j] + 1e-9) * increments[j]
                        dust[mine, j] += qty[mine, j] - sold
                    proceeds = sold * o.exit_price * (1.0 - e) * (1.0 - f)
                    gain = proceeds - spent[mine, j]
                    cash[mine] += proceeds
                    net[mine] += gain
                    days = spent[mine, j] * (o.exit_s - o.entry_s) / DAY_S
                    held[mine] += days
                    trades[mine] += 1
                    if detail and mine[0]:
                        detail_rows.append(
                            (i, float(spent[0, j]), float(gain[0]), float(days[0]))
                        )
                    qty[mine, j] = 0.0
                    spent[mine, j] = 0.0
                    holding[mine, j] = -1
                    exited[mine, j] = o.exit_s
                    if cooldown is not None:
                        k = 0 if cooldown.global_ else j
                        last_exit[mine, k] = o.exit_s
                        last_loss[mine, k] = o.exit_price * (1.0 - e) < (
                            o.entry_price * (1.0 + e)
                        )
                continue
            # an entry: flat when it was decided (not exiting at its own fill)
            flat = (holding[:, j] == -1) & alive & (exited[:, j] != o.entry_s)
            if detail and alive[0] and not flat[0]:
                status[i] = "not_flat"
            if cooldown is not None and flat.any():
                k = 0 if cooldown.global_ else j
                decided = o.entry_s - cooldown.bar_s  # the decision bar's open
                elapsed = (decided - last_exit[:, k]) // cooldown.bar_s
                need = np.where(
                    last_loss[:, k],
                    max(cooldown.bars_after_exit, cooldown.bars_after_loss),
                    cooldown.bars_after_exit,
                )
                cooling = flat & (elapsed < need)
                skipped_cool += cooling
                if detail and cooling[0]:
                    status[i] = "cooldown"
                flat &= ~cooling
            if not flat.any():
                continue
            value = equity_now()
            if size_fraction is not None:
                amount = cash * float(size_fraction)
            else:
                amount = np.maximum(value, 0.0) * account.start_pct / 100.0
                floor = floors[o.coin]
                if floor:
                    amount = np.maximum(amount, floor)
                budget = np.maximum(value, 0.0) * account.max_coin_pct / 100.0
                allowed = np.maximum(budget, floor or 0.0)
                amount = np.where(amount > allowed + 0.005, 0.0, amount)
            no_cash = flat & (amount > cash + 1e-9)
            skipped_cash += no_cash
            veto_here = flat & ~no_cash & veto[:, i]
            vetoed += veto_here
            scaled = amount * scale[:, i]
            floor = floors[o.coin]
            below = (
                flat & ~no_cash & ~veto_here & (scale[:, i] < 1.0) & (scaled < floor)
                if (floor and size_fraction is None)
                else np.zeros(paths, dtype=bool)
            )
            skipped_min += below
            go = flat & ~no_cash & ~veto_here & ~below & (scaled > 0)
            if detail and flat[0]:
                status[i] = (
                    "no_cash"
                    if no_cash[0]
                    else (
                        "vetoed"
                        if veto_here[0]
                        else (
                            "below_minimum"
                            if below[0]
                            else "taken" if go[0] else "no_cash"
                        )
                    )
                )
            if go.any():
                spend = scaled[go]
                qty[go, j] = spend * (1.0 - f) / (o.entry_price * (1.0 + e))
                spent[go, j] = spend
                cash[go] -= spend
                holding[go, j] = i
        # mark the hour
        value = equity_now()
        committed = spent.sum(axis=1)
        live = alive.copy()
        in_market += live & (committed > 0)
        share = np.where(value > 0, committed / np.where(value > 0, value, 1.0), 0.0)
        committed_sum += np.where(live, share, 0.0)
        committed_peak = np.maximum(committed_peak, np.where(live, share, 0.0))
        peak = np.where(live, np.maximum(peak, value), peak)
        fall = np.where(peak > 0, (peak - value) / peak, 0.0)
        fall_usd = peak - value
        mdd = np.where(live, np.maximum(mdd, fall), mdd)
        mdd_usd = np.where(live, np.maximum(mdd_usd, fall_usd), mdd_usd)
        if low_marks is not None:  # reported only: nothing below depends on it
            worst_fall = np.maximum(fall, low_fall)
            in_mdd = np.where(live, np.maximum(in_mdd, worst_fall), in_mdd)
            in_mdd_usd = np.where(
                live,
                np.maximum(in_mdd_usd, np.maximum(fall_usd, low_fall_usd)),
                in_mdd_usd,
            )
            in_halt_s[
                live & (in_halt_s < 0) & (worst_fall >= account.halt_pct / 100.0)
            ] = t
        first_halt = live & (halt_s < 0) & (fall >= account.halt_pct / 100.0)
        halt_s[first_halt] = t
        if first_halt.any():  # what was open, and what it was worth, at the halt
            halt_qty[first_halt] = qty[first_halt]
            marks_now = np.nan_to_num(last_close, nan=0.0)
            halt_value[first_halt] = (halt_qty[first_halt] * marks_now).sum(axis=1)
            halt_low[first_halt] = halt_value[first_halt]
        watching = (halt_s >= 0) & (t - halt_s <= HALT_WATCH_S)
        if watching.any():
            worth = (halt_qty[watching] * np.nan_to_num(last_close, nan=0.0)).sum(1)
            halt_low[watching] = np.minimum(halt_low[watching], worth)
        if detail:
            curve_equity[h] = value[0]
        if halt_ends and first_halt.any():
            # the path ends here: open positions are marked, then frozen
            for jj in range(len(coins)):
                mine = first_halt & (holding[:, jj] >= 0)
                if not mine.any():
                    continue
                mark = last_close[jj] if np.isfinite(last_close[jj]) else 0.0
                proceeds = qty[mine, jj] * mark * (1.0 - e) * (1.0 - f)
                gain = proceeds - spent[mine, jj]
                k = holding[mine, jj]
                entry = np.array([opps[x].entry_s for x in k.tolist()])
                cash[mine] += proceeds
                net[mine] += gain
                held[mine] += spent[mine, jj] * (t - entry) / DAY_S
                trades[mine] += 1
                qty[mine, jj] = 0.0
                spent[mine, jj] = 0.0
                holding[mine, jj] = -1
            alive &= ~first_halt

    count = max(len(hours), 1)
    final = equity_now()
    return Paths(
        net=net,
        capital_days=held,
        trades=trades,
        skipped_cash=skipped_cash,
        skipped_minimum=skipped_min,
        vetoed=vetoed,
        max_drawdown=mdd,
        max_drawdown_usd=mdd_usd,
        halt_s=halt_s,
        final_equity=final,
        time_in_market=in_market / count,
        mean_committed=committed_sum / count,
        peak_committed=committed_peak,
        start=float(account.start),
        detail=detail_rows,
        curve=(hours, curve_equity) if detail else None,
        status=status,
        skipped_cooldown=skipped_cool,
        dust_usd=(
            np.nan_to_num(dust * last_close[None, :], nan=0.0).sum(axis=1)
            if len(coins)
            else np.zeros(paths)
        ),
        halt_exposure=halt_value,
        halt_further_loss=np.maximum(halt_value - halt_low, 0.0),
        intrabar_max_drawdown=in_mdd if intrabar else None,
        intrabar_max_drawdown_usd=in_mdd_usd if intrabar else None,
        intrabar_halt_s=in_halt_s if intrabar else None,
    )
