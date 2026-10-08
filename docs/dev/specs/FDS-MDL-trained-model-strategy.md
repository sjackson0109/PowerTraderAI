# FDS-MDL — Trained-Model Strategy (STRAT-003) with an Honest Train/Test Split

**Issue:** none yet. Raise "Evaluate the trained model through the catalogue backtester" and link it here.
**Target repo:** `sjackson0109/powertraderai`
**Branch:** `feat/model-strategy-1`, cut from `main` after `feat/strategy-batch-1` is merged (from `feat/strategy-batch-1` if it is not merged yet).
**Recommended model:** Claude Opus 5.5, effort high, for Phases 0 and 1 (trainer audit and any port). Sonnet 5.5, effort high, for Phases 2 to 4.
**Run log:** `docs/dev/RUN-LOG-model-1.md`, the same format as batch 1.

---

## 1. Objective

Put the neural trainer's output through the same honest backtester as STRAT-001 and STRAT-002, so the project can answer one question with evidence:

> Does the trained model, trained only on past data, beat buy-and-hold and a random-entry baseline on data it has never seen?

The batch-1 backtest did not test this. Its strategies are fixed indicator formulas, and no trained model was loaded.

## 2. Background, and the open question this spec settles

- The hub launches a trainer through the `script_neural_trainer` setting, and the thinker reads its output files.
- An earlier outside review found that `app/pt_trainer.py`, `app/pt_trainer_standalone.py` and the per-coin copies (ETH, DOGE, XRP, BNB) were stubs. They had sleep-loop epochs, hardcoded accuracy (95%, 97.5%) and `random.uniform` weights and memories. The upstream `pt_trainer.py` in `garagesteve1155/PowerTrader_AI` (about 1,600 lines) does genuine candle pattern-matching and writes predicted high/low bands for the thinker.
- The repo owner reports that the trainer does train. That review may be stale, or it may have read files the hub does not launch.

**Do not assume either answer.** Phase 0 settles it with evidence before anything is built.

## 3. Phase 0: trainer audit (gate, read-only)

Do not change any code in this phase.

1. Find the exact trainer script the hub launches today: the setting's resolved value, its path, and how the hub invokes it.
2. Find every file the trainer writes and every place the thinker reads from (paths, formats, field meanings).
3. Run these checks and record the evidence:
   - **Static.** Does the training path contain `time.sleep` in epoch loops, `random` used for weights or memories, or a literal accuracy value? Quote file and line.
   - **Determinism.** Train twice on the same fixed candle fixture with a fixed seed. The outputs must be identical.
   - **Data dependence.** Train on two different fixtures (for example BTC and ETH, or two non-overlapping windows). The outputs must differ in a way that traces to the data.
   - **Reported metrics.** Is any reported accuracy computed from held-out data, or is it constant across different inputs?
4. Write `docs/dev/TRAINER-AUDIT.md` with a verdict:
   - **REAL:** all checks pass. Skip Phase 1.
   - **STUB:** any check fails in a way that shows outputs are not learned from data. Do Phase 1.
   - **MIXED:** for example, the hub launches a stub but a real trainer exists elsewhere in the repo. Do Phase 1, wiring up the real one rather than porting.
5. Commit the audit on its own. **Stop the run and log BLOCKED** if the hub's trainer cannot be identified with certainty.

## 4. Phase 1: restore a real trainer (only if the verdict is STUB or MIXED)

1. Port upstream `pt_trainer.py`. Record the upstream commit hash in the module header and the run log.
2. Replace its KuCoin calls with `app/market_data/candles.py` (Binance, cached). Note in the run log that the data source changed, since this can change behaviour.
3. The trainer takes an explicit `train_start` and `train_end` and **must never read a candle after `train_end`**. Enforce this in the data call, not by convention.
4. Make it seedable and deterministic for a given seed and data.
5. Keep the output format the thinker already reads, so the legacy path still works.
6. Point the hub's `script_neural_trainer` default at the real trainer. Leave the stub files in place, but add a `MOCK - DO NOT USE FOR DECISIONS` header and make the hub refuse to launch them unless an explicit `allow_mock_trainer` setting is true (default false).
7. If a full training run takes more than 30 minutes on 1h data from 2023 to 2025, record the runtime and continue. **Do not subsample the data silently.**

## 5. Phase 2: model artifact provenance

Every training run writes `hub_data/models/<model_id>/manifest.json` beside its output files:

`model_id, trainer_path, trainer_git_commit, upstream_commit (if ported), symbol, timeframes, train_start, train_end, candle_file_sha256 (per timeframe), params, seed, created_at, validation_metrics`

- `validation_metrics` must be computed on a held-out slice **inside** the training window (its last 20%), never on data after `train_end`.
- Any loader (thinker, backtester, `SignalEngine`) **refuses an artifact that has no manifest** or whose manifest does not match its files. It fails closed and logs an ERROR.
- The legacy thinker path logs the `model_id` and `train_end` it loaded at start-up.

## 6. Phase 3: STRAT-003 adapter

A catalogue strategy that turns the trained model's output into `ENTER_LONG`, `EXIT_LONG` or `HOLD`, using the existing `Strategy` protocol and `StrategyRunner`.

1. **Model loading.** The artifact is loaded once, at construction, by `model_id`. `on_bar` performs no I/O and never refits or updates the model.
2. **Decision rule.** Reproduce the legacy thinker's rule exactly as documented in `ARCHITECTURE.md` (the "Signal Path" section from FDS-121). Map it to long-only:
   - `ENTER_LONG` when the thinker's rule would signal LONG on at least `min_tf_agree` timeframes. The default is whatever the legacy rule uses; document the value.
   - `EXIT_LONG` when the thinker's rule would signal SHORT on the primary timeframe.
   - `HOLD` otherwise.

   Write the mapping into the catalogue entry's `entry_logic_summary` and `exit_logic_summary`. If the legacy rule cannot be reproduced faithfully, log BLOCKED rather than inventing a different rule.
3. **Multi-timeframe data.** At decision time *t*, every timeframe the model uses may only see bars that have **closed** by *t*. For example, a 4h bar is visible only after its close. Add a test for this.
4. **Catalogue entry.** `STRAT-003`, `class_type: main`. Add `model` to the `family` enum and note the addition in the catalogue docs. `default_params` includes `model_id`, `min_tf_agree` and `timeframes`.
5. **Lookahead guard in the backtester.** If the loaded artifact's `train_end` is later than the first bar being scored, the backtest **refuses to run** with error `LOOKAHEAD_MODEL`. This applies to every run, not just this report.
6. `strategy.active_id` stays `STRAT-001`. Do not make STRAT-003 the default.

## 7. Phase 4: evaluation and report

### Declared before any result is seen (write these into the report header first)

- Symbols and timeframes: BTCUSDT and ETHUSDT, primary 1h and 4h. These are the same cached candles as batch 1, verified by SHA-256.
- Costs: 10 bps fee and 5 bps slippage per side.
- Overlay sets: none, and OVL-ATR + OVL-COOLDOWN (defaults), the same as batch 1.
- Model parameters: the trainer's defaults. **Nothing is tuned on anything.**

### Test A: single split (comparable with batch 1)

Train on the first 70% of 2023-01-01 to 2026-09-30, using the same split timestamp as batch 1. Score the last 30%. Report in-sample and out-of-sample results with the full KPI set and buy-and-hold.

### Test B: walk-forward

Use an expanding window. Train on everything up to the end of month *m*, score months *m+1* to *m+3*, roll forward 3 months and repeat until the data ends. The first training window ends at 2024-06-30. Report every window, plus the median and worst window against buy-and-hold.

### Control: random-entry baseline

For each symbol, timeframe and overlay set, generate 100 random-entry strategies (seeds 0 to 99) on the same out-of-sample bars. Match STRAT-003's trade count and average holding period, and apply the same costs and overlays. Report STRAT-003's percentile within that distribution.

### Verdict rule (declared in advance)

Report **"evidence of an edge"** only if all three hold:
1. In Test A, out of sample, STRAT-003 beats buy-and-hold in at least 3 of 4 symbol/timeframe combinations, without overlays.
2. In those same combinations, STRAT-003 is at or above the 95th percentile of the random-entry baseline.
3. In Test B, the median walk-forward window beats buy-and-hold.

Otherwise report **"no evidence of an edge."** The generator asserts the verdict against the numbers before printing it, as batch 1 did.

### Outputs

- `docs/dev/BACKTEST-REPORT-model-1.md`
- `docs/dev/backtest-model-1/` containing JSON KPIs, trade CSVs, random-baseline distributions and manifests of every model used
- `docs/dev/run_backtest_model1.py fetch|train|run|report` to reproduce everything

Also include a short side-by-side table with STRAT-001 and STRAT-002 from batch 1, taken from the existing batch-1 JSON. Do not re-run them.

## 8. Out of scope

Parameter tuning or grid search, new model architectures, shorting, live trading, GUI work beyond the existing mode strip, and deleting the mock trainer files.

## 9. Acceptance criteria

1. `TRAINER-AUDIT.md` exists, states REAL, STUB or MIXED, and quotes evidence for each check.
2. *(If Phase 1 ran.)* The trainer cannot read candles after `train_end`. A test passes a fixture with poisoned post-`train_end` bars and asserts that the output is unchanged.
3. Training is deterministic for a fixed seed and data (test), and outputs differ for different data (test).
4. Loaders refuse an artifact with a missing or mismatched manifest (test).
5. The backtester refuses with `LOOKAHEAD_MODEL` when `train_end` is after the first scored bar (test).
6. A STRAT-003 decision at *t* never uses an unclosed higher-timeframe bar (test).
7. STRAT-003 reproduces the legacy thinker's LONG/SHORT decisions on a recorded fixture, bar for bar (test).
8. The random baseline matches trade count to within ±10% and is reproducible by seed (test).
9. The report exists, its pre-declared header is committed before its results (check the commit order), and the verdict is asserted by the generator.
10. No test touches the network. The full suite is no worse than the batch-1 baseline.

## 10. Run protocol

Same as `00-RUN-ORDER.md`:
- One commit per phase, gated on a green full suite.
- Paper only. No API keys are read, created or requested.
- If a phase is blocked: revert it, log BLOCKED with the reason, and skip any phase that depends on it. Never weaken a test to make it pass.
- Commit the report header (the declared settings and verdict rule) **in its own commit before running Test A**, so the order of decisions is visible in git.
