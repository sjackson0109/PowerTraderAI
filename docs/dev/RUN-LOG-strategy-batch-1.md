# Run log — strategy batch 1

Branch: `feat/strategy-batch-1` (base: FDS-096, commit `9c52ffb`)
Spec order: 096b → 087 → 121 → 122 → 123 → 129 → backtest report.

## How the "full suite" is measured

CI runs `pytest app/test_*.py`. In this environment one test file kills its own
runner (`test_phase1_phase2_integration.py` sends `CTRL_C` to its process group)
and one scipy test is very slow, so the suite is run **one file at a time** with a
per-file timeout (`scratchpad/suite.ps1`: every `app/test_*.py` and
`app/tests/test_*.py`, excluding `test_phase1_phase2_integration.py`, which is
skipped here and unchanged by this batch). Baseline = commit `9c52ffb` (FDS-096)
run from a separate git worktree.

### Baseline (FDS-096, before this batch)

| File | Result |
|---|---|
| test_advanced_features | 22 passed |
| test_api | 1 passed |
| test_backup_validation | 35 passed |
| test_binance_exchange | 66 passed |
| test_circuit_breaker | 22 passed |
| test_comprehensive | no tests collected |
| test_core | 1 passed |
| test_credential_audit | 9 passed |
| test_credentials_rotation | 34 passed |
| test_database_manager | 36 passed |
| test_dependencies | 1 passed |
| test_error_handler | 24 passed |
| test_exchanges | 2 passed |
| test_gui_exchange_integration | 3 passed |
| test_hub_trainer | 1 passed |
| test_integration | 8 passed, **2 failed** (`test_graceful_degradation`, `test_powertrader_hub_creation`: `'tkapp' object has no attribute 'notebook'`) |
| test_paper_mode | 15 passed |
| test_paper_trading_integration | 8 passed, 1 skipped |
| test_phase3_integration | 15 passed |
| test_real_app | 1 passed |
| test_security_logger | 30 passed |
| test_subprocess_trainer | 1 passed |
| test_suite | 16 passed, **8 failed** (DB-file permission errors + exchange factory; identical before/after this batch) |
| test_tabbed_interface | 1 passed |
| test_trade_proposal_approval | 23 passed, **1 failed** (`test_expired_proposal_cannot_execute`, known) |
| test_trading_mode | 49 passed |

Pre-existing failures (not caused by this batch): `test_expired_proposal_cannot_execute`
(known), and the two `test_integration` hub tests above (they assert a `hub.notebook`
attribute that does not exist; they do construct the real hub, so they double as a
smoke test that hub start-up still works).

## Specs

### FDS-096b — price-source integrity — **done** (ended 2026-10-02 03:04 local)
- Commit: `e0d726e`
- Tests: new `app/tests/test_price_source_integrity.py` 48 passed (+17 subtests); existing `test_trading_mode` updated to the `Quote` API; full suite no worse than baseline (`test_suite` 8 pre-existing failures identical; `test_integration` 1 failed vs 2 at baseline — display-dependent).
- Decisions / notes:
  - Binance `bookTicker` has no timestamp. `quote_ts` is the response `Date` header (1 s resolution); a response without a usable Date header is **stale**, never live.
  - `simulate_and_flag` + a *stale* quote fills at the stale quote marked `stale` (more honest than inventing a price); with *no* quote it fills at the simulator price marked `simulated`.
  - Trader never uses its cached bid/ask older than `paper.max_quote_age_s` in paper mode.
  - Hub strip shows PRICES only from a status file less than 120 s old, so a stopped trader never leaves a stale "LIVE" claim.
- Out-of-scope bugs found: none new.

### FDS-087 — paper trading demo — **done** (ended 2026-10-02 03:04 local)
- Commit: `6869922`
- Tests: `app/tests/test_demo_paper_trading.py` 11 passed. Manual run against live Binance printed `Paper trading system: OPERATIONAL` (exit 0).
- Process note: the first 087 commit was made before reading a failing test (a format change after the test was written); amended before anything else was built on it. Commits are now gated on the test result in the same command.

### FDS-121 — strategy runtime, catalogue (lite), honest backtesting — **done** (ended 2026-10-02 03:34 local)
- Commit: `dae9b3e`
- Tests (new, all in `app/tests/`): indicators 17, catalogue 18, candles 22, backtest engine 30, runner 13, signal engine + trader integration 37, CLI 13 = 150 new tests, all passing. Full suite vs baseline: identical pre-existing failures only (`test_integration` x2, `test_suite` x8, known `test_expired_proposal_cannot_execute`).
- Acceptance: 1 indicators vs independent scalar references (1e-6) + hand values; 2 lookahead (mutating later bars never changes the decision, plus a backtest-level check); 3 fills at t+1 open with fees+slippage checked to 1e-9; 4 buy-and-hold on identical window/costs; 5 catalogue fails on missing field / orphan class / orphan entry; 6 scripted candles drive one ENTER and one EXIT through `pt_trader` into `PaperExchange`; 7 unknown id/engine -> no orders + ERROR; 8 CLI writes JSON + trades CSV (also run as `python -m app.backtest`); 9 random-price example labelled `DEMO ONLY - SYNTHETIC DATA`.
- Design decisions:
  - JSON catalogue (PyYAML is not in `requirements.txt`). Candle cache is CSV (parquet needs pyarrow, also not a dependency).
  - A strategy is a pure function of the last `lookback_bars` bars; backtest and live use the same `StrategyRunner` and window, so they cannot disagree. `StrategyRunner` already implements the FDS-129 composition rules (max stop, stop only moves up, exit-rule attribution, entry gates) so 129 only adds overlay classes, persistence and telemetry.
  - In `catalogue` mode the legacy DCA buys and trailing-PM sells are **off**; entries use the trader's existing (tiny) start allocation; exits sell only the ledger quantity and never a holding without a ledger cost basis. Documented in `ARCHITECTURE.md` (section "Signal Path and Strategy Engine").
  - OOS window starts flat at the split; bars before the split are indicator history only (never traded). A position still open on the last bar is closed at that bar's close with costs, in both strategy and benchmark.
  - Undefined KPIs (e.g. Sharpe with zero variance, win rate with no trades) are `null`, never 0.
- Bugs found and fixed while building: SignalEngine retry rate-limit did not apply before the first successful fetch; warning throttle treated a clock near 0 as "just warned".
- Out-of-scope observations: the trader's risk adapter limits any single order to 1% of the portfolio (`RiskManager.validate_trade`), so strategy sizing above that would be blocked; left as is.
- Environment note: `test_phase1_phase2_integration.py` is excluded from the per-file suite runner because it raises `KeyboardInterrupt` in its own process group on Windows (pre-existing, not changed by this batch).

### FDS-122 — STRAT-001 DEMA/TEMA crossover — **done** (ended 2026-10-02 03:51 local)
- Commit: `677a069`
- Tests: new `app/tests/test_trend_crossover.py` 28 passed (+23 subtests). Full suite vs baseline: identical pre-existing failures only. `test_advanced_features` / `test_core` timed out once when the machine was busy with other work and passed when re-run alone (63 s / 8 s).
- Acceptance: 1 ENTER fires exactly on bar `cross + persistence_bars` (checked for k = 0,1,2,3,5 and against an independent run-length restatement of the rule on a choppy market for TEMA and DEMA); 2 ADX below `adx_min` -> no ENTER (and the threshold is inclusive); 3 EXIT on the first bar fast < slow, no persistence; 4 `slow_len <= fast_len` raises `StrategyError` naming both; 5 HOLD/WARMUP before `3*slow_len + adx_len` bars; 6 backtest CLI on cached BTCUSDT 1h candles prints full KPIs (in/out-of-sample + buy-and-hold); 7 paper trader runs STRAT-001 on scripted candles (buy at the confirmed cross bar, sell at the death cross) with no runtime errors; 8 defaults not tuned (they are the spec's).
- `strategy.active_id` default is now `STRAT-001` (settings manager and reader); the engine/trader tests pin `STRAT-000` explicitly.
- Test-fixture lesson: TEMA is lag-free on a straight line, so a linear ramp gives degenerate fast/slow crosses. Fixtures use smooth waves.
### FDS-123 — STRAT-002 Supertrend with ATR trailing exit — **done** (ended 2026-10-02 04:01 local)
- Commit: `df2b12e`
- Tests: new `app/tests/test_supertrend.py` 30 passed (+29 subtests); catalogue +1. Full suite vs baseline: identical pre-existing failures only.
- Acceptance: 1 Supertrend matches (a) an 8-bar case worked by hand in exact fractions (ATR 7/3, 23/9, 73/27, 308/81; line values to 1e-9) with one flip each way, and (b) an independent scalar reference on a 70-bar fixture (both flip directions) and on 600 real BTC bars, tolerance 1e-6; 2 final lower band never decreases while direction is up and the upper band never rises while down — checked on the hand/70-bar fixtures, cached real BTC and ETH candles at four parameter sets, and 40 random walks x 3 parameter sets; flips follow the spec rules (close > prior final upper / close < prior final lower) on real candles; 3 ENTER respects `confirm_bars` (0-3) against an independent restatement, including a whipsaw market where half the flips die inside the window; EXIT on the flip bar and every bar while down; 4 HOLD/WARMUP before `3*atr_len` bars; 5 CLI runs STRAT-002 on BTCUSDT and ETHUSDT at 1h and 4h with the full KPI set (4h bars are exact UTC-aligned aggregations of the recorded real 1h candles); 6 paper trader follows STRAT-002 through several round trips on scripted candles; 7 defaults are the spec's (no tuning).
- Design decision (band carry rule): the bands carry forward **with the trend direction** (lower band = `max(basic_lower, previous final lower)` while up; upper = `min(basic_upper, previous final upper)` while down; fresh basic band on a flip). The other common formulation resets a band whenever the *previous close* sits beyond it, which can let the lower band fall while the direction is still up when a close lands between the old and new band. The spec's acceptance criterion (lower band never decreases while up) holds by construction with the direction-based rule. Flip tests use the *previous* final band, as specified.
- Gap found and fixed while testing: catalogue parameter validation accepted a float for whole-number parameters (`atr_len=10.5`); now rejected (float-valued params have float defaults; `adx_min` default is `20.0`).
- Supertrend state is path-dependent, so a signal depends on the window it is given; backtest and live use the same `lookback_bars` window (230 bars at default), so they agree.
- Fixture added: `app/tests/fixtures/ETHUSDT_1h.csv` (recorded real Binance 1h candles, 2026-06-10..2026-08-12).
### FDS-129 — composable risk overlays (#113-#116) — **done** (ended 2026-10-02 04:17 local)
- Commit: `d486960`
- Tests: new `app/tests/test_overlays.py` 47 passed (+11 subtests). Full suite vs baseline: identical pre-existing failures only (`test_integration` showed 1 failure this run vs 2 before: display-dependent).
- Acceptance: 1 ratchet — stop = entry*(1+0.5%) exactly at +2.00% (not at +1.99%), +1% per further 1% step, never decreases through a rally and pullback, exits when close < stop and names `stop:OVL-RATCHET`; 2 ATR — stop equals running max of (highest close - mult*ATR) bar by bar, never decreases although the raw stop falls on a widening-range fixture; 3 PLOCK — each stage engages exactly at its threshold (2.99/3.00, 5.99/6.00, 9.99/10.00); 4 cooldown — blocked for 3 bars after a win, 12 after a loss, whichever is longer; global vs per-symbol; 5 composition of RATCHET+ATR+PLOCK — effective stop equals the max of three independent single-overlay runs at every bar, ownership changes hands, exit reason names the owner at that moment, and adding overlays never exits later than any one alone; 6 restart mid-position — a fresh trader/engine restores the position, stop, owner and overlay state identically, keeps the stop monotonic, then closes the position; cooldown timers also survive; 7 backtest CLI runs STRAT-001 and STRAT-002 with and without `--overlays OVL-ATR,OVL-COOLDOWN` (benchmark unchanged by overlays; overlays change results on real ETH candles; trades CSV names `stop:*` exit rules); 8 no test uses the network.
- Design decisions: gains are measured on the **highest close** since entry (so ratchet steps and profit-lock stages, once reached, stay reached); a cooldown is counted from the bar whose open the exit filled (with `bars_after_exit=3` signals on that bar and the next two are blocked); a "loss" is exit fill below entry fill (before fees); `OVL-COOLDOWN` needs the bar length (`StrategyRunner.set_timeframe`) and raises rather than guessing when it is missing. `Overlay` gained `on_exit` and `export_state/import_state` beyond the spec's three methods (cooldowns need to learn about exits and survive restarts).
- Hub: text only — the trail-line column shows `<stop> (<owner>)` and its heading lists the overlay ids when the catalogue engine is active; not exercised by a GUI test (the position table is built from live trader status).
- Bugs found and fixed while testing: `register` set `strategy_id` but not `overlay_id` on overlay classes.
### Backtest report (run-order section 5) — **done** (ended 2026-10-02 04:25 local)
- Output: `docs/dev/BACKTEST-REPORT-batch-1.md` (+ `docs/dev/backtest-batch-1/` JSON and trades CSV for all 16 runs; reproduce with `python docs/dev/run_backtest_batch1.py fetch|run|report`).
- Data: BTCUSDT and ETHUSDT, 1h and 4h, 2023-01-01..2026-09-30 from Binance public klines (32,855 1h and 8,214 4h candles each; one missing 1h bar per symbol, reported not filled); SHA-256 of each cached file is in the report.
- Declared before any result was seen: default parameters for STRAT-001/002; one overlay set (OVL-ATR + OVL-COOLDOWN, defaults); 10 bps fee + 5 bps slippage; 70/30 split. Nothing was tuned on anything.
- Result (computed + asserted in the generator): 8 of 16 out-of-sample runs finished ahead of buy-and-hold, **all at 4h and all by losing less in a falling market**; all 16 strategy runs lost money out of sample (-17% to -65%) while buy-and-hold lost 29-40%; all eight 1h runs trailed buy-and-hold; in-sample buy-and-hold (+268% to +608%) beat every strategy run. Overlays helped OOS in 6 of 8 comparisons and in-sample in 1 of 8 (a lower-exposure effect, not evidence of skill). Plain answer in the report: no evidence of an edge.

## Batch summary

| Spec | Commit |
|---|---|
| FDS-096 (base) | `9c52ffb` |
| FDS-096b | `e0d726e` |
| FDS-087 | `6869922` |
| FDS-121 | `dae9b3e` |
| FDS-122 | `677a069` |
| FDS-123 | `df2b12e` |
| FDS-129 | `d486960` |
| Backtest report | see `git log` |

- Final per-file suite vs baseline: only the pre-existing failures remain (`test_expired_proposal_cannot_execute`, `test_integration` hub tests, `test_suite` DB/permission tests). `test_phase1_phase2_integration.py` is excluded from the runner here (it kills its own process group on Windows). Tk-dependent tests skip when no display is available.
- Manual network check: `python app/demo_paper_trading.py` printed `Paper trading system: OPERATIONAL` (exit 0) against live Binance.
- Nothing was pushed; `main` was never committed to. API keys were never read, created or requested; only public Binance endpoints were used.