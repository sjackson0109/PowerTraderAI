# SR-001 long-holding resampling study

**Date:** 2026-11-08. **Status:** research and documentation only. Synthetic data only. Nothing was registered, frozen or re-run, and E1 is untouched.
**Pre-statement:** `PRE-STATEMENT.md`, committed in `cb311c1` before the study script existed.
**Script:** `docs/dev/sr1_bootstrap_study.py`, run as `"$PY" docs/dev/sr1_bootstrap_study.py <out-dir> --jobs 14`.
**Outputs here:**
- `results.json.gz`: the script's `results.json`, gzipped byte for byte;
- `tables.md`: every cell and method;
- `diagnostics.json`, from `docs/dev/sr1_bootstrap_diagnostics.py`.

The summary tables below come from `docs/dev/sr1_bootstrap_report_tables.py`.

> **Verdict.**
> - **FDS-SR-001 §6.0's long-trade rule is not dependable.** When trades last weeks to months it is anti-conservative: size 7.1% to 42.0% at a nominal 5%, and up to 45% family-wise error under Holm.
> - **No block length rescues entry-day attribution.** Every length from 14 to 896 days exceeded 7.5% somewhere.
> - **Marking open positions to market by day, with short circular blocks, holds the error rate.** Size was at most 4.2% in every deciding cell, and Holm's family-wise error at most 1.0%.
> - **But it is conservative where profits are strongly right-skewed** (down to 1.3%). So no method met the pre-stated size band in every cell.
> - **The pre-stated fallback selected M-14.** Marked days with blocks of 7 to 56 days cannot be told apart in this study.
> - Synthetic data only: this says how the test behaves, not whether any strategy makes money.

## 1. The question, and the answer in brief

**The question.** FDS-SR-001 §6.0 sets the day-block bootstrap's block length for long trades at L = 28 × 2^k days, with k the smallest integer ≥ 0 for which at most 1% of the family's trades last longer than L ÷ 2. For daily trend strategies this gave 896-day blocks over a 1,586-day period: under two blocks.

**What goes wrong.** Two things:
1. **The rule follows the longest 1% of trades.** Heavy-tailed holds drive L to the length of the period:
   - median holds of 10, 30, 60 and 120 days gave L = 224, 896, 1,792 and 3,584 days (table B);
   - with L ≥ N there is one block; every draw then equals the estimate, so p = 1 ÷ (B + 1) whenever θ̂ > 0. The test then rejects about as often as θ̂ is positive.
   - With K blocks of independent days, a circular block bootstrap's variance is about (1 − 1 ÷ K) of the truth: half at two blocks. Table C shows the effect on both attributions.
2. **Entry-day attribution creates the long dependence.**
   - A trade's whole profit sits on its entry day. Trades that overlap in time share the same market days, but their entry days fall in different blocks.
   - A short block cuts those links (too narrow), and a long block leaves too few blocks (too narrow again).
   - Every entry-day method's bootstrap spread was too narrow: a median of 0.54 to 0.75 of the true scale over the deciding cells (table K).

**What works.** Attribute each day's change in the open positions' marked value to that day.
- Entries are decided on closed bars, so with no edge the day-to-day changes are close to uncorrelated, however long the trades last.
- A day's common shock stays inside one day, with every coin's positions together.
- The sums are the same, so θ̂ does not change. Only the resampling unit changes.

## 2. Blinding

- The grids were set without looking at E1's results: trade counts of 50 to 300, median holds of 10 to 120 days, the market models and the effect sizes. They are round numbers, stated in the pre-statement before the script existed.
- Not opened, read or searched: `docs/dev/sr1-e1/`, the M5c section of `docs/dev/RUN-LOG-sr-1.md` and the backlog after it, and any file reporting E1's figures.
- **Disclosure.** This session's working notes held one line about E1: its 896-day blocks (also in the owner's brief) and that its two economic members did not pass. No E1 figure was seen.
- The method was then chosen by the pre-stated rule, mechanically, on synthetic data.

## 3. What was compared

The full design is in `PRE-STATEMENT.md`. In short:

**The statistic** is FDS-SR-001's: return per capital-day, θ̂ = Σ net ÷ Σ capital-days. It is tested one-sided against 0 by the centred p-value, as `signal_fusion.evaluation.bootstrap` computes it.

**Two ways to put a trade on days:**
- **E (entry day)** is today's: a trade's whole net and capital-days sit on its entry day (FDS-SIG-004 §6.0).
- **M (marked days)** is new: each day carries the change in the open positions' marked value that day, and their capital that day.
  - The round-trip cost is booked once, on the entry day; the exit day carries the rest of the trade's net.
  - The day sums add up to the same totals, so θ̂ is the same number.

**25 methods** (24 bootstraps and one reference):
- E with the §6.0 rule (uncapped, and capped at 112 days), fixed blocks of 14 to 896 days, Politis–White (PW) and the stationary bootstrap (SB);
- M with fixed blocks of 1 to 896 days, PW and SB;
- trades resampled independently (T-iid), and episodes of overlapping trades resampled (T-episode);
- a Newey–West t-test on the marked series (NW), as a non-bootstrap reference.

**Markets** (11 coins, 1,586 scored days, daily simple returns):
- **base:** a common factor with GARCH volatility and t₄ shocks, coin loadings 0.8 to 1.3, and coin-specific GARCH noise;
- **bear:** the same plus one 365-day bear market at a random place (−0.25% a day, volatility × 1.5);
- **regime** (stress only): persistent Markov drift regimes (±0.15% a day, spells of a year on average).

**Trades:**
- **exo(n, h):** an entry process with heavy-tailed holds.
  - Holds are lognormal with a median of h ∈ {10, 30, 60, 120} days; the 99th percentile is 6 to 10 times the median after the cut at the period's end.
  - n ∈ {50, 100, 150, 300} trades over the period. Three combinations cannot fit 11 coins with one position each and were dropped: (150, 120), (300, 60) and (300, 120).
  - Entries are three times as likely after a 30-day rise, so they cluster across coins.
- **donchian** and **tsmom:** STRAT-004's and STRAT-005's own rules at their defaults, on the simulated closes.
- One position per coin, with positions overlapping across coins: 1 to 10 open at a time on average. Costs are 0.50% + 0.05% a fill.

**The null** is exact for each cell. θ_true is estimated from 4,000 separate replications, and every trade is moved by θ_true per capital-day.
**Alternatives** add δ per capital-day. Every method's statistic and draws move by exactly δ, so power comes from the null draws (a self-check confirms the shift).

**Scale:**
- 10 runs of 300 replications for every cell, run r seeded 20261108 + r: 3,000 replications a cell, B = 1,000 draws a replication.
- 60 cells: 22 deciding, 11 reported only (8 with n = 50, 3 stress), 3 family-wise cells with four members, and 24 floor cells (4 reuse core cells of the same design).

**The real implementation:**
- Every circular day-block method runs through the repository's own `Bootstrap.resampled`, `ratio`, `centred_p` and `interval`. Only the start days come from numpy rather than `random()`, for speed.
- Self-checks at the start of the run (all passed):
  - the class sums the same days as the original for the same starts;
  - the marked sums add up to the trades' nets and capital-days;
  - the entry-day sums equal the implementation's `day_sums`;
  - one position per coin;
  - the shift property;
  - p ≤ 5% exactly when θ̂ exceeds the stored critical value;
  - the Donchian windows;
  - the two stationary-bootstrap forms;
  - the §6.0 rule on hand-worked holds.
- The study's copy of the §6.0 rule agrees with `strategy_lab.e1.block_length` on 2,000 random sets of holds (a one-off check, run in the sandbox).
- Six methods were rerun through `bootstrap.test_statistic` unchanged (§4.8).

## 4. Results

All figures are percentages, pooled over 10 runs × 300 replications a cell. Per-run ranges are in brackets. A size estimate from 3,000 replications has a standard error of about 0.4 points at 5%.

### 4.1 Every method over the 22 deciding null cells (table A)

Size at nominal 5% (one-sided); coverage of the two-sided 90% interval; power at λ = 2.5, i.e. an effect of 2.5 × SD₀ (an ideal test with a normal estimate has 80%).

| Method | Size: lowest – highest cell | Size: mean over cells (runs) | 90% coverage, worst cell: percentile / basic | Agreement of p ≤ 5% with "90% interval above 0", worst cell: percentile (null / λ 2.5) · basic (null / λ 2.5) | Power at λ = 2.5: lowest cell (runs) | Power at λ = 2.5: mean | Holm FWER: highest cell | Units: fewest | Valid |
|---|---|---|---|---|---|---|---|---|---|
| E-rule | 7.1 – 42.0 | 17.9 (17.1–18.8) | 0.0 / 0.0 | 92.8 / 94.1 · 99.9 / 99.7 | 87 (83–88) | 96 | 45.3 | 1 | no |
| E-rule-cap | 5.4 – 9.7 | 7.1 (6.7–7.5) | 59.9 / 60.8 | 94.7 / 95.2 · 99.8 / 99.8 | 87 (83–88) | 95 | 5.3 | 15 | no |
| E-14 | 6.0 – 16.9 | 11.0 (10.6–11.4) | 49.9 / 51.2 | 96.0 / 97.8 · 99.7 / 99.7 | 89 (86–90) | 97 | 8.3 | 114 | no |
| E-28 | 5.3 – 14.9 | 9.5 (9.0–10.1) | 52.4 / 53.4 | 94.9 / 97.3 · 99.7 / 99.8 | 88 (84–89) | 96 | 7.3 | 57 | no |
| E-56 | 5.2 – 12.1 | 8.1 (7.8–8.7) | 55.6 / 56.9 | 94.6 / 96.3 · 99.6 / 99.7 | 87 (84–89) | 96 | 6.1 | 29 | no |
| E-112 | 5.3 – 9.6 | 7.0 (6.7–7.4) | 60.2 / 60.8 | 94.7 / 95.5 · 99.8 / 99.7 | 87 (81–88) | 95 | 5.2 | 15 | no |
| E-224 | 5.9 – 8.6 | 7.0 (6.7–7.5) | 62.6 / 63.8 | 94.6 / 94.6 · 99.8 / 99.8 | 87 (82–88) | 95 | 5.5 | 8 | no |
| E-448 | 6.7 – 9.8 | 8.5 (7.9–9.0) | 61.6 / 62.8 | 93.8 / 93.7 · 99.8 / 99.8 | 88 (83–89) | 95 | 8.2 | 4 | no |
| E-896 | 10.7 – 15.5 | 13.2 (12.6–13.9) | 53.9 / 54.4 | 91.8 / 95.5 · 99.9 / 99.9 | 92 (89–93) | 97 | 17.0 | 2 | no |
| E-PW | 6.5 – 18.7 | 12.1 (11.6–12.6) | 47.7 / 49.0 | 96.8 / 98.1 · 99.8 / 99.9 | 90 (87–91) | 97 | 9.6 | 21 | no |
| E-SB | 6.5 – 18.2 | 12.0 (11.5–12.6) | 48.1 / 49.0 | 96.8 / 98.0 · 99.8 / 99.8 | 90 (87–92) | 97 | 9.5 | 24 | no |
| M-1 | 1.3 – 4.6 | 3.3 (3.0–3.5) | 88.6 / 91.3 | 99.2 / 97.3 · 99.7 / 99.5 | 81 (77–82) | 89 | 1.7 | 1586 | no |
| M-7 | 1.3 – 4.3 | 3.1 (3.0–3.3) | 87.1 / 88.1 | 98.9 / 97.3 · 99.8 / 99.6 | 82 (78–82) | 89 | 1.3 | 227 | no |
| **M-14** | **1.3 – 4.2** | **3.0 (2.8–3.2)** | **86.4 / 87.6** | **98.7 / 97.2 · 99.9 / 99.7** | **82 (78–83)** | **90** | **1.0** | **114** | **no** |
| M-28 | 1.6 – 4.2 | 2.9 (2.8–3.2) | 84.3 / 86.8 | 98.6 / 97.1 · 99.9 / 99.7 | 83 (79–83) | 90 | 0.9 | 57 | no |
| M-56 | 1.6 – 4.3 | 3.0 (2.8–3.3) | 82.5 / 86.1 | 98.5 / 96.1 · 99.7 / 99.7 | 84 (80–85) | 91 | 1.0 | 29 | no |
| M-112 | 1.8 – 4.9 | 3.3 (2.9–3.7) | 79.5 / 84.7 | 98.3 / 95.3 · 99.8 / 99.5 | 85 (81–85) | 92 | 1.4 | 15 | no |
| M-224 | 2.4 – 6.3 | 4.2 (3.8–4.7) | 75.8 / 81.1 | 97.1 / 94.2 · 99.8 / 99.7 | 85 (81–87) | 93 | 2.5 | 8 | no |
| M-448 | 3.1 – 8.5 | 6.2 (5.9–6.5) | 70.8 / 76.4 | 96.6 / 93.1 · 99.8 / 99.8 | 87 (84–89) | 94 | 5.6 | 4 | no |
| M-896 | 6.6 – 14.6 | 11.1 (10.5–11.7) | 61.9 / 64.7 | 94.3 / 95.4 · 99.8 / 99.9 | 91 (87–93) | 97 | 13.4 | 2 | no |
| M-PW | 1.3 – 4.5 | 3.1 (2.8–3.5) | 86.4 / 87.7 | 98.9 / 97.4 · 99.8 / 99.6 | 82 (77–83) | 90 | 1.3 | 15 | no |
| M-SB | 1.2 – 4.2 | 3.0 (2.8–3.4) | 85.7 / 87.6 | 98.9 / 97.4 · 99.9 / 99.7 | 82 (78–83) | 90 | 1.2 | 14 | no |
| T-iid | 7.2 – 20.8 | 14.5 (13.9–14.8) | 42.2 / 43.5 | 96.7 / 98.3 · 99.7 / 99.7 | 91 (88–92) | 98 | 14.6 | 53 | no |
| T-episode | 5.2 – 47.1 | 23.5 (22.6–24.3) | 0.0 / 0.0 | 87.6 / 73.4 · 99.7 / 99.8 | 84 (80–84) | 94 | 52.5 | 1 | no |
| NW | 1.3 – 4.5 | 3.2 (3.0–3.5) | 87.7 / 87.7 | 100.0 / 100.0 · 100.0 / 100.0 | 82 (77–83) | 90 | 1.4 | – | reference |

Notes:
- **Power is only comparable at matched size.** The entry-day and trade-level methods look more powerful because they reject too often under the null.
- **Power at λ = 2.5 exceeds the ideal 80%** for the marked methods, although they are conservative. Under the null θ̂ is right-skewed (median skew 2.1 over the deciding cells), so its left tail is short and a shift of 2.5 × SD₀ clears the critical value more often than for a normal estimate.
- **Basic against percentile.** The basic interval's "above 0" agrees with "p ≤ 5%" in 99.5% to 100% of replications. The remainder is the gap between the interpolated percentile and the p-value's count. The percentile interval disagrees in up to 2.8% (M-14) and up to 26.6% (T-episode).

### 4.2 Size, every null cell (table B)

| Cell | Trades | Hold p50 / p99 | §6.0 L | E-rule | E-rule-cap | E-28 | E-112 | E-448 | E-PW | E-SB | M-1 | M-7 | M-14 | M-28 | M-56 | M-112 | M-448 | M-PW | M-SB | T-iid | T-episode | NW |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| exo(50,10):base | 48 | 11 / 85 | 224 | 6.7 | 4.7 | 4.3 | 4.7 | 7.8 | 4.5 | 4.6 | 3.9 | 3.3 | 3.3 | 3.5 | 3.6 | 4.3 | 7.4 | 3.6 | 3.6 | 5.3 | 4.6 | 3.5 |
| exo(50,30):base | 48 | 30 / 242 | 896 | 15.7 | 5.6 | 5.8 | 5.4 | 8.8 | 7.1 | 7.0 | 3.4 | 3.0 | 2.7 | 2.8 | 3.0 | 3.8 | 7.4 | 2.8 | 2.8 | 7.4 | 8.1 | 3.1 |
| exo(50,60):base | 48 | 59 / 444 | 1792 | 29.4 | 6.3 | 7.6 | 6.3 | 8.6 | 9.0 | 8.7 | 2.7 | 2.8 | 2.6 | 2.5 | 2.4 | 2.5 | 5.6 | 2.4 | 2.4 | 9.6 | 22.0 | 2.9 |
| exo(50,120):base | 48 | 114 / 757 | 1792 | 40.5 | 9.0 | 10.8 | 9.2 | 9.4 | 11.9 | 11.9 | 2.4 | 2.4 | 2.5 | 2.5 | 2.5 | 2.7 | 4.7 | 2.3 | 2.4 | 12.5 | 39.8 | 2.5 |
| **exo(100,10):base** | 95 | 11 / 89 | 224 | 7.5 | 5.4 | 5.7 | 5.3 | 8.8 | 6.5 | 6.5 | 4.3 | 4.0 | 4.1 | 4.2 | 4.3 | 4.9 | 8.1 | 4.3 | 4.2 | 7.2 | 5.4 | 4.2 |
| **exo(100,30):base** | 95 | 30 / 257 | 896 | 16.8 | 5.8 | 7.4 | 5.8 | 8.2 | 10.0 | 9.8 | 3.1 | 3.0 | 2.9 | 2.8 | 2.8 | 3.0 | 6.3 | 3.2 | 2.7 | 10.4 | 14.0 | 3.2 |
| **exo(100,60):base** | 96 | 58 / 478 | 1792 | 34.1 | 8.3 | 11.2 | 8.2 | 8.9 | 13.8 | 13.6 | 3.3 | 3.4 | 2.8 | 2.7 | 2.8 | 2.6 | 5.1 | 2.9 | 3.1 | 14.7 | 42.3 | 3.3 |
| **exo(100,120):base** | 97 | 113 / 826 | 3584 | 40.7 | 9.5 | 12.4 | 9.6 | 8.8 | 14.4 | 14.7 | 1.8 | 1.6 | 1.7 | 1.8 | 1.8 | 1.8 | 3.6 | 1.9 | 1.9 | 15.9 | 40.7 | 1.8 |
| **exo(150,10):base** | 142 | 10 / 93 | 224 | 7.7 | 5.9 | 6.3 | 5.8 | 9.4 | 8.5 | 8.4 | 4.2 | 4.1 | 4.2 | 4.1 | 4.3 | 4.7 | 8.5 | 4.3 | 4.2 | 9.6 | 6.3 | 4.4 |
| **exo(150,30):base** | 142 | 30 / 264 | 896 | 15.6 | 7.6 | 10.6 | 7.7 | 9.3 | 13.8 | 13.9 | 4.4 | 3.8 | 3.4 | 3.1 | 3.2 | 3.5 | 7.0 | 3.6 | 3.7 | 15.7 | 31.7 | 4.0 |
| **exo(150,60):base** | 144 | 59 / 498 | 1792 | 36.2 | 9.7 | 14.9 | 9.6 | 9.7 | 18.7 | 18.2 | 3.3 | 3.1 | 2.9 | 2.9 | 2.9 | 2.9 | 5.8 | 3.0 | 3.0 | 20.0 | 45.0 | 3.2 |
| **exo(300,10):base** | 281 | 10 / 97 | 224 | 7.1 | 5.6 | 7.1 | 5.3 | 8.9 | 10.2 | 9.7 | 4.0 | 3.8 | 3.5 | 3.5 | 3.8 | 4.1 | 8.1 | 3.5 | 3.7 | 12.9 | 8.6 | 3.7 |
| **exo(300,30):base** | 287 | 30 / 277 | 896 | 14.8 | 8.3 | 12.6 | 8.2 | 9.1 | 17.0 | 17.0 | 3.7 | 3.4 | 3.1 | 3.1 | 3.2 | 3.4 | 7.1 | 3.2 | 3.3 | 20.8 | 47.1 | 3.5 |
| **donchian:base** | 159 | 23 / 99 | 224 | 7.6 | 6.3 | 8.5 | 6.3 | 8.5 | 10.4 | 9.8 | 2.9 | 2.9 | 2.9 | 2.9 | 3.3 | 3.6 | 7.4 | 2.7 | 2.6 | 18.0 | 7.0 | 3.0 |
| **tsmom:base** | 189 | 20 / 200 | 448 | 13.2 | 8.9 | 11.2 | 9.1 | 9.8 | 13.4 | 13.5 | 1.5 | 1.3 | 1.5 | 1.6 | 1.7 | 2.1 | 5.1 | 1.6 | 1.3 | 17.1 | 12.4 | 1.5 |
| exo(50,10):bear | 48 | 11 / 85 | 224 | 7.8 | 5.4 | 4.9 | 5.2 | 9.1 | 5.4 | 5.2 | 4.0 | 3.9 | 3.9 | 3.5 | 4.1 | 4.6 | 8.5 | 3.9 | 3.9 | 5.7 | 5.3 | 3.9 |
| exo(50,30):bear | 48 | 30 / 240 | 896 | 14.2 | 5.4 | 6.1 | 5.5 | 8.0 | 6.9 | 6.9 | 3.7 | 3.4 | 3.3 | 3.2 | 2.9 | 3.2 | 6.6 | 3.4 | 3.3 | 7.4 | 8.6 | 3.7 |
| exo(50,60):bear | 48 | 59 / 450 | 1792 | 27.2 | 6.0 | 7.1 | 6.3 | 7.5 | 7.9 | 8.1 | 2.9 | 2.8 | 2.8 | 2.7 | 2.7 | 2.9 | 4.9 | 2.7 | 2.7 | 8.7 | 20.6 | 2.9 |
| exo(50,120):bear | 48 | 113 / 761 | 1792 | 39.3 | 7.1 | 8.6 | 7.6 | 7.9 | 9.6 | 9.7 | 2.3 | 2.4 | 2.3 | 2.2 | 2.1 | 2.1 | 3.8 | 2.2 | 2.2 | 10.0 | 38.0 | 2.5 |
| **exo(100,10):bear** | 96 | 11 / 90 | 224 | 7.6 | 5.7 | 5.3 | 5.6 | 8.7 | 6.9 | 6.9 | 3.9 | 3.7 | 3.4 | 3.5 | 4.0 | 4.7 | 7.9 | 3.6 | 3.5 | 7.5 | 5.2 | 3.7 |
| **exo(100,30):bear** | 95 | 30 / 257 | 896 | 17.1 | 6.1 | 8.0 | 5.9 | 8.2 | 10.2 | 10.2 | 3.7 | 3.3 | 3.3 | 3.3 | 3.4 | 3.7 | 6.2 | 3.3 | 3.3 | 11.0 | 14.1 | 3.6 |
| **exo(100,60):bear** | 96 | 58 / 481 | 1792 | 32.5 | 7.4 | 10.6 | 7.3 | 7.5 | 12.7 | 12.7 | 3.1 | 3.0 | 3.0 | 2.7 | 2.6 | 2.7 | 4.3 | 3.0 | 2.8 | 13.8 | 41.6 | 3.0 |
| **exo(100,120):bear** | 96 | 113 / 836 | 3584 | 42.0 | 9.1 | 12.7 | 9.1 | 7.8 | 15.6 | 15.4 | 2.5 | 2.3 | 2.2 | 2.3 | 2.2 | 2.3 | 3.1 | 2.4 | 2.3 | 16.8 | 42.0 | 2.5 |
| **exo(150,10):bear** | 143 | 10 / 93 | 224 | 7.5 | 5.7 | 6.0 | 5.5 | 8.7 | 8.1 | 8.1 | 4.1 | 3.8 | 3.7 | 3.5 | 3.8 | 4.6 | 8.2 | 4.0 | 4.0 | 9.2 | 5.5 | 3.9 |
| **exo(150,30):bear** | 143 | 30 / 265 | 896 | 12.4 | 5.7 | 8.4 | 5.8 | 6.7 | 12.3 | 12.0 | 3.5 | 3.4 | 3.1 | 3.3 | 3.3 | 3.3 | 5.4 | 3.2 | 3.3 | 13.1 | 30.3 | 3.4 |
| **exo(150,60):bear** | 144 | 59 / 502 | 1792 | 33.9 | 7.0 | 11.5 | 7.1 | 6.9 | 14.6 | 14.5 | 2.7 | 2.5 | 2.7 | 2.4 | 2.3 | 2.2 | 4.1 | 2.5 | 2.6 | 16.0 | 43.4 | 2.7 |
| **exo(300,10):bear** | 282 | 10 / 96 | 224 | 7.8 | 6.2 | 7.5 | 6.1 | 9.1 | 11.4 | 11.0 | 4.6 | 4.3 | 4.1 | 4.2 | 4.1 | 4.4 | 8.1 | 4.5 | 4.2 | 14.5 | 8.9 | 4.5 |
| **exo(300,30):bear** | 287 | 30 / 276 | 896 | 11.7 | 6.3 | 11.1 | 6.7 | 6.8 | 15.1 | 14.8 | 3.2 | 2.8 | 2.7 | 2.3 | 2.4 | 2.5 | 4.9 | 2.9 | 2.7 | 18.5 | 44.7 | 2.8 |
| **donchian:bear** | 160 | 24 / 103 | 224 | 7.5 | 6.2 | 8.3 | 6.2 | 8.2 | 10.2 | 9.5 | 3.2 | 3.3 | 3.1 | 3.0 | 2.9 | 3.6 | 7.0 | 3.2 | 3.3 | 18.8 | 7.7 | 3.4 |
| **tsmom:bear** | 186 | 21 / 219 | 448 | 12.9 | 8.7 | 11.1 | 8.6 | 9.1 | 13.1 | 13.1 | 1.3 | 1.4 | 1.3 | 1.6 | 1.6 | 2.0 | 4.4 | 1.3 | 1.2 | 16.8 | 12.0 | 1.3 |
| stress exo(150,30):regime | 143 | 30 / 267 | 896 | 15.5 | 9.4 | 12.3 | 9.2 | 11.0 | 15.6 | 15.2 | 5.3 | 5.3 | 5.0 | 4.8 | 4.8 | 5.2 | 8.7 | 5.2 | 5.1 | 16.9 | 31.6 | 5.5 |
| stress exo(50,120):regime | 48 | 114 / 760 | 1792 | 37.5 | 9.1 | 10.7 | 9.3 | 9.3 | 12.1 | 12.0 | 3.5 | 3.6 | 3.6 | 3.5 | 3.4 | 3.3 | 5.1 | 3.5 | 3.5 | 12.3 | 36.4 | 3.7 |
| stress donchian:regime | 157 | 24 / 104 | 224 | 9.2 | 7.9 | 9.9 | 7.8 | 9.6 | 11.4 | 10.9 | 3.6 | 3.6 | 3.4 | 3.3 | 4.5 | 5.0 | 8.2 | 3.1 | 3.3 | 21.0 | 8.8 | 3.6 |

Bold: deciding cells. "§6.0 L" is the rule's median block length in that cell. Every cell's per-run ranges are in `tables.md`.

### 4.3 Size by block length (table C)

Fixed blocks at N = 1,586 days, over the 22 deciding cells:

| L (days) | Blocks | E: mean size | E: highest cell | M: mean size | M: highest cell |
|---|---|---|---|---|---|
| 1 | 1586 | – | – | 3.3 | 4.6 |
| 7 | 227 | – | – | 3.1 | 4.3 |
| 14 | 114 | 11.0 | 16.9 | 3.0 | 4.2 |
| 28 | 57 | 9.5 | 14.9 | 2.9 | 4.2 |
| 56 | 29 | 8.1 | 12.1 | 3.0 | 4.3 |
| 112 | 15 | 7.0 | 9.6 | 3.3 | 4.9 |
| 224 | 8 | 7.0 | 8.6 | 4.2 | 6.3 |
| 448 | 4 | 8.5 | 9.8 | 6.2 | 8.5 |
| 896 | 2 | 13.2 | 15.5 | 11.1 | 14.6 |

- **The marked series is flat from 1 to 56 days.** It then rises as blocks become few: 8 blocks add about 1 point, 4 blocks 3 points and 2 blocks 8 points.
- That is the (1 − 1 ÷ K) effect. At two blocks the bootstrap's standard deviation is about 70% of the truth, and a normal test would reject about 12% of the time; 11.1% was observed.
- The entry-day series is too narrow at every length: short blocks cut overlapping trades apart, and long ones leave too few blocks.

### 4.4 Family-wise error under Holm (table D)

Holm at 5% over four members, all null:
- A, a strategy;
- A with a random 30% of its entries vetoed;
- B, a second strategy on the same days;
- B with 30% vetoed.

The members' θ̂ correlate: A with A-veto 0.90 to 1.00, A with B 0.80 to 0.81. Pooled figures, with per-run ranges:

| Method | exo(150,30):base | exo(100,60):bear | donchian+tsmom:bear |
|---|---|---|---|
| E-rule | 17.1 (15.7–19.0) | 45.3 (42.3–48.3) | 11.8 (10.7–13.0) |
| E-rule-cap | 4.7 (3.3–6.0) | 5.0 (2.7–6.7) | 5.3 (4.0–6.7) |
| E-28 | 6.1 (4.7–7.7) | 6.9 (4.3–9.0) | 7.3 (5.7–8.3) |
| E-112 | 4.6 (3.0–5.7) | 5.0 (3.3–6.3) | 5.2 (3.7–6.3) |
| E-448 | 8.2 (6.7–10.3) | 7.0 (5.3–9.0) | 7.2 (6.3–8.3) |
| E-PW | 9.6 (7.3–11.3) | 9.2 (6.0–12.3) | 9.1 (8.0–10.7) |
| E-SB | 9.5 (7.3–11.7) | 9.3 (6.3–14.0) | 8.7 (7.7–10.0) |
| M-1 | 1.7 (1.0–2.7) | 1.3 (0.3–2.3) | 0.6 (0.0–1.3) |
| M-7 | 1.3 (0.7–2.0) | 1.0 (0.3–2.0) | 0.7 (0.0–1.7) |
| **M-14** | **1.0 (0.3–1.7)** | **1.0 (0.3–2.0)** | **0.8 (0.3–1.3)** |
| M-28 | 0.9 (0.3–1.3) | 0.9 (0.3–1.7) | 0.7 (0.0–1.3) |
| M-56 | 1.0 (0.3–2.3) | 0.8 (0.0–2.0) | 0.9 (0.3–1.7) |
| M-112 | 1.4 (0.7–3.0) | 1.0 (0.0–2.0) | 1.2 (0.7–2.3) |
| M-448 | 5.6 (4.0–7.3) | 3.5 (2.0–5.7) | 4.3 (3.7–6.0) |
| M-PW | 1.3 (0.7–2.3) | 1.0 (0.3–2.3) | 0.6 (0.0–1.7) |
| M-SB | 1.2 (0.0–2.0) | 1.2 (0.3–2.3) | 0.6 (0.0–1.7) |
| T-iid | 10.7 (8.7–12.7) | 9.8 (7.0–14.3) | 14.6 (12.0–17.3) |
| T-episode | 44.5 (40.7–49.3) | 52.5 (46.0–55.7) | 10.5 (9.0–12.0) |
| NW | 1.4 (1.0–2.0) | 1.4 (0.7–2.3) | 0.6 (0.0–1.3) |

- Holm controls the family-wise error whatever the dependence, if each member's p-value is valid. With anti-conservative members it does not.
- **Correlated members make Holm conservative,** as with the marked methods: four tests that move together reject together, and Holm pays for four.

### 4.5 Power (tables E and F)

Power against the standardised effect λ = δ ÷ SD₀, mean over the deciding cells:

| Method | λ = 1.0 | λ = 2.0 | λ = 2.5 | λ = 3.0 | λ = 4.0 |
|---|---|---|---|---|---|
| E-rule | 58 | 90 | 96 | 99 | 100 |
| E-28 | 50 | 90 | 96 | 99 | 100 |
| E-112 | 44 | 87 | 95 | 98 | 100 |
| M-1 | 26 | 73 | 89 | 96 | 99 |
| M-7 | 26 | 74 | 89 | 96 | 99 |
| **M-14** | **26** | **75** | **90** | **96** | **99** |
| M-28 | 27 | 76 | 90 | 97 | 100 |
| M-56 | 28 | 77 | 91 | 97 | 100 |
| M-112 | 30 | 79 | 92 | 97 | 100 |
| M-448 | 39 | 84 | 94 | 98 | 100 |
| M-PW | 26 | 74 | 90 | 96 | 100 |
| M-SB | 26 | 75 | 90 | 97 | 100 |
| T-iid | 60 | 93 | 98 | 99 | 100 |
| T-episode | 62 | 88 | 94 | 97 | 99 |
| NW | 26 | 74 | 90 | 96 | 99 |
| ideal (normal) | 26 | 64 | 80 | 91 | 99 |

M-14 against absolute effects, in return per capital-day:

| Cell | SD₀ | δ = 0.025% | δ = 0.05% | δ = 0.10% | δ = 0.20% | ideal at 0.10% |
|---|---|---|---|---|---|---|
| exo(100,10):base | 0.148% | 6 | 8 | 14 | 39 | 17 |
| exo(100,30):base | 0.121% | 5 | 8 | 18 | 52 | 21 |
| exo(100,60):base | 0.114% | 5 | 7 | 18 | 62 | 22 |
| exo(100,120):base | 0.115% | 3 | 5 | 15 | 67 | 22 |
| exo(150,10):base | 0.269% | 6 | 9 | 18 | 44 | 10 |
| exo(150,30):base | 0.112% | 6 | 9 | 20 | 60 | 23 |
| exo(150,60):base | 0.104% | 5 | 8 | 21 | 67 | 25 |
| exo(300,10):base | 0.118% | 6 | 9 | 20 | 54 | 21 |
| exo(300,30):base | 0.099% | 6 | 9 | 23 | 68 | 26 |
| donchian:base | 0.214% | 4 | 5 | 10 | 26 | 12 |
| tsmom:base | 0.225% | 2 | 3 | 6 | 22 | 12 |
| exo(100,10):bear | 0.163% | 5 | 7 | 13 | 33 | 15 |
| exo(100,30):bear | 0.140% | 5 | 8 | 16 | 46 | 18 |
| exo(100,60):bear | 0.127% | 4 | 7 | 14 | 50 | 20 |
| exo(100,120):bear | 0.121% | 3 | 5 | 12 | 56 | 21 |
| exo(150,10):bear | 0.142% | 6 | 8 | 15 | 40 | 17 |
| exo(150,30):bear | 0.119% | 5 | 7 | 16 | 51 | 21 |
| exo(150,60):bear | 0.122% | 4 | 6 | 15 | 54 | 21 |
| exo(300,10):bear | 0.134% | 6 | 9 | 19 | 49 | 18 |
| exo(300,30):bear | 0.148% | 4 | 7 | 17 | 56 | 17 |
| donchian:bear | 0.241% | 4 | 5 | 8 | 22 | 11 |
| tsmom:bear | 0.225% | 2 | 3 | 5 | 16 | 11 |

- **Power is low.** An edge of 0.10% per capital-day (36.5% a year on the capital in use) is found 5% to 23% of the time over 4.3 years.
- For the two strategy rules, the chance was 16% to 26% even at 0.20% per capital-day.
- **"Too few trades to tell" will remain the usual answer** for daily strategies (FDS-SR-001 §6.5).
- SD₀ is inflated in a few cells (exo(150,10):base, the strategy cells) by rare replications with an extreme rally. There the standardised λ overstates the absolute effect, and the absolute table is the one to read.

### 4.6 Why each method behaves as it does (table K, post-hoc diagnostics)

These figures explain the results; they did not decide anything.
- **Spread ÷ true scale:** the median bootstrap standard deviation over θ̂'s robust scale (interquartile range ÷ 1.349) in the same cell.
- **Correlation:** between a replication's θ̂ and its bootstrap spread.

Medians over the deciding cells:

| Method | Spread ÷ true scale: median (lowest–highest) | Correlation of spread with θ̂: median |
|---|---|---|
| E-rule | 0.62 (0.00–0.89) | +0.37 |
| E-rule-cap | 0.75 (0.51–0.91) | +0.63 |
| E-28 | 0.64 (0.42–0.88) | +0.63 |
| E-112 | 0.75 (0.51–0.91) | +0.63 |
| E-448 | 0.72 (0.53–0.85) | +0.58 |
| E-PW | 0.54 (0.37–0.82) | +0.63 |
| E-SB | 0.54 (0.37–0.82) | +0.63 |
| M-1 | 1.02 (0.95–1.06) | +0.41 |
| **M-14** | **0.99 (0.93–1.04)** | **+0.52** |
| M-28 | 0.97 (0.91–1.03) | +0.55 |
| M-112 | 0.92 (0.85–0.99) | +0.61 |
| M-448 | 0.80 (0.73–0.91) | +0.60 |
| M-PW | 1.00 (0.93–1.05) | +0.54 |
| M-SB | 0.99 (0.93–1.05) | +0.55 |
| T-iid | 0.45 (0.35–0.79) | +0.64 |
| T-episode | 0.81 (0.00–0.97) | +0.26 |
| NW | 1.00 (0.94–1.05) | +0.48 |

- **The marked methods get the spread right.** Their low size comes from the positive correlation: a replication with a high θ̂ also has a wide spread, so it rarely rejects.
- That is how a one-sided upper test behaves on right-skewed data (Johnson 1978; Hall 1992). Here the skew comes from compounding: a winning position's marked value grows, and so do its daily moves.
- The effect is strongest when positions are held most of the time: exo(100,120) is in the market 94% of coin-days, and TSMOM holds through long trends.

### 4.7 The not-assessable floor (table G)

M-14 over shorter windows; size at nominal 5%, pooled (runs):

| Window (days) | Blocks of 14 days | exo base | donchian base | exo bear | donchian bear |
|---|---|---|---|---|---|
| 183 | 14 | 4.1 (2.7–5.7) | 4.1 (2.3–5.7) | 5.9 (3.7–8.0) | 3.3 (2.0–6.0) |
| 274 | 20 | 4.4 (2.0–5.7) | 3.3 (1.7–4.7) | 5.6 (3.7–8.3) | 3.6 (1.7–6.0) |
| 365 | 27 | 3.5 (1.0–5.7) | 3.6 (2.3–4.3) | 5.2 (2.7–7.7) | 3.8 (2.0–5.3) |
| 549 | 40 | 3.5 (2.3–5.7) | 3.3 (1.7–4.7) | 5.4 (3.0–8.0) | 3.0 (1.7–4.3) |
| 731 | 53 | 3.7 (2.3–5.0) | 2.7 (1.3–4.3) | 4.5 (2.3–7.0) | 3.0 (2.3–4.7) |
| 1586 | 114 | 3.1 (2.0–4.7) | 2.9 (2.0–4.0) | 2.7 (1.3–4.0) | 3.1 (1.7–4.7) |

- **The pre-stated rule gives the floor at the grid's shortest window:** 183 days, 14 blocks.
- The study did not find a window where M-14 fails. Shorter windows were not tested, so the floor is set there, not below.
- **The bear cells** are within the band, but rise as the window shortens: 5.9% at 183 days. A short window that falls wholly inside or outside a bear market holds one regime, and resampling cannot see across regimes (§4.9).
- **In practice the F3 trade floor binds first.** 100 trades and 30 in each half take a year or more for daily strategies on 11 coins. The share of replications meeting it was 29% to 39% in the n = 100 cells, and 100% for the others.

### 4.8 The real-implementation check (table H)

`bootstrap.test_statistic` unchanged (10 runs of 1,000, `random()`, the pooled p), against the study's fast version (B = 1,000, numpy starts), on the same replications:

| Cell | Replications | Method | Size, real | Size, fast | Same decision | Mean abs. p difference |
|---|---|---|---|---|---|---|
| exo(150,30):base | 200 | E-rule | 15.0 | 15.5 | 99.5 | 0.0070 |
| exo(150,30):base | 200 | E-28 | 12.0 | 12.5 | 99.5 | 0.0077 |
| exo(150,30):base | 200 | M-14 | 1.5 | 2.0 | 99.5 | 0.0113 |
| exo(150,30):base | 200 | M-28 | 3.0 | 2.5 | 99.5 | 0.0101 |
| exo(150,30):base | 200 | M-56 | 2.0 | 2.5 | 98.5 | 0.0117 |
| exo(150,30):base | 200 | M-112 | 3.0 | 3.5 | 99.5 | 0.0103 |
| exo(100,60):bear | 200 | E-rule | 29.5 | 29.5 | 100.0 | 0.0021 |
| exo(100,60):bear | 200 | E-28 | 8.5 | 8.5 | 98.0 | 0.0071 |
| exo(100,60):bear | 200 | M-14 | 1.5 | 1.5 | 99.0 | 0.0109 |
| exo(100,60):bear | 200 | M-28 | 1.0 | 1.0 | 100.0 | 0.0110 |
| exo(100,60):bear | 200 | M-56 | 2.0 | 2.0 | 100.0 | 0.0105 |
| exo(100,60):bear | 200 | M-112 | 2.0 | 2.5 | 99.5 | 0.0102 |
| donchian:bear | 200 | E-rule | 9.5 | 8.5 | 99.0 | 0.0094 |
| donchian:bear | 200 | E-28 | 9.5 | 11.0 | 98.5 | 0.0075 |
| donchian:bear | 200 | M-14 | 2.0 | 3.0 | 99.0 | 0.0108 |
| donchian:bear | 200 | M-28 | 2.0 | 2.0 | 100.0 | 0.0102 |
| donchian:bear | 200 | M-56 | 4.0 | 4.0 | 99.0 | 0.0116 |
| donchian:bear | 200 | M-112 | 5.0 | 5.0 | 100.0 | 0.0098 |

The decisions agree in 98% to 100% of replications. The differences are the draws' noise at B = 1,000.

### 4.9 Stress: persistent drift regimes

In the regime cells (table B, last rows):
- **M-14's size was 3.4% to 5.0%.** E-rule's was 9.2% to 37.5%, E-28's 9.9% to 12.3%, and T-iid's 12.3% to 21.0%.
- The marked methods held here, but this is one stress model with spells of a year on average. Under longer or stronger regimes the variance of any 4.3-year estimate is dominated by a handful of spells.
- No resampling of one history can estimate that. It is a limit of one market history (FDS-SR-001 §9 item 4), not something a block rule can fix.

### 4.10 Run by run (table J)

M-14:

| Run | Mean size | Highest size | Cells outside [2.5%, 7.5%] | Lowest power at λ = 2.5 | Mean power at λ = 2.5 | Highest FWER |
|---|---|---|---|---|---|---|
| 0 | 2.9 | 5.0 | 10 of 22 | 81 | 89 | 1.0 |
| 1 | 2.8 | 4.3 | 5 of 22 | 82 | 90 | 1.3 |
| 2 | 3.0 | 5.3 | 8 of 22 | 80 | 90 | 2.0 |
| 3 | 3.1 | 5.7 | 9 of 22 | 79 | 90 | 1.3 |
| 4 | 3.2 | 5.7 | 7 of 22 | 82 | 90 | 1.0 |
| 5 | 3.0 | 5.7 | 8 of 22 | 82 | 89 | 1.7 |
| 6 | 3.0 | 6.0 | 9 of 22 | 83 | 91 | 1.3 |
| 7 | 3.1 | 5.7 | 9 of 22 | 81 | 90 | 1.3 |
| 8 | 3.0 | 5.0 | 6 of 22 | 83 | 90 | 1.0 |
| 9 | 3.0 | 5.3 | 9 of 22 | 78 | 90 | 1.0 |

The §6.0 rule (E-rule):

| Run | Mean size | Highest size | Cells outside [2.5%, 7.5%] | Lowest power at λ = 2.5 | Mean power at λ = 2.5 | Highest FWER |
|---|---|---|---|---|---|---|
| 0 | 17.1 | 38.7 | 17 of 22 | 87 | 96 | 42.7 |
| 1 | 17.3 | 42.7 | 16 of 22 | 85 | 96 | 42.3 |
| 2 | 18.7 | 46.3 | 16 of 22 | 86 | 96 | 42.3 |
| 3 | 17.5 | 43.3 | 17 of 22 | 86 | 96 | 44.7 |
| 4 | 17.2 | 37.7 | 20 of 22 | 88 | 96 | 45.3 |
| 5 | 17.8 | 44.3 | 19 of 22 | 88 | 96 | 47.3 |
| 6 | 18.8 | 44.7 | 18 of 22 | 87 | 96 | 46.0 |
| 7 | 18.5 | 43.0 | 20 of 22 | 85 | 95 | 47.0 |
| 8 | 18.2 | 43.0 | 20 of 22 | 87 | 96 | 48.3 |
| 9 | 18.0 | 44.7 | 18 of 22 | 83 | 96 | 47.3 |

- With 300 replications a cell, a single run's size has a standard error of about 1.3 points. So M-14's single runs stray outside the band by chance, mostly below it; the decision uses the pooled 3,000.
- The §6.0 rule's runs agree with each other: it is anti-conservative in every run.

## 5. What each method gets wrong

- **E-rule (§6.0 as written).** The block length follows the longest 1% of trades. That gave 224 days for 10-day median holds and 896 to 3,584 days for 30 to 120. With one or two blocks the bootstrap's spread collapses:
  - size 7.1% to 42.0%, Holm FWER up to 45%;
  - its intervals covered the true value in 0% of replications where L ≥ N, because every draw equals the estimate.
- **E-rule-cap and fixed entry-day blocks (14 to 896 days).** A trade's whole profit sits on its entry day, so overlapping trades fall into different blocks although they share market days.
  - Short blocks cut them apart; long blocks leave too few. Every length was anti-conservative somewhere (worst cells 8.6% to 16.9%).
  - 90% intervals covered as little as 50% to 64% of the time.
- **E-PW and E-SB.** Politis–White reads individual autocorrelations of the entry-day series. Each is small, though together they matter, so it picks short blocks: worst cells 18.2% to 18.7%.
- **M with 448 or 896-day blocks.** Too few blocks: the (1 − 1 ÷ K) shortfall (worst cells 8.5% and 14.6%).
- **M with 1 to 224-day blocks, M-PW, M-SB and the NW reference.** They hold the error rate (at most 4.9%, and 6.3% at 224 days), but are conservative where profits are right-skewed and positions are held most of the time (1.2% to 2.5% in exo(100,120) and the TSMOM cells). They lose some power there, never error control.
  - Their 90% intervals covered 79.5% to 91.3% in the worst cells. Coverage falls as L grows: 87.6% for M-14 and 84.7% for M-112 (basic).
- **T-iid.** It treats trades as independent. Trades open on the same days share the common factor, so the spread is half the truth: size 7.2% to 20.8%, rising with overlap.
- **T-episode.** Joining overlapping trades into episodes is right in principle. But with 11 coins and holds of a month or more the episodes merge, and in 13 of the 22 deciding cells the fewest episodes in a replication was one.
  - With one episode every draw equals the estimate: size up to 47.1%, Holm FWER up to 52.5%.
  - It works only when positions rarely overlap (exo(100,10), with 37 episodes on average).
- **The percentile interval with the centred p-value.** The implementation's percentile interval and its centred p-value invert different things. Under skew they disagree: up to 2.8% of replications for M-14, and 26.6% for T-episode. The basic interval, 2θ̂ minus the draws' quantiles, is the one the centred p-value inverts.

## 6. The outcome of the pre-stated rule

1. **Valid methods:** none. No bootstrap had size within [2.5%, 7.5%] in all 22 deciding cells:
   - every entry-day and trade-level method exceeded 7.5% somewhere;
   - every marked method with blocks up to 224 days fell below 2.5% somewhere: M-14 in 4 cells, M-28 in 6;
   - M-448 and M-896 exceeded 7.5%.
2. **The fallback** (pre-statement §8 item 5) selects the method whose largest size is smallest, provided it is at most 10%. That is **M-14, at 4.20%.**
   - M-28 and M-SB both had 4.23%: one replication in 3,000. M-7 had 4.27%, M-56 4.30%, M-PW 4.47% and M-1 4.60%.
   - **The study cannot tell blocks of 7 to 56 days apart.** Lowest power at λ = 2.5 was 82% for M-14 against 83% for M-28, and Holm FWER at most 1.0% against 0.9%.
3. **The pre-stated wording** is that the selected method is "the least anti-conservative option, not a valid one". Precisely: M-14 never exceeded nominal 5% (at most 4.2%; Holm FWER at most 1.0%). It is outside the band only on the conservative side, in the four cells named in §4.6.
4. **The interval** (item 6): the basic interval. Its worst 90% coverage was 87.6%, against the percentile interval's 86.4%, and it agrees with "p ≤ 5%" by construction.
5. **The floor** (item 7): at least 14 blocks of 14 days, the shortest window tested (183 days). FDS-SIG-004 F3's trade floor still applies and binds first in practice.

**For the owner's decision** (amendment decision AM1-D2):
- Within FDS-SR-001 the day-block bootstrap decides only path statistics. M-14 would therefore be the one scheme for FDS-SR-001's deciding tests.
- FDS-SR-001's forecast figures come from FDS-SIG-004's and FDS-MH-001's tools, with 28-day blocks that keep their 14-day labels together. They are shown, not deciding, and are not changed.
- Choosing M-28 instead would give one block length across all three specs, at no measurable cost in this study. Either choice is blind to any strategy's results.
- The pre-stated rule did not consider this alignment.

## 7. Deviations from the pre-statement

1. **Floor windows of 1,586 days reuse the matching core cells,** exo(300, 30) and donchian on base and bear, rather than new replications of the same design. This saved time and has no effect on the result.
2. **The stationary bootstrap is drawn day by day when its mean block is under 8 days,** and block by block otherwise. The scheme is the same; a self-check compares the two forms.
3. **The diagnostics of §4.6** (`sr1_bootstrap_diagnostics.py`) were added after the results, to explain them. They decide nothing.
4. **The size-band fallback** was written with anti-conservative failures in mind. It was applied as written, although the failures here are on the conservative side (§6).
5. **File names.** The pre-statement names `results.json` and `REPORT.md`.
   - The results are committed as `results.json.gz`, the script's exact output gzipped (8.7 MB unpacked), as FDS-SIG-004's run did.
   - This file is `STUDY.md` because the tooling refused the name `REPORT.md` from a subagent.

## 8. Limits of this study

- **Synthetic data, one family of market models:**
  - daily simple returns with a GARCH-t common factor;
  - one bear-market model and one regime model;
  - no serial correlation of returns other than the regimes;
  - no jumps beyond the t₄ tails.
- **Simplified trades:**
  - fills at the decision day's close;
  - one unit a trade, not 1% of equity;
  - no minimum entry, lot sizes, coin budget or halt.

  The statistic is scale-free, and these change which trades occur, not how they are resampled.
- **The exo holding times are independent of returns.** The STRAT-004 and STRAT-005 cells cover path-dependent exits.
- **Only one kind of alternative:** a constant edge per capital-day. An edge concentrated in one regime or one coin was not simulated.
- **B = 1,000 draws a replication** against the implementation's 10 × 1,000. The check in §4.8 agreed on 98% to 100% of decisions.
- **The choice among marked methods of 7 to 56 days is within noise** (§6 item 2).
- **Right-skewed profits make every valid test here conservative.** A studentised (bootstrap-t) version might recover some power. It was not in the pre-statement and was not tested.

## 9. Runtime and reproduction

- **The run:** 6,903 seconds (1 h 55 min), 14 worker processes on 8 cores, 2026-11-08. The diagnostics took 8 seconds.
- **To reproduce,** from the repository root, with `$PY` a Python with numpy, `PYTHONNOUSERSITE=1`, and `POWERTRADER_HOME`, `APPDATA` and `LOCALAPPDATA` pointing at a scratch folder:

```
"$PY" docs/dev/sr1_bootstrap_study.py <out-dir> --jobs 14
"$PY" docs/dev/sr1_bootstrap_diagnostics.py <out-dir> <out-dir>/diagnostics.json
"$PY" docs/dev/sr1_bootstrap_report_tables.py <out-dir>/results.json
```

- Every number is a function of the seeds (run r: 20261108 + r; oracle and bootstrap draws on their own seed streams).
- The script refuses to resume from saved parts made by a different version of itself.
- **The script that ran.** It hashes its own file to tie its saved parts to its text. The run's stamp was `684cb71133df2b860b353e5a5e7b00ee8ba46746dfc332c4b1b560287999edf3`, from the Windows checkout, where `core.autocrlf` gives the file CRLF line endings.
  - The committed text, with LF endings, hashes to `388144c1577e838afc46e13b2637d07ec422a774302354f64cdcbb21cd262e69`.
  - The two differ only in line endings. So a rerun on a checkout that keeps LF endings starts a fresh parts folder.
- On Windows the table reader needs `PYTHONIOENCODING=utf-8`, because its tables print λ and θ̂.

## References

- Berger, R. L. (1982). Multiparameter hypothesis testing and acceptance sampling. *Technometrics* 24(4), 295–300.
- Bradley, J. V. (1978). Robustness? *British Journal of Mathematical and Statistical Psychology* 31, 144–152.
- Hall, P. (1992). *The Bootstrap and Edgeworth Expansion.* Springer.
- Hall, P., and Wilson, S. R. (1991). Two guidelines for bootstrap hypothesis testing. *Biometrics* 47(2), 757–762.
- Holm, S. (1979). A simple sequentially rejective multiple test procedure. *Scandinavian Journal of Statistics* 6(2), 65–70.
- Johnson, N. J. (1978). Modified t tests and confidence intervals for asymmetrical populations. *Journal of the American Statistical Association* 73(363), 536–544.
- Künsch, H. R. (1989). The jackknife and the bootstrap for general stationary observations. *Annals of Statistics* 17(3), 1217–1241.
- Lahiri, S. N. (2003). *Resampling Methods for Dependent Data.* Springer.
- Ledoit, O., and Wolf, M. (2008). Robust performance hypothesis testing with the Sharpe ratio. *Journal of Empirical Finance* 15(5), 850–859.
- Newey, W. K., and West, K. D. (1987). A simple, positive semi-definite, heteroskedasticity and autocorrelation consistent covariance matrix. *Econometrica* 55(3), 703–708.
- Patton, A., Politis, D. N., and White, H. (2009). Correction to "Automatic block-length selection for the dependent bootstrap". *Econometric Reviews* 28(4), 372–375.
- Politis, D. N., and Romano, J. P. (1992). A circular block-resampling procedure for stationary data. In *Exploring the Limits of Bootstrap*, Wiley, 263–270.
- Politis, D. N., and Romano, J. P. (1994). The stationary bootstrap. *Journal of the American Statistical Association* 89(428), 1303–1313.
- Politis, D. N., and White, H. (2004). Automatic block-length selection for the dependent bootstrap. *Econometric Reviews* 23(1), 53–70.
- White, H. (2000). A reality check for data snooping. *Econometrica* 68(5), 1097–1126.
