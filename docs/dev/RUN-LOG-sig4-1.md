# RUN-LOG-sig4-1: price-volume signal fusion (FDS-SIG-004)

## 2026-11-07: the owner's build authorisation

The owner approved FDS-SIG-004 revision 3 (`146ec05`, PR #229), its decisions D1 to D18, and the FDS-MH-001 amendments of its Appendix A. The owner authorised:
1. finalising #229;
2. the FDS-MH-001 amendment PR;
3. FDS-MH-001 phase C;
4. the evaluation framework, the price-only and price-volume models, the placebo comparisons, calibration and risk assessment;
5. the development experiments and their reports;
6. the log-only GUI integration, with every new control off.

**Not authorised:** live trading; activating the predictive veto or any sizing control; registering a forward window.

**Pull requests** (the owner merges):

| Step | What | PR |
|---|---|---|
| S1 | FDS-MH-001 amendment 1 (docs) | #230 |
| S2 | FDS-MH-001 phase C | #231, on #230 |
| S3 | FDS-SIG-004 phase A: `app/signal_fusion/evaluation` | this branch, from `main` |

#229 is final, and its checks are green. Merging it was blocked by the auto-mode classifier, so the owner merges it.

## Phase A: the evaluation framework

**Branch** `feat/sig4-a-evaluation`, from `main`. It depends on nothing new: it reads `model_lab.stats` for Holm.

**Built** (`app/signal_fusion/evaluation/`):
- `scoring.py`: log loss, the Brier score and Murphy's decomposition, the Brier skill score, calibration in the large (a), the calibration slope (b), sharpness and QLIKE.
- `bootstrap.py`: circular blocks of 28 calendar days (56 under the long-trade rule), all coins together, the centred p-value, and 10 runs of 1,000 draws.
- `replay.py`: the portfolio replay, for many paths at once.
- `baselines.py`: R3 (stratified by coin, and unstratified to show) and R3s.
- `findings.py`: F1, F2 and F3, Q2 and Q3, Holm over a family, and the verdict lines with their wording rule.

### Where the spec was not explicit

| Point | As built | Why |
|---|---|---|
| Murphy's decomposition on continuous forecasts | Over 10 equal-count bins. The rest of the Brier score is reported as `within`, so the parts add up | The decomposition is exact only for discrete forecasts |
| Calibration fits | Newton's method, unpenalised; a and b are refitted on each draw's rows, weighted by how often the draw took each day | So the intervals come from the same block bootstrap as every other test |
| The bootstrap's random numbers | `random.Random(seed + run)` and its `random()` alone | As FDS-MH-001's draws: a seed repeats exactly across Python versions |
| The portfolio replay's speed | All paths of a run replayed together, as arrays (one pass over the hours, 1,000 paths at a time) | R3 and R3s replay every draw through the trader's constraints (section 6.1) without one replay per draw |
| Path 0's statuses | Each opportunity's outcome (taken, vetoed, not flat, no cash, below the minimum, ended), from which the filter's eligible opportunities are read | R3 vetoes only the filter's assessable, eligible opportunities |
| The halt | Reported as the first hour the drawdown reached the level; `halt_ends` gives the variant in which the path ends there | Section 6.0 |

### A spec erratum (recorded, not reopened)

- §12 item 10 says that "no verdict line except an F3 pass contains 'profitable' or 'makes money'".
- But §6.1's own F3 failure line is "Not shown to be profitable after fees".
- **As built:** only F3's own lines may use the words. The pass says the result is profitable, and the failure says it is not shown to be. Every other line never uses them, so a result that loses less than its controls is never called profitable.
- This keeps the rule's intent. The spec's §12 text should say "except F3's own lines" in a later docs PR.

### Tests

`tests/test_signal_fusion_evaluation.py`, 14 tests:
- the scoring rules against hand-worked values and scikit-learn;
- the calibration measures recovering known values;
- the bootstrap's reproducibility, its pairing and its day counts;
- the 10-run pooling and the block-length rule;
- R3's per-coin counts on candidates only, and R3s;
- the replay against `run_backtest` (one coin at 100%), and its one-trade-per-coin, cash, minimum, veto and halt rules;
- F1 on constructed forecasts, and the three calibration outcomes (§12 item 7);
- F3 and the wording rules on constructed paths (§12 item 10).

## Phase B: the signal-fusion package

**Branch** `feat/sig4-b-signal-fusion`, from phase C's branch (#231), with phase A (#232) merged in. It needs both: blocks P and V come from `model_lab.features`, and the scoring comes from phase A.

**Built** (`app/signal_fusion/`):
- `liquidity.py`: block L:
  - the approximate dollar volume, and its error bound against the true value, ē = max((TP − L)/L, (H − TP)/H);
  - zero-volume and invalid bars;
  - the 20-day hourly median, with ε_max and the participation share's bound against the true median;
  - the participation and spread caps, where a missing input is never a pass;
  - the Abdi–Ranaldo estimate, as a historical sensitivity only.
- `volatility.py`: block S, with the EWMA (λ = 0.94, 168-bar burn-in), Parkinson and naive candidates; QLIKE selection against naive; σ_ref, the terciles and the shrink, min(1, σ_ref / σ̂).
- `labels.py`: STRAT-001's opportunities from the backtester with no costs; r_g; m(f, e); M; the payoff tables (cells under 30 pooled); EV with costs once; the execution allowance max(½ spread, 0.05%); the payoff-calibration table.
- `meta.py`: F_P and F_PV, as logistic regression with L2 and C = 1:
  - training rows purged by each trade's own exit;
  - Platt calibration fitted only on earlier folds' out-of-fold predictions;
  - the climatology from the training rows.
- `assessment.py`: the two stages of §5.8.4, with each part failing by its own rule (§5.8.3) and the invariants of §5.8.5.
- `compat.py`: the venue compatibility test, with D17's tolerances.
- `artifact.py`: the code hash (this package plus `model_lab/features.py`), and the registered-artifact check the live hook uses.

### Where the spec was not explicit

| Point | As built | Why |
|---|---|---|
| STRAT-001's opportunities | `run_backtest` with no costs (so its fills are the raw opens) and STRAT-001 at its defaults | One definition of the trade. m(f, e) then gives the net return at any fee, and a test checks it against the backtester's at three fee rates |
| A forced trade | A trade the bars closed only because they ended is never a training label (M = −1) | Its true exit is unknown |
| The EWMA after a missing return | It starts again, with its burn-in | It never averages across a gap |
| σ_ref in development | Per fold, the median σ̂ of that fold's training opportunities | "The pooled median of σ̂ over the evaluation's training rows" (§5.6), walk-forward |

### Tests

`tests/test_signal_fusion_phase_b.py`, 22 tests:
- the hand-worked cases A to H of §12 item 5, including revision 2's bound failing in case C;
- zero volume and seven kinds of invalid bar;
- the hourly median and the participation bound;
- the spread cap on unusable quotes;
- the volatility candidates' look-ahead, and the shrink;
- m(f, e) against the backtester's net return on every trade at three fees;
- a fee entering EV only through m;
- the payoff pooling;
- every row of §5.8.3's table, the minimum check, and the result's invariants;
- calibration strictly out of fold;
- the compatibility test;
- the registered artifact.

## Backlog (non-critical, for later)

- §12 item 10's wording, as above.
- `findings.calibration` refits a and b by Newton's method on every draw: about 10,000 fits a run of the analysis. It is fast enough at the development run's size; a closed-form weighted update would make it faster.
- `model_lab.targets.t2` replays one trade for every hour on its next 720 hours, one `model_gate.replay` call each. That is the slowest part of building T2 labels. One pass over the hours would be faster, with the same labels.
- `model_lab.contestants.ModelFit` scores a fold's hours twice for a T1 contestant: once for its entries, once for its probabilities. Scoring once would halve that time. The scores are identical.

## Phase C: the development run (2026-11-07)

**Branch** `feat/sig4-c-dev-run`, from phase B's branch.

**Scripts:** `docs/dev/run_sig4_dev.py` (freeze, run, analyse), `docs/dev/sig4_dev_analysis.py` and `docs/dev/sig4_dev_report.py`.

**The report:** `docs/dev/SIG4-REPORT-dev.md`.

**Evidence:** `docs/dev/sig4-dev/`:
- the analysis;
- PV-1's batch file, results (gzipped), runs and report;
- the trial log;
- the sandbox launcher, with its paths replaced by placeholders.

**The sandbox:**
- `POWERTRADER_HOME`, `APPDATA` and `LOCALAPPDATA` are scratch folders, and the keyring fails, so there are no keys.
- Settings come from the shipped template (Coinbase primary).
- Candles are FDS-MH-001 phase B's sandbox cache of Coinbase 1-hour bars, read offline.
- The only network reads were the public product endpoint, for today's minimum order (every coin: $1), and the exchange layer's unauthenticated connect.

**Batch PV-1:** `20261107-175558`, declared pv-1, spec version 1.1.
- 18 folds from 2021-01-01 to 2025-05-06. The lockbox, never read, runs from 2025-05-06.
- 13 coins, of which BNB and HYPE have no bars before 2025-05-06.
- 0.50% plus 0.05%.
- Seeds 500000, 600000 and 0; B = 10,000.
- It ran in 1,030 s.
- The probabilities it saved (24 MB, not committed) have these SHA-256s:

| File | SHA-256 |
|---|---|
| `pv.linear.t1.P.q50.npz` | `fab539dda03b3f5c7020d3ca8986bfe6268a5a6418e4ed8a5cf3201ce7aad62e` |
| `pv.linear.t1.PV.q50.npz` | `ce72439610a93fb2e6ad4fa28915417c82bf2ff8f1b9957a98291ecf4dc25d03` |
| `pv.linear.t1.PVp.q50.npz` | `8532132bdfeeb17c09e243f62dc6d5fa8ebeaa7967d5152f3402ea118a989346` |
| `pv.linear.t1.PVp2.q50.npz` | `f6a30805bc2f868b265b8477cb5a61d13bd88b26bc8898a801b1f29c4ca50e61` |
| `pv.linear.t1.PVp3.q50.npz` | `3252e735ad718d5344cd790641313ce3b2bd4ac2a8648fa66ba99a25e479cc51` |
| `pv.linear.t1.PVp4.q50.npz` | `186d66ab8270436960b172b90a2e791b0ba49ec911702dc3b30508a5820d3567` |
| `pv.linear.t1.PVp5.q50.npz` | `588f0ce889a6bc34c92ba82962e5fe9044e3e8c72e0e332786f663462ef3f690` |

**The analysis** took 15 minutes. Its seeds are fixed in the driver (`TEST_SEEDS`). It scored the development family at 0.50% and $10,000, with 1.20% and $100 shown. Eight trials were logged, all in the sandbox:
- PV-1's 3 "trading" trials;
- 1 "forecast" trial (F1);
- 2 "decision" trials (F2, F3);
- 1 "calibration" trial (Q2);
- 1 "sizing" trial (Q3).

### What development found

Each line carries its caveat. This is development only, never evidence for enabling anything, and volume's rows from 2023-11-06 on were already seen by the volume research.

| Finding | Result | p (Holm over K = 5) |
|---|---|---|
| F1 | No forecast improvement detected: Δ log loss +0.00033 (smallest detectable 0.00112), n = 351,099 rows, base rate 0.253. The placebo and stability conditions also fail | 0.170 |
| F2 | No improvement over price alone detected. Both filters veto about 94% of STRAT-001's 6,825 opportunities. Against R3, p = 0.070 | 0.139 |
| F3 | Not shown to be profitable after fees. F_PV's path: 385 trades, net −$131 on $10,000, return per capital-day −0.47% | 0.831 |
| Q2 | Calibration not assessable: the 90% intervals of a and b are too wide for their bands. BSS +0.008 is not shown at the family's level | 0.022 |
| Q3 | No reduction in drawdown compared with random sizing detected | 0.694 |

**Facts worth the owner's attention, beyond the family:**
- **Unfiltered STRAT-001 loses heavily at the account's fee.**
  - At 1h and its defaults, 0.50%: 6,825 trades, net −$5,191 on $10,000, and an equity-curve maximum drawdown of 53%.
  - The 8% halt level would first have been reached on 2021-07-17.
  - At 1.20%: −$8,135, an 82% drawdown.
  - This agrees with the volume research's −1.1% a trade, and is unchanged by this spec (§3.7).
- **F1's only positive volume signal is in the months the volume research already saw.**
  - From 2023-11-06: D̄ = +0.00095 (p 0.048).
  - Before it, on unseen data: −0.00009 (p 0.59).
  - The exposure split (§6.4.1) shows that the seen months are where the effect is.
- **The trading level under the legacy exits (PV-1):** all three contestants read "Too few trades to tell" (an edge above +0.012% a day was needed).

**What this decides** (§6.4.2): only whether a forward confirmation is worth registering. Development gives no reason to expect one to confirm volume for STRAT-001 at the account's fee. Registering one is the owner's decision and is not authorised here.
