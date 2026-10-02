# Run log — FDS-108a: separate product directory from user config, data and secrets

Branch: `feat/user-data-separation`. Paper mode only; no network calls in tests; no real orders.

## Starting point

* The branch already contained `main` + `feat/strategy-batch-1` + `fix/coinbase-connector`, plus the
  owner's commit `25bf2b8` ("pushing config changes": `config/*.yaml` and one `.gitignore` line).
* `chore/untrack-trading-config`, the third prerequisite, was **not** merged yet. It was merged
  here as `58efed2` (local merge commit, nothing pushed). The only conflict was `.gitignore`
  (both sides appended entries); both sides were kept.
* Working tree clean before and after the baseline run. `app/pt_config.json` and
  `app/gui_settings.json` exist on this machine. They were never opened; only their SHA-256 prefixes
  were recorded (unchanged by the baseline run).

## How the suite is measured

Same per-file runner as `RUN-LOG-coinbase-1.md`: every `app/test_*.py` and `app/tests/test_*.py`, one
file at a time with a timeout, `test_phase1_phase2_integration.py` excluded (it kills its own process
group on Windows). Interpreter: Python 3.13 in a throw-away venv outside the repo
(`--system-site-packages` + `pytest`, `pytest-timeout`; later `platformdirs` and `keyring`).

## Baseline (after the prerequisite merge, before any FDS-108a change)

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
| test_integration | 8 passed, **2 failed** (`test_graceful_degradation`, `test_powertrader_hub_creation`) |
| test_paper_mode | 15 passed |
| test_paper_trading_integration | 8 passed, 1 skipped |
| test_phase3_integration | 15 passed |
| test_real_app | 1 passed |
| test_security_logger | 30 passed |
| test_subprocess_trainer | 1 passed |
| test_suite | 16 passed, **8 failed** (`test_exchange_factory`, `test_database_initialization`, `test_holdings_database`, `test_holdings_manager`, `test_performance_metrics`, `test_portfolio_analytics_initialization`, `test_portfolio_snapshot`, `test_database_integration`) |
| test_tabbed_interface | 1 passed |
| test_trade_proposal_approval | 23 passed, **1 failed** (`test_expired_proposal_cannot_execute`) |
| test_trading_config_fallback | 9 passed |
| test_trading_mode | 49 passed, 1 skipped |
| tests/test_backtest_cli | 13 passed |
| tests/test_backtest_engine | 30 passed |
| tests/test_candles | 22 passed |
| tests/test_catalogue | 19 passed |
| tests/test_coinbase_auth | 20 passed, 1 skipped |
| tests/test_coinbase_connection | 27 passed |
| tests/test_coinbase_gui | 12 passed |
| tests/test_coinbase_paper_gate | 15 passed |
| tests/test_demo_paper_trading | 11 passed |
| tests/test_indicators | 17 passed |
| tests/test_overlays | 47 passed |
| tests/test_price_source_integrity | 48 passed |
| tests/test_runner | 13 passed |
| tests/test_signal_engine | 37 passed |
| tests/test_supertrend | 30 passed |
| tests/test_trend_crossover | 28 passed |

11 failures, exactly the known set: `test_expired_proposal_cannot_execute` (1), the two
`test_integration` hub tests (2), eight `test_suite` tests (8).

## Phase 0 — Inventory

`docs/dev/PATHS-INVENTORY.md`. Found by grep plus three read-only sweeps (hub; trader/thinker/trainer/
exchanges/settings; every other module), Python source only. Key results:

* Credentials live in four places: `trading_config.json` (setup window), `exchange_config.json` (live
  gate), the Robinhood vault `r_key.enc`/`r_secret.enc` (+ legacy `r_key.txt`/`r_secret.txt` and
  never-deleted `*.bak_<ts>` plaintext copies), and environment variables. The GUI and the live gate read
  different stores.
* The "two places" bug is a `TypeError` (duplicate `api_key` kwarg) swallowed by
  `ExchangeManager.add_exchange`.
* The running app writes into `app/` (settings, hub_data, coin folders, vault, two SQLite DBs, audit log,
  snapshots) and into the CWD (four more SQLite DBs, logs, a second `order_management.db`).
* The eight `test_suite` failures are open SQLite handles in `%TEMP%` (7) and an empty exchange registry
  (1) — not program-directory writes.
* Committed config files (`config/*.yaml`, `app/config/*.json`, `trading_config.example.json`) were
  checked through `git show` for credential keys: all such values are empty.

Suite: documentation-only commit; not re-run (identical to baseline).

## Phase 1 — Paths module

* `app/pt_paths.py`: `config_dir()`, `data_dir()`, `log_dir()`, `cache_dir()`, `hub_dir()`, `models_dir()`,
  `program_dir()`, `legacy_dir()`, `ensure_dirs()`, `describe()`, named config files, `install_default()`,
  `write_private_text()` (atomic, `0600` on POSIX), `secure_file()`, `is_inside_program_dir()`.
  `platformdirs` with `appname="PowerTraderAI"`, `appauthor="SJackson"`; config `roaming=True`, data
  `roaming=False`; folders created lazily (`0700` on POSIX). `POWERTRADER_HOME` puts everything under
  `config/`, `data/`, `logs/`, `cache/`. Functions return `str` (the codebase is `os.path`-based).
* Windows resolution checked: `%APPDATA%\SJackson\PowerTraderAI`, `%LOCALAPPDATA%\SJackson\PowerTraderAI`,
  `...\Logs`, `...\Cache` (string comparison only; nothing created).
* `app/conftest.py` (autouse, every test under `app/`): fresh `POWERTRADER_HOME` temp folder per test (and
  one set at import, before any module computes a path), in-memory keyring per test,
  `PYTHON_KEYRING_BACKEND=fail` for child processes, real platform-folder resolution blocked, legacy folder
  = empty temp folder, and a per-test check that the four real folders were not created or changed
  (`os.stat` of the folder only).
* `platformdirs>=4.0.0` added to `requirements.txt` and `app/requirements.txt`.
* Tests: `app/tests/test_pt_paths.py` (11 + 1 POSIX-only skip).

Suite (run on exactly this commit's files in a scratch worktree): baseline + `test_pt_paths` 11 passed;
`test_trading_mode` 50 passed (baseline 49 + 1 skipped: a Tk test that intermittently cannot initialise Tk).
Same 11 known failures, no new ones.
