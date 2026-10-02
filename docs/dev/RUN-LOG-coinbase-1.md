# Run log — Coinbase connector fix

Branch: `fix/coinbase-connector` (from `feat/strategy-batch-1` @ `47b70ee`; that branch is untouched).
Scope: make the exchange-setup **Test** button work for Coinbase, move the connector to the current
Coinbase auth scheme, prove the paper/live gate holds for Coinbase. Paper mode only; no live calls.

## Environment and how the suite is measured

* Same per-file runner as `RUN-LOG-strategy-batch-1.md`: every `app/test_*.py` and `app/tests/test_*.py`,
  one file at a time, `test_phase1_phase2_integration.py` excluded (it kills its own process group on Windows).
* Interpreter: Python 3.13 (has matplotlib/scipy/numpy/cryptography) inside a throw-away venv created with
  `--system-site-packages` plus `pytest` only (venv lives outside the repo; nothing was installed into the
  global Python). The Python 3.14 install on this machine has pytest but no matplotlib/scipy, so it cannot
  reproduce the documented baseline and was not used.
* `app/trading_config.json` is a tracked file with an **uncommitted local modification** that pre-dates this
  work. It was not opened, printed or copied. Its hash prefix was recorded before and after the baseline run and
  is unchanged. Every commit on this branch uses explicit `git add <path>`; that file is never staged.
* The baseline run created an untracked `config/` directory at the repo root (five `*.yaml` files written by a
  test's config bootstrap). It is a test artefact, not part of this work, and is not committed.

## Baseline (before any change on this branch)

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
| test_trading_mode | 50 passed |
| tests/test_backtest_cli | 13 passed |
| tests/test_backtest_engine | 30 passed |
| tests/test_candles | 22 passed |
| tests/test_catalogue | 19 passed |
| tests/test_demo_paper_trading | 11 passed |
| tests/test_indicators | 17 passed |
| tests/test_overlays | 47 passed |
| tests/test_price_source_integrity | 48 passed |
| tests/test_runner | 13 passed |
| tests/test_signal_engine | 37 passed |
| tests/test_supertrend | 30 passed |
| tests/test_trend_crossover | 28 passed |

The 11 failures are exactly the known set: `test_expired_proposal_cannot_execute` (1), the two
`test_integration` hub tests (2), and eight `test_suite` tests.

## Task 1 — Diagnosis

**Symptom:** `'MultiExchangeManager' object has no attribute 'test_exchange_connection'`.

**Callers of `test_exchange_connection`** (`grep -rn` over `app/`, `*.py`):

| Location | What it is |
|---|---|
| `app/exchange_config_gui.py:525` | "📋 Test Connection" button `command=self.test_exchange_connection` (the GUI's own method) |
| `app/exchange_config_gui.py:1074` | `ExchangeConfigGUI.test_exchange_connection` — the GUI method; **calls the manager at :1092** |
| `app/exchange_config_gui.py:1092` | `self.multi_exchange.test_exchange_connection(exchange_name)` ← the failing call |
| `app/exchange_config_gui.py:1133` | `ExchangeConfigGUI.test_all_exchanges` calls the same missing manager method |

No other file in `app/` references it.

**Real methods of `MultiExchangeManager`** (`app/pt_multi_exchange.py:188`): `__init__`, `initialize`,
`get_current_price`, `compare_prices`, `get_best_price`, `place_order`, `get_available_exchanges`,
`_get_exchange_credentials`. There is no connection test of any kind. (`ExchangeConfigManager` is the
config store; it has none either.)

**Verdict: missing implementation.** Not a rename (nothing similarly named exists on any exchange class
or manager) and the GUI is calling the right object — the manager simply never had the method.

**Related defects found while tracing (all on the same path):**

1. **The Test button ignores what the user typed.** The GUI method never reads the key/secret fields. Even if the
   manager method existed it would have no credentials unless the user had already pressed Save.
2. **`test_all_exchanges` is broken a second way:** it does `config.get("exchanges", {})` on the
   `TradingConfig` dataclass returned by `load_config()` (no `.get`), so it raises before reaching the call.
3. **`CoinbaseExchange` (`app/pt_exchanges.py:953`) never authenticates.** It keeps `api_key`/`api_secret`
   on the object but sends nothing signed; `get_current_price`/`get_market_data` call the *unauthenticated*
   `https://api.exchange.coinbase.com/products/{id}/ticker`; `place_order`, `get_balance`, `get_order_status`,
   `cancel_order` all `raise NotImplementedError`. The class docstring says "Advanced Trade API" but the
   base URL is the Coinbase Exchange (ex-Pro) host. So even a "successful" test via that class would have
   proved nothing about the key. (Task 3.)
4. **The GUI's setup text and fields describe a scheme that no longer exists** ("Copy API Key and Secret", single-line
   secret entry). (Task 3.)
5. **Credentials are stored in plaintext JSON.** `ExchangeConfigManager.save_config` writes `api_key`/`api_secret`
   into `app/trading_config.json`, which is a *tracked* file. Anything saved through the GUI lands in a file git
   will offer to commit. Not changed here (out of scope) — see the final report.
6. Credential sources are inconsistent: GUI → `trading_config.json`; `ExchangeFactory.get_exchange` (used by the
   live gate in `trading_mode._build_live_exchange`) → env vars `POWERTRADER_<NAME>_API_KEY/SECRET` or
   `exchange_config.json`. A key saved through the GUI is therefore not what the live gate would load.
