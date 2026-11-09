# RUN-LOG-mh-1: the multi-model harness (FDS-MH-001)

## 2026-11-06: the owner's go-ahead

The owner said "go" on D1–D10 as recommended:
- the spec is PR #225;
- phase A, the gate fix, is PR #226.

## 2026-11-06: phase B, the harness core

**Branch** `feat/mh-b-harness-core`, stacked on `feat/mh-a-gate-per-day` (#226). The package is `app/model_lab/`; the tests are `app/tests/test_model_lab.py`. There is no new dependency.

### Where the spec was not explicit

Each of these is also written into the spec (#225).

| Point | As built | Why |
|---|---|---|
| A series' SHA-256 (§5.2) | The SHA-256 of the bars used, in the candle cache's CSV format (`pt_pattern_trainer.candle_sha256`'s) | The cache file is shared and grows, so its own hash would not identify the bars |
| Reading a frozen series again | From the exchange it was frozen with, from its recorded first bar | So a later change of primary exchange cannot swap the data; and a pair listed late is not asked for again before its first bar |
| R2's offset (§5.6) | A draw takes one number u in [0, 1); each coin's δ is that share of its range [D, length − D] | "One δ for every coin" and "at least D from 0 and from the stream's length" cannot both hold when streams differ in length. Coins with the same stream length, as most are, still move together |
| R2's comparison | Against the contestant's trades on the coins that take part in R2 | R2's draws cover only those coins |
| No coin long enough for R2 | p₂ = 1 | It must beat both; a baseline that cannot be drawn is not beaten |
| K (§5.6) | Every tested contestant, one with no entries at p = 1 | So the correction does not shrink when a contestant makes no entries |
| Daily rules | The last *built* UTC day; undecided when the day that just ended was not built (an hour missing); N days = the last N built days | A day with a missing hour is a gap (`build_candles`), not a guess |
| Joining late (§5.4) | Rules: once the coin has 100 complete UTC days. Pattern model: from the first fold that starts 365 days after the coin's first bar | As §5.4, made exact |
| Refusals | A batch whose file, code (SHA-256 of `model_lab/*.py` and what it replays and fits with) or candles changed since it was frozen is refused | "The same batch on the same cached candles gives the same results" holds only for the same code |
| Trial log | A trial is logged as soon as it is scored | A stopped batch's scored trials stay counted |

### D11: the lockbox is 18 months (owner, 2026-11-06)

§5.7 draws R1 and R2 on the lockbox's hours, but a 6-month lockbox is shorter than 2D (320 days), so R2 could not be drawn there. Asked, the owner chose to lengthen the lockbox to 18 months ("let's expand the spec to 18mths") over the alternative, R1 only.

`walkforward.LOCKBOX_MONTHS` is now 18. For batch 1, frozen on 2026-11-06:
- the walk-forward runs from 2021-01-01 to 2025-05-06, in 18 folds (22 before);
- the lockbox runs from 2025-05-06 to the end.

Two consequences:
- **Fewer walk-forward trades.** The walk-forward stream is about 4.3 years rather than 5.3, so about a fifth fewer trades, and "too few trades to tell" is a little more likely.
- **Late coins.** BNB and HYPE start on Coinbase after 2025-05-06, so they are in the final check only.

Nothing in phase B opens the lockbox: that comes with phase D's "Final check…".

### Tests (no network, fixture candles)

- **No look-ahead.** Every rule's decision at an hour, made from bars cut at that hour, equals its decision from all bars. This was checked at 70 hours per coin, including the hours around a missing hour, a 6-hour gap and a 20-hour gap.
- **Lockbox.** A batch run never passes a contestant a bar from the lockbox.
- **R2's offsets.** R2 never moves a signal less than D, in 2,000 random streams; a coin whose stream is shorter than 2D takes no part.
- **False-pass rate.** On random-walk prices, R1 and R2 each pass a no-skill contestant at about the nominal rate: 200 trials, within the binomial range of 2 to 22 passes.
- **Determinism.** A batch run twice gives byte-identical `results.json`.
- **Refusals.** A batch whose file, candles or code changed is refused.
- **Pattern fold 1.** The pattern contestant's fold-1 entries and long counts equal those of the trainer's sibling fit (`validation_fit`) on the same window, and so do the model files' SHA-256.
- **Trade table.** It is `model_gate.replay` from every hour.
- **Late listings.** A coin listed after the lockbox starts (as BNB and HYPE are on Coinbase) has an empty walk-forward stream: it never joins, is reported as such, and takes no part in R2. The first timing run found this.
- **Statistics.** Holm, Benjamini-Hochberg, the p-values and PBO, on hand-checked cases.
- **Full suite:** 2659 passed, 13 skipped, 0 failed.

### Measured: batch 1 without the trained contestants

**The run.** A sandbox (no keys, no real user folders), with Settings from the shipped template (Coinbase primary) and public candles. Batch `20261106-143033`:
- 13 coins from 2020-01-01;
- the seven rules, `ref.always` and `pattern`;
- 0.50% a side (the owner's account rate) plus 0.05% slippage;
- the trader's default rules;
- B = 10,000.

**Candles.** Every series came from Coinbase. Coins that start later there:
- ADA 2021-03, ZEC 2020-12, DOGE and SOL 2021-06, AVAX 2021-09;
- BNB 2025-10-22 and HYPE 2026-02-05;
- XRP's series starts 2023-07-13: Coinbase halted XRP from 2021-01-19, and a gap longer than 24 hours ends the earlier part.

The walk-forward stream is 380,539 coin-hours, in 18 folds from 2021-01-01 to 2025-05-06.

| Stage | Time |
|---|---|
| Freeze, downloading 2020-01 to 2023-11 for 13 coins and BTC | 114 s (2 s from the cache) |
| Read the series again and check their SHA-256 | 2 s |
| Trade cache: every stream hour's trade, 380,539 replays | 231 s (0.6 ms each) |
| The seven rules' decisions | 1 s |
| Pattern model: 155 fits (18 folds, the coins with 12 months of bars), with their counts | 3,565 s (23 s a fit) |
| Draws: R1 and R2 × 10,000 for 8 contestants, the fee lines, and the pattern model's neural DCA line (1,000 draws) | 1,333 s |
| Holm, Benjamini-Hochberg, PBO, the best-rule comparison | 1 s |
| **Run, in all** | **5,133 s (86 min)** |

The run ended "done". The coins joined where §5.4 says they should:
- BNB and HYPE never joined;
- the pattern model joined ADA on 2022-04-01 and XRP on 2024-10-01;
- XRP's pattern stream is shorter than 2D, so it takes no part in R2 there.

Phase C adds pooled fits: 6 contestants × 18 folds.

**These are trials.** The run logged 8 trials in the sandbox's trial log. Phase E's report counts them.

## 2026-11-06: the owner's review of #225 and #226

### 1. The LLM gate's per-trade minimum

**The finding.** #226, as first pushed, retired `gate_min_return_after_fees` and fixed the LLM signal gate's rule b at 0%. Anyone who had saved another value would see different LLM gate decisions, and the tests compared decisions at the default settings only.

**Checked.** I ran `main`'s gate code (500a355) and #226 as pushed (`a652b5b`) on the same LLM fixtures, at seven saved settings: minimums of 0%, +0.5%, +3%, −5% and −10%, plus two with other non-default fields.
- At +3%, the "edge" model (mean return after fees +2.39%) **passed under `a652b5b` and is rejected by `main`**.
- At every setting, `a652b5b`'s records lacked the minimum's key.

**Fixed** (`09f9fa6` on #226). The owner offered two routes, a separate LLM threshold or an explicit approval of the change; this keeps the threshold.
- `gate_min_return_after_fees` stays as saved and is the LLM signals' rule b (`GateSettings.min_mean_return`). Its field is back in Settings > Training as "Minimum mean return per LLM signal after fees %".
- A trained model keeps its own per-day minimum. The per-trade value is never turned into it.
- `llm_settings_ui.py` is `main`'s again.
- With the fix, every decision figure equals `main`'s at all seven settings. The tests pin `main`'s texts at +3%, at −5%, and at +1% with the 90th percentile.

### 2. Provenance: earlier looks at results

**The finding.** The pattern model has already been evaluated on part of the proposed holdout. Those observations are not unseen evidence for it.

**Built** in #227: `model_lab/catalogue.py`'s `LOOKS` records every earlier look at a contestant's results, with the months covered and where each is written up. A batch records, when frozen, which looks cover its lockbox. A contestant with any is never given "Beats random entries": a finalist reads "Passed; its lockbox was seen before, so a final check would not be unseen evidence".

The pattern model's looks:

| Look | Coins | Months | On |
|---|---|---|---|
| FDS-MDL Tests A and B (as STRAT-003, that strategy's exits) | BTC, ETH | 2024-07-01 to 2026-10-01 | 2026-10-07 |
| Volume research, held-out replay and model experiment | 10 | 2026-03-31 to 2026-11-05 | 2026-11-05 |
| The entry gate's held-out slices of the models in use | the coins with a model | from about 2026-04 | 2026-11-05 |
| Gate diagnostic | 13 | 2026-04-05 to 2026-11-05 | 2026-11-05 |

With batch 1's lockbox (from 2025-05-06), the pattern model's final check cannot be unseen evidence for it. The seven rules have no earlier look at their lockbox.

The phase B timing run (2021-01-01 to 2025-05-06, walk-forward only) is recorded for all 8 of its contestants, and its 8 trials count in phase E's report.

No substantive Copilot review was received on #225 or #226: GitHub reported insufficient review quota.

**Full suites after the review:** #226 on its own, 2635 passed, 13 skipped, 0 failed; #227 with everything, 2663 passed, 13 skipped, 0 failed.

## 2026-11-07: phase C, the trained contestants, as amended by amendment 1

**Authority.** The owner approved FDS-SIG-004 revision 3 (`146ec05`), D1 to D18 and its Appendix A, and authorised phase C on 2026-11-07. Amendment 1 is PR #230 (docs only).

**Branch** `feat/mh-c-trained-contestants`, stacked on `docs/fds-mh-001-amendment-1` (#230).

**New:**
- `model_lab/features.py`: the 26 features, the blocks P, v1, v2 and V, the placebo's lag and PV-1's common rows.
- `model_lab/targets.py`: T1, T2, the purge and uniqueness weights.
- `contestants.py`: batch 1's six trained contestants, PV-1's three and the placebo's variants 2 to 5.
- `catalogue.py`: explicit `BATCH_1`, `BATCH_PV_1` and `DECLARED`, and the look at v2.
- `batch.py`: `declared`, `spec_version` and `libraries` in the batch file; trial kinds; probabilities; the 10-run report.
- `app/requirements.txt`: `scikit-learn>=1.5`.

**Not run:** batch 1 (phase E) and PV-1 (FDS-SIG-004 §8.2, S6). Phase C builds and tests the contestants only.

### Where the spec was not explicit

| Point | As built | Why |
|---|---|---|
| The 50-day average (§5.5) | The mean of the last 1,200 hourly closes. The 24-hour, 7-, 30- and 50-day averages all use hourly closes | §5.5 lists them together; FDS-SIG-004 §13 item 3 left the choice to phase C. It needs 1,200 bars, within FDS-SIG-004's 1,224 |
| Realised volatility | The root mean square of the hourly log returns in the window | Scale-free and has no mean to estimate. Its ratio and BTC's use the same definition |
| Rolling windows | At least 90% of the window's hours present | A gap of a few hours keeps the feature. A long run of missing hours does not |
| v1's 30 days | The 30 completed UTC days ending with the last completed day (as the daily rules read days). A missing hour counts as zero volume (FDS-SIG-004 §5.2.1) | So v1 never reads the day still in progress. Its warm-up is 719 to 743 hours, depending on the hour the series starts |
| A log of 0 | Missing | v2 for an hour with zero volume is missing, not minus infinity |
| A flat bar (H = L) | Body and both wicks 0 | A share of a zero range is otherwise undefined |
| An invalid bar | A missing hour for every feature (FDS-SIG-004 §5.2) | The same rule as the liquidity block's |
| T1's barriers | `model_gate.replay`'s own arithmetic: average cost C (1 + slippage) / (1 − fee); the profit line `pm_start_pct_no_dca` above it, the DCA level `dca_levels[0]` below it | "As the trader computes it" (§5.5) |
| T1 unresolved | When the label's 336 hours are not all on the grid and no barrier was hit | Neither a win nor a loss is known yet |
| T2 | `model_gate.replay` on the next 720 hours' closes. A trade still open is sold at that close, its exit fee included. Unresolved when the window runs past the grid before the trade closes | §5.5's "marked at that close", with the replay's own exit accounting |
| Uniqueness | Per coin, among the fit's own training rows, each label spanning from its hour to its barrier hit or exit (or t + H) | López de Prado's average uniqueness, on the rows that are weighted together |
| Standardisation | The unweighted mean and standard deviation of the training rows. A constant feature is left unscaled | "Standardised on training rows" (§7) |
| Threshold | The unweighted (1 − q) quantile of the scores the fit gave its own training rows. An entry at or above it | "The top q of the scores it gave its own training rows" (§5.5) |
| Trees' seed | `random_state` = the batch's fits seed, 0 | §7's "random_state 0" and the batch's "fits from 0" |
| A fold with no rows, or with T1 rows of one class | No fit: every hour of that fold undecided | Nothing can be learned, and nothing is guessed |
| PV-1's join | The first decided hour, its first common row (§7a) | Batch 1's contestants keep §5.4's fold-based join, so batch 1 is unchanged |
| The 10 runs | Consecutive scored draws, split into 10. A draw with no score is left out, as in every baseline, so the runs follow the scored draws | The pooled p is exactly the batch's p-value either way (a test) |
| Probabilities | `probabilities/<key>.npz` in the batch's folder, outside `results.json` | So `results.json` is unchanged for every contestant that existed before |
| scikit-learn's version | Recorded with numpy's and pandas'. A batch with a trained contestant is refused when it has changed | The same batch on the same candles gives the same results only with the same library |

### Batch 1 is unchanged: the byte-identity check

The two phase B fixture batches were run with `main`'s code (the amendment branch, `e633db9`, whose code is `e0d837a`'s) and again with phase C's code:
- the rules-only batch (BTC and ETH, 420 days, 200 draws);
- the pattern batch (BTC, 150 days, `rule.sma20` and `pattern`, 50 draws).

Each run's `results.json` was taken without the batch's own id and SHA-256. Those two fields identify the batch file, which records the code's hashes, so they differ whenever the code does.

| Code | SHA-256 of the two batches' results |
|---|---|
| `main` (before amendment 1) | `fc94ee050fe6da6b0558eb67a1e9c87aa4ffcf77bd2c7aefbffe832d2a5478d0` |
| phase C | `fc94ee050fe6da6b0558eb67a1e9c87aa4ffcf77bd2c7aefbffe832d2a5478d0` |

**Identical, byte for byte.**
- The `main` results are committed as `tests/fixtures/model_lab_phase_b_golden.json`.
- `test_the_rules_and_the_pattern_model_give_the_results_they_gave_before` compares against that file on every run. Integers, strings and structure must match exactly; floats must match to a relative 1e-9.
- The tolerance is there because CI runs on another platform, where the last bits of a float can differ.

### Tests

`tests/test_model_lab_phase_c.py`, 23 tests (no network, fixture candles), with `tests/test_model_lab.py`'s 28 unchanged.

**Phase C's own tests:**
- feature look-ahead around gaps;
- T1 on four hand-built paths, plus an unresolved one;
- T2 against the replay;
- the purge;
- uniqueness on a hand-checked case;
- thresholds and fits unchanged when every bar after the fold is corrupted;
- a frozen fit's entries with its data cut at the hour.

**Amendment 1's tests:**
- `BATCH_1` against §7's list, also with an extra contestant in the catalogue;
- byte identity (above);
- trial kinds;
- the placebo:
  - encoded source hours: every value is its hour minus its lag, never later;
  - the missing span at the start and after a gap longer than 24 hours;
  - poisoning at the first common row and later;
  - the declared lags;
- identical row sets and probability hours across PV-1's seven;
- the blocks' sizes, with no round-one candidate;
- the 10-run report pooling exactly.

**Also:**
- a PV-1 batch end to end (K = 3; variants 2 to 5 forecast-only);
- a batch with batch 1's trained contestants;
- the scikit-learn refusal.

### Backlog (non-critical, recorded for later)

- **T2's labels replay every hour in Python.** Batch 1's real run (13 coins, about 5 years) needs about 600,000 replays. They are made once per run and cached; phase E should measure the time.
- **`ModelFit` scores each fold's hours twice,** once for entries and once for probabilities.

## 2026-11-09: phase D, Settings > Training, "Compare models…"

**Authority.** The owner asked why none of the model lab's models appears in Settings ("UI, not CLI"), and on 2026-11-09 authorised phase D as specified, without the final check.

**Branch** `feat/mh-d-compare-models`, from `main` at `2ab8ce8`.

**New:**
- `model_lab_ui.py`: the window (§5.9).
- `pt_hub.py`: the "Compare models…" button on Settings > Training, under "Check the models in use…", and `open_compare_models`. The window belongs to the hub, so a batch keeps running when Settings closes.
- `tests/test_model_lab_ui.py`: 14 tests.

No module under `model_lab/` changes, so batch 1's and PV-1's code hashes are unchanged.

### Where the spec was not explicit, and where this differs from it

| Point | As built | Why |
|---|---|---|
| The window's end | Every batch frozen from the window ends on **2026-11-06** (`model_lab_ui.END`, `strategy_lab.windows.LOCKBOX[1]`). Its last 18 months are then 2025-05-06 to 2026-11-06, and its walk-forward ends at 2025-05-06 | §5.8 and `freeze()` end a batch at the last closed hour. A batch frozen after 2026-11-06 would then score hours inside the shared lockbox (2025-05-06 to 2026-11-06) and lock months reserved for a forward check. The fixed end keeps every window batch on batch 1's dates. **A deviation for the owner to confirm** |
| The final check (§5.9, "Final check…") | Not built | The owner's instruction for this phase. Nothing in the window reads the lockbox |
| Declared batches | Two buttons tick batch 1 or PV-1. When the ticks are exactly a declared batch, it is frozen as that batch (`declared`), in its declared order | So a declared batch run from the window records its spec version. An addition |
| The last batch's choices | The newest readable batch's contestants, coins and start are ticked. With no batch, batch 1's contestants and the coin list | §5.9: "The last batch's choices are ticked" |
| Coins | The coin list as ticks, with other coins typed in, separated by commas or spaces | §5.9 |
| The start | Refused unless before 2024-05-06, the latest start that leaves 12 months before a first fold ending by 2025-05-06 | The calendar's own rule, with the reason in plain words |
| Progress | The run's stages in words: reading candles, replaying trades, fitting models, scoring models, each as "n of m" | §5.9's "folds, coins and draws": the harness reports these stages |
| Stop | Stop, or closing the window, stops the run at its next check. The batch keeps its frozen record, marked as stopped | §5.8 |
| Results | A batch chooser (the newest first, each with its state), the batch's dates, fees, models tested and probability of backtest overfitting, then a table: model, result, trades, return per day held, total profit, worst drawdown, time in a trade, then the percentiles among R1's and R2's draws and the smallest detectable edge. Selecting a row shows its coins, rising and falling markets, half and double fees, the best rule on shared hours, neural DCA, and whether its held-back months were looked at before | §5.9's list. The deciding figures come first so they fit the window; the rest scroll |
| Words | No spec names, contestant keys, "R1"/"R2", "Holm", "lockbox" or exchange names in the window's own words (a test). The verdicts are `batch.VERDICTS`' own, as §5.6 and §5.7 word them, so a finalist whose lockbox was seen before reads "Passed; its lockbox was seen before…" | The facts-only rule |
| Fees and candles | A read-only line: the primary exchange, then the others in Settings > Exchanges, and each coin's fee as that exchange states it, plus slippage. The batch's own fees are shown with its results | `freeze()`'s defaults (`series.load`, `entry_gate.trading_fees`) |

### Tests

- **The window's dates:** a batch ending on `END` has its lockbox exactly at FDS-SR-001's, its last fold ends at 2025-05-06, and the latest start is 2024-05-06.
- **Choices:** wrong choices are explained, and nothing is frozen. Typed coins join the ticked ones once. The declared buttons freeze PV-1 and batch 1 as declared, and a set that is not declared is frozen in catalogue order. Every catalogue contestant is offered.
- **Runs:**
  - a real batch on fixture candles, run from the window, with its rows and a row's detail;
  - progress and Stop with a fake run;
  - closing the window stops a run;
  - a real batch stopped is shown as stopped, with no rows.
- **Saved batches:** the newest first with their states, and the last batch's choices ticked. With no batch, batch 1 is ticked.
- **Words:** the facts-only check over every label, row, detail and heading.
- **The hub:** Settings > Training has the button; it opens the window and raises the open one.

**One fix in the tests.** A closed window's Tk variables, collected later by garbage collection on a worker thread, each waited on a destroyed test interpreter (about 60 s). The tests collect them on the Tk thread after each test. This is a test effect only: the app's interpreter lives as long as the hub.

**Screenshot:** the real hub, alpha 0, captured with PrintWindow; checked by eye, not committed.

### Not done (phase E and later)

- Batch 1 and PV-1 have not been run. A run from the window is the owner's choice, and each is a trial in `trials.jsonl`.
- No final check, no lockbox opening, no change to any model in use.
