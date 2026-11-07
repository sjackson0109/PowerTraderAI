# B: Architecture assessment for strategy research and catalogue expansion

**Code read:** `main` at `cdae9c9` (2026-11-07). This is read-only: nothing was run, and no candle or account file was opened.
**For:** FDS-SR-001, the specification this assessment supports.
**References:** `file:line` references are to that commit, relative to `app/` unless stated.

This document records what exists, what can be reused and what is missing. It recommends nothing; FDS-SR-001 does that.

---

## 1. Summary

| Area | What exists | Reusable as it is | Missing for this initiative |
|---|---|---|---|
| Strategy interface | `Strategy.on_bar(candles) -> Signal`, closed bars only, pure, long-only (`strategies/base.py`) | Yes, for any single-coin strategy | No interface for a strategy that ranks several coins |
| Catalogue | `catalogue.json` plus a registry, cross-checked when the package is imported; parameter bounds; versions (`strategies/catalogue.py`) | Yes | Status (research-only / paper-eligible), research references, data requirements, model dependency, and families other than trend |
| Composition | `StrategyRunner`: the main strategy plus overlays, with the tightest stop winning and stops only moving up (`strategies/runner.py`) | Yes | An overlay's entry gate cannot see candles (`allow_entry(symbol, bar_time)`), so a market-regime gate cannot be an overlay today |
| Strategies | STRAT-000 to STRAT-003 | As baselines | Breakout, mean-reversion, time-series-momentum and relative-strength strategies |
| Execution | One trader process, one engine and one strategy for all coins, read on every loop | Yes, for one selected strategy | Position ownership, per-strategy cash and per-coin assignment |
| Backtester | `run_backtest`: one coin, next-open fills, fee and slippage in basis points (`backtest/engine.py`) | Yes, per coin | Portfolio, exchange minimum, coin budget, halt, account size |
| Portfolio replay | `signal_fusion.evaluation.replay`: one shared account with the trader's sizing, minimums, coin budget and halt report, for many paths at once | Yes | Opportunities from a strategy other than STRAT-001 at 1h (`signal_fusion/labels.py:35`) |
| Model lab | Walk-forward, a lockbox, R1/R2 baselines, Holm/BH, PBO, a trial log, earlier looks (`model_lab/`) | Yes, for models under the legacy exits | Scoring a model under any other strategy's exits; any GUI |
| Signal fusion | F_P/F_PV meta-models over STRAT-001's opportunities; R3/R3s; F1–F3, Q2, Q3 (`signal_fusion/`) | Yes | Generalising from STRAT-001 to any strategy |
| Market data | The exchange layer, primary first; an on-disk cache; closed bars only; rate limits per exchange (`market_data/`) | Yes | An in-process memo (each call re-reads the CSV) |
| Settings > Strategy | One engine; one strategy (STRAT-003 hidden); parameters bounded by the catalogue; one timeframe; overlays (`strategy_settings_ui.py`) | Yes, extended | A catalogue browser with status, backtests, a comparison view and model evidence |
| Backtest GUI | The hub's "Backtesting Framework" tab runs a separate legacy engine with "MA Cross" and "RSI Strategy" on a CSV file or a synthetic random walk (`backtesting_gui.py:220-228, 634-690`) | No | A window that runs `backtest.engine` on the catalogue strategies and cached candles |
| Paper trading | One account and one book, shared with Order Management; fees at the pricing exchange's rate; fills at the top of the book (`trading_mode.py`, `pt_paper_trading.py`) | Yes | Slippage beyond the spread; several simulated accounts |

## 2. Terms used in this assessment

The repository already separates these, though not always by name:

- **A strategy** decides entries and exits from closed candles: `Strategy.on_bar` returns ENTER_LONG, EXIT_LONG or HOLD (`strategies/base.py:1-17`).
- **A risk overlay** adds exits (stops) or entry gates to any strategy, through the runner (`strategies/runner.py:6-18`).
- **A model** estimates an outcome:
  - the pattern model's LONG/SHORT counts;
  - the lab's T1/T2 probabilities;
  - signal fusion's P(M = 1).

  A model becomes a strategy only through an adapter (STRAT-003, `strategies/model_strategy.py`), or acts as an entry filter on a fixed strategy (the model lab; signal fusion).
- **An execution policy** decides how a position is bought or sold, not whether to hold one. Examples are the legacy DCA ladder and the trailing profit margin.
  - Today these are hard-wired into the legacy engine (`pt_trader.py:2647-2858`) and into the lab's fixed strategy (`model_gate.replay`, `model_gate.py:255-331`).
  - No catalogue strategy uses them (`pt_trader.py:2588-2645`).
- **A baseline** is a reference for evaluation, never selected for trading. Three exist:
  - buy-and-hold (`backtest/engine.py`, `buy_and_hold`);
  - matched random entries (`backtest/random_baseline.py`; the lab's R1/R2; signal fusion's R3/R3s);
  - "always flat" (`model_lab/contestants.py:256`).

## 3. The strategy layer (`app/strategies/`)

### 3.1 Interface and determinism

- `on_bar(candles)` receives closed bars only (`open_time, open, high, low, close, volume`, UTC, ascending) and must never see the forming bar (`base.py:6-17`).
  - It is pure: no I/O, randomness or clock.
  - The runner ignores ENTER while long and EXIT while flat.
- **`warmup_bars` and `lookback_bars`:** `lookback_bars = max(5 × warmup, warmup + 200)`.
  - The backtester and the live engine feed the same window, so a signal is reproducible in either (`base.py:84-90`).
- `set_timeframe(tf_seconds)` lets a strategy refuse a timeframe (`base.py:92-95`).

### 3.2 The catalogue and registry

- **Required fields:**
  - `strategy_id`, `strategy_name`, `family`, `class_type`, `long_short_mode`;
  - `timeframe_primary`, `entry_logic_summary`, `exit_logic_summary`;
  - `dependencies_indicators`, `default_params`, `param_bounds`, `version` (`strategies/catalogue.py:19-32`).
- **Constraints:**
  - `class_type` is `main` or `risk_overlay`;
  - `family` is `trend`, `risk_overlay` or `model`;
  - `long_short_mode` must be `long_only` (`strategies/catalogue.py:33-35, 186-193`).
- **Loading fails loudly** when (`strategies/catalogue.py:174-226`):
  - an entry has no class, or a class has no entry;
  - a field is missing;
  - the defaults and bounds name different parameters;
  - a default is out of its bounds.
- **Parameter kinds:** `min`/`max`, `values`, `bool`, `model_id`, `model_timeframes` and `stages` (`strategies/catalogue.py:70-132`).
  - `resolve_params` rejects unknown names and out-of-bounds values, and refuses a float where the default is an integer (`strategies/catalogue.py:244-271`).
- **Not present:**
  - a lifecycle status;
  - research references;
  - a record of data requirements (history, timeframes, other coins);
  - a model dependency other than the family `model`.

### 3.3 Composition (`runner.py`)

- **Rules** (FDS-129 §2, `runner.py:6-18`):
  - the effective stop is the maximum of the overlays' stops;
  - a stop only moves up;
  - an exit fires on any overlay exit, a close below the stop, or the strategy's EXIT;
  - an entry needs ENTER and every overlay's `allow_entry`;
  - fills are at the next bar's open.
- **Overlay hooks:** `on_entry`, `on_bar(pos, candles)`, `allow_entry(symbol, now_bar_time)`, `on_exit`, plus export/import of state (`runner.py:91-139`).
  - **`allow_entry` receives no candles** (`runner.py:129`). An entry gate that depends on the market, such as "BTC above its 200-day average" or "volatility in its top tercile", cannot be written as an overlay without extending this hook.
- **State:** position and overlay state survive a restart (`PositionState.to_dict`, `runner.py:40-75`; `signal_engine.py:203-257`).

### 3.4 The existing strategies

| ID | Name | Family | Entry | Exit | Defaults | Timeframe |
|---|---|---|---|---|---|---|
| STRAT-000 | EMA Cross (baseline) | trend | Fast EMA crosses above slow on the closed bar | Fast below slow | 20/50 | 1h |
| STRAT-001 | Trend Crossover (DEMA/TEMA) | trend | Fast above slow for `persistence_bars`, the cross fresh, ADX ≥ 20 | Fast below slow | TEMA 12/48, persistence 2, ADX 14 ≥ 20 | 1h |
| STRAT-002 | Supertrend with ATR trailing exit | trend | Supertrend flips up and stays up `confirm_bars` | Supertrend down (the ATR trailing line) | ATR 10 × 3.0, confirm 1 | 4h |
| STRAT-003 | Trained pattern model (legacy rule) | model | ≥ `min_tf_agree` of 7 timeframes LONG, none SHORT | Primary timeframe SHORT | 3 of 7 | 1h |

- STRAT-000, -001 and -002 are all **trend-following crossover or trailing rules**. None is a breakout, mean-reversion, momentum-ranking or volatility-scaled strategy.
- STRAT-003 cannot be selected in Settings > Strategy (`strategy_settings_ui.py:44-51`). Its defaults name no model, so the engine refuses it (`strategies/settings.py:105-117`).
- **Overlays:**
  - OVL-RATCHET: a stepped stop;
  - OVL-ATR: highest close − 2.5 × ATR(14);
  - OVL-PLOCK: staged profit locks;
  - OVL-COOLDOWN: bars blocked after an exit or a loss.
- **Defaults as shipped:** STRAT-001, 1h, no overlays (`pt_settings_manager.py:131-138`).

### 3.5 Settings keys

- **Keys:** `strategy.engine` (`catalogue` | `legacy_neural`, default `catalogue`), `strategy.active_id` (default `STRAT-001`), `strategy.timeframe` (default `1h`), `strategy.params` (`{id: {name: value}}`) and `strategy.overlays` (`[{id, params}]`) (`strategies/settings.py:1-33`).
- **Fails closed:** a bad value is reported in `problem` and the trader places no orders (`strategies/settings.py:14-17`; `pt_trader.py:1756-1766`).
- **Coins are not a strategy setting:** a `strategy.symbols` left in an older settings file is ignored (`strategies/settings.py:10-12`).

## 4. Execution (`pt_trader.py`, `signal_engine.py`, `trading_mode.py`)

### 4.1 One strategy for every coin

- **One active strategy:**
  - `manage_trades` reads the strategy settings on every pass (`pt_trader.py:2261-2273`).
  - `SignalEngine` holds a single runner, built from `strategy.active_id`, its parameters and the overlays (`signal_engine.py:81, 125`).
  - It rebuilds the runner when the settings' signature changes (`signal_engine.py:118-145`).
  - So all coins use the same strategy, timeframe and overlays.
- **No per-coin or per-strategy mapping** exists anywhere in `app/`.
- **The engine switch is all-or-nothing:** catalogue mode skips the legacy trailing profit margin and DCA with a `continue` (`pt_trader.py:2588-2645`).
- **Switching hands over open positions:** a change of strategy or engine passes the open positions to the new logic (`signal_engine.py:118-139, 162-180`).

### 4.2 The legacy neural engine and its DCA

| Rule | Key | Default | Where |
|---|---|---|---|
| Entry | `trade_start_level` | Long count ≥ 3 and short count 0 | `pt_trader.py:82, 2955-2960` |
| Signal age | `SIGNAL_MAX_AGE_SECONDS` | 900 s; older reads as 0 or None | `pt_trader.py:179, 1120, 1168` |
| DCA trigger | `dca_levels` | −2.5, −5, −10, −20, −30, −40, −50% (the last repeats) | `pt_trader.py:87, 2769-2774` |
| Neural DCA trigger | none (hard-coded) | Long ≥ stage + 4 and PnL < 0, stages 0–3 | `pt_trader.py:2780-2787` |
| DCA size | `dca_multiplier` | 2.0 × the position's current value | `pt_trader.py:86, 2802` |
| DCA rate | `max_dca_buys_per_24h` | 2 per coin per rolling 24 h | `pt_trader.py:88, 2806-2812` |
| DCA budget | `max_coin_allocation_pct` | 10% of the account per coin | `pt_trader.py:2814-2824` |
| Exit | `pm_start_pct_no_dca` / `_with_dca`, `trailing_gap_pct` | 5.0% / 2.5% above average cost, trailing 0.5% | `pt_trader.py:89-92, 2647-2756` |

- **DCA is an execution policy here, not a predictive strategy:**
  - it averages down a position that a separate signal opened;
  - its only limits are the coin budget, the 24-hour rate and the cash.
- No maximum number of DCA buys exists (`position_sizing.py:11-15`).

### 4.3 Sizing, the risk gate and the halt

- **Entry size:** `start_allocation_pct` (1%) of the account's value (`pt_trader.py:2068-2088`; `position_sizing.py:74-106`).
  - If that is below the exchange minimum, it is raised to the minimum × (1 + spread + 2 × taker + margin 2%).
- **The coin cap:** a buy may be at most `max_coin_allocation_pct` (10%) of the account. The cap is raised to the minimum entry where that is larger (`pt_trader.py:1734-1739`).
  - So for an account below about 100 × the minimum entry, every entry is the minimum, above 1% (FDS-SIG-004 §3.7 item 1).
- **The halt:**
  - At `risk.emergency_drawdown_pct` (8%) from the peak the trader saw, it saves the halt and its loop **ends** (`pt_trader.py:3096-3115`).
  - Nothing is sold, including at stops, until the owner presses Resume (`pt_trader.py:339-385`).
  - `RiskManager._close_all_positions` and the related methods only write a log line (`pt_risk.py:383-396`).
  - A strategy's exits and its overlays' stops do not run while halted.
- **Account value** includes coins the trader did not buy (`pt_trader.py:2354`).

### 4.4 Paper execution

- **Fills:** a market buy fills at the best ask and a sell at the best bid, from the exchanges in Settings, primary first (`trading_mode.py:464-506, 770-789`). That is the top of the book, whatever the order's size.
  - Neither `trading_mode.py` nor `pt_paper_trading.py` contains the word "slippage".
- **Fees:** the taker rate for a market order and the maker rate for a limit order, of the exchange whose quote priced the fill (`trading_mode.py:717-741`).
  - The fallbacks are that exchange's stored standard rates, then the account's rate.
  - The fee is taken from cash (`pt_paper_trading.py:405-424`).
- **Prices:** a stale or simulated price rejects the order by default (`paper.price_fallback_policy = pause`, `trading_mode.py:593, 638-692`).
- **One account:** one process-wide `PaperExchange` and one book, `<hub>/paper/paper_account.json`, shared with Order Management through a lock file (`trading_mode.py:1289-1342, 586-589`). It starts at $10,000 (`trading_mode.py:1044`).
- **Coins:**
  - The coins are the `coins` list in `gui_settings.json`, reloaded each pass (`pt_trader.py:171, 223, 289`).
  - In paper mode, `paper_coins_mode = override` limits new entries to a subset (`paper_coins.py:1-58`).
  - Exits run over every holding (`pt_trader.py:2396`).

### 4.5 Live guards (unchanged by this initiative)

These are FDS-LIVE-001 D1–D10:
- `trading.mode` must be exactly `live`;
- a supported broker;
- a typed confirmation;
- a key check at start;
- the mode and broker pinned per process;
- per-broker books (`trading_mode.py:7-15, 1353-1397, 1515-1588, 1632-1686`).

### 4.6 Constraints on running several strategies at once

These are facts today, not proposals:

1. One strategy, one timeframe and one overlay set per trader process (§4.1). There is one trader process (`pt_hub.py:733, 2571-2576`).
2. Positions have no owning strategy:
   - the ledger's `open_positions` and `strategy_state.json` are keyed by coin (`pt_trader.py:913-916`; `signal_engine.py:85, 218-220`);
   - trade history rows carry tags (`ENTRY`, `EXIT:<rule>`, `DCA`, `TRAIL_SELL`) but no strategy id (`pt_trader.py:989-1016`).
3. One trade per coin: any non-dust holding blocks a new entry, including one the trader did not buy (`pt_trader.py:2919-2922`).
4. Shared cash, sized on the whole account's value. There is no per-strategy budget (`pt_trader.py:1587-1602, 1736, 2971`).
5. Entries are tried in the coin list's order, so earlier coins get the cash first (`pt_trader.py:2913-3032`).
6. One halt for the whole account (`risk_state.py:6-9`).
7. Exits sell different amounts by engine:
   - legacy trailing sells the whole holding (`pt_trader.py:2721`);
   - catalogue exits are capped at the ledger's quantity (`pt_trader.py:1972-1980`).

## 5. Research tools

### 5.1 The backtester (`app/backtest/`)

- **Signature:** `run_backtest(candles, runner, symbol, tf, start_index, end_index, cost=CostModel(), initial_equity=10_000)` (`backtest/engine.py:134-143`).
  - `CostModel` has a fee of 10 bps a side, slippage of 5 bps and a size fraction of 1.0 (`backtest/engine.py:40-50`).
- **Behaviour:** one coin; a signal at a bar's close fills at the next open; a position open at the end is closed at the last close (`backtest/engine.py:173-248`).
- **Not modelled:** the exchange minimum, the coin budget or the halt.
- **KPIs:** total and annualised return, maximum drawdown, Sharpe, Sortino, trades, win rate, average trade, exposure, fees, versus buy-and-hold (`backtest/kpis.py:12-24`). There is no return per capital-day.
- **Also there:**
  - a 70/30 split (`backtest/engine.py:273-383`);
  - `random_baseline` (N trades of the strategy's mean hold, placed at random; `backtest/random_baseline.py:63-219`);
  - a lookahead refusal for a model trained past the first scored bar (`backtest/engine.py:92-116`).
- **CLI:** `python -m app.backtest` (`backtest/cli.py:320-356`). There is no initial-balance flag.

### 5.2 The model lab (`app/model_lab/`)

- **Contestants:** entry models only.
  - `Fitted.entries(coin, close_s)` gives 1/0/−1 per hour (`model_lab/contestants.py:64-71`).
  - The rule contestants are `rule.sma20/50/100`, `rule.mom14`, `rule.high20`, `rule.btc50`, `rule.dip24` and `ref.always`.
  - Batch 1 also has the pattern model and trained linear or tree models (`model_lab/catalogue.py:74-90`).
- **The fixed strategy:** `model_gate.replay` with the legacy rules: trailing profit margin, the DCA ladder (neural DCA off), the 24-hour DCA cap and the coin budget, on a 100-unit account, not compounded (`model_lab/replay.py:1-62`; `model_gate.py:255-331`).
  - **No other strategy's exits can be used:**
    - `TradeTable.trade` calls `model_gate.replay` directly (`model_lab/replay.py:60`);
    - the frozen batch has no strategy field (`model_lab/batch.py:426-457`);
    - the targets T1/T2 depend on the same rules (`model_lab/targets.py:44-49, 97-103`).
  - The batch's code hashes do not cover `strategies/` (`model_lab/batch.py:104-111`).
- **Inference:**
  - walk-forward with 3-month folds and a 12-month warm-up;
  - an 18-month lockbox from 2025-05-06, never read; the final check that opens it is not yet implemented;
  - R1/R2 with B = 10,000; BH at q = 0.10, then Holm at 5%;
  - a minimum of 100 trades; PBO ≤ 0.5;
  - the 10-run report (`model_lab/walkforward.py:42-44`; `model_lab/batch.py:90-127, 977-1070`; `stats.py`).
- **Provenance:**
  - `LOOKS` (earlier exposures, `model_lab/catalogue.py:111-209`);
  - the trial log `<data dir>/model_lab/trials.jsonl`, by kind;
  - `DECLARED` batches with their spec versions;
  - a batch refuses to run if its code, scikit-learn version or candles changed (`model_lab/batch.py:126-273, 580-596`).
- **No GUI:** `model_lab_ui.py` (FDS-MH-001 phase D) does not exist yet. Batches have been run from `docs/dev/run_sig4_dev.py`.

### 5.3 Signal fusion (`app/signal_fusion/`)

- **The portfolio replay:**
  - `replay(opps, prices, costs, account, veto, scale, paths, size_fraction, halt_ends, ...)` (`signal_fusion/evaluation/replay.py:150-162`);
  - `Account(start, start_pct, max_coin_pct, margin_pct, halt_pct)`;
  - `Costs(fee, allowance, minimum_usd)`.
  - It follows the trader's sizing, the minimum-entry raise, the coin budget, one trade per coin and the cash check. It reports the halt, or ends the path at it (`signal_fusion/evaluation/replay.py:13-37, 258-336`).
- **Several account sizes from one data load** already work as one call per size: the development run looped over $10,000 and $100 (`docs/dev/sig4_dev_analysis.py:414-426`).
  - Amounts are in USD; nothing converts GBP.
- **Opportunities come from STRAT-001 at 1h only:**
  - `STRATEGY = "STRAT-001"` (`signal_fusion/labels.py:35`);
  - generated with `run_backtest` at zero cost, with no overlays (`signal_fusion/labels.py:87-110`).
- **Also:**
  - meta-models (F_P, F_PV);
  - baselines R3 (random veto) and R3s (random sizing);
  - the day-block bootstrap (28/56 days, 10 × 1,000 draws);
  - findings F1–F3, Q2 and Q3, with Holm (`evaluation/*.py`).

### 5.4 Market data

- **The entry point:** `exchange_candles(symbol, tf, start, end, closed_only, cache_dir, offline, ...)`. It goes primary first, with one exchange per series (`market_data/candles.py:436-508`).
- **The cache:** `<cache>/candles/<exchange>/<PAIR>_<TF>.csv`.
  - Only missing ranges are fetched; `offline` refuses a range the cache lacks.
  - A forming bar is never written or returned.
  - Gaps are reported, not filled (`candles.py:8-345`).
  - 2h, 4h, 8h, 12h and 1w are built from smaller cached bars where an exchange lacks them (`candles.py:366-433`).
- **Rate limits:** a shared state file per exchange under a lock. Coinbase 10/s, Binance 10, Kraken 1, KuCoin 66 (`rate_limits.py`; `pt_exchanges.py:354, 690, 1827, 2753`).
- **Sharing one load:** each call re-reads the CSV (`candles.py:281`).
  - Within one process, one DataFrame can feed any number of runners.
  - The lab loads each series once per batch (`model_lab/batch.py:648-693`).

## 6. The administration GUI today

- **Settings window tabs:** Trading, Training, Exchanges, Paper trading, LLM, Display, Working Directories and System (`pt_hub.py:7682-8161`). Strategy and Risk open as their own windows from the Trading tab.
- **Settings > Strategy** (`strategy_settings_ui.py`):
  - the signal source (rule-based or legacy neural);
  - one strategy from the catalogue (STRAT-003 not offered);
  - parameters as spinboxes bounded by `param_bounds`, checked on save;
  - one timeframe;
  - overlays ticked on or off with their parameters;
  - the entry assessment rows (FDS-SIG-004, Off).

  The descriptions come from `strategies/descriptions.py`, which every offered strategy must cover (a test checks).
- **Settings > Training:** gate settings, "Check the models in use…", and auto-retrain (`pt_hub.py:7836-7911`).
  - The trainer's training-window constants exist (`pt_pattern_trainer.py:116-118`), but there is no window field in Settings.
- **The hub's "Backtesting Framework" tab** is a separate legacy engine (§1), unrelated to `backtest.engine` and the catalogue.

## 7. Specifications and evidence already in the repository

- **FDS-121, -122, -123 and -129** (strategy runtime and catalogue, DEMA/TEMA, Supertrend, overlays) were built.
  - Their outcomes are in `docs/dev/RUN-LOG-strategy-batch-1.md` and `docs/technical/ARCHITECTURE.md`.
  - **Their spec files were never committed.** They are named only in `docs/dev/specs/00-RUN-ORDER.md:15-18`, and code comments cite their sections.
- **Specs in `docs/dev/specs/`:** FDS-MDL (and addendum A), FDS-MH-001 (and amendment 1), FDS-SIG-001 to -004, FDS-MX-001, FDS-LIVE-001 and FDS-CHART-001.
- **Evidence about the existing strategies:**
  - **`docs/dev/BACKTEST-REPORT-batch-1.md`** (2023-01 to 2026-09, BTC and ETH, Binance, 10 bps fee + 5 bps slippage, 100% of equity per entry):
    - Out of sample (2025-08-16 to 2026-09-30), every STRAT-001 and STRAT-002 run lost money.
    - On 1h they did worse than buy-and-hold (−29% and −39%).
    - On 4h some lost less than buy-and-hold.
    - These are one look, on one split; the lockbox months are included.
  - **`docs/dev/SIG4-REPORT-dev.md`:** unfiltered STRAT-001 at 1h, 0.50% fee, 2021-01-01 to 2025-05-06, 11 coins: 6,825 trades, net −$5,191 on $10,000, a 53% maximum drawdown.
  - **`docs/dev/model-research/C-evidence.md`:** methods (White, SPA, DSR, PBO, FDR, lockbox, how many trades are needed), and the verdict that no published study shows a model timing crypto entries better than random after costs like ours.
- **Earlier looks relevant to new strategies:**
  - The lab's rule contestants `rule.high20` (a 20-day high) and `rule.mom14` (14-day momentum) are entry signals close to a breakout and a time-series-momentum strategy.
  - The phase B timing run read their walk-forward results (2021-01-01 to 2025-05-06) under the legacy exits (FDS-MH-001 §5.7). That is a look at those *entry signals* over the development period, under different exits.

## 8. Reusable interfaces

| Need | Existing interface |
|---|---|
| A strategy's decisions on cached candles | `strategies.factory.build_runner`; `backtest.engine.run_backtest` |
| Buy-and-hold with the same costs | `backtest.engine.buy_and_hold` |
| Matched random entries (per coin) | `backtest.random_baseline.match`, `placement`, `run_seed` |
| A shared account at several sizes | `signal_fusion.evaluation.replay.replay` with `Account`, `Costs` |
| Random-veto and random-sizing baselines | `signal_fusion.evaluation.baselines.r3`, `r3s` |
| Day-block bootstrap, 10 runs | `signal_fusion.evaluation.bootstrap` |
| Holm, BH, PBO, smallest detectable edge | `model_lab.stats` |
| Walk-forward calendar | `model_lab.walkforward.make_calendar`, `Calendar` |
| Frozen batches, trial log, looks | `model_lab.batch.freeze`, `log_trial`, `trial_counts`; `model_lab.catalogue.LOOKS` |
| Model probabilities per hour | `model_lab.contestants.Fitted.probabilities`; `signal_fusion.meta` |
| Candles, primary exchange first, cached | `market_data.candles.exchange_candles`; `model_lab.series.load` |
| Fees per exchange | `entry_gate.trading_fees`; the exchange layer's `trading_fees` |
| Minimum entry | `position_sizing.minimum_entry_usd`, `entry_usd` |

## 9. Integration gaps

1. **Strategy-neutral opportunities:** `signal_fusion.labels` is fixed to STRAT-001 at 1h with no overlays.
2. **A portfolio backtest of a catalogue strategy:** today `run_backtest` (one coin, no minimums, no budget, no halt) and the replay (portfolio, but only for supplied opportunities) are separate.
3. **Model × strategy in the lab:** the lab scores models only under the legacy exits. The batch record has no strategy field, and its code hash does not cover `strategies/`.
4. **A market-aware entry gate:** an overlay's `allow_entry` cannot see candles.
5. **A strategy that ranks coins:** `on_bar` sees one coin's candles. Relative strength needs every coin's bars at the same closed hour, and a portfolio-level decision.
6. **Catalogue status:** nothing records whether a strategy is research-only, eligible for paper or selected. Every main strategy except a model one is selectable today.
7. **GUI:**
   - no window runs `backtest.engine` or compares results;
   - the legacy "Backtesting Framework" tab uses synthetic or file data;
   - no model lab window exists.
8. **Paper slippage:** paper fills at the top of the book. The spread is paid, but nothing models the size of the order.
9. **Position ownership:** positions are keyed by coin, and trade records carry no strategy id or version.
10. **The halt:** it ends the trader's loop without exits. Any evaluation that reports a strategy's drawdown must state that a halted trader stops managing its positions (FDS-SIG-004 §3.7 item 3).

## 10. Points found in passing, for the backlog

These are not defects this initiative depends on, and none is reopened here:

- **The neural DCA trigger and the display disagree:** the trigger hard-codes `stage + 4` (`pt_trader.py:2781`), while the display shows `start_level + 1 + stage` (`pt_trader.py:2438-2442`). They differ when `trade_start_level` ≠ 3.
- **`paper_mode_balance` is not read:** the key in `gui_settings.json` (`pt_hub.py:590`) is not read by the trader. Settings > Paper Account sets the balance.
- **The legacy "Backtesting Framework" tab** runs strategies outside the catalogue on synthetic or file data. Its results are not comparable with `backtest.engine`'s.
- **FDS-121/122/123/129** spec files are missing from the repository. Code comments cite their sections.
