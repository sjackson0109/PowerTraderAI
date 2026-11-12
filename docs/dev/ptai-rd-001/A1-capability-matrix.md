# A1: As-built capability matrix (PTAI-RD-001, Deliverable A)

**Code read:** `main` at `e6b96ca` (= origin/main), 2026-11-11. Read-only: nothing was run, no test was executed, no cache or user folder was opened.
**References:** `file:line` at that commit, relative to `app/` unless stated. "nv" = not verified.
**Status words:** implemented · tested · integrated (called by the trader or hub) · operational (owner can use it from the UI today) · research-only · defective · missing.

Test counts are `grep -c "def test_"` per file (parametrised cases are not expanded). The suite has 145 `tests/test_*.py` files and about 2,611 test functions. CI runs the whole app suite on Windows with Python 3.13 (`.github/workflows/ci-cd.yml:79-130`).

---

## 1. Capability matrix

### 1.1 Data acquisition

| Capability | Module(s), evidence | Status | In live/paper trader? | Tests | Notes |
|---|---|---|---|---|---|
| OHLCV candles from 4 exchanges, primary first then fallbacks, one exchange per series | `market_data/candles.py:436-508`; `pt_exchange_abstraction.py:842-851, 1065-1145`; connectors in `pt_exchanges.py`: Binance 968-998, Coinbase 2048-2077, Kraken 421-453, KuCoin 2842-2874 | implemented, tested, integrated, operational | Yes: signal engine `signal_engine.py:50-60`, runner `market_data/runner_history.py:53-56`, trainer `pt_pattern_trainer.py:553-587` | test_exchange_market_data 28, test_binance_exchange 66, test_exchange_candles 8, test_candles 17, test_candle_requests 8, test_primary_exchange_choice 11 (~150 data-layer tests) | The other ~24 connectors give prices only; the base `candles` raises NotImplementedError (`pt_exchange_abstraction.py:658-666`). Kraken serves only its latest 720 bars (`pt_exchange_abstraction.py:1108-1115`). |
| Per-exchange CSV candle cache | `candles.py:70-88, 213-345` | implemented, tested, integrated | Yes | test_candles 17, test_candle_requests 8 | Interior gaps are never refetched and exchange corrections are never picked up (`candles.py:286-304`). The CSV is re-read on every call (`:281`). Latent: an OSError on a cache write moves the series to a fallback exchange (`:495-497`). |
| Resampling to sizes an exchange lacks | `market_data/resample.py:15-64` | implemented, tested, integrated | Yes | test_candle_requests, test_exchange_market_data | Only complete groups are built; an incomplete group is a gap (`resample.py:51-52`). |
| Closed-bar enforcement | `pt_exchange_abstraction.py:1129-1136`; `candles.py:241-245`; `signal_engine.py:296, 305-318` | implemented, tested, integrated | Yes | test_exchange_market_data (:496) | The hub chart shows the forming bar on purpose (`pt_hub.py:925-934`). |
| Gaps, duplicates, listing and delisting | gaps reported, not filled: `candles.py:139-185`. Duplicates raise: `:164-176`. Listing: `market_data/listing.py:1-124`. `market_status.json` is written by the trainer (`pt_pattern_trainer.py:1735, 1802`) and the thinker (`pt_thinker.py:627-636`), and the trader reads it (`pt_trader.py:1160-1179`) | implemented, tested, integrated | Yes: buys and DCA are blocked; sells are allowed | test_coin_listing_window 32 | The trainer joins bars across gaps (`pt_pattern_trainer.py:519-542`). Catalogue mode has no listing check of its own; stale bars give HOLD. Defect N17 (A2) joins bars across exchange halts. |
| Best bid/ask (L1) | `trading_mode.py:462-480`; `pt_thinker.py:53-62` | implemented, tested, integrated | Yes: paper fill price, thinker price | test_price_source_integrity 51, test_paper_prices_from_exchanges 4 | Top of book only. |
| Order book depth, 24-hour ticker | `real_time_market_data.py:670-800`; connectors `pt_exchanges.py:588, 1152-1162, 2196, 3010-3017` | implemented, tested, operational | No: Market Data tab only | test_market_data_tab 11, _gui 19, _tickers 18 | `calculate_impact` is never called. The `trades` and `klines` SQLite tables are created but never written (`real_time_market_data.py:385-416`). |
| Trades/ticks, funding, open interest, on-chain, news/sentiment | enum values only (`real_time_market_data.py:49-50`) | **missing** | No | none | `tests/test_suite.py:395-412` imports `NewsAggregator`/`SentimentAnalyzer`, which do not exist, and skips. |
| Point-in-time universe (listings plus 30-day volume rank) | `signal_audit/ranking.py:184-235`; `pt_exchange_abstraction.py:681-695` | implemented, tested, research-only | No | test_signal_audit_ranking 14 | E1 uses a fixed coin set (`strategy_lab/e1.py:1230-1231`). The live universe is the coins in Settings. |
| Cross-process rate limiting | `rate_limits.py:1-19, 129-190` | implemented, tested, integrated | Yes | test_rate_limits 18 | |
| Scheduled refresh or backfill of data | none (grep: no prefetch or backfill) | **missing** | n/a | none | Candles are fetched on demand only. |
| Legacy `DataProvider.get_kline_data` | `pt_data_provider.py:220-245` | **defective** | No: the callers are the mock trainer and the dead `pt_neural_processor` | none | It invents one bar at the current price with volume 1000. |

### 1.2 Feature engineering

| Capability | Module(s), evidence | Status | In live/paper trader? | Tests | Notes |
|---|---|---|---|---|---|
| Strategy indicators: EMA, DEMA, TEMA, Wilder ATR, ADX, Supertrend | `strategies/indicators.py:26-171` | implemented, tested, integrated | Yes | test_indicators 17, test_supertrend 30 | Also used by Order Management ATR orders (`order_management_execution.py:1784`). |
| Regime context: daily SMA of a reference coin | `strategies/overlays.py:171-215`; `strategies/runner.py:89-110, 157-172` | implemented, tested, research-only (OVL-REGIME) | The plumbing is live (`signal_engine.py:324-327`); the overlay is not authorised | test_regime_gate 15, test_overlays 47 | Fails closed. |
| Research feature set: 26 scale-free hourly features plus seeded placebo lags | `model_lab/features.py:59-61, 177-400` | implemented, tested, research-only | No | test_model_lab_phase_c 23, test_model_lab 28 | Shared with signal_fusion (`signal_fusion/artifact.py:26`) and E1 (`strategy_lab/e1.py:1235-1260`). |
| Volatility and liquidity features: EWMA, Parkinson, QLIKE choice, dollar volume, Abdi-Ranaldo spread | `signal_fusion/volatility.py:1-37`; `signal_fusion/liquidity.py:68-186` | implemented, tested; integrated log-only | Log-only after the order (`signal_fusion/live.py:1-46`) | test_signal_fusion_phase_b 18, test_signal_fusion_live 7 | |
| Legacy pattern features and rule | inline in the thinker (`pt_thinker.py:929-990`); re-implemented in `pattern_model.py:94-365` | implemented, tested, integrated (engine `legacy_neural`) | Yes, in legacy mode | test_pattern_trainer 32, test_model_provenance 41, test_model_strategy 40 | **Two implementations** of the live rule. The thinker imports only `GAP_PASS_LIMIT` from pattern_model (`pt_thinker.py:25`). |
| Candlestick patterns | `candlestick_patterns.py:1-12`; `pt_chart_patterns.py` | implemented, tested, operational (chart only) | No | test_candlestick_patterns 24, test_chart_label_ranking 4 | "Nothing here feeds a strategy." |
| LLM prompt features: RSI14, SMA50/200, 24h change, 7-day high/low | `llm_research_engine.py:90-110, 229-260` | implemented, tested, operational | Only through the LLM hook (§1.9) | test_llm_research_engine 12 | Its own RSI implementation. |
| Feature store or shared feature library | none | **missing** | n/a | none | Features are recomputed on every run, in about 10 places (§5). |

### 1.3 Signal generation

| Capability | Module(s), evidence | Status | In live/paper trader? | Tests | Notes |
|---|---|---|---|---|---|
| Catalogue strategy engine: SignalEngine plus StrategyRunner, latest closed bar | `signal_engine.py:115-148, 264-340`; `strategies/runner.py:197-353`; trader entry `pt_trader.py:2971-2981`, exit `:2626-2680` | implemented, tested, integrated, operational | Yes, the default engine: STRAT-001 at 1h (`strategies/settings.py:45-47`) | test_signal_engine 38, test_runner 13, test_runner_history_and_signals 22 | The same runner as the backtester. One strategy for all coins. |
| Legacy pattern model: thinker plus trained memories | `pt_thinker.py:240-332, 684-707, 929-990`; trader `pt_trader.py:2982-2996` | implemented, tested, integrated, operational (`strategy.engine = legacy_neural`) | Yes, when selected | test_pattern_trainer 32, test_model_provenance 41, test_training_keeps_runner 17 | 14-day freshness check, manifest byte-match. Coins the gate refuses get 0 signals. |
| STRAT-003 model-strategy adapter | `strategies/model_strategy.py:127-246` | implemented, tested, research-only | No (`catalogue.json:87` research) | test_model_strategy 40, test_model_backtest 78 | It reads the model exchange's cache only (`model_strategy.py:93-110`). |
| Trained ML entry models: LogisticRegression, HistGradientBoosting | `model_lab/contestants.py:610-640` | implemented, tested, research-only | No | test_model_lab_phase_c 23 | **scikit-learn is not installed in the owner's `.venv`** (§4), so the 6 trained contestants in the default Compare-models selection (`model_lab/catalogue.py:74-89`) would fail at `contestants.py:618`. How the window reports that: nv. |
| Signal-fusion meta-models F_P/F_PV, out-of-fold Platt calibration | `signal_fusion/meta.py:45-60`; artifact `signal_fusion/artifact.py:1-78` | implemented, tested, research-only | No predictive part live: no artifact registered (`artifact.py:14`) | test_signal_fusion_evaluation 14, test_signal_fusion_phase_b 18 | Also needs sklearn. |
| Signal audit candidates SIG-A (CMF-20) and SIG-B (BTC lead) | `signal_audit/round_one.py:31-103`; `signal_audit/engine.py:37-46` | implemented, tested, research-only | No (`signal_audit/__init__.py:1-24`) | test_signal_audit_* ~110 | **No round registered** (no `docs/dev/sig-audit/round-N`). FDS-SIG-003 (SIG-C/SIG-D) is **missing**: no code. |
| LLM trade signals: JSON direction, strength, target, stop, horizon | `llm_research_engine.py:31-72, 150-190`; scoring `llm_signals.py:1-32` | implemented, tested, operational (LLM Research tab) | Only through the entry hook, default `log_only` (`llm_settings.py:74-95`) | test_llm_research_engine 12, test_llm_research_gui 18 | Its input is 200 hourly candles only: no news, order book or on-chain data. |

### 1.4 Strategy decisions

| Capability | Module(s), evidence | Status | In live/paper trader? | Tests | Notes |
|---|---|---|---|---|---|
| Catalogue of 11 entries with lifecycle `authorisation` (research/paper/live) | `strategies/catalogue.json:3-228`; `strategies/catalogue.py:12-18, 56-61, 232-279`; per-order check `pt_trader.py:1788-1806` | implemented, tested, integrated, operational | Yes. Authorised for paper/live: STRAT-000/001/002 and OVL-RATCHET/ATR/PLOCK/COOLDOWN. Research-only: STRAT-003/004/005 and OVL-REGIME | test_catalogue 19, test_strategy_lifecycle 18, test_strategy_params 15 | No entry is at `paper`. Promotion means editing `catalogue.json` in the read-only program folder: **no UI path**. |
| Strategies: EMA cross, DEMA/TEMA, Supertrend, Donchian 55/20, TS-momentum 30/90/365 | `builtin.py`, `trend_crossover.py`, `supertrend.py`, `breakout.py:38-77`, `momentum.py:41-115` | implemented, tested | 000-002 yes; 004 and 005 research-only | test_trend_crossover 28, test_strategy_breakout 14, test_strategy_momentum 24 | STRAT-005's gap bug is fixed (`momentum.py:97-104`), but E1's frozen results still contain it (§1.8). |
| Overlays: stop ratchet, ATR stop, profit lock, cooldown | `strategies/overlays.py`; composition `runner.py:289-344` | implemented, tested, integrated, operational | Yes | test_overlays 47 | Tightest stop wins; stops move up only. |
| Mean-reversion and relative-strength families; cross-sectional (ranking) strategies | families declared at `catalogue.py:52-53`; `strategies/base.py` `on_bar` takes one coin | **missing** | n/a | none | No class and no multi-coin interface. |
| Several strategies at once, position ownership | one runner (`signal_engine.py:81`); one trader process (`pt_hub.py:730-734`) | **missing** | n/a | none | Trade rows now carry strategy_id, version, params sha, timeframe and overlays (`pt_trader.py:1036-1064`), but positions are keyed by coin. |
| Legacy DCA ladder and trailing profit margin | `pt_trader.py:85-93, 2685-2790, 2795-2895` | implemented, integrated (legacy mode only), **defective** | Yes, legacy mode | test_partial_sells 5; nv beyond | The DCA trigger uses `stage+4` (`pt_trader.py:2813-2818`) but the display uses `start_level+1+stage` (`:2473-2479`). They disagree when `trade_start_level` ≠ 3. |

### 1.5 Portfolio construction and sizing

| Capability | Module(s), evidence | Status | In live/paper trader? | Tests | Notes |
|---|---|---|---|---|---|
| Entry size: 1% of account, raised to the exchange minimum plus costs; 10% per-coin cap | `position_sizing.py:24-33, 74-121`; `pt_trader.py:1765-1772, 2103-2124` | implemented, tested, integrated, operational | Yes | test_position_budget 24, test_entries_above_minimum 13 | |
| Cross-coin allocation, exposure cap, volatility or correlation sizing | coins are tried in list order; any holding blocks entry (`pt_trader.py:2950-2968, 2147-2160`) | **missing** | n/a | none | No total-exposure limit. |
| Mean-variance portfolio optimiser | `portfolio_optimizer.py:38-39, 148-149`; "Apply as Targets" `portfolio_optimizer_gui.py:1136-1175` | implemented, tested, operational | **No**: it writes Long-term Holdings targets, which the trader never reads | test_portfolio_optimization_tab 39 | |
| Research portfolio replay: one shared account, trader sizing, minimums, coin budget, halt reported | `signal_fusion/evaluation/replay.py:41-110, 187`; `strategy_lab/simulate.py:111-169` | implemented, tested, research-only | No | test_signal_fusion_evaluation 14, test_strategy_lab 17 | This is the only portfolio engine. |
| Cost manager | `pt_cost.py` is instantiated at `pt_trader.py:608` and never used again | implemented, not integrated | No | none | |

### 1.6 Risk controls

| Capability | Module(s), evidence | Status | In live/paper trader? | Tests | Notes |
|---|---|---|---|---|---|
| Drawdown halt: warn 3%, critical 5%, emergency 8%, persisted, Resume from Settings > Risk | `pt_trader.py:308-467, 3117-3155`; `risk_state.py:12-33`; `risk_settings_ui.py:1-20` | implemented, tested, integrated, operational, **defective** | Yes | test_risk_state 20, test_risk_settings_ui 23 | The halt `break`s the trader loop (`pt_trader.py:3129, 3152`). The emergency-stop actions only write log lines (`pt_risk.py:383-401`), so open positions get no stops while halted. |
| Daily loss limit 2%, volatility and leverage thresholds | `pt_risk.py:47, 153-248` | implemented, **not integrated** | No: `start_monitoring` is never called by the app (`pt_risk.py:112-117` says so) | nv | |
| Circuit breaker | `pt_circuit_breaker.py` | implemented, tested, **not integrated** | No: nothing imports it | test_circuit_breaker 22 | |
| `RiskManager.validate_trade` 1% cap | bypassed on purpose (`pt_trader.py:402-423`) | not integrated | No | | |
| Non-trading market blocks buys | `pt_trader.py:1161-1181, 2826-2827, 2965-2968` | implemented, tested, integrated | Yes | test_coin_listing_window 32 | |
| Manual (Order Management) orders respect sizing caps | only the halt is checked (`order_management_execution.py:483-495`); no coin_budget or position_sizing reference | **defective (gap)** | n/a | test_order_management_tab 45 | |
| Strategy-config fail-closed | `pt_trader.py:1788-1806`; `strategies/settings.py:129-218` | implemented, tested, integrated | Yes | test_strategy_lifecycle 18 | |

### 1.7 Execution

| Capability | Module(s), evidence | Status | In live/paper trader? | Tests | Notes |
|---|---|---|---|---|---|
| Order gate and trading mode (paper/testnet/live), books per mode | `trading_mode.py:236-247, 1417-1452`; `pt_trader.py:1743-1975, 2162-2247` | implemented, tested, integrated, operational | Yes | test_trading_mode 64 | The mode is fixed at start; changing it needs a restart. |
| Live market orders | `SUPPORTS_LIVE_ORDERS` only Binance (`pt_exchanges.py:692`) and Coinbase (`:2225`); the others raise NotImplementedError (e.g. `:314-318, 604-607`) | implemented, tested; Coinbase **not yet operated** | Yes, if the owner switches to live | test_coinbase_live_* 44, test_binance_exchange 66 | Market orders only. Coinbase Phase 0 has not been run (`docs/dev/RUN-LOG-live-1.md:16`). Testnet is Binance only (`trading_mode.py:86`). |
| Order lifecycle: idempotent client id, wait for terminal state, reconcile at start | `pt_trader.py:538-541, 726-848, 1873-1880` | implemented, tested, integrated | Yes | test_coinbase_live_trader 20 | |
| Order Management: limit, stop-limit, trailing, OCO (native or app-managed) | `order_management_execution.py:1-41, 1009-1035, 1123-1153`; native kinds `pt_exchanges.py:1509-1512, 2440-2448` | implemented, tested, operational | Separate from the trader; it shares the paper book | test_order_types 29, test_native_orders 5, test_order_management_tab 45 | The monitor runs only while the hub is open (`order_management_view.py:1485`). |
| Paper execution: top-of-book fills, pricing exchange's fees, pause on a stale quote | `trading_mode.py:562-590, 715-756, 1293-1350` | implemented, tested, integrated, operational | Yes | test_paper_account 25, test_paper_fees 19, test_paper_mode 14 | No slippage beyond the spread. **One** $10k book (`trading_mode.py:1044`). |
| Slippage, size-impact and partial-fill model | live/paper: none. Research: fixed bps (`backtest/engine.py:40-51`) | **missing** | n/a | none | |

### 1.8 Performance evaluation

| Capability | Module(s), evidence | Status | In live/paper trader? | Tests | Notes |
|---|---|---|---|---|---|
| Single-coin backtester: next-open fills, fee/slippage bps, 70/30 split, buy-and-hold, KPIs | `backtest/engine.py:134-349`; `backtest/kpis.py:10-85`; CLI `backtest/cli.py:368-407` | implemented, tested | No (only `CostModel` is reused by `entry_gate.py:409`) | test_backtest_engine 30, test_backtest_cli 13, test_model_backtest 78 | `python -m backtest` only: no UI. No initial-balance flag. The CLI hashes the growing cache file (`cli.py:183-189`). |
| Portfolio exploratory backtest vs hold/cash/random, GBP accounts | `strategy_lab/runs.py:134-247`; `strategy_lab/simulate.py:33-38`; UI `strategy_lab_ui.py:192` via Settings > Strategy > "Run a backtest…" (`strategy_settings_ui.py:575-600`) | implemented, tested, operational, research-only, **defective** | No | test_strategy_lab 17, test_strategy_backtest_window 13 | **N17 (A2):** `TradeTable.trade_from` walks bar indices with no time-gap check (`strategy_lab/candidates.py:197-230`), so trades span exchange halts. This produced the impossible XRP trades in `docs/dev/COMPARISON-9-COINS-REPORT-dev.md:135-148`. It refuses reserved months (`windows.py:54-67`). |
| Compare saved runs; model evidence per strategy | `strategy_lab_ui.py:586, 632`; `strategy_lab/evidence.py:92-143` | implemented, tested, operational, research-only | No | test_strategy_evidence 7, test_strategy_catalogue_view 13 | |
| Paper observation segments and reconcile vs replay | `strategy_lab/observation.py:128-196, 303-377`; `observation_ui.py`; Settings > Paper trading > "Observation…" (`pt_hub.py:8129`) | implemented, tested, operational | Reads the paper books | test_observation 7 | |
| Legacy "Backtesting Framework" tab | `backtesting_gui.py:221-225, 666-690`; `backtesting_engine.py:123-197, 649-680`; tab `pt_hub.py:4237-4255` | operational, **defective** | No | test_advanced_features 21 | Runs "MA Cross"/"RSI" on a seeded random walk or a user file, so it is not comparable with `backtest.engine`. |
| Book performance: realised, unrealised, since start, account-value chart, trade history | `pt_hub.py:1952-1990, 2523-2526, 6640-6660`; `trade_history_view.py:1-14` | implemented, tested, operational | Yes (reads the books) | test_account_profit_and_chart 12, test_trade_history_tab 11 | No Sharpe, drawdown series or per-strategy attribution is computed from the books. |
| Performance Attribution tab | `performance_attribution.py:636-645`; `performance_attribution_gui.py:178, 694-705` | operational, display-only | No | nv | Uses sample or CSV data, not the trader's books. |
| STRAT-003 holdout verdict ("Test A") | `backtest/model_eval.py:16-288` | implemented, tested, research-only | No | test_model_backtest 78 | Script only (`docs/dev/run_backtest_model1.py`). |

### 1.9 Experiment registration, statistics, authorisation, LLM, reporting, scheduling

| Capability | Module(s), evidence | Status | In live/paper trader? | Tests | Notes |
|---|---|---|---|---|---|
| Model-lab sealed batches plus trial log | `model_lab/batch.py:58-60, 104-111, 147-148, 267-299, 325-465, 572-631`; UI `model_lab_ui.py:385-401`, Settings > Training > "Compare models…" (`pt_hub.py:7941`) | implemented, tested, operational, research-only | No | test_model_lab 28, test_model_lab_ui 14 | Refuses a run after code, candle or sklearn changes. The code hash omits `strategies/` and `market_data/candles.py` (a code-hash gap, §5). |
| Strategy-lab sealed experiments plus trial log | `strategy_lab/experiment.py:38-59, 115-137, 154-184, 198-280` | implemented, tested, research-only | No | test_strategy_experiments 10, test_e1 18 | E1 is script only (`docs/dev/run_sr1_e1.py`). The code hash omits the exchange layer (a code-hash gap, §5). |
| Signal-audit registration (git-committed rounds) | `signal_audit/registration.py:1-66, 153-186, 215-352` | implemented, tested, research-only | No | test_signal_audit_run 39, test_signal_audit_script 3 | It calls `git` from a subprocess. No round is registered. |
| Signal-fusion artifact registry | `signal_fusion/artifact.py:1-78` | implemented, tested | No: none registered | nv | |
| Lockbox / reserved periods | `strategy_lab/windows.py:36-67`; `model_lab/walkforward.py:41-44, 107-141` | implemented, tested | n/a | test_e1 (:136-146) | **The final check is missing:** verdicts say "final check not run" (`model_lab/batch.py:38, 115`). The lockbox is defined twice. |
| One cross-subsystem trial ledger; correction for the number of trials | none | **missing** | n/a | none | 2 JSONL schemas plus git rounds plus artifact (§5). Trial counts are shown (`model_lab_ui.py:529`) but never used. |
| Block bootstrap (circular, day blocks, all coins together) | `signal_fusion/evaluation/bootstrap.py:33-48, 79, 140-232`; `signal_audit/stats.py:379, 422-531` | implemented, tested, research-only | No | test_signal_fusion_evaluation 14, test_signal_audit_stats 21 | Three block-length rules (§5). |
| Holm; Benjamini-Hochberg (displayed only) | `model_lab/stats.py:39-62`; `signal_audit/stats.py:532-555` | implemented, tested, research-only | No | test_model_lab, test_signal_audit_stats | Holm is implemented twice. |
| PBO / CSCV (16 blocks) | `model_lab/stats.py:85-108`; E1 robustness `strategy_lab/e1.py:1699-1716` | implemented, tested, research-only | No | test_model_lab | |
| Random-entry baselines (6 variants) | `backtest/random_baseline.py:42-219`; `entry_gate.py:221-315`; `model_gate.py:351-384`; `model_lab/baselines.py:74-118`; `signal_fusion/evaluation/baselines.py:48-127`; `strategy_lab/baselines.py:95-151` | implemented, tested; the `entry_gate` variant is integrated (trainer publication) | Indirectly: the model gate | test_entry_gate 29, test_strategy_lab 17 | |
| Scoring rules, calibration; non-inferiority (Q3 only) | `signal_fusion/evaluation/scoring.py:47-186`; `findings.py:467-500` | implemented, tested, research-only | No | test_signal_fusion_evaluation | |
| Deflated Sharpe, White's Reality Check / Hansen SPA, stationary bootstrap, Romano-Wolf | none (grep) | **missing** | n/a | none | Described only in `docs/dev/model-research/C-evidence.md`. |
| Model gate at publication: ≥20 held-out entries, beats the 95th percentile of 1,000 same-wait random runs, drawdown ≤ random median | `entry_gate.py:317-360`; `model_gate.py:1-60, 255-331`; `pt_pattern_trainer.py:1419-1491`; thresholds `training_settings.py:31-45` | implemented, tested, integrated, operational | Yes: legacy mode (the thinker holds refused coins, `pt_thinker.py:684-707`) | test_entry_gate 29, test_mock_trainer_refusal 12 | Always on and fails closed. It gates only the legacy pattern model, not catalogue strategies. |
| Strategy authorisation by mode | `strategies/settings.py:201-206`; `pt_trader.py:1788-1806`; UI filter `strategy_settings_ui.py:53-62, 183-184` | implemented, tested, integrated, operational | Yes | test_strategy_lifecycle 18, test_strategy_settings_ui 16 | |
| Live switch: typed confirmation plus key check | `trading_mode.py:1353-1397, 1496-1546`; `trading_mode_ui.py:222`; File > Trading Mode (`pt_hub.py:2943-2945`) | implemented, tested, integrated, operational | Yes | test_trading_mode 64, test_coinbase_paper_gate 15 | |
| Per-trade human approval | `trade_proposal_approval.py` | implemented, tested, **not integrated** | No: nothing imports it | test_trade_proposal_approval 24 | |
| Credentials in the OS keyring | `pt_secrets.py:1-30` | implemented, tested, integrated | Yes | test_pt_secrets 22, test_credentials_* 50 | `pt_credentials.py` is used only by `pt_migrate.py`. |
| Read-only local API | `pt_api_server.py:93-333`; off by default (`pt_hub.py:570-572`) | implemented, operational (opt-in) | No order routes | nv | |
| LLM providers: ollama, openai, anthropic, nvidia; preferred plus fallbacks | `llm_providers.py:343-545`; `llm_settings.py:85-95` | implemented, tested, operational | — | test_llm_providers 17, test_llm_settings_ui 10 | Raw HTTP: the declared `openai` package is never imported. |
| LLM entry hook (confirm/veto) and LLM signal gate | `llm_gate.py:1-57`; `pt_trader.py:1350-1369, 3000-3004` | implemented, tested, integrated | Entries only. Default `log_only`, which changes nothing; fails open | test_llm_gate 19 | A signal may confirm or veto only after it passes `entry_gate` on paper signals. |
| Entry assessment (SIG-004) | `signal_fusion/settings.py:23-35`; `pt_trader.py:1371-1420, 3013-3024` | implemented, tested, integrated (log-only) | Off or Log only; no effect on any order | test_signal_fusion_live 7, test_entry_checks_ui 5 | Veto/On are deferred (`settings.py:30-35`). |
| Research reports | `docs/dev/sr1_e1_report.py`, `sig4_dev_report.py`, `model_lab/batch.py` report.md | implemented, research-only | No | partial | Markdown, generated by scripts. |
| Hub windows (operational) | Settings, 8 tabs (`pt_hub.py:7800-8219`); Strategy (`7841-7855`); Risk (`7856-7860`); Check models (`7935`); Compare models (`7941`); Observation (`8129`); LLM Providers (`8139-8147`); bottom tabs `3634-4327` | implemented, tested, operational | — | test_hub_layout 38, test_settings_tabs 22 | Display-only or simulated: Institutional Trading (`institutional_trading.py:281-282`, `asyncio.sleep` fills) and Performance Attribution. Portfolio Analytics has been **removed** (`archive/legacy/portfolio_analytics.py`). |
| Scheduler | Tk `after()` timers in the hub: auto-retrain on by default every 6 h (`pt_hub.py:565-567, 5484-5577`); Order Management monitor; LLM auto-refresh (off at start) | implemented, tested, operational **only while the hub is open** | Retrain only | test_retrain_schedule 17 | No OS scheduler or service, and no scheduled data, research or observation jobs. `pt_process_manager.py` is dead. |
| Training window (30d…3y/all) | `pt_pattern_trainer.py:116, 175-178, 189, 308` | implemented, tested; **not in the UI** | Default 3y | test_trainer_every_bar 9 | The hub passes no window (`pt_hub.py:5368`); it can be set only by env or CLI. This conflicts with the owner's UI-not-CLI rule. |

---

## 2. Dependency map (module level)

```
pt_hub (process; starts the others with Popen, pt_hub.py:730-734, 3958-3988)
  ├─ strategies.settings/descriptions, trading_mode, position_sizing, risk_state,
  │  order_management_*, market_data.timeframes, pt_exchange_abstraction  (top level)
  ├─ lazy UI: strategy_settings_ui → strategy_lab_ui → strategy_lab.{runs,simulate,windows,evidence}
  │           model_lab_ui → model_lab.{batch,catalogue,walkforward,series} + strategy_lab.windows
  │           observation_ui → strategy_lab.observation
  │           entry_checks_ui / entry_assessment_view → signal_fusion.{settings,live}
  │           backtesting_gui → backtesting_engine (legacy)
pt_trader (process)
  ├─ signal_engine → strategies.{factory,runner,catalogue,settings} → market_data.candles
  ├─ strategies.base/settings; strategies.catalogue (lazy :1047)
  ├─ signal_fusion.live/settings (lazy :1386-1413, log-only)
  ├─ llm_gate (lazy :1354) → entry_gate, llm_signals → backtest.engine.CostModel (lazy, llm_signals.py:151)
  └─ position_sizing, risk_state, pt_risk, pt_cost, trading_mode, paper_coins, market_data.listing
pt_thinker (process) → model_store, pattern_model (one constant), market_data.{listing,candles,runner_history}, pt_data_provider
pt_pattern_trainer (process) → market_data.*, entry_gate, model_gate, training_settings, model_store, pattern_model

strategy_lab → model_lab (batch._seal, stats, features, series, catalogue.Look, walkforward), signal_fusion (replay, bootstrap,
               baselines, findings, labels, meta, volatility), strategies, market_data
model_lab    → entry_gate, model_gate, pt_pattern_trainer, pattern_model, market_data, pt_exchange_abstraction
signal_fusion→ model_lab.features/stats (lazy), backtest.engine (labels.py:92), strategies, position_sizing, market_data
signal_audit → market_data, pt_exchange_abstraction only; imported by nothing in app/ (docs/dev scripts only)
backtest     → strategies, market_data, pattern_model, pt_exchange_abstraction
```

- **The trader does not import** strategy_lab, model_lab or signal_audit, at module level or lazily. It does import signal_fusion (log-only) and, through llm_gate → llm_signals, `backtest.engine.CostModel`.
- **model_lab is not on any trading path.** The dependency runs the other way: model_lab imports the trainer's modules. It reaches the hub only through `model_lab_ui`.
- strategy_lab sits on top of model_lab and signal_fusion. A change to either changes E1's code hash (`strategy_lab/experiment.py:58`).

---

## 3. The data layer

| Topic | Finding | Evidence |
|---|---|---|
| Exchanges with candles | Binance (`/api/v3/klines`, 1000 per page), Coinbase Exchange (`/products/{p}/candles`, 300 per page), Kraken (`/0/public/OHLC`, latest 720 bars only), KuCoin (`/api/v1/market/candles`, 1500 per page). Only these 4 can be primary for market data. | `pt_exchanges.py:200-204, 968-998, 2048-2077, 421-453, 2842-2874`; `pt_exchange_abstraction.py:842-851` |
| Timeframes | Strategy timeframes 1m…1d; candle-only 1w (Monday 00:00 UTC). Native: Binance all; Coinbase 1m/5m/15m/1h/6h/1d; Kraken 1m/5m/15m/30m/1h/4h/1d; KuCoin 1m…12h, 1d. The others are built from the largest native divisor, complete groups only. | `market_data/timeframes.py:3-30, 55-60`; `resample.py:15-64` |
| Routing | Primary first, then the enabled exchanges in Settings order. The first exchange that can serve the whole range gives the series; series are never mixed. `df.attrs` records the exchange and pair. The trainer pins one exchange per run; the live engine does not pin. | `pt_multi_exchange.py:314-338, 503-518`; `candles.py:436-508`; `pt_pattern_trainer.py:553-587` |
| Cache location | `<cache>/candles/<exchange>/<PAIR>_<TF>.csv`. `<cache>` = `platformdirs.user_cache_dir("PowerTraderAI","SJackson")` or `$POWERTRADER_HOME/cache`. The pair is the exchange's own (BTCUSDT, BTC-USD, BTC-USDT, XBTUSD). | `candles.py:70-88`; `pt_paths.py:12-27, 110-153` |
| Cache format | CSV `open_time_ms,open,high,low,close,volume`, written to a temp file then `os.replace`, with no lock. Late listings get a `.start.json` record (re-asked after 30 days). Parquet is rejected. The old flat cache is moved once into `binance/`. | `candles.py:11-15, 91-133, 213-238, 511-541` |
| Refresh | Only bars before the first and after the last cached bar are fetched. Interior gaps and exchange corrections are never refetched. Merge = concat, dedupe keep-last, sort. | `candles.py:286-333` |
| Closed vs forming | Dropped at three layers: exchange layer, cache, signal engine (stale > 2 bars → HOLD `STALE_CANDLES`). The legacy runner uses a flat placeholder for the forming bar. The hub chart shows it (display only). | `pt_exchange_abstraction.py:1129-1136`; `candles.py:241-245`; `signal_engine.py:296, 305-318`; `runner_history.py:115-135`; `pt_hub.py:925-934` |
| Gaps | Reported in `df.attrs["report"]`, never filled. Treatment differs by consumer: the trainer and strategy_lab join across gaps; model_lab drops everything before the last gap over 24 h (`model_lab/series.py:32, 228-262`). | `candles.py:139-185`; `pt_pattern_trainer.py:519-542`; `strategy_lab/candidates.py:197-230` |
| Duplicates | Raise `CandleDataError` on read (no repair). Merges and connectors dedupe. | `candles.py:164-176, 327-331`; `pt_exchanges.py:2054-2077` |
| Delisting | Each connector reports `market_status`. `market_data/listing.py` caches it for 1 h (known) or 5 min (unknown); an unknown status never counts as "not trading". The per-coin `market_status.json` blocks buys. | `listing.py:15-17, 79-124`; `pt_trader.py:1160-1179` |
| Other data | **Fetched and used in decisions:** L1 bid/ask only. **Display only:** order book, 24h ticker. **Research only:** daily quote volume. **Not fetched anywhere:** trades/ticks, funding, open interest, on-chain, news/sentiment. | `trading_mode.py:462-480`; `real_time_market_data.py:49-50, 385-416, 670-800`; `signal_audit/ranking.py:184-221` |
| Data defects | E1 `first_cached` looks for `"{coin}-USD"` files (`strategy_lab/e1.py:532-545, 606`), but cache files use each exchange's pair (`candles.py:477-489`). Only Coinbase caches match: latent. `pt_data_provider` invents klines (`:220-245`): dead callers only. | as cited |

---

## 4. Python environment

The launcher runs `.venv\Scripts\python.exe app\pt_hub.py` (`start_powertrader.bat:16`). `install_dependencies.py:26-47` installs the **root** `requirements.txt`; CI installs **`app/requirements.txt`** (`ci-cd.yml:111`). Both venvs are Python 3.13.15 with `include-system-site-packages = false`.

| Package | root req / root opt | app req / app opt | `.venv` installed | Imported by app code | Flag |
|---|---|---|---|---|---|
| numpy | ≥1.24 / – | ≥1.24 / – | 2.5.3 | widely | ok |
| pandas | ≥2.0 / – | ≥2.0 / – | 3.0.6 | widely | ok |
| scipy | ≥1.11 / – | ≥1.9 / – | 1.18.1 | `signal_audit/stats.py:111-799`, `portfolio_optimizer.py:38`, `backtesting_engine.py:31` | the two files' bounds differ |
| **scikit-learn** | – / ≥1.3 | **≥1.5** / ≥1.3 | **NOT installed** | `model_lab/contestants.py:618-633`, `signal_fusion/meta.py:51` (lazy); dead `pt_neural_*` | **Mismatch.** Required by `app/requirements.txt`, but optional in the root file the installer uses. Compare-models trained contestants and F_P/F_PV cannot run in the owner's venv. |
| torch | – / ≥2.1 | – / ≥2.1 | not installed | `pt_neural_network.py:19-22` (guarded; dead module) | harmless |
| ta | – / ≥0.11 | – / ≥0.11 | not installed | `pt_neural_network.py:26` (dead) | harmless |
| lightgbm, xgboost, statsmodels, arch, hmmlearn, numba | not declared | not declared | not installed | none | none used |
| ccxt | ≥4.0 | ≥4.0 | 4.5.85 | **none** (connectors use raw `requests`) | declared but unused |
| PyYAML | ≥6.0.1 | ≥6.0.1 | **NOT installed** | `pt_config.py:16`, top-level import; only the dead `pt_integration` and `pt_testing` import `pt_config` | mismatch, no runtime effect today |
| aiohttp / aiofiles / aiodns | ≥3.9 / ≥23.2 / ≥3.2 | same | 3.14.4 / **missing** / **missing** | `pt_async_patterns.py:8-9` (dead) | mismatch, no runtime effect |
| watchdog | – / ≥3.0 | – / ≥3.0 | not installed | `pt_config.py:20` (guarded) | harmless |
| openai, kucoin-python, krakenex, beautifulsoup4, websockets, PyNaCl | declared | declared | installed | **none** | declared but unused |
| python-binance | not declared | not declared | 1.0.37 | none | installed but undeclared |
| matplotlib, seaborn, sqlalchemy, flask(+cors) | declared | declared | 3.11.2, 0.13.2, 2.1.4, 3.1.3 | hub charts; legacy GUIs only (seaborn); `order_management_db.py`; `pt_api_server.py` | ok |
| pytest | commented out | commented out | not installed | tests | CI adds it; `.venv` cannot run the suite |

`app/.venv` also exists. It has the same package set (minor version differences: openai 3.24.0, sqlalchemy 2.1.3) and the same gaps.

---

## 5. Duplication and overlap (unify, don't rebuild)

| Job | Implementations | Recommendation input |
|---|---|---|
| Candle loading | ~10 loaders: `exchange_candles`/`get_candles` (canonical, `candles.py:248-508`); direct `ExchangeManager.candles` users (runner_history 30 s memo, hub 10 s memo, LLM, signal-audit cross-check); `model_strategy.cached_bars` (`:93-110`); `e1.first_cached`/`development_loader` (`e1.py:532-596`); trainer `_cached_range` (`pt_pattern_trainer.py:589-603`); signal-audit gz snapshots (`evidence.py:300+`); backtest `--candles-file`; fake `pt_data_provider` klines; legacy `backtesting_gui` CSV/random walk | One loader; four different gap rules today |
| Bar identity hash | `pt_pattern_trainer.candle_sha256` (`:605-619`), `model_lab.series.bars_sha256` (`:210-225`), `signal_audit.evidence.bars_sha256` (`:85`); the backtest CLI hashes the whole file instead | One function |
| `_connector(manager, name)`; exchange managers | `candles.py:544`, `signal_audit/ranking.py:224`, `real_time_market_data.py:454`; `pt_data_provider.py:44-64` builds a second MultiExchangeManager | |
| Single-coin trade simulation | `backtest/engine.py:134` `run_backtest`; `strategy_lab/candidates.py:128-255` `TradeTable` (re-implements its rules at zero cost, without the gap check); legacy `backtesting_engine.py:233` | Keep one engine |
| Legacy-exit replay | `model_gate.py:255-331` (trailing PM plus DCA, 100-unit account), used by model_lab and the trainer gate | Separate from catalogue exits |
| Portfolio replay | `signal_fusion/evaluation/replay.py:187` only (strategy_lab wraps it) | Already single: the base to build on |
| Live rule of the legacy model | `pt_thinker.py:929-990` inline vs `pattern_model.py:94-365` | Two copies |
| Random baselines | 6 variants (§1.9) | One baseline library |
| Holm / MDE / bootstrap | Holm: `model_lab/stats.py:53-62`, `signal_audit/stats.py:532-555`. MDE: model_lab, `entry_gate.py:700`, signal_audit. Block length: 28/56 d (`bootstrap.py:41-48`), 28·2^k (`e1.py:682-692`), Bartlett (`signal_audit/stats.py:379`) | One stats module |
| Trial ledgers and registries | `model_lab/trials.jsonl` (`batch.py:147-148`) vs `strategy_lab/trials.jsonl` (`experiment.py:79-80`): different schemas, overlapping `kind` names. Also signal-audit git rounds, signal-fusion artifact, observation segments. Committed copies in `docs/dev/{mh-batch-1,sig4-dev,sr1-e1,compare-9}/trials.jsonl` | One ledger |
| Sealing and code hashes | Sealing: `model_lab/batch.py:151-170` (reused by strategy_lab), `signal_fusion/artifact.py:46-56`, `signal_audit/registration.py:117`. Code-hash sets: 4, each covering different files (a code-hash gap, §5) | |
| Strategy and signal registries | `strategies/catalogue.json` (11); model_lab contestants (`rule.high20` ≈ STRAT-004, `rule.mom14` ≈ STRAT-005, `rule.btc50` ≈ OVL-REGIME, `rule.smaN` ≈ trend); signal-audit SIG-A/B; legacy GUI "MA Cross"/"RSI" | One catalogue |
| Cost models | `backtest/engine.py:40-51` CostModel (bps); `signal_fusion/evaluation/replay.py:99-110` Costs; `entry_gate.py:370-411` Fees; `llm_signals.py:150-157`; legacy commission; unused `pt_cost.CostManager` | One cost model, fed from `trading_fees` |
| Lockbox | `strategy_lab/windows.py:36-42` (fixed dates) and `model_lab/walkforward.py:107-141` (18 months before batch end) | |
| Features | RSI ×3 (LLM Wilder, legacy rolling mean; none in indicators.py); Parkinson ×2 (`model_lab/features.py:251-252`, `signal_fusion/volatility.py`); SMA ×3 | Feature library |
| Sharpe / KPIs | `backtest/kpis.py`, `backtesting_engine`, `portfolio_optimizer`, `pt_cost`, `pt_model_evaluation`, `pt_risk` | |
| Config, trainers, process managers, credentials | `pt_config` (YAML, dead) vs `pt_settings_manager`; `pt_pattern_trainer` vs mock `pt_trainer`/`pt_trainer_standalone` (refused by `trainer_guard.py:1-30`); hub Popen vs dead `pt_process_manager`; `pt_secrets` vs `pt_credentials` (migration only); root vs app requirements files | Delete or merge |

About 12 modules are imported by nothing outside tests: `pt_process_manager`, `pt_neural_processor`, `pt_neural_network`, `pt_model_evaluation`, `pt_caching_system`, `pt_integration`, `pt_async_patterns`, `pt_circuit_breaker`, `pt_testing`, `pt_database_manager`, `pt_gui_integration`, `trade_proposal_approval`, `demo_paper_trading`, `start_powertrader`.

---

## 6. The ten biggest gaps against the target pipeline

| # | Stage | Gap | Evidence |
|---|---|---|---|
| 1 | Data acquisition | Candles plus L1 quotes only, from 4 exchanges (Kraken capped at 720 bars). No trades, funding, OI, on-chain or news. No scheduled backfill. Interior gaps and corrections are never refetched. The only point-in-time universe is in the signal audit. | §3; `candles.py:286-304`; `real_time_market_data.py:49-50` |
| 2 | Feature engineering | No feature library or store. Live strategies use only `indicators.py`. The 26 research features (`model_lab/features.py`) cannot reach the trader. RSI, Parkinson and SMA are duplicated. | §1.2, §5 |
| 3 | Signal → strategy bridge | Nothing from research can reach trading. No signal-fusion artifact is registered; entry assessment is Off or Log only; STRAT-003/004/005 and OVL-REGIME are research-only. Promotion needs a hand edit of `catalogue.json` (no UI). No mean-reversion, relative-strength or cross-sectional strategy. | `signal_fusion/artifact.py:14`; `signal_fusion/settings.py:27-35`; `catalogue.py:52-53` |
| 4 | Portfolio construction | One strategy for all coins. Entries are 1% per coin in coin-list order. No exposure, volatility or correlation sizing. The optimiser writes only Long-term Holdings targets. Positions are keyed by coin, with no ownership. | `pt_trader.py:2147-2160, 2950-2968`; `portfolio_optimizer_gui.py:1136-1175` |
| 5 | Risk assessment | The halt ends the trader loop with no protective exits (stubs at `pt_risk.py:383-401`). The daily-loss limit thread is never started (`pt_risk.py:112-117`). The circuit breaker is unimported. Manual orders bypass the coin caps. | §1.6 |
| 6 | Execution | Market orders only; live only on Binance and Coinbase (Coinbase Phase 0 never run). No slippage, size-impact or partial-fill model in paper or research beyond fixed bps. | `pt_exchanges.py:692, 2225`; `RUN-LOG-live-1.md:16`; `trading_mode.py:562-590` |
| 7 | Performance evaluation | The portfolio backtester joins trades across exchange halts (N17 in A2, `candidates.py:197-230`). The legacy Backtesting tab runs on a random walk. Real and paper books show only realised and unrealised profit and "since start": no per-strategy Sharpe, drawdown or attribution. | §1.8 |
| 8 | Experiment registration and statistics | No single trial ledger (2 JSONL schemas, git rounds, artifact). Trial counts feed no correction. Deflated Sharpe, White RC/SPA, stationary bootstrap and Romano-Wolf are missing. The lockbox final check is not implemented (`model_lab/batch.py:38, 115`). Code hashes miss `strategies/` (model_lab) and the exchange layer (strategy_lab). E1 still holds the pre-fix STRAT-005 results. | §1.9, §5 |
| 9 | Scheduler | Tk timers inside the hub only (auto-retrain 6 h, Order Management monitor). Nothing runs with the hub closed. No scheduled data refresh, research batch or observation job. The training window is not settable from the UI. | `pt_hub.py:565-567, 5484-5577, 5368` |
| 10 | Paper-portfolio isolation | One process-wide paper book ($10k singleton), shared with Order Management (`trading_mode.py:1036-1044, 1293-1350`). No per-strategy or per-experiment paper accounts, and no parallel paper traders (one trader process). | `pt_hub.py:730-734`; `signal_engine.py:81` |

Also blocking, though not a pipeline stage: the owner's `.venv` lacks scikit-learn (§4), so the in-app model lab cannot run its trained contestants.

---

## 7. `B-architecture-assessment.md` (written at cdae9c9) checked against e6b96ca

| B claim (section) | Now | Evidence |
|---|---|---|
| Catalogue has no status, research refs or data requirements (§1, §3.2, §9.6) | **Out of date.** `authorisation`, `research_refs` and `data_requirements` exist and are enforced per mode | `catalogue.py:12-18, 40, 56-61, 198-229`; `pt_trader.py:1788-1806` |
| Families only trend/risk_overlay/model (§3.2) | **Out of date.** breakout, momentum and regime were added; mean_reversion and relative_strength are declared without classes | `catalogue.py:45-54` |
| Overlay `allow_entry` sees no candles; no regime gate possible (§1, §3.3, §9.4) | **Out of date.** `context_needs` plus `allow_entry_in`; OVL-REGIME, also in the live engine | `runner.py:18-24, 160-173`; `overlays.py:170-200`; `signal_engine.py:324-327` |
| Strategies STRAT-000..003 only (§1, §3.4) | **Out of date.** STRAT-004 Donchian and STRAT-005 TS-momentum (research) | `breakout.py:38`; `momentum.py:41` |
| Every main strategy except a model one is selectable (§9.6) | **Out of date.** Research entries are not offered for paper/live | `strategy_settings_ui.py:53-62, 184` |
| Trade records carry no strategy id (§9.9) | **Partly out of date.** Rows carry strategy_id, version, params sha, timeframe and overlays; positions are still keyed by coin | `pt_trader.py:1036-1064` |
| Model lab has no GUI (§1, §5.2, §9.7) | **Out of date.** Compare models window | `model_lab_ui.py:385-401`; `pt_hub.py:7941` |
| No window runs a catalogue backtest or compares results (§1, §6, §9.7) | **Out of date.** Run a backtest / Compare results / Model evidence | `strategy_settings_ui.py:575-600`; `strategy_lab_ui.py:192, 586, 632` |
| No portfolio backtest of a catalogue strategy (§9.2) | **Out of date.** | `strategy_lab/simulate.py:111-169`; `runs.py:134-247` |
| Signal-fusion opportunities STRAT-001 at 1h only (§1, §5.3, §9.1) | **Partly out of date.** `labels.py:35` is unchanged, but it is generalised through `strategy_lab.models` | `strategy_lab/models.py:16-21, 64-71` |
| Amounts in USD; nothing converts GBP (§5.3) | **Out of date.** Declared GBP→USD rate | `strategy_lab/simulate.py:33-38` |
| Replay signature at `replay.py:150-162` (§5.3) | Moved to `:187` and extended (mark_s, cooldown, halt_exposure) | `signal_fusion/evaluation/replay.py:41-54, 187` |
| Model lab scores models only under legacy exits; batch has no strategy field; hash excludes `strategies/` (§5.2, §9.3) | Still true within model_lab. Lab probabilities are now applied to catalogue trades by E1 family M | `model_lab/replay.py:1-60`; `batch.py:104-111`; `strategy_lab/models.py:92` |
| Lockbox final check not implemented (§5.2) | **Still true** | `model_lab/batch.py:38, 115` |
| Backtester one coin, no minimum/budget/halt; KPIs lack return per capital-day; no initial-balance flag (§5.1) | **Still true** for `backtest/` | `backtest/engine.py:1-24`; `kpis.py:12-24`; `cli.py:368-406` |
| Market data: one exchange per series, closed bars, gaps reported, CSV re-read per call (§5.4) | **Still true** | `candles.py:213, 281, 436-508` |
| One strategy/timeframe/overlay set per trader; one process; catalogue mode skips DCA/trailing (§4.1) | **Still true** | `signal_engine.py:81`; `pt_trader.py:2622-2680` |
| Sizing 1%, minimum raise, coin cap; halt ends loop, RiskManager close is a log line (§4.3, §9.10) | **Still true** | `position_sizing.py:24-33`; `pt_risk.py:383-401`; `pt_trader.py:3129, 3152` |
| Paper: one $10k account shared with Order Management, top-of-book fills, no slippage (§4.4, §9.8) | **Still true** | `trading_mode.py:562-590, 1036-1044, 1293-1350` |
| FDS-LIVE-001 live guards D1-D10; Phase 0 not run (§4.5) | **Still true** | `trading_mode.py:1353-1397`; `RUN-LOG-live-1.md:16` |
| Legacy Backtesting Framework tab on synthetic/file data (§1, §6, §10) | **Still true** | `backtesting_gui.py:221-225, 666-690` |
| No training-window field in Settings > Training (§6) | **Still true**, and the hub passes none | `pt_hub.py:7868-7960, 5368` |
| Neural DCA trigger and display disagree; `paper_mode_balance` unread (§10) | **Still true** | `pt_trader.py:2473-2479` vs `2813-2818`; `pt_hub.py:590, 2822` |
| No coin-ranking strategy (§9.5) | **Still true** | `strategies/base.py` |
| FDS-121/122/123/129 spec files never committed (§7) | **Still true** | `docs/dev/specs/` listing |
