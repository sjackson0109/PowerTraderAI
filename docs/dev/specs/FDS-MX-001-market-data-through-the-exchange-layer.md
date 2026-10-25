# FDS-MX-001 — Market Data Through the Exchange Layer, Primary Exchange First

**Issue:** none yet. Raise "Market data must come from the exchanges in Settings, not one exchange" and link it here.
**Target repo:** `sjackson0109/powertraderai`
**Branch:** this spec is on `docs/fds-mx-001-exchange-market-data`, cut from `main` at `4ab466c`. Each phase is built on its own `feat/mx-<letter>-…` branch, cut from `main` after the previous phase is merged.
**Recommended model:** Claude Opus 5.5, effort high, for phase A (the interface and the four connectors) and phase F (the trainer). Sonnet 5.5, effort high, for the wiring phases.
**Run log:** `docs/dev/RUN-LOG-mx-1.md`.
**Status:** draft for owner review, 2026-10-25. The owner's decisions go in §8.
**Related:** PR #177, which reads minimum order sizes this way already (`AbstractExchange.min_order_usd`, primary first). FDS-CHART-001 §4 and the FDS-MDL data section name Binance as the candle source, and change with this spec (phase H).

---

## 1. Objective

PowerTraderAI uses **multiple exchanges, with the user's primary exchange preferred** and the other enabled exchanges as fallbacks (Settings → Primary exchange; `trading_config.json`). Every piece of market data the app reads should come through that layer: prices, candles, market status and minimum order sizes.

Today eleven features bypass the layer. They call Binance directly, or KuCoin, or Robinhood. This spec moves each of them onto the layer, one phase at a time, and adds a test that fails if an exchange endpoint is written outside the connectors again.

## 2. The rule (owner, 2026-10-25)

> This product is designed, and should remain designed, to use multiple exchanges, with a preference of a primary exchange. Never deviate from this design.

In code this means:

- Only connector classes (`app/pt_exchanges.py`, one class per exchange) contain an exchange's API host, endpoints or field names.
- Everything else asks the exchange layer (`ExchangeManager` / `MultiExchangeManager`, reached through `pt_multi_exchange.shared_manager()`).
- The layer asks the **primary exchange first**, then the other enabled exchanges in their Settings order.

## 3. Today: what bypasses the layer

Found by searching all tracked app code for exchange hosts and names, 2026-10-25. The list is complete; tests, docs, exchange setup screens and the connectors themselves are not listed.

| # | Feature | Where | Reads from | Since |
|---|---|---|---|---|
| 1 | Paper trading prices (bid/ask the paper book fills at) | `trading_mode.fetch_public_quote` (`_QUOTE_URL`) | Binance `ticker/bookTicker` | FDS-096, `9c52ffb`, 2026-10-02 |
| 2 | Paper demo script | `demo_paper_trading.py` | Binance (through #1) | FDS-087, `6869922`, 2026-10-02 |
| 3 | Hub paper "Run sample" | `pt_paper_mode.fetch_binance_btc_price` | Binance `ticker/price` | #86, `ffa282d`, 2026-05-23 |
| 4 | Neural runner price history | `market_data/runner_history.py`, through `pt_data_provider.get_historical_data` | Binance klines | `df33189`, 2026-10-12 |
| 5 | Neural runner current price, when the layer fails | `pt_thinker.robinhood_current_ask` | Robinhood API, with credentials | upstream |
| 6 | Market status (delisted / halted coins) | `market_data/listing.py`; used by the runner, trainer, trader and chart labels | Binance `exchangeInfo` | PR #159, `7f6a91e`, 2026-10-12 |
| 7 | Strategy candles and backtests | `market_data/candles.py` (`BinanceKlines`), `signal_engine.default_candle_provider`, `backtest/cli.py`, `strategies/model_strategy.py` (reads that cache) | Binance klines | FDS-121, `dae9b3e`, 2026-10-02 |
| 8 | Pattern trainer data | `pt_pattern_trainer.py`, through #7 | Binance klines | FDS-MDL, `03f489e`, 2026-10-06 |
| 9 | Chart pattern labels | `pt_chart_patterns.binance_closed_bars`, `candlestick_patterns.HUB_TO_BINANCE` | Binance klines (through #7) | FDS-CHART-001, `caee234`, 2026-10-13 |
| 10 | Hub chart candles | `pt_hub.CandleFetcher` | KuCoin `{COIN}-USDT` | upstream |
| 11 | Hub "Market Data" tab | `real_time_market_data.py`, `real_time_market_data_gui.py` | its own ccxt clients (Binance, Coinbase, Kraken) and Binance/Coinbase websockets; default selection "binance" | `3d59d58`, 2026-02-24 |

Also: `pt_async_patterns.py` holds Binance ticker and kline URLs, but no module imports it.

These stay as they are (they are not data sources):

- the Binance connector;
- the exchange lists and setup screens;
- credential names;
- the region defaults in `create_default_config` (the GLOBAL region's default primary is Binance until the user picks one);
- the icon set in `pt_hub._fetch_binance_icon` (a GitHub icon pack, not an exchange API).

## 4. What the four main exchanges offer

Checked against their public endpoints on 2026-10-25 ("verified"), or taken from their API documentation ("documented").

| | Binance | Coinbase | Kraken | KuCoin |
|---|---|---|---|---|
| **Candle sizes** | all the app uses, 1m–1d and 1w (documented; used today) | 1m, 5m, 15m, 1h, 6h, 1d. **No 2h, 4h, 8h, 12h or 1w** (4h and 1w refused: verified) | 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w, 15d. **No 2h, 8h or 12h** (documented) | all the app uses, including 1w (verified) |
| **History** | years | years (2018 verified) | **only the latest ~720 bars**: 721 hourly bars = 30 days (verified) | years (2019 verified) |
| **Bars per request** | 1000 | 350 returned (verified) | 720 | 1500 (documented) |
| **Market status** | `exchangeInfo` `status` (TRADING, BREAK, HALT, ...) | product `status` (`online`, `delisted`) and `trading_disabled` (verified) | AssetPairs `status` (`online`, `cancel_only`, ...) (verified) | symbol `enableTrading` (verified) |
| **Dollar quote** | USDT | USD | USD | USDT |
| **Minimum order** | NOTIONAL filter | `min_market_funds` | `costmin` / `ordermin` | `minFunds` / `quoteMinSize` / `baseMinSize` |

The app uses these candle sizes:

- 1h, 2h, 4h, 8h, 12h, 1d and 1w for the runner (`pt_thinker.tf_choices`);
- 1h by default for the strategies (`strategy.timeframe` accepts any size in `TIMEFRAME_SECONDS`; the saved backtests used 1h and 4h);
- the same seven as the runner for the trainer, over a three-year window (`pt_pattern_trainer.DEFAULT_WINDOW`, 1095 days);
- 1m to 1w for the chart.

## 5. Design

### 5.1 The exchange interface (`AbstractExchange`)

Four optional methods. Each has a default answer of "not supported", so connectors that don't implement it keep working; the layer skips them for that request.

| Method | Returns |
|---|---|
| `candles(symbol, tf, start_ms, end_ms)` | closed bars, oldest first: `[open_time_ms, open, high, low, close, volume]`, in sizes the exchange serves natively |
| `candle_timeframes()` and `max_history_bars(tf)` | which sizes it serves, and how far back (Kraken: 720) |
| `market_status(symbol)` | `trading` (True / False / None when unknown), the exchange's own status word, a one-line reason |
| `quote(symbol)` | bid, ask and the quote time from the exchange's clock where it gives one (the paper book's staleness rules, FDS-096b, need a real quote time) |
| `min_order_usd(symbol)` | already in PR #177 |

Phase A implements all four for Binance, Coinbase, Kraken and KuCoin. Paging and back-off follow `BinanceKlines`, which becomes the Binance connector's `candles`.

### 5.2 Primary first, then the others

`ExchangeManager` gains `candles`, `market_status` and `quote` beside `min_order_usd`. Each one:

1. asks the primary exchange first;
2. then asks the other enabled exchanges, in Settings order;
3. skips an exchange that doesn't support the request, doesn't list the coin, can't reach back far enough, or fails;
4. returns its answer **with the name of the exchange and the pair that gave it**, so logs and files can say "from coinbase (primary)" or "from kucoin (coinbase has no XMR market)".

**One candle series comes from one exchange.** Bars from two exchanges are never mixed in one series: prices and candle boundaries differ slightly between exchanges.

### 5.3 Building candle sizes an exchange doesn't serve

Missing sizes are built from a smaller native size:

- 2h, 4h, 8h and 12h from 1h;
- 1w from 1d, with weeks opening Monday 00:00 UTC (as the weekly bars do today, `market_data/timeframes.py`).

Only complete groups are built. A 4h bar with an hour missing is not built; it shows as a gap, as `validate_candles` reports gaps today. This lives in a new `market_data/resample.py`, with its own tests.

### 5.4 Coins, pairs and dollars

- The app keeps naming coins `BTC`, `ETH`, and so on.
- Each connector maps a coin to its own pair: `BTCUSDT` (Binance), `BTC-USD` (Coinbase), `XBTUSD` (Kraken), `BTC-USDT` (KuCoin).
- USD, USDT and USDC count as the same dollar, as the Coinbase connector already does.
- The pair actually used is recorded with the data.
- `strategy.symbols` defaults to `["BTCUSDT"]`, a Binance pair name, and `signal_engine.pair_for` turns `BTC` into `BTCUSDT`. Phase E reads these as coins. A saved `BTCUSDT` keeps working as `BTC`; new saves store the coin.

### 5.5 The candle cache, per exchange

- Path: `<cache>/candles/<exchange>/<PAIR>_<tf>.csv`.
- The existing files are Binance bars, so they move once under `binance/` and stay usable.
- A cached series is only ever extended from the exchange it came from.

### 5.6 Keeping it this way

- **Guard test.** A new test fails if app code outside the connector module contains an exchange API host (`api.binance.com`, `api.kucoin.com`, `api.kraken.com`, `api.exchange.coinbase.com`, `trading.robinhood.com`, websocket hosts, `ccxt.<exchange>(`).
- **Shrinking allowlist.** It starts in phase A with an allowlist of the §3 entries. Each phase removes its own entries, and phase H ends with the allowlist empty.
- **No network in tests.** Tests use fake exchanges with recorded payload shapes, as `tests/helpers.FakeMarkets` does in PR #177.

## 6. Phases (one PR each)

Phase A comes first; the rest depend on it. B and C follow straight away, as the owner asked. Every phase:

- runs the full guarded suite before merge (CI runs only `app/test_*.py`);
- leaves zero failures;
- removes its rows from the §5.6 allowlist.

### Phase A — the interface and the four connectors

**Scope:** §5.1–§5.3 and the guard test with its allowlist (§5.6).

**Files:** `pt_exchange_abstraction.py`, `pt_exchanges.py`, `pt_multi_exchange.py`, new `market_data/resample.py`, tests.

**Acceptance:**
- each connector's `candles`, `market_status` and `quote` parse the shapes in §4;
- 2h, 4h, 8h, 12h and 1w are built correctly from 1h and 1d;
- the layer asks the primary first and falls back in Settings order;
- one series never mixes exchanges.

**No user-visible change.**

### Phase B — paper trading prices (§3 rows 1–3)

**Scope:**
- The paper book's quotes come from `quote()` through the layer, primary first.
- Each fill records which exchange priced it. The FDS-096b provenance fields exist already.
- `demo_paper_trading.py` and the hub's "Run sample" use the same feed.
- The staleness and fallback policy (`paper.max_quote_age_s`, `price_fallback_policy`) is unchanged.

**Decision D7** (the paper book's 10% per-order cap) is settled here.

**Acceptance:**
- a paper fill on a Coinbase-primary setup is priced from Coinbase and says so;
- with Coinbase unreachable, the next enabled exchange prices it, and the ledger says which.

### Phase C — neural runner price history and current price (rows 4–5)

**Scope:**
- `runner_history` reads recent bars through the layer, primary first. The row format the runner parses stays the same.
- `pt_data_provider.get_historical_data` goes through it.
- The Robinhood fallback in `pt_thinker` is removed (decision D4): a price the layer cannot give is reported as missing.

**Acceptance:**
- the runner's log names the exchange each coin's bars came from;
- a coin the primary doesn't list is read from the next exchange.

**Interim:** until phase F and a retrain, the models were trained on Binance USDT bars, while the runner reads the primary's bars. USD and USDT prices differ by a fraction of a percent. Decision D5.

### Phase D — market status (row 6)

**Scope:**
- `listing.py` asks `market_status()` through the layer.
- `market_status.json` gains `"exchange"`.
- The runner, trainer, trader and chart labels keep their current calls.
- Decision D8 sets whose verdict counts.

**Acceptance:**
- a coin halted on the primary gets no new buys, and the log names the exchange;
- unknown stays unknown and is asked again (as today).

### Phase E — strategy candles, backtests, chart pattern labels (rows 7 and 9)

**Scope:**
- `get_candles` fetches through the layer, using the per-exchange cache (§5.5) with its one-time move.
- `signal_engine`, `backtest/cli.py` (the backtest's source records the exchange), `model_strategy`'s cache read and `pt_chart_patterns` follow.
- `strategy.symbols` and `pair_for` move from Binance pair names to coins (§5.4).

**Acceptance:** a backtest report names the exchange and pair its bars came from.

### Phase F — the pattern trainer, provenance, retraining (row 8)

**Scope:**
- The trainer reads through the layer. It needs the whole training range, so an exchange that can't reach back (Kraken) is skipped for training (decision D6).
- Model provenance records the exchange and pair.
- The runner's provenance gate warns when a model was trained on another exchange than the one the runner reads.

**Acceptance:** a model trained on a Coinbase-primary setup records Coinbase BTC-USD.

**After merge:** retrain every coin (decision D5).

### Phase G — hub chart, Market Data tab, unused module (rows 10–11)

**Scope:**
- `CandleFetcher` reads through the layer, primary first, and shows which exchange the chart is from.
- The Market Data tab lists the exchanges in Settings with the primary selected (decision D9).
- `pt_async_patterns.py`, imported by nothing, is deleted (decision D10).

### Phase H — docs, fakes and the empty allowlist

**Scope:**
- Docs: FDS-CHART-001 §4, the FDS-MDL data section, `docs/technical/ARCHITECTURE.md`, `docs/reference/API_REFERENCE.md`, and the module docstrings that say "Binance".
- Tests: the `FakeBinance` fake becomes a general fake exchange.
- The guard test's allowlist ends empty.

## 7. Limits and risks

- **Rate limits.**
  - Coinbase and KuCoin public endpoints allow several requests a second; Kraken allows about one.
  - A first backfill of years of hourly bars takes many requests. Coinbase: about 25 for a year of hourly bars at 350 per request.
  - The cache means each bar is fetched once.
- **Kraken has no deep history.** As primary, it serves the runner, chart and strategies (recent bars), not training (D6).
- **Live orders are not touched.**
  - Only the Binance connector can place orders (`SUPPORTS_LIVE_ORDERS`).
  - In live mode, prices and minimums come from the broker the order goes to, as in PR #177.
  - Order support for other exchanges is separate work.
- **Exchanges disagree slightly.** The same coin has slightly different prices on different exchanges, and in USD versus USDT. Recording the exchange and pair with every series makes that visible instead of hidden.

## 8. Decisions for the owner

Each has a recommendation. Phases that depend on a decision wait for it.

| # | Question | Recommendation | Alternative |
|---|---|---|---|
| D1 | When the primary can't answer, ask the other enabled exchanges? | **Yes, in Settings order**, and record which one answered | Primary only; the coin is skipped |
| D2 | May one candle series mix exchanges? | **No, never** (§5.2) | — |
| D3 | Treat USD, USDT and USDC as the same dollar? | **Yes**, recording the actual pair | Use only the primary's own quote currency |
| D4 | The runner's Robinhood fallback (row 5) | **Remove it**; the layer already includes Robinhood if it is enabled | Keep it as a last resort |
| D5 | Retrain the models on the primary's bars? | **Yes, every coin, after phase F**; current models stay in use until then | Retrain only at the next scheduled training |
| D6 | Training needs three years of bars; what if the primary can't reach back (Kraken: 30 days)? | **Train from the next exchange that has the whole range, and record it** | Shorten training to what the primary has |
| D7 | The paper book refuses any order over 10% of the paper account (`pt_paper_trading._validate_order_risk`); a real exchange doesn't | **Remove that cap**; the trader's budget rules (PR #177) already limit size | Keep it |
| D8 | Whose market status counts for a coin? | **The exchange that serves the coin's data** (the primary, unless it doesn't list the coin) | The primary's only |
| D9 | The Market Data tab | **Rewire it to the exchanges in Settings** | Remove the tab |
| D10 | `pt_async_patterns.py` (imported by nothing) | **Delete it** | Rewire it |

## 9. Out of scope

- Order placement on exchanges other than Binance.
- New connectors.
- Changes to the region defaults or the list of exchanges in Settings.
- The trainer's model format.
- The strategies' logic.
