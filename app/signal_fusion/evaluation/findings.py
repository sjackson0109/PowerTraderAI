"""
FDS-SIG-004's findings and their verdicts (sections 5.5, 6.1 to 6.3 and 6.7).

* **F1, forecast value** (``f1``): the paired log-loss difference between the price-only
  and the price-plus-volume model on the same rows, with the placebo and stability
  conditions.
* **F2, relative trading value** (``f2``): the paired difference in return per
  capital-day between the two filters' paths, with the R3 condition.
* **F3, economic viability** (``f3``): the five absolute requirements, with the capital
  use and drawdown report.
* **Q2, calibration** (``calibration``): skill (BSS > 0), calibration within tolerance (the
  90% intervals of a and b inside their bands) and the sample floor, with three outcomes.
* **Q3, the volatility shrink** (``shrink``): its drawdown against R3s, and
  non-inferiority of its return per capital-day.

Each primary test returns its p-value; the Holm family is applied by the caller over the
family's primary tests (``holm``). A condition is tested at 5%. Only an F3 pass may use
the words "profitable" or "makes money" (``check_wording``).
"""

from __future__ import annotations

from statistics import NormalDist
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from signal_fusion.evaluation import baselines as bl
from signal_fusion.evaluation import bootstrap as bs
from signal_fusion.evaluation import scoring as sc
from signal_fusion.evaluation.replay import DAY_S, Paths

CONDITION_ALPHA = 0.05
HOLM_ALPHA = 0.05
POWER = 0.8

# F3's requirements (D18)
F3_MIN_TRADES = 100
F3_MIN_HALF = 30
F3_PROFIT = "a profit per capital-day"  # f3_failed's name for the bootstrap requirement

# Q2's tolerances (D16)
INTERCEPT_BAND = (-0.10, 0.10)
SLOPE_BAND = (0.80, 1.20)
MIN_EVENTS = 200
MIN_NON_EVENTS = 200

# Q3's non-inferiority margin (D12): 0.01 percentage points per capital-day
SHRINK_MARGIN = 0.0001

PROFIT_WORDS = ("profitable", "makes money")


def holm(ps: Sequence[float], alpha: float = HOLM_ALPHA) -> List[bool]:
    from model_lab import stats

    return stats.holm(list(ps), alpha)


def smallest_detectable(draws, k: int, alpha: float = HOLM_ALPHA, power: float = POWER):
    """(z at 1 - alpha/K, plus z at power) x the draws' standard deviation."""
    d = np.asarray(draws, dtype=float).ravel()
    d = d[np.isfinite(d)]
    if len(d) < 2:
        return float("nan")
    z = NormalDist().inv_cdf(1 - alpha / max(1, k)) + NormalDist().inv_cdf(power)
    return float(z * np.std(d))


def _halves(times_s: np.ndarray) -> np.ndarray:
    """0 or 1 for each time: the half of the scored days it falls in, split at the middle
    day."""
    day = np.asarray(times_s, dtype=np.int64) // DAY_S
    first, last = int(day.min()), int(day.max())
    middle = first + (last - first + 1) // 2
    return (day >= middle).astype(int)


# --- F1 --------------------------------------------------------------------------------------


def f1(
    y,
    p_price,
    p_volume,
    p_placebos: Sequence[Any],
    times_s,
    seed: int,
    k: int,
    block: int = bs.BLOCK_DAYS,
) -> Dict[str, Any]:
    """F1 on rows (outcomes ``y`` of T1, each model's probability, the rows' hours)."""
    y = np.asarray(y, dtype=float)
    ll_p = sc.log_loss_rows(y, p_price)
    ll_v = sc.log_loss_rows(y, p_volume)
    ll_placebo = np.mean([sc.log_loss_rows(y, p) for p in p_placebos], axis=0)
    d = ll_p - ll_v
    e = ll_placebo - ll_v
    ones = np.ones(len(y))
    times_s = np.asarray(times_s, dtype=np.int64)
    sums_d = bs.day_sums(times_s, [d, ones])
    sums_e = bs.day_sums(times_s, [e, ones])
    test = bs.test_statistic(sums_d, bs.mean_of(0, 1), seed, block)
    placebo = bs.test_statistic(sums_e, bs.mean_of(0, 1), seed, block)
    boot = bs.Bootstrap(sums_d.days, seed, block)
    edge = smallest_detectable(boot.draws(sums_d, bs.mean_of(0, 1)), k)
    half = _halves(times_s)
    halves = [
        float(d[half == h].mean()) if (half == h).any() else float("nan")
        for h in (0, 1)
    ]
    per_variant = [float(np.mean(ll_p - sc.log_loss_rows(y, p))) for p in p_placebos]
    return {
        "rows": int(len(y)),
        "base_rate": float(y.mean()) if len(y) else float("nan"),
        "log_loss": {"price": float(ll_p.mean()), "volume": float(ll_v.mean())},
        "test": test,
        "placebo": placebo,
        "halves": halves,
        "per_placebo": per_variant,
        "smallest_detectable": edge,
        "conditions": {
            "placebo": placebo["p"] <= CONDITION_ALPHA,
            "stability": bool(all(h > 0 for h in halves)),
        },
    }


def f1_passes(result: Dict[str, Any], holm_pass: bool) -> bool:
    return bool(holm_pass and all(result["conditions"].values()))


# --- F2 --------------------------------------------------------------------------------------


def path_day_sums(
    trades: Sequence[Sequence[float]], first_s: int, last_s: int
) -> bs.DaySums:
    """Per-day (net, capital-days) of a path's trades, each on its entry's day; trades are
    (entry time, net, capital-days)."""
    t = [row[0] for row in trades] or [first_s]
    net = [row[1] for row in trades] or [0.0]
    days = [row[2] for row in trades] or [0.0]
    return bs.day_sums(t, [net, days], first_s, last_s)


def paired_paths(
    a: Sequence[Sequence[float]],
    b: Sequence[Sequence[float]],
    first_s: int,
    last_s: int,
    seed: int,
    block: int = bs.BLOCK_DAYS,
) -> Dict[str, Any]:
    """RPCD(a) - RPCD(b), by the paired block bootstrap over entry days."""
    sa = path_day_sums(a, first_s, last_s)
    sb = path_day_sums(b, first_s, last_s)
    both = bs.DaySums(sa.first_day, np.hstack([sa.sums, sb.sums]))
    return bs.test_statistic(both, bs.ratio_difference(0, 1, 2, 3), seed, block)


def f2(
    volume_trades,
    price_trades,
    volume_rpcd: float,
    r3_rpcd_draws,
    first_s: int,
    last_s: int,
    seed: int,
    block: int = bs.BLOCK_DAYS,
) -> Dict[str, Any]:
    """F2: the paired decision test, and the V filter against R3's draws of RPCD."""
    test = paired_paths(volume_trades, price_trades, first_s, last_s, seed, block)
    p_r3 = bl.upper_p(volume_rpcd, r3_rpcd_draws)
    return {
        "test": test,
        "r3": {"p": p_r3, "median": float(np.median(r3_rpcd_draws))},
        "conditions": {"r3": p_r3 <= CONDITION_ALPHA},
    }


# --- F3 --------------------------------------------------------------------------------------


def drawdown_details(hours: np.ndarray, equity: np.ndarray) -> Dict[str, Any]:
    """The largest fall from a peak: its start, trough and recovery, and the time under
    water."""
    if not len(equity):
        return {}
    peak = np.maximum.accumulate(equity)
    fall = np.where(peak > 0, (peak - equity) / peak, 0.0)
    trough = int(np.argmax(fall))
    start = int(np.argmax(equity[: trough + 1])) if trough else 0
    after = np.nonzero(equity[trough:] >= equity[start])[0]
    recovered = int(trough + after[0]) if len(after) else None
    under = float(np.mean(equity < peak))
    return {
        "max_drawdown": float(fall[trough]),
        "max_drawdown_usd": float(peak[trough] - equity[trough]),
        "start_s": int(hours[start]),
        "trough_s": int(hours[trough]),
        "recovered_s": int(hours[recovered]) if recovered is not None else None,
        "time_under_water": under,
    }


def f3(
    path: Paths,
    entries_s: Sequence[int],
    coins: Sequence[str],
    first_s: int,
    last_s: int,
    seed: int,
    halt_pct: float = 8.0,
    block: int = bs.BLOCK_DAYS,
) -> Dict[str, Any]:
    """F3 for one path (path 0 of a ``replay(..., detail=True)``). ``entries_s`` and
    ``coins`` give each opportunity's entry time and coin.

    The drawdown requirement is measured at the replay's marks (closes), as declared.
    When the path has the intrabar figures (a replay given ``lows``), the report shows
    them beside it: the largest drawdown with positions at their lows, when the halt
    level was first reached that way, and whether it stayed below it. They decide
    nothing; without them they are None."""
    rows = path.detail  # (opportunity, amount, net, capital-days)
    t = np.array([entries_s[i] for i, *_ in rows], dtype=np.int64)
    net = np.array([r[2] for r in rows], dtype=float)
    days = np.array([r[3] for r in rows], dtype=float)
    amount = np.array([r[1] for r in rows], dtype=float)
    coin = [coins[i] for i, *_ in rows]
    n = len(rows)
    first_day, last_day = first_s // DAY_S, last_s // DAY_S
    middle = first_day + (last_day - first_day + 1) // 2
    second = (t // DAY_S) >= middle if n else np.zeros(0, dtype=bool)
    halves_n = [int(np.sum(~second)), int(np.sum(second))]
    halves_net = [float(net[~second].sum()), float(net[second].sum())]
    by_coin: Dict[str, float] = {}
    for c, x in zip(coin, net):
        by_coin[c] = by_coin.get(c, 0.0) + float(x)
    best = max(by_coin, key=by_coin.get) if by_coin else None
    without_best = float(sum(v for c, v in by_coin.items() if c != best))
    sums = bs.day_sums(
        t if n else [first_s],
        [net if n else [0.0], days if n else [0.0]],
        first_s,
        last_s,
    )
    test = bs.test_statistic(sums, bs.ratio(0, 1), seed, block)
    total_net = float(net.sum())
    rpcd = total_net / float(days.sum()) if days.sum() > 0 else 0.0
    curve = path.curve
    dd = drawdown_details(curve[0], curve[1]) if curve is not None else {}
    window_days = (last_s - first_s) / DAY_S
    roe = total_net / path.start
    annual = (
        (1.0 + roe) ** (365.0 / window_days) - 1.0
        if window_days > 0 and roe > -1
        else float("nan")
    )
    req = {
        "trades": n >= F3_MIN_TRADES and min(halves_n) >= F3_MIN_HALF,
        "profit": test["p"],  # its pass is decided in the Holm family
        "stable": all(h > 0 for h in halves_net),
        "not_one_coin": without_best > 0,
        "within_halt": float(path.max_drawdown[0]) < halt_pct / 100.0,
    }
    returns = net / amount if n else np.zeros(0)
    low_dd = (
        float(path.intrabar_max_drawdown[0])
        if path.intrabar_max_drawdown is not None
        else None
    )
    low_halt = (
        int(path.intrabar_halt_s[0]) if path.intrabar_halt_s is not None else None
    )
    return {
        "requirements": req,
        "test": test,
        "report": {
            "net_usd": total_net,
            "return_on_equity": roe,
            "annualised": annual,
            "rpcd": rpcd,
            "time_in_market": float(path.time_in_market[0]),
            "mean_committed": float(path.mean_committed[0]),
            "peak_committed": float(path.peak_committed[0]),
            "capital_days": float(days.sum()),
            "trades": n,
            "trades_by_half": halves_n,
            "net_by_half": halves_net,
            "net_by_coin": by_coin,
            "without_best_coin": without_best,
            "win_rate": float(np.mean(net > 0)) if n else float("nan"),
            "mean_return": float(returns.mean()) if n else float("nan"),
            "median_return": float(np.median(returns)) if n else float("nan"),
            "largest_loss_usd": float(net.min()) if n else float("nan"),
            "halt_reached_s": int(path.halt_s[0]),
            "halt_pct": float(halt_pct),
            # within the bar: shown beside requirement 5, never deciding it
            "intrabar_max_drawdown": low_dd,
            "intrabar_halt_reached_s": low_halt,
            "intrabar_within_halt": (
                None if low_dd is None else low_dd < halt_pct / 100.0
            ),
            **dd,
        },
    }


def f3_passes(result: Dict[str, Any], holm_pass: bool) -> bool:
    r = result["requirements"]
    return bool(
        r["trades"]
        and holm_pass
        and r["stable"]
        and r["not_one_coin"]
        and r["within_halt"]
    )


def f3_failed(result: Dict[str, Any], holm_pass: bool) -> Optional[str]:
    r = result["requirements"]
    if not r["trades"]:
        return "too few trades"
    for name, ok in (
        (F3_PROFIT, holm_pass),
        ("a profit in each half", r["stable"]),
        ("a profit without the most profitable coin", r["not_one_coin"]),
        ("a drawdown below the halt level", r["within_halt"]),
    ):
        if not ok:
            return name
    return None


def f3_failures(
    result: Dict[str, Any], holm_pass: bool, halt_pct: Optional[float] = None
) -> List[str]:
    """Every F3 requirement the result did not meet, in ``f3_failed``'s order, each
    worded as a failure with its figures; empty when all are met. ``f3_failed`` names
    only the first, as the condition itself ("a profit in each half"), which read alone
    can sound met. ``halt_pct`` defaults to the level the result was scored with."""
    r = result["requirements"]
    rep = result["report"]
    if halt_pct is None:
        halt_pct = rep.get("halt_pct")
    out: List[str] = []
    if not r["trades"]:
        first, second = rep["trades_by_half"]
        out.append(
            f"failed the requirement for at least {F3_MIN_TRADES} trades and "
            f"{F3_MIN_HALF} in each half ({rep['trades']} trades: {first} and {second})"
        )
    if not holm_pass:
        out.append(
            "failed the requirement that its bootstrap test of return per capital-day "
            f"passes Holm (p = {result['test']['p']:.4f})"
        )
    if not r["stable"]:
        first, second = rep["net_by_half"]
        out.append(
            "failed the requirement for a positive net profit in both evaluation halves "
            f"(first half ${first:+,.2f}, second half ${second:+,.2f})"
        )
    if not r["not_one_coin"]:
        by_coin = rep.get("net_by_coin") or {}
        best = max(by_coin, key=by_coin.get) if by_coin else "the best coin"
        out.append(
            "failed the requirement for a positive net profit without its most "
            f"profitable coin (${rep['without_best_coin']:+,.2f} without {best})"
        )
    if not r["within_halt"]:
        level = f"{halt_pct:g}% " if halt_pct is not None else ""
        out.append(
            f"exceeded the permitted {level}maximum drawdown, reaching "
            f"{rep.get('max_drawdown', float('nan')):.2%}"
        )
    return out


def f3_not_shown(
    result: Dict[str, Any],
    holm_pass: bool,
    halt_pct: Optional[float] = None,
    holm_over: Optional[int] = None,
    subject: str = "It",
) -> str:
    """A failed F3's sentences: "Not shown to be profitable after fees.", then each unmet
    requirement as a failure. When the bootstrap test passed Holm, a sentence says that
    is one of the five requirements, so a small p is never read as the pass."""
    failures = f3_failures(result, holm_pass, halt_pct)
    if not failures:
        raise ValueError("every F3 requirement is met: the result is not a failure")
    text = f"Not shown to be profitable after fees. {subject} " + ", and ".join(
        failures
    )
    text += "."
    if holm_pass:
        over = f" over {holm_over}" if holm_over else ""
        text += (
            f" Its bootstrap test of return per capital-day passed Holm{over} "
            f"(p = {result['test']['p']:.4f}), but that is one of F3's five "
            "requirements, and a pass needs all five."
        )
    return text


# --- Q2 --------------------------------------------------------------------------------------


def calibration(
    y,
    p,
    climatology,
    times_s,
    seed: int,
    k: int,
    block: int = bs.BLOCK_DAYS,
    runs: int = bs.RUNS,
    per_run: int = bs.DRAWS_PER_RUN,
) -> Dict[str, Any]:
    """Skill, calibration within tolerance and the sample floor (section 5.5). The
    intervals of a and b refit both on each draw's rows (``runs`` x ``per_run`` draws).
    """
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    times_s = np.asarray(times_s, dtype=np.int64)
    b_model = sc.brier_rows(y, p)
    b_clim = sc.brier_rows(y, climatology)
    sums = bs.day_sums(times_s, [b_model, b_clim])
    skill = bs.test_statistic(sums, bs.skill(0, 1), seed, block)
    a_hat = sc.calibration_intercept(y, p)
    b_hat = sc.calibration_slope(y, p)[1]
    boot = bs.Bootstrap(sums.days, seed, block, runs, per_run)
    day = times_s // DAY_S - sums.first_day
    a_draws, b_draws = [], []
    for run in range(boot.runs):
        counts = boot.day_counts(run)
        for row in counts:
            w = row[day]
            if w.sum() <= 0:
                continue
            a_draws.append(sc.calibration_intercept(y, p, w))
            b_draws.append(sc.calibration_slope(y, p, w)[1])
    a_int = bs.interval(np.array(a_draws), 0.90)
    b_int = bs.interval(np.array(b_draws), 0.90)
    events = int(np.sum(y == 1))
    non_events = int(np.sum(y == 0))
    enough = events >= MIN_EVENTS and non_events >= MIN_NON_EVENTS
    inside = (
        INTERCEPT_BAND[0] <= a_int[0]
        and a_int[1] <= INTERCEPT_BAND[1]
        and SLOPE_BAND[0] <= b_int[0]
        and b_int[1] <= SLOPE_BAND[1]
    )
    excludes = not (a_int[0] <= 0.0 <= a_int[1]) or not (b_int[0] <= 1.0 <= b_int[1])
    if inside:
        outcome = "calibrated"
    elif excludes:
        outcome = "miscalibrated"
    else:
        outcome = "not_assessable"
    return {
        "skill": skill,
        "skill_edge": smallest_detectable(boot.draws(sums, bs.skill(0, 1)), k),
        "intercept": {
            "value": a_hat,
            "interval_90": a_int,
            "band": list(INTERCEPT_BAND),
        },
        "slope": {"value": b_hat, "interval_90": b_int, "band": list(SLOPE_BAND)},
        "events": events,
        "non_events": non_events,
        "enough": enough,
        "outcome": outcome,
        "summary": sc.summary(y, p, climatology),
    }


def calibration_passes(result: Dict[str, Any], holm_pass: bool) -> bool:
    return bool(holm_pass and result["outcome"] == "calibrated" and result["enough"])


# --- Q3 --------------------------------------------------------------------------------------


def shrink(
    shrunk: Paths,
    unscaled_trades,
    shrunk_trades,
    r3s_drawdowns,
    first_s: int,
    last_s: int,
    seed: int,
    margin: float = SHRINK_MARGIN,
    block: int = bs.BLOCK_DAYS,
) -> Dict[str, Any]:
    """Q3: the shrink's equity-curve drawdown against R3s (lower is better), and
    non-inferiority of its return per capital-day against unscaled."""
    mdd = float(shrunk.max_drawdown[0])
    p = bl.lower_p(mdd, r3s_drawdowns)
    paired = paired_paths(shrunk_trades, unscaled_trades, first_s, last_s, seed, block)
    return {
        "max_drawdown": mdd,
        "p": p,
        "r3s_median": float(np.median(r3s_drawdowns)),
        "non_inferiority": {
            "lower_95": paired["lower_95"],
            "margin": margin,
            "passes": paired["lower_95"] >= -margin,
        },
        "paired": paired,
    }


def shrink_passes(result: Dict[str, Any], holm_pass: bool) -> bool:
    return bool(holm_pass and result["non_inferiority"]["passes"])


# --- verdicts ----------------------------------------------------------------------------------


def check_wording(line: str, f3_line: bool) -> str:
    """Only F3's own lines may use the words "profitable" or "makes money" (section 6.1's
    wording rules): its pass says the result is profitable, and its failure says it is
    "Not shown to be profitable after fees". Every other line never uses them, so a result
    that loses less than its controls is never called profitable."""
    low = line.lower()
    if not f3_line and any(w in low for w in PROFIT_WORDS):
        raise ValueError(f"only an F3 line can say: {line!r}")
    return line


def f1_line(result: Dict[str, Any], passed: bool) -> str:
    t = result["test"]
    if result["rows"] == 0:
        return "Not assessable: no scored rows"
    if passed:
        return check_wording(
            f"Volume improves forecasts over price alone "
            f"(Δ log loss = {t['theta']:+.5f}, n = {result['rows']}, base rate "
            f"{result['base_rate']:.3f})",
            False,
        )
    return check_wording(
        f"No forecast improvement detected (Δ log loss = {t['theta']:+.5f}, smallest "
        f"detectable Δ log loss = {result['smallest_detectable']:.5f}, n = {result['rows']})",
        False,
    )


def f2_line(
    result: Dict[str, Any], passed: bool, path_net: float, trades: int, edge: float
) -> str:
    if trades == 0:
        return "Not assessable: the path made no trades"
    if passed and path_net <= 0:
        return check_wording(
            "Volume reduces losses compared with price alone and with random vetoes. The "
            f"strategy still loses money after fees (net {path_net:+,.2f} over {trades} "
            "trades)",
            False,
        )
    if passed:
        return check_wording(
            "Volume improves results compared with price alone and with random vetoes. "
            "Profitability is shown separately (F3)",
            False,
        )
    return check_wording(
        f"No improvement over price alone detected (smallest detectable difference = "
        f"{edge:+.5f} a capital-day)",
        False,
    )


def f3_line(
    result: Dict[str, Any],
    passed: bool,
    failed: Optional[str],
    holm_pass: Optional[bool] = None,
) -> str:
    """F3's verdict. A failure names every unmet requirement as a failure
    (``f3_not_shown``). Without ``holm_pass`` it follows from ``failed``:
    ``f3_failed`` checks the bootstrap first, so it names it only when it failed."""
    rep = result["report"]
    if not result["requirements"]["trades"]:
        return (
            f"Not assessable: {rep['trades']} trades ({rep['trades_by_half']} by half)"
        )
    if passed:
        return check_wording(
            f"Profitable after fees in the confirmation window: net {rep['net_usd']:+,.2f}, "
            f"return per capital-day {rep['rpcd']:+.4%}, {rep['trades']} trades, maximum "
            f"drawdown {rep.get('max_drawdown', float('nan')):.2%}",
            True,
        )
    if holm_pass is None:
        holm_pass = failed != F3_PROFIT
    return check_wording(f3_not_shown(result, holm_pass), True)


def shrink_line(result: Dict[str, Any], passed: bool) -> str:
    if passed:
        return check_wording(
            f"Reduces drawdown compared with random sizing (maximum drawdown "
            f"{result['max_drawdown']:.2%} against a median of {result['r3s_median']:.2%})",
            False,
        )
    return check_wording(
        "No reduction in drawdown compared with random sizing detected", False
    )
