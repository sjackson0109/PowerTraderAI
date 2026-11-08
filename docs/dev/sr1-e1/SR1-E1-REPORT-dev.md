# FDS-SR-001 E1: development report

> **Development only: not evidence for enabling anything.** E1 read the development period only (2021-01-01 to 2025-05-06). The lockbox (2025-05-06 to 2026-11-06) was not opened. No strategy, gate or model is activated, promoted or enabled by this report.

## 1. Verdicts

Three families, each corrected on its own by Holm at 5% (E-D11). Trading lines compare against random baselines; only an economic line can say "profitable".

### Family S: Strategies alone (K = 4)

| Member | Question | Outcome | p (pooled) | p in each run | p passes Holm |
|---|---|---|---|---|---|
| S1 | Does STRAT-004 time its entries better than random entries with its own exits? | Pass | 0.0065 | 0.0040 to 0.0110 | yes |
| S2 | Does STRAT-005 time its entries better than random entries with its own exits? | Too few trades to tell | 0.1836 | 0.1628 to 0.2118 | no |
| S3 | Is STRAT-004 profitable after fees at £10,000 and 0.50% + 0.05%? | Fail | 0.0086 | 0.0050 to 0.0140 | yes |
| S4 | Is STRAT-005 profitable after fees at £10,000 and 0.50% + 0.05%? | Fail | 0.0001 | 0.0010 to 0.0010 | yes |

For S3 and S4 the day-block bootstrap is the family member, and "p passes Holm" is about it alone. The outcome also needs every condition of FDS-SIG-004 F3; the line names the one that failed. With blocks of 896 days (section 2) that bootstrap carries little information.

- **S1.** Beats random entries (return per capital-day +0.2882% against a random median of +0.0104%, p = 0.0065 (Holm over 4, B = 10,000), 135 trades). Development only: not evidence for enabling anything.
- **S2.** Too few trades to tell: this test could only see an edge above +0.2087% a capital-day (return per capital-day +0.1683% against a random median of +0.1094%, p = 0.1836 (Holm over 4, B = 10,000), 151 trades). Development only: not evidence for enabling anything.
- **S3.** Not shown to be profitable after fees: a profit in each half (net $+1,692.94 on £10,000, return per capital-day +0.2882%, 135 trades, maximum drawdown 7.32%, p = 0.0086 (Holm over 4), smallest detectable return per capital-day +0.5595%). Development only: not evidence for enabling anything.
- **S4.** Not shown to be profitable after fees: a drawdown below the halt level (net $+1,528.33 on £10,000, return per capital-day +0.1683%, 151 trades, maximum drawdown 10.14%, p = 0.0001 (Holm over 4), smallest detectable return per capital-day +0.2586%). Development only: not evidence for enabling anything.

### Family G: The regime gate (K = 3)

| Member | Question | Outcome | p (pooled) | p in each run | p passes Holm |
|---|---|---|---|---|---|
| G1 | Does the regime gate add value to STRAT-001 over random vetoes? | Fail | 0.1827 | 0.1638 to 0.2028 | no |
| G2 | Does the regime gate add value to STRAT-004 over random vetoes? | Pass | 0.0001 | 0.0010 to 0.0010 | yes |
| G3 | Does the regime gate add value to STRAT-005 over random vetoes? | Pass | 0.0126 | 0.0090 to 0.0190 | yes |

- **G1.** No better than random vetoes (return per capital-day -1.3641% against a random median of -1.4247%, p = 0.1827 (Holm over 3, B = 10,000), 3851 trades; smallest detectable edge +0.2026% a capital-day). Development only: not evidence for enabling anything.
- **G2.** The gate adds value over random vetoes (return per capital-day +0.3929% against a random median of +0.2785%, p = 0.0001 (Holm over 3, B = 10,000), 111 trades). Development only: not evidence for enabling anything.
- **G3.** The gate adds value over random vetoes (return per capital-day +0.1907% against a random median of +0.1422%, p = 0.0126 (Holm over 3, B = 10,000), 114 trades). Development only: not evidence for enabling anything.

### Family M: Models with strategies (K = 2)

| Member | Question | Outcome | p (pooled) | p in each run | p passes Holm |
|---|---|---|---|---|---|
| M1 | Does the PV model's veto improve STRAT-004's entries over random vetoes? | Pass | 0.0011 | 0.0010 to 0.0030 | yes |
| M2 | Does the PV model's veto improve STRAT-005's entries over random vetoes? | Pass | 0.0255 | 0.0210 to 0.0360 | yes |

- **M1.** The model adds value over random vetoes (return per capital-day +0.3877% against a random median of +0.3085%, p = 0.0011 (Holm over 2, B = 10,000), 104 trades). Development only: not evidence for enabling anything.
- **M2.** The model adds value over random vetoes (return per capital-day +0.2052% against a random median of +0.1546%, p = 0.0255 (Holm over 2, B = 10,000), 99 trades). Development only: not evidence for enabling anything.

## 2. Registration

- **Record:** `SR1-E1`, frozen 2026-11-08T12:38:00.703293+00:00, SHA-256 `ba060bb6006ec8620dcc96a4357c673ea58318248bdce216ae0b0eff092acecb`. Every member, seed, cost, account and rule was fixed there before anything was scored.
- **GBP/USD:** 1.3476 (Bank of England Database, series XUDLUSS (spot exchange rate, US$ into sterling), 2026-11-05; retrieved 2026-11-08T12:18:57.506361+00:00). Checked against the European Central Bank euro foreign exchange reference rates (USD per EUR / GBP per EUR): 1.34592 on the same day, a difference of 0.125% (tolerance 0.25%).
- **Accounts:** £10,000 = $13,476.00, £500 = $673.80, £50 = $67.38; £10,000 decides. Sizing: 1.0% entries raised to the minimum entry, 10.0% a coin, halt at 8.0% (reported, not modelled).
- **Costs:** 0.50% taker + 0.05% slippage a fill (the owner's account taker rate on Coinbase, 0.50% (E-D10; FDS-MH-001 section 7, from the check window on 2026-11-05)). Shown: taker 1.20% (Coinbase's published taker rate); maker 0.60% (hypothetical) (a limit-order scenario only: the orders stay market orders, which are not filled at a maker rate).
- **Venue rules:** minimum orders and sell steps for 11 coins, read 2026-11-08T12:38:00.671185+00:00 (today's values; past values are not recorded).
- **Candles:** 44 series from coinbase (Settings order: coinbase, kraken, kucoin, binance), offline, each read once. Coins with development bars: ADA, AVAX, BTC, DASH, DOGE, ETH, LINK, LTC, SOL, XRP, ZEC. Left out: BNB:12h (BNB-USD 12h: no cached bars); BNB:1d (BNB-USD 1d: no cached bars); BNB:1h (BNB-USD 1h: no cached bars); BNB:4h (BNB-USD 4h: no cached bars); HYPE:12h (HYPE-USD 12h: no cached bars); HYPE:1d (HYPE-USD 1d: no cached bars); HYPE:1h (HYPE-USD 1h: no cached bars); HYPE:4h (HYPE-USD 4h: no cached bars).
- **Model probabilities:** batch 20261107-175558, `pv.linear.t1.P.q50` `fab539dda03b…`, `pv.linear.t1.PV.q50` `ce72439610a9…` (matching docs/dev/RUN-LOG-sig4-1.md).
- **Day blocks:** family S: 896 days by section 6.0's rule in 1,586 days, 1.8 blocks. Its 95% intervals (return per capital-day): S3 -0.0888% to +0.5232%; S4 -0.0125% to +0.2548%.
- **Run:** 9557.7 s. Trials logged by kind: calibration 1, gate 11, model 10, strategy 24.

## 3. Each strategy at £10,000, against the baselines

| Strategy | Bars | Trades | Net $ | Net £ | RPCD | Return | Max DD | In market | REF-HOLD net $ | REF-HOLD RPCD | REF-RANDOM median RPCD | p vs random |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| STRAT-000 | 1h | 3535 | -1,944.43 | -1,442.88 | -0.1756% | -14.43% | 19.6% | 94.0% | +1,773.03 | +0.0766% | -1.0904% | 0.0010 |
| STRAT-001 | 1h | 6829 | -7,045.11 | -5,227.90 | -1.4237% | -52.28% | 52.8% | 69.6% | +1,780.02 | +0.0769% | -3.4413% | 0.0010 |
| STRAT-002 | 4h | 1036 | +1,008.33 | +748.24 | +0.0950% | +7.48% | 8.8% | 81.2% | +948.18 | +0.0434% | -0.0762% | 0.0020 |
| STRAT-004 | 1d | 135 | +1,692.94 | +1,256.27 | +0.2882% | +12.56% | 7.3% | 62.8% | +799.68 | +0.0369% | +0.0104% | 0.0065 |
| STRAT-005 | 1d | 151 | +1,528.33 | +1,134.11 | +0.1683% | +11.34% | 10.1% | 83.1% | +1,271.36 | +0.0686% | +0.1094% | 0.1836 |

RPCD is return per capital-day: summed net over summed (amount × days held). REF-CASH is 0 throughout. REF-HOLD buys each coin once at the strategy's first decision bar (so it differs with each strategy's warm-up), sized like a trade (1% of the account), and holds it to the end, so its dollar figures are small; compare RPCD.

### Trades, holding and capital

| Strategy | Candidates | Trades | By half | Net by half $ | Median days | 90th pct days | Win rate | Largest loss $ | Mean committed | Peak committed | DD recovery days |
|---|---|---|---|---|---|---|---|---|---|---|---|
| STRAT-000 | 3535 | 3535 | 1607 / 1928 | -888.12 / -1,056.30 | 1.5 | 5.0 | 23.9% | -26.29 | 5.53% | 11.16% | not recovered |
| STRAT-001 | 6829 | 6829 | 3213 / 3616 | -3,838.54 / -3,206.57 | 0.6 | 1.6 | 26.2% | -20.01 | 3.23% | 11.06% | not recovered |
| STRAT-002 | 1036 | 1036 | 466 / 570 | +593.25 / +415.07 | 5.3 | 15.3 | 32.9% | -38.41 | 4.72% | 11.09% | 1173 |
| STRAT-004 | 1002 | 135 | 68 / 67 | -116.89 / +1,809.83 | 26.0 | 61.2 | 38.5% | -73.63 | 2.64% | 10.95% | 756 |
| STRAT-005 | 927 | 151 | 53 / 98 | +174.18 / +1,354.15 | 21.0 | 133.0 | 35.8% | -55.88 | 3.97% | 10.88% | 1025 |

## 4. The three accounts (E-D5)

The same candles, candidate trades and period at each size; each account has its own minimum entries, sell rounding, cash and halt level.

| Strategy | Account | Trades | Net $ | Net £ | RPCD | Return | Max DD | Raised | No cash | Below min | Unsold $ | p vs random |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| STRAT-000 | £10,000 | 3535 | -1,944.43 | -1,442.88 | -0.1756% | -14.43% | 19.6% | 0 | 0 | 0 | +26.62 | 0.0010 |
| STRAT-000 | £500 | 3535 | -125.36 | -93.03 | -0.2272% | -18.61% | 20.8% | 0 | 0 | 0 | +27.45 | n/a |
| STRAT-000 | £50 | 3535 | -45.08 | -33.45 | -0.4999% | -66.90% | 50.1% | 3535 | 0 | 0 | +26.61 | n/a |
| STRAT-001 | £10,000 | 6829 | -7,045.11 | -5,227.90 | -1.4237% | -52.28% | 52.8% | 0 | 0 | 0 | +53.58 | 0.0010 |
| STRAT-001 | £500 | 6829 | -406.66 | -301.76 | -1.6598% | -60.35% | 54.9% | 0 | 0 | 0 | +54.69 | n/a |
| STRAT-001 | £50 | 2977 | -66.36 | -49.24 | -2.9562% | -98.49% | 85.4% | 2977 | 3852 | 0 | +26.49 | n/a |
| STRAT-002 | £10,000 | 1036 | +1,008.33 | +748.24 | +0.0950% | +7.48% | 8.8% | 0 | 0 | 0 | +8.70 | 0.0020 |
| STRAT-002 | £500 | 1036 | +41.47 | +30.77 | +0.0783% | +6.15% | 9.4% | 0 | 0 | 0 | +8.63 | n/a |
| STRAT-002 | £50 | 1036 | -1.25 | -0.93 | -0.0162% | -1.85% | 20.2% | 1036 | 0 | 0 | +8.66 | n/a |
| STRAT-004 | £10,000 | 135 | +1,692.94 | +1,256.27 | +0.2882% | +12.56% | 7.3% | 0 | 0 | 0 | +1.09 | 0.0065 |
| STRAT-004 | £500 | 135 | +83.81 | +62.19 | +0.2854% | +12.44% | 7.4% | 0 | 0 | 0 | +0.87 | 0.0070 |
| STRAT-004 | £50 | 135 | +11.43 | +8.48 | +0.2607% | +16.97% | 11.7% | 135 | 0 | 0 | +1.12 | 0.0070 |
| STRAT-005 | £10,000 | 151 | +1,528.33 | +1,134.11 | +0.1683% | +11.34% | 10.1% | 0 | 0 | 0 | +1.27 | 0.1836 |
| STRAT-005 | £500 | 151 | +75.20 | +55.81 | +0.1656% | +11.16% | 10.2% | 0 | 0 | 0 | +1.55 | 0.1778 |
| STRAT-005 | £50 | 151 | +10.12 | +7.51 | +0.1512% | +15.02% | 14.9% | 151 | 0 | 0 | +1.53 | 0.1548 |

## 5. By coin, year and market regime (£10,000)

### STRAT-004

| Coin | Trades | Net $ | RPCD |
|---|---|---|---|
| ADA | 12 | +142.71 | +0.3178% |
| AVAX | 8 | +299.70 | +0.8764% |
| BTC | 16 | +162.26 | +0.2045% |
| DASH | 14 | -110.29 | -0.2149% |
| DOGE | 9 | +313.41 | +0.6655% |
| ETH | 15 | +207.12 | +0.2764% |
| LINK | 14 | +20.85 | +0.0369% |
| LTC | 17 | -231.01 | -0.3676% |
| SOL | 11 | +769.63 | +1.3389% |
| XRP | 6 | +223.54 | +1.0855% |
| ZEC | 13 | -104.98 | -0.1804% |

| Breakdown | Bucket | Trades | Net $ | RPCD |
|---|---|---|---|---|
| Year | 2021 | 30 | +396.03 | +0.2546% |
| Year | 2022 | 24 | -517.98 | -1.0209% |
| Year | 2023 | 41 | +794.12 | +0.4144% |
| Year | 2024 | 34 | +1,215.06 | +0.7029% |
| Year | 2025 | 6 | -194.28 | -1.1642% |
| BTC against its 200-day average | above | 100 | +1,958.20 | +0.4141% |
| BTC against its 200-day average | below | 35 | -265.25 | -0.2316% |
| BTC's 200-day average over 30 days | falling | 39 | -276.20 | -0.2094% |
| BTC's 200-day average over 30 days | rising | 96 | +1,969.15 | +0.4322% |
| The coin's 30-day volatility (terciles) | high | 45 | +1.49 | +0.0008% |
| The coin's 30-day volatility (terciles) | low | 45 | +462.31 | +0.2212% |
| The coin's 30-day volatility (terciles) | middle | 45 | +1,229.14 | +0.6660% |

### STRAT-005

| Coin | Trades | Net $ | RPCD |
|---|---|---|---|
| ADA | 12 | -120.03 | -0.2081% |
| AVAX | 9 | +246.17 | +0.4619% |
| BTC | 13 | +271.47 | +0.2098% |
| DASH | 12 | +125.23 | +0.1575% |
| DOGE | 14 | +89.63 | +0.1329% |
| ETH | 17 | +163.68 | +0.1226% |
| LINK | 19 | +104.80 | +0.0914% |
| LTC | 25 | -70.10 | -0.0606% |
| SOL | 11 | +417.83 | +0.5974% |
| XRP | 5 | +346.53 | +1.0851% |
| ZEC | 14 | -46.89 | -0.0850% |

| Breakdown | Bucket | Trades | Net $ | RPCD |
|---|---|---|---|---|
| Year | 2021 | 16 | +554.97 | +0.2603% |
| Year | 2022 | 22 | -343.17 | -0.8044% |
| Year | 2023 | 53 | +905.15 | +0.2752% |
| Year | 2024 | 47 | +564.52 | +0.1862% |
| Year | 2025 | 13 | -153.15 | -0.7582% |
| BTC against its 200-day average | above | 93 | +1,089.64 | +0.1979% |
| BTC against its 200-day average | below | 58 | +438.69 | +0.1227% |
| BTC's 200-day average over 30 days | falling | 28 | +9.04 | +0.0082% |
| BTC's 200-day average over 30 days | rising | 123 | +1,519.29 | +0.1905% |
| The coin's 30-day volatility (terciles) | high | 50 | -61.58 | -0.0233% |
| The coin's 30-day volatility (terciles) | low | 51 | +913.38 | +0.2672% |
| The coin's 30-day volatility (terciles) | middle | 50 | +676.52 | +0.2243% |

### STRAT-001

| Coin | Trades | Net $ | RPCD |
|---|---|---|---|
| ADA | 650 | -683.74 | -1.4520% |
| AVAX | 593 | -693.55 | -1.7589% |
| BTC | 678 | -652.66 | -1.2651% |
| DASH | 628 | -697.86 | -1.4266% |
| DOGE | 639 | -578.59 | -1.2886% |
| ETH | 673 | -485.55 | -0.9299% |
| LINK | 698 | -865.83 | -1.6999% |
| LTC | 685 | -764.61 | -1.4956% |
| SOL | 600 | -602.80 | -1.4379% |
| XRP | 289 | -220.23 | -1.3203% |
| ZEC | 696 | -799.69 | -1.5976% |

| Breakdown | Bucket | Trades | Net $ | RPCD |
|---|---|---|---|---|
| Year | 2021 | 1354 | -1,564.19 | -1.2576% |
| Year | 2022 | 1615 | -2,206.49 | -1.6596% |
| Year | 2023 | 1610 | -1,287.34 | -1.1124% |
| Year | 2024 | 1717 | -1,568.99 | -1.6492% |
| Year | 2025 | 533 | -418.10 | -1.5677% |
| BTC against its 200-day average | above | 3851 | -3,552.46 | -1.3471% |
| BTC against its 200-day average | below | 2978 | -3,492.65 | -1.5110% |
| BTC's 200-day average over 30 days | falling | 1855 | -2,127.86 | -1.4874% |
| BTC's 200-day average over 30 days | rising | 4974 | -4,917.25 | -1.3977% |
| The coin's 30-day volatility (terciles) | high | 2257 | -2,997.56 | -1.7260% |
| The coin's 30-day volatility (terciles) | low | 2257 | -1,824.23 | -1.1746% |
| The coin's 30-day volatility (terciles) | middle | 2257 | -2,164.63 | -1.3490% |
| The coin's 30-day volatility (terciles) | unknown | 58 | -58.69 | -1.0820% |

## 6. The regime gate (OVL-REGIME: BTC above its 200-day average)

| Strategy | Trades | Net $ | RPCD | Gated trades | Gated net $ | Gated RPCD | Gated max DD | Vetoes | R3 median RPCD | p vs R3 | Role |
|---|---|---|---|---|---|---|---|---|---|---|---|
| STRAT-001 | 6829 | -7,045.11 | -1.4237% | 3851 | -4,439.78 | -1.3641% | 33.8% | 2978 | -1.4247% | 0.1827 | member |
| STRAT-004 | 135 | +1,692.94 | +0.2882% | 111 | +2,118.74 | +0.3929% | 5.8% | 110 | +0.2785% | 0.0001 | member |
| STRAT-005 | 151 | +1,528.33 | +0.1683% | 114 | +1,514.76 | +0.1907% | 9.5% | 117 | +0.1422% | 0.0126 | member |
| STRAT-000 | 3535 | -1,944.43 | -0.1756% | 1991 | -601.87 | -0.0845% | 10.9% | 1544 | -0.1668% | 0.0729 | shown |
| STRAT-002 | 1036 | +1,008.33 | +0.0950% | 577 | +314.25 | +0.0573% | 7.5% | 459 | +0.0993% | 0.7053 | shown |

## 7. Models with strategies

The strategy and its exits are held fixed: a model can only veto a trade. The generic models forecast a T1 barrier outcome under the legacy rules, not the strategy's trade (section 9 item 11).

Names: **PV model** and **P model** are the generic lab models (`pv.linear.t1.PV.q50`, `pv.linear.t1.P.q50`); M1 and M2 use the PV model. **F_PV** and **F_P** are the strategy-specific models, refitted on each strategy's own candidate trades (shown only).

| Strategy | Model | Trades | Net $ | RPCD | Vetoes | R3 median RPCD | p vs R3 |
|---|---|---|---|---|---|---|---|
| STRAT-004 | PV (member) | 104 | +1,984.69 | +0.3877% | 151 | +0.3085% | 0.0011 |
| STRAT-004 | P (shown) | 103 | +1,736.38 | +0.3515% | 166 | +0.3098% | 0.0529 |
| STRAT-005 | PV (member) | 99 | +1,522.56 | +0.2052% | 171 | +0.1546% | 0.0255 |
| STRAT-005 | P (shown) | 100 | +937.78 | +0.1342% | 206 | +0.1393% | 0.5684 |

### Prediction (shown; E1 declares no prediction test)

| Model | AUC (trade won after fees) | Other | Rows |
|---|---|---|---|
| STRAT-004 F_PV | 0.512 | BSS -0.0393, miscalibrated | n/a |
| STRAT-004 P model | 0.493 | base rate 36.4% | 926 |
| STRAT-004 PV model | 0.515 | base rate 36.4% | 926 |
| STRAT-005 P model | 0.447 | base rate 28.2% | 917 |
| STRAT-005 PV model | 0.460 | base rate 28.2% | 917 |

An AUC of 0.5 is no better than chance at ranking the strategy's winning trades above its losing ones.

## 8. Fees (£10,000)

| Strategy | 0.50% net $ | 0.50% RPCD | 1.20% net $ | 1.20% RPCD | 0.60% maker net $ (hypothetical) | 0.60% maker RPCD |
|---|---|---|---|---|---|---|
| STRAT-000 | -1,944.43 | -0.1756% | -6,409.62 | -0.7047% | -2,726.40 | -0.2536% |
| STRAT-001 | -7,045.11 | -1.4237% | -11,017.00 | -3.2652% | -7,869.60 | -1.6870% |
| STRAT-002 | +1,008.33 | +0.0950% | -961.30 | -0.0972% | +708.60 | +0.0675% |
| STRAT-004 | +1,692.94 | +0.2882% | +1,386.33 | +0.2383% | +1,648.68 | +0.2810% |
| STRAT-005 | +1,528.33 | +0.1683% | +1,193.80 | +0.1328% | +1,479.81 | +0.1632% |

The 0.60% maker scenario is hypothetical: the strategies place market orders, which are not filled at a maker rate.

## 9. Robustness (section 6.4: shown, never deciding)

| Variant | Trades | Net $ | RPCD | Max DD | REF-RANDOM median | p (B = 1,000) | Coins |
|---|---|---|---|---|---|---|---|
| STRAT-001 + OVL-REGIME 100 days | 3633 | -4,179.51 | -1.3682% | 32.0% | -3.3704% | 0.0010 | 11 |
| STRAT-001 + OVL-REGIME 300 days | 4825 | -5,551.24 | -1.4711% | 41.9% | -3.4017% | 0.0010 | 11 |
| STRAT-004 + OVL-REGIME 100 days | 119 | +2,011.75 | +0.3650% | 5.8% | +0.0237% | 0.0030 | 11 |
| STRAT-004 + OVL-REGIME 300 days | 117 | +1,795.94 | +0.3368% | 6.7% | +0.0473% | 0.0130 | 11 |
| STRAT-004 entry 100 / exit 10 | 117 | +1,435.15 | +0.4964% | 5.1% | +0.2050% | 0.0619 | 11 |
| STRAT-004 entry 100 / exit 20 | 90 | +917.12 | +0.2339% | 7.4% | +0.0179% | 0.0679 | 11 |
| STRAT-004 entry 20 / exit 10 | 309 | +2,868.63 | +0.3698% | 6.4% | +0.1557% | 0.0100 | 11 |
| STRAT-004 entry 55 / exit 10 | 173 | +2,194.55 | +0.5153% | 4.6% | +0.1191% | 0.0080 | 11 |
| STRAT-004 on 12h candles | 137 | +1,986.37 | +0.3294% | 7.5% | +0.0913% | 0.0110 | 11 |
| STRAT-004 on 4h candles | 138 | +1,963.42 | +0.3311% | 7.7% | +0.0692% | 0.0070 | 11 |
| STRAT-004, BTC and ETH only | 31 | +371.90 | +0.2416% | 1.3% | +0.0552% | 0.0370 | 2 |
| STRAT-004, coins with bars from 2021-01-01 | 89 | -57.25 | -0.0154% | 7.4% | -0.1501% | 0.0579 | 6 |
| STRAT-005 + OVL-REGIME 100 days | 113 | +1,630.56 | +0.2007% | 9.5% | +0.0667% | 0.0549 | 11 |
| STRAT-005 + OVL-REGIME 300 days | 131 | +1,618.14 | +0.1890% | 9.6% | +0.1118% | 0.1289 | 11 |
| STRAT-005 every 28 days | 68 | +1,045.54 | +0.1170% | 11.0% | +0.1186% | 0.5135 | 11 |
| STRAT-005 on 12h candles | 151 | +1,528.33 | +0.1683% | 10.2% | +0.1068% | 0.1778 | 11 |
| STRAT-005 on 4h candles | 103 | -175.76 | -0.0286% | 7.4% | +0.2185% | 1.0000 | 11 |
| STRAT-005, BTC and ETH only | 30 | +441.14 | +0.1692% | 2.6% | +0.1491% | 0.3816 | 2 |
| STRAT-005, coins with bars from 2021-01-01 | 100 | +554.52 | +0.0890% | 8.8% | +0.0277% | 0.1189 | 6 |

### Probability of backtest overfitting (CSCV, 16 blocks)

| Set | Contestants | PBO |
|---|---|---|
| OVL-REGIME with STRAT-001 | G1 (default), STRAT-001 + OVL-REGIME 100 days, STRAT-001 + OVL-REGIME 300 days | 0.936 |
| OVL-REGIME with STRAT-004 | G2 (default), STRAT-004 + OVL-REGIME 100 days, STRAT-004 + OVL-REGIME 300 days | 0.923 |
| OVL-REGIME with STRAT-005 | G3 (default), STRAT-005 + OVL-REGIME 100 days, STRAT-005 + OVL-REGIME 300 days | 0.939 |
| STRAT-004 parameters | STRAT-004 (default), STRAT-004 entry 20 / exit 10, STRAT-004 entry 55 / exit 10, STRAT-004 entry 100 / exit 10, STRAT-004 entry 100 / exit 20 | 0.523 |
| STRAT-005 decision interval | STRAT-005 (default), STRAT-005 every 28 days | 0.699 |

Not run:

- **STRAT-004 entry 20 / exit 20:** its exit_days must be below its entry_days
- **exchanges:** Kraken, second in the Settings order, serves only its latest 720 bars of a series: they do not reach the development period, and reading them would read the reserved months
- **the volatility shrink:** it needs FDS-SIG-004's hourly volatility estimate per trade, which E1 does not build; recorded for a later declared run

## 10. Exploratory cells (Benjamini-Hochberg at q = 0.10; never a pass)

| Cell | p | Value | Baseline median | BH |
|---|---|---|---|---|
| Calibration of STRAT-004's F_PV | 0.7474 | n/a | n/a |  |
| STRAT-000 + OVL-REGIME vs R3 | 0.0729 | -0.0845% | -0.1668% |  |
| STRAT-000 vs REF-RANDOM | 0.0010 | -0.1756% | -1.0904% | flagged |
| STRAT-001 + P model vs R3 | 0.5714 | -1.3753% | -1.3664% |  |
| STRAT-001 + PV model vs R3 | 0.5704 | -1.3657% | -1.3554% |  |
| STRAT-001 vs REF-RANDOM | 0.0010 | -1.4237% | -3.4413% | flagged |
| STRAT-002 + OVL-REGIME vs R3 | 0.7053 | +0.0573% | +0.0993% |  |
| STRAT-002 vs REF-RANDOM | 0.0020 | +0.0950% | -0.0762% | flagged |
| STRAT-004 + F_P vs R3 | 0.9530 | +0.1719% | +0.2473% |  |
| STRAT-004 + F_PV vs R3 | 0.8941 | +0.1924% | +0.2477% |  |
| STRAT-004 + P model vs R3 | 0.0529 | +0.3515% | +0.3098% |  |
| STRAT-004: PV model vs P model | 0.1934 | +0.0363% | n/a |  |
| STRAT-005 + F_P vs R3 | not assessable |  |  | 199 events and 468 non-events scored; 200 of each are needed |
| STRAT-005 + F_PV vs R3 | not assessable |  |  | 199 events and 468 non-events scored; 200 of each are needed |
| STRAT-005 + P model vs R3 | 0.5684 | +0.1342% | +0.1393% |  |
| STRAT-005: PV model vs P model | 0.0174 | +0.0709% | n/a | flagged |

## 11. The 8% halt (reported, not modelled)

| Strategy | Account | First reached | Open then $ | Worst further 30-day fall $ |
|---|---|---|---|---|
| STRAT-000 | £10,000 | 2022-04-26 | 651.61 | 221.39 |
| STRAT-000 | £500 | 2022-02-24 | 7.23 | 0.00 |
| STRAT-000 | £50 | 2021-05-23 | 1.09 | 0.00 |
| STRAT-001 | £10,000 | 2021-07-17 | 122.60 | 7.64 |
| STRAT-001 | £500 | 2021-07-13 | 24.93 | 4.53 |
| STRAT-001 | £50 | 2021-05-19 | 0.00 | 0.00 |
| STRAT-002 | £10,000 | 2023-08-25 | 532.34 | 47.93 |
| STRAT-002 | £500 | 2023-06-10 | 0.00 | 0.00 |
| STRAT-002 | £50 | 2021-07-20 | 1.84 | 0.05 |
| STRAT-004 | £10,000 | not reached | n/a | n/a |
| STRAT-004 | £500 | not reached | n/a | n/a |
| STRAT-004 | £50 | 2022-08-20 | 2.71 | 0.42 |
| STRAT-005 | £10,000 | 2022-11-09 | 347.88 | 56.15 |
| STRAT-005 | £500 | 2022-11-09 | 17.39 | 2.81 |
| STRAT-005 | £50 | 2021-05-20 | 7.51 | 1.52 |

## 12. Limits

- **Development only, one market history.** 2021 to 2025: two or three cycles, mostly rising for the coins that survived. Nothing here was checked on unseen months.
- **Survivorship.** Today's coins, with no point-in-time universe (section 9 item 3); the BTC and ETH and the listed-by-2021 rows are shown for that reason.
- **Venue rules** are today's; fees are assumed proportional with no fixed fee.
- **The halt does not exit:** a halted trader manages nothing, and the replay cannot model the owner's resume.
- **Paper and live fills** differ from the next open (section 9 item 8).

## 13. After the results were read

I wrote this section by hand after reading the results. Nothing here is a test or changes a verdict. Every figure comes from `results.json`, except the gap count in 13.4, which counts timestamps in the cached candles. After the run, three presentation changes were made to the report generator: the per-run p column, the day-block line and the note under family S. No figure changed.

### 13.1 The three kinds of finding (section 6.6)

| Kind | Finding |
|---|---|
| Prediction | **No forecast improvement detected.** The PV model ranks the strategies' after-fee winners at AUC 0.515 for STRAT-004 (n = 926) and 0.460 for STRAT-005 (n = 917); 0.5 is chance. STRAT-004's own F_PV is miscalibrated. STRAT-005's could not be scored: 199 events, where 200 are needed. E1 declares no prediction test. Development only: not evidence for enabling anything. |
| Trading | **STRAT-004 beats random entries with its own exits** (S1, p = 0.0065, every run 0.004 to 0.011). The gate and the PV model each add value over random vetoes for STRAT-004 and STRAT-005 (G2, G3, M1, M2), **mostly by skipping 2022** (13.2). STRAT-005 alone: too few trades to tell (S2). The gate on STRAT-001: no better than random vetoes (G1). Development only: not evidence for enabling anything. |
| Profitability | **Not shown for either new strategy.** STRAT-004 lost $117 in the first half (S3). STRAT-005's drawdown reached 10.1%, above the 8% halt (S4). The bootstrap had 1.8 blocks (13.4), so it would carry little weight even had the conditions held. On the account: STRAT-004 made +12.6% over the period (2.8% a year), with 2.6% of the account committed on average; STRAT-005 made +11.3% (2.5% a year), with 4.0% committed. Idle cash earns nothing in the replay (REF-CASH = 0). Development only: not evidence for enabling anything. |

### 13.2 The gate and the model are one finding: mostly 2022

| £10,000 | Trades | 2022 trades | 2022 net $ | Net $ | Return per capital-day | A year, on the account |
|---|---|---|---|---|---|---|
| STRAT-004 alone | 135 | 24 | -518 | +1,693 | +0.2882% | 2.76% |
| STRAT-004 with the gate | 111 | 0 | 0 | +2,119 | +0.3929% | 3.42% |
| STRAT-004 with the PV model | 104 | 9 | -196 | +1,985 | +0.3877% | 3.21% |
| STRAT-005 alone | 151 | 22 | -343 | +1,528 | +0.1683% | 2.50% |
| STRAT-005 with the gate | 114 | 0 | 0 | +1,515 | +0.1907% | 2.48% |
| STRAT-005 with the PV model | 99 | 9 | -122 | +1,523 | +0.2052% | 2.49% |

- **The vetoes fall mostly in 2022.** Both filters veto mostly in the 2022 bear market, the strategies' worst year (2025's few trades also lost). R3 spreads the same number of vetoes at random over 4.3 years, so a filter that concentrates its vetoes in that year beats it. That is one episode, and it does not show the effect repeats.
- **STRAT-005's gain is capital, not money.** For STRAT-005, the higher return per capital-day came from committing less capital. The net was no higher.
- **The model is not picking winners.** The PV model's AUCs near 0.5 (13.1) fit this: its probabilities were low in 2022.

### 13.3 Coins listed after 2021 carry STRAT-004's profit

| £10,000 | Coins | STRAT-004 net $ | STRAT-005 net $ |
|---|---|---|---|
| With bars from 2021-01-01: BTC, DASH, ETH, LINK, LTC, ZEC | 6 | -56 | +548 |
| Listed later: ADA, AVAX, DOGE, SOL, XRP | 5 | +1,749 | +980 |

- **SOL alone** made +$770 of STRAT-004's profit.
- **Survivorship.** Today's list includes coins because they survived and grew (section 9 item 3).
- **The six older coins.** On them, STRAT-004 still beat random entries in the robustness run (p = 0.058, B = 1,000, shown only), but it did not make money.

### 13.4 Two problems found

1. **The block rule and long trades.** Section 6.0's rule gave family S blocks of 896 days (k = 5): 1.8 blocks in 1,586 days.
   - With so few blocks, S3's and S4's 95% intervals include zero, while their centred p-values are below 0.01. The test cannot weigh these strategies.
   - The spec expected 112 or 224 days.
   - E1's rule stays as frozen. Future experiments need an amended rule (13.6).
2. **STRAT-005 holds when any bar in its year is missing.**
   - **What it does.** It finds each lookback's earlier close by counting bars back, then requires that bar to have opened exactly L days earlier. One missing bar anywhere in the 365-day window shifts the count, so every decision for up to a year reads `BARS_MISSING`: no entries and no exits.
   - **The 4h row.** The cached 4h series have 1 to 7 gaps per coin (XRP none). The gaps held 832 of the 1,960 weekly decisions (42%). So the 4h robustness row (-$176) reflects this rule, not the market.
   - **What is unaffected.** The daily and 12h series have no gaps, so S2, S4, G3 and M2 are unaffected.
   - **Docs and test disagree.** The module's docstring describes the narrower behaviour: hold only when the lookback bar itself is missing. Its test drops a bar 50 days back, between two lookbacks, and checks the wider one.

### 13.5 What the reserved months could show

At E1's trade rates, the lockbox (2025-05-06 to 2026-11-06, 549 days) would hold about 47 STRAT-004 trades (38 with the gate) and 52 STRAT-005 trades. F3 needs at least 100, so a final check there would read "Not assessable". The lockbox stays closed.

## 14. Recommendation for the next development phase

For the owner's decision. Nothing here is registered, enabled or started.

1. **Promote nothing.**
   - No strategy, gate or model is shown to be profitable after fees.
   - The passes rest largely on one bear market and on coins chosen today.
2. **Fix STRAT-005's gap rule (one PR).**
   - Look up each lookback bar by its time, and hold only when that bar is missing.
   - Test a gap away from the lookback bars.
   - STRAT-005 is research-only, so no trading behaviour changes.
   - Until this is fixed, STRAT-005 should not be observed in paper: one missing daily bar would freeze it for a year.
3. **Amend section 6.0's block rule for long-holding strategies (a spec PR)**, before any further economic test of the daily strategies.
   - For example, cap L and report the trades longer than L ÷ 2, or bootstrap at trade level.
   - E1's results stay as frozen.
4. **If you want operational evidence, observe STRAT-004 in paper.**
   - Candidate: STRAT-004 at its defaults, gate off. Section 6.7's conditions are met: its tests pass, including the parity test (the live signal engine and a replayed runner agree on every closed daily bar), and E1 has reported. The decision is yours.
   - Its record would state S1 pass and S3 fail.
   - Paper can show execution and backtest–paper parity, at about 31 trades a year. It cannot show profitability.
5. **Do not tune.** PBO is 0.52 across STRAT-004's parameter sets and 0.92 to 0.94 across the gate's lengths: choosing among them by these results would not carry over. Keep the defaults.
6. **Do not spend the lockbox on these strategies** at their trade rates (13.5).
   - Stronger evidence needs either a point-in-time coin universe (section 9 item 3) or forward months.
   - A later, separately approved spec would register those.
