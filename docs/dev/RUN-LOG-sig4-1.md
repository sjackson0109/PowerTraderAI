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
