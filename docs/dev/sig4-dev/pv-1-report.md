# Model lab batch 20261107-175558

- Frozen 2026-11-07T17:55:58Z; batch file SHA-256 `f4389fb8b07b70a44896b6981f6479113f1942619e758e49146ebc0e554b5be0`.
- Spec version 1.1; declared as pv-1.
- Window 2020-01-01T00:00:00Z to 2026-11-06T00:00:00Z; 18 folds of 3 months from 2021-01-01T00:00:00Z to 2025-05-06T00:00:00Z; the last 18 months (2025-05-06T00:00:00Z to 2026-11-06T00:00:00Z) are locked and were not read.
- 3 contestants tested; 10000 draws of each random baseline (seeds from 500000 and 600000); probability of backtest overfitting 0.643 over 16 blocks.
- Trade rules: {"dca_levels": [-2.5, -5.0, -10.0, -20.0, -30.0, -40.0, -50.0], "dca_multiplier": 2.0, "max_coin_allocation_pct": 10.0, "max_dca_buys_per_24h": 2, "pm_start_pct_no_dca": 5.0, "pm_start_pct_with_dca": 2.5, "start_allocation_pct": 1.0, "trade_start_level": 3, "trailing_gap_pct": 0.5}; neural DCA off for every contestant; the pattern model is also shown with it on.

## Series

| Coin | Exchange | Pair | First bar | Last bar | Bars | SHA-256 | Fee a side | Why |
|---|---|---|---|---|---|---|---|---|
| ADA | coinbase | ADA-USD | 2021-03-18T16:00:00Z | 2026-11-05T23:00:00Z | 49385 | `5300034b117dc429` | 0.50% + 0.05% slippage | batch PV-1's coins (FDS-MH-001 section 7a) |
| AVAX | coinbase | AVAX-USD | 2021-09-30T19:00:00Z | 2026-11-05T23:00:00Z | 44679 | `5efd791d823603ea` | 0.50% + 0.05% slippage | batch PV-1's coins (FDS-MH-001 section 7a) |
| BNB | coinbase | BNB-USD | 2025-10-22T18:00:00Z | 2026-11-05T23:00:00Z | 9091 | `ba706d8aa7cfb57e` | 0.50% + 0.05% slippage | batch PV-1's coins (FDS-MH-001 section 7a) |
| BTC | coinbase | BTC-USD | 2020-01-01T00:00:00Z | 2026-11-05T23:00:00Z | 60008 | `53862fde3c219234` | 0.50% + 0.05% slippage | batch PV-1's coins (FDS-MH-001 section 7a) |
| DASH | coinbase | DASH-USD | 2020-01-01T00:00:00Z | 2026-11-05T23:00:00Z | 59999 | `10d8fdde75120491` | 0.50% + 0.05% slippage | batch PV-1's coins (FDS-MH-001 section 7a) |
| DOGE | coinbase | DOGE-USD | 2021-06-03T16:00:00Z | 2026-11-05T23:00:00Z | 47537 | `f73c735fe4912cb1` | 0.50% + 0.05% slippage | batch PV-1's coins (FDS-MH-001 section 7a) |
| ETH | coinbase | ETH-USD | 2020-01-01T00:00:00Z | 2026-11-05T23:00:00Z | 60008 | `4cde004c203286bb` | 0.50% + 0.05% slippage | batch PV-1's coins (FDS-MH-001 section 7a) |
| HYPE | coinbase | HYPE-USD | 2026-02-05T19:00:00Z | 2026-11-05T23:00:00Z | 6552 | `f09bffafc3330e9e` | 0.50% + 0.05% slippage | batch PV-1's coins (FDS-MH-001 section 7a) |
| LINK | coinbase | LINK-USD | 2020-01-01T00:00:00Z | 2026-11-05T23:00:00Z | 60005 | `0e04dd7042532734` | 0.50% + 0.05% slippage | batch PV-1's coins (FDS-MH-001 section 7a) |
| LTC | coinbase | LTC-USD | 2020-01-01T00:00:00Z | 2026-11-05T23:00:00Z | 60006 | `a4541ad7268594a7` | 0.50% + 0.05% slippage | batch PV-1's coins (FDS-MH-001 section 7a) |
| SOL | coinbase | SOL-USD | 2021-06-17T16:00:00Z | 2026-11-05T23:00:00Z | 47201 | `6479acc111596555` | 0.50% + 0.05% slippage | batch PV-1's coins (FDS-MH-001 section 7a) |
| XRP | coinbase | XRP-USD | 2023-07-13T20:00:00Z | 2026-11-05T23:00:00Z | 29058 | `d99839d9c305677b` | 0.50% + 0.05% slippage | batch PV-1's coins (FDS-MH-001 section 7a) |
| ZEC | coinbase | ZEC-USD | 2020-12-08T17:00:00Z | 2026-11-05T23:00:00Z | 51784 | `cf881a833975ffac` | 0.50% + 0.05% slippage | batch PV-1's coins (FDS-MH-001 section 7a) |

## Contestants

| Contestant | Trades | Return per day held | R1 median | R1 percentile | R2 percentile | p | Smallest detectable edge | Verdict | Total profit | Worst drawdown | Time in a trade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Logistic regression on clean wins from price only, top 50% (`pv.linear.t1.P.q50`) | 435 | -0.005% a day | -0.003% a day | 34.9 | 2.5 | 0.9750 | +0.012% a day | Too few trades to tell: this test could only see an edge above +0.012% a day | -5.54 | -90.77% | +98% |
| Logistic regression on clean wins from price and volume, top 50% (`pv.linear.t1.PV.q50`) | 448 | +0.000% a day | -0.003% a day | 78.1 | 52.4 | 0.4759 | +0.012% a day | Too few trades to tell: this test could only see an edge above +0.012% a day | 0.02 | -91.11% | +98% |
| Logistic regression on clean wins from price and volume from an earlier time, top 50% (`pv.linear.t1.PVp.q50`) | 437 | -0.004% a day | -0.003% a day | 36.6 | 4.0 | 0.9602 | +0.012% a day | Too few trades to tell: this test could only see an edge above +0.012% a day | -5.21 | -90.77% | +98% |
| Logistic regression on clean wins from price and volume from an earlier time (2), top 50% (`pv.linear.t1.PVp2.q50`) | - | - | - | - | - | - | - | Forecast scores only, not tested here | - | - | - |
| Logistic regression on clean wins from price and volume from an earlier time (3), top 50% (`pv.linear.t1.PVp3.q50`) | - | - | - | - | - | - | - | Forecast scores only, not tested here | - | - | - |
| Logistic regression on clean wins from price and volume from an earlier time (4), top 50% (`pv.linear.t1.PVp4.q50`) | - | - | - | - | - | - | - | Forecast scores only, not tested here | - | - | - |
| Logistic regression on clean wins from price and volume from an earlier time (5), top 50% (`pv.linear.t1.PVp5.q50`) | - | - | - | - | - | - | - | Forecast scores only, not tested here | - | - | - |

### Logistic regression on clean wins from price only, top 50% (`pv.linear.t1.P.q50`)

Parameters: {"features": "25: P", "model": "logistic regression, L2 penalty, C = 1, standardised", "rows": "every batch coin's rows before the fold, purged, weighted by uniqueness; common rows only", "target": "clean win: the profit line before the first DCA level, within 336 hours", "top": "50% of the scores of its own training rows"}.

- R1 as 10 runs of 1000 draws: p from 0.6234 to 0.6683; pooled 0.6512.
- R2 as 10 runs of 1000 draws: p from 0.9670 to 0.9820; pooled 0.9750.
| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2021-10-04T20:00:00Z | 7 | -0.048% a day | -5.15 |
| AVAX | 2022-04-18T20:00:00Z | 2 | -0.067% a day | -6.30 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 69 | +0.072% a day | 8.59 |
| DASH | 2021-01-01T01:00:00Z | 45 | -0.014% a day | -1.99 |
| DOGE | 2021-12-20T20:00:00Z | 35 | +0.005% a day | 0.51 |
| ETH | 2021-01-01T01:00:00Z | 58 | +0.002% a day | 0.23 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 24 | -0.032% a day | -4.17 |
| LTC | 2021-01-01T01:00:00Z | 50 | -0.001% a day | -0.10 |
| SOL | 2022-01-03T20:00:00Z | 59 | +0.019% a day | 1.92 |
| XRP | 2024-01-29T20:00:00Z | 45 | +0.064% a day | 2.13 |
| ZEC | 2021-06-26T20:00:00Z | 41 | -0.010% a day | -1.21 |

- Rising markets: 405 trades, -0.009% a day; falling: 30 trades, +0.024% a day.
- At half the fee rate: 491 trades, +0.006% a day, total profit 6.72.
- At double the fee rate: 356 trades, -0.016% a day, total profit -20.02.
- Not in R2 (stream shorter than twice the shortest move): BNB, HYPE.
- Pass conditions: drawdown yes, pbo no, profit_above_0 no, trades yes; Holm no; screen no.

### Logistic regression on clean wins from price and volume, top 50% (`pv.linear.t1.PV.q50`)

Parameters: {"features": "27: P + V", "model": "logistic regression, L2 penalty, C = 1, standardised", "rows": "every batch coin's rows before the fold, purged, weighted by uniqueness; common rows only", "target": "clean win: the profit line before the first DCA level, within 336 hours", "top": "50% of the scores of its own training rows"}.

- R1 as 10 runs of 1000 draws: p from 0.2078 to 0.2438; pooled 0.2192.
- R2 as 10 runs of 1000 draws: p from 0.4555 to 0.5055; pooled 0.4759.
| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2021-10-04T20:00:00Z | 6 | -0.047% a day | -5.12 |
| AVAX | 2022-04-18T20:00:00Z | 2 | -0.067% a day | -6.30 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 68 | +0.073% a day | 8.64 |
| DASH | 2021-01-01T01:00:00Z | 47 | -0.017% a day | -2.42 |
| DOGE | 2021-12-20T20:00:00Z | 35 | +0.003% a day | 0.31 |
| ETH | 2021-01-01T01:00:00Z | 43 | -0.005% a day | -0.60 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 46 | -0.010% a day | -1.26 |
| LTC | 2021-01-01T01:00:00Z | 40 | -0.002% a day | -0.32 |
| SOL | 2022-01-03T20:00:00Z | 60 | +0.017% a day | 1.76 |
| XRP | 2024-01-29T20:00:00Z | 45 | +0.075% a day | 2.48 |
| ZEC | 2021-06-26T20:00:00Z | 56 | +0.024% a day | 2.84 |

- Rising markets: 413 trades, +0.001% a day; falling: 35 trades, -0.003% a day.
- At half the fee rate: 498 trades, +0.010% a day, total profit 11.47.
- At double the fee rate: 362 trades, -0.016% a day, total profit -19.98.
- Not in R2 (stream shorter than twice the shortest move): BNB, HYPE.
- Pass conditions: drawdown yes, pbo no, profit_above_0 yes, trades yes; Holm no; screen no.
- An earlier look at its results: 2023-11-06 to 2026-11-05, 10 coins, on 2026-11-05: the volume research's look at v2 (as rv_hod20) against STRAT-001's trades: a look at a feature, not at this contestant's results (docs/research/volume-module.md, sections 5.4 and 6.2).
- Its lockbox months were seen before (the looks from 2023-11-06), so a final check is shown and is not unseen evidence.

### Logistic regression on clean wins from price and volume from an earlier time, top 50% (`pv.linear.t1.PVp.q50`)

Parameters: {"features": "27: P + Vp1", "model": "logistic regression, L2 penalty, C = 1, standardised", "rows": "every batch coin's rows before the fold, purged, weighted by uniqueness; common rows only", "target": "clean win: the profit line before the first DCA level, within 336 hours", "top": "50% of the scores of its own training rows"}.

- R1 as 10 runs of 1000 draws: p from 0.6064 to 0.6593; pooled 0.6335.
- R2 as 10 runs of 1000 draws: p from 0.9540 to 0.9670; pooled 0.9602.
| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2021-10-04T20:00:00Z | 7 | -0.048% a day | -5.15 |
| AVAX | 2022-04-18T20:00:00Z | 2 | -0.067% a day | -6.30 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 69 | +0.072% a day | 8.57 |
| DASH | 2021-01-01T01:00:00Z | 47 | -0.018% a day | -2.51 |
| DOGE | 2021-12-20T20:00:00Z | 35 | +0.004% a day | 0.42 |
| ETH | 2021-01-01T01:00:00Z | 53 | -0.001% a day | -0.17 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 32 | -0.024% a day | -3.08 |
| LTC | 2021-01-01T01:00:00Z | 51 | +0.001% a day | 0.09 |
| SOL | 2022-01-03T20:00:00Z | 61 | +0.026% a day | 2.70 |
| XRP | 2024-01-29T20:00:00Z | 46 | +0.058% a day | 1.93 |
| ZEC | 2021-06-26T20:00:00Z | 34 | -0.014% a day | -1.71 |

- Rising markets: 406 trades, -0.009% a day; falling: 31 trades, +0.029% a day.
- At half the fee rate: 475 trades, +0.006% a day, total profit 7.06.
- At double the fee rate: 363 trades, -0.016% a day, total profit -19.38.
- Not in R2 (stream shorter than twice the shortest move): BNB, HYPE.
- Pass conditions: drawdown yes, pbo no, profit_above_0 no, trades yes; Holm no; screen no.
- An earlier look at its results: 2023-11-06 to 2026-11-05, 10 coins, on 2026-11-05: the volume research's look at v2 (as rv_hod20) against STRAT-001's trades: a look at a feature, not at this contestant's results (docs/research/volume-module.md, sections 5.4 and 6.2).
- Its lockbox months were seen before (the looks from 2023-11-06), so a final check is shown and is not unseen evidence.

### Logistic regression on clean wins from price and volume from an earlier time (2), top 50% (`pv.linear.t1.PVp2.q50`)

Parameters: {"features": "27: P + Vp2", "model": "logistic regression, L2 penalty, C = 1, standardised", "rows": "every batch coin's rows before the fold, purged, weighted by uniqueness; common rows only", "target": "clean win: the profit line before the first DCA level, within 336 hours", "top": "50% of the scores of its own training rows"}.

- Fitted for its probabilities only, which are saved with the batch; its trades are not scored and it is not one of the K.

### Logistic regression on clean wins from price and volume from an earlier time (3), top 50% (`pv.linear.t1.PVp3.q50`)

Parameters: {"features": "27: P + Vp3", "model": "logistic regression, L2 penalty, C = 1, standardised", "rows": "every batch coin's rows before the fold, purged, weighted by uniqueness; common rows only", "target": "clean win: the profit line before the first DCA level, within 336 hours", "top": "50% of the scores of its own training rows"}.

- Fitted for its probabilities only, which are saved with the batch; its trades are not scored and it is not one of the K.

### Logistic regression on clean wins from price and volume from an earlier time (4), top 50% (`pv.linear.t1.PVp4.q50`)

Parameters: {"features": "27: P + Vp4", "model": "logistic regression, L2 penalty, C = 1, standardised", "rows": "every batch coin's rows before the fold, purged, weighted by uniqueness; common rows only", "target": "clean win: the profit line before the first DCA level, within 336 hours", "top": "50% of the scores of its own training rows"}.

- Fitted for its probabilities only, which are saved with the batch; its trades are not scored and it is not one of the K.

### Logistic regression on clean wins from price and volume from an earlier time (5), top 50% (`pv.linear.t1.PVp5.q50`)

Parameters: {"features": "27: P + Vp5", "model": "logistic regression, L2 penalty, C = 1, standardised", "rows": "every batch coin's rows before the fold, purged, weighted by uniqueness; common rows only", "target": "clean win: the profit line before the first DCA level, within 336 hours", "top": "50% of the scores of its own training rows"}.

- Fitted for its probabilities only, which are saved with the batch; its trades are not scored and it is not one of the K.
