# Model lab batch 20261110-232634

- Frozen 2026-11-10T23:26:34Z; batch file SHA-256 `7129db9455beefdf3e0d4c9af0c572461ba0dcb9de214ee52f11574554804be5`.
- Spec version 1; declared as batch-1.
- Window 2020-01-01T00:00:00Z to 2026-11-06T00:00:00Z; 18 folds of 3 months from 2021-01-01T00:00:00Z to 2025-05-06T00:00:00Z; the last 18 months (2025-05-06T00:00:00Z to 2026-11-06T00:00:00Z) are locked and were not read.
- 14 contestants tested; 10000 draws of each random baseline (seeds from 300000 and 400000); probability of backtest overfitting 0.777 over 16 blocks.
- Trade rules: {"dca_levels": [-2.5, -5.0, -10.0, -20.0, -30.0, -40.0, -50.0], "dca_multiplier": 2.0, "max_coin_allocation_pct": 10.0, "max_dca_buys_per_24h": 2, "pm_start_pct_no_dca": 5.0, "pm_start_pct_with_dca": 2.5, "start_allocation_pct": 1.0, "trade_start_level": 3, "trailing_gap_pct": 0.5}; neural DCA off for every contestant; the pattern model is also shown with it on.

## Series

| Coin | Exchange | Pair | First bar | Last bar | Bars | SHA-256 | Fee a side | Why |
|---|---|---|---|---|---|---|---|---|
| ADA | coinbase | ADA-USD | 2021-03-18T16:00:00Z | 2026-11-05T23:00:00Z | 49385 | `5300034b117dc429` | 0.50% + 0.05% slippage | batch 1's coins (FDS-MH-001 section 7) |
| AVAX | coinbase | AVAX-USD | 2021-09-30T19:00:00Z | 2026-11-05T23:00:00Z | 44679 | `5efd791d823603ea` | 0.50% + 0.05% slippage | batch 1's coins (FDS-MH-001 section 7) |
| BNB | coinbase | BNB-USD | 2025-10-22T18:00:00Z | 2026-11-05T23:00:00Z | 9091 | `ba706d8aa7cfb57e` | 0.50% + 0.05% slippage | batch 1's coins (FDS-MH-001 section 7) |
| BTC | coinbase | BTC-USD | 2020-01-01T00:00:00Z | 2026-11-05T23:00:00Z | 60008 | `53862fde3c219234` | 0.50% + 0.05% slippage | batch 1's coins (FDS-MH-001 section 7) |
| DASH | coinbase | DASH-USD | 2020-01-01T00:00:00Z | 2026-11-05T23:00:00Z | 59999 | `10d8fdde75120491` | 0.50% + 0.05% slippage | batch 1's coins (FDS-MH-001 section 7) |
| DOGE | coinbase | DOGE-USD | 2021-06-03T16:00:00Z | 2026-11-05T23:00:00Z | 47537 | `f73c735fe4912cb1` | 0.50% + 0.05% slippage | batch 1's coins (FDS-MH-001 section 7) |
| ETH | coinbase | ETH-USD | 2020-01-01T00:00:00Z | 2026-11-05T23:00:00Z | 60008 | `4cde004c203286bb` | 0.50% + 0.05% slippage | batch 1's coins (FDS-MH-001 section 7) |
| HYPE | coinbase | HYPE-USD | 2026-02-05T19:00:00Z | 2026-11-05T23:00:00Z | 6552 | `f09bffafc3330e9e` | 0.50% + 0.05% slippage | batch 1's coins (FDS-MH-001 section 7) |
| LINK | coinbase | LINK-USD | 2020-01-01T00:00:00Z | 2026-11-05T23:00:00Z | 60005 | `0e04dd7042532734` | 0.50% + 0.05% slippage | batch 1's coins (FDS-MH-001 section 7) |
| LTC | coinbase | LTC-USD | 2020-01-01T00:00:00Z | 2026-11-05T23:00:00Z | 60006 | `a4541ad7268594a7` | 0.50% + 0.05% slippage | batch 1's coins (FDS-MH-001 section 7) |
| SOL | coinbase | SOL-USD | 2021-06-17T16:00:00Z | 2026-11-05T23:00:00Z | 47201 | `6479acc111596555` | 0.50% + 0.05% slippage | batch 1's coins (FDS-MH-001 section 7) |
| XRP | coinbase | XRP-USD | 2023-07-13T20:00:00Z | 2026-11-05T23:00:00Z | 29058 | `d99839d9c305677b` | 0.50% + 0.05% slippage | batch 1's coins (FDS-MH-001 section 7) |
| ZEC | coinbase | ZEC-USD | 2020-12-08T17:00:00Z | 2026-11-05T23:00:00Z | 51784 | `cf881a833975ffac` | 0.50% + 0.05% slippage | batch 1's coins (FDS-MH-001 section 7) |

## Contestants

| Contestant | Trades | Return per day held | R1 median | R1 percentile | R2 percentile | p | Smallest detectable edge | Verdict | Total profit | Worst drawdown | Time in a trade |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Enter whenever flat (`ref.always`) | 540 | +0.004% a day | n/a | n/a | n/a | n/a | n/a | Reference only, not tested | 5.44 | -91.38% | +100% |
| Daily close above its 20-day average (`rule.sma20`) | 519 | +0.003% a day | +0.003% a day | 48.6 | 59.7 | 0.5136 | +0.026% a day | Too few trades to tell: this test could only see an edge above +0.026% a day | 4.30 | -91.38% | +99% |
| Daily close above its 50-day average (`rule.sma50`) | 511 | +0.003% a day | +0.003% a day | 37.6 | 54.0 | 0.6244 | +0.035% a day | Too few trades to tell: this test could only see an edge above +0.035% a day | 3.28 | -91.38% | +99% |
| Daily close above its 100-day average (`rule.sma100`) | 515 | +0.003% a day | +0.004% a day | 29.8 | 56.2 | 0.7018 | +0.044% a day | Too few trades to tell: this test could only see an edge above +0.044% a day | 4.06 | -91.38% | +100% |
| Daily close above its close 14 days earlier (`rule.mom14`) | 520 | +0.005% a day | +0.003% a day | 67.6 | 63.9 | 0.3609 | +0.024% a day | Too few trades to tell: this test could only see an edge above +0.024% a day | 5.75 | -91.38% | +99% |
| Daily close at or above the highest of the previous 20 daily closes (`rule.high20`) | 425 | +0.007% a day | +0.002% a day | 76.7 | 55.6 | 0.4441 | +0.051% a day | Too few trades to tell: this test could only see an edge above +0.051% a day | 8.57 | -91.48% | +90% |
| BTC's daily close above its 50-day average (`rule.btc50`) | 700 | +0.025% a day | +0.005% a day | 100.0 | 94.9 | 0.0508 | +0.037% a day | Too few trades to tell: this test could only see an edge above +0.037% a day | 30.20 | -91.84% | +95% |
| 24-hour return below the coin's own 10th percentile of the last 90 days (`rule.dip24`) | 487 | +0.005% a day | -0.000% a day | 77.0 | 72.5 | 0.2752 | +0.028% a day | Too few trades to tell: this test could only see an edge above +0.028% a day | 5.61 | -91.90% | +91% |
| The pattern model, as the trader uses it (`pattern`) | 515 | +0.007% a day | +0.002% a day | 79.3 | 61.5 | 0.3854 | +0.026% a day | Too few trades to tell: this test could only see an edge above +0.026% a day | 7.04 | -92.08% | +95% |
| Logistic regression on clean wins, top 50% (`linear.t1.q50`) | 560 | +0.006% a day | +0.002% a day | 85.6 | 84.6 | 0.1538 | +0.013% a day | Too few trades to tell: this test could only see an edge above +0.013% a day | 7.68 | -91.72% | +98% |
| Logistic regression on clean wins, top 20% (`linear.t1.q20`) | 531 | +0.004% a day | +0.000% a day | 77.2 | 68.9 | 0.3115 | +0.019% a day | Too few trades to tell: this test could only see an edge above +0.019% a day | 5.02 | -91.51% | +95% |
| Gradient-boosted trees on clean wins, top 50% (`trees.t1.q50`) | 496 | +0.001% a day | +0.002% a day | 33.7 | 32.6 | 0.6737 | +0.012% a day | Too few trades to tell: this test could only see an edge above +0.012% a day | 1.03 | -91.57% | +99% |
| Gradient-boosted trees on clean wins, top 20% (`trees.t1.q20`) | 386 | -0.003% a day | +0.000% a day | 24.9 | 22.9 | 0.7708 | +0.022% a day | Too few trades to tell: this test could only see an edge above +0.022% a day | -4.08 | -91.90% | +95% |
| Gradient-boosted trees on return per day held, top 50% (`trees.t2.q50`) | 522 | +0.004% a day | +0.003% a day | 57.2 | 67.9 | 0.4281 | +0.025% a day | Too few trades to tell: this test could only see an edge above +0.025% a day | 4.62 | -91.39% | +99% |
| Gradient-boosted trees on return per day held, top 20% (`trees.t2.q20`) | 509 | +0.002% a day | -0.002% a day | 84.7 | 57.6 | 0.4237 | +0.047% a day | Too few trades to tell: this test could only see an edge above +0.047% a day | 2.75 | -91.38% | +90% |

### Enter whenever flat (`ref.always`)

Parameters: {}.

| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2021-06-27T00:00:00Z | 30 | -0.001% a day | -0.09 |
| AVAX | 2022-01-09T00:00:00Z | 14 | -0.053% a day | -5.36 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 60 | +0.057% a day | 6.92 |
| DASH | 2021-01-01T01:00:00Z | 49 | -0.018% a day | -2.63 |
| DOGE | 2021-09-12T00:00:00Z | 28 | -0.000% a day | -0.00 |
| ETH | 2021-01-01T01:00:00Z | 78 | +0.011% a day | 1.45 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 58 | +0.011% a day | 1.44 |
| LTC | 2021-01-01T01:00:00Z | 46 | -0.018% a day | -2.32 |
| SOL | 2021-09-26T00:00:00Z | 71 | +0.032% a day | 3.63 |
| XRP | 2023-10-22T00:00:00Z | 69 | +0.124% a day | 5.04 |
| ZEC | 2021-03-19T00:00:00Z | 37 | -0.020% a day | -2.63 |

- Rising markets: 498 trades, +0.008% a day; falling: 42 trades, -0.033% a day.
- At half the fee rate: 608 trades, +0.011% a day, total profit 14.65.
- At double the fee rate: 480 trades, -0.005% a day, total profit -7.00.

### Daily close above its 20-day average (`rule.sma20`)

Parameters: {"bars": "complete UTC days", "days": 20}.

- R1 as 10 runs of 1000 draws: p from 0.4805 to 0.5465; pooled 0.5136.
- R2 as 10 runs of 1000 draws: p from 0.3906 to 0.4296; pooled 0.4029.
| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2021-06-27T00:00:00Z | 25 | -0.001% a day | -0.13 |
| AVAX | 2022-01-09T00:00:00Z | 12 | -0.052% a day | -5.16 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 65 | +0.067% a day | 7.76 |
| DASH | 2021-01-01T01:00:00Z | 43 | -0.022% a day | -3.14 |
| DOGE | 2021-09-12T00:00:00Z | 27 | -0.010% a day | -1.15 |
| ETH | 2021-01-01T01:00:00Z | 78 | +0.011% a day | 1.42 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 52 | +0.010% a day | 1.35 |
| LTC | 2021-01-01T01:00:00Z | 46 | -0.018% a day | -2.32 |
| SOL | 2021-09-26T00:00:00Z | 64 | +0.028% a day | 3.14 |
| XRP | 2023-10-22T00:00:00Z | 70 | +0.138% a day | 5.16 |
| ZEC | 2021-03-19T00:00:00Z | 37 | -0.020% a day | -2.63 |

- Rising markets: 486 trades, +0.007% a day; falling: 33 trades, -0.031% a day.
- At half the fee rate: 577 trades, +0.011% a day, total profit 13.64.
- At double the fee rate: 457 trades, -0.006% a day, total profit -8.02.
- Not in R2 (stream shorter than twice the shortest move): BNB, HYPE.
- Pass conditions: drawdown yes, pbo no, profit_above_0 yes, trades yes; Holm no; screen no.
- An earlier look at its results: 2021-01-01 to 2025-05-06, 13 coins, on 2026-11-06: the phase B timing run, batch 20261106-143033: walk-forward only, the lockbox not read (docs/dev/RUN-LOG-mh-1.md).

### Daily close above its 50-day average (`rule.sma50`)

Parameters: {"bars": "complete UTC days", "days": 50}.

- R1 as 10 runs of 1000 draws: p from 0.6094 to 0.6444; pooled 0.6244.
- R2 as 10 runs of 1000 draws: p from 0.4226 to 0.4895; pooled 0.4604.
| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2021-06-27T00:00:00Z | 25 | -0.003% a day | -0.43 |
| AVAX | 2022-01-09T00:00:00Z | 8 | -0.058% a day | -5.78 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 60 | +0.057% a day | 6.92 |
| DASH | 2021-01-01T01:00:00Z | 44 | -0.021% a day | -3.00 |
| DOGE | 2021-09-12T00:00:00Z | 22 | -0.010% a day | -1.08 |
| ETH | 2021-01-01T01:00:00Z | 78 | +0.011% a day | 1.45 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 52 | +0.010% a day | 1.35 |
| LTC | 2021-01-01T01:00:00Z | 45 | -0.018% a day | -2.31 |
| SOL | 2021-09-26T00:00:00Z | 71 | +0.032% a day | 3.63 |
| XRP | 2023-10-22T00:00:00Z | 69 | +0.139% a day | 5.18 |
| ZEC | 2021-03-19T00:00:00Z | 37 | -0.020% a day | -2.63 |

- Rising markets: 484 trades, +0.006% a day; falling: 27 trades, -0.042% a day.
- At half the fee rate: 571 trades, +0.009% a day, total profit 11.37.
- At double the fee rate: 455 trades, -0.007% a day, total profit -8.65.
- Not in R2 (stream shorter than twice the shortest move): BNB, HYPE.
- Pass conditions: drawdown yes, pbo no, profit_above_0 yes, trades yes; Holm no; screen no.
- An earlier look at its results: 2021-01-01 to 2025-05-06, 13 coins, on 2026-11-06: the phase B timing run, batch 20261106-143033: walk-forward only, the lockbox not read (docs/dev/RUN-LOG-mh-1.md).

### Daily close above its 100-day average (`rule.sma100`)

Parameters: {"bars": "complete UTC days", "days": 100}.

- R1 as 10 runs of 1000 draws: p from 0.6843 to 0.7303; pooled 0.7018.
- R2 as 10 runs of 1000 draws: p from 0.4176 to 0.4635; pooled 0.4378.
| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2021-06-27T00:00:00Z | 22 | -0.002% a day | -0.26 |
| AVAX | 2022-01-09T00:00:00Z | 9 | -0.055% a day | -5.55 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 60 | +0.057% a day | 6.92 |
| DASH | 2021-01-01T01:00:00Z | 48 | -0.018% a day | -2.62 |
| DOGE | 2021-09-12T00:00:00Z | 25 | -0.010% a day | -1.14 |
| ETH | 2021-01-01T01:00:00Z | 77 | +0.011% a day | 1.46 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 55 | +0.011% a day | 1.50 |
| LTC | 2021-01-01T01:00:00Z | 45 | -0.018% a day | -2.31 |
| SOL | 2021-09-26T00:00:00Z | 70 | +0.032% a day | 3.64 |
| XRP | 2023-10-22T00:00:00Z | 67 | +0.125% a day | 5.06 |
| ZEC | 2021-03-19T00:00:00Z | 37 | -0.020% a day | -2.63 |

- Rising markets: 494 trades, +0.007% a day; falling: 21 trades, -0.036% a day.
- At half the fee rate: 579 trades, +0.011% a day, total profit 14.17.
- At double the fee rate: 457 trades, -0.006% a day, total profit -7.50.
- Not in R2 (stream shorter than twice the shortest move): BNB, HYPE.
- Pass conditions: drawdown yes, pbo no, profit_above_0 yes, trades yes; Holm no; screen no.
- An earlier look at its results: 2021-01-01 to 2025-05-06, 13 coins, on 2026-11-06: the phase B timing run, batch 20261106-143033: walk-forward only, the lockbox not read (docs/dev/RUN-LOG-mh-1.md).

### Daily close above its close 14 days earlier (`rule.mom14`)

Parameters: {"bars": "complete UTC days", "days": 14}.

- R1 as 10 runs of 1000 draws: p from 0.3087 to 0.3377; pooled 0.3237.
- R2 as 10 runs of 1000 draws: p from 0.3317 to 0.3896; pooled 0.3609.
| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2021-06-27T00:00:00Z | 25 | -0.002% a day | -0.28 |
| AVAX | 2022-01-09T00:00:00Z | 12 | -0.052% a day | -5.16 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 61 | +0.063% a day | 7.49 |
| DASH | 2021-01-01T01:00:00Z | 47 | -0.019% a day | -2.82 |
| DOGE | 2021-09-12T00:00:00Z | 27 | -0.002% a day | -0.25 |
| ETH | 2021-01-01T01:00:00Z | 77 | +0.013% a day | 1.62 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 51 | +0.010% a day | 1.24 |
| LTC | 2021-01-01T01:00:00Z | 46 | -0.018% a day | -2.32 |
| SOL | 2021-09-26T00:00:00Z | 64 | +0.028% a day | 3.15 |
| XRP | 2023-10-22T00:00:00Z | 73 | +0.153% a day | 5.71 |
| ZEC | 2021-03-19T00:00:00Z | 37 | -0.020% a day | -2.63 |

- Rising markets: 484 trades, +0.008% a day; falling: 36 trades, -0.031% a day.
- At half the fee rate: 580 trades, +0.010% a day, total profit 12.45.
- At double the fee rate: 464 trades, -0.007% a day, total profit -8.64.
- Not in R2 (stream shorter than twice the shortest move): BNB, HYPE.
- Pass conditions: drawdown yes, pbo no, profit_above_0 yes, trades yes; Holm no; screen no.
- An earlier look at its results: 2021-01-01 to 2025-05-06, 13 coins, on 2026-11-06: the phase B timing run, batch 20261106-143033: walk-forward only, the lockbox not read (docs/dev/RUN-LOG-mh-1.md).

### Daily close at or above the highest of the previous 20 daily closes (`rule.high20`)

Parameters: {"bars": "complete UTC days", "days": 20}.

- R1 as 10 runs of 1000 draws: p from 0.2018 to 0.2647; pooled 0.2330.
- R2 as 10 runs of 1000 draws: p from 0.4186 to 0.4625; pooled 0.4441.
| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2021-06-27T00:00:00Z | 21 | -0.013% a day | -1.63 |
| AVAX | 2022-01-09T00:00:00Z | 9 | -0.057% a day | -5.72 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 51 | +0.050% a day | 5.40 |
| DASH | 2021-01-01T01:00:00Z | 35 | -0.026% a day | -3.57 |
| DOGE | 2021-09-12T00:00:00Z | 45 | +0.055% a day | 4.97 |
| ETH | 2021-01-01T01:00:00Z | 72 | +0.075% a day | 7.04 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 37 | -0.009% a day | -1.15 |
| LTC | 2021-01-01T01:00:00Z | 28 | -0.032% a day | -4.18 |
| SOL | 2021-09-26T00:00:00Z | 42 | +0.048% a day | 5.08 |
| XRP | 2023-10-22T00:00:00Z | 42 | +0.070% a day | 2.40 |
| ZEC | 2021-03-19T00:00:00Z | 43 | -0.001% a day | -0.08 |

- Rising markets: 367 trades, +0.010% a day; falling: 58 trades, -0.003% a day.
- At half the fee rate: 511 trades, +0.017% a day, total profit 19.01.
- At double the fee rate: 376 trades, -0.004% a day, total profit -5.25.
- Not in R2 (stream shorter than twice the shortest move): BNB, HYPE.
- Pass conditions: drawdown no, pbo no, profit_above_0 yes, trades yes; Holm no; screen no.
- An earlier look at its results: 2021-01-01 to 2025-05-06, 13 coins, on 2026-11-06: the phase B timing run, batch 20261106-143033: walk-forward only, the lockbox not read (docs/dev/RUN-LOG-mh-1.md).

### BTC's daily close above its 50-day average (`rule.btc50`)

Parameters: {"bars": "complete UTC days", "coin": "BTC, for every coin", "days": 50}.

- R1 as 10 runs of 1000 draws: p from 0.0010 to 0.0020; pooled 0.0003.
- R2 as 10 runs of 1000 draws: p from 0.0420 to 0.0649; pooled 0.0508.
| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2021-06-27T00:00:00Z | 29 | -0.001% a day | -0.13 |
| AVAX | 2022-01-09T00:00:00Z | 12 | -0.054% a day | -5.36 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 60 | +0.057% a day | 6.92 |
| DASH | 2021-01-01T01:00:00Z | 78 | +0.011% a day | 1.48 |
| DOGE | 2021-09-12T00:00:00Z | 28 | +0.001% a day | 0.11 |
| ETH | 2021-01-01T01:00:00Z | 104 | +0.043% a day | 4.67 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 81 | +0.043% a day | 5.22 |
| LTC | 2021-01-01T01:00:00Z | 68 | +0.010% a day | 1.21 |
| SOL | 2021-09-26T00:00:00Z | 89 | +0.057% a day | 5.96 |
| XRP | 2023-10-22T00:00:00Z | 66 | +0.123% a day | 4.99 |
| ZEC | 2021-03-19T00:00:00Z | 85 | +0.045% a day | 5.14 |

- Rising markets: 561 trades, +0.034% a day; falling: 139 trades, +0.001% a day.
- At half the fee rate: 742 trades, +0.033% a day, total profit 39.31.
- At double the fee rate: 634 trades, +0.015% a day, total profit 17.77.
- Not in R2 (stream shorter than twice the shortest move): BNB, HYPE.
- Pass conditions: drawdown no, pbo no, profit_above_0 yes, trades yes; Holm no; screen no.
- An earlier look at its results: 2021-01-01 to 2025-05-06, 13 coins, on 2026-11-06: the phase B timing run, batch 20261106-143033: walk-forward only, the lockbox not read (docs/dev/RUN-LOG-mh-1.md).

### 24-hour return below the coin's own 10th percentile of the last 90 days (`rule.dip24`)

Parameters: {"bars": "hourly", "days": 90, "hours": 24, "percentile": 10.0}.

- R1 as 10 runs of 1000 draws: p from 0.2128 to 0.2677; pooled 0.2303.
- R2 as 10 runs of 1000 draws: p from 0.2557 to 0.2887; pooled 0.2752.
| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2021-06-27T00:00:00Z | 17 | -0.037% a day | -3.99 |
| AVAX | 2022-01-09T00:00:00Z | 30 | -0.018% a day | -1.67 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 58 | +0.064% a day | 6.69 |
| DASH | 2021-01-01T01:00:00Z | 35 | -0.026% a day | -3.59 |
| DOGE | 2021-09-12T00:00:00Z | 21 | -0.026% a day | -2.73 |
| ETH | 2021-01-01T01:00:00Z | 69 | +0.025% a day | 2.76 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 75 | +0.037% a day | 4.20 |
| LTC | 2021-01-01T01:00:00Z | 35 | -0.016% a day | -2.01 |
| SOL | 2021-09-26T00:00:00Z | 75 | +0.053% a day | 4.83 |
| XRP | 2023-10-22T00:00:00Z | 52 | +0.193% a day | 5.99 |
| ZEC | 2021-03-19T00:00:00Z | 20 | -0.037% a day | -4.87 |

- Rising markets: 414 trades, +0.005% a day; falling: 73 trades, +0.005% a day.
- At half the fee rate: 529 trades, +0.016% a day, total profit 17.62.
- At double the fee rate: 436 trades, -0.004% a day, total profit -4.35.
- Not in R2 (stream shorter than twice the shortest move): BNB, HYPE.
- Pass conditions: drawdown no, pbo no, profit_above_0 yes, trades yes; Holm no; screen no.
- An earlier look at its results: 2021-01-01 to 2025-05-06, 13 coins, on 2026-11-06: the phase B timing run, batch 20261106-143033: walk-forward only, the lockbox not read (docs/dev/RUN-LOG-mh-1.md).

### The pattern model, as the trader uses it (`pattern`)

Parameters: {"entry": "long count at least the trade start level, short count 0", "fit": "the trainer's, per coin, on every bar before the fold"}.

- R1 as 10 runs of 1000 draws: p from 0.1738 to 0.2268; pooled 0.2071.
- R2 as 10 runs of 1000 draws: p from 0.3716 to 0.4106; pooled 0.3854.
| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2022-04-01T01:00:00Z | 20 | +0.027% a day | 2.52 |
| AVAX | 2022-10-01T01:00:00Z | 44 | +0.008% a day | 0.55 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 61 | +0.063% a day | 6.95 |
| DASH | 2021-01-01T01:00:00Z | 43 | -0.024% a day | -3.41 |
| DOGE | 2022-07-01T01:00:00Z | 46 | -0.002% a day | -0.18 |
| ETH | 2021-01-01T01:00:00Z | 67 | +0.018% a day | 2.15 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 49 | -0.007% a day | -0.87 |
| LTC | 2021-01-01T01:00:00Z | 42 | -0.022% a day | -2.81 |
| SOL | 2022-07-01T01:00:00Z | 75 | +0.063% a day | 4.14 |
| XRP | 2024-10-01T01:00:00Z | 35 | +0.115% a day | 1.51 |
| ZEC | 2022-01-01T01:00:00Z | 33 | -0.035% a day | -3.50 |

- Rising markets: 451 trades, +0.011% a day; falling: 64 trades, -0.004% a day.
- At half the fee rate: 572 trades, +0.019% a day, total profit 19.93.
- At double the fee rate: 423 trades, -0.008% a day, total profit -9.11.
- Not in R2 (stream shorter than twice the shortest move): BNB, HYPE, XRP.
- On the hours both cover, against the best untrained rule (`rule.btc50`): +0.007% a day against +0.024% a day; total profit 7.04 against 25.04.
- Pass conditions: above_best_rule no, drawdown no, pbo no, profit_above_0 yes, trades yes; Holm no; screen no.
- An earlier look at its results: 2024-07-01 to 2026-10-01, BTC, ETH, on 2026-10-07: FDS-MDL Tests A and B, the pattern model as STRAT-003 with that strategy's exits (docs/dev/BACKTEST-REPORT-model-1.md).
- An earlier look at its results: 2026-03-31 to 2026-11-05, 10 coins, on 2026-11-05: the volume research's held-out replay and model experiment (docs/research/volume-module.md, sections 6.4 and 6.5).
- An earlier look at its results: 2026-04-01 to 2026-11-06, the coins with a model in use, on 2026-11-05: the entry gate's held-out slices of the models in use (the last 20% of each one's window), in Check the models in use... and the trainer's gate.
- An earlier look at its results: 2026-04-05 to 2026-11-05, 13 coins, on 2026-11-05: the entry gate diagnostic (docs/dev/GATE-DIAGNOSTIC-2026-11-05.md).
- An earlier look at its results: 2021-01-01 to 2025-05-06, 13 coins, on 2026-11-06: the phase B timing run, batch 20261106-143033: walk-forward only, the lockbox not read (docs/dev/RUN-LOG-mh-1.md).
- Its lockbox months were seen before (the looks from 2024-07-01, 2026-03-31, 2026-04-01, 2026-04-05), so a final check is shown and is not unseen evidence.
- With neural DCA on (shown only): 485 trades, +0.014% a day; random entries with the same waits +0.002% a day (median of 1000), percentile 99.2.

### Logistic regression on clean wins, top 50% (`linear.t1.q50`)

Parameters: {"features": "26: P + v1", "model": "logistic regression, L2 penalty, C = 1, standardised", "rows": "every batch coin's rows before the fold, purged, weighted by uniqueness", "target": "clean win: the profit line before the first DCA level, within 336 hours", "top": "50% of the scores of its own training rows"}.

- R1 as 10 runs of 1000 draws: p from 0.1119 to 0.1628; pooled 0.1441.
- R2 as 10 runs of 1000 draws: p from 0.1319 to 0.1688; pooled 0.1538.
| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2021-07-01T01:00:00Z | 21 | -0.040% a day | -4.65 |
| AVAX | 2022-01-01T01:00:00Z | 21 | -0.039% a day | -4.06 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 62 | +0.057% a day | 6.84 |
| DASH | 2021-01-01T01:00:00Z | 48 | -0.017% a day | -2.47 |
| DOGE | 2021-10-01T01:00:00Z | 28 | -0.004% a day | -0.42 |
| ETH | 2021-01-01T01:00:00Z | 64 | +0.006% a day | 0.75 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 51 | +0.012% a day | 1.57 |
| LTC | 2021-01-01T01:00:00Z | 74 | +0.014% a day | 1.72 |
| SOL | 2021-10-01T01:00:00Z | 76 | +0.031% a day | 3.43 |
| XRP | 2023-10-01T01:00:00Z | 54 | +0.106% a day | 4.51 |
| ZEC | 2021-04-01T01:00:00Z | 61 | +0.004% a day | 0.47 |

- Rising markets: 506 trades, +0.008% a day; falling: 54 trades, -0.002% a day.
- At half the fee rate: 601 trades, +0.010% a day, total profit 12.84.
- At double the fee rate: 446 trades, -0.007% a day, total profit -9.24.
- Not in R2 (stream shorter than twice the shortest move): BNB, HYPE.
- On the hours both cover, against the best untrained rule (`rule.btc50`): +0.006% a day against +0.025% a day; total profit 7.27 against 29.54.
- Pass conditions: above_best_rule no, drawdown no, pbo no, profit_above_0 yes, trades yes; Holm no; screen no.

### Logistic regression on clean wins, top 20% (`linear.t1.q20`)

Parameters: {"features": "26: P + v1", "model": "logistic regression, L2 penalty, C = 1, standardised", "rows": "every batch coin's rows before the fold, purged, weighted by uniqueness", "target": "clean win: the profit line before the first DCA level, within 336 hours", "top": "20% of the scores of its own training rows"}.

- R1 as 10 runs of 1000 draws: p from 0.2078 to 0.2527; pooled 0.2283.
- R2 as 10 runs of 1000 draws: p from 0.2777 to 0.3457; pooled 0.3115.
| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2021-07-01T01:00:00Z | 23 | -0.034% a day | -3.81 |
| AVAX | 2022-01-01T01:00:00Z | 37 | -0.024% a day | -2.41 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 53 | +0.043% a day | 5.17 |
| DASH | 2021-01-01T01:00:00Z | 45 | -0.016% a day | -2.17 |
| DOGE | 2021-10-01T01:00:00Z | 28 | -0.006% a day | -0.66 |
| ETH | 2021-01-01T01:00:00Z | 56 | +0.007% a day | 0.85 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 57 | +0.007% a day | 0.88 |
| LTC | 2021-01-01T01:00:00Z | 38 | -0.019% a day | -2.46 |
| SOL | 2021-10-01T01:00:00Z | 76 | +0.041% a day | 4.23 |
| XRP | 2023-10-01T01:00:00Z | 52 | +0.069% a day | 2.77 |
| ZEC | 2021-04-01T01:00:00Z | 66 | +0.023% a day | 2.62 |

- Rising markets: 466 trades, +0.018% a day; falling: 65 trades, -0.016% a day.
- At half the fee rate: 555 trades, +0.014% a day, total profit 16.21.
- At double the fee rate: 458 trades, -0.008% a day, total profit -9.14.
- Not in R2 (stream shorter than twice the shortest move): BNB, HYPE.
- On the hours both cover, against the best untrained rule (`rule.btc50`): +0.002% a day against +0.025% a day; total profit 2.96 against 29.54.
- Pass conditions: above_best_rule no, drawdown yes, pbo no, profit_above_0 yes, trades yes; Holm no; screen no.

### Gradient-boosted trees on clean wins, top 50% (`trees.t1.q50`)

Parameters: {"early_stopping": false, "features": "26: P + v1", "l2_regularization": 1.0, "learning_rate": 0.05, "max_iter": 300, "max_leaf_nodes": 15, "min_samples_leaf": 200, "model": "histogram gradient-boosted trees", "rows": "every batch coin's rows before the fold, purged, weighted by uniqueness", "target": "clean win: the profit line before the first DCA level, within 336 hours", "top": "50% of the scores of its own training rows"}.

- R1 as 10 runs of 1000 draws: p from 0.6384 to 0.6873; pooled 0.6631.
- R2 as 10 runs of 1000 draws: p from 0.6354 to 0.7083; pooled 0.6737.
| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2021-07-01T01:00:00Z | 25 | -0.012% a day | -1.54 |
| AVAX | 2022-01-01T01:00:00Z | 18 | -0.038% a day | -3.94 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 66 | +0.061% a day | 7.27 |
| DASH | 2021-01-01T01:00:00Z | 52 | -0.018% a day | -2.53 |
| DOGE | 2021-10-01T01:00:00Z | 32 | -0.012% a day | -1.33 |
| ETH | 2021-01-01T01:00:00Z | 55 | +0.011% a day | 1.44 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 46 | -0.000% a day | -0.06 |
| LTC | 2021-01-01T01:00:00Z | 38 | -0.020% a day | -2.53 |
| SOL | 2021-10-01T01:00:00Z | 66 | +0.026% a day | 2.90 |
| XRP | 2023-10-01T01:00:00Z | 64 | +0.110% a day | 4.44 |
| ZEC | 2021-04-01T01:00:00Z | 34 | -0.024% a day | -3.09 |

- Rising markets: 476 trades, -0.000% a day; falling: 20 trades, +0.021% a day.
- At half the fee rate: 531 trades, +0.008% a day, total profit 10.00.
- At double the fee rate: 417 trades, -0.011% a day, total profit -13.69.
- Not in R2 (stream shorter than twice the shortest move): BNB, HYPE.
- On the hours both cover, against the best untrained rule (`rule.btc50`): -0.001% a day against +0.025% a day; total profit -0.98 against 29.54.
- Pass conditions: above_best_rule no, drawdown no, pbo no, profit_above_0 yes, trades yes; Holm no; screen no.

### Gradient-boosted trees on clean wins, top 20% (`trees.t1.q20`)

Parameters: {"early_stopping": false, "features": "26: P + v1", "l2_regularization": 1.0, "learning_rate": 0.05, "max_iter": 300, "max_leaf_nodes": 15, "min_samples_leaf": 200, "model": "histogram gradient-boosted trees", "rows": "every batch coin's rows before the fold, purged, weighted by uniqueness", "target": "clean win: the profit line before the first DCA level, within 336 hours", "top": "20% of the scores of its own training rows"}.

- R1 as 10 runs of 1000 draws: p from 0.7243 to 0.7752; pooled 0.7511.
- R2 as 10 runs of 1000 draws: p from 0.7393 to 0.7922; pooled 0.7708.
| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2021-07-01T01:00:00Z | 21 | -0.021% a day | -2.67 |
| AVAX | 2022-01-01T01:00:00Z | 35 | -0.016% a day | -1.61 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 49 | +0.052% a day | 6.02 |
| DASH | 2021-01-01T01:00:00Z | 24 | -0.041% a day | -5.69 |
| DOGE | 2021-10-01T01:00:00Z | 18 | -0.023% a day | -2.44 |
| ETH | 2021-01-01T01:00:00Z | 38 | -0.001% a day | -0.07 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 31 | -0.000% a day | -0.02 |
| LTC | 2021-01-01T01:00:00Z | 25 | -0.023% a day | -2.87 |
| SOL | 2021-10-01T01:00:00Z | 76 | +0.078% a day | 7.60 |
| XRP | 2023-10-01T01:00:00Z | 45 | +0.052% a day | 2.07 |
| ZEC | 2021-04-01T01:00:00Z | 24 | -0.037% a day | -4.40 |

- Rising markets: 336 trades, +0.005% a day; falling: 50 trades, -0.024% a day.
- At half the fee rate: 411 trades, +0.003% a day, total profit 3.21.
- At double the fee rate: 331 trades, -0.016% a day, total profit -20.04.
- Not in R2 (stream shorter than twice the shortest move): BNB, HYPE.
- On the hours both cover, against the best untrained rule (`rule.btc50`): -0.006% a day against +0.025% a day; total profit -7.23 against 29.54.
- Pass conditions: above_best_rule no, drawdown no, pbo no, profit_above_0 no, trades yes; Holm no; screen no.

### Gradient-boosted trees on return per day held, top 50% (`trees.t2.q50`)

Parameters: {"early_stopping": false, "features": "26: P + v1", "l2_regularization": 1.0, "learning_rate": 0.05, "max_iter": 300, "max_leaf_nodes": 15, "min_samples_leaf": 200, "model": "histogram gradient-boosted trees", "rows": "every batch coin's rows before the fold, purged, weighted by uniqueness", "target": "return per day held of the replayed trade, 30 days at most", "top": "50% of the scores of its own training rows"}.

- R1 as 10 runs of 1000 draws: p from 0.4166 to 0.4446; pooled 0.4281.
- R2 as 10 runs of 1000 draws: p from 0.3017 to 0.3367; pooled 0.3214.
| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2021-07-01T01:00:00Z | 26 | -0.008% a day | -1.03 |
| AVAX | 2022-01-01T01:00:00Z | 20 | -0.039% a day | -4.08 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 60 | +0.058% a day | 6.57 |
| DASH | 2021-01-01T01:00:00Z | 48 | -0.018% a day | -2.62 |
| DOGE | 2021-10-01T01:00:00Z | 27 | -0.003% a day | -0.38 |
| ETH | 2021-01-01T01:00:00Z | 73 | +0.005% a day | 0.58 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 56 | +0.010% a day | 1.26 |
| LTC | 2021-01-01T01:00:00Z | 47 | -0.008% a day | -1.08 |
| SOL | 2021-10-01T01:00:00Z | 66 | +0.028% a day | 3.12 |
| XRP | 2023-10-01T01:00:00Z | 67 | +0.126% a day | 5.16 |
| ZEC | 2021-04-01T01:00:00Z | 32 | -0.022% a day | -2.89 |

- Rising markets: 500 trades, +0.002% a day; falling: 22 trades, +0.031% a day.
- At half the fee rate: 593 trades, +0.010% a day, total profit 12.98.
- At double the fee rate: 456 trades, -0.006% a day, total profit -7.95.
- Not in R2 (stream shorter than twice the shortest move): BNB, HYPE.
- On the hours both cover, against the best untrained rule (`rule.btc50`): +0.003% a day against +0.025% a day; total profit 3.34 against 29.54.
- Pass conditions: above_best_rule no, drawdown yes, pbo no, profit_above_0 yes, trades yes; Holm no; screen no.

### Gradient-boosted trees on return per day held, top 20% (`trees.t2.q20`)

Parameters: {"early_stopping": false, "features": "26: P + v1", "l2_regularization": 1.0, "learning_rate": 0.05, "max_iter": 300, "max_leaf_nodes": 15, "min_samples_leaf": 200, "model": "histogram gradient-boosted trees", "rows": "every batch coin's rows before the fold, purged, weighted by uniqueness", "target": "return per day held of the replayed trade, 30 days at most", "top": "20% of the scores of its own training rows"}.

- R1 as 10 runs of 1000 draws: p from 0.1359 to 0.1768; pooled 0.1532.
- R2 as 10 runs of 1000 draws: p from 0.4016 to 0.4466; pooled 0.4237.
| Coin | Joined | Trades | Return per day held | Total profit |
|---|---|---|---|---|
| ADA | 2021-07-01T01:00:00Z | 35 | -0.004% a day | -0.49 |
| AVAX | 2022-01-01T01:00:00Z | 19 | -0.039% a day | -3.91 |
| BNB | never | 0 | n/a | 0.00 |
| BTC | 2021-01-01T01:00:00Z | 54 | +0.192% a day | 5.76 |
| DASH | 2021-01-01T01:00:00Z | 56 | -0.013% a day | -1.84 |
| DOGE | 2021-10-01T01:00:00Z | 21 | -0.007% a day | -0.73 |
| ETH | 2021-01-01T01:00:00Z | 59 | -0.004% a day | -0.43 |
| HYPE | never | 0 | n/a | 0.00 |
| LINK | 2021-01-01T01:00:00Z | 54 | +0.003% a day | 0.40 |
| LTC | 2021-01-01T01:00:00Z | 46 | -0.016% a day | -2.08 |
| SOL | 2021-10-01T01:00:00Z | 72 | +0.037% a day | 3.88 |
| XRP | 2023-10-01T01:00:00Z | 61 | +0.113% a day | 4.35 |
| ZEC | 2021-04-01T01:00:00Z | 32 | -0.016% a day | -2.15 |

- Rising markets: 458 trades, +0.002% a day; falling: 51 trades, +0.004% a day.
- At half the fee rate: 563 trades, +0.008% a day, total profit 9.71.
- At double the fee rate: 455 trades, -0.010% a day, total profit -11.81.
- Not in R2 (stream shorter than twice the shortest move): BNB, HYPE.
- On the hours both cover, against the best untrained rule (`rule.btc50`): +0.002% a day against +0.025% a day; total profit 2.18 against 29.54.
- Pass conditions: above_best_rule no, drawdown yes, pbo no, profit_above_0 yes, trades yes; Holm no; screen no.
