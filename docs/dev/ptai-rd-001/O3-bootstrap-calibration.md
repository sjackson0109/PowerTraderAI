# O3: calibrating the stationary-bootstrap test

> **Synthetic data only.** No market data or network was used. This sets the default of a library function (`research_stats.resampling.rpcd_test`) that nothing in the app calls yet. Adopting the test for a declared evaluation is still the owner's decision O3.

**Prepared:** 2026-11-12, on `feat/research-stats-calibration`, cut from PR #266 (`c50b670`).
**Why:** PR #266's test rejected slightly too often under dependence (7.4% at AR(0.4) in its first check, nominal 5%). The owner approved adopting a stricter variant.
**Files:** the script `o3/calibrate.py`, its raw output `o3/results.json` (every scenario, variant and run).

## Result

**The new default is variant D: the studentised (bootstrap-t) test with the block length x1.5.** No variant met the 6.0% limit. Under the rule, the lowest worst-case size then wins, and D's was lowest: **6.2%** at nominal 5% (AR(0.4) with Student-t(3) shocks, 750 days). PR #266's method (A) reached 7.5%. D's mean power was 1.6 points lower than A's (77.5% against 79.1%).

Two things limit what that says. D's 6.2% and B's 6.6% are 0.4 points apart, less than one Monte Carlo standard error, so the rule's choice of D over B is not a measured difference. And a test of exactly 5% would show about 6.15% as its worst of 12 cells by chance alone (see Limits), so missing 6.0% by 0.2 points is not evidence of a size problem.

## The rule, as declared before the run

From the owner's brief (2026-11-12), written into the script before it ran:

1. Take each variant's worst pooled null size at nominal 5%, across all null scenarios and both lengths. Keep the variants whose worst is at most 6.0%.
2. Among those, choose the highest pooled power, averaged over the power cells (the three power scenarios at both lengths, equal weights).
3. A tie within 2 points of power goes to the simpler variant: A < C < B < D.
4. If no variant is at most 6.0%, choose the one with the lowest worst-case size, and say plainly that none met 6%.

Step 4 applied.

## What was measured

| Variant | Method | Mean block length |
|---|---|---|
| A | Percentile (PR #266's) | Chosen from the data (Politis and White), x1.0 |
| B | Studentised | x1.0 |
| C | Percentile | x1.5 |
| D | Studentised | x1.5 |

Lengths are still capped at min(3 sqrt(N), N/3) after scaling.

**The studentised method.** t = theta / se. The standard error comes from the linearised ratio z_t = pnl_t - theta x capital_t, through a Bartlett-kernel (Newey-West) long-run variance whose bandwidth is the mean block length. Each resample gets the same formula with its own theta*, and the observed t is compared with the centred t* draws. This is the "naive" block bootstrap of a HAC t statistic (Gonçalves and Vogelsang 2011). It carries the kernel estimate's downward bias into the bootstrap distribution, so the bias is not mistaken for evidence. Götze and Künsch (1996) and Lahiri (2003) give the theory for studentised block bootstraps.

**Scenarios (no edge).** Each was run at N = 750 and 1500 days:

- AR(1) daily results with phi 0, 0.4 and 0.7.
- AR(0.4) with Student-t(3) shocks.
- GARCH(1,1): omega 0.05, alpha 0.1, beta 0.85.
- Marked trades. The price is a martingale random walk (3% daily SD). Long-only trades last 20 to 60 days, with flat gaps of 30 to 120 days and 50 to 150 USD each, marked daily by `daily_marks`. About a third of days hold capital.

**Scenarios (power).** These were also run at both lengths:

- AR(0.4) plus 0.1 a day.
- AR(0.4) plus 0.2 a day. Both edges are in units of the shock SD; the series' own SD is 1.09.
- Marked trades with a drift of 0.004 a day.

**Choosing the drift.** A pilot chose the drift, using variant A only at 750 days and 10 runs x 30 each. It took the grid value closest to 50% power. The grid was too coarse to land on 50%: 0.003 gave 38.0% and 0.004 gave 60.7%. In the main run, with fresh seeds, A's power at 0.004 was 63.3%.

| Drift a day | A's power at 750 days, % (per-run range) |
|---|---|
| 0.001 | 11.7 (3–20) |
| 0.002 | 22.0 (10–30) |
| 0.003 | 38.0 (30–57) |
| 0.004 | 60.7 (47–83) |
| 0.005 | 78.3 (63–93) |

**Replications** (the owner's rule):

- Every cell is 10 seeded runs. Each null cell has 100 replications per run, 1000 in all; each power cell has 30 per run, 300 in all.
- Each test used 999 bootstrap draws.
- In each replication the four variants saw the same data and the same bootstrap seed, so the comparisons between variants are paired.
- The run used 6 worker processes and took 724 seconds.

## Size: rejection rate with no edge, nominal 5%

Pooled % over 1000 replications, with the range across the 10 runs of 100. The pooled Monte Carlo SE is about 0.7 points; a single run's is about 2.2 points, so per-run ranges like 1–11 are expected. Each variant's worst cell is in bold.

| Scenario | N | A | B | C | D |
|---|---:|---:|---:|---:|---:|
| AR(1), phi 0 | 750 | 4.0 (1–8) | 4.1 (1–8) | 3.9 (1–7) | 4.0 (1–7) |
| AR(1), phi 0 | 1500 | 5.0 (2–8) | 5.0 (2–8) | 4.8 (2–9) | 4.8 (2–10) |
| AR(1), phi 0.4 | 750 | 5.9 (4–8) | 4.9 (1–8) | 5.8 (3–9) | 4.7 (2–9) |
| AR(1), phi 0.4 | 1500 | 5.0 (3–8) | 4.7 (2–8) | 4.9 (2–8) | 4.4 (1–7) |
| AR(1), phi 0.7 | 750 | **7.5 (5–11)** | 5.5 (2–10) | **7.3 (4–11)** | 5.8 (3–11) |
| AR(1), phi 0.7 | 1500 | 6.8 (2–11) | 4.7 (1–7) | 6.6 (3–9) | 5.4 (2–7) |
| AR(0.4), t(3) shocks | 750 | 7.1 (3–11) | **6.6 (3–12)** | 6.2 (1–12) | **6.2 (3–11)** |
| AR(0.4), t(3) shocks | 1500 | 5.2 (3–9) | 4.8 (3–9) | 4.9 (3–8) | 4.7 (3–9) |
| GARCH(1,1) | 750 | 4.6 (1–9) | 4.7 (1–8) | 4.4 (2–9) | 4.6 (2–10) |
| GARCH(1,1) | 1500 | 5.1 (3–7) | 5.0 (3–7) | 5.0 (3–7) | 4.9 (3–6) |
| Marked trades | 750 | 4.9 (1–9) | 5.2 (1–10) | 5.5 (1–9) | 5.7 (1–9) |
| Marked trades | 1500 | 4.6 (3–8) | 4.6 (3–8) | 4.6 (3–8) | 4.7 (3–7) |
| **Worst** | | **7.5** | **6.6** | **7.3** | **6.2** |

At 1% and 10% the pattern is the same; the full rates are in `results.json`. For example, under AR(0.7) at 750 days, A rejects 2.1% at 1% and 12.7% at 10%; D rejects 1.6% and 11.3%.

## Power: rejection rate with an edge, nominal 5%

Pooled % over 300 replications (range across the 10 runs of 30).

| Scenario | N | A | B | C | D |
|---|---:|---:|---:|---:|---:|
| AR(0.4) + 0.1/day | 750 | 54.3 (43–73) | 49.0 (40–67) | 52.3 (40–70) | 48.3 (37–60) |
| AR(0.4) + 0.1/day | 1500 | 75.7 (60–87) | 73.7 (53–87) | 75.7 (63–83) | 73.7 (57–83) |
| AR(0.4) + 0.2/day | 750 | 95.7 (90–100) | 94.7 (90–100) | 95.0 (90–100) | 94.0 (90–97) |
| AR(0.4) + 0.2/day | 1500 | 100.0 (100–100) | 100.0 (100–100) | 100.0 (100–100) | 100.0 (100–100) |
| Marked trades, drift 0.004/day | 750 | 63.3 (53–77) | 62.7 (47–77) | 64.7 (53–77) | 63.7 (53–77) |
| Marked trades, drift 0.004/day | 1500 | 85.3 (77–97) | 85.0 (77–97) | 85.0 (73–97) | 85.3 (77–97) |
| **Mean of the six** | | **79.1** | **77.5** | **78.8** | **77.5** |

## Mean block lengths (days)

| Scenario | N | x1.0 (A, B) | x1.5 (C, D) | Cap |
|---|---:|---:|---:|---:|
| AR(1), phi 0 | 750 / 1500 | 1.4 / 1.4 | 2.2 / 2.2 | 83 / 117 |
| AR(1), phi 0.4 | 750 / 1500 | 7.3 / 9.7 | 10.9 / 14.5 | 83 / 117 |
| AR(1), phi 0.7 | 750 / 1500 | 15.8 / 20.7 | 23.6 / 31.0 | 83 / 117 |
| AR(0.4), t(3) shocks | 750 / 1500 | 7.3 / 9.7 | 10.9 / 14.5 | 83 / 117 |
| GARCH(1,1) | 750 / 1500 | 1.7 / 1.6 | 2.5 / 2.5 | 83 / 117 |
| Marked trades | 750 / 1500 | 5.0 / 4.7 | 7.4 / 7.1 | 83 / 117 |
| AR(0.4) + 0.1/day | 750 / 1500 | 7.4 / 9.7 | 11.1 / 14.6 | 83 / 117 |
| AR(0.4) + 0.2/day | 750 / 1500 | 7.1 / 9.7 | 10.7 / 14.5 | 83 / 117 |
| Marked trades, drift | 750 / 1500 | 5.6 / 5.1 | 8.4 / 7.6 | 83 / 117 |

The mean lengths stayed far below the cap in every scenario.

## What the tables show

- **Studentising removed most of the excess under strong dependence.** At AR(0.7), A rejected 7.5% (750 days) and 6.8% (1500 days); B rejected 5.5% and 4.7%, and D 5.8% and 5.4%.
- **Longer blocks alone did little.** C was within 0.3 points of A in every dependent cell except t(3) at 750 days, where it was 0.9 points lower.
- **The cell that decided the result was heavy tails at 750 days.** Every variant was 6.2% to 7.1% there. At 1500 days all four were 4.4% to 5.4%, except A and C at AR(0.7) (6.8% and 6.6%).
- **Independent days, GARCH and marked trades were near 5% for every variant.** The marked trades are the real use case.
- **The power cost of D is in the weak-edge AR cell.** At AR(0.4) + 0.1 a day over 750 days, D found the edge 48.3% of the time against A's 54.3%. On marked trades there was no cost: 63.7% against 63.3%, and 85.3% against 85.3%. Some of A's extra power comes from its over-rejection.

## What changed in the code

- `rpcd_test` has two new parameters: `method` (`"percentile"` or `"studentised"`) and `block_scale`. Their defaults are now `"studentised"` and `1.5`.
- Existing calls still work, but their p-values and intervals now come from D.
- `method="percentile", block_scale=1.0` reproduces PR #266's results exactly; this was checked bit for bit on four series.
- `Result` gains `method`. Its `mean_block` is the length used, after the scale and the cap.
- There are new helpers: `bartlett_lrv` and `block_cap`.
- There are 9 new tests:
  - each variant runs and repeats with its seed;
  - the default is D;
  - an unknown method is refused;
  - the block scale and the cap work;
  - the Bartlett variance is right;
  - the default's size on 200 marked-trade null series is between 1% and 10%. It measured 5.5%.
- No existing test bound changed. Under D, the existing size tests measure 3.3% (phi 0) and 4.0% (phi 0.4) against bounds of 1.5% to 10%. The edge test measures 94%, against a floor of 80%.

## Limits

- **Synthetic only.** This shows nothing about real market data: regime changes, trends, structural breaks, tails heavier than t(3), several coins, overlapping trades, or costs. One market history cannot be resampled into another regime (FDS-SR-001 §9 item 4).
- **The 6.0% limit sits near chance.** Each cell's pooled size has an SE of about 0.7 points. The worst of 12 independent cells from a test of exactly 5% averages 6.15% (exact binomial). So the rule is strict: a perfectly sized test fails it 57% of the time. A and C's 7.3% to 7.5% is a real excess, about 3.5 SE above 5%. Allowing for taking the worst of 12, B's 6.6% and D's 6.2% are not clearly distinguishable from 5%, or from each other.
- **One level, one direction.** Only the one-sided 5% test of theta <= 0 decided this. The 1% and 10% rates are recorded but did not count, and interval coverage was not measured.
- **The theory is for a related bootstrap.** Gonçalves and Vogelsang's result is for the moving-block bootstrap. Its use here with the stationary bootstrap rests on these simulations only.
- **Power depends on the fixtures.** The AR edges are in shock-SD units. The marked-trade drift (0.4% a day) is large in real terms; it was chosen to give A roughly 50% power, and gave about 61–63%. The marked trades number only 6 or 7 per 750 days, so those results depend on the trade generator.
- **This run differs from the first check.** That check (500 replications) put A at 7.4% (AR(0.4)) and 6.8% (AR(0.7)); this run has 5.9% and 7.5%. Different seeds, draws and replication counts account for the gap.
- **Provenance.** `results.json` records `git_head` as `c50b670`: the run used the working tree on top of it, with this commit's variant code. The defaults were changed after the run; the script names each variant explicitly, so that does not affect the results. Black reformatted `calibrate.py` after the run, layout only.

## Reproducing

Run this from the repository root, with numpy available:

```
python docs/dev/ptai-rd-001/o3/calibrate.py            # about 12 minutes with 6 workers here
python docs/dev/ptai-rd-001/o3/calibrate.py --quick --out <scratch file>   # a smoke run
```

The seeds are fixed (base 20261112), so the same numpy version gives the same counts.

## References

- Gonçalves, S. and Vogelsang, T. J. (2011). Block bootstrap HAC robust tests: the sophistication of the naive bootstrap. *Econometric Theory* 27(4), 745–791.
- Götze, F. and Künsch, H. R. (1996). Second-order correctness of the blockwise bootstrap for stationary observations. *Annals of Statistics* 24(5), 1914–1933.
- Lahiri, S. N. (2003). *Resampling Methods for Dependent Data*. Springer.
- Newey, W. K. and West, K. D. (1987). A simple, positive semi-definite, heteroskedasticity and autocorrelation consistent covariance matrix. *Econometrica* 55(3), 703–708.
- Patton, A., Politis, D. N. and White, H. (2009). Correction to "Automatic block-length selection for the dependent bootstrap". *Econometric Reviews* 28(4), 372–375.
- Politis, D. N. and Romano, J. P. (1994). The stationary bootstrap. *Journal of the American Statistical Association* 89(428), 1303–1313.
- Politis, D. N. and White, H. (2004). Automatic block-length selection for the dependent bootstrap. *Econometric Reviews* 23(1), 53–70.
