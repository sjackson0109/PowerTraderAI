# SR-001 long-holding resampling study: pre-statement

**Written:** 2026-11-08, before the study script existed and before any simulation output. It is committed on its own, ahead of the script, so that the order can be checked in git.
**Authority:** the owner's instruction of 2026-11-08 to review resampling methods for long-holding strategies and recommend a replacement for FDS-SR-001 §6.0's long-trade block rule, supported by simulation. Research and documentation only.
**Script:** `docs/dev/sr1_bootstrap_study.py` (to be written). **Results:** `results.json` and `REPORT.md` in this folder.

## 1. Blinding

- The grids below (trade counts, holding times, effect sizes, market models) were set without looking at E1's results.
- Not opened, read or searched: anything under `docs/dev/sr1-e1/`, the M5c section of `docs/dev/RUN-LOG-sr-1.md`, the backlog section after it, and any file reporting E1's figures.
- **Disclosure.** The working notes loaded into this session contain one line about E1: that its period gave 896-day blocks under §6.0 (also stated in the owner's brief) and that its two economic members did not pass. No E1 figure (p-value, profit, trade count or holding time) was seen.
- The method is chosen by the mechanical rule in §8, on synthetic data only. Nothing here is fitted to E1's trades.

## 2. What is tested

- **The statistic:** return per capital-day, θ̂ = Σ net ÷ Σ capital-days, where a trade's capital-days are its amount × days held.
- **The test:** H₀: θ ≤ 0 against θ > 0, one-sided, by the centred p-value p = (1 + #{b : θ*_b − θ̂ ≥ θ̂}) ÷ (B + 1), as in `signal_fusion.evaluation.bootstrap`. A test rejects when p ≤ α (Holm's convention in `model_lab.stats`).
- **Intervals:** the implementation's percentile intervals (90% and 95%), and the basic interval 2θ̂ − (upper, lower quantile), which is the interval the centred p-value inverts.
- **Draws:** B = 1,000 per replication, from numpy's PCG64.
  - Every circular day-block method uses the real implementation: `Bootstrap.resampled`, `ratio`, `centred_p` and `interval`, imported from `app/`. Only `Bootstrap.starts` is replaced, by numpy draws, for speed. A self-check confirms that the replaced class gives the same sums as the original for the same start days.
  - A separate check (§7) reruns some methods with the implementation unchanged: its own `random()` draws, 10 runs of 1,000 seeded `seed + r`, the pooled p.

## 3. Methods compared

Two ways of placing a trade's profit and capital-days on days:
- **E (entry day), as today:** each trade's whole net and capital-days sit on its entry day (FDS-SIG-004 §6.0).
- **M (mark to market), proposed for comparison:** each day carries the change in the open positions' marked value that day, and their capital that day. The entry day carries the change from the amount paid to the position's liquidation value at that close, so the round-trip costs are booked once, on the entry day. The exit day carries the rest of the trade's net. The day sums add up exactly to Σ net and Σ capital-days, so θ̂ is the same number under E and M.

| ID | Units | Rule |
|---|---|---|
| E-rule | entry days | §6.0 as written: L = 28 × 2^k, k the smallest ≥ 0 with at most 1% of the trades longer than L ÷ 2 days. No cap |
| E-rule-cap | entry days | The same, capped at 112 days |
| E-14, E-28, E-56, E-112, E-224, E-448, E-896 | entry days | Fixed L |
| E-PW | entry days | Politis and White (2004), with Patton, Politis and White's (2009) correction, for the circular bootstrap, on the day series of net − θ̂ × capital-days. Rounded, and clipped to 1 to 112 days |
| E-SB | entry days | The stationary bootstrap (Politis and Romano 1994), with mean block length from the same Politis–White estimate for the stationary bootstrap, clipped to 1 to 112 |
| M-1, M-7, M-14, M-28, M-56, M-112, M-224, M-448, M-896 | marked days | Fixed L |
| M-PW | marked days | Politis–White as for E-PW, on the marked series |
| M-SB | marked days | The stationary bootstrap, as for E-SB, on the marked series |
| T-iid | trades | Trades resampled independently with replacement |
| T-episode | episodes | Trades whose holding periods overlap, on any coin, joined into one unit (connected chains of overlap). Episodes resampled with replacement, as many as observed |
| NW (reference only) | marked days | A Newey–West t-test on the marked series, Bartlett weights, lag ⌊4 (N/100)^(2/9)⌋. Not a bootstrap, so not eligible: §6.0 keeps one bootstrap scheme |

Expected before running (stated so that the result can contradict it): T-iid is anti-conservative under common shocks; E-rule and long fixed blocks are anti-conservative when the period holds few blocks; T-episode collapses to a few episodes when positions overlap.

## 4. Data-generating processes

**The period:** N = 1,586 scored days, 11 coins, a 400-day warm-up before it (for the strategy rules and the entry signal). Amounts are 1 unit a trade (the statistic does not depend on scale). Costs: 0.50% taker and 0.05% allowance a fill, through the repository's multiplier m = (1 − f)²(1 − e) ÷ (1 + e). Fills are at the decision day's close.

**Markets** (daily simple returns; values chosen as round numbers, not fitted):
- **base:** a common factor with GARCH(1,1) volatility (α 0.10, β 0.85, unconditional 3.5% a day) and Student-t innovations with 4 degrees of freedom. Coin loadings 0.8 to 1.3, evenly spaced. Each coin adds its own GARCH(1,1)-t₄ noise (α 0.08, β 0.88, 2.0% to 3.5% a day, evenly spaced). Mean zero. Returns below −90% are clipped.
- **bear:** base plus one 365-day bear market, placed uniformly at random on the period's circle. Inside it the factor drifts −0.25% a day and its volatility is 1.5 times higher; elsewhere it drifts +0.0747% a day, so that the drift averages zero over the circle. The warm-up has the bull drift.
- **regime (stress):** base plus a two-state Markov drift: ±0.15% a day, mean spell 365 days in each state, volatility 1.5 times higher in the down state.

**Trades:**
- **exo(n, h):** an entry process independent of future returns.
  - Each coin, when flat, enters with a daily probability whose rate is 3 times higher when the coin's trailing 30-day return is positive than when it is not. This clusters entries across coins, as breakouts cluster.
  - The holding time is drawn at entry: lognormal with median h days and log-standard deviation 1.0 (a heavy right tail; the 99th percentile is about 10 × h), rounded up to whole days, and cut at the period's last day (a forced exit).
  - One position per coin. A coin can re-enter from the day after its exit.
  - The base rate is set so that the expected count is about n: mean gap = 11 N ÷ n − E[hold]. A cell is infeasible, and dropped, if the mean gap would be under 2 days.
  - Grid: n ∈ {50, 100, 150, 300}, h ∈ {10, 30, 60, 120}.
- **donchian:** STRAT-004's rule at its defaults on each coin's simulated closes (enter on a close above the previous 55 closes; exit on a close below the previous 20).
- **tsmom:** STRAT-005's rule at its defaults (30-, 90- and 365-day returns, two of three positive, decided every 7 days).
- Trades entered in the period are scored. Positions open at the last day are closed at its close.

**The null.** For each cell, θ_true = E[Σ net] ÷ E[Σ capital-days] is estimated from 4,000 separate replications. Every trade's net is then reduced by θ_true × its capital-days (and every marked day by θ_true × its capital), so that θ = 0 holds for the cell.

**Alternatives.** The null data plus δ per capital-day on every capital-day. The ratio statistic and every resampling scheme above shift exactly by δ, so power at any δ comes from the null replications' draws. Effects:
- standardised, λ = δ ÷ SD₀, where SD₀ is the standard deviation of θ̂ over the 4,000 oracle replications: λ ∈ {1, 2, 2.5, 3, 4} (λ = 2.5 is where an ideal one-sided 5% test has 80% power);
- absolute: δ ∈ {0.025%, 0.05%, 0.10%, 0.20%} per capital-day.

**Cells:**
- **Core:** every feasible exo(n, h), and donchian and tsmom, each on base and bear.
- **Deciding:** the core cells with n ≥ 100 (the economic test's trade floor, FDS-SIG-004 F3), and the four strategy cells whatever their counts. The n = 50 cells are reported, not deciding.
- **Stress (reported, not deciding):** exo(150, 30), exo(50, 120) and donchian on regime. Reason, stated now: under persistent drift regimes the variance of a 4.3-year estimate is dominated by a handful of regime spells. No resampling of one history can estimate it. The report states what each method does there.
- **Family-wise error (FWER) cells:** exo(150, 30) on base, exo(100, 60) on bear, and donchian on bear. Four members on the same market days: A; A with a random 30% of its entries vetoed; B (a second, independent draw of the same entry process; tsmom in the donchian cell); and B with a random 30% vetoed. Each member gets its own θ_true. Holm at 5% over the four p-values.
- **Floor cells:** exo with the per-day intensity of n = 300 over 1,586 days and h = 30, and donchian, on base and bear, over windows of N ∈ {183, 274, 365, 549, 731, 1,586} days (about 7, 10, 14, 20, 27 and 57 blocks of 28 days). The target count scales with N. For bear, the 365-day bear market is placed at random on a 1,586-day circle and the window is its first N days, so a short window may sit wholly inside or outside it.

## 5. Metrics

For every method and cell, pooled and per run:
- **size:** the share of null replications with p ≤ 5%;
- **coverage** of θ_true by the 90% and 95% percentile and basic intervals;
- **agreement:** the share of replications in which "p ≤ 5%" and "the 90% interval's lower end is above 0" agree, for each interval, under the null and at λ = 2.5;
- **power** at each λ and δ, and the ideal test's power for comparison;
- **effective units:** the number of blocks (⌈N ÷ L⌉, or N ÷ mean length for the stationary bootstrap), episodes or trades: mean and minimum;
- **the block length used**, where it is chosen from the data: mean, minimum and maximum;
- **FWER** under Holm at 5% with four members, and the correlation of the members' θ̂;
- **size by number of blocks**, from the fixed-L methods and the floor cells.

## 6. Replications and seeds

- 10 runs of 300 replications for every cell, run r seeded `20261108 + r`: 3,000 replications a cell, reported pooled and per run.
- The oracle replications use their own seed stream.
- Bootstrap draws are seeded per run, cell, replication and method, so that every number is reproducible.

## 7. The real-implementation check

On exo(150, 30) base, exo(100, 60) bear and donchian bear, 10 runs of 20 replications: E-rule, E-28, M-14, M-28, M-56 and M-112 through `bootstrap.test_statistic` exactly as the code runs it (10 runs of 1,000, `random()`, the pooled p). Reported beside the fast version on the same data, with the share of identical decisions. It checks; it does not decide.

## 8. The selection rule

Fixed now, before any output:
1. **Eligible:** every bootstrap method in §3 (not NW).
2. **Valid:** pooled size within [2.5%, 7.5%] (Bradley's liberal criterion, 0.5α to 1.5α) in every deciding null cell, and Holm FWER at most 7.5% in every FWER cell.
3. **Most powerful:** among the valid methods, the one with the highest minimum power across the deciding cells at λ = 2.5.
4. **Ties:** minimum powers within 1 percentage point are tied. Ties are broken, in order, by:
   - the worst 90% coverage over the deciding null cells closest to 90%, for the interval the amendment would report (item 6);
   - a fixed block length before a data-driven one;
   - the larger minimum number of resampling units.
5. **If no method is valid:** the method whose largest size over the deciding null cells is smallest is reported, provided that size is at most 10%; the amendment then says it is the least anti-conservative option, not a valid one. If even that exceeds 10%, no replacement is recommended.
6. **The reported interval:** the basic interval, which agrees with "p ≤ α" by construction, unless its worst 90% coverage over the deciding null cells is more than 5 points further from 90% than the percentile interval's. Then the percentile interval is kept, and its disagreement rate is stated.
7. **The not-assessable floor:** the smallest number of blocks in the floor study's grid at which the selected method's size is at most 7.5% in every base floor cell, at that window and every longer one. The bear floor cells are reported beside it.
8. The stress cells, the n = 50 cells and the NW reference are reported and never decide.

Deviations from this plan, if any, are listed in the report with their reasons.
