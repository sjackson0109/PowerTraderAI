# PATHS-INVENTORY — every runtime file the product reads or writes (FDS-108a Phase 0)

Baseline: commit `58efed2` (all line numbers refer to it). Method: Python source only — `open(`,
`json.load/dump`, `sqlite3.connect`, `create_engine`, `os.path.join`/`Path(` against `__file__` or the
CWD, `os.makedirs`/`mkdir`, `shutil.*`, `os.remove/replace`, `glob`, `os.environ`/`getenv`,
`expanduser`, logging handlers, `torch.save/load`, `to_csv`, plus the literal names `pt_config.json`,
`trading_config.json`, `exchange_config.json`, `hub_data`. No real config file, keyring entry or
`%APPDATA%`/`%LOCALAPPDATA%` content was opened; committed files were inspected through `git show` only
(key names and emptiness, never values).

Abbreviations: **app/** = the program directory (`<repo>/app`). **CWD** = the process working
directory (the hub never `chdir`s; `start_powertrader.bat` runs it from `<repo>`; the hub starts
`pt_thinker.py`/`pt_trader.py` with `cwd=app/` and the trainer with `cwd=<coin folder>`).
**Git**: T = tracked, I = ignored, U = untracked and *not* ignored (could be staged by `git add .`).
**Used**: whether the running hub/trader/thinker/trainer reaches the code (yes / no = demo, CLI or dead
code / lazy = only on some path).

## 1. How the base directories resolve today

| Symbol | Resolves to | Where |
|---|---|---|
| `pt_hub.project_dir` | `app/` | pt_hub.py:1978 |
| `pt_hub` main neural dir | `gui_settings["main_neural_dir"]` (relative → `app/`), else `app/` | pt_hub.py:1980-1985, 539 |
| `pt_hub.hub_dir` | `gui_settings["hub_data_dir"]` (relative → **CWD**), else `app/hub_data` | pt_hub.py:1988-1992, 580 |
| `pt_hub` trader dir | `hub_dir/<paper\|testnet\|"">` (`TradingSettings.data_subdir`) | pt_hub.py:1997; trading_mode.py:191-196 |
| `pt_hub` coin folders | BTC = main dir itself (`app/`), others `main dir/<COIN>`; empty main dir → `os.getcwd()` | pt_hub.py:733-763 |
| `pt_trader.HUB_DATA_DIR` | env `POWERTRADER_HUB_DIR`, else `app/hub_data` (created at import) | pt_trader.py:35-38 |
| `pt_trader._GUI_SETTINGS_PATH` | env `POWERTRADER_GUI_SETTINGS`, else `app/gui_settings.json`; rejected unless inside `app/` or `app/config` | pt_trader.py:57-59, 93-100 |
| `pt_trader` coin base paths | `os.getcwd()` or `main_neural_dir`; BTC = base, others base/`<SYM>` | pt_trader.py:127-156, 197, 246-251 |
| `pt_thinker.BASE_DIR` / `coin_folder()` | `app/` (BTC) / `app/<SYM>`; ignores `main_neural_dir` | pt_thinker.py:394-400 |
| `pt_thinker.HUB_DIR` | env `POWERTRADER_HUB_DIR`, else `app/hub_data` (created at import) | pt_thinker.py:436-440 |
| `pt_thinker._GUI_SETTINGS_PATH` | env `POWERTRADER_GUI_SETTINGS`, else `app/gui_settings.json` | pt_thinker.py:288-290 |
| trainer `data_dir` | `<script dir>/../data`: `<repo>/data` for `app/pt_trainer.py` and the BTC copies; **`app/data`** for the copies run from `app/<SYM>/` | pt_trainer.py:199-200; BTC/pt_trainer.py:79-80; *_standalone.py:69-70 |
| `SettingsManager.settings_path` | `settings_dir/settings_file`, else `app/pt_config.json` | pt_settings_manager.py:118, 397-403 |
| `trading_mode.default_settings_path()` | `app/pt_config.json` | trading_mode.py:94-95 |
| `ExchangeConfigManager.config_dir` | argument, else `app/` | pt_multi_exchange.py:51-58 |
| `ExchangeFactory.load_credentials` | argument, else `app/exchange_config.json` | pt_exchange_abstraction.py:301-310 |
| `SecureCredentialManager.base_dir` / `PermissionValidator.base_dir` | argument, else `app/` | pt_credentials.py:105, 587 |
| `market_data.candles.cache_dir_default()` | env `POWERTRADER_HUB_DIR`, else `app/hub_data`, then `/candles` | market_data/candles.py:59-64 |
| `pt_config.ConfigurationManager` | `Path("config")` → **CWD**; global instance built at import | pt_config.py:257, 266, 553 |
| `pt_logging_system` | `Path(log_directory or "logs")` → **CWD** | pt_logging_system.py:429-430 |

The same file can therefore land in `app/`, `<repo>/` or wherever the hub was started from. Filenames
present in **both** `<repo>/` and `app/` on this machine (`market_data.db`, `portfolio_optimization.db`,
`order_management.db`, `data/automation.db`, `data/holdings.db`, `logs/*.log`, `cache/models`) confirm
that the app has been run from both working directories.

## 2. Config

| Path as written (resolved) | Files and lines | R/W | Holds | Git | Used |
|---|---|---|---|---|---|
| `SETTINGS_FILE = "gui_settings.json"` → `app/gui_settings.json` (+ `.tmp`) | pt_hub.py:615, 627-630, 2510-2513, 2524-2527, 8720; pt_trader.py:57-59, 85-103; pt_thinker.py:288-290, 305-313; pt_paper_mode.py:365-366 (default name) | RW (hub), R (trader, thinker) | coins, DCA/PM values, `main_neural_dir`, `hub_data_dir`, script paths, exchange region, API server host/port, paper balance | I | yes |
| `pt_config.json` → `app/pt_config.json` (+ `.tmp`) | pt_settings_manager.py:118, 397-403, 412-414 (R), 473 (mkdir), 485-488 (W); trading_mode.py:61, 94-95, 122-129, 208-250 (R); strategies/settings.py:21, 70-71; pt_paper_mode.py:81-87, 353-362; pt_hub.py:6459-6460 (mtime), 1942, 2433, 6466 (via trading_mode/strategies); pt_trader.py:336, 358 | RW | `trading.mode`, `active_broker`, `<broker>_testnet`, `strategy.*`, `risk.*`, `paper.*` (no credential fields) | I | yes |
| `pt_config.json.backup.<ts>` (keeps 5) | pt_settings_manager.py:476-481, 812-833 | W, delete | settings backups | I (`app/pt_config.json.*`) | yes |
| settings export/import (caller path) | pt_settings_manager.py:723-742 | W / R | settings dump | n/a | lazy |
| `trading_config.json` → `app/trading_config.json` | pt_multi_exchange.py:51-58, 70-75 (R), 93-106 (W), 160, 181-207, 218-223; exchange_config_gui.py:98, 656, 746, 773, 803, 827, 1156-1161, 1184, 1306; exchange_setup.py:140-154, 207, 234, 303; pt_data_provider.py:43-57; pt_thinker.py:153-159, 202-206, 231-235 (global `multi_exchange_manager`); pt_hub.py:8820-8823, 8984 | RW | region, primary exchange, per-exchange enabled/priority/sandbox **and plaintext `api_key`/`api_secret`/`passphrase`** (Coinbase: key name + EC PEM) | I (since `58efed2`) | yes |
| `trading_config.example.json` → `app/` | pt_multi_exchange.py:21, 58, 70 | R (fallback) | shipped template, all credential fields empty | T | yes |
| `exchange_config.json` → `app/exchange_config.json` | pt_exchange_abstraction.py:301-310, 342-343; trading_mode.py:810 | R | per-exchange constructor kwargs **including `api_key`/`api_secret`** — the **live gate's** credential file | **U** | yes (live mode only) |
| `config/` (CWD) + `{trading,exchange,security,ui,system}.yaml` | pt_config.py:266, 298 (mkdir), 306-310, 331-364 (R), 380-390 (writes defaults), 505-521 (W), 553 (global instance at import) | mkdir, RW | YAML config; `exchange.yaml` has `api_key`/`api_secret` (empty defaults), `security.yaml` has `webhook_secret` | T (`config/*.yaml`, `app/config/*.yaml`) | no (imported only by pt_integration, pt_system, pt_testing) |
| `config/environment.<POWERTRADER_ENV>.yaml` (CWD) | pt_config.py:286, 409-412 | R | overrides | n/a | no |
| `config/monitoring.json` (CWD) | pt_live_monitor.py:103, 136-138, 159-164, 176-178 | mkdir, RW | monitoring config **plus SMTP username/password** | T (`app/config/monitoring.json`, empty values) | no (only pt_gui_integration) |
| `config/production.ini`, `config/alert_thresholds.json`, `config/secrets.json` (defined, never used) (CWD) | production_deployment.py:20-37, 87-88, 190-204 | mkdir, RW | production config | T (`app/config/*`, `app/production.ini`, `app/alert_thresholds.json`) | lazy (only via start_powertrader.py) |
| `config/integration_test.json` (CWD) | pt_integration.py:73, 83-85 | RW | test config | T | no |
| `app/config/update_settings.json`, `app/version.json` | pt_updater.py:29-45, 64-79 | RW | updater state | U | no |
| `data_provider_config.json` → `app/` | pt_data_provider.py:84-91; exchange_config_gui.py:111-119 | R | provider settings, exchange catalogue | T | yes |
| `.github/scripts/create_desktop_installer.py` templates (`settings.json`, `logging_config.json`) | create_desktop_installer.py:52-105, 149-171 | W (build) | installer build tree | n/a | no (build-time) |

## 3. Secrets (files that hold credentials today)

| Path as written (resolved) | Files and lines | R/W | Holds | Git | Used |
|---|---|---|---|---|---|
| `app/trading_config.json` | see §2 | RW | plaintext exchange keys written by the setup window and `exchange_setup.py` | I | yes |
| `app/exchange_config.json` | see §2 | R | plaintext exchange keys read by the live gate | **U** | yes (live) |
| `r_key.txt`, `r_secret.txt` → `app/` | pt_credentials.py:530-549 (R then delete), 564-568, 880-887 (plaintext fallback R); pt_hub.py:7693-7696, 7722-7734 (R when no vault), 7786-7789 (Clear: delete), 8413-8431 (zero-fill + delete after vault save); pt_thinker.py:69, 76 (message text) | R, delete | legacy plaintext Robinhood API key + base64 Ed25519 seed | I | yes |
| `r_key.txt.bak_<ts>`, `r_secret.txt.bak_<ts>` → `app/` | pt_hub.py:7929-7935 (dead helper), **8206-8215 (Test Credentials button)**, **8382-8387 (save)** | W | **plaintext copies of the Robinhood secrets, never deleted** | **U** | yes |
| `r_key.enc`, `r_secret.enc`, `.pt_salt`, `.pt_cred_meta` (+ `*.bak`, mkstemp temps) → `app/` | pt_credentials.py:105-121, 156-234, 239-322 (W), 344-413 (R), 438-505 (rotate), 554-560; pt_hub.py:7704-7721 (R), 8394-8403 (W) | RW | Fernet-encrypted Robinhood credentials (key derived from host + user name) and rotation metadata | **U** | yes |
| `config/exchange.yaml` (`api_key`, `api_secret`), `config/security.yaml` (`webhook_secret`) (CWD) | pt_config.py:72-73, 101-102, 380-390, 505-521 | W | credential fields (written empty by default) | T (values empty) | no |
| `config/monitoring.json` `smtp_settings.password` (CWD) | pt_live_monitor.py:159-164, 506-548 | RW | SMTP password | T (empty) | no |
| `config/secrets.json` (CWD) | production_deployment.py:25 | — | path defined, never read or written | n/a | no |

## 4. Data

| Path as written (resolved) | Files and lines | R/W | Holds | Git | Used |
|---|---|---|---|---|---|
| `hub_dir` / `HUB_DATA_DIR` / `HUB_DIR` → `app/hub_data/` | pt_hub.py:580, 1988-1992, 659-660; pt_trader.py:35-38; pt_thinker.py:436-440 | mkdir | runner state shared by hub, trader, thinker | I | yes |
| `<hub>/<paper\|testnet\|"">/` | pt_trader.py:337-338 | mkdir | per-mode books | I | yes |
| `<hub>/<sub>/trader_status.json` (+ `.tmp`) | pt_trader.py:339, 446-451, 822-823, 2423; pt_hub.py:1998, 6479-6506; pt_api_server.py:116-119 (at **hub root**, not `<sub>`) | W (trader), R (hub, API) | account, positions, price integrity | I | yes |
| `<hub>/<sub>/trade_history.jsonl` | pt_trader.py:340, 455-458, 497-505, 820, 955-966, 1096-1107; pt_hub.py:641, 1396, 1643, 1776, 6622, 6811-6827, 3320, 3340, 7266, 7286; pt_api_server.py:141-154 | RW | fills | I | yes |
| `<hub>/<sub>/pnl_ledger.json` (+ `.tmp`) | pt_trader.py:341, 461-489; pt_hub.py:2000, 6793-6801; pt_api_server.py:210-219; pt_hub_chart_components.py:502-504 | RW | realised PnL, open positions | I | yes |
| `<hub>/<sub>/account_value_history.jsonl` | pt_trader.py:342-344, 2419-2422; pt_hub.py:1637-1663, 3319, 7265; pt_api_server.py:175-180; pt_hub_chart_components.py:496-514 | RW | equity curve | I | yes |
| `<hub>/<sub>/strategy_state.json` (+ `.tmp`) | pt_trader.py:346; signal_engine.py:154-164 (R), 182-197 (W) | RW | strategy positions, overlay state | I | yes |
| `<hub>/<sub>/paper_account.json` (+ `.tmp`) | pt_trader.py:349-352; trading_mode.py:430-447, 629-656 | RW | paper book | I | yes |
| `<hub>/runner_ready.json` (+ `.tmp`) | pt_thinker.py:442-465, 575-577, 666-669; pt_hub.py:2006, 5096-5099, 5151-5153, 6144-6147 | RW | thinker readiness gate | I | yes |
| coin folders `app/` (BTC) and `app/<SYM>/` | pt_hub.py:2585-2590, 5601-5602, 8787-8789 (mkdir); pt_thinker.py:469-470 (mkdir at import), 555-634 and 1492 (`chdir`) | mkdir, chdir | per-coin neural working dir **inside the program dir** | T (folders hold tracked trainer copies) | yes |
| trainer copies `<coin dir>/pt_trainer.py` | pt_hub.py:2564-2598, 5592-5609, 8763-8795 (`shutil.copy2`) | W | program code copied into the data folders | T (`app/<SYM>/pt_trainer*.py`) | yes |
| `low_bound_prices.html`, `high_bound_prices.html`, `long_dca_signal.txt`, `short_dca_signal.txt`, `memory.json`, `futures_*_profit_margin*.txt`, `signals_dca_spread.txt`, `signals_dca_single.txt` (coin folder / thinker CWD) | pt_thinker.py:649-656, 1316-1325, 1377-1394; pt_hub.py:827-831, 1159-1210, 1523-1526, 7142-7157; pt_trader.py:872-877, 894-899, 917-922 | W (thinker), R (hub, trader); the hub **deletes the thinker's `.tmp` files** (pt_hub.py:1172-1176) | neural signals | I (`app/*.txt`; html/json by pattern) | yes |
| `neural_perfect_threshold_<tf>.txt`, `memories_<tf>.txt`, `memory_weights{,_high,_low}_<tf>.txt` (trainer CWD = coin folder) | pt_trainer.py:40-43, 83-102; pt_thinker.py:748-792, 931-934; pt_hub.py:5633-5647 (glob + delete before retrain) | RW, delete | model weights / thresholds | I | yes |
| `trainer_status.json`, `trainer_last_training_time.txt`, `trainer_last_start_time.txt`, `killer.txt` (coin folder) | pt_hub.py:1968-1971, 5223-5278, 5633-5647, 6100-6104; pt_trainer.py:207-209; pt_thinker.py:420-425 | RW, delete | training state | U / I | yes |
| `<coin>_training_results.json` in trainer `data_dir` (`<repo>/data` or `app/data`) | pt_trainer.py:199-204; BTC/pt_trainer.py:79-84; *_standalone.py:69-74 | mkdir, W | training summary | **T** (`app/*_training_results.json`, `app/<SYM>/*_training_results.json`) | yes |
| `app/order_management.db` (+ `-wal`/`-shm`) | order_management_db.py:49-52, 63-93, 562-567; order_management_integration.py:85, 540-545; pt_hub.py:3851 | RW | orders, conditions, notifications | I | yes |
| `sqlite:///order_management.db` (**CWD**) — a second, separate DB | llm_research_engine.py:659, 676-680, 1022-1030; llm_research_gui.py:50; pt_hub.py:4439 | RW | same schema | I | yes |
| `data/automation.db` (**CWD**) | advanced_order_automation.py:181-183, 209, 805-907; pt_hub.py:4562 | mkdir, RW | advanced/OCO/bracket orders | I | yes |
| `data/holdings.db` (**CWD**) | long_term_holdings.py:73-74, 79-211, 237-240, 411; pt_hub.py:4480 | mkdir, RW | holdings | I | yes |
| `portfolio_optimization.db` (**CWD**) | portfolio_optimizer.py:40-41, 74, 478-554; pt_hub.py:4647 | RW | optimisation results | I | yes |
| `app/institutional_trading.db` | institutional_trading.py:399-402, 682-686; pt_hub.py:4774 | RW | institutional orders | I | yes |
| `data/portfolio_analytics.db` (**CWD**) | portfolio_analytics.py:91-98, 169-480 | mkdir, RW | snapshots | I | lazy (tab disabled) |
| `risk_management.db`, `app/compliance_audit.db` (**CWD**) | advanced_risk_management.py:476-1157; compliance_audit_system.py:300-812 | RW | risk alerts, audit events | I | no |
| `"order_management.db"` passed as a non-URL to `OrderManagementDB` | advanced_stop_loss.py:341; advanced_take_profit.py:545; conditional_order_logic.py:858; dca_automation.py:527; order_analytics_dashboard.py:53; order_execution_engine.py:184; order_risk_management.py:511, 1193 | RW (intended) | orders | I | no |
| `app/migrations/`, `<db>.backup_<ts>` | migrations.py:25-66, 400-498 | mkdir, RW | schema migrations, DB backups | U | no (never called) |
| `<db dir>/backups/`, `backup_manifest.json`, `backup_<ts>.db` | pt_backup.py:86-363 | mkdir, RW, delete | DB backups | n/a | no |
| `data/best_model.pth`, `data/<sym>_neural_model.pth` (**CWD**); `save_model(path)` | pt_neural_network.py:477-507, 564-584; pt_neural_processor.py:435-441 | RW | torch checkpoints | I | no (demos) |
| `model_evaluations/` (**CWD**) | pt_model_evaluation.py:39-41, 210-309 | mkdir, RW | evaluation JSON/plots | U | no |
| `test_results/` (**CWD**) | pt_integration.py:109-111, 736-748 | mkdir, W | integration results | U | no |
| `config`, `data`, `data/logs`, `data/backups`, `data/cache` (**CWD**, created at import by `system = PowerTraderSystem()`) | pt_system.py:49-93, 149-185, 518 | mkdir, W | — | I/U | no |
| `logs`, `config`, `data`, `backups` (**CWD**) | production_deployment.py:402-406 | mkdir | — | I/U | lazy (start_powertrader.py) |
| `app/backup/`, `app/temp/*.zip`, `update_extract` | pt_updater.py:155-272 | mkdir, RW, rmtree | updater | U | no |
| backtest `--out X.json` + `X_trades.csv` | backtest/cli.py:172, 185-191 | mkdir, W | backtest results (user-chosen path) | n/a | CLI |
| `docs/dev/backtest-batch-1/*`, `docs/dev/BACKTEST-REPORT-batch-1.md` | docs/dev/run_backtest_batch1.py:29, 56-106, 266-268 | RW | dev report | T | dev script |
| user exports/imports via file dialogs | backtesting_gui.py:634-652; portfolio_optimizer_gui.py:449-471; performance_attribution_gui.py:619-672, 1047-1055; llm_research_gui.py:984-997; long_term_holdings_gui.py:556-565 → long_term_holdings.py:332-362; pt_hub.py:5044-5063 | R/W | user files | n/a | yes (user-chosen, stays as is) |

## 5. Logs

| Path as written (resolved) | Files and lines | R/W | Holds | Git | Used |
|---|---|---|---|---|---|
| `Path(log_directory or "logs")` (**CWD**): `powertrader.log`, `errors.log`, `trades.log`, `security.log`, `audit.log` (rotating) | pt_logging_system.py:344-379, 429-514, 651-664 | mkdir, RW | application logs | I | lazy (pt_settings_manager → `log_warning`/`log_error`) |
| `credential_audit.jsonl` (+ `.1`) → `app/` | pt_credentials.py:582-588, 679-747 | RW | permission audit log | I | lazy |
| `emergency_snapshot_<ts>.json` (**CWD**) | pt_risk.py:354, 392-393 (via 205, 254, 324) | W | emergency state dump | **U** | yes (trader CWD = `app/`; hub CWD = launch dir) |
| `~/.powertraderai/logs/security_audit.jsonl` (+ `.1`-`.10`) | pt_security_logger.py:177-241, 503-561 | mkdir, RW | security audit | n/a (outside repo) | no |
| `logs/powertrader_YYYYMMDD.log`, `logs/audit_YYYYMMDD.log` (**CWD**) | production_deployment.py:110-157 | mkdir, W | logs; clears root handlers | I | lazy (start_powertrader.py) |
| `pt_logging.configure(log_file=...)` + `performance.log`, `audit.log`, `trades.log` | pt_logging.py:180-214, 341-377 | mkdir, W | logs | n/a | no (only pt_system) |
| `dependency_report.txt`, `PHASE_COMPLETION_REPORT.txt` (**CWD**) | dependency_checker.py:471-474; phase_completion.py:185 | W | reports | I/U | no |
| hub child process output | pt_hub.py:3807-3828 (pipes to in-memory queues) | — | not written to disk | — | yes |

## 6. Cache

| Path as written (resolved) | Files and lines | R/W | Holds | Git | Used |
|---|---|---|---|---|---|
| `<hub>/candles/<SYM>_<TF>.csv` (+ `.tmp`) | market_data/candles.py:59-68, 211-230, 260-321; signal_engine.py:46-59; backtest/cli.py:99-105, 170; run_backtest_batch1.py:44-53 | RW | downloaded Binance klines | I | yes |
| `<SYM>_current_price.txt` (trader **CWD** = `app/`; also present at `<repo>` root) | pt_trader.py:1972-1974, 2265-2267 | W | last buy price | **T at `<repo>/`**, I in `app/` | yes |
| `cache/`, `cache/models/`, `<md5>.cache` pickles (**CWD**) | pt_caching_system.py:384-692; created at import by pt_neural_processor.py:28-32 | mkdir, RW, delete | pickled cache | **U** | no (demos) |

## 7. Program assets read at runtime (stay in `app/`, read-only)

`strategies/catalogue.json` (strategies/catalogue.py:34, 182-196), `data_provider_config.json`,
`trading_config.example.json`, the runner scripts executed by the hub (`pt_thinker.py`, `pt_trader.py`,
`pt_trainer.py` — pt_hub.py:2035-2050, 3812, 5361-5363, 5613-5616), `requirements.txt`
(install_dependencies.py:26, 45-52; pt_security.py:46-59 **overwrites** it in `fix` mode — not used),
`app/tests/fixtures/*.csv` (tests only), and `sys.path` set-up from `__file__` in many modules (no I/O).

## 8. Credentials: every field, every environment variable, every reader

| Name | Stored in | Read by | Written by |
|---|---|---|---|
| `ExchangeConfig.api_key` / `api_secret` / `passphrase` | `app/trading_config.json` (plaintext) | `MultiExchangeManager._get_exchange_credentials` (pt_multi_exchange.py:399-428), setup window (exchange_config_gui.py:827-856, 1181-1198), `test_all_exchanges` (1306-1311) | `ExchangeConfigManager.update_exchange_credentials` (181-195) ← GUI save (exchange_config_gui.py:1156), Remove (803), `exchange_setup.py:122-143` |
| exchange constructor kwargs | `app/exchange_config.json` (plaintext) | `ExchangeFactory._get_credentials` (pt_exchange_abstraction.py:330-345) ← `get_exchange` ← `trading_mode._build_live_exchange` (trading_mode.py:800-819) and `ExchangeManager.add_exchange` | nothing in the product (hand-edited) |
| `POWERTRADER_<EXCHANGE>_API_KEY`, `_API_SECRET` | environment | `ExchangeFactory._get_credentials` (**env first**, then `exchange_config.json`; no passphrase); `MultiExchangeManager._get_exchange_credentials` (**file first**, then env) | — |
| `POWERTRADER_<EXCHANGE>_PASSPHRASE` | environment | `MultiExchangeManager` only (pt_multi_exchange.py:422) | — |
| Coinbase key name / EC private key PEM | `api_key` / `api_secret` above | `CoinbaseExchange(api_key, api_secret)` (pt_exchanges.py:972, 983-986) | setup window validates with `coinbase_auth` (exchange_config_gui.py:1140-1148) |
| Robinhood API key + base64 Ed25519 seed | `app/r_key.enc` + `app/r_secret.enc` (Fernet, key from host+user), legacy `app/r_key.txt`/`r_secret.txt`, `*.bak_<ts>` | `pt_credentials.get_credentials()` (vault → `POWERTRADER_ROBINHOOD_API_KEY`/`_PRIVATE_KEY` → plaintext) ← pt_thinker.py:26, 183; hub Robinhood window (pt_hub.py:7704-7734) | hub Robinhood wizard (pt_hub.py:8392-8403), `migrate_from_plaintext` (pt_credentials.py:528-552) |
| `USER`/`USERNAME`/`COMPUTERNAME` | environment | vault key derivation (pt_credentials.py:141, 150-151) | — |
| LLM `api_key` / `openai_api_key` | memory only | llm_research_engine.py:128-137, 664-668; llm_research_gui.py:79-90, 488-491, 1041-1051 | never saved |
| ccxt `apiKey`/`secret`/`passphrase` | empty literals in code | real_time_market_data.py:388-421 | — |
| SMTP `username`/`password` | `config/monitoring.json` | pt_live_monitor.py:506-548 | default written 176-178 (not used by the app) |
| `webhook_secret`, YAML `api_key`/`api_secret` | `config/*.yaml` | pt_config.py | pt_config.py:380-390, 505-521 (not used by the app) |

Exchange constructors (pt_exchanges.py): every connector takes `api_key, api_secret` (Coinbase: key name
+ PEM; Binance and the base class default both to `""`); KuCoin, Bitget and Bitso also read
`kwargs["passphrase"]`; Aave, Yearn Finance and Lido Finance take `wallet_address, private_key`.

Other environment variables: `POWERTRADER_HUB_DIR` (set by the hub for the trader, thinker and trainer —
pt_hub.py:3817, 5666; *not* for the per-coin thinker at 5361-5388), `POWERTRADER_GUI_SETTINGS`,
`POWERTRADER_ENV`, `POWERTRADER_USER_REGION`, `POWERTRADER_LOG_LEVEL` (CI conftest).

## 9. Findings that FDS-108a must fix (not fixed in this phase)

1. **Two credential stores that disagree.** The setup window writes `trading_config.json`; the live gate
   reads env vars or `exchange_config.json`. A key saved in the GUI is never used for live trading.
2. **Credentials in two places drop the exchange.** `MultiExchangeManager.initialize` passes its
   credentials to `ExchangeManager.add_exchange(**creds)`, and `ExchangeFactory.get_exchange` adds its own
   (`exchange_class(**creds, **kwargs)`, pt_exchange_abstraction.py:319-327). With both an env var /
   `exchange_config.json` entry and a GUI-saved key, Python raises `TypeError: got multiple values for
   keyword argument 'api_key'`, `add_exchange` catches it and prints "Failed to add" (396-398).
3. **Plaintext secret copies.** `r_key.txt.bak_<ts>`/`r_secret.txt.bak_<ts>` are created by the
   Robinhood Test and Save buttons and never removed; they, `exchange_config.json`, `r_key.enc`,
   `.pt_salt` and `.pt_cred_meta` are not git-ignored.
4. **Writes into the program directory** by the running app: `gui_settings.json`, `pt_config.json` and
   its backups, `trading_config.json`, `hub_data/`, the coin folders (signals, weights, trainer status,
   trainer code copies), the Robinhood vault, `order_management.db`, `institutional_trading.db`,
   `credential_audit.jsonl`, `emergency_snapshot_*.json`, `<SYM>_current_price.txt`, and every
   CWD-relative file when the hub is launched from `app/`.
5. **CWD-relative writes** (`market_data.db`, `portfolio_optimization.db`, `data/*.db`, a second
   `order_management.db`, `logs/`, `config/`, `cache/`) land in whatever folder the hub was started from.
6. Side observations, out of scope: the thinker writes `signals_dca_*.txt` while the trader reads
   `*_dca_signal.txt`; `pt_api_server` reads the trader files at the hub root while the trader writes them
   under `hub/<mode>/`; trainer results go to `<repo>/data` or `app/data` depending on which copy runs.

## 10. The eight baseline `test_suite` failures

Not caused by writing into the program directory. Seven (`test_database_initialization`,
`test_holdings_database`, `test_holdings_manager`, `test_performance_metrics`,
`test_portfolio_analytics_initialization`, `test_portfolio_snapshot`, `test_database_integration`) fail
in `tearDown` with `PermissionError: [WinError 32] ... %TEMP%\tmpXXXX\test.db` — the tests already use a
temp directory, and Windows refuses to delete a SQLite file that the code under test left open. The
eighth, `test_exchange_factory`, asserts that `ExchangeFactory().get_available_exchanges()` is non-empty
without importing `pt_exchanges` (nothing registered). Neither is a path problem; both are left as they
are.

## 11. `.gitignore` gaps

Not ignored today: `app/exchange_config.json`, `app/r_key.txt.bak_*`/`app/r_secret.txt.bak_*`,
`app/r_key.enc`, `app/r_secret.enc`, `app/.pt_salt`, `app/.pt_cred_meta` (+ `.bak`),
`app/trainer_status.json` (and per-coin copies), `emergency_snapshot_*.json`, `cache/`,
`model_evaluations/`, `test_results/`, `app/migrations/`, `<repo>/<SYM>_current_price.txt` (tracked).
