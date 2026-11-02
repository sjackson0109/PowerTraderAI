# FDS-LIVE-001 — Live Trading on Coinbase (Advanced Trade)

**Issue:** none yet. Raise "Live trading on Coinbase: balances, orders and order status" and link it here.
**Target repo:** `sjackson0109/powertraderai`
**Branch:** this spec is on `docs/fds-live-001-coinbase-live-trading`, cut from `main` at `efc2106`. Each phase is built on its own `feat/live-<letter>-…` branch, cut from `main` after the previous phase is merged.
**Recommended model:** Claude Opus 5.5, effort high, for every phase: this is real money.
**Run log:** `docs/dev/RUN-LOG-live-1.md`.
**Status:** D1-D10 accepted as recommended by the owner on 2026-10-31 ("happy to go and build D1-D10"). Phases A, B, C and E are built (§10). Phase 0 has not been run: it needs the owner's go-ahead for each run (D9). Phase D is the owner's.
**Related:** FDS-MX-001 (market data through the exchange layer); PR #155 (Coinbase Ed25519 keys); PR #177 (minimum order sizes). Three local branches, not yet merged, come first (§6, Prerequisites).

> **Read this first.** This spec adds the ability to trade real money on Coinbase. It does not make any strategy profitable. No strategy in this repo has shown an edge. In `docs/dev/BACKTEST-REPORT-batch-1.md`, all 16 out-of-sample runs lost money and every 1-hour run did worse than buy-and-hold. The FDS-MDL Test A found no evidence of an edge. Live trading is plumbing, not a reason to expect a profit.

---

## 1. Objective

The owner trades on Coinbase and has a Coinbase API key saved in PowerTrader. Today PowerTrader can trade live only on Binance. For Coinbase it reads prices only, which is why the hub shows "Exchange: COINBASE (prices only)".

This spec adds three things to the Coinbase connector: balances, market orders and order status. It also fixes the parts of the live path that would let an exchange without orders be chosen as the live broker, or would record a Coinbase fill wrongly. Paper trading stays the default and does not change.

## 2. Rules

- **Multiple exchanges, primary preferred** (owner, 2026-10-25): "never deviate from this design". In live trading the trader sends every order to `trading.active_broker` through `OrderTarget` (`trading_mode.py`). No code outside the connector may say "if coinbase". Coinbase hosts and field names stay in `pt_exchanges.py` and `coinbase_auth.py`; `test_exchange_hosts_only_in_connectors.py` enforces that. Kraken or KuCoin can later implement the same contract without trader changes.
- **Real money:** live needs the typed confirmation, as it does today. It is refused when the broker cannot place orders, and refused when the saved key cannot trade.
- **Every option in Settings** (owner, 2026-10-28): "NOT EVERYONE IS CLI PROFICIENT". Nothing a user needs may require a terminal or a hand-edited JSON file.
- **UI text states facts only**: no spec names and no design caveats on screen.

## 3. Today (code read on 2026-10-28, `main` `efc2106`)

| # | Fact | Where |
|---|---|---|
| 1 | Coinbase `place_order`, `get_balance`, `get_order_status` and `cancel_order` raise `NotImplementedError`. `SUPPORTS_LIVE_ORDERS` is False. | `pt_exchanges.CoinbaseExchange` |
| 2 | The live gate does not check `SUPPORTS_LIVE_ORDERS`, the key's permissions, or whether credentials exist. The Trading Mode dialog offers every registered exchange (23). So Coinbase can be picked as the live broker today; it fails only when the trader asks for a balance or places an order. | `trading_mode.resolve_order_target` (:1135); `pt_hub._brokers_for_selector` (:2332) |
| 3 | "(prices only)" describes `primary_exchange` (the market-data exchange), not `trading.active_broker`. With primary Coinbase and broker Binance, live trading works but the label says "prices only". | `pt_hub._exchange_status_once` (:8292) |
| 4 | The trader makes a client order id for every order but never sends it. `OrderTarget.place_order` passes only `(symbol, side, amount, price)`, so no order is idempotent. | `pt_trader.py:1487`; `trading_mode.py:1095` |
| 5 | Every order is a market order sized in coins: a buy is `round(usd / ask, 8)`. | `pt_trader.py:1710` |
| 6 | A fill is accounted from the change in buying power before and after the order. Fees are always `None`. Only the status `"filled"` (lower case) counts. | `pt_trader.py:737-807, :1536, :1571` |
| 7 | Buying power is USD, else USDT. USDC counts as cash but not as buying power. | `pt_trader.py:42-44` |
| 8 | Every non-testnet live broker shares one ledger and history folder (the hub root). | `trading_mode.TradingSettings.data_subdir` (:188) |
| 9 | The Coinbase JWT signer refuses a path with a query string. Listing accounts and fills needs query parameters. | `coinbase_auth.build_uri_claim` (:219) |
| 10 | Only Binance has a testnet (`TESTNET_BROKERS`). Live Coinbase is real money. | `trading_mode.py:71` |
| 11 | On `main`, the market-data manager reads saved keys, so it holds a key-bearing Coinbase connector. Its `place_order` has no gate and no production caller. | `pt_multi_exchange.initialize`; `ExchangeManager.place_order` (:769) |
| 12 | The owner's saved key is Ed25519, with permissions view yes, trade no, transfer no (Settings Test, 2026-10-08). | PR #155 run |

These tests pin today's limits and change in phase C: `test_exchange_choice_and_runner.py:164` (live brokers are exactly `["binance"]`), `test_coinbase_connection.py:161`, `test_coinbase_paper_gate.py:296` and `:309`, and `test_coinbase_auth.py:94` (query strings refused).

## 4. Coinbase Advanced Trade: what this needs

Read from Coinbase's developer documentation on 2026-10-28 ("documented"). Phase 0 checks the uncertain items against the real API ("verify").

Base URL: `https://api.coinbase.com/api/v3/brokerage`. Each request carries a CDP JWT: `Authorization: Bearer <jwt>`. The claims are `sub`/`kid` = key name, `iss` = `cdp`, `nbf`, `exp` = now + 120 s, a nonce, and `uri` = `"<METHOD> api.coinbase.com<path>"`. `coinbase_auth.build_jwt` already builds these.

| Call | Method and path | Key permission (documented) | Used for |
|---|---|---|---|
| Key permissions | `GET /key_permissions` | view | the Test button (exists); the live gate (new) |
| Accounts | `GET /accounts?limit=250&cursor=…` (`has_next`, `cursor`) | view | balances: `available_balance.value` per `currency` |
| Product | `GET /products/{product_id}` | view | `base_increment`, `quote_increment`, `base_min_size`, `quote_min_size`, `trading_disabled`, `is_disabled`, `cancel_only`, `limit_only` |
| Create order | `POST /orders` | trade | the order |
| Preview order | `POST /orders/preview` | **view** | preview mode (§5.6); phase 0 |
| Get order | `GET /orders/historical/{order_id}` | view | status, `filled_size`, `average_filled_price`, `total_fees`, `filled_value` |
| Fills | `GET /orders/historical/fills?order_ids=…` | view | the fills behind an order, if needed |
| Cancel | `POST /orders/batch_cancel` `{"order_ids": […]}` | trade | cancelling a stuck order |
| Fee tier | `GET /transaction_summary` | view | the owner's maker and taker rates (shown, not guessed) |

- **Order body:** `client_order_id`, `product_id` (e.g. `BTC-USD`), `side` (`BUY` or `SELL`) and `order_configuration`. This spec uses only `market_market_ioc`, with `base_size` (coins) or `quote_size` (dollars). The documentation does not say which side accepts which size field (verify).
- **Response:** `success`, then either `success_response.order_id` or `error_response.new_order_failure_reason` and `message`. Examples of failure reasons: `INSUFFICIENT_FUND`, `INVALID_SIZE_PRECISION`, `TRADING_DISABLED`, `DUPLICATE_CLIENT_ORDER_ID`.
- **Idempotency:** the documentation says a reused `client_order_id` returns the existing order instead of creating a new one, yet `DUPLICATE_CLIENT_ORDER_ID` also exists (verify which happens).
- **Order status:** `PENDING`, `OPEN`, `FILLED`, `CANCELLED`, `EXPIRED`, `FAILED`, `UNKNOWN_ORDER_STATUS`, `QUEUED`, `CANCEL_QUEUED`, `EDIT_QUEUED`. A market IOC order can end `CANCELLED` with part of it filled (`filled_size` > 0).
- **Key types:** Coinbase's own pages disagree. The Coinbase App page says only ES256 (ECDSA) keys work and that Ed25519 is "NOT supported". The CDP pages say either works for direct API calls. The owner's Ed25519 key passed `key_permissions` on 2026-10-08, so it works for that call at least (verify on orders).
- **Query strings in the JWT:** the documentation shows the `uri` claim without a query. Phase 0 checks that a path signed without its query string is accepted (verify).
- **Sandbox:** `https://api-sandbox.coinbase.com/api/v3/brokerage` returns fixed, mocked responses for the account and order calls, with no authentication. An `X-Sandbox` header selects error responses (e.g. `PostOrder_insufficient_fund`). It does no matching, so it is a source of response shapes for tests, not a testnet.
- **Rate limits:** no Advanced Trade REST rate-limit page was found. The connector backs off on HTTP 429 and, like Binance, never retries an order after a network error.

## 5. Design

### 5.1 The order contract (all live brokers)

- `OrderTarget.place_order` and `AbstractExchange.place_order` gain a keyword-only `client_order_id: Optional[str] = None`. The trader passes its existing UUID. Binance already maps it to `newClientOrderId`, and a connector that ignores it still works.
- `OrderResult` gains `fee: Optional[float] = None` (in the quote currency) and `filled_value: Optional[float] = None`, both filled when the exchange reports them.
- The trader accounts a fill from the order's own numbers (filled quantity, average price, value and fee) when the connector supplies them. Otherwise it falls back to the balance change, as today, so Binance accounting does not change.
- Orders stay market orders sized in coins (one trader path for every broker). If phase 0 shows Coinbase refuses `base_size` on a market buy, the **connector** converts to `quote_size` (coins × ask, rounded to `quote_increment`). The trader does not change (D2).

### 5.2 The Coinbase connector

- **Constructor:** `api_key=""` and `api_secret=""` by default, as in `AbstractExchange`, so building it without keys no longer raises `TypeError`.
- **`get_balance()`:** every page of `GET /accounts`, returning `{currency: available}` for each non-zero `available_balance`. Holds are excluded, matching Binance's free-only balances.
- **Product rules:** `GET /products/{id}`, cached per product for an hour. A product with `trading_disabled`, `is_disabled`, `cancel_only` or `limit_only` refuses market orders locally, with Coinbase's flag as the reason.
- **`place_order()`:**
  - `market_market_ioc`, with `base_size` rounded **down** to `base_increment`.
  - Below `base_min_size`, or below `quote_min_size` at the current ask, the order is refused locally and nothing is sent.
  - `client_order_id` is the one given, or a new UUID.
  - On success it returns `OrderResult(order_id=<Coinbase order_id>, status="pending")`.
  - On failure it returns `status="rejected"` with `reason="<new_order_failure_reason>: <message>"`. An HTTP or network error raises, as Binance does.
- **`get_order_status(order_id)`:** `GET /orders/historical/{order_id}`, mapped to the trader's lower-case states:

  | Coinbase | Trader |
  |---|---|
  | `FILLED` | `filled` |
  | `CANCELLED` or `EXPIRED` with `filled_size` > 0 | `filled`, for the filled part only, with reason "partly filled: X of Y" |
  | `CANCELLED` | `cancelled` |
  | `EXPIRED` | `expired` |
  | `FAILED` | `failed` |
  | `PENDING`, `OPEN`, `QUEUED`, `CANCEL_QUEUED`, `EDIT_QUEUED` | `pending` |
  | `UNKNOWN_ORDER_STATUS` | `pending` (the trader's wait times out and reconciles later) |

  `amount` = `filled_size`, `price` = `average_filled_price`, `fee` = `total_fees`, `filled_value` = `filled_value`.
- **`cancel_order(order_id)`:** `POST /orders/batch_cancel`. Returns True when that order's result has `success`.
- **`SUPPORTS_LIVE_ORDERS = True`**, set only in phase C, once the gate and the trader are ready.

### 5.3 Signing paths with a query

`build_uri_claim` signs the path without its query, and the request sends the parameters separately. The current refusal turns into one rule: the claim never contains a query. Tests pin both halves: the claim has no `?`, and the request URL carries the parameters. Phase 0 confirms Coinbase accepts it.

### 5.4 The gate and the broker list (all live brokers)

- `resolve_order_target` refuses live mode when the broker's class has `SUPPORTS_LIVE_ORDERS` False.
- The Trading Mode dialog offers only brokers that can place orders.
- **Key check:** when live mode is applied, and again when the trader starts, the broker's read-only key check runs (`check_connection`). If the key cannot trade (`can_trade` false), live mode is refused: "This API key cannot place orders. Create a key with Trade permission, then save it in Configure Exchange APIs." A key that can transfer gets a warning and is not refused (D4).
- The ungated `ExchangeManager.place_order` and `MultiExchangeManager.place_order` are removed (no production callers; D10).

### 5.5 The trader and its books (all live brokers)

- The trader passes `client_order_id`, records `fee` in `trade_history.jsonl` and the P&L ledger, and accounts partial fills at the filled quantity.
- **Ledger folders:** each live broker gets its own folder, `live/<broker>/`, so an order id from one exchange is never looked up on another. Live books left in the hub root are moved once into `live/<broker>/` for the broker that was active, with a backup first (D5).
- **Buying power:** unchanged (USD, then USDT). A Coinbase USDC balance is shown as cash but not spent (D6).

### 5.6 Settings and the hub

- **Trading Mode window**, when the broker is Coinbase:
  - It shows the saved key's permissions (view, trade, transfer) from the key check.
  - It states "Coinbase has no test network: live orders use real money."
  - It offers a **Preview orders only** checkbox (D3). With it ticked, the trader runs the whole live path, but each order goes to `POST /orders/preview`, which needs only View permission. Its log shows what would have been bought or sold, at what estimated price and fee, and nothing is recorded as a trade. Preview mode works with the owner's current key.
- **The hub's Exchange line:** in live mode it names the live broker ("COINBASE (live orders)" or "(preview orders)"). In paper mode it names the primary exchange ("COINBASE (prices)") (D7).
- **Check Exchanges** (branch `feat/live-exchange-check`): the API key row states whether the key can trade.

## 6. Phases (one PR each)

**Prerequisites:** merge three local branches first:
- `fix/coinbase-quote-time`: quotes dated by the response;
- `fix/market-data-no-credentials`: market data holds no keys (§3 row 11);
- `feat/live-exchange-check`: Settings > Check Exchanges.

### Phase 0: verify (nothing merged, no order placed)

This phase uses the owner's saved key for view-only calls, so it runs only with the owner's go-ahead for each run, or the owner runs it. Results go to `RUN-LOG-live-1.md`.

1. `GET /accounts?limit=250`, with the claim signed without the query. Expect 200. This checks the query rule and an Ed25519 key on a list call.
2. `POST /orders/preview`: a market buy with `base_size` for about $2 of BTC, and a market sell with `base_size`. Expect empty `errs`. This checks an Ed25519 key on a POST, and whether a market buy accepts `base_size`.
3. `GET /products/BTC-USD`, to record the increments and minimums.
4. `GET /transaction_summary`, to record the owner's fee tier.

If step 2 fails for the key type, live trading on Coinbase needs an ECDSA key. The Configure Exchange APIs window and `coinbase-setup.md` will then say so (D8).

### Phase A: the connector, read-only

- the constructor defaults;
- `get_balance`, product rules, `get_order_status` and the status map;
- the query-string signing rule.

Tests use recorded HTTP (`helpers_coinbase.recorded_http`), with response shapes taken from the sandbox. Acceptance: no test sends an order; every Coinbase status maps as in §5.2; a balance covers several pages.

### Phase B: orders and preview

- `place_order`, `cancel_order` and the preview path;
- local refusals (size, increments, product flags);
- the failure-reason mapping;
- partial IOC fills.

Acceptance:
- an order below the minimum sends nothing;
- a repeated `client_order_id` is handled as phase 0 found;
- a network error during an order is not retried.

### Phase C: gate, trader, books, hub

- the gate's `SUPPORTS_LIVE_ORDERS` check and the key check;
- the broker list;
- `client_order_id`, fees and partial fills in the trader;
- the `live/<broker>/` folders and the one-time move;
- the Exchange line;
- the Trading Mode window additions;
- `SUPPORTS_LIVE_ORDERS = True`;
- the tests in §3 updated.

Acceptance: through the real trader with a mocked Coinbase, a buy and a sell are recorded with Coinbase's own quantity, price and fee, in `live/coinbase/`.

### Phase D: the owner's acceptance

1. A day in preview mode, with the current view-only key.
2. Then a trade-enabled key with no transfer permission, and one real buy and sell of about $2 of BTC.
3. Compare the trader's history and ledger with Coinbase's order history: quantity, price and fee. They must match.

### Phase E: docs

Update these:
- `docs/exchanges/coinbase-setup.md`: key permissions, preview mode, "no test network";
- `docs/exchanges/README.md`;
- `docs/reference/QUICK_REFERENCE.md`, whose "API Trading: Yes" claim is wrong today;
- `docs/reference/EXCHANGE_DOCUMENTATION.md`, which describes a passphrase and a `coinbase_config.json` that do not exist.

## 7. Limits and risks

- **Real money.** A wrong size, a duplicated order or a mis-recorded fill costs money. Hence preview mode, `client_order_id`, the key check and the owner's $2 acceptance trade.
- **Fees.** At the paper account's order size ($1 to $2), Coinbase's fees are a large part of each trade. Phase 0 records the owner's tier, and the history records the real fee of every order.
- **Key types.** The documentation disagrees on Ed25519 (§4); phase 0 settles it.
- **Unknown rate limits.** The connector backs off on 429. The trader places at most a few orders an hour.
- **Partial fills.** IOC orders can partly fill. They are recorded at the filled part (§5.2).
- **No edge.** See the note at the top.

## 8. Decisions for the owner

| # | Decision | Recommendation |
|---|---|---|
| D1 | Order types | Market (IOC) only for now. Limit and post-only orders (lower fees) are later work. |
| D2 | Buy size | In coins for every broker. The Coinbase connector converts to dollars only if Coinbase refuses coins. |
| D3 | Preview mode | Yes. Use it before the first real order. |
| D4 | Key permissions | Refuse live mode without Trade. Warn, not refuse, when the key can Transfer, and recommend a key without Transfer. |
| D5 | Ledger folders | `live/<broker>/` for every live broker, with a one-time move (backed up) of the books in the hub root. |
| D6 | USDC | Not buying power for now (USD only on Coinbase). |
| D7 | Exchange line | The live broker in live mode; the primary exchange in paper mode. |
| D8 | Key type | Accept Ed25519 and ECDSA. If phase 0 shows Ed25519 fails on orders, live mode asks for an ECDSA key with a clear message. |
| D9 | Phase 0 | Run the four view-only calls with the owner's key, with a go-ahead per run. Or the owner runs them. |
| D10 | Ungated order paths | Remove `ExchangeManager.place_order` and `MultiExchangeManager.place_order`. |

## 9. Out of scope

- limit, stop, bracket and TWAP orders;
- websockets;
- choosing a portfolio;
- futures and perpetuals;
- transfers and withdrawals (never);
- OAuth;
- live orders on Kraken, KuCoin or other exchanges (they can implement §5.1 later, without trader changes).

## 10. As built (2026-10-31)

One branch per phase, each cut from the one before: `feat/live-a-coinbase-connector`, `feat/live-b-coinbase-orders`, `feat/live-c-live-path`, `feat/live-e-docs`. The run log is `docs/dev/RUN-LOG-live-1.md`.

Where the build differs from §5 and §6, and why:

| # | Change | Why |
|---|---|---|
| 1 | The gate's `SUPPORTS_LIVE_ORDERS` check is in phase B, not C. | Phase B adds `place_order`. Without the check, merging B alone would let a confirmed live-Coinbase setting send real orders through the old trader. |
| 2 | A market buy is always sent in dollars (`quote_size`), without first trying coins. | Coinbase's Advanced Trade order guide and its Python SDK both say a market buy takes `quote_size` and a market sell `base_size`. D2's condition ("only if Coinbase refuses coins") is met by the documentation. The trader still sizes every order in coins. |
| 3 | The buy's dollar amount is rounded to the nearest cent, not down. | The trader sizes a minimum entry as `round(usd / ask, 8)` coins; rounding that back down would put a $1 order at $0.99, below Coinbase's minimum. |
| 4 | **Preview orders only** is a per-broker setting (`trading.<broker>_preview`) that is on until turned off. A preview run keeps its books in `live/<broker>/preview/`. | Like the testnet flag, the safe value is the default. Phase D starts with a day of preview. Keeping a preview run's status and account history apart from the real books keeps those books clean. |
| 5 | A repeated `client_order_id` is handled as Coinbase's reference says: Coinbase returns the order it already made. `DUPLICATE_CLIENT_ORDER_ID` is reported as a refusal. | Phase 0 has not been run, so this follows the documentation. The trader makes a new id for every order and never resends one. |
| 6 | Check Exchanges is unchanged. | Coinbase's key check already reports "trade: yes/no" on the API key row. |
| 7 | `apply_trading_mode` refuses a broker that cannot place orders, as well as the Trading Mode window not offering one. | The window is not the only caller. |
| 8 | The one-time move of the books takes the five book files (`trade_history.jsonl`, `pnl_ledger.json`, `account_value_history.jsonl`, `trader_status.json`, `strategy_state.json`) for the active broker. It runs when a live trader starts and when the hub starts in live mode, and never merges into a folder that already has books. | Each live broker's books stay separate (D5). |

Changed after the code reviews of #195 and #196 (2026-11-02):

| # | Change | Why |
|---|---|---|
| 9 | The ungated `ExchangeManager.place_order` and `MultiExchangeManager.place_order` were removed in phase B, with the gate check, not in C (D10). | Once phase B could place Coinbase orders, those two paths would have sent one past the gate. |
| 10 | A new `client_order_id` is made only when none is given; a blank one is refused before anything is sent. The gate passes the trader's id on unchanged. | A caller's id must never be swapped for another, or the order loses its idempotency. |
| 11 | An order the broker answers with that is already in the trade history is not recorded again. | Coinbase answers a repeated `client_order_id` with the order it already made (item 5); one fill must be recorded once. |
| 12 | A sell that stops part-way is marked (`OrderResult.partial`). Both exits keep the strategy position, the trailing line and the DCA window, and each sell row records `closes_position`, so the DCA stages and 24h window rebuilt from the history carry on past it. | A market IOC sell can end part-filled; the coins still held must stay managed until they are sold. |
| 13 | The move of the books writes a marker first. A move that stopped part-way is finished on the next start, into the broker folder it began for, and the trader does not start until it is. | A half-moved set of books (history without its ledger) would lose position costs and pending orders. |
| 14 | The public REST API reads the books of the trading mode in use (`paper/`, `testnet/` or `live/<broker>/`). | It read the hub folder itself, which no longer holds any books. |
| 15 | The Trading Mode window runs the key check on a worker thread, with every choice and both buttons disabled until it answers. | A slow broker would freeze the hub, and Apply must save the choice whose key was checked. |
| 16 | A holding worth less than the coin's minimum order is dust: it is shown, but it does not stop a new entry and no exit or DCA is tried on it. | A sell rounded down to Coinbase's step can leave such a remainder; it cannot be sold, and counting it as held would block the coin for good. |

Still open:
- **Phase 0** (D9): the four view-only calls with the owner's key, with a go-ahead for each run. It confirms items 2 and 5, the query-string rule (§5.3) and Ed25519 on a POST (D8). Until then, a 401 on an order with an Ed25519 key says that Coinbase's trading documentation lists ECDSA keys.
- **Phase D:** the owner's day in preview mode, then one real buy and sell of about $2.
