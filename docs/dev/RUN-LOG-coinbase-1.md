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

## Task 2 — Test button (done)

* `MultiExchangeManager.test_exchange_connection(exchange, api_key=None, api_secret=None, passphrase=None)`
  now exists and returns a `ConnectionTestResult(exchange, status, message, details)` (`pt_exchange_abstraction.py`).
  It never raises for a bad connection and never saves what it is given. Typed credentials win; with both
  blank it uses saved credentials (config file, then `POWERTRADER_<EXCHANGE>_*`).
* New `AbstractExchange.check_connection()` — default returns `UNSUPPORTED` ("not tested"), so exchanges
  without a check can never show a false green. `CoinbaseExchange.check_connection()` is the only real
  implementation: **one** `GET https://api.coinbase.com/api/v3/brokerage/key_permissions` (needs only the View
  scope; returns `can_view/can_trade/can_transfer`), `allow_redirects=False`, 10 s timeout, no body/query.
* Outcomes (distinct status + message): `OK` (reports view/trade/transfer, notes a view-only key, warns if the
  key can transfer funds), `INVALID_CREDENTIALS` (malformed key, detected locally, **nothing sent**),
  `AUTH_FAILED` (401), `PERMISSION_DENIED` (403, or 200 with `can_view: false`), `NETWORK_ERROR`
  (DNS/TLS/timeout/refused), `ENDPOINT_ERROR` (404/429/5xx/3xx/non-JSON 200 — explicitly *not* an auth verdict),
  `UNSUPPORTED`.
* Because a signed call is needed to test anything, the ES256 JWT signer (`app/coinbase_auth.py`) lands in this
  commit; Task 3 audits it against the docs and hardens the input side and the GUI text.
* GUI (`exchange_config_gui.py`): the button tests what is typed in the form (blank form → saved credentials),
  runs on a worker thread so the window does not freeze, and prints one block per outcome.
  `test_all_exchanges` was also repaired (it called `.get` on a dataclass) and now uses the same method.
* Tests: `app/tests/test_coinbase_connection.py` — 27 tests. HTTP is mocked at `requests.sessions.Session.request`
  (the funnel under `requests.get/post/...`), with `socket.create_connection` and `socket.socket.connect`
  patched to fail, so a stray call of any kind is both visible and unable to leave the machine. Keys are
  generated per test. Asserts: exactly one GET to `key_permissions`, no non-GET and no order/preview URL,
  every outcome, bad credentials send nothing, messages contain neither the token nor key material,
  the manager neither saves typed credentials nor claims success for unsupported exchanges.
* Suite vs baseline: no regressions. `test_integration` showed 1 failed + 1 skipped instead of 2 failed
  (display-dependent, same flip noted in the batch-1 log); all other files identical; new file 27 passed.

## Task 3 — Authentication audit and fix (done)

**Sources fetched this session (not from memory):**
[CDP API key authentication](https://docs.cdp.coinbase.com/coinbase-app/authentication-authorization/api-key-authentication),
[Advanced Trade REST endpoints](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/rest-api),
[Get API key permissions](https://docs.cdp.coinbase.com/api-reference/advanced-trade-api/rest-api/data-api/get-api-key-permissions),
[Advanced Trade FAQ](https://docs.cdp.coinbase.com/coinbase-app/advanced-trade-apis/faq).

**Current scheme (per those docs):** key = *key name* `organizations/{org_id}/apiKeys/{key_id}` + EC private key
(PEM). Per request, an **ES256** JWT: header `{alg: ES256, typ: JWT, kid: <key name>, nonce}`; claims
`{sub: <key name>, iss: "cdp", nbf: now, exp: now+120, uri: "<METHOD> <host><path>"}`; sent as
`Authorization: Bearer <jwt>` to `https://api.coinbase.com/api/v3/brokerage/...`. Keys must be created with
signature algorithm **ECDSA** — Ed25519 is not supported by the Coinbase App / Advanced Trade SDKs. Coinbase Pro
"has been disabled for use and all customers have been migrated as of December 1, 2023"; Pro API keys cannot be
used with Advanced Trade.

**What the connector did before:** nothing authenticated (see Task 1 finding 3). It used the unauthenticated Coinbase
Exchange host for tickers and never signed or sent the key; the setup text told the user to "Copy API Key and Secret"
into a single-line secret box; `docs/exchanges/coinbase-setup.md` documented the retired key + secret + passphrase
scheme (and a `credentials/coinbase_config.json` that nothing reads, and a `test_exchanges.py --exchange=coinbase`
flag that does not exist). So: not "the wrong auth", but no auth, plus instructions for a scheme that no longer works.

**Changes:**
* `coinbase_auth.py` (introduced in the Task 2 commit, hardened here): strict key-name check (a short legacy key or a
  Pro key gets a message saying that scheme is retired); `normalise_private_key` accepts a real multi-line paste, literal
  `\n` escapes (the downloaded JSON form), CRLF, quotes, and a body flattened onto one line — BEGIN/END lines required;
  `load_private_key` accepts SEC1 and PKCS#8 EC keys on P-256 only and gives specific errors for Ed25519, other
  curves, encrypted keys and garbage, none of which echo the input. The signer uses `cryptography` (already a
  requirement) rather than adding PyJWT. The `uri` claim refuses a query string instead of guessing (see "not verified").
* GUI: for Coinbase the labels become **Key name** / **Private key (PEM)** and the secret is a multi-line box;
  every other exchange is unchanged. Save validates a Coinbase key (name format, key type/curve) and stores the cleaned
  PEM, refusing junk. A saved private key is **never echoed back** into the box (a hint says one is saved; blank box +
  key name means "use the saved one"); the box is cleared after a successful Save. Setup text rewritten (CDP portal →
  Secret API Keys, ECDSA, View/Trade/no Transfer, IP allowlist, paste both values, Test then Save).
* Labels naming the retired product: `data_provider_config.json` display name "Coinbase Pro" → "Coinbase" (this is
  the name in the exchange list); the feed-status label in `real_time_market_data_gui.py` → "Coinbase".
  Docs: `coinbase-setup.md` Steps 2–4 and troubleshooting rewritten, `QUICK_REFERENCE.md` env vars corrected to the real
  `POWERTRADER_COINBASE_API_KEY/_API_SECRET` names, `exchanges/README.md` and `RISK_MANAGEMENT_FRAMEWORK.md` labels.
* Not renamed on purpose: the internal data-source identifier `coinbase_pro` / `DataSource.COINBASE_PRO` in
  `real_time_market_data*.py` (shown as a value in two market-data dropdowns). It is a key for a *public*
  `wss://ws-feed.exchange.coinbase.com` market-data feed that carries no credentials, and renaming it would change a
  persisted/selected identifier. Flagged for a follow-up.
* GUI worker threads now only touch a `queue.Queue`; Tk is only called from the UI thread (my first cut called
  `window.after` from the worker, which failed under test and is unsafe in general).
* Tests: `test_coinbase_auth.py` (21) — header/claims match the documented fields exactly, `exp = nbf + 120`, uri claim
  format, raw 64-byte `r||s` signature verified with `cryptography`, tamper/wrong-key rejected, fresh nonce per
  request, PyJWT cross-check (runs only where PyJWT is installed; it was in the scratch venv), every paste format, and
  each rejection reason. `test_coinbase_gui.py` (12) — labels, multi-line box, instructions, no "Coinbase Pro" in the
  list, Save rejects bad input and stores nothing, normalised storage, saved key never echoed, Test button end to end
  for 200/401/403/500/bad-credentials with mocked HTTP, `test_all_exchanges`. It uses one Tk root per class: the first
  version created 13 roots and hit an intermittent `init.tcl` load failure in `tk.Tk()` on this machine.
* Suite vs baseline: same 11 known failures, nothing new; new files 21 + 12 passed. `test_integration` 2 failed /
  8 passed, identical to baseline.

## Task 4 — Paper gate with Coinbase (done)

`app/tests/test_coinbase_paper_gate.py` (15 tests). Premise check: the tests load synthetic Coinbase credentials
via `POWERTRADER_COINBASE_*` (the path `ExchangeFactory`, hence the live gate, reads) and a first test proves the
factory *would* build a `CoinbaseExchange` from them. Every test then runs inside `recorded_http()`, which replaces
`requests.sessions.Session.request` with a recorder (so `requests.get/post/delete` and any Session are all seen) and
makes raw sockets fail; a final test proves that recorder flags an order POST, an order preview GET and an order
DELETE, so the zero-HTTP assertions cannot pass vacuously.

Paper mode with `active_broker = coinbase` and credentials loaded:
* `resolve_order_target` returns the `PaperExchange` (broker `None`), never a `CoinbaseExchange`;
  `ExchangeFactory.get_exchange` is not called.
* Through the real trader path (`place_buy_order` / `place_sell_order`, and a full `manage_trades()` pass): zero HTTP
  requests of any kind, `CoinbaseExchange.place_order` never invoked, fills land in the paper account.
* Limit orders, order status, cancel, balance and market data on the paper target: zero HTTP.
* Mode values that are not exactly `live` (None, "", "liv", "true", 1, True, [], {}, ...) stay paper.
* Credentials loaded the other way (saved via the config store, connected by `MultiExchangeManager.initialize`): still zero HTTP.
* The Test button is permitted in paper mode and is exactly one read-only GET; no paper order is created.

Live mode:
* Live with no broker is refused (`LiveTradingRefused`) for both `resolve_order_target` and trader start-up, with
  credentials loaded: zero HTTP, factory untouched. Flipping to live-without-broker mid-run refuses orders.
* `can_apply` / `apply_trading_mode`: live + coinbase needs both the broker and the explicit confirmation; each missing
  piece is refused and the effective mode stays paper; with both, the mode becomes `live:coinbase`.
* Observations (tested, not changed): (a) `coinbase` is not in `TESTNET_BROKERS`, so there is **no Coinbase testnet**:
  live + coinbase is real money regardless of the `coinbase_testnet: true` flag in `pt_config.json`, which the gate ignores.
  (b) A confirmed live + coinbase target is built, but `CoinbaseExchange.place_order`/`cancel_order` raise
  `NotImplementedError` before any request is formed; through the trader the order returns `None` and no trade is recorded.
  So today Coinbase cannot trade live, whatever the settings.

Suite vs baseline: same 11 known failures, no new ones; new Coinbase files 21 + 27 + 12 + 15 passed.
