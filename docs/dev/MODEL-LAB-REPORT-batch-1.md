# Model lab: batch 1's walk-forward (FDS-MH-001 phase E)

**In one line:** none of the 14 entry models is better than random entries by enough for this test to tell. That includes the legacy trainer's pattern model, at 515 trades over 13 coins, on the development months only (2021-01-01 to 2025-05-06). The test could see an edge only above about +0.012% to +0.051% a day, depending on the model. The probability of backtest overfitting is 0.78.

- **Authority:** on 2026-11-09 the owner left the timing of batch 1's run to me, and on 2026-11-10 replied "you decide". I ran it as the model half of the nine-coin comparison the owner scoped (`COMPARISON-9-COINS-PLAN.md`), on the development data only.
- **Run:** 2026-11-10/11, in a sandbox, on public Coinbase candles.
- **Driver:** `docs/dev/run_mh_batch1.py`, committed before the run (4e787e6).
- **Evidence:** in `docs/dev/mh-batch-1/`:
  - the frozen batch file, the harness's own report, the results (gzipped) and the 10-run split of the draws;
  - the sandbox's trial log and its launcher.
- **Not done:** the lockbox (2025-05-06 to 2026-11-06) was locked and not read, and no final check was run. No model passed, so none would have been a finalist anyway.

## 1. What was run

Batch 1 is exactly as FDS-MH-001 §7 declares it.

- **Contestants:** 14 tested, plus the reference ("enter whenever flat").
  - the seven daily and hourly rules;
  - the pattern model, as the trader uses it, refitted every 3 months on earlier bars only;
  - two logistic regressions;
  - four gradient-boosted tree models.
- **Window:** from 2020-01-01, with 18 folds of 3 months from 2021-01-01 to 2025-05-06.
  - The batch ends on 2026-11-06, so its last 18 months are exactly the shared lockbox.
- **Exits:** the trader's default rules, with DCA and the trailing profit margin, and neural DCA off.
- **Fees:** 0.50% a side (the owner's account rate) plus 0.05% slippage.
- **Draws:** 10,000 random-entry draws of each baseline. R1 keeps each model's waits in a random order (seeds from 300000); R2 moves them to other dates (seeds from 400000).
- **Frozen:** 2026-11-10 at 23:26:34Z as batch `20261110-232634`.
  - Declared as `batch-1`, spec version 1.
  - The record's own SHA-256 is `7129db9455beefdf…`.
- **The same as PV-1's (2026-11-07):**
  - every series' SHA-256;
  - every code hash;
  - the trade rules;
  - the library versions (numpy 2.5.4, pandas 3.1.0, scikit-learn 1.9.1).

**Run time:** 4,863 s (81 minutes).

| Stage | Time |
|---|---|
| Fits | 2,940 s |
| Draws | 1,772 s |
| Trade cache | 144 s |

**Reproduced byte for byte.**
- Windows' temporary-file cleanup deleted most of the scratch Python environment's files at 00:16, during the run. The running process kept the modules it had already loaded.
- So the batch was run again, from a copy of the sandbox, in a freshly built environment with the same package versions.
- `results.json`, `runs.json`, `report.md` and every probability file are byte-identical. The SHA-256 of `results.json` is `627f7dcbcdee088a…`.

## 2. Data

All 13 series come from Coinbase, read offline from the cache PV-1 read. The table below shows only the owner's nine; the other four are ADA, AVAX, LINK and LTC. `mh-batch-1/batch-1-report.md` lists every series with its SHA-256.

| Coin | First bar | First entry (enter whenever flat) | Note |
|---|---|---|---|
| BTC, ETH, DASH | 2020-01-01 | 2021-01-01 | |
| ZEC | 2020-12-08 | 2021-03-19 | |
| DOGE | 2021-06-03 | 2021-09-12 | |
| SOL | 2021-06-17 | 2021-09-26 | |
| XRP | 2023-07-13 | 2023-10-22 | Coinbase halted XRP from 2021-01-19 |
| BNB | 2025-10-22 | never | Starts inside the lockbox |
| HYPE | 2026-02-05 | never | Starts inside the lockbox |

The pattern model needs 12 months of a coin's bars before its first fit, so it joins later: ZEC on 2022-01-01, SOL and DOGE on 2022-07-01, and XRP on 2024-10-01.

FDS-MH-001 §9 foresaw BNB and HYPE having no walk-forward trades on Coinbase. The strategy half of the comparison reads them from KuCoin instead; see `COMPARISON-9-COINS-REPORT-dev.md`.

## 3. Results

**Columns:**
- **Per day:** the return per capital-day after fees.
- **R1 and R2:** each model's percentile among the 10,000 draws.
- **p:** the larger of the two one-sided p-values, as the pass rule requires both.
- **Edge:** the smallest edge this test could see, at 80% power.
- **Profit:** in units where each coin's account is 100. A trade starts at 1 unit, and DCA can take it to 10. Accounts are not compounded, and profit is summed over the 13 coins.

| Model | Trades | Per day | R1 | R2 | p | Edge | Profit | Verdict |
|---|---|---|---|---|---|---|---|---|
| Enter whenever flat (reference) | 540 | +0.004% | — | — | — | — | +5.44 | Reference only |
| Close above its 20-day average | 519 | +0.003% | 48.6 | 59.7 | 0.51 | +0.026% | +4.30 | Too few trades to tell |
| Close above its 50-day average | 511 | +0.003% | 37.6 | 54.0 | 0.62 | +0.035% | +3.28 | Too few trades to tell |
| Close above its 100-day average | 515 | +0.003% | 29.8 | 56.2 | 0.70 | +0.044% | +4.06 | Too few trades to tell |
| Close above its close 14 days earlier | 520 | +0.005% | 67.6 | 63.9 | 0.36 | +0.024% | +5.75 | Too few trades to tell |
| Close at a 20-day closing high | 425 | +0.007% | 76.7 | 55.6 | 0.44 | +0.051% | +8.57 | Too few trades to tell |
| **BTC's close above its 50-day average** | 700 | **+0.025%** | **100.0** | **94.9** | **0.051** | +0.037% | **+30.20** | Too few trades to tell |
| 24-hour return in its own bottom 10% | 487 | +0.005% | 77.0 | 72.5 | 0.28 | +0.028% | +5.61 | Too few trades to tell |
| **Pattern model (legacy trainer)** | 515 | +0.007% | 79.3 | 61.5 | 0.39 | +0.026% | +7.04 | Too few trades to tell |
| Logistic regression, top 50% | 560 | +0.006% | 85.6 | 84.6 | 0.15 | +0.013% | +7.68 | Too few trades to tell |
| Logistic regression, top 20% | 531 | +0.004% | 77.2 | 68.9 | 0.31 | +0.019% | +5.02 | Too few trades to tell |
| Trees on clean wins, top 50% | 496 | +0.001% | 33.7 | 32.6 | 0.67 | +0.012% | +1.03 | Too few trades to tell |
| Trees on clean wins, top 20% | 386 | −0.003% | 24.9 | 22.9 | 0.77 | +0.022% | −4.08 | Too few trades to tell |
| Trees on return per day, top 50% | 522 | +0.004% | 57.2 | 67.9 | 0.43 | +0.025% | +4.62 | Too few trades to tell |
| Trees on return per day, top 20% | 509 | +0.002% | 84.7 | 57.6 | 0.42 | +0.047% | +2.75 | Too few trades to tell |

**Further lines:**
- **Multiple testing:** no model passes Holm's correction over the 14 at 5%. The smallest p is 0.051, against Holm's first threshold of 0.0036.
- **Overfitting:** the probability of backtest overfitting is 0.78 over 16 blocks. The model that looks best in one half of the months usually ranks below the median in the other half.
- **Time in a trade:** 90% to 100% of the hours for every model. Under these exits a model mostly decides when a nearly continuous position restarts.
- **Worst drawdown:** about −91% to −92% for every model. This is one trade's worst fall below its average cost, under DCA down to −50%, not an account's drawdown.

### The two lines worth a second look, and why neither is evidence

- **BTC's close above its 50-day average** has the highest per-day return of the 14, at +0.025% a day. That is about five times its R1 median of +0.005%.
  - It is the only model that stays positive in falling markets (+0.001% a day over 139 trades) and at double fees (+0.015% a day).
  - **Not evidence:** against R2 it sits at the 95th percentile (p 0.051), and one model in 14 at that level is what chance gives.
  - It is the same kind of filter as OVL-REGIME, which uses BTC above its 200-day average. E1 tested that gate (G2 and G3) and found it helps mostly by skipping 2022.
- **The pattern model, with neural DCA on,** is at the 99.2nd percentile of R1 (1,000 draws).
  - **Not evidence:** this line is shown, not tested. It has no R2 and no correction.
  - With neural DCA off, as tested, the same model is at the 79th percentile.

### The nine coins

Profit per coin, then trades (units as above):

| Model | BTC | ETH | XRP | SOL | DOGE | ZEC | DASH | BNB, HYPE |
|---|---|---|---|---|---|---|---|---|
| Enter whenever flat | +6.92/60 | +1.45/78 | +5.04/69 | +3.63/71 | −0.00/28 | −2.63/37 | −2.63/49 | no bars |
| BTC above its 50-day average | +6.92/60 | +4.67/104 | +4.99/66 | +5.96/89 | +0.11/28 | +5.14/85 | +1.48/78 | no bars |
| Pattern model | +6.95/61 | +2.15/67 | +1.51/35 | +4.14/75 | −0.18/46 | −3.50/33 | −3.41/43 | no bars |
| Logistic regression, top 50% | +6.84/62 | +0.75/64 | +4.51/54 | +3.43/76 | −0.42/28 | +0.47/61 | −2.47/48 | no bars |
| Close at a 20-day closing high | +5.40/51 | +7.04/72 | +2.40/42 | +5.08/42 | +4.97/45 | −0.08/43 | −3.57/35 | no bars |

`mh-batch-1/batch-1-report.md` has every model's per-coin lines.
- **On BTC** every model does about what entering whenever flat does, because the position is nearly always open.
- **DASH and ZEC lose under most models.**

### Robustness

- **The 10 runs of 1,000 draws** agree with the pooled p-values to within a few hundredths. For BTC's 50-day rule, R2's runs range from 0.042 to 0.065.
- **At half fees** every model's per-day return is positive.
- **At double fees** every model's is negative except BTC's 50-day rule.

## 4. Trials

The sandbox's trial log (`mh-batch-1/trials.jsonl`) holds 30 distinct trials:

| Source | Trials |
|---|---|
| Phase B's timing run on 2026-11-06 (batch `20261106-143033`): the seven rules and the pattern model, on the walk-forward only | 8 |
| FDS-SIG-004's development run on 2026-11-07 (PV-1) | 3 trading, 1 forecast, 2 decision, 1 calibration, 1 sizing |
| Batch 1 | 14 |

FDS-MH-001 §5.7 says phase B's 8 trials count here. They looked at the same eight contestants on almost the same walk-forward.

**Earlier looks (§5.7):** the pattern model has four recorded looks that cover part of the lockbox. The other 13 models have none.

## 5. What was found

On the development months, under the trader's own exits and at the owner's 0.50% fee, no entry model picks better hours than random entries by enough for 500-odd trades to show. That holds for the rules, the legacy pattern model and the newer trained models. The test could only see an edge of at least about +0.012% to +0.051% a day.

The best-looking line is BTC's own 50-day trend. It is one of 14 lines, at R2's 95th percentile and with an overfitting probability of 0.78, so it is a lead for a declared test and not a result.
