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
- Commit: see `git log` (`FDS-121: ...`)
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
