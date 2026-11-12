# A2: Known-defect register (PTAI-RD-001 M0, Deliverable A)

- **Repository:** `sjackson0109/PowerTraderAI` at `e6b96ca` (origin/main), read on 2026-11-11.
- **Method:** code and documents read only. Nothing was run, edited or installed, and no git state was changed. All line numbers refer to `e6b96ca`. Paths are relative to the repository root; a bare `app/...` path is the application code.
- **"Verified"** means the cited lines were read and do what the row says. **"Not verified"** marks behaviour that depends on an exchange, or that was traced in code but not reproduced.
- **Severity** reflects the effect on M1's goals. **High:** it can invalidate a research result, or leave real positions or orders unsafe, without anyone noticing. **Medium:** a material but bounded or visible effect. **Low:** small, cosmetic, or only reachable through misuse.
- **IDs:**
  - D1 to D7 come from `docs/dev/STRAT-004-paper-readiness.md` §0 and §11.
  - A1 to A7 come from FDS-SIG-001 §15.6.
  - N1 onwards are new.

## 0. High-severity items at a glance

| ID | One line | Where |
|---|---|---|
| D1 | A bar that the exchange publishes late is decided one bar late, or never. This affects hourly and 4-hour strategies as well as daily ones. | `app/signal_engine.py:349-351, 367` |
| N1 | The 8% emergency halt ends the trader process. No exit or stop runs, nothing is cancelled and nothing is sold, yet `pt_risk` logs that it "closed all positions". | `app/pt_trader.py:3141-3152`; `app/pt_risk.py:388-396` |
| N5 | After a network error, the next pass re-sends the order with a new `client_order_id`. That can duplicate the order, orphan a position, or (live) sell the owner's own coins. | `app/pt_trader.py:1837-1845, 2641, 3001` |
| N19 | The long-holding bootstrap's block rule gave 896-day blocks (1.8 blocks), so the S3 and S4 p-values are artefacts. The amendment is a draft and not approved. | `app/strategy_lab/e1.py:682-691`; `docs/dev/specs/FDS-SR-001-amendment-1-long-holding-resampling.md:3` |

## 1. Register

Columns: ID / Defect / Evidence (file:line) / Status / Severity / Affects / Proposed fix / Fix changes paper or live trading? / Test that would reproduce it.

| ID | Defect | Evidence | Status | Sev. | Affects | Proposed fix | Changes trading? | Reproducing test |
|---|---|---|---|---|---|---|---|---|
| **Signal timing and the readiness defects (D1 to D7)** | | | | | | | | |
| D1 | The signal engine caches a candle frame that lacks the just-closed bar as the frame for that bar, and fetches again only at the next close. A late bar is decided a bar late, or skipped. The same code runs for every timeframe, so 1h (STRAT-000/001, authorised `live`), 4h (STRAT-002, `live`) and 1d strategies are all affected. Entries that fire once on an event are lost for good. | `app/signal_engine.py:291, 349-351, 365-367`; context frames `390-393, 408-409`; one-shot entries `app/strategies/builtin.py:33`, `trend_crossover.py:59`, `supertrend.py:48`; `app/strategies/catalogue.json:18,49,68`; `docs/dev/strat-004-readiness/late_daily_bar.txt` | Fixed: PR #260 (merged `2709b99`, 2026-11-12) | High | Both | Key the cached frame by its own last `open_time` when that is older than the expected bar. The frame then misses the cache and is fetched again after `FETCH_RETRY_SECONDS` (30 s). Apply the same change at line 409. | Yes | §3.1 |
| D2 | The segment snapshot does not freeze `llm.signal_mode`, which can confirm or veto entries. It also does not freeze the exchange order in `trading_config.json`, which decides the quote, fee, minimum and candles. | `app/strategy_lab/observation.py:45-61, 73-84`; `app/llm_gate.py:28-45`; `app/observation_ui.py:56-74` | Fix in PR #286 | Medium | Research | Add `llm.signal_mode`, `llm.signal_use` and the enabled exchanges, in order, to the snapshot. | No | Start a segment, then set the signal mode to veto or reorder the exchanges, and run `check`. Assert that the segment ends. |
| D3 | A change is noticed only when the Observation window opens or reconciles, so a change that is reverted in between is never seen. Reconcile also ignores each row's strategy fields. | `app/observation_ui.py:173-180`; `app/strategy_lab/observation.py:235-274` | Fix in PR #286 (Reconcile flags other strategy settings; `check` still runs only when the window opens or reconciles) | Medium | Research | Have Reconcile flag every row whose strategy id, version, parameter hash, timeframe or overlays differ from the frozen values. | No | Put a STRAT-001 row inside a STRAT-004 segment. Assert that it is flagged; today it shows as "matched". |
| D4 | Reconcile hides duplicated entries, because a second ENTRY overwrites the first. It shows a delay within the same candle as matched and an open trade as "Different candle". It omits exits, exit fees, residuals and refused orders, and it replays the Settings coins rather than the paper coins. | `app/strategy_lab/observation.py:207-216, 247-248`; `app/observation_ui.py:110-115`; `docs/dev/strat-004-readiness/reconcile_probe.txt` | Fix in PR #286 (refused orders and residuals not yet) | Medium | Research | Keep every ENTRY row and flag a second one before an exit. Add the exit fill, fee and delay to `Row`. Label trades Open or Pending, and replay the paper coins. | No | Turn the five cases in `reconcile_probe.py` into assertions. |
| D5 | `trader_status.json` reports `blocked: null` while every order is refused for authorisation, because the status reads the settings without the trading mode. The hub's strip is correct. | `app/pt_trader.py:2048-2053`; `app/signal_engine.py:102-104` | Fix in PR #279 | Low | Execution (display) | Read the settings with `mode=self._target.mode`. | No | Select a research-only strategy in paper and assert that `status["signals"]["blocked"]` is set. |
| D6 | The Observation window does not show the segment's SHA-256 or its frozen settings. | `app/observation_ui.py:182-196` | Fix in PR #286 | Low (the readiness document says low to medium) | Research | Show the hash and the frozen values, facts only. | No | A UI test asserting that the window shows the hash. |
| D7 | A segment records no code version, and the owner's app runs from the checkout, so a merge can change the trader in the middle of a segment without anyone noticing. | `app/strategy_lab/observation.py:73-84` | Fix in PR #286 | Medium | Research | Record the SHA-256 of each trading-path file at the start, and have `check` end the segment when any of them changes. | No | Change a hashed file in a temporary copy and assert that `check` ends the segment. |
| **Execution: positions and orders** | | | | | | | | |
| N1 | When the 8% emergency halt triggers, `run()` breaks and the process exits. No strategy exit, overlay stop or trailing logic runs. Pending orders are not cancelled and nothing is liquidated. Meanwhile `RiskManager.emergency_stop()` logs "Cancelling all pending orders", "Closing all positions" and "Emergency notifications sent", although those methods are empty stubs. A restart while halted exits again before managing anything. | `app/pt_trader.py:3131-3152, 3122-3129, 337-345, 412-413, 450-463, 1752-1756`; `app/pt_risk.py:347-381, 388-396, 424-427`; `docs/dev/specs/FDS-SR-001-strategy-research-and-catalogue.md:108, 602, 625` | Fix in PR #270 (O1 approved 2026-11-12): a halt refuses buys; exits, stops and the trailing margin still sell; the false log lines are removed | High | Execution (live and paper) | Correct or remove the stub log lines. Add an "exits only" halt in which buys are refused but the strategy's exits and stops still sell the positions in the ledger. This is the owner's decision, because the halt's behaviour is out of scope for FDS-SR-001 (line 625). | Yes | §3.2 |
| N2 | A strategy settings or authorisation problem (the trader "fails closed") freezes held positions. Catalogue mode is turned off, so the strategy and overlay exits are not evaluated. The legacy trailing-PM and DCA code runs on those positions instead, and every order it tries is refused, with an error logged each time. | `app/pt_trader.py:2300-2310, 2629, 2684-2898, 2177-2179, 2220-2222, 1788-1801`; `docs/dev/STRAT-004-paper-readiness.md:98` | Open (verified; the freeze is documented) | Medium | Execution | Never run the legacy branch while `strategy.engine` is `catalogue`. Keep exits for the positions in the ledger, using the last valid configuration or the exits-only rule from N1. This is the owner's decision. | Yes | Hold a STRAT-004 position in paper and change STRAT-004's authorisation to `research`. Assert that no legacy DCA or trailing sell is attempted. After the fix, assert that the strategy exit still sells. |
| N3 | When the runner cannot be built (for example STRAT-003 without a usable model, or refused parameters), `decide()` returns None. Held positions then get no exit or stop. The order gate does not check `block_reason()`. | `app/signal_engine.py:121-136, 285-287`; `app/pt_trader.py:2632-2636, 1793-1795` | Open (verified) | Medium | Execution | Apply the same exits-only rule as N1 and N2, and alert while `block_reason` is set and positions are held. | Yes | Use an engine whose build raises `ModelStoreError`, with a held position and candles that call for an exit. Assert that no sell is placed (today's behaviour). |
| N4 | When candles are stale (more than 2 bars old) or missing, held positions get HOLD as well, so neither the strategy's exits nor the overlay stops are evaluated until candles return. | `app/signal_engine.py:46, 294-318` | Open (verified; noted in readiness §3) | Medium | Execution | For held positions, try the next exchange's bars, and alert after one missed bar. | Yes | A provider returns bars that are 3 bars old, with a close below the stop. Assert HOLD today. |
| N5 | When `place_order` raises (a network error after the exchange may have accepted the order, or "accepted but gave no order id"), nothing is recorded as pending. The next pass sends a new order with a new uuid as its `client_order_id`, which defeats the idempotency that FDS-LIVE-001 relies on. A duplicate entry is possible. An unrecorded fill becomes a holding that the strategy never sells. A repeated exit sells `min(holding, ledger)`, which in live can be the owner's other coins. | `app/pt_trader.py:1837-1845, 2640-2650, 3001, 2007-2015, 2675-2681`; `app/pt_exchanges.py:2338-2339, 2360-2365`; `docs/dev/specs/FDS-LIVE-001-coinbase-live-trading.md:247` | Fix in PR #271 (O2 approved 2026-11-12): an intent is kept before sending; Coinbase resends the same id, elsewhere a 60 s wait. N6 stays open | High | Execution (live) | Persist an order intent (coin, side, decision bar, client id) before sending. On an error, resend with the same id, which makes Coinbase return the existing order. Place no other order for that coin until the intent is resolved. | Yes | §3.3 |
| N6 | An order that is not confirmed within 60 s stays in `pending_orders` and is settled only at the next start. Until then, a filled buy is a holding with no cost basis in the ledger, so the strategy never sells it, and a filled sell leaves a position in the ledger that no longer exists. A paper order can never be confirmed after a restart, because the paper book keeps no orders. | `app/pt_trader.py:1905-1910, 602, 757-847, 2675-2681`; `app/trading_mode.py:888-893, 972-995` | Open (verified) | Medium | Execution | Poll pending orders on every pass, not only at start-up, and block orders for that coin while one is pending. | Yes | A fake target confirms an order after 90 s. Assert that the fill is recorded during the run. |
| N7 | On Binance live, order results carry no fee, filled value or average price; a market order reports price 0, so the trader's own quote stands in. An order that ends `EXPIRED` or `CANCELED` with `executedQty > 0` is dropped as unfilled. | `app/pt_exchanges.py:1376-1386, 1752-1760`; `app/pt_trader.py:58-60, 1912-1915, 1920-1921` | Open (verified in code) | Medium | Execution (live, Binance) | Map a partly filled terminal state to `filled` with `partial`, as the Coinbase connector does (`pt_exchanges.py:2697-2699`). Read `cummulativeQuoteQty` and the commission of each fill. | Yes | Feed a recorded `EXPIRED` answer with `executedQty > 0` and assert that a partial fill is recorded. |
| N8 | An exception while handling one coin aborts the whole pass. `_get_candles` catches only `CandleDataError` and `OSError`, but `exchange_candles` raises `MarketNotFound` (a `RuntimeError`) when no exchange lists the coin. The loops have no per-coin `try`, so every pass skips the remaining coins (entries, and held coins later in the list) and the status file is not written. | `app/signal_engine.py:358-364, 399-405`; `app/market_data/candles.py:501-504`; `app/pt_exchange_abstraction.py:30`; `app/pt_trader.py:2433, 2952-2976, 3163-3167` | Fix in PR #272 | Medium | Execution | Catch `MarketNotFound` in both fetch paths and HOLD with a warning. Handle each coin inside its own `try`. | Yes | The provider raises `MarketNotFound` for the first coin. Assert that the second coin is still decided and that the status file is written. |
| N9 | In live mode, cached bid and ask prices are used at any age (paper alone has a limit), and an incomplete account snapshot falls back to the last complete one indefinitely. Sizing, the coin budget and the drawdown halt can therefore run on stale values. | `app/pt_trader.py:1720-1734, 2398-2410, 3133-3141` | Open (verified) | Medium | Execution (live) | Apply `max_quote_age_s` in live too. Mark the snapshot stale after a set time and suspend entries while it is. | Yes | A live fake whose quotes fail after one success. Assert that no entry is sized on a quote 10 minutes old. |
| N10 | An unreadable `pt_config.json` reads as `{}`. That means paper mode with the default strategy (STRAT-001 on 1h, authorised `live`) and no problem reported, so a paper trader switches strategy instead of failing closed. In live mode the mode check stops trading instead. | `app/trading_mode.py:152-159, 300-304`; `app/strategies/settings.py:4-6, 44-47, 135-147`; `app/pt_trader.py:2284-2291` | Open (verified) | Low | Both (paper) | Report an unreadable settings file as a problem. | Yes | Point the settings at a truncated file in paper mode and assert that trading is blocked. |
| N11 | The drawdown halt measures the whole account: holdings the trader did not open, and deposits or withdrawals. USDC is excluded from both cash and holdings. A withdrawal, or moving USD into USDC, can therefore trigger the halt. | `app/pt_trader.py:53-55, 1618-1623, 2366-2391, 425-448` | Open (verified) | Low | Execution | Measure the halt on the trader's own equity, or adjust for transfers. | Yes | Simulate a withdrawal that drops the account by 9% and assert that the halt triggers today. |
| **Backtest and paper parity** | | | | | | | | |
| N12 | An entry decision stays actionable for the whole bar. A refused or failed entry is retried every 0.5 s, and a trader started mid-bar acts on the last closed bar, so a fill can come hours after the open that the backtest uses. | `app/signal_engine.py:288-293`; `app/pt_trader.py:2973-2982, 3026-3034, 3162` | Open (verified) | Medium | Research | Act on an ENTER only within a window after the bar's close (for example 15 minutes). Otherwise record it as missed, with the reason. | Yes | Set the clock to the close plus 6 hours with an ENTER decision. After the fix, assert no buy and a "missed" record. |
| N13 | In live, OVL-COOLDOWN counts from the decision bar, because `record_exit` is passed `decision.bar_time`. The backtester counts from the fill bar, so live can re-enter one bar earlier. OVL-COOLDOWN is authorised `live`. | `app/pt_trader.py:2665-2669`; `app/signal_engine.py:197-201`; `app/strategies/overlays.py:117-119, 130-134`; `app/backtest/engine.py:212, 233` | Fix in PR #280 | Medium | Research | Pass the fill bar (the decision bar plus one step) to `record_exit`. | Yes | Run a replay and the engine with `bars_after_exit=3` and assert the same first allowed entry bar. |
| N14 | After an exit, live re-evaluates the same closed bar with no position and can re-enter in the same pass. After an entry, it re-evaluates the signal bar with the new position, so `highest_close` can include that bar's close from before the entry. The backtester decides the next bar in both cases. This shows only where an entry signal is a state rather than an event (STRAT-005, STRAT-003) and an overlay exits. | `app/pt_trader.py:2674, 2948, 2975-2976, 3041-3045`; `app/strategies/runner.py:302-303`; `app/strategies/momentum.py:91, 114`; `app/backtest/engine.py:216-255` | Open (verified; neither strategy is authorised to trade) | Low | Research | Record, per coin, the bar of the last entry and exit, and do not decide that bar again. | Yes | STRAT-005 with OVL-ATR, where the stop is hit on a decision day. Assert no re-entry in the same pass. |
| N15 | Candles come from the first exchange in Settings that serves them. If the primary fails, the decision silently uses another exchange's bars (USD against USDT), and the decision log does not name the exchange. | `app/market_data/candles.py:436-508`; `app/signal_engine.py:50-60, 412-434`; readiness §3 (`docs/dev/STRAT-004-paper-readiness.md:148`) | Logged: PR #273 names the exchange on every decision. Pinning one exchange for held positions is not done (it changes trading) | Medium | Research | Log the exchange with each decision. For held positions and observation segments, use one fixed exchange, or HOLD when it fails. | No (yes if the exchange is pinned) | The primary raises and the second exchange serves. Assert that the decision log names the exchange. |
| N16 | Whether a bar has closed is decided by the local clock, and the first fetch comes within about a second of the close. A bar that the exchange revises afterwards (or that is still forming there because the local clock runs fast) is cached permanently: cached bars are never fetched again and gaps inside the cache are never refilled. Reconcile and later backtests read the same cache, so they would agree with the flawed decision. | `app/market_data/candles.py:241-245, 279, 286-304, 332-333` | Open (whether exchanges revise bars is not verified) | Medium | Both | Decide a bar only after a short settling delay. Fetch the last few cached bars once more and compare them, and refill interior gaps. | Yes | A fake fetcher first returns a provisional close and later a revised one. Assert that the cache holds the revised bar. |
| N17 | Gaps in a series are reported but never acted on. The strategy lab, the backtester and the live engine join bars across a gap of any length: Coinbase's 2.5-year XRP halt became single trades in compare-9, and strategies that count bars (STRAT-000/001/002/004) stretch their lookbacks without notice. What a cache holds also depends on how it was fetched: E1's XRP daily series starts after the halt, and compare-9's does not. | `app/market_data/candles.py:164-185, 347`; `app/strategy_lab/simulate.py:81`; `app/backtest/engine.py:216-255`; `docs/dev/COMPARISON-9-COINS-REPORT-dev.md:135-151, 228`; `docs/dev/sr1-e1/cache_cut.json` (`XRP-USD_1d`: 662 rows kept) | Fixed in the strategy lab: PR #265. The single-coin backtester and the live engine are unchanged | Medium | Both | End a series at any gap longer than one day, as the model lab already does (`app/model_lab/series.py:10-12, 32`). In live, hold entries while the decision window contains a gap. | Yes (the live part) | A synthetic series with a 30-day hole and an open position. Assert that no trade spans the hole. |
| N18 | E1's drawdowns, and F3's "below the halt level" condition, are measured at the strategy's own closes (daily). The live halt checks bid-valued equity on every pass, so a replay can pass F3 while live would have halted. | `app/strategy_lab/simulate.py:135-152`; `app/signal_fusion/evaluation/replay.py:28-35`; `app/pt_trader.py:2391, 3133-3141` | Reported in PR #284 (intrabar fields beside the close-based ones; declared rules unchanged) | Medium | Research | Mark drawdown and the halt at hourly closes, or at intrabar lows. | No | A daily path with an intraday dip of 9% whose closes fall 7%. Assert that the halt is reported. |
| **Statistics** | | | | | | | | |
| N19 | In the long-holding bootstrap, §6.0's rule (L = 28 × 2^k days, with at most 1% of trades longer than L/2) gave 896-day blocks: 1.8 blocks in 1,586 days, with each trade's whole net booked on its entry day. The S3 and S4 p-values (below 0.01) are artefacts, and so are their smallest detectable effects. | `app/strategy_lab/e1.py:682-691, 822-847, 1336`; `app/signal_fusion/evaluation/findings.py:236`; `docs/dev/sr1-e1/SR1-E1-REPORT-dev.md:56, 375-378` | Replacement method: PR #266 (library) and PR #277 (calibration; default studentised, 1.5x blocks, worst null size 6.2%). E1 stays frozen | High | Research | §3.4 | No | §3.4 |
| N20 | There is no point-in-time coin universe (survivorship). STRAT-004's E1 profit came from the five coins listed after 2021: +$1,749, against −$56 on the six older coins. | `docs/dev/sr1-e1/SR1-E1-REPORT-dev.md:362-371`; `docs/dev/RUN-LOG-sr-1.md:626` | Open (backlog) | Medium | Research | Build the universe from listing and delisting evidence, and report the older-coin subset as a deciding row. | No | n/a (data and method) |
| N21 | Multiple testing: Holm is applied only within each family (S K=4, G K=3, M K=2), with nothing across families. Exploratory runs (compare-9's 10) are uncorrected, and the same development months were reused by E1, compare-9, the model lab and SIG-004. | `docs/dev/sr1-e1/SR1-E1-REPORT-dev.md:7-45`; `docs/dev/COMPARISON-9-COINS-REPORT-dev.md:207`; `app/model_lab/stats.py:53-62` | Open (the per-family control was declared by design, E-D11) | Medium | Research | Keep one programme-wide trial ledger with an error budget, and run deciding tests only on unseen months. | No | n/a |
| N22 | PBO is computed with only 2 to 5 contestants, and each trade's net is attributed to the block of its entry, so long holds leak between the halves of each split. The estimates (0.52 to 0.94) are coarse. | `app/model_lab/stats.py:85-108`; `app/strategy_lab/e1.py:1051-1063` | Open | Low | Research | Use marked day sums per block, and report PBO as indicative only. | No | Two contestants whose trades span blocks. Compare attribution by entry with attribution by mark. |
| N23 | REF-RANDOM uses random entries with the strategy's own exits, not matched holding periods. A draw that runs out of bars stops short of the strategy's entry count. | `app/strategy_lab/baselines.py:9-20` | Open (a limitation by owner decision on 2026-11-07, not a bug) | Low | Research | Show a matched-holding baseline beside it, and the share of draws that stopped short. | No | n/a |
| N24 | Entry gate: each coin's held-out sample is 6 to 35 trades (most below 20), against a minimum of 20 entries and a 95th-percentile test. No model can pass, and no realistic edge can be detected. | `app/entry_gate.py:318, 761-762`; `app/training_settings.py:33`; `docs/dev/GATE-DIAGNOSTIC-2026-11-05.md:28-31, 37-54, 59` | Partly fixed: the baseline was replaced by "same waits" with a per-day score (PR #224, 500a355). The sample size is open, pending a decision on pooling coins. | Medium | Research (and which legacy models are published) | Pool the coins and walk forward over years, as the diagnostic recommends. | Yes (which models are published) | A fixture with 10 entries per coin and a true edge of 0.1% a day. Assert that power is below 10%. |
| N25 | The gate runs afresh at every retrain (every 1 to 336 hours) for each coin, and a model is published on any pass, with no correction for repeated tests. | `app/pt_hub.py:753-754`; `app/pt_pattern_trainer.py:101-112`; `app/entry_gate.py:739-800` | Open (latent while N24 lets nothing pass) | Medium | Research | Set a fixed error budget per coin and window, or require confirmation on a later window. | Yes (which models are published) | Retrain a model with no skill 50 times and assert a publication rate of at most 5%. |
| N26 | Model gate: it replays the trailing-PM and DCA exits on hourly closes and never raises an entry to the exchange minimum, whereas the trader acts on live bid and ask prices every pass. The fit it tests (on 80% of the window) is not the fit that is published (refit on the whole window). Rule f compares scores from different held-out windows. | `app/model_gate.py:20-41`; `app/pt_pattern_trainer.py:1145-1152, 1208-1216`; `app/entry_gate.py:63-64` | Open (verified) | Medium | Research | Replay exits on the finest bars available. Say that the published fit is untested, and compare rule f on the same window. | No | Replay the same trades on hourly closes and on 1-minute bars, and report the difference. |
| **Fees and fills** | | | | | | | | |
| N27 | Some fee defaults bypass the exchange layer. The backtest engine and its CLI default to 0.10%. LLM signal scoring falls back to 0.10%, and so does paper as a last resort. The strategy lab's fee is typed in (0.50% by default), and the legacy Backtesting tab uses 0.1%. | `app/backtest/engine.py:42`; `app/backtest/cli.py:390`; `app/llm_signals.py:150-185`; `app/pt_paper_trading.py:215`; `app/trading_mode.py:733-739`; `app/strategy_lab_ui.py:233`; `app/backtesting_gui.py:206` | Open (verified) | Low | Research (the paper last resort affects both) | Default to `entry_gate.trading_fees`, and refuse rather than assume a rate when none is known. | Yes (paper last resort) | The fee feed raises and the quote names no exchange. Assert that paper refuses rather than charging 0.10%. |
| N28 | Paper fills differ from live and from the replay. Paper has no sell rounding, no minimum order and no partial fills, and it charges the fee on top of the amount, whereas the replay takes the fee out of the amount. | `app/pt_paper_trading.py:359-366, 388-421`; `app/trading_mode.py:772-789`; `app/signal_fusion/evaluation/replay.py:23-26`; readiness §4 (`docs/dev/STRAT-004-paper-readiness.md:183`) | Open (verified; about cents per trade at $135 entries) | Low | Research | Apply the venue's `base_increment` and minimum in paper, as the replay's `Costs` already does. | Yes | A paper sell of 0.123456789 DOGE. After the fix, assert that it is rounded down to 0.1. |
| N29 | The hub's legacy "Backtesting Framework" tab fills on the signal bar's own close (look-ahead). It also uses its own strategies, a 0.1% commission and optional synthetic sample data. | `app/backtesting_engine.py:262-279`; `app/backtesting_gui.py:206, 666-695`; `app/pt_hub.py:4255` | Open (not used in E1 or compare-9) | Low | Research (if used) | Retire the tab, or route it through `backtest.engine`. | No | A signal on bar t. Assert that it fills at the open of bar t+1. |
| **Books and reconciliation** | | | | | | | | |
| N30 | Order Management appends MANUAL rows to the same `trade_history.jsonl` without updating `pnl_ledger.json`. A manual trade in a coin the strategy holds leaves the ledger's quantity and cost basis wrong, and `_trade_ended` stale until the trader restarts. | `app/order_management_execution.py:1492-1528`; `app/pt_trader.py:1072-1095, 2007-2015` | Open (verified) | Low | Both | Keep separate books for each source, or update the ledger from MANUAL fills. | Yes | Sell half of a strategy position manually. Assert that the ledger quantity equals the holding. |
| N31 | Writes to the ledger, the trade history, the status file and the paper book swallow every error, so a failed write loses a fill record without a trace. | `app/pt_trader.py:625-639, 665-670`; `app/trading_mode.py:986-993` | Open (verified) | Low | Both | Log the error and retry, as `app/market_data/listing.py:166-178` does. | Yes | Make the trade-history path read-only and assert that an error is logged. |
| N32 | A live sell is rounded down to the exchange's step. The remainder stays in the ledger after the trade ends, so the next trade's cost basis and profit include it. | `app/pt_trader.py:942-968`; `app/pt_exchanges.py:2249-2250` | Open (verified) | Low | Research (P&L) | Clear the ledger position when `closes_position` is true, and record the remainder separately. | Yes | Sell a quantity that rounds down by 1e-8. Assert that the next trade's cost basis excludes the remainder. |
| N33 | `market_status.json` has no age limit: a stale "not trading" record blocks buys indefinitely, and a missing file allows them. Only the runner and the trainer write it. | `app/market_data/listing.py:145-198`; `app/pt_trader.py:1161-1180` | Open (verified) | Low | Execution | Use `checked_at` with a maximum age. Let the signal engine record `MarketNotFound` there. | Yes | A record written 30 days ago. Assert that the market is checked again. |
| **Fixed since the source documents** | | | | | | | | |
| N34 | STRAT-005 held for up to a year when any bar in its 365-day window was missing, because it counted bars back instead of looking up dates. | `app/strategies/momentum.py:96-106` (now looks up each reference bar by its time) | Fixed: c5533d6, PR #252 (0cc1a35) | was Medium | Research | n/a | No (research-only) | `docs/dev/STRAT-005-lookbacks-by-time.md` |
| N35 | Paper fills paid no fee, and Order Management had no `trading_fees()` (the earlier notes). | `app/trading_mode.py:579-584, 717-741, 779-789`; `app/order_management_view.py:399-410` | Fixed: 0f68204 and bc5b5fb in PR #219 (2a1ebea); Order Management in PR #221 (d490690) | was Medium | Both | n/a | n/a (merged) | `app/tests/test_paper_fees.py` |
| N36 | A backtest with OVL-REGIME crashed on its start time. | `app/strategy_lab/simulate.py` | Fixed: a193125, PR #256 (2f0eb3c) | was Low | Research | n/a | n/a | n/a |
| N37 | CI ran none of FDS-SR-001's tests. | `.github/workflows/ci-cd.yml:79-81, 127` | Fixed: PR #250 (575baf9) | was Medium | Research | n/a | n/a | n/a |
| **FDS-SIG-001 §15.6 (A1 to A7)** | | | | | | | | |
| A1 | Binance cannot complete a signal-audit ranking under the strict data-integrity rule, and excluding inactive markets would need a method that accounts for selection bias. | `docs/dev/specs/FDS-SIG-001-signal-candidate-audit.md:977-982`; `docs/dev/RUN-LOG-sig-1.md:533` | Open (deferred by the owner) | Low | Research | A provider-neutral exclusion method, in a later spec. | No | n/a |
| A2 | KuCoin's `tradingStartTime` is accepted as listing evidence. | `FDS-SIG-001:983-984` | Fixed (decided; nothing to change in code, PR #228) | Low | Research | n/a | No | n/a |
| A3 | A replacement round may overlap an unexamined cancelled window, but evaluates only observations after its own registration. | `FDS-SIG-001:985-986`; `app/signal_audit/registration.py:641-647` | Fixed (PR #228; the start rule is enforced in code) | Low | Research | n/a | No | n/a |
| A4 | A replacement round ranks afresh. | `FDS-SIG-001:987`; `docs/dev/RUN-LOG-sig-1.md:606` | Partly fixed (decided; enforced only by review) | Low | Research | Make it a refusal in the script. | No | A replacement that reuses the old ranking. Assert that it is refused. |
| A5 | A replacement round takes the next free round number. | `FDS-SIG-001:988`; `RUN-LOG-sig-1.md:606` | Partly fixed (enforced only by review) | Low | Research | Make it a refusal in the script. | No | n/a |
| A6 | A confirmation window must not reuse evaluated observations; a window cancelled before results is the exception. | `FDS-SIG-001:989-998`; `app/signal_audit/registration.py:593-625, 628-655` | Fixed: 5ac6d03, PR #228 (e0d837a) | Low | Research | n/a | No | n/a |
| A7 | Research results reach `main` without merging frozen code. | `FDS-SIG-001:999-1000`; `RUN-LOG-sig-1.md:606` | Partly fixed (enforced only by review) | Low | Research | A transfer check in the script. | No | n/a |

## 2. Fees: the questions asked

- **Taken from the exchange layer?** Mostly. These all use it:
  - paper fills: the taker rate of the exchange whose quote priced the fill (`app/trading_mode.py:779-789`);
  - live fills: the fee the exchange reports (`app/pt_trader.py:1954`);
  - entry sizing (`app/pt_trader.py:2093-2101`);
  - the entry gate and the model lab (`app/entry_gate.py:66-72`; `app/model_lab/batch.py:394`).

  The exceptions are listed in N27. The Binance connector reports no fee at all (N7).
- **Is paper charged fees?** Yes, since PR #219. "Paper has no fees" is no longer true. The last-resort rate of 0.10% applies only when no exchange states a rate (N27).
- **`trading_fees()` missing in Order Management?** No longer true: `trading_fees_of` is at `app/order_management_view.py:399-410` (PR #221).

## 3. High-severity items

### 3.1 D1: a late bar is decided late, or never

**Mechanism.**
1. The trader calls `decide()` for every coin on every pass, about every 0.5 s (`app/pt_trader.py:3161-3162`).
2. `decide()` sets `expected_last_open = now.floor(step) - step` (`app/signal_engine.py:291`).
3. `_get_candles` returns the cached frame whenever its key equals that bar (`349-351`).
4. Otherwise, at most once every 30 s (`352-357`), it asks the provider and stores whatever comes back under the expected key (`367`), even when the frame's last bar is older.
5. If the first fetch after a close lacks the just-closed bar, that frame counts as current until the next close.
   - Each pass re-decides the previous bar, which repeats a decision already made.
   - The stale test does not fire, because the frame is less than 2 bars old (`305-307`).
6. At the next close, a newer bar is last, so the late bar is never the decision bar.

**Effect, by strategy.**
- **Entries that fire once** are lost for good, because their event is tied to one bar:
  - STRAT-000: a cross on this bar (`app/strategies/builtin.py:33`);
  - STRAT-001: the fresh confirmation (`app/strategies/trend_crossover.py:59`);
  - STRAT-002: the flip (`app/strategies/supertrend.py:48`).
- **STRAT-004** enters a day late, or never.
- **Exits** that depend on a state (for example fast below slow, or a new closing low) are delayed by one bar.
- **Every timeframe** is affected:
  - 1h (STRAT-000 and STRAT-001, authorised `live`);
  - 4h (STRAT-002, authorised `live`). Coinbase builds 4h bars from 1h bars and skips an incomplete group (`app/market_data/resample.py:47-49`), so one late hour removes the 4-hour bar;
  - 1d.
- **The overlay context** has the same defect (`390-393`, `408-409`).

**Exposure.** It depends on how quickly each exchange publishes a closed bar, which is not verified. The trader's first fetch comes within about a second of the close.

**Minimal reproduction** (a unit test with synthetic data, in the pattern of `docs/dev/strat-004-readiness/late_daily_bar.py`):
1. Build 300 hourly bars in which the last bar closed at T, bar k, is STRAT-000's fresh cross.
2. Give `SignalEngine` a fake clock and a provider that returns bars up to k−1 on its first call and up to k on every later call.
3. Call `decide("BTC")` at T+1 s, T+31 s and T+3,601 s.
   - **Today:** the decisions are for bars k−1, k−1 and k+1, with no ENTER_LONG.
   - **Expected:** bar k is decided ENTER_LONG by T+31 s.
4. Second case: the provider never publishes bar k. Count its calls from T to T+600 s; expect at most 21, one every 30 s.
5. Repeat both cases with daily bars and STRAT-004.

**Smallest safe fix** (`app/signal_engine.py:367`, and the same at `409`):
```python
last = df["open_time"].iloc[-1]
self._candles[pair] = (expected_last_open if last >= expected_last_open else last, df)
```
- A frame without the expected bar is then only a fallback. The next pass misses the cache, and the existing 30-second pacing (`353-356`) limits how often it fetches.
- Bars that arrive on time behave exactly as today.
- **Changes paper and live trading:** yes. Decisions are made within about 30 s of a late bar, instead of a bar later.

### 3.2 N1: the emergency halt leaves positions unmanaged and says otherwise

**Mechanism.**
1. At the start of each loop, `run()` reads the last complete account value and calls `check_emergency_conditions` (`app/pt_trader.py:3133-3141`, `425-448`).
2. At 8% below the peak it calls `emergency_stop()` (`450-463`) and then `break` (`3152`). `run()` returns, and the process ends (`3176`).
3. `emergency_stop()` calls `RiskManager.emergency_stop()` (`app/pt_risk.py:347-381`). That method logs "Cancelling all pending orders", "Closing all positions" and "Emergency notifications sent". The methods behind those lines are empty stubs (`388-396`, `424-427`).
4. The halt is saved. On the next start, the risk adapter restores it (`337-345`), and `run()` exits before `manage_trades()` (`3122-3129`).
5. Any order is refused while the halt stands, sells included (`412-413`, `1752-1756`).

**Effect.**
- Positions stay open with no strategy exit, overlay stop or trailing management, at exactly the point where the account is falling.
- `trader_status.json` stops updating, because it is written at the end of `manage_trades()` (`3083-3115`).
- FDS-SR-001 documents "A halt stops the trader, exits included" (`docs/dev/specs/FDS-SR-001-strategy-research-and-catalogue.md:108, 602`) and puts changing the halt out of scope (`625`). The false log lines are not documented.

**Minimal reproduction.**
1. Create a paper `CryptoAPITrading` with an injected `SignalEngine`, using scripted candles in which STRAT-004's exit fires for a held position, a temporary books folder and `risk_state` with a peak of 10,000.
2. Set `_last_good_account_snapshot["total_account_value"] = 9100`.
3. Call `run()`.
4. Assert that it returns after one loop, that no sell is placed, that the position is still held, that `risk_state` is halted, and that the log contains "Closing all positions" (the false claim).
5. After the fix, assert that buys are refused, the exit sell fills, and the log says that only exits are allowed.

**Smallest safe fix.**
1. **Behaviour unchanged.** Stop the stubs claiming actions they do not take: remove the stub calls, or change their messages to "not implemented: positions remain open" (`app/pt_risk.py:388-396, 424-427`).
2. **An "exits only" halt.** On a halt, do not `break`. Instead:
   - set a flag so that `validate_order` and `_risk_check` refuse buys but approve sells;
   - skip the entry loop;
   - keep running `manage_trades()`, so that the strategy's exits and overlay stops still sell the positions in the ledger.

   It can be offered in Settings > Risk ("On an emergency stop: stop everything / keep exits"), with today's behaviour as the default. This is the owner's decision.
- Liquidating on a halt is not proposed: no specification asks for it, and it would sell at the worst moment.
- **Changes paper and live trading:** yes (step 2 only).

### 3.3 N5: retrying with a new client order id

**Mechanism.**
1. Every entry and every exit makes a new `client_order_id` from `uuid4` on each pass (`app/pt_trader.py:2641`, `3001`).
2. When `target.place_order` raises, `_place_gated_order` logs "ORDER FAILED" and returns None, and no `pending_orders` record exists (`1837-1845`).
   - The Coinbase connector raises on an HTTP or network error and does not retry (`app/pt_exchanges.py:2338-2339`).
   - It also raises when Coinbase accepts an order but returns no id (`2360-2365`).
3. The decision is unchanged for the rest of the bar, so the next pass places the order again with a new id.
   - Coinbase's protection against duplicates applies only to a repeated id (`docs/dev/specs/FDS-LIVE-001-coinbase-live-trading.md:247`: "The trader makes a new id for every order and never resends one").

**Outcomes.**
- **Entry duplicated.** The first order filled, but the holdings were not yet updated when the next pass ran, so a second order was placed.
- **Orphan holding.** The fill was never recorded, so the holding has no ledger cost basis, and the strategy never sells it (`2675-2681`).
- **Exit repeated.** The exit sells `min(holding, ledger quantity)` (`2007-2015`). In live, if the first sell filled unrecorded and the owner holds more of that coin, the second sell sells the owner's own coins.

**Minimal reproduction.**
1. Create a fake live `OrderTarget` whose `place_order` stores the order, fills it, and then raises `ConnectionError` on the first call only.
2. Use an ENTER decision for BTC and run `manage_trades()` twice.
3. Today: assert two orders with different `client_order_id`s, and one ledger entry or none.
4. Exit variant: the owner holds 0.5 BTC outside the trader, and the trader's ledger holds 0.1. After the first sell raises, the second pass sells a further 0.1 BTC of the owner's coins.

**Smallest safe fix.**
1. Before sending, write an intent to `pending_orders`, keyed by coin, side and decision bar, holding the `client_order_id`.
2. On an exception, keep the intent. On the next pass, resend with the same `client_order_id`, so that Coinbase returns the existing order (or `DUPLICATE_CLIENT_ORDER_ID`, which is resolved by a status lookup).
3. Place no new order for that coin and side while an intent is unresolved.
- **Changes live trading:** yes. Paper is not affected, because paper orders are synchronous.

### 3.4 N19: the bootstrap block rule for long holdings

**Mechanism.**
1. `block_length` doubles L from 28 days until at most 1% of trades last longer than L/2 (`app/strategy_lab/e1.py:682-691`).
2. Each trade's whole net and capital-days are put on its entry day (`822-847`; `app/signal_fusion/evaluation/findings.py:236`).
3. Family S's longest trades (the 90th percentile is 133 days for STRAT-005) pushed L to 896 days: 1.8 blocks in a period of 1,586 days (`docs/dev/sr1-e1/SR1-E1-REPORT-dev.md:56, 375-378`).
4. With fewer than about two blocks, the draws are nearly copies of the sample, so the centred p-value approaches 1/(B+1) whenever the estimate is positive.
5. The amendment's simulation found that the rule rejected a true null 7% to 42% of the time at a nominal 5% (`docs/dev/specs/FDS-SR-001-amendment-1-long-holding-resampling.md`, "Read this first").

**Effect.**
- S3's and S4's p-values (0.0086 and 0.0001), and their smallest detectable effects, carry no information.
- The verdicts still fail on other F3 requirements (addendum 1).
- The rule is still the approved rule for any new economic test, because amendment 1 is a draft and has not been approved (line 3).

**Minimal reproduction.**
1. **Block length.** `block_length` on 135 trade durations in which 2% exceed 448 days must return 896. Over a 1,586-day window that is fewer than 2 blocks, and assert that the economic test is not refused (today's behaviour).
2. **Size.** Generate 200 zero-drift random-walk daily series. Run STRAT-004-like long holds through `findings.f3`'s bootstrap with the §6.0 rule, and assert that the rejection rate at 5% is well above 5%. This is the amendment study's setting; a reduced version runs in seconds with B = 200.

**Smallest safe fix.**
- **Interim, with no approval needed:** a guard in `economic_test` and `findings.f3` that marks any day-block bootstrap with fewer than 14 blocks "Not assessable", which matches amendment 1's floor (§2.4).
- **Full fix:** once the owner approves, adopt amendment 1 (marked day sums, 14-day circular blocks, the basic interval).
- E1 stays frozen.
- **Changes paper and live trading:** no.

## 4. Positions left open: the four paths, and four questions for each

The four questions are:
1. Are new entries refused?
2. Are pending entries cancelled?
3. Are protective exits kept: strategy exits, overlay stops and trailing?
4. Are positions liquidated?

| Path | Trigger and where | 1. New entries refused? | 2. Pending entries cancelled? | 3. Protective exits kept? | 4. Liquidated? |
|---|---|---|---|---|---|
| **P1. Emergency halt (8%)** | `app/pt_trader.py:3137-3152`. Also any restart while halted: `337-345`, `3122-3129`. | **Yes.** The process exits. Every order is also refused at `412-413` and `1752-1756`. | **No.** The trader's unconfirmed market orders stay in `pending_orders` until the next start (`602`, `757-847`). Order Management's resting native orders on Coinbase (LIMIT, STOP_LIMIT, OCO; `app/pt_exchanges.py:2440-2441`) are not cancelled and can fill during the halt. Its own managed orders are skipped while halted (`app/order_management_execution.py:895-897`). `pt_risk` logs "Cancelling all pending orders" from a stub (`app/pt_risk.py:388-391`). | **No.** `manage_trades()` (strategy and overlay exits at `2629-2682`) no longer runs, and any sell would be refused. Order Management's PowerTrader-managed stops and trailing stops (all of them in paper) are suspended (`895-897`). Only native stop orders already resting on Coinbase still protect a position. | **No.** `_close_all_positions` is a stub that logs "Closing all positions" (`app/pt_risk.py:393-396`). Positions stay open until the owner presses Resume (`app/pt_trader.py:358-386`) and restarts the trader. |
| **P2. Strategy settings or authorisation refused (fail-closed)** | Settings are read with the trading mode (`2300-2310`), which sets `catalogue_mode = False`. The order gate (`1788-1801`) reads the same thing. | **Yes.** The entry loop takes the legacy branch (`2983-2997`), and each buy is refused at `2177-2179`. | **No.** Nothing cancels; pending orders are as in P1. | **No.** Held positions fall into the legacy trailing-PM and DCA code (`2684-2898`) instead of the strategy's exits (`2629-2682`). Every sell (`2753-2763`) and every DCA buy (`2863-2873`) is refused at the gate (`2220-2222`, `2177-2179`), and the error is logged on every pass while a trigger holds. D5 shows the strategy as not blocked (`2049`). | **No.** |
| **P3. The engine cannot decide (catalogue mode, no settings problem)** | (a) The runner cannot be built, so `decide()` returns None (`app/signal_engine.py:121-136, 285-287`). (b) Candles are stale (older than 2 bars) or missing, so the result is HOLD (`294-318`). (c) A late bar (D1). (d) A coin with no market raises `MarketNotFound` and aborts the pass (N8). | **Yes** in (a), (b) and (d), because no ENTER is made. In (c), the entry is delayed or lost. | **No.** | **No** in (a) and (b): `runner.evaluate` is not called, so stops are not checked. In (c), exits are a bar late. In (d), held coins after the failing one are not managed (`app/pt_trader.py:2433`, `3163-3167`). The order gate does not look at `block_reason()` (`1793-1795`). | **No.** |
| **P4. Fills the trader did not record (orphans)** | (a) `place_order` raised after the exchange accepted the order (`1837-1845`; N5). (b) The order was not confirmed within 60 s (`1905-1910`; N6). (c) A Binance partial fill ending EXPIRED or CANCELED (`1912-1915`; N7). | Not applicable. A repeated entry is possible with a new id (N5). | Not applicable. Case (b) stays pending until the next start. | **No.** The holding has no ledger cost basis, so catalogue mode says "the strategy will not sell it" (`2675-2681`). In legacy mode, a cost basis of 0 disables trailing (`2688`). | **No.** |

**Lesser paths, which leave positions in the same state:**
- **The trading mode changed while running.** `manage_trades()` returns before touching any position until the trader restarts (`app/pt_trader.py:2284-2291`).
- **No usable price.** A held coin without a valid quote is skipped (`2437-2438`), and a sell finds no price (`2227-2229`). Under paper's default `pause` policy that covers any quote older than 30 s (`app/trading_mode.py:656-661`).
- **The trader is not running.** Nothing manages positions; this is not a code defect.

## 5. What was not verified

- **How quickly exchanges publish bars (D1) and whether they revise them (N16).** Coinbase phase 0 has not been run.
- **The Coinbase timeout and duplicate-id behaviour behind N5.** The connector's docstring follows Coinbase's documentation; it has not been observed against the live API.
- **Whether `MarketNotFound` (N8) reaches the trader in practice.** That depends on whether the runner has already written `market_status.json` for the coin.
- **How the hub shows positions after a halt.** The trader stops writing `trader_status.json`; the hub's display of that was not traced.
- **Whether E1's XRP series is affected by the gap problem (N17).** E1's XRP cache holds 662 daily rows before the cut, so it appears to start after Coinbase's halt. This was inferred from `docs/dev/sr1-e1/cache_cut.json`; the cache itself was not opened.
- **Tests.** No test was run, so every "reproducing test" above is a design and has not been executed.
