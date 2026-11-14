# Calibrating the mean test for SR1-E2's comparison with a hold

> **Synthetic data only.** No market data or network was used. This measures a new library function, `research_stats.resampling.mean_test`, that nothing in the app calls. SR1-E2 will use it for a figure it shows and does not test (its registration draft, decision D3). No default changed: `mean_test` and `rpcd_test` both stay at O3's choice.

**Verdict: the variant SR1-E2 names, D (studentised, blocks ×1.5), rejects slightly too often under autocorrelated heavy-tailed nulls. Its worst null size was 6.9% at nominal 5%, above O3's 6.0% limit. Pooled over all 14 null cells it was 5.6%. Each cell had 1,000 replications, a Monte Carlo SE of 0.7 points; pooled over the 14 cells the SE is 0.18 points. Its power matched that of an exact z-test that knows the standard error: 13.5%, 26.1% and 80.2% at true means of 0.5, 1.0 and 2.5 standard errors (6,000 replications each), against 12.6%, 26.0% and 80.4%. Synthetic series only.**

**Prepared:** 2026-11-14, on `feat/research-stats-mean-test`, cut from `main` (`795dba5`).
**Why:** SR1-E2's registration draft (§3, §8 item 2) shows the ensemble book against an equal-weight hold as the mean daily log-return difference (book less hold). It asks for "a studentised stationary bootstrap … on `research_stats.resampling.stationary_indices` with O3's block rule ×1.5, calibrated on null fixtures, as O3's variants were, before the freeze". This is that calibration.
**Files:** the script `mean-test/calibrate.py`, and its raw output `mean-test/results.json` (every cell, variant and run).
**Provenance:** the run used commit `60c50b5`, which adds `mean_test`. `results.json` records the module's SHA-256 (LF endings), which matched that commit, and the script's.

## Result

- **D's worst cell was 6.9%:** AR(0.7) with Student-t(3) shocks, at 750 days.
- **That is more than chance.**
  - Five of D's 14 cells were above 6.0%. A test of exactly 5% would put about 0.9 of 14 cells there, and five or more with probability 0.2% (exact binomial).
  - The worst of 14 cells from an exact test averages 6.2%, and reaches 6.9% or more 7% of the time.
- **Where the excess is:** the four AR cells with t(3) shocks pooled 6.4%; the other ten cells pooled 5.3%.
- **The other variants:**
  - B (studentised, ×1.0) had the lowest worst cell, 6.6%, and pooled 5.4%.
  - A and C (percentile) reached 7.5%.
  - In O3 the order was reversed: D's worst was 6.2% and B's 6.6%. Neither run separates B from D.
- **The interval:** D's 95% interval covered the true mean in 94.3% of null replications on average, and in 92.2% at worst (AR(0.7) with t(3) shocks, 1,580 days). Its lower end was above the true mean in 2.7% on average and 4.2% at worst, against 2.5% nominal.

## Which variant SR1-E2 names

SR1-E2's draft names the studentised test with blocks ×1.5: variant D, O3's default and `mean_test`'s. The script declared, before the run, that the run chooses nothing. It reports D against O3's 6.0% limit.

**D's worst null size, 6.9%, is above 6.0%.** That limit decided O3, and no variant met it there either. Here B came closest (6.6%). The defaults are unchanged.

For SR1-E2, the figure is shown, not tested (D3), so no pass or fail rests on it. On series like these fixtures, read its interval as slightly narrow when the daily differences are autocorrelated and heavy-tailed: there it covered the truth 92% to 94% of the time, not 95%.

## What was measured

| Variant | Method | Mean block length |
|---|---|---|
| A | Percentile | Chosen from the data (Politis and White), ×1.0 |
| B | Studentised | ×1.0 |
| C | Percentile | ×1.5 |
| D | Studentised (SR1-E2's) | ×1.5 |

Lengths are capped at min(3 sqrt(N), N/3) after scaling: 83 days at N = 750 and 120 at N = 1,580.

**The statistic** is the mean of a daily series, tested for H0: mean ≤ 0 against mean > 0. The studentised method divides by a Bartlett-kernel (Newey-West) standard error whose bandwidth is the mean block length, on the original and on each resample. It is `rpcd_test`'s method with one unit of capital every day, and a test checks that the two agree draw for draw.

**Null scenarios (mean 0).** Each was run at N = 750 and 1,580 days; the development period is about 1,586 days. The shocks have unit variance.
- Independent days, normal; and independent days, Student-t(3).
- AR(1) with phi 0.4 and 0.7, each with normal shocks and with t(3) shocks.
- A volatility cluster: GARCH(1,1) with omega 0.05, alpha 0.1, beta 0.85 and normal shocks, as in O3.

**Power scenarios.** Independent normal days, AR(0.4) with t(3) shocks, and the GARCH series, at both lengths. To each was added a mean of 0.5, 1.0 or 2.5 standard errors: the sample mean's exact standard error for that process and N. For comparison:
- An exact one-sided z-test at 5% that knew the standard error would find those means 12.6%, 26.0% and 80.4% of the time.
- SR1-E2's draft (§6) reports that the exploration's 95% interval for the yearly lead over the hold had a half-width of about 0.39. On that spread, one standard error is roughly 0.2 a year of log return. So 2.5 standard errors is roughly the 0.5 a year that the draft says the development months could detect.

**Replications** (the owner's rule):
- Every cell is 10 seeded runs of 100 replications, 1,000 in all, for the null and for the power cells.
- Each test used 999 bootstrap draws.
- In each replication the four variants saw the same data and the same bootstrap seed, so the comparisons between variants are paired.
- 128,000 tests in all, at about 64 ms each. The run used 6 worker processes and took 1,374 seconds (23 minutes).

## Size: rejection rate with no edge, nominal 5%

Pooled % over 1,000 replications, with the range across the 10 runs of 100. The pooled Monte Carlo SE is about 0.7 points; a single run's is about 2.2 points. Each variant's worst cell is in bold.

| Scenario | N | A | B | C | D |
|---|---:|---:|---:|---:|---:|
| Independent, normal | 750 | 5.6 (2–9) | 5.6 (2–9) | 5.7 (3–9) | 5.8 (3–9) |
| Independent, normal | 1580 | 5.7 (4–9) | 5.9 (4–9) | 6.4 (4–9) | 6.3 (4–9) |
| Independent, t(3) | 750 | 3.3 (1–6) | 3.7 (1–7) | 3.3 (0–6) | 4.1 (1–7) |
| Independent, t(3) | 1580 | 3.8 (3–6) | 4.4 (3–8) | 4.0 (3–6) | 4.6 (3–7) |
| AR(0.4), normal | 750 | 6.5 (3–12) | 5.2 (2–11) | 6.5 (3–11) | 5.4 (2–10) |
| AR(0.4), normal | 1580 | 5.5 (2–12) | 5.0 (2–10) | 5.6 (2–12) | 5.5 (2–12) |
| AR(0.4), t(3) shocks | 750 | **7.5 (4–15)** | 5.9 (3–12) | 6.6 (3–14) | 6.2 (1–13) |
| AR(0.4), t(3) shocks | 1580 | 6.6 (3–8) | 6.5 (3–10) | 6.4 (3–10) | 6.4 (3–10) |
| AR(0.7), normal | 750 | 5.6 (3–9) | 4.1 (1–6) | 5.5 (3–7) | 4.1 (1–7) |
| AR(0.7), normal | 1580 | 6.8 (3–9) | 5.8 (3–8) | 6.7 (3–9) | 5.9 (2–9) |
| AR(0.7), t(3) shocks | 750 | **7.5 (5–11)** | **6.6 (5–9)** | **7.5 (5–11)** | **6.9 (4–10)** |
| AR(0.7), t(3) shocks | 1580 | 7.0 (3–12) | 6.5 (2–11) | 7.2 (2–12) | 6.2 (1–11) |
| GARCH(1,1) | 750 | 5.5 (3–8) | 5.4 (3–8) | 5.6 (2–8) | 5.6 (2–8) |
| GARCH(1,1) | 1580 | 5.2 (1–8) | 5.4 (1–9) | 5.4 (1–10) | 5.5 (1–10) |
| **Worst** | | **7.5** | **6.6** | **7.5** | **6.9** |
| Pooled over the 14 | | 5.86 | 5.43 | 5.89 | 5.61 |

The pooled rates over 14,000 replications have an SE of 0.18 points around 5%. D's 5.61% is 3.3 SE above it, and B's 5.43% is 2.3 SE above.

**At 1% and 10%** the pattern is the same; the full rates are in `results.json`.

| Variant | Worst at 1% | Pooled at 1% | Worst at 10% | Pooled at 10% |
|---|---:|---:|---:|---:|
| A | 2.3 (AR(0.7), t(3), 1580) | 1.34 | 13.0 (AR(0.4), t(3), 750) | 11.39 |
| B | 2.0 (AR(0.7), t(3), 750) | 1.14 | 12.6 (independent, normal, 750) | 10.76 |
| C | 2.3 (AR(0.7), t(3), 1580) | 1.31 | 12.9 (AR(0.7), t(3), 750) | 11.24 |
| D | 2.2 (AR(0.7), t(3), 750) | 1.15 | 12.4 (independent, normal, 750) | 10.79 |

## The 95% interval: coverage with no edge

% of the 1,000 replications whose interval covered the true mean (0), with the share whose interval lay wholly above it / wholly below it (2.5% each nominal). The SE of a coverage near 95% is about 0.7 points.

| Scenario | N | A | B | C | D |
|---|---:|---:|---:|---:|---:|
| Independent, normal | 750 | 96.0 (2.1 / 1.9) | 96.2 (2.1 / 1.7) | 96.4 (2.1 / 1.5) | 96.8 (1.8 / 1.4) |
| Independent, normal | 1580 | 94.0 (2.8 / 3.2) | 94.3 (2.9 / 2.8) | 94.2 (2.8 / 3.0) | 94.7 (2.8 / 2.5) |
| Independent, t(3) | 750 | 95.8 (1.6 / 2.6) | 95.8 (1.5 / 2.7) | 95.9 (1.7 / 2.4) | 95.4 (1.5 / 3.1) |
| Independent, t(3) | 1580 | 95.6 (2.1 / 2.3) | 95.8 (2.1 / 2.1) | 95.8 (1.8 / 2.4) | 95.7 (2.0 / 2.3) |
| AR(0.4), normal | 750 | 92.6 (3.6 / 3.8) | 95.1 (2.3 / 2.6) | 92.5 (3.8 / 3.7) | 95.0 (2.5 / 2.5) |
| AR(0.4), normal | 1580 | 91.9 (3.6 / 4.5) | 93.6 (2.8 / 3.6) | 92.6 (3.3 / 4.1) | 93.4 (2.7 / 3.9) |
| AR(0.4), t(3) shocks | 750 | 92.5 (3.5 / 4.0) | 94.9 (2.4 / 2.7) | 93.5 (3.0 / 3.5) | 93.9 (3.1 / 3.0) |
| AR(0.4), t(3) shocks | 1580 | 92.4 (4.1 / 3.5) | 92.7 (3.8 / 3.5) | 92.4 (4.1 / 3.5) | 92.9 (4.0 / 3.1) |
| AR(0.7), normal | 750 | 92.5 (2.9 / 4.6) | 94.6 (1.9 / 3.5) | 92.4 (2.8 / 4.8) | 94.3 (1.9 / 3.8) |
| AR(0.7), normal | 1580 | 91.9 (3.7 / 4.4) | 93.8 (3.1 / 3.1) | 92.0 (3.6 / 4.4) | 94.0 (2.7 / 3.3) |
| AR(0.7), t(3) shocks | 750 | 91.3 (4.9 / 3.8) | 93.2 (4.0 / 2.8) | 91.0 (5.2 / 3.8) | 93.1 (4.2 / 2.7) |
| AR(0.7), t(3) shocks | 1580 | 90.6 (4.7 / 4.7) | 92.0 (4.0 / 4.0) | 90.6 (4.5 / 4.9) | 92.2 (3.8 / 4.0) |
| GARCH(1,1) | 750 | 94.3 (2.7 / 3.0) | 94.3 (2.6 / 3.1) | 94.3 (2.6 / 3.1) | 94.4 (2.6 / 3.0) |
| GARCH(1,1) | 1580 | 94.6 (2.4 / 3.0) | 94.9 (2.5 / 2.6) | 94.7 (2.4 / 2.9) | 94.4 (2.6 / 3.0) |
| **Lowest** | | **90.6** | **92.0** | **90.6** | **92.2** |

In the power cells D's coverage ran from 93.3% to 95.9% (all in `results.json`).

## Power: rejection rate with an edge, nominal 5%

Pooled % over 1,000 replications (range across the 10 runs of 100). The SE is about 1.1 points at 13%, 1.4 at 26% and 1.3 at 80%; a mean of six cells has roughly 0.4 times those.

| Scenario | N | z-test | A | B | C | D |
|---|---:|---:|---:|---:|---:|---:|
| Independent, normal + 0.5 SE | 750 | 12.6 | 13.9 (7–18) | 13.9 (7–19) | 13.9 (8–19) | 14.0 (7–19) |
| Independent, normal + 0.5 SE | 1580 | 12.6 | 12.7 (9–17) | 12.9 (9–17) | 13.2 (9–17) | 13.3 (9–17) |
| AR(0.4), t(3) shocks + 0.5 SE | 750 | 12.6 | 15.9 (12–20) | 14.3 (10–19) | 15.6 (13–21) | 14.5 (9–19) |
| AR(0.4), t(3) shocks + 0.5 SE | 1580 | 12.6 | 16.4 (11–21) | 15.2 (11–19) | 15.5 (13–18) | 14.5 (11–17) |
| GARCH(1,1) + 0.5 SE | 750 | 12.6 | 11.3 (7–17) | 11.4 (7–17) | 11.3 (7–16) | 11.7 (9–16) |
| GARCH(1,1) + 0.5 SE | 1580 | 12.6 | 12.9 (8–21) | 12.8 (8–20) | 13.1 (8–22) | 13.0 (7–23) |
| Independent, normal + 1 SE | 750 | 26.0 | 26.6 (20–33) | 25.9 (20–32) | 26.1 (20–31) | 25.6 (19–30) |
| Independent, normal + 1 SE | 1580 | 26.0 | 22.8 (17–29) | 22.5 (16–28) | 22.7 (15–29) | 22.6 (15–29) |
| AR(0.4), t(3) shocks + 1 SE | 750 | 26.0 | 32.4 (27–40) | 28.2 (21–38) | 31.7 (27–40) | 27.7 (22–38) |
| AR(0.4), t(3) shocks + 1 SE | 1580 | 26.0 | 29.8 (23–36) | 27.6 (20–36) | 29.1 (21–37) | 27.6 (20–34) |
| GARCH(1,1) + 1 SE | 750 | 26.0 | 27.7 (24–35) | 27.8 (24–34) | 27.5 (22–36) | 27.6 (22–37) |
| GARCH(1,1) + 1 SE | 1580 | 26.0 | 26.3 (17–33) | 26.2 (16–32) | 25.7 (16–32) | 25.6 (15–32) |
| Independent, normal + 2.5 SE | 750 | 80.4 | 78.5 (71–83) | 78.3 (71–83) | 78.4 (71–85) | 78.5 (72–85) |
| Independent, normal + 2.5 SE | 1580 | 80.4 | 79.9 (73–89) | 79.9 (73–90) | 80.3 (73–88) | 80.1 (72–88) |
| AR(0.4), t(3) shocks + 2.5 SE | 750 | 80.4 | 84.3 (78–89) | 80.3 (72–87) | 84.0 (77–89) | 81.0 (75–86) |
| AR(0.4), t(3) shocks + 2.5 SE | 1580 | 80.4 | 83.7 (79–89) | 79.8 (72–86) | 82.5 (77–88) | 80.1 (71–86) |
| GARCH(1,1) + 2.5 SE | 750 | 80.4 | 82.8 (78–86) | 82.5 (77–86) | 82.7 (77–87) | 82.5 (78–86) |
| GARCH(1,1) + 2.5 SE | 1580 | 80.4 | 79.8 (72–86) | 79.8 (73–86) | 79.7 (72–85) | 79.1 (72–85) |
| **Mean at 0.5 SE** | | 12.6 | **13.9** | **13.4** | **13.8** | **13.5** |
| **Mean at 1 SE** | | 26.0 | **27.6** | **26.4** | **27.1** | **26.1** |
| **Mean at 2.5 SE** | | 80.4 | **81.5** | **80.1** | **81.3** | **80.2** |

## Mean block lengths (days)

| Scenario | N 750: ×1.0 (A, B) / ×1.5 (C, D) | N 1580: ×1.0 / ×1.5 |
|---|---:|---:|
| Independent, normal | 1.5 / 2.2 | 1.4 / 2.1 |
| Independent, t(3) | 1.4 / 2.1 | 1.5 / 2.3 |
| AR(0.4), normal | 7.1 / 10.7 | 9.8 / 14.7 |
| AR(0.4), t(3) shocks | 7.2 / 10.8 | 9.8 / 14.8 |
| AR(0.7), normal | 15.9 / 23.8 | 20.9 / 31.4 |
| AR(0.7), t(3) shocks | 15.7 / 23.5 | 21.1 / 31.7 |
| GARCH(1,1) | 1.7 / 2.5 | 1.7 / 2.5 |
| Cap | 83 | 120 |

The mean lengths stayed far below the cap in every scenario.

## What the tables show

- **Heavy tails with dependence are the problem cells.** Every variant was at its worst under AR(0.7) with t(3) shocks, and all four were 5.9% to 7.5% in the four AR cells with t(3) shocks.
- **Studentising helped under dependence, as in O3.** With normal AR shocks, B and D were 4.1% to 5.9%, and A and C 5.5% to 6.8%. The interval's coverage moved the same way: 93.4% to 95.0% for D against 91.9% to 92.6% for A.
- **Longer blocks alone did little.** C was within 0.9 points of A in every null cell, and D within 0.5 of B.
- **Independent heavy tails made every variant conservative:** 3.3% to 4.6% under independent t(3) days.
- **The GARCH cluster and independent normal days gave 5.2% to 6.4%** across the variants. D's 6.3% (independent normal days, 1,580 days) is one of its five cells above 6.0%.
- **D's power is the z-test's.** Its mean power was within 0.9 points of the z-test's at each effect size. A's mean power was 0.4 to 1.5 points higher than D's. Most of that came from the AR cells with t(3) shocks, where A was 1.4 to 4.7 points higher and also over-rejected most.

## What changed in the code

- `research_stats.resampling.mean_test(x, draws=2000, seed=0, mean_block=None, level=0.95, method=DEFAULT_METHOD, block_scale=DEFAULT_BLOCK_SCALE)`, returning `MeanResult(mean, p_value, interval, level, mean_block, draws, days, method)`.
- Its methods and block rule are `rpcd_test`'s: percentile or studentised; Politis-White ×`block_scale`, capped. A `mean_block` given is used as it is. The mean and interval are per day: callers annualise (×365).
- It refuses fewer than two days, values that are not finite, and anything but one value a day.
- `rpcd_test`, `Result` and the defaults are unchanged.
- There are 16 new tests:
  - size on independent days and a clear positive mean, for each method;
  - repeating with the seed;
  - agreement with `rpcd_test` on one unit of capital a day;
  - the methods differ, and the default;
  - the block scale, the cap and a given length;
  - bad input.

## Limits

- **Synthetic only.** This shows nothing about the real book-less-hold series. Real daily differences may have tails heavier than t(3), regime changes (the book in cash while the hold falls), trends or breaks. One market history cannot be resampled into another regime (FDS-SR-001 §9 item 4).
- **The 6.0% limit sits near chance.** A test of exactly 5% shows a worst of 14 cells above 6.0% 62% of the time. D's case does not rest on its worst cell, though: five cells above 6.0% and a pooled 5.6% are a small real excess on these fixtures.
- **One level, one direction for the size.** The one-sided 5% test of mean ≤ 0 is the measure reported against O3's limit. The 1% and 10% rates and the interval's coverage are recorded beside it.
- **The theory is for a related bootstrap.** Gonçalves and Vogelsang's result is for the moving-block bootstrap. Its use here with the stationary bootstrap rests on simulations only, as in O3.
- **Power depends on the fixtures.** The effects are in exact standard errors of each process, which a real analysis does not know. Three processes were used for power, not all seven.
- **This run differs from O3.** The seeds, lengths (1,580 days, not 1,500) and scenarios differ. O3's AR cells with unit capital were the same statistic. Its AR(0.4) cell with t(3) shocks at 750 days gave D 6.2%, as here.

## Reproducing

Run this from the repository root, with numpy available:

```
python docs/dev/ptai-rd-001/mean-test/calibrate.py            # about 23 minutes with 6 workers here
python docs/dev/ptai-rd-001/mean-test/calibrate.py --quick --out <scratch file>   # a smoke run
```

The seeds are fixed (base 20261114), so the same numpy version gives the same counts. The chance figures in "Result" (cells above 6.0%, the worst of 14, the pooled SE) are exact binomial computations from the counts in `results.json`.

## References

- Gonçalves, S. and Vogelsang, T. J. (2011). Block bootstrap HAC robust tests: the sophistication of the naive bootstrap. *Econometric Theory* 27(4), 745–791.
- Götze, F. and Künsch, H. R. (1996). Second-order correctness of the blockwise bootstrap for stationary observations. *Annals of Statistics* 24(5), 1914–1933.
- Lahiri, S. N. (2003). *Resampling Methods for Dependent Data*. Springer.
- Newey, W. K. and West, K. D. (1987). A simple, positive semi-definite, heteroskedasticity and autocorrelation consistent covariance matrix. *Econometrica* 55(3), 703–708.
- Patton, A., Politis, D. N. and White, H. (2009). Correction to "Automatic block-length selection for the dependent bootstrap". *Econometric Reviews* 28(4), 372–375.
- Politis, D. N. and Romano, J. P. (1994). The stationary bootstrap. *Journal of the American Statistical Association* 89(428), 1303–1313.
- Politis, D. N. and White, H. (2004). Automatic block-length selection for the dependent bootstrap. *Econometric Reviews* 23(1), 53–70.
