# SIG4-REPORT-dev: FDS-SIG-004's development run

**What this is.** The development run of FDS-SIG-004 phase C (spec §8.3). It ran in a sandbox on public Coinbase candles, read offline from a cache. It scores the development period only: PV-1's walk-forward, 2021-01-01 00:00 to 2025-05-06 00:00 UTC, in 18 folds. No bar from 2025-05-06 on was read.

**What it decides** (spec §6.4.2): only whether a forward confirmation is worth registering, and what it would register. A development pass is never evidence for enabling anything. The volume rows from 2023-11-06 on were seen by the volume research (exposure X1), so they are not unseen evidence for volume.

## Verdicts (development family, Holm over K = 5, at 0.50% and $10,000)

- **F1, forecast value:** No forecast improvement detected (Δ log loss = +0.00033, smallest detectable Δ log loss = 0.00112, n = 351099). Development only: not evidence for enabling anything.
- **F2, relative trading value:** No improvement over price alone detected (smallest detectable difference = +0.00298 a capital-day). Development only: not evidence for enabling anything.
- **F3, economic viability:** Not shown to be profitable after fees: a profit per capital-day. Development only: not evidence for enabling anything.
- **Q2, calibration of F_PV:** Calibration not assessable; no skill above the base rate shown. Development only: not evidence for enabling anything.
- **Q3, the volatility shrink:** No reduction in drawdown compared with random sizing detected. Development only: not evidence for enabling anything.

| Test | p (pooled, 10 runs) | Holm at 5% | Conditions | Passes |
|---|---|---|---|---|
| F1 | 0.1704 | no | placebo no, stability no | no |
| F2 | 0.1386 | no | r3 no | no |
| Q2 | 0.0220 | no | calibrated no, enough yes | no |
| Q3 | 0.6940 | no | non_inferiority no | no |
| F3 | 0.8308 | no | not_one_coin no, stable no, trades yes, within_halt yes | no |

## F1: does volume improve T1 forecasts over price alone?

- **Rows:** 351,099 common rows (all seven models present, T1 resolved), base rate 0.253.
- **Log loss:** price only 0.57012, price and volume 0.56979.
- **D̄ = ll(P) − ll(PV):** +0.000327; p = 0.1704 (runs from 0.1469 to 0.1908); 90% interval [-0.000247, +0.000924]; blocks of 28 days over 1586 days.
- **Smallest detectable D̄** (at the Holm level, 80% power): 0.001117.
- **Placebo condition** (mean of 5 lagged placebos minus PV): Ē = +0.000436, p = 0.1580: no.
- **Stability:** D̄ by half of the scored days: -0.000359 and +0.000843: no.
- **Each placebo against price only** (expected at most 0): +0.000157, -0.000438, +0.000024, -0.000353, +0.000065.
- **D̄ before 2023-11-06 (no recorded look):** -0.000094, p = 0.5885.
- **D̄ from 2023-11-06 (seen by the volume research):** +0.000948, p = 0.0480.
- **D̄ by coin:** ADA +0.000537, AVAX +0.000867, BTC -0.001323, DASH +0.000648, DOGE +0.000473, ETH +0.000087, LINK +0.000456, LTC +0.000717, SOL +0.000044, XRP +0.002513, ZEC +0.000282.

## Q1's trading level: batch PV-1 under FDS-MH-001's fixed strategy (shown)

Batch `20261107-175558` (declared PV-1, spec version 1.1), file SHA-256 `f4389fb8b07b70a4…`; K = 3; probability of backtest overfitting 0.643. A relative finding of F2's kind under the legacy exits; never F3.

| Contestant | Trades | Return per day held | Total profit | p | Verdict |
|---|---|---|---|---|---|
| `pv.linear.t1.P.q50` | 435 | -0.0046% | -5.54 | 0.9750 | Too few trades to tell: this test could only see an edge above +0.012% a day |
| `pv.linear.t1.PV.q50` | 448 | +0.0000% | 0.02 | 0.4759 | Too few trades to tell: this test could only see an edge above +0.012% a day |
| `pv.linear.t1.PVp.q50` | 437 | -0.0043% | -5.21 | 0.9602 | Too few trades to tell: this test could only see an edge above +0.012% a day |

## STRAT-001 1h at its defaults: the decision level

- **σ̂:** parkinson (QLIKE: ewma 0.4860, naive 0.6005, parkinson 0.4760).
- **Venue minimums** (today's, from the public product endpoint; past ones are not recorded anywhere): ADA 1.0, AVAX 1.0, BTC 1.0, DASH 1.0, DOGE 1.0, ETH 1.0, LINK 1.0, LTC 1.0, SOL 1.0, XRP 1.0, ZEC 1.0.

### At 0.50% (deciding)

6825 opportunities in the development period; blocks of 28 days.

| Account | Path | Trades | Vetoed | Net | Return per capital-day | Max drawdown | Halt level reached |
|---|---|---|---|---|---|---|---|
| $10000 | F_P | 386 | 6439 | -147.95 | -0.5301% | +3.45% | never |
| $10000 | F_PV | 385 | 6440 | -131.02 | -0.4710% | +3.37% | never |
| $10000 | unfiltered | 6825 | 0 | -5,191.34 | -1.4168% | +52.67% | 2021-07-17 11:00 |
| $100 | F_P | 386 | 6439 | -1.52 | -0.5263% | +3.56% | never |
| $100 | F_PV | 385 | 6440 | -1.34 | -0.4667% | +3.47% | never |
| $100 | unfiltered | 6825 | 0 | -75.19 | -1.4265% | +75.63% | 2021-07-16 07:00 |

- **F2:** Δ RPCD (F_PV − F_P) = +0.000591, p = 0.1386; against R3, p = 0.0702 (R3's median -0.6135%). Veto counts per coin: {'ADA': 622, 'AVAX': 577, 'BTC': 629, 'DASH': 589, 'DOGE': 612, 'ETH': 627, 'LINK': 651, 'LTC': 643, 'SOL': 576, 'XRP': 266, 'ZEC': 648}.
- **F3 (F_PV's path):** trades 385 ([331, 54] by half), net -131.02 (-1.31% of equity, -0.30% a year), return per capital-day -0.4710% (p = 0.8308); net by half [-134.37, 3.35]; without the best coin -174.10; maximum drawdown +3.37%; time in the market +8.2%; mean committed +0.18% of equity, peak +7.01%; win rate +33.5%; largest single loss -9.86. Requirements: trades yes, stable no, not one coin no, within the halt level yes.
- **Q2 (F_PV):** BSS +0.0083 (p = 0.0220); intercept a = -0.076, 90% interval [-0.157, 0.004] against [-0.1, 0.1]; slope b = 0.987, 90% interval [0.626, 1.383] against [0.8, 1.2]; 1678 events and 4799 non-events: **not assessable**.
- **Q3:** the shrink's maximum drawdown +48.17% against R3s' median +48.00% (p = 0.6940); non-inferiority lower bound -0.000997 against −0.0001: no; 0 entries skipped below the minimum.
- **The research's 1.5× rule** (before 2023-11-06 only, shown): 4318 opportunities, 3325 vetoed, return per capital-day -1.3891% against R3's median -1.3897% (p = 0.4988).

### At 1.20% (shown)

6825 opportunities in the development period; blocks of 28 days.

| Account | Path | Trades | Vetoed | Net | Return per capital-day | Max drawdown | Halt level reached |
|---|---|---|---|---|---|---|---|
| $10000 | F_P | 344 | 6481 | -588.65 | -2.4884% | +6.76% | never |
| $10000 | F_PV | 344 | 6481 | -585.30 | -2.4685% | +6.76% | never |
| $10000 | unfiltered | 6825 | 0 | -8,135.35 | -3.2572% | +81.53% | 2021-05-17 17:00 |
| $100 | F_P | 344 | 6481 | -6.32 | -2.4948% | +7.23% | never |
| $100 | F_PV | 344 | 6481 | -6.29 | -2.4742% | +7.24% | never |
| $100 | unfiltered | 3911 | 0 | -98.99 | -3.1909% | +99.00% | 2021-05-04 16:00 |

- **F2:** Δ RPCD (F_PV − F_P) = +0.000199, p = 0.1761; against R3, p = 0.2432 (R3's median -2.4807%). Veto counts per coin: {'ADA': 628, 'AVAX': 579, 'BTC': 639, 'DASH': 591, 'DOGE': 616, 'ETH': 631, 'LINK': 655, 'LTC': 646, 'SOL': 577, 'XRP': 267, 'ZEC': 652}.
- **F3 (F_PV's path):** trades 344 ([312, 32] by half), net -585.30 (-5.85% of equity, -1.38% a year), return per capital-day -2.4685% (p = 0.9994); net by half [-519.0, -66.3]; without the best coin -580.77; maximum drawdown +6.76%; time in the market +7.2%; mean committed +0.15% of equity, peak +7.01%; win rate +24.7%; largest single loss -10.94. Requirements: trades yes, stable no, not one coin no, within the halt level yes.
- **Q2 (F_PV):** BSS +0.0172 (p = 0.0004); intercept a = -0.122, 90% interval [-0.226, -0.022] against [-0.1, 0.1]; slope b = 1.102, 90% interval [0.857, 1.37] against [0.8, 1.2]; 1106 events and 5371 non-events: **miscalibrated**.
- **Q3:** the shrink's maximum drawdown +77.28% against R3s' median +77.18% (p = 0.7617); non-inferiority lower bound -0.001482 against −0.0001: no; 0 entries skipped below the minimum.
- **The research's 1.5× rule** (before 2023-11-06 only, shown): 4318 opportunities, 3325 vetoed, return per capital-day -3.4219% against R3's median -3.2213% (p = 0.8377).

## Limits

- One market history (2021 to 2025) on one venue; survivorship: the coins are those listed today.
- Past exchange minimums and spreads are not recorded anywhere: the replays use today's minimums and 0.05% a fill.
- The drawdown halt is reported, not modelled (spec §6.0).
- Volume's rows from 2023-11-06 were seen by the volume research; only a forward window can confirm volume.

