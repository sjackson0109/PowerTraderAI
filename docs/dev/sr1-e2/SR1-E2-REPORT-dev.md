# SR1-E2: the Donchian ensemble, development report

> **Development only: not evidence for enabling anything.** SR1-E2 read the development period only (2021-01-01 to 2025-05-06). These months had already been looked at for this book (section 3, earlier exposures). The lockbox (2025-05-06 to 2026-11-06) was not opened. Nothing is activated, promoted or enabled by this report.

## 1. Power (before the result)

Each member at Holm's first level (5% / 2) and 80% power; the hold comparison one-sided at 5%. The lockbox projections assume the same daily spread over its 549 days (against 1586 here).

| Test | Smallest detectable effect | On the lockbox's months | Notes |
|---|---|---|---|
| B1: the book against random entries | +0.2184% a capital-day | about 218 trades | random median +0.2981%; too few to tell if it does not pass: yes |
| B2: return per capital-day above 0 | +0.7626% a capital-day | +1.2961% a capital-day | studentised stationary bootstrap's standard error |
| The hold comparison (shown) | +0.525 a year (log return) | +0.892 a year | mean daily log-return difference x 365 |

## 2. Verdicts

One family, B (K = 2), corrected by Holm at 5%. The trading line compares with random entries; only the economic line can say "profitable".

| Member | Outcome | p (pooled) | p in each run | Holm-adjusted p | p passes Holm |
|---|---|---|---|---|---|
| B1 | Too few trades to tell | 0.1549 | 0.1144 to 0.1841 | 0.1935 | no |
| B2 | Fail | 0.0967 | 0.0850 to 0.1064 | 0.1935 | no |

- **B1.** Too few trades to tell: this test could only see an edge above +0.2184% a capital-day (return per capital-day +0.3751% against a random median of +0.2981%, p = 0.1549 (Holm over 2, B = 2,000), 630 trades). Development only: not evidence for enabling anything.
- **B2.** Not shown to be profitable after fees. The book failed the requirement that its bootstrap test of return per capital-day passes Holm (p = 0.0967). Figures: net $+36,983.30 on £10,000, return per capital-day +0.3751%, 630 trades, maximum drawdown 47.26% at the bars' lows, against the equal-weight hold's 74.55%, smallest detectable return per capital-day +0.7626%. The book reached the trader's 8% halt on 2021-01-12: trading it would need the halt changed. Development only: not evidence for enabling anything.

**Finalist:** no. The ensemble is not a finalist, and the lockbox stays closed.

**The halt:** The book reached the trader's 8% halt on 2021-01-12: trading it would need the halt changed. That is at the bars' lows; at the closes it was 2021-01-22. The halt is reported, not modelled: the replay keeps trading after it, as the registration declared (D1).

## 3. Registration

- **Record:** `SR1-E2`, frozen 2026-11-14T19:37:25.667668+00:00, SHA-256 `f3caa70d9b2cb80328b787dbff9a946ed0eb963291308d4efcbf18643514cd4a`; the approved design's SHA-256 `de4c2057797408a8acd4f90a3d81855bf56076ace137133d49365bec7c407c80`. Every member, seed, cost, account and rule was fixed there before anything was scored.
- **Code:** 82 files' SHA-256s, including the ensemble, STRAT-007, the sizing, the gap rule and the research statistics.
- **GBP/USD:** 1.3238 (Bank of England Database, series XUDLUSS (spot exchange rate, US$ into sterling), 2026-11-12; retrieved 2026-11-14T18:57:33.160588+00:00). Checked against European Central Bank euro foreign exchange reference rates (USD per EUR / GBP per EUR): 1.32556, a difference of 0.133%.
- **Accounts:** £10,000 = $13,238.00, £500 = $661.90, £50 = $66.19; £10,000 decides.
- **Costs:** 0.50% taker + 0.05% slippage a fill (the owner's account taker rate on Coinbase, 0.50% (E1's E-D10, from the check window on 2026-11-05), as the registration's section 4 sets). Venue rules for 9 coins, the exchange layer's public product data, primary first, read 2026-11-14T19:37:25.645870+00:00.
- **Candles:** 9 series, from coinbase, kucoin (Settings order: coinbase, kraken, kucoin, binance), offline, each read once. Coins: BNB, BTC, DASH, DOGE, ETH, HYPE, SOL, XRP, ZEC. Left out: none.
- **Earlier exposures** (recorded before the run): PR #291, the ensemble exploration of 2026-11-13: the book, each member alone and volatility sizing at 25% a year, on these nine coins and months; PR #300, O18's runs at 50% and 75% a year, of STRAT-004 and of this book; PR #257, the nine-coin comparison: STRAT-004 and others, not STRAT-007, on the same months and coins; the exploration sandbox's trial log, 84 lines, 38 of them explorations.
- **Run:** 961.9 s. Trials logged by kind: sizing 3, strategy 16.

## 4. The book against the equal-weight hold (£10,000)

|  | Trades | Net $ | RPCD | Return | Max DD (closes) | Max DD (lows) | Mean committed | Skipped: cash | Skipped: minimum |
|---|---|---|---|---|---|---|---|---|---|
| The book | 630 | +36,983.30 | +0.3751% | +279.37% | 42.2% | 47.3% | 18.9% | 62 | 0 |
| Equal-weight hold | 9 | +32,518.01 | +0.1921% | +245.64% | 72.2% | 74.5% | 36.3% | 0 | 0 |

- **Drawdown (D1):** the book's 47.3% against the hold's 74.5%, each at the bars' lows from a peak at the earlier bars' highs (at the closes: 42.2% and 72.2%).
- **Halves (by entry day):** 281 and 349 trades; net +11,360.68 and +25,622.62.
- **Without the most profitable coin** (BNB, every member's trades on it summed): +25,854.00.
- **The hold** buys each of the 9 coins with its own 1/N of the starting account ($1,470.89) at its first decision bar; a late-listed coin's share waits as cash until then. Every coin was bought.

### The yearly lead over the hold (shown, D3)

Mean daily log-return difference (book less hold) x 365: +0.021; studentised stationary bootstrap (mean block 6.6 days), 10 runs of 2,000: p = 0.4589, 95% interval (median of the runs' bounds) -0.369 to +0.442; 48.9% of 1586 days ahead. Benjamini-Hochberg flag: no.

### By year and by member

| Year | Trades | Net $ | RPCD |
|---|---|---|---|
| 2021 | 144 | +14,226.33 | +0.7285% |
| 2022 | 98 | -2,932.95 | -0.5135% |
| 2023 | 183 | +10,448.56 | +0.3052% |
| 2024 | 168 | +17,571.30 | +0.4971% |
| 2025 | 37 | -2,329.94 | -0.6173% |

| Member (days) | Trades | Net $ | RPCD |
|---|---|---|---|
| 20 | 235 | +6,921.27 | +0.3938% |
| 30 | 164 | +7,087.91 | +0.4434% |
| 60 | 91 | +5,720.92 | +0.3645% |
| 90 | 61 | +4,698.87 | +0.3374% |
| 150 | 38 | +4,259.76 | +0.3532% |
| 250 | 24 | +3,619.79 | +0.3199% |
| 360 | 17 | +4,674.78 | +0.3881% |

| Coin | Trades | Net $ | RPCD |
|---|---|---|---|
| BNB | 89 | +11,129.30 | +0.6953% |
| BTC | 105 | +2,280.95 | +0.1098% |
| DASH | 89 | -473.77 | -0.0591% |
| DOGE | 74 | +2,552.39 | +0.2776% |
| ETH | 85 | +3,261.12 | +0.2072% |
| HYPE | 5 | -57.29 | -0.1643% |
| SOL | 71 | +10,412.40 | +0.8076% |
| XRP | 33 | +8,755.24 | +1.2791% |
| ZEC | 79 | -877.05 | -0.0997% |

## 5. Random entries for the book (B1) and matched holding (shown)

- **REF-RANDOM-E:** 2,000 draws (10 runs of 200). Return per capital-day: the book +0.3751%, the draws' median +0.2981% (5th to 95th percentile +0.1584% to +0.4139%); 15.4% of draws at or above the book. Entries wanted 630, reached (median) 630; 0 draws ran out of bars before their last entry.
- **Matched holding** (reported only): 2,000 draws; median return per capital-day +0.1546%; 0.0% at or above the book; median drawdown at the lows 28.9%, 100.0% at or below the book's; 0 of 1,260,000 holds found no place.

## 6. Each member alone (the coin's whole allocation; shown)

|  | Trades | Net $ | RPCD | Return | Max DD (closes) | Max DD (lows) | Mean committed | Skipped: cash | Skipped: minimum | Trades a coin a year | DD below the hold's | p (RPCD > 0) | BH |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 20 days | 237 | +50,781.24 | +0.3517% | +383.60% | 36.0% | 40.9% | 24.1% | 0 | 0 | 6.1 | yes | 0.0362 | no |
| 30 days | 165 | +56,039.42 | +0.4128% | +423.32% | 30.0% | 34.8% | 22.0% | 3 | 0 | 4.2 | yes | 0.0251 | no |
| 60 days | 91 | +36,180.35 | +0.3629% | +273.31% | 52.1% | 54.8% | 21.4% | 0 | 0 | 2.3 | yes | 0.1311 | no |
| 90 days | 62 | +25,748.07 | +0.3369% | +194.50% | 64.0% | 66.0% | 18.7% | 5 | 0 | 1.6 | yes | 0.2109 | no |
| 150 days | 40 | +25,668.65 | +0.3259% | +193.90% | 52.9% | 54.2% | 16.1% | 5 | 0 | 1.0 | yes | 0.2182 | no |
| 250 days | 27 | +21,365.01 | +0.2763% | +161.39% | 51.9% | 54.5% | 15.2% | 6 | 0 | 0.7 | yes | 0.2501 | no |
| 360 days | 17 | +32,342.82 | +0.3935% | +244.32% | 49.2% | 53.8% | 14.6% | 5 | 0 | 0.4 | yes | 0.1732 | no |

## 7. Volatility-sized books (shown; the book's own sizing decides, D4)

|  | Trades | Net $ | RPCD | Return | Max DD (closes) | Max DD (lows) | Mean committed | Skipped: cash | Skipped: minimum | Mean scale | DD below the hold's | p (RPCD > 0) | BH |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| volatility 25% | 647 | +9,215.80 | +0.3880% | +69.62% | 22.3% | 23.9% | 8.0% | 0 | 0 | 0.35 | yes | 0.0908 | no |
| volatility 50% | 647 | +20,627.06 | +0.3669% | +155.82% | 34.3% | 36.0% | 14.4% | 0 | 0 | 0.67 | yes | 0.0872 | no |
| volatility 75% | 636 | +32,239.47 | +0.3870% | +243.54% | 40.8% | 43.6% | 17.5% | 35 | 0 | 0.85 | yes | 0.0874 | no |

## 8. Probability of backtest overfitting (shown)

CSCV over 16 equal blocks of days, each scored by its marked profit over its capital-days, across 8 contestants (the seven members alone and the book): PBO = 0.930.

## 9. Robustness (shown, never deciding)

|  | Trades | Net $ | RPCD | Return | Max DD (closes) | Max DD (lows) | Mean committed | Skipped: cash | Skipped: minimum | Coins | Hold's DD (lows) | DD below the hold's | p (RPCD > 0) | BH |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fees at 1.20% | 630 | +30,023.25 | +0.3304% | +226.80% | 46.1% | 48.2% | 19.0% | 66 | 0 | BNB, BTC, DASH, DOGE, ETH, HYPE, SOL, XRP, ZEC | 74.5% | yes | 0.1397 | no |
| BTC and ETH only | 142 | +8,466.44 | +0.1298% | +63.96% | 22.7% | 24.2% | 22.2% | 663 | 0 | BTC, ETH | 80.0% | yes | 0.1584 | no |
| coins with bars from 2021-01-01 | 414 | +32,486.12 | +0.2189% | +245.40% | 50.8% | 51.9% | 24.5% | 223 | 0 | BNB, BTC, DASH, ETH, ZEC | 78.4% | yes | 0.1812 | no |
| the second exchange in Settings order | not run |  |  |  |  |  |  |  |  | kraken's cache has no development bars for these coins |  |  |  |  |
| £500 | 630 | +1,848.50 | +0.3749% | +279.27% | 42.2% | 47.3% | 18.9% | 62 | 0 | BNB, BTC, DASH, DOGE, ETH, HYPE, SOL, XRP, ZEC | 74.5% | yes | 0.0962 | no |
| £50 | 630 | +184.14 | +0.3737% | +278.20% | 42.3% | 47.3% | 18.9% | 66 | 0 | BNB, BTC, DASH, DOGE, ETH, HYPE, SOL, XRP, ZEC | 74.5% | yes | 0.0959 | no |

- **fees at 1.20%:** Coinbase's published taker rate, with the same slippage
- **the second exchange in Settings order:** the coins its cache holds development bars for, at the same fees and minimums
- **£50:** each slice is 1/7 of a coin's 1/N of the account: the skips show how many fell below the venue's minimums
- **£500:** each slice is 1/7 of a coin's 1/N of the account: the skips show how many fell below the venue's minimums

## 10. The 8% halt (reported, not modelled)

|  | First reached (lows) | First reached (closes) |
|---|---|---|
| The book | 2021-01-12 | 2021-01-22 |
| Equal-weight hold | 2021-01-09 | 2021-01-22 |

Trading the book as configured would need the trader's halt changed. For this evaluation only, the registration replaced F3's halt requirement by the comparison with the hold (D1).

## 11. Limits

- **Not unseen evidence.** These months were explored for this book before (section 3).
- **One market history and survivorship:** today's coins; the BTC and ETH and the listed-by-2021 rows are shown for that reason.
- **Venue rules** are today's; fees are assumed proportional with no fixed fee.
- **The halt is reported, not modelled**, and fills at the next open differ from paper and live fills.

## 12. Recommendation

<!-- written after the results were read -->

- **The ensemble is not a finalist, and the lockbox stays closed**, as the registration declared. Neither member passed.
  - **B1** (the book against random entries with each member's own exits): too few trades to tell. 15.4% of 2,000 random draws did as well, and the test could only see an edge above +0.22% a capital-day.
  - **B2** met every economic requirement except its profit test (p = 0.097; 0.19 after Holm). That includes D1's: the book's largest fall at the lows was 47%, against the hold's 75%.
- **No more registered spend on this book on these months.** Another look at the same months would be fitting them. PBO across the seven members and the book is 0.93, so picking the 20- or 30-day member from section 6 would most likely pick noise.
- **What the shown figures suggest (hypotheses only, not findings):**
  - **Matched holding:** random entries held as long as the book's trades never reached the book's return per capital-day, in 2,000 draws.
  - **Random entries:** with the members' own exits, they did so in 15% of draws.
  - **Together:** whatever the book has seems to come from its exits (the midline stop), not its entries. That would need a new declared test on new months.
- **The halt:** fully invested, the book reaches the trader's 8% halt in its first month (2021-01-12 at the lows). Any future use needs a decision on the halt, or a sizing that keeps the fall within it, made before seeing new data.
- **STRAT-007 and OVL-MIDLINE stay at `research`.** Nothing here supports paper or live use.
- **The first freeze was void** (`void-1/`):
  - **The record:** `0ee98507…`, 2026-11-14 18:58 UTC.
  - **What went wrong:** it left BNB and HYPE out, because the cache lookup named KuCoin's files by the dollar pair. It was never run, and nothing was scored or logged.
  - **The fix:** PR #314 corrected the lookup and made a missing declared coin refuse the freeze.
  - **This record** (`f3caa70d…`) was frozen afterwards, on `main` at `b8eb618`.
