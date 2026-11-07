"""
Simulated no-skill data for FDS-SIG-001 section 16 item 2: rules that carry no
information must not pass, at or below 5% per family and alpha/F per test, within Monte
Carlo error.

Each scenario makes one row of eligible pairs whose calls are independent of the
outcomes given the regimes (no skill), in the forms section 16 item 2 lists:

* ``random``: seeded random calls, independent returns;
* ``near_constant``: "always up" with seeded 10% flips, at an up share above and below
  50%, exercising the best-constant comparator;
* ``persistent``: calls in runs of 100-200 bars over regime-drifting returns (month-long
  regimes in the up share, +-4 points, and in the mean return);
* ``drift``: calls drawn with a probability that drifts slowly (a cycle of two weeks to a
  month, random phase; or a fixed ``period_days``, such as exactly a month, the cycle
  the Bartlett window cannot see) by +-0.15 or +-0.30 around 0.5, over regime-drifting
  returns: a
  one-sided (up-only) candidate for the one-sided hit test, a two-sided one for the
  two-sided magnitude test.

``false_pass_rates`` runs the full test of section 7.4 (the exact, block bootstrap and
batch-means p-values, the largest entering Holm) on ``trials`` rows, in ``runs``
independent runs (the owner, 2026-11-06: every simulation locally, ten times over), and
reports per-test and per-family false-pass rates. A family is ``F`` independent rows'
tests; the family false-pass rate is the share of families with any Holm survivor.

**A whole round** (``simulate_round``, ``round_false_passes``; the PR #228 review,
finding 4). The scenarios above are single rows, and their families are independent
rows; a round's family is not. ``simulate_round`` makes a round's market: BTC and the
other coins' hourly OHLCV over the window, the 4h bars built from them by the candle
layer's own ``build_candles``, and the round's family from them as the audit makes it
(``registration.family_rows``, ``pairs.row_pairs``, SIG-A and SIG-B as registered):
with ten coins, 38 rows and F = 76. The rows are dependent as a real round's are:

* **between coins:** one market factor (BTC's own shock) in every coin, at a correlation
  of 0.6 to 0.9, so the nine SIG-B rows of a timeframe share their calls and have
  correlated outcomes;
* **between timeframes:** the 4h bars are the 1h bars, aggregated;
* **between statistics:** the hit rate and the magnitude of a row are the same pairs;
* **in time:** volatility that clusters (a GARCH(1,1) on the factor), month-long
  volatility regimes, a daily volatility cycle, fat-tailed shocks (Student t, 4 degrees
  of freedom), and volume that persists and rises with the absolute return; and market
  outages that leave gaps in every coin at once.

No skill: each bar's return is a constant drift (per coin, an up share of about 48 to
52%) plus a shock independent of every earlier bar, so no rule reading closed bars can
beat the best constant except by chance. A drift that changes within the window is
left out on purpose: a rule that follows recent bars then has real skill over the
best constant, and its passes would not be false (the single-row scenarios cover
calls independent of regime-drifting returns). ``lead`` adds real skill (a coin's
return following BTC's previous return), for checking that a pass is still found.

``screened_row`` is ``engine.evaluate_row`` without the bootstrap where the bootstrap
cannot change any decision: the p-value entering Holm is the largest of the exact,
bootstrap and batch-means p-values, so when the exact and batch-means p-values of both
directions already exceed the family error, neither direction can survive Holm at it
(an adjusted p-value is never below the p-value), and every other member's adjusted
p-value at or below the family error is the same (Holm's step-down never reaches past
it); the bootstrap is then skipped and the two lower bounds stand in. Otherwise the row
is ``engine.evaluate_row`` exactly, with the same seeds. The audit itself never skips.
"""

from __future__ import annotations

import math
from dataclasses import replace
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from signal_audit import stats as st

MONTH_1H = 720


def _regimes(rng, E: int, length: int, size: float) -> np.ndarray:
    k = -(-E // length)
    return np.repeat(rng.uniform(-size, size, k), length)[:E]


def scenario(name: str, rng: np.random.Generator, E: int, **kw) -> st.Pairs:
    tf = kw.get("timeframe", "1h")
    if name == "random":
        calls = rng.choice([st.UP, st.DOWN], size=E)
        up = (rng.random(E) < 0.5).astype(np.int8)
        ret = np.where(up == 1, 1, -1) * rng.uniform(0.0005, 0.01, E)
        return st.Pairs(calls.astype(np.int8), up, ret, st.TWO_SIDED, tf)
    if name == "near_constant":
        share = kw["up_share"]
        calls = np.where(rng.random(E) < 0.10, st.DOWN, st.UP)
        up = (rng.random(E) < share).astype(np.int8)
        ret = np.where(up == 1, 1, -1) * rng.uniform(0.0005, 0.01, E)
        return st.Pairs(calls.astype(np.int8), up, ret, st.TWO_SIDED, tf)
    regime = _regimes(rng, E, MONTH_1H, 0.04)
    drift_ret = _regimes(rng, E, MONTH_1H, 0.002)
    up = (rng.random(E) < 0.5 + regime).astype(np.int8)
    ret = np.where(up == 1, 1, -1) * rng.uniform(0.0005, 0.01, E) + drift_ret
    up = (ret > 0).astype(np.int8)
    if name == "persistent":
        calls = np.empty(E, dtype=np.int8)
        i = 0
        while i < E:
            n = int(rng.integers(100, 201))
            calls[i : i + n] = rng.choice([st.UP, st.DOWN])
            i += n
        return st.Pairs(calls, up, ret, st.TWO_SIDED, tf)
    if name == "drift":
        amp = kw["amplitude"]
        if kw.get("period_days"):
            period = float(kw["period_days"]) * 24  # a fixed cycle (the worst case)
        else:
            period = rng.uniform(14 * 24, 30 * 24)
        phase = rng.uniform(0, 2 * math.pi)
        prob = 0.5 + amp * np.sin(2 * math.pi * np.arange(E) / period + phase)
        draw = rng.random(E) < prob
        if kw["kind"] == st.UP_ONLY:
            calls = np.where(draw, st.UP, st.ABSTAIN).astype(np.int8)
            return st.Pairs(calls, up, ret, st.UP_ONLY, tf)
        calls = np.where(draw, st.UP, st.DOWN).astype(np.int8)
        return st.Pairs(calls, up, ret, st.TWO_SIDED, tf)
    raise ValueError(name)


def false_pass_rates(
    name: str,
    statistic: str,
    trials: int,
    runs: int,
    family_size: int,
    E: int,
    seed: int,
    draws: Optional[int] = None,
    **kw,
) -> Dict[str, Any]:
    """Per-test and per-family false-pass rates of ``statistic`` on scenario ``name``.

    A test "passes" when it is assessable, its p-value entering Holm is at most
    alpha_1 = 5% / F and it meets its extra condition (a pass at Holm's first step,
    the strictest; per-test rate to compare with alpha / F). Families group ``F``
    consecutive trials and pass when any member survives Holm and meets its extra
    condition. NOT ASSESSABLE trials count as not passing, and are counted."""
    alpha1 = st.first_holm_alpha(family_size)
    B = draws or st.min_bootstrap_draws(family_size)
    out_runs = []
    for r in range(runs):
        rng = np.random.default_rng(int(seed) + r)
        passes = 0
        assessable = 0
        family_hits = 0
        families = 0
        member_p: List[float] = []
        member_ok: List[bool] = []
        for t in range(trials):
            p = scenario(name, rng, E, **kw)
            blocks = st.block_length(p)
            res = st.evaluate_statistic(
                p, statistic, blocks, B, rng, np.random.default_rng(rng.integers(2**63))
            )
            ok = res.assessable and res.extra_met
            assessable += res.assessable
            passes += int(ok and res.p_holm <= alpha1)
            member_p.append(res.p_holm)
            member_ok.append(ok)
            if len(member_p) == family_size:
                adj = st.holm_adjusted(member_p)
                families += 1
                family_hits += int(any(a <= 0.05 and o for a, o in zip(adj, member_ok)))
                member_p, member_ok = [], []
        out_runs.append(
            {
                "trials": trials,
                "assessable": assessable,
                "per_test_passes": passes,
                "per_test_rate": passes / trials,
                "families": families,
                "family_passes": family_hits,
                "family_rate": family_hits / families if families else None,
            }
        )
    total = sum(x["trials"] for x in out_runs)
    total_pass = sum(x["per_test_passes"] for x in out_runs)
    total_fam = sum(x["families"] for x in out_runs)
    fam_pass = sum(x["family_passes"] for x in out_runs)
    return {
        "scenario": name,
        "statistic": statistic,
        "params": kw,
        "E": E,
        "family_size": family_size,
        "alpha_1": alpha1,
        "bootstrap_draws": B,
        "runs": out_runs,
        "per_test_rate": total_pass / total,
        "per_test_mc_se": math.sqrt(alpha1 * (1 - alpha1) / total),
        "family_rate": fam_pass / total_fam if total_fam else None,
        "family_mc_se": math.sqrt(0.05 * 0.95 / total_fam) if total_fam else None,
        "seeds": [int(seed) + r for r in range(runs)],
    }


# --- a whole round (module docstring) ----------------------------------------------------

HOUR_S = 3600
ROUND_START_S = 1_767_225_600  # 2026-01-01T00:00:00Z: any fixed date will do


def _student_t(rng: np.random.Generator, df: float, size) -> np.ndarray:
    """Student t shocks scaled to unit variance."""
    return rng.standard_t(df, size) / math.sqrt(df / (df - 2.0))


def simulate_round(
    rng: np.random.Generator,
    coins: int = 10,
    days: int = 270,
    lead: Optional[Dict[int, float]] = None,
    timeframes: Sequence[str] = ("1h", "4h"),
):
    """A round's market with no skill in it (module docstring): returns ``(bars,
    names, start_s, end_s)``, ``bars`` keyed by (coin, timeframe) as the audit reads
    them. Coin 0 is BTC. ``lead`` maps a coin's number to the share of BTC's previous
    hourly shock added to its return (real skill for SIG-B on that coin)."""
    from market_data.resample import build_candles
    from signal_audit.candidates import Bars

    warm_days = 3
    T = (days + warm_days) * 24
    start_s = ROUND_START_S + warm_days * 86400
    end_s = start_s + days * 86400
    open_s = ROUND_START_S + HOUR_S * np.arange(T, dtype=np.int64)
    # the market's volatility: a GARCH(1,1) on its shocks, month-long regimes and a
    # daily cycle, around 0.6% an hour
    z = _student_t(rng, 4.0, T)
    h = np.empty(T)
    h[0] = 1.0
    a, b = 0.08, 0.90
    for t in range(1, T):
        h[t] = (1.0 - a - b) + a * z[t - 1] ** 2 * h[t - 1] + b * h[t - 1]
    months = np.repeat(rng.normal(0.0, 0.3, T // 720 + 1), 720)[:T]
    hour = (open_s // HOUR_S) % 24
    sigma = (
        0.006
        * np.sqrt(h)
        * np.exp(months)
        * (1.0 + 0.3 * np.sin(2 * np.pi * hour / 24))
    )
    # outages: a few hours missing in every coin at once
    present = np.ones(T, dtype=bool)
    for _ in range(int(rng.integers(2, 6))):
        at = int(rng.integers(warm_days * 24, T - 3))
        present[at : at + int(rng.integers(1, 4))] = False
    names = ["BTC"] + [f"C{i:02d}" for i in range(1, coins)]
    lead = lead or {}
    out = {}
    for i, name in enumerate(names):
        if i == 0:
            rho, scale = 1.0, 1.0
        else:
            rho, scale = float(rng.uniform(0.6, 0.9)), float(rng.uniform(1.0, 1.8))
        idio = _student_t(rng, 4.0, T)
        coin_months = np.repeat(rng.normal(0.0, 0.15, T // 720 + 1), 720)[:T]
        s = sigma * scale * np.exp(coin_months)
        shock = rho * z + math.sqrt(max(0.0, 1.0 - rho * rho)) * idio
        drift = float(rng.uniform(-0.04, 0.04)) * 0.006 * scale  # up share 48-52%
        r = drift + s * shock
        if lead.get(i):
            r[1:] += float(lead[i]) * sigma[:-1] * z[:-1]
        close = 100.0 * np.exp(np.cumsum(r))
        opened = np.concatenate([[100.0], close[:-1]])
        wick = np.abs(rng.normal(0.0, 0.5, (2, T))) * s
        high = np.maximum(opened, close) * np.exp(wick[0])
        low = np.minimum(opened, close) * np.exp(-wick[1])
        noise = np.empty(T)
        noise[0] = 0.0
        e = rng.normal(0.0, 0.3, T)
        for t in range(1, T):
            noise[t] = 0.9 * noise[t - 1] + e[t]
        volume = np.exp(3.0 + 0.6 * np.log(np.abs(r) / s + 0.05) + noise)
        rows = [
            [int(open_s[t]) * 1000, opened[t], high[t], low[t], close[t], volume[t]]
            for t in range(T)
            if present[t]
        ]
        for tf in timeframes:
            built = rows if tf == "1h" else build_candles(rows, "1h", tf)
            arr = np.array(built, dtype=float)
            out[(name, tf)] = Bars(
                name,
                tf,
                (arr[:, 0] // 1000).astype(np.int64),
                arr[:, 2],
                arr[:, 3],
                arr[:, 4],
                arr[:, 5],
            )
    return out, names, start_s, end_s


def round_rows(bars, names: Sequence[str], start_s: int, end_s: int, timeframes):
    """The round's family as the audit makes it: every registered row's pairs."""
    from signal_audit import round_one
    from signal_audit.pairs import row_pairs
    from signal_audit.registration import family_rows

    cands = round_one.by_key()
    rows = []
    for key in family_rows(round_one.candidates(), names, timeframes, "sim"):
        c = cands[key.candidate]
        inputs = {ic: bars[(ic, key.timeframe)] for ic in c.input_coins}
        rows.append(
            (key, row_pairs(c, bars[(key.coin, key.timeframe)], inputs, start_s, end_s))
        )
    return rows


def _lower_bounds(r: st.StatisticResult):
    """The p-values entering the forward and the opposite Holm, less the bootstrap's:
    lower bounds of both (1 when NOT ASSESSABLE, as there)."""
    if not r.assessable:
        return 1.0, 1.0
    lo_p = st._largest(r.p_exact, r.batch.p_upper if r.batch else None)
    lo_q = st._largest(
        r.q_exact, r.batch_opposite.p_lower if r.batch_opposite else None
    )
    return lo_p, lo_q


def screened_row(index: int, key, data, draws: int, seed: int, screen: float):
    """``engine.evaluate_row``, with a statistic's bootstrap skipped where it cannot
    change any decision at family error ``screen`` (module docstring); a statistic not
    skipped is evaluated with ``engine.evaluate_row``'s own seeds and streams. Returns
    ``(row, statistics skipped)``."""
    from signal_audit import engine

    p = data.pairs
    blocks = st.block_length(p)
    spare = np.random.default_rng(0)
    results = {}
    skipped = 0
    for s in st.STATISTICS:
        pre = st.evaluate_statistic(p, s, blocks, 1, spare, spare)
        lo_p, lo_q = _lower_bounds(pre)
        if min(lo_p, lo_q) > screen:
            results[s] = replace(
                pre,
                bootstrap=None,
                bootstrap_opposite=None,
                se_bootstrap=None,
                p_holm=lo_p,
                q_holm=lo_q,
            )
            skipped += 1
        elif s == st.HIT:
            results[s] = st.evaluate_statistic(
                p,
                s,
                blocks,
                draws,
                engine._rng(seed, index, engine.HIT_STREAM),
                engine._rng(seed, index, engine.WORSE_STREAM),
            )
        else:
            results[s] = st.evaluate_statistic(
                p, s, blocks, draws, engine._rng(seed, index, engine.MAGNITUDE_STREAM)
            )
    return engine.Row(key, p.kind, data, st.counts(p), blocks, results), skipped


def round_false_passes(
    rounds: int,
    runs: int,
    seed: int,
    coins: int = 10,
    days: int = 270,
    draws: Optional[int] = None,
    timeframes: Sequence[str] = ("1h", "4h"),
    screen: float = st.FAMILY_ERROR,
    lead: Optional[Dict[int, float]] = None,
    run_numbers: Optional[Sequence[int]] = None,
) -> Dict[str, Any]:
    """False PASS and WORSE verdicts over simulated rounds (module docstring), in
    ``runs`` independent runs of ``rounds`` rounds; run r is seeded ``seed + r``. Per
    round: any PASS (the family false-pass rate, nominal 5%) and any WORSE; per test:
    the share of (row, statistic) members that are assessable, meet their extra
    condition and have a p-value entering Holm at most alpha_1 = 5% / F (nominal
    alpha_1), and the same for each component p-value and the opposite direction."""
    from signal_audit import engine

    out_runs = []
    F = None
    for r in run_numbers if run_numbers is not None else range(runs):
        rng = np.random.default_rng(int(seed) + r)
        tally = {
            "rounds": 0,
            "rounds_with_pass": 0,
            "rounds_with_worse": 0,
            "tests": 0,
            "assessable": 0,
            "per_test_passes": 0,
            "per_test_worse": 0,
            "exact_below_alpha1": 0,
            "batch_below_alpha1": 0,
            "statistics_skipped": 0,
            "rows": 0,
            "pass_rows": [],
            "worse_rows": [],
            "by_row_type": {},
        }
        for j in range(rounds):
            bars, names, start_s, end_s = simulate_round(
                rng, coins, days, lead, timeframes
            )
            rows_data = round_rows(bars, names, start_s, end_s, timeframes)
            F = 2 * len(rows_data)
            B = draws or st.min_bootstrap_draws(F)
            alpha1 = st.first_holm_alpha(F)
            boot_seed = int(rng.integers(2**63))
            rows = []
            for i, (k, d) in enumerate(rows_data):
                row, skipped = screened_row(i, k, d, B, boot_seed, screen)
                rows.append(row)
                tally["statistics_skipped"] += skipped
            engine.apply_holm(rows)
            verdicts = []
            for row in rows:
                row.verdict, row.passing = engine.verdict_of(row)
                verdicts.append(row.verdict)
                for s in st.STATISTICS:
                    res = row.results[s]
                    tally["tests"] += 1
                    tally["assessable"] += int(res.assessable)
                    kind = tally["by_row_type"].setdefault(
                        f"{row.key.candidate} {row.key.timeframe} {s}",
                        {"tests": 0, "assessable": 0, "blocks_L": [], "blocks_K": []},
                    )
                    kind["tests"] += 1
                    kind["assessable"] += int(res.assessable)
                    if len(kind["blocks_L"]) < 50:
                        kind["blocks_L"].append(row.blocks.L)
                        kind["blocks_K"].append(row.blocks.K)
                    if not res.assessable:
                        continue
                    tally["per_test_passes"] += int(
                        res.extra_met and res.p_holm <= alpha1
                    )
                    tally["per_test_worse"] += int(res.q_holm <= alpha1)
                    tally["exact_below_alpha1"] += int(
                        res.p_exact is not None and res.p_exact <= alpha1
                    )
                    tally["batch_below_alpha1"] += int(
                        res.batch is not None and res.batch.p_upper <= alpha1
                    )
                if row.verdict == engine.PASS:
                    tally["pass_rows"].append(f"round {j}: {row.key.text()}")
                if row.verdict == engine.WORSE:
                    tally["worse_rows"].append(f"round {j}: {row.key.text()}")
            tally["rows"] += len(rows)
            tally["rounds"] += 1
            tally["rounds_with_pass"] += int(engine.PASS in verdicts)
            tally["rounds_with_worse"] += int(engine.WORSE in verdicts)
        tally["seed"] = int(seed) + r
        tally["family_size"] = F
        out_runs.append(tally)
    return combine_round_runs(
        out_runs,
        {
            "bootstrap_draws": draws or (st.min_bootstrap_draws(F) if F else None),
            "coins": coins,
            "days": days,
            "timeframes": list(timeframes),
            "screen": screen,
            "lead": lead or {},
        },
    )


def combine_round_runs(out_runs: Sequence[Dict[str, Any]], meta: Dict[str, Any]):
    """The pooled figures of ``round_false_passes``'s runs (run separately, say in
    parallel, and joined here), with each run's own."""
    out_runs = sorted(out_runs, key=lambda x: x["seed"])
    F = out_runs[0]["family_size"] if out_runs else None
    total = lambda k: sum(x[k] for x in out_runs)  # noqa: E731
    n_rounds = total("rounds")
    n_assess = total("assessable")
    alpha1 = st.first_holm_alpha(F) if F else None
    by_type: Dict[str, Dict[str, Any]] = {}
    for x in out_runs:
        for name, v in x["by_row_type"].items():
            t = by_type.setdefault(
                name, {"tests": 0, "assessable": 0, "L": [], "K": []}
            )
            t["tests"] += v["tests"]
            t["assessable"] += v["assessable"]
            t["L"] += v["blocks_L"]
            t["K"] += v["blocks_K"]
    for t in by_type.values():
        t["assessable_share"] = t["assessable"] / t["tests"] if t["tests"] else None
        L, K = t.pop("L"), t.pop("K")
        t["median_L"] = float(np.median(L)) if L else None
        t["median_K"] = float(np.median(K)) if K else None
    for x in out_runs:
        x["family_rate"] = x["rounds_with_pass"] / x["rounds"] if x["rounds"] else None
        x["family_rate_worse"] = (
            x["rounds_with_worse"] / x["rounds"] if x["rounds"] else None
        )
        x["per_test_rate"] = (
            x["per_test_passes"] / x["assessable"] if x["assessable"] else None
        )
    return {
        **meta,
        "family_size": F,
        "alpha_1": alpha1,
        "runs": out_runs,
        "by_row_type": dict(sorted(by_type.items())),
        "rounds": n_rounds,
        "family_rate": total("rounds_with_pass") / n_rounds if n_rounds else None,
        "family_rate_worse": (
            total("rounds_with_worse") / n_rounds if n_rounds else None
        ),
        "family_mc_se": math.sqrt(0.05 * 0.95 / n_rounds) if n_rounds else None,
        "tests": total("tests"),
        "assessable": n_assess,
        "per_test_rate": total("per_test_passes") / n_assess if n_assess else None,
        "per_test_rate_worse": total("per_test_worse") / n_assess if n_assess else None,
        "per_test_rate_exact": (
            total("exact_below_alpha1") / n_assess if n_assess else None
        ),
        "per_test_rate_batch": (
            total("batch_below_alpha1") / n_assess if n_assess else None
        ),
        "per_test_mc_se": (
            math.sqrt(alpha1 * (1 - alpha1) / n_assess) if n_assess and alpha1 else None
        ),
        "seeds": [x["seed"] for x in out_runs],
    }
