# Run log — FDS-108a: separate product directory from user config, data and secrets

Branch: `feat/user-data-separation`. Paper mode only; no network calls in tests; no real orders.

## Starting point

* The branch already contained `main` + `feat/strategy-batch-1` + `fix/coinbase-connector`, plus the
  owner's commit `25bf2b8` ("pushing config changes": `config/*.yaml` and one `.gitignore` line).
  * *Corrected after review:* `25bf2b8` was dropped during review. The branch was rebuilt from
    `6a8cc2b` without it (chore merge now `23243b0`, FDS-108a phases `4938e39`..`d949df4`; the old tip
    `7bbb810` is kept as `backup/user-data-separation-7bbb810`). Its root `config/*.yaml` were
    byte-identical to `app/config/*.yaml` and read by no code; they are no longer tracked. See
    `RUN-LOG-paths-2.md`.
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
| test_hub_trainer | 1 passed (tests nothing: hard-coded `C:\Users\Administrator` paths and its own copy of main's copy-and-run logic; see `RUN-LOG-paths-2.md` item 2) |
| test_integration | 8 passed, **2 failed** (`test_graceful_degradation`, `test_powertrader_hub_creation`) |
| test_paper_mode | 15 passed |
| test_paper_trading_integration | 8 passed, 1 skipped |
| test_phase3_integration | 15 passed |
| test_real_app | 1 passed |
| test_security_logger | 30 passed |
| test_subprocess_trainer | 1 passed (tests nothing: hard-coded `C:\Users\Administrator` paths, no assert; see `RUN-LOG-paths-2.md` item 2) |
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
  * *Corrected after review:* (1) Legacy files can be modified: a legacy Robinhood vault
    (`r_key.enc`/`r_secret.enc`) that only decrypts with the old machine-password derivation is
    re-encrypted in place, in the legacy folder, by `SecureCredentialManager.decrypt_credentials`
    (`app/pt_credentials.py:350-418`, called from `app/pt_migrate.py`'s Robinhood step), and its
    `.pt_cred_meta` is rewritten, or created if missing (`encrypt_credentials` saves metadata), so up
    to three legacy files are written. Not reachable on the owner's machine (no vault there). (2) Conflicts, after review item 4: both files are kept. A file
    already in the new location is never replaced; a legacy file that differs is copied next to it as
    `<name>.conflict-app.<ext>` or `<name>.conflict-root.<ext>` (config copies stripped of credentials).
    When `app/` and the install root both hold a version of a file the new location does not have yet,
    the newer one gets `<name>` and the older one the conflict name, decided before anything is copied
    (`app/pt_migrate.py:435-555`, configs `594-629`). Keyring entries are still never replaced.
* Idempotent: `migration-state.json` records each handled item by legacy size+mtime and whether the legacy
  copy is redundant; a second run with nothing new writes nothing (not even the state file) and returns
  no report, so the hub shows no dialog. A legacy file changed later is reported once. Credentials that
  could not be stored (no keyring) are not recorded, so they are retried on the next start.
* Hub dialog: summary + **Remove old files**; deletion only after an explicit Yes on a warning that the
  files may contain plaintext credentials, and only of files the migration recorded as safely copied
  (never conflicted files, never code). Emptied legacy sub-folders are pruned; root folders never.
  * *Corrected after review:* as built here, `--remove-old-files` deleted every path listed at migration
    time without looking at it again, so a legacy file changed afterwards (for example by running `main`)
    or whose new copy had gone could be lost; the review reproduced this. After review item 3 the dialog
    and the CLI share one path, `remove_old_files` (`app/pt_migrate.py:1320`). It refuses, with the
    reason, any file not recorded as migrated, whose SHA-256 differs from the one recorded at migration,
    or whose migrated copy (file or keyring entry) is missing (`_refusal`, `:1185`), and checks each unit
    again after renaming it aside, just before deleting it (`_delete_unit`). A SQLite `.db` with its
    `-wal`/`-shm`/`-journal` is one unit, checked and deleted together, sidecars first and the `.db` last;
    if a delete still fails, the parts not yet deleted are put back, so a `.db` can be left without its
    `-wal` or `-journal` (their content is in the new location). On macOS/Linux a program that already
    holds a part open can still write to it after the last check (on Windows the rename fails then). In
    a git checkout `app/pt_config.json` and `app/gui_settings.json` are always kept (`_kept_reason`).
    After item 4 a conflicted file is removable once its conflict copy exists, under the same checks.
    Since the safety audit, files reached through a link or junction are neither copied nor removed (a
    recorded file whose real path changed is refused), and a legacy config that is the same file as the
    one in use is skipped.
* `python app/pt_migrate.py --from <path>`: import one config file (kind by name or content); same rules.
  `--remove-old-files` asks before deleting.
* Tests: `test_pt_migrate.py` (12): fresh migration (every destination; legacy tree byte-identical with
  identical mtimes afterwards), migrated settings are what the app reads, conflicts (file, keyring
  entry, hub_data file), idempotent re-run, changed legacy file, no keyring (nothing stored, retried
  later), Robinhood vault decrypted into the keyring, import from path (CLI), import never overwrites,
  removal only after confirmation (function, CLI, Tk dialog).

Suite (this commit's files in the scratch worktree): Phase 3 results + `test_pt_migrate` 12 passed. Same
11 known failures.

## Phase 5 — Docs and visibility

* README: new section **Where your data lives** with the section-2 table, what goes where, the
  credential env vars, `POWERTRADER_HOME`, and the upgrade/migration behaviour.
* Settings window: a **Paths** section shows the resolved config, data and log folders (read-only
  fields), each with an **Open folder** button.
* Docs that sent users to files under `app/` or described plaintext/file key storage were updated:
  `docs/exchanges/coinbase-setup.md`, `docs/setup/CREDENTIAL_SETUP.md`,
  `docs/reference/QUICK_REFERENCE.md`, `docs/reference/API_REFERENCE.md`,
  `docs/user-guide/README.md`, `docs/user-guide/DESKTOP_INSTALLATION_GUIDE.md`,
  `docs/README_DESKTOP.md`, `docs/getting-started/README.md`, `docs/getting-started/installation.md`,
  `docs/guides/GUI_USER_GUIDE.md`, `docs/technical/ARCHITECTURE.md`.
* `.gitignore`: added the legacy runtime paths from inventory section 11 (`app/gui_settings.json`,
  `app/exchange_config.json`, `app/r_key*`, `app/r_secret*`, `app/.pt_salt`, `app/.pt_cred_meta*`,
  `trainer_status.json`, `killer.txt`, `emergency_snapshot_*.json`, `*_current_price.txt`,
  `cache/`, `model_evaluations/`, `test_results/`, `app/migrations/`, `app/backup/`, `app/temp/`,
  `app/data/`, `data/*_training_results.json`, report files). `app/trading_config.json` kept (an
  existing test checks it).
* `app/trading_config.example.json` (the only `*.example.json`) no longer has `api_key`/`api_secret`/
  `passphrase` at all, and carries a `_note` pointing to **Configure exchange APIs** and the env vars.
* Config files written by the YAML config manager, the live monitor and production deployment are now
  `0600` on POSIX too (the app's own config writers already were).
* Tests: `test_docs_and_visibility.py` (5).

### End-to-end check of the hub (acceptance 2 and 9)

The hub (`app/pt_hub.py`) was started from a clean checkout of this branch in the scratch worktree
(`git clean -fdx` first, cwd = install root like `start_powertrader.bat`) with `POWERTRADER_HOME` set
to a folder outside the checkout and `PYTHON_KEYRING_BACKEND` = the fail backend (no credential store),
left running 60 s, then stopped. The window stayed up and every file it created landed under
`POWERTRADER_HOME` (`config/trading_config.json` from the template, `data/*.db`,
`cache/market_data.db`); no `pt_config.json` was written, so the mode stayed the paper default.

* **First run found a leak:** `market_data.db` appeared in the install root. `MarketDataManager`
  (the hub's market data tab) still passed the bare name `"market_data.db"` to the aggregator; Phase 3
  had only changed the aggregator's default. Fixed here (default `None` -> cache folder), added to
  `test_program_dir_read_only`, and `test_no_legacy_paths` gained a second static rule: no relative
  `*.db`/`*.sqlite` literal outside a `pt_paths` call (checked to flag the old defaults in four
  modules plus this one).
* **Second run: 0 files changed inside the checkout.**
* Not done with `POWERTRADER_HOME` unset: that would create files in the real `%APPDATA%` /
  `%LOCALAPPDATA%`, which the run protocol forbids. The unset case differs only in how the four base
  folders resolve, which `test_pt_paths` checks (Windows layout matches the spec, string comparison).
* The hub makes the same public market-data requests it always has while running; no order was placed.

### Acceptance criteria

| # | Criterion | Evidence |
|---|---|---|
| 1 | Inventory covers every runtime read and write | `docs/dev/PATHS-INVENTORY.md` |
| 2 | Clean checkout: hub writes nothing in the program folder | hub run above (0 changes); `test_program_dir_read_only`; `test_no_legacy_paths` |
| 3 | Windows: config in `%APPDATA%\SJackson\PowerTraderAI\`, data in `%LOCALAPPDATA%\SJackson\PowerTraderAI\` | `test_pt_paths::test_windows_layout_matches_the_spec` |
| 4 | No credential written to any file | `pt_secrets` keyring only; config readers/writers strip credential keys; `test_credentials_single_source`, `test_config_no_secrets`, `test_pt_secrets` no-backend tests. (The old `SecureCredentialManager` file vault class remains for its own tests and for the migration to read old vaults; no production code writes with it.) |
| 5 | Setup windows and live gate read from the same place | `test_gui_saved_coinbase_key_is_what_the_live_gate_builds_with` |
| 6 | Two sources no longer drop the exchange; precedence applied and logged | `test_env_and_keyring_both_set_no_longer_drop_the_exchange`, `test_explicit_credentials_and_stored_ones_do_not_collide`, `test_environment_wins_over_keyring_and_the_source_is_logged` |
| 7 | Legacy files migrate on first start, nothing deleted without confirmation, report lists every move | `pt_hub` start-up hook; `test_pt_migrate` |
| 8 | `pt_migrate.py --from <path>` | `test_import_a_backup_config_from_anywhere` |
| 9 | No keyring: nothing stored in plaintext, hub starts in paper mode | `test_no_backend_refuses_and_writes_no_file`, `test_without_a_keyring_nothing_is_stored_and_trading_stays_paper`, migration no-keyring test, hub run above |
| 10 | Static legacy-path test passes | `test_no_legacy_paths` |
| 11 | Suite at baseline or better; no assertion weakened, skipped or deleted | suite below; the only edit to an existing test is the data source of one `test_demo_paper_trading` test |
| 12 | Paper/live gate behaviour and tests unchanged | gate test files untouched and green; `trading_mode.py` changed only `default_settings_path()` (the credential source behind `ExchangeFactory` is now `pt_secrets`, as phase 2 requires) |

### For the owner

* **Out of scope, still owed under #108** (comment to post when the PR opens): master password or
  encrypted start-up gate (closed PR #130); key rotation UI and expiry reminders; an actual installer
  (MSI, pkg, deb) -- this branch only makes one possible; encrypting config files at rest beyond OS file
  permissions.
* On this machine `app/pt_config.json`, `app/gui_settings.json` and other legacy runtime files still
  exist (never opened). The next hub start will copy them to the new folders and show the migration
  dialog; nothing is deleted until **Remove old files** is confirmed.
* Still tracked by git although they are runtime output: `<repo>/<SYM>_current_price.txt` (5 files),
  `app/*_training_results.json` and `app/<SYM>/*_training_results.json`, and the per-coin trainer copies
  `app/<SYM>/pt_trainer*.py` (the hub no longer runs or copies them). Untracking/removing them was left
  for you to decide.
* `config/*.yaml` (your commit `25bf2b8`) and `app/config/*.json|yaml` are tracked; their credential
  fields are empty, and the app no longer reads or writes those copies (the YAML manager now uses
  `<config>/yaml/`).
  * *Corrected after review:* `25bf2b8` was dropped, so root `config/*.yaml` are no longer tracked;
    `app/config/*.json|yaml` still are.
* The YAML config tests skip in the suite venv (no PyYAML); they pass with PyYAML installed.

### Final suite (this commit's files, clean scratch worktree)

Phase 4 results + `test_docs_and_visibility` 5 passed + `test_no_legacy_paths` 4 passed (was 2).
Totals: **910 passed, 11 failed, 5 skipped** (baseline: 822 passed, 11 failed, 3 skipped). The 11
failures are exactly the baseline set (`test_integration` x2, `test_suite` x8,
`test_expired_proposal_cannot_execute`). Skips: the two pre-existing ones (`test_paper_trading_integration`,
`test_coinbase_auth`), the POSIX-only permission test, and the two YAML tests (no PyYAML here); the
baseline's skipped Tk test in `test_trading_mode` passed. No existing test was skipped, deleted or had an
assertion changed.

The full suite was run on a checkout cleaned with `git clean -fdx`; afterwards the checkout contained no
new file at all (at baseline the suite left `app/hub_data/`, `app/*.db`, `<repo>/*.db`, `data/`, `logs/`
behind). The developer's real `app/pt_config.json` and `app/gui_settings.json` have the same SHA-256 prefixes
as before the work started.
