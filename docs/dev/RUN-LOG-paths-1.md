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

## Phase 2 — Secrets module

* `app/pt_secrets.py` is the only module that reads or writes credentials: `keyring`, service
  `SJackson.PowerTraderAI`, entries `<exchange>:<field>` (`coinbase:key_name`, `coinbase:private_key`,
  `robinhood:api_key`, `robinhood:private_key`, `<x>:api_key|api_secret|passphrase`, DeFi
  `<x>:private_key`). API: `get_secret`, `set_secret`, `delete_secret`, `has_credentials`, plus
  `set_credentials`, `get_credentials` (connector kwargs), `credential_source`, `delete_credentials`.
* Precedence defined once: environment variables, then keyring. A source counts only when it holds every
  required field (values are never mixed); both full -> environment wins and one warning per exchange
  names the source (never a value). The env-var table is in the module docstring; the existing names
  (`POWERTRADER_<X>_API_KEY/_API_SECRET/_PASSPHRASE`, `POWERTRADER_ROBINHOOD_PRIVATE_KEY`) are kept, so
  the Coinbase gate tests' environment set-up still works unchanged.
* No plaintext fallback: `fail`/`null` backends and every `keyrings.alt` (file) backend are refused; a
  chained backend is narrowed to its first acceptable member so a write cannot fall through to a file.
  Without a backend `set_secret` raises `KeyringUnavailable` naming the env vars and saying the app stays
  in paper mode; nothing is written.
* Redaction: `Secret` (repr/str/format `***`, no pickle/JSON) and `Credentials` (a dict with a redacted
  repr). Backend errors are re-raised `from None` so a traceback cannot carry a value.
* Size: the Windows backend stores the value as UTF-16 (`win32ctypes` `create_unicode_buffer`), so the
  2,560-byte `CRED_MAX_CREDENTIAL_BLOB_SIZE` is about 1,280 characters. A Coinbase EC PEM is about 230
  characters (SEC1 and PKCS#8 both tested); a Robinhood seed is 44. `SecretTooLarge` is raised above the
  limit on every platform, before anything is written. Checked from library source only; the real
  Credential Manager was never written to or read.
* One store: `ExchangeConfigManager` keeps exchange settings in `trading_config.json` and credentials in
  the keyring (loaded configs carry them in memory; `repr=False`); credential fields found in the file are
  ignored with a warning and never written back. `MultiExchangeManager`, `ExchangeFactory` (the live gate)
  and the setup window all read through `pt_secrets`. `exchange_config.json` now only supplies
  non-secret constructor options. `ExchangeFactory._credentials`/`load_credentials` keep their names (the
  gate tests patch them).
* Latent bug fixed: `ExchangeFactory.get_exchange` uses caller-supplied credentials *or* stored ones,
  never both, so the duplicate-kwarg `TypeError` that silently dropped an exchange cannot happen.
* Robinhood: `KeyringCredentialManager` (same method names as the old vault, so `pt_hub.py` still calls
  `encrypt_credentials`/`decrypt_credentials` and `test_credential_audit` passes unchanged) stores in the
  keyring; only rotation dates go to `robinhood_rotation.json` in the config folder. `get_credentials()`
  = env then keyring; it no longer reads or auto-migrates the old vault or plaintext files (Phase 4 does).
  The hub's Robinhood window no longer makes plaintext `*.bak_<ts>` copies, no longer wipes legacy files
  by itself, and "Clear" removes the keyring entries; the "Open Folder" buttons are gone.
* GUI: a saved secret, private key or passphrase is never echoed into the setup form (a hint says it is
  saved and blank keeps it). The API key / Coinbase key name is still shown: it identifies the key, and
  the existing `test_reselecting_never_echoes_the_saved_private_key` asserts it is displayed.
* Tests: `test_pt_secrets.py` (24), `test_credentials_single_source.py` (15: GUI-saved key is what the
  live gate builds; paper never builds it; no secret in the config file; legacy plaintext ignored;
  env+keyring keeps the exchange; explicit + stored creds don't collide; Robinhood keyring/env/no-file;
  no-keyring refusal; setup window never echoes), `test_isolation_guard.py` (6).
* `keyring>=24.0.0` added to both requirements files.

Suite (this commit's files in the scratch worktree): baseline + 56 new tests passing; the same 11 known
failures; the paper/live gate tests (`test_trading_mode`, `test_paper_mode`, `test_coinbase_paper_gate`)
unchanged and green.

## Phase 3 — Rewire every component

Every path in the inventory now goes through `pt_paths`, every credential through `pt_secrets`.

* **Config** (`config_dir()`): `pt_config.json` (`SettingsManager`, `trading_mode.default_settings_path`,
  strategies), `gui_settings.json` (hub, trader, thinker), `trading_config.json`, `exchange_config.json`,
  the YAML configs (`<config>/yaml/`), `monitoring.json`, `production.ini`, `integration_test.json`,
  `update_settings.json`. Every config read strips credential keys (`pt_secrets.strip_secret_fields`:
  `api_key`, `api_secret`, `private_key`, `passphrase`, `password`, `*_secret`, `*_password`, `*_token`,
  ...) with a warning naming the key path, never the value; every write strips them too, so a credential
  is never written back. The SMTP password moved to `pt_secrets` (`smtp:password` /
  `POWERTRADER_SMTP_PASSWORD`).
* **Shipped defaults**: `trading_config.example.json` stays read-only in the program folder; the hub copies
  it into the config folder on first run only (`pt_paths.install_default`, never overwrites);
  `ExchangeConfigManager()` falls back to it.
* **Data** (`data_dir()`): `hub_data/` (hub, trader, thinker, API server, chart components), the neural
  folders (default `<data>/hub_data/models`, BTC in the root, other coins in `<SYM>/` as before), every
  SQLite database (order management -- the research engine now shares it instead of a second CWD copy --,
  automation, holdings, institutional, portfolio optimisation/analytics, risk, compliance), training
  summaries (`<data>/training_results/`), model checkpoints, evaluations, updater backups.
* **Logs** (`log_dir()`): `pt_logging_system`, security audit log (was `~/.powertraderai/logs`),
  `credential_audit.jsonl`, emergency snapshots, production logs, reports.
* **Cache** (`cache_dir()`): candles (`<cache>/candles`), `market_data.db`, the pickle cache, updater
  downloads.
* The trainer is no longer copied into the coin folders: the hub runs `app/pt_trainer.py` with the coin's
  neural folder as working directory (started from a terminal inside the program folder it moves there
  itself). Child processes start with `cwd = data_dir()`, so a stray relative write cannot land in `app/`.
  `<SYM>_current_price.txt` is written to the trader's data folder.
* `hub_data_dir` / `main_neural_dir` settings: blank = defaults; relative = under `data_dir()`; a value
  inside the program/install folder is refused with a warning (`pt_paths.user_dir_setting`). The thinker
  now honours `main_neural_dir` like the hub and trader (it used to always write into `app/`).
* The paper/live gate code is unchanged except `default_settings_path()`; its tests pass unchanged.
* Tests: `test_no_legacy_paths.py` (static: no module other than `pt_paths`/`pt_migrate` builds a path to
  `pt_config.json`, `gui_settings.json`, `trading_config.json`, `exchange_config.json` or `hub_data` --
  verified to flag 19 sites in the baseline versions of 11 modules), `test_program_dir_read_only.py`
  (default-path components started with `cwd = app/` change nothing under the install folder),
  `test_config_no_secrets.py` (two YAML tests skip here because PyYAML is not installed in the suite venv;
  they pass in a second venv with PyYAML).
* Changed data source of one existing test (`test_demo_paper_trading.test_never_reads_or_writes_the_users_config_or_ledger`):
  it stat'ed the developer's real `app/pt_config.json`; it now checks `pt_paths.settings_file()` and
  `pt_paths.hub_dir()` (the fixture's temp home). Assertions unchanged.
* Left as is (not runtime state): build/dev tools (`production_deployment.create_deployment_package`,
  `.github/scripts/create_desktop_installer.py`, `docs/dev/run_backtest_batch1.py`), user-chosen
  export/import paths from file dialogs, read-only program assets (`strategies/catalogue.json`,
  `data_provider_config.json`), caller-supplied paths (`pt_backup`, `pt_database_manager`, `pt_utils`),
  and the tracked trainer copies in `app/<SYM>/` (no longer run by the hub).

Suite (this commit's files in the scratch worktree): Phase 2 results + `test_no_legacy_paths` 2,
`test_program_dir_read_only` 5, `test_config_no_secrets` 5 passed / 2 skipped. Same 11 known failures.
The run wrote nothing new into the worktree's `app/` or root (checked by modification time).

## Phase 4 — Migration

* `app/pt_migrate.py`, run by the hub before it reads any setting (and before the first-run template
  copy, so a migrated `trading_config.json` is never shadowed by the template), and as a command.
* Sources: `app/` (`pt_config.json`, `gui_settings.json`, `trading_config.json`, `exchange_config.json`,
  `hub_data/`, BTC neural files in `app/` and per-coin files in `app/<SYM>/`, `order_management.db`(+`-wal`/
  `-shm`), `institutional_trading.db`, `credential_audit.jsonl`, emergency snapshots, the Robinhood vault
  `r_key.enc`/`r_secret.enc`/`.pt_salt` (+ `.pt_cred_meta`) or `r_key.txt`/`r_secret.txt`, and the
  `r_key.txt.bak_*` plaintext copies) and the install root (the CWD-relative DBs `market_data.db`,
  `portfolio_optimization.db`, `order_management.db`, `data/*.db`, and `logs/`). Both roots come from
  `pt_paths.legacy_dir()` / `legacy_install_dir()`, which the test fixture points at empty temp folders.
* Destinations: config files (credentials stripped; `gui_settings` folder settings that pointed into the
  old program folder are blanked so the new defaults apply), keyring (`pt_secrets`, field names only in
  the report), `hub_data` -> data folder (`candles/` -> cache folder), neural files -> `models/`, DBs ->
  data folder (`market_data.db` -> cache), logs -> `<logs>/legacy/`, audit log -> logs.
* Never deletes or modifies a legacy file; never overwrites a file or keyring entry in the new location
  (conflict listed, new location kept). `migration-report.md` lists copies, credentials moved (by
  `exchange:field`), conflicts, failures, legacy files still holding plaintext credentials, and the copies
  that can be removed.
* Idempotent: `migration-state.json` records each handled item by legacy size+mtime and whether the legacy
  copy is redundant; a second run with nothing new writes nothing (not even the state file) and returns
  no report, so the hub shows no dialog. A legacy file changed later is reported once. Credentials that
  could not be stored (no keyring) are not recorded, so they are retried on the next start.
* Hub dialog: summary + **Remove old files**; deletion only after an explicit Yes on a warning that the
  files may contain plaintext credentials, and only of files the migration recorded as safely copied
  (never conflicted files, never code). Emptied legacy sub-folders are pruned; root folders never.
* `python app/pt_migrate.py --from <path>`: import one config file (kind by name or content); same rules.
  `--remove-old-files` asks before deleting.
* Tests: `test_pt_migrate.py` (12): fresh migration (every destination; legacy tree byte-identical with
  identical mtimes afterwards), migrated settings are what the app reads, conflicts (file, keyring
  entry, hub_data file), idempotent re-run, changed legacy file, no keyring (nothing stored, retried
  later), Robinhood vault decrypted into the keyring, import from path (CLI), import never overwrites,
  removal only after confirmation (function, CLI, Tk dialog).

Suite (this commit's files in the scratch worktree): Phase 3 results + `test_pt_migrate` 12 passed. Same
11 known failures.
