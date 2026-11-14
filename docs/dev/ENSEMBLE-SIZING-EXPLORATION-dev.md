# The Donchian ensemble and volatility sizing on the development months (exploration)

PTAI-RD-001 backlog 3.1 and work package 4.2, run on 2026-11-13. **Exploration only.** These months were already used by E1, the model lab and the nine-coin comparison. Nothing was registered, and nothing here is evidence for trading.

## Verdict

**The ensemble ended ahead of an equal-weight hold, with a much smaller fall. But on one path, the lead in returns cannot be told from chance.**
- **Return:** about 4 points a year ahead in mean daily log return, but the bootstrap's 95% interval runs from −33 to +44 points, and 42% of resamples were at or below zero.
- **Drawdown:** the largest fall was 42% against the hold's 72%. That is one path, untested.
- **Volatility sizing:** it cut every drawdown, but by about as much as the same sizes handed out in random order (5% and 21% of random orders did as well). It also cut the net by two thirds or more.
- **At 50% and 75% a year (§4, added the same day, O18):** no consistent sign that the timing of the sizes helps. Across six comparisons (two strategies, three targets), the share of random orders that fell no further ranged from 5% to 26%, with no pattern by strategy or target. The smallest, 5.0%, is not unusual among six looks (Holm-adjusted, 30%). Sizing also made the ensemble's book worse per unit of drawdown at every target.

## What was run

| | |
|---|---|
| **Coins** | BTC, ETH, XRP, BNB, DOGE, SOL, ZEC, DASH, HYPE: the nine-coin comparison's, from its sandbox's cached public candles. BNB and HYPE are from KuCoin, because Coinbase and Kraken have no bars for them in these months |
| **Period** | 2021-01-01 to 2025-05-06, daily |
| **Account** | £10,000 at 1.3476 = $13,476 |
| **Costs** | 0.50% a side, plus 0.05% slippage a fill; Coinbase's minimums and sell steps |
| **Set-ups** | 1. STRAT-004 (55/20) at the account's own sizing (1% entries, as the app sizes) |
| | 2. STRAT-004 sized to 25% a year volatility (EWMA, λ 0.94) |
| | 3. STRAT-007 (20 days) with OVL-MIDLINE, and the ensemble of 20, 30, 60, 90, 150, 250 and 360 days |
| | 4. Set-up 3 sized to 25% a year volatility |
| **Ensemble sizing** | Each coin gets 1/9 of the account, and each of the 7 members 1/7 of that, sized once at entry. The book never holds more than the account |
| **Random parts** | 10 seeded runs (seeds 700000 to 709000): 200 random entries per seed, through the strategy's own exits, and 200 random orders of the sizes |
| **Trials** | 4 explorations logged in the sandbox's trial log, which then held 80 lines, 34 of them explorations. §4's 4 runs brought it to 84 lines, 38 of them explorations (`compare-ensemble/trials.jsonl`) |
| **Code** | `ptai/combo2` at `2cc9185`, merged locally: #267 to #287, the drawdown and sizing branches (#288, #289), the ensemble branch (#290) without its last commit, and the fixes that became #292 to #297. §4 and the correction below used `main` at `76534a1` with #288 to #297 merged locally |

## 1. The ensemble against an equal-weight hold

Both are fully invested by design, and both are in the same $13,476 account.

| | Net | Compound a year | Largest fall (closes) | Within the bar | Longest below a high | Trades |
|---|---:|---:|---:|---:|---:|---:|
| **Ensemble** | **+$37,648 (+279%)** | **36.0%** | **42.2%** | 47.3%* | 1,031 days (to 2024-03-08) | 630 |
| Equal-weight hold | +$29,095 (+216%) | 30.5% | 72.2% | 75.4% | 1,306 days (to 2024-12-08) | 9 |
| Ensemble, volatility-sized | +$9,381 (+70%) | 13.0% | 22.3% | 23.9%* | 1,031 days | 647 |

\* **Corrected on 2026-11-13** (first published as 45.1% and 22.7%).
- **The cause:** the run's code was the ensemble branch without its last commit, so the ensemble's book took its intrabar peak at the closes. The hold and the strategies took theirs at the earlier bars' highs (O12), so the column compared unlike figures.
- **The fix:** recomputed on the merged code (`compare-ensemble/ensemble_recheck.json`, `ensemble_recheck.py`). Only the intrabar figures changed:
  - the book's drawdowns as above;
  - every member's (not shown in this report);
  - the volatility-sized book's intrabar halt date, from 2021-02-23 to 2021-02-21.
- **Unchanged:** every other figure (net, trades, the close-based falls, the hold) came out identical.

**By calendar year:**

| | 2021 | 2022 | 2023 | 2024 | 2025 (to May 6) |
|---|---:|---:|---:|---:|---:|
| Ensemble | +109% | −12% | +30% | +71% | −7% |
| Equal-weight hold | +209% (from its first entry) | −56% | +33% | +116% | −19% |
| Ensemble, volatility-sized | +29% | −4% | +12% | +26% | −3% |

- **Years at or above 10%:** 3 of 4 whole years for the ensemble; 2 of 3 for the hold, whose 2021 is not whole.
- **Where the gap comes from:** 2022. The ensemble lost 12% where the hold lost 56%.
- **Each member alone** (with the coin's whole 1/9): four of the seven (20, 30, 60 and 360 days) beat the hold's net, and the 90-, 150- and 250-day members did not. Every one fell less than the hold. By days, with trades a coin a year:

| Days | 20 | 30 | 60 | 90 | 150 | 250 | 360 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Net | +$51,694 | +$57,047 | +$36,831 | +$26,211 | +$26,130 | +$21,749 | +$32,924 |
| Largest fall | 36% | 30% | 52% | 64% | 53% | 52% | 49% |
| Trades a coin a year | 6.1 | 4.2 | 2.3 | 1.6 | 1.0 | 0.7 | 0.4 |

  The short members did best here. That is one ranking on one path, and choosing members by it would be fitting the past.
- **Skipped entries:** the ensemble skipped 62 entries because the cash was in other slices that had gained. It sizes once at entry and never re-sizes, as the branch's notes say.

**How sure (`ensemble_difference.py`):**
- the daily log-return difference (book less hold), annualised: +0.041;
- a stationary bootstrap of the days (mean block 20), as 10 seeded runs of 500;
- pooled 95% interval −0.327 to +0.443; 41.5% of resamples at or below zero;
- every run's interval also spans zero (each run is listed in the file).

This is descriptive, not a registered test. The volatility-sized book is −0.144 against the hold (interval −0.637 to +0.373; 70% at or below zero).

## 2. Volatility sizing

| | Net | Largest fall | Mean size | Random orders with a fall at or below this | Random orders with a net at or above this |
|---|---:|---:|---:|---:|---:|
| STRAT-004, account's own | +$3,198 | 5.7% | 1 | | |
| STRAT-004, volatility-sized | +$1,069 | 1.8% | 0.36 | 5.0% (2.5% to 8.0% by seed) | 48% |
| STRAT-007 20 days, own | +$2,630 | 4.3% | 1 | | |
| STRAT-007 20 days, volatility-sized | +$861 | 1.6% | 0.37 | 21.2% (15.5% to 25% by seed) | 47% |

- **Size and fall:** at 25% a year the mean size is 0.37 of the account's own, so these coins' volatility at the entries was about 70% a year (0.25 / 0.37). Most of the smaller fall is simply the smaller size.
- **Drawdown against random orders:** for STRAT-004, 5% of random orders of the same sizes fell no further (2,000 orders, base rate 50%). That is borderline. For STRAT-007, 21% did. This matches the repo's earlier finding for the volatility shrink (Q3, p = 0.69): no reliable drawdown gain beyond what any smaller size gives.
- **Net against random orders:** about half of random orders made as much. Volatility timing added no return.

## 3. Random entries (the strategies alone, at 1% entries)

| | Return per capital-day | Hold's | Random draws at or above, pooled (by seed) |
|---|---:|---:|---:|
| STRAT-004 | 0.61% | 0.19% | 8.7% (5.5% to 12.0%) |
| STRAT-004, volatility-sized | 0.57% | 0.19% | 12.2% (9.5% to 16.5%) |
| STRAT-007 20 days | 0.47% | 0.19% | 4.1% (2.0% to 5.5%) |
| STRAT-007 20 days, volatility-sized | 0.44% | 0.19% | 4.1% (1.5% to 7.5%) |

- **Base rate:** 50% of 2,000 draws would be at or above with no entry skill.
- **STRAT-004:** 8.7% is below that, but this is the nine-coin comparison's strategy on the same months, now looked at again.
- **STRAT-007 at 20 days:** 4.1% is lower, after four set-ups on months used before. No correction is made for these four.

## 4. Higher targets: 50% and 75% a year (O18)

**Why:** at 25% a year, the sizes averaged about a third of the account's own, so most of the smaller fall was simply the smaller size. On 2026-11-13 the owner chose to test targets that keep the sizes nearer the account's own: STRAT-004, and STRAT-007 with its ensemble, each at 50% and 75% a year.

**What was run:**
- **Set-up:** everything else as above: coins, months, costs, EWMA (λ 0.94), 10 seeded runs of 200 random entries and 200 random orders.
- **Trials:** 4 explorations logged.
- **Code:** `run_vol_targets.py`.

**The strategies' own trades, by target:**

| | Mean size | Net | Largest fall (closes) | Random orders that fell no further, pooled (by seed) | Random orders that made at least as much |
|---|---:|---:|---:|---:|---:|
| STRAT-004, own | 1 | +$3,198 | 5.7% | | |
| STRAT-004, 25% | 0.36 | +$1,069 | 1.8% | 5.0% (2.5% to 8.0%) | 49% |
| STRAT-004, 50% | 0.68 | +$2,098 | 3.4% | 6.8% (4.5% to 9.5%) | 49% |
| STRAT-004, 75% | 0.85 | +$2,997 | 4.8% | 26.4% (19.5% to 34.0%) | 21% |
| STRAT-007 20 days, own | 1 | +$2,630 | 4.3% | | |
| STRAT-007 20 days, 25% | 0.37 | +$861 | 1.6% | 21.2% (15.5% to 25.0%) | 47% |
| STRAT-007 20 days, 50% | 0.70 | +$1,667 | 2.9% | 15.9% (9.5% to 20.0%) | 63% |
| STRAT-007 20 days, 75% | 0.87 | +$2,146 | 3.5% | 5.4% (2.0% to 7.5%) | 76% |

- **Base rate:** if the timing of the sizes did nothing, about half of random orders would fall no further. Each share is pooled over 2,000 orders.
- **No pattern:**
  - **STRAT-004** looks best at 25% and 50% and not at 75%; STRAT-007 the other way round.
  - **On net,** STRAT-004 at 75% made more than 79% of random orders, while 76% of random orders made at least as much as STRAT-007 at 75%.
  - **Six comparisons in all.** The smallest share, 5.0%, is 30% after Holm over the six. This is what chance looks like across six looks.
- **Size:** the net and the fall rise with the mean size, close to in proportion.

**The ensemble's book** (one path each; it has no random part):

| | Net | Largest fall (closes) | Within the bar | Mean committed | Entries skipped for cash | Net per point of fall |
|---|---:|---:|---:|---:|---:|---:|
| Own sizing | +$37,648 | 42.2% | 47.3% | 18.9% | 62 | $892 |
| 25% a year | +$9,381 | 22.3% | 23.9% | 8.0% | 0 | $421 |
| 50% a year | +$20,998 | 34.3% | 36.0% | 14.4% | 0 | $612 |
| 75% a year | +$32,819 | 40.8% | 43.6% | 17.5% | 35 | $804 |

- **Worse per unit of drawdown:** at every target, the sized book made less per point of its largest fall than the book at its own sizing.
- **The halt:** every book would have reached the trader's 8% halt within its first two months (own sizing on 2021-01-22, the sized books in February 2021).

**What it means:** with this estimator on these months, volatility targeting showed nothing beyond holding less. For the registration draft (SR1-E2, D4), the book's own sizing should decide, with sizing shown only.

## What this cannot show
- **Other months.** These include one bull year (2021), one bear (2022) and its recovery, and they were used before. The lockbox (from 2025-05-06) was not read.
- **A test.** There is one path for each set-up, no registration, and no correction across the eight set-ups (§4 shows Holm over its six sizing comparisons only). The ensemble's book has no random-entry baseline of its own. The bootstrap above is descriptive.
- **Survivorship.** All nine coins are listed today. Holding, and trend rules, look better on coins that survived.
- **The paper's own design.** Its 5- and 10-day members, sizes up to 200% and daily re-sizing are left out on purpose (the branch's notes say why).
- **Small accounts.** Only £10,000 was run. At £500, each slice (1/63 of the account) is below most minimums and would be skipped.
- **Other fees.** All runs are at 0.50% a side, the account's rate.

## Files
- `run_compare_ensemble.py`: the four set-ups, 10 seeds each, in a sandbox (`compare-ensemble/run.sh.txt`).
- `ensemble_periods.py`: the books' period returns and drawdowns, recomputed for this report (nothing logged).
- `ensemble_difference.py`: the bootstrap.
- `run_vol_targets.py`: §4's four runs; `vol_targets_summary.py`: its tables; `ensemble_recheck.py`: the correction in §1 (nothing logged).
- `compare-ensemble/`:
  - `compare_ensemble.json`: every run's record, with daily and weekly rows trimmed;
  - `ensemble_periods.json`;
  - `ensemble_difference.json`;
  - `vol_targets.json`: §4's records, trimmed the same way, and `vol_targets_summary.json`;
  - `ensemble_recheck.json`: the correction in §1;
  - `trials.jsonl`: the sandbox's trial log after §4 (84 lines);
  - `run-o18.sh.txt`: how §4 and the correction were run.

## For you to decide
1. **A registered evaluation of the ensemble** (with its random-entry baseline, the stationary bootstrap you accepted as O3, and your drawdown rule, O12) would be the next step before any paper use. It needs your approval, and it must not read the lockbox until a finalist is declared. **Answered on 2026-11-13 (O17): drafted for review** in `ptai-rd-001/E2-ensemble-registration-draft.md`.
2. **Volatility sizing at 25%** adds nothing beyond its smaller size here. A test at a higher target (where sizes stay nearer 1) would show whether it does anything but shrink. **Answered on 2026-11-13 (O18): run at 50% and 75% in §4.** It showed nothing beyond shrinking there either.
