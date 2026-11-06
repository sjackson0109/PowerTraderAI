# Entry gate diagnostic (2026-11-05)

Why no model passed the entry gate (PR #224), and whether the gate measures the right thing. Run in a scratch sandbox: no app data, keys or settings were read, and nothing in `main` changed. The scripts stayed in the sandbox; FDS-MH-001 phase A and B rebuild the baselines below as tested code.

## Setup

- **Models:** pattern models trained by `main`'s trainer as it was before the gate (the way the models in use were trained), on Coinbase 1-hour candles from 2023-11-06 to 2026-11-05.
  - The owner's nine coins: BTC, ETH, XRP, BNB, DOGE, SOL, ZEC, DASH, HYPE.
  - Four more cached coins: ADA, AVAX, LINK, LTC.
  - BNB-USD starts on Coinbase on 2025-10-22 and HYPE-USD on 2026-02-05, so their held-out slices are short.
- **Held-out hours:** captured from the merged trainer's `--check-gate` (the last 20% of each window, about 7 months), with fees of 0.50% (the owner's account taker rate, shown in the owner's check window) plus 0.05% slippage per fill. Trade rules: the trader's defaults (`model_gate.TRADER_DEFAULTS`).
- **Checks:** every replayed trade equalled `model_gate.replay`'s. The gate's recorded percentile was reproduced exactly for all 13 coins, and the pooled gate baseline equalled `entry_gate.run_baseline`.

## Baselines compared

- **B1, the gate's:** N distinct random held-out hours, N being the model's entry count, each replayed as its own trade (so random trades can overlap). Seeds 0 to 999.
- **B2, a coin-flip trader**, one trade at a time, entry probability calibrated to give N entries. Degenerate: on DASH, ETH, XRP and ADA the model enters about as often as a trader who buys the moment it is flat, so the calibrated probability is 1 and there is one path. Discarded.
- **B3, same waits, random order:** one trade at a time; after each exit, wait one of the model's own waits (hours from being free to entering), drawn at random with replacement. This keeps the model's patience and randomises only its timing. Seeds 200000 to 200999.

## Findings

1. **The gate's baseline (B1) is biased against any trader that holds one trade at a time.** Overlapping random entries include buys made while a trade would still be open, part-way down a drawdown. No real trader can take those, and they recover well. Pooled over the nine coins, B1's median return per capital-day is +0.149%, against +0.071% for B3. Against B1 the model looks worse than random (mean per trade at the 1.3rd percentile, per capital-day at the 7.8th); against B3 it does not.
2. **Against B3, the model's timing is no better than random, and not worse.**
   - Nine coins, 129 trades: per capital-day at the 67th percentile, total profit 68th, mean per trade 10th. Stouffer z on per capital-day +1.11.
   - 13 coins, 181 trades: per capital-day at the 48th percentile (+0.047% against +0.048%), total profit 49th, mean per trade 6th. Stouffer z on per capital-day +0.63.
3. **Mean return per trade and return per capital-day disagree** (nine coins: 10th against 67th percentile). The mean per trade ignores how long capital is tied up, and DCA doublings make some long trades look good per trade. It is the wrong score for these exits.
4. **The exits leave entries little room.** The model is in a trade 74-94% of hours, and its trades last about 10 days. It waits a median of 6-107 hours after an exit, and its signal was on in the hour after a trailing sell in only 2 of 177 cases (so it is not re-buying straight after selling). Entry timing can only matter in the hours when no trade is open.
5. **Power.**
   - The spread of one trade's return under these rules, over every 4th held-out hour of the 13 coins, is 4.57% (6.00% for the model's own trades).
   - Pooled over 13 coins (about 176 B3 trades a draw), the smallest edge the B3 test could detect with 80% power at one-sided 5% is 2.49 × the spread of the draws' scores: 0.57 percentage points of mean return per trade (23% of the median), or 116% of the median return per capital-day.
   - So on one 7-month held-out slice, only a model that about doubles the return per capital-day of random entries would be seen.

## Per coin (B3, 13 coins)

The model's figure, then B3's median, then the model's percentile among the B3 draws.

| Coin | Trades | B3 median trades | Mean per trade | Per capital-day | Total profit (100-unit account) |
|---|---:|---:|---|---|---|
| ADA | 13 | 12 | +0.24% vs +0.96% (28th) | −0.075% vs −0.044% (29th) | −1.08 vs −0.60 (28th) |
| AVAX | 12 | 13 | +0.88% vs +1.51% (26th) | −0.036% vs +0.006% (27th) | −0.52 vs +0.08 (27th) |
| BNB | 6 | 5 | +3.68% vs +1.77% (99th) | +0.262% vs +0.004% (90th) | +0.48 vs +0.01 (82nd) |
| BTC | 10 | 9 | +2.66% vs +2.93% (24th) | +0.074% vs +0.076% (47th) | +0.79 vs +0.78 (52nd) |
| DASH | 20 | 18 | +3.05% vs +3.12% (45th) | +0.120% vs +0.065% (74th) | +1.87 vs +1.01 (76th) |
| DOGE | 6 | 7 | −1.84% vs −0.44% (24th) | −0.138% vs −0.134% (42nd) | −2.13 vs −2.02 (39th) |
| ETH | 15 | 14 | +2.29% vs +2.28% (51st) | +0.019% vs +0.032% (19th) | +0.25 vs +0.41 (19th) |
| HYPE | 6 | 6 | +2.86% vs +2.53% (60th) | +0.514% vs +0.276% (72nd) | +1.47 vs +0.76 (83rd) |
| LINK | 15 | 17 | +1.50% vs +1.96% (16th) | −0.007% vs +0.016% (28th) | −0.10 vs +0.19 (27th) |
| LTC | 12 | 11 | +1.75% vs +1.45% (66th) | +0.042% vs −0.008% (76th) | +0.55 vs −0.10 (76th) |
| SOL | 16 | 12 | +2.37% vs +1.57% (90th) | +0.073% vs −0.023% (93rd) | +0.74 vs −0.28 (93rd) |
| XRP | 15 | 13 | +3.31% vs +2.25% (96th) | +0.099% vs +0.032% (85th) | +1.18 vs +0.39 (85th) |
| ZEC | 35 | 36 | +2.55% vs +4.30% (0th) | +0.281% vs +0.386% (29th) | +3.49 vs +4.36 (29th) |
| **Pooled** | **181** | **176** | +2.12% vs +2.49% (6.4th) | +0.047% vs +0.048% (48.0th) | +6.98 vs +7.05 (48.6th) |

With 6-35 trades a coin, none of these per-coin percentiles can separate skill from luck.

## What follows for the gate and the harness

- Replace B1 with a one-at-a-time baseline such as B3, and score return per capital-day (or total profit), not mean return per trade. B3's entry count varies around the model's, so this departs from the gate's "as many random entries as the model made".
- Pool the coins, and test over more held-out hours (walk-forward over years), because the per-coin samples cannot resolve an edge this small.
