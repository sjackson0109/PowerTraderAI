# FDS-SIG-004 — Price-Volume Signal Fusion, Confidence and Volatility Assessment

**Issue:** none yet. Raise "Assess entries with price, volume, confidence, volatility and liquidity, behind the existing controls" and link it here.
**Target repo:** `sjackson0109/powertraderai`
**Branch:** this spec is on `docs/fds-sig-004`, cut from `main` at `e0d837a` (PR #228 merged). Each phase is built on its own `feat/sig4-<letter>-…` branch, cut from `main` after the step before it is merged (§8.2).
**Recommended model:** Claude Opus 5.5, effort high, for phases A to D (statistics, look-ahead, the replays). Sonnet 5.5, effort high, for phase E (the hook, Settings and the table).
**Run log:** `docs/dev/RUN-LOG-sig4-1.md`, from phase A.
**Status:** draft for the owner's review.
- Revision 1 (2026-11-07, `64b0ea5`): the first proposal.
- Revision 2 (2026-11-07, `ca151be`): revised after an independent review of revision 1. §0.1 answers the review finding by finding.
- Revision 3 (2026-11-07): three final corrections from the same review: the placebo's timing, separating relative value from economic viability, and the liquidity approximation's error bound. §0.2 lists them.
- Nothing is implemented. This document changes no code, trainer, strategy, runner, trader or other spec, and it registers nothing.
- The changes it needs in FDS-MH-001 are proposed as exact text in Appendix A, to be applied by their own PR before FDS-MH-001's phase C (§8.2).
- §10 lists the decisions, each with its status and a recommended answer.

**Depends on:**
- FDS-SIG-001 and FDS-SIG-002: the signal audit and round one's candidates.
- FDS-MH-001: the multi-model harness. Phases A and B are merged; C, D and E are not built.
- FDS-MX-001: market data through the exchange layer.
- FDS-121: the strategy backtester.

**Evidence:**
- `docs/research/volume-module.md`: the volume research of 2026-11-05. It was exploratory: 296 subset tests, nothing registered in advance.
- `docs/dev/GATE-DIAGNOSTIC-2026-11-05.md`.
- `docs/dev/model-research/A-classic.md`, `B-deep.md` and `C-evidence.md`.
- The architectural review in §3. It is a code reading of `main` at `e0d837a`, done on 2026-11-07, with every claim given a file and line.

> **Read this first.** On today's evidence, expect most answers here to be "no", or "too little data to tell".
> - **Volume.** Adding volume to the pattern model changed nothing: hit rate p = 0.82, mean return p = 0.96 (volume research §6.5). No study read for that research shows a volume filter surviving retail fees.
> - **Power.** The harness can see a trading edge only if it roughly doubles profit per capital-day (gate diagnostic).
> - **Confidence.** A calibrated confidence built on weak signals will mostly sit close to the base rate.
> - **The default strategy.** An honest expected-value check would veto most STRAT-001 entries.
>   - On 3 years of Coinbase data, STRAT-001 makes −0.12% a trade before fees (n = 4,333).
>   - At the account's 0.50% taker rate that is about −1.1% a trade after fees. This is arithmetic from research §6.1's 0.40% and 0.60% columns, −0.92% and −1.31%.
>
> A design that reports these results is working. Nothing in this spec lets volume, confidence or volatility open a trade or make one larger.
>
> **Losing less is not making money.** A filter that loses less than its controls is reported as reducing losses. Only a result that clears §6.1's absolute requirements is called profitable.
>
> **Two existing limits are not fixed here** (§3.7): an entry raised to the exchange minimum can exceed the coin's budget, and STRAT-001 has no stop. No result of this spec makes a small account safer than it is today.

---

## 0. Responses to the independent review

### 0.1 Revision 2

The review supported the architectural direction, including D14's split of price-only from price-plus-volume models. It asked for eight refinements before any implementation is approved.

| # | Finding | What revision 2 does | Where |
|---|---|---|---|
| 1 | **Target separation.** An expected-value veto needs a probability and payoff model that fit the strategy's own exits, with costs applied once | **T1 and M are now separate events with separate uses.**<br>• T1 is a barrier event of the legacy exits, with the fees already inside its barrier. It serves only Q1's forecast test and never enters an expected value.<br>• M is "this strategy's trade ends with a profit after costs". It is the only probability a veto uses, with a payoff model built from the same strategy's trades.<br>• **Costs enter once,** through one multiplier that matches the backtester's fill accounting exactly | §5.3, §5.8.1 |
| 2 | **Unavailable assessments.** D8 must distinguish Off, Log only, missing predictive evidence and enabled protective limits | **Five cases, each with its own rule:**<br>• Off and Log only never change an entry.<br>• A missing predictive input fails open, recorded.<br>• An enabled protective limit (the volatility shrink, the participation cap, the spread cap) fails closed: the entry is skipped, with the reason shown.<br>• No blanket exception handler | §5.8.3, D8 |
| 3 | **Feature history.** The 20-day warm-up clashed with the 30-day and 50-day features | **Revision 1's warm-up was wrong.**<br>• The predictive part needs 1,224 closed hourly bars, for P's 50-day features. v1 needs 744 and v2 needs 481.<br>• Now defined: complete bars, gaps, absent and zero-volume hours, late listings, Kraken's 720-bar limit, and a venue compatibility test | §5.2.1–§5.2.3 |
| 4 | **Calibration acceptance.** "The interval contains the ideal value" rewards imprecision | **Replaced by equivalence bounds.**<br>• The 90% interval must lie inside pre-registered tolerances: intercept ±0.10 logit, slope 0.80 to 1.20.<br>• At least 200 events and 200 non-events.<br>• Three outcomes: within tolerance, miscalibrated, not assessable.<br>• The planned precision is checked by simulation before registration.<br>• Calibration stays strictly out of fold, with proper scoring rules | §5.5, §6.2, D16 |
| 5 | **FDS-MH-001 amendment governance** | **Batch 1 is preserved exactly,** and its 8 timing-run trials stay.<br>• The pair and the placebo go in a new batch, PV-1, declared now with its own keys, K, seeds and dates, before any trained contestant has been scored anywhere.<br>• Exact amendment text is in Appendix A, applied by its own PR before phase C.<br>• Every earlier exposure to the data is listed.<br>• R3, R3s and the portfolio replay move out of FDS-MH-001 into this spec, because they concern STRAT-001's exits | §6.4.1, §6.5, §7, §8.1, Appendix A |
| 6 | **Statistical procedures** | **One block scheme for every test:** circular blocks of 28 calendar days, doubled by a fixed rule if trades run long.<br>• The paired forecast test, the placebo (5 offsets, never reading held-back bars) and R3 are now specified down to the formula.<br>• R3 runs in a portfolio replay with the trader's sizing, budget, minimum, one trade per coin and free cash. It vetoes only assessable, eligible opportunities, per coin | §6.0, §6.1, §6.3 |
| 7 | **Forward-window independence** | **Phase E's live log is never an input to phase D's analysis,** which uses refetched candles and frozen code.<br>• The live hook runs only the registered artifact.<br>• Nothing outcome-linked is computed or shown during the window.<br>• Everything an observation could influence is frozen at registration, and any change cancels the window | §6.4.3, §6.6 |
| 8 | **Small-capital safety** | **Recorded as existing limits that this spec does not resolve:**<br>• the minimum raise above the coin budget;<br>• no stop on STRAT-001;<br>• a halt that stops exits too.<br>A new consequence is also recorded: where 1% of the account is below the minimum, the shrink acts as a veto | §3.7, §5.6, §11 |

**Also corrected in revision 2:**
- **§3.1:** STRAT-001 enters only when ADX ≥ 20, which revision 1's wording blurred. It fires once per fresh cross (`strategies/trend_crossover.py:16-27`).
- **§5.7:** revision 1 said "a $100 paper account". That was the gates' 100-unit replay account. The app's paper account starts at $10,000 by default (`trading_mode.py:1044`), and this spec does not read the owner's account.
- **Rule 4:** features come from the candles the runner already reads, primary first. The spread and the fees come from the venue that prices the order.
- **D10:** the predictive veto stays right after the LLM hook. The protective part moves to right after sizing, so it checks the amount the order will actually have.
- **D6:** the single "Veto and shrink" mode is split into four settings, one for each part.
- **The research's chosen rule** (same-hour relative volume above 1.5×) is now in the confirmation family. Before, it was tested outside any family.
- **§7:** the FDS-MH-001 amendments are cut to what Q1 needs inside the harness. The rest is this spec's own code.

### 0.2 Revision 3

The review accepted revision 2's direction and supported D14, subject to three corrections. Revision 3 makes only those.

| # | Correction | What revision 3 does | Where |
|---|---|---|---|
| 1 | **The placebo's timing.** Revision 2 moved V forward and wrapped it round the development period, so a row could carry volume from a later time | **The placebo is now a lag.**<br>• At hour t it uses the same coin's V from hour t − δ_j, with δ_j between 160 and 170 days and never a whole number of days.<br>• There is no wrap. A row whose lagged hour has no V has no placebo, and is dropped from every model in the comparison, so the rows stay paired.<br>• Tests check that no row reads anything after its own time, at the series' start, across gaps and at fold boundaries | §6.1, Appendix A (AM1-2, AM1-7, AM1-8) |
| 2 | **Relative value is not economic viability** | **Three findings are kept apart:**<br>• F1, volume improves forecasts;<br>• F2, volume improves results or reduces losses against matched controls;<br>• F3, the approach as it would trade is profitable after fees.<br>F3 has its own requirements: at least 100 trades, a profit above 0 that is significant per capital-day, a profit in both halves of the window and without the best coin, and a drawdown below the halt level, with capital use and drawdown reported. The predictive veto can be turned On only with F3. A filter that loses less is described as reducing losses | §6.1, §6.5, §6.7, §5.8.3, §8.3, D18 |
| 3 | **The liquidity approximation's error bound** | **Relative error is defined against the true traded value.** Its bound is the least one the bar's own OHLC supports: max((TP − L)/L, (H − TP)/H). Revision 2's (H − L)/TP holds only when the estimate is the denominator, and can fail for the true one. The claim that finer bars give a smaller error is removed. Hand-worked cases cover a VWAP near the low and near the high, a flat bar, zero volume and invalid prices | §5.2, §5.7, §12 |

## 1. Objective

Answer three questions with evidence, and define one design that combines the answers without weakening any existing control.

1. **Q1: does volume add predictive value beyond price?**
   - Compare a price-only model with the same model plus volume, with everything else held the same.
   - Report three findings separately (§6.1):
     - **F1:** whether volume improves forecasts;
     - **F2:** whether it improves trading results, or reduces losses, against matched controls;
     - **F3:** whether the resulting approach makes money after fees.
   - F2 never implies F3.
2. **Q2: how should confidence be calibrated?**
   - Define a confidence as a calibrated probability of a stated event.
   - Measure it with proper scoring rules.
   - Allow it to affect a decision only when it is shown to carry information beyond the base rate, and to be calibrated within stated tolerances.
3. **Q3: how should volatility and liquidity influence trading decisions?**
   - Volatility: as a forecast input and a risk-based size reduction, never as an entry signal.
   - Liquidity: as a cost and a hard limit, never as a signal.

**The design** is one assessment per entry, in two parts:
- **a predictive part,** which may only **veto** an entry that the active strategy or the thinker already wants;
- **a protective part,** which may only **skip** or **shrink** it.

Every existing control still applies after the assessment, in today's order.

**What this spec produces:** a design, an evaluation protocol and a staged plan. It wires nothing to trading. As with FDS-SIG-001 §14 and FDS-MH-001 D10, enabling any effect is a later decision for the owner (§8, phase F).

**It runs alongside FDS-SIG-001.** It develops and evaluates its design while FDS-SIG-001's research window runs, without touching that window (§6.4.4).

## 2. Rules

1. **Only veto or shrink.**
   - Volume, confidence, volatility and liquidity never open a trade or make one larger.
   - They never delay or block an exit, never trigger or change a DCA buy, and never move a stop.
   - They may only veto, skip or shrink an entry the existing path already wants.
2. **Existing controls stay.** Every existing control applies after the assessment, unchanged and in today's order (§3.1).
3. **One implementation.**
   - The harness, the backtester and the trader call the same assessment code, and its files are hashed into the record of the model in use.
   - When the hash differs from the evaluated one, the predictive part counts as unavailable (§5.9).
4. **Exchange-neutral.**
   - Every input has one definition on every connector, read through the exchange layer (FDS-MX-001).
   - Features come from the candles the runner already reads for the coin: the primary exchange first, then the fallbacks. The live spread and the fees come from the venue that prices the order.
   - Nothing that only some connectors offer is an input.
   - A model runs on a venue other than the one it was evaluated on only after that venue passes the compatibility test (§5.2.3).
5. **Evidence first.**
   - An effect is enabled only after its evidence has passed on data no one had looked at.
   - Every earlier look at the data is recorded (§6.4.1), as FDS-MH-001 §5.7 does for contestants.
6. **A confidence is a calibrated probability** of a declared event, or it is not called a confidence.
7. **Simulations run locally, as 10 seeded runs,** reported pooled and per run (owner, 2026-11-06).
8. **Settings, not files.**
   - Every option is reachable from Settings.
   - In-app text states facts only: no spec names and no design caveats.
9. **Off by default.** Every new setting defaults to off, and saved settings keep their meaning.
10. **Fail safe by kind** (§5.8.3).
    - A missing input never silently removes a protective limit the owner has turned on. That entry is skipped.
    - A missing input to the predictive part removes only the predictive veto, which returns the entry to today's path.
11. **No retrospective change.**
    - A declared batch, a registration and a recorded trial are never edited.
    - A change makes a new batch or a new registration, and the old one stays on record (§8.1).

## 3. The review: three components today (`main` at `e0d837a`)

File references are relative to `app/`.

### 3.1 One entry, end to end

| Step | Legacy chain (`strategy.engine = "legacy_neural"`) | Strategy catalogue (the default: STRAT-001, 1h, no overlays; `pt_settings_manager.py:131-138`) |
|---|---|---|
| Signal | The thinker matches the last closed bar's body % against the trainer's memories, per timeframe (`pt_thinker.py:929-931, 1033`). It writes long and short counts, 0 to 7 (`pt_thinker.py:1521`). An entry needs long ≥ `trade_start_level` (3) and short = 0 (`pt_trader.py:2894-2905`) | `SignalEngine.decide` runs STRAT-001 on the last closed 1h bars (`signal_engine.py:261-330`).<br>• **Its defaults:** TEMA 12 against TEMA 48.<br>• **When it enters:** on the first closed bar on which the fast average has stayed above the slow for 2 further bars after a fresh cross, and only when ADX(14) ≥ 20.<br>• **It fires once per cross,** never on a stale state, so a vetoed entry is not offered again on the next bar (`strategies/trend_crossover.py:16-27, 55-73`; `strategies/catalogue.json:29-37`) |
| Evidence gate | The entry gate, at training time: a random-entry baseline, scored by return per capital-day. A model is published only on a pass (`pt_pattern_trainer.py:1615-1623`) | **None.** `signal_engine.py` and `strategies/` import neither `entry_gate` nor `model_gate` |
| LLM hook | Both modes, after the signal and before sizing (`pt_trader.py:2908-2913`). It can only confirm or veto, never create. Any exception lets the entry go ahead (`pt_trader.py:1327-1338`). The default mode is `log_only` (`llm_settings.py:75`) | same |
| Size | 1% of the account (Start allocation). Below the exchange's minimum entry it is raised to that minimum: the minimum order plus room for the spread, two taker fees and a 2% margin (`position_sizing.py:74-106`; `pt_trader.py:2017-2037`) | same |
| Risk check | The coin budget (Max per coin 10%) caps a buy, except that the minimum entry is always allowed, even above the budget (`pt_trader.py:1680-1689`).<br>• **Drawdown levels:** 3%, 5% and 8% (`pt_settings_manager.py:123-127`).<br>• **At 8% trading halts,** and a halt ends the trader's loop: no order of any kind, exits included, until Resume trading in Settings > Risk (`pt_trader.py:3016-3025`) | same |
| Placement | Pinned to the mode the trader started in. Preview places nothing. Paper fills pay the taker or maker rate of the venue whose quote priced them (`trading_mode.py:579-583, 773-795`) | same |
| Exits | DCA buys of ×2 at −2.5%, −5%, −10% and further levels. The trailing profit margin starts at +5% (+2.5% after a DCA) with a 0.5% gap (`pt_trader.py:2593-2735`) | STRAT-001's exit when the fast average falls below the slow. DCA and the trailing margin are skipped (`pt_trader.py:2591`). **No stop:** the default overlays are none |

### 3.2 What the decisions use

| Information | Used today | Where |
|---|---|---|
| Price | Thinker: open and close only. Trainer: open, close, high and low. STRAT-001: close, plus high and low for ADX | `pt_thinker.py:494-503`; `pt_pattern_trainer.py:538-545`; `strategies/trend_crossover.py:45-73` |
| Volume | **No decision reads candle volume.**<br>• The runner's rows carry it, but the thinker never reads it: `pt_thinker.py` contains no "volume".<br>• The trainer only hashes it.<br>• No catalogue strategy uses it.<br>• The one route is the 24-hour volume in the LLM's prompt, which matters only in the LLM's confirm and veto modes | `market_data/runner_history.py:99-114`; `pt_pattern_trainer.py:605-617`; `llm_research_engine.py:254` |
| Confidence | **None is calibrated, and none changes a size.**<br>• The thinker's counts and STRAT-001's ADX are thresholds.<br>• The LLM's 0–100 confidence is self-reported, and is only shown and filtered on.<br>• `Signal` and `Decision` have no confidence or size field.<br>• A harness contestant returns 1, 0 or −1 per hour.<br>• `pt_neural_processor.py` has a confidence-weighted combination, but nothing imports it | `llm_signals.py:94-101`; `llm_gate.py:344-368`; `strategies/base.py:37-42`; `strategies/runner.py:133-143`; `model_lab/contestants.py:45-47` |
| Volatility | **Sizing is a fixed percentage.**<br>• ATR appears only in the opt-in STRAT-002 and OVL-ATR.<br>• `pt_risk`'s volatility limits sit in a monitoring loop that the app never starts | `position_sizing.py:91-106`; `strategies/indicators.py:110-171`; `strategies/overlays.py:230-252`; `pt_risk.py:116-121` |
| Liquidity | **Only the exchange minimum and the quote's spread, both in the entry floor.**<br>• Fees appear in that floor and in paper fills.<br>• Neither the trader nor paper fills model slippage. The gates use 0.05% a fill.<br>• No volume or order-book depth is used | `pt_trader.py:2017-2037`; `entry_gate.py:405-411` |

### 3.3 FDS-MH-001, the harness

**Built:** phases A and B (#226, #227).

**What it measures:**
- It scores trades only. The deciding score is return per capital-day, compared with R1 (the same waits in random order) and R2 (the same schedule moved by at least 160 days).
- It applies a Benjamini-Hochberg screen and Holm at 5%, computes PBO, and reports the smallest detectable edge.

**Gaps that matter here:**
- **No forecast is ever scored.** No application file computes a log loss, a Brier score or a calibration.
- **No contestant reads volume.** The daily series keeps each day's open time and close only (`model_lab/series.py:161-200`).
- **Phase C as specified cannot answer Q1.** Its 26 planned features include one volume feature, "log of 24-hour volume over the 30-day daily mean" (FDS-MH-001 §5.5), and no price-only twin is planned.
- **No paired test of two contestants.** `_on_shared` puts a trained contestant beside the best rule on shared hours, as a point comparison only (`model_lab/batch.py:474-485`).
- **Regimes:** results are shown per coin and by BTC's 90-day trend, but not by volatility or liquidity.
- **Drawdown:** "worst drawdown" is the worst single trade's fall below its own cost, not the drawdown of an equity curve (`entry_gate.py:100-105`).
- **Batch membership:** `BATCH_1` is every key in the catalogue (`model_lab/catalogue.py:60`). Adding a contestant to the catalogue would therefore add it to batch 1 in code.
- **Not built yet:** the lockbox opening, and phases C, D and E.

### 3.4 FDS-SIG-001 and FDS-SIG-002, the audit (merged `e0d837a`)

- **The test:** a pre-registered test, per coin and per timeframe, of whether a rule calls the next bar's direction better than the best constant.
  - Holm over the family, F = 76 for round one.
  - Fresh windows only, and a confirmation round.
  - Each round is run from its own frozen worktree (FDS-SIG-001 §12.1).
- **Round one:**
  - SIG-A, the sign of Chaikin Money Flow over 20 bars. It is a volume rule.
  - SIG-B, BTC's one-bar lead.
  - It is not registered, and decisions 1 to 6 are open.
- **The order is fixed (FDS-SIG-001 §14):**
  1. directional skill is CONFIRMED;
  2. then a trading-result test under a separate spec.
- **What it answers:** "does this one rule predict the next bar's direction?" It does not answer:
  - whether a rule adds anything to price information;
  - how to calibrate a probability;
  - how to size a trade.

  This spec covers those three.

### 3.5 Data through the exchange layer

| | Binance | Coinbase | Kraken | KuCoin |
|---|---|---|---|---|
| Base volume per bar | yes | yes | yes | yes |
| Quote volume per bar | sent, dropped by the connector | **not offered** | VWAP sent, dropped | turnover sent, dropped |
| Trade count, taker-buy volume | sent, dropped | no | count only, dropped | no |
| Bid/ask, order book | live only | live only | live only | live only |
| History | years | years | **latest 720 bars** (`pt_exchanges.py:198`) | years (some symbols from 2022-09-29) |
| Trading fees | the account's rate with a key, else the published default | the account's rate with a key, else the published default | public | the published default only |

- **No order-book or trade history is stored anywhere.**
- **The candle cache** keeps closed bars per exchange and tops them up (`market_data/candles.py:2-13`). It never stores the still-forming bar, and it is safe to delete (`market_data/candles.py:71`).
- **The shared market-data manager connects with empty credentials** (`pt_multi_exchange.py:486-490`), so its Coinbase fee falls back to the published 1.20% taker rate (`pt_exchange_abstraction.py:268-273`). The owner's account reads 0.50%.
- **The audit's market methods** (`spot_markets`, `daily_quote_volume`) are called on connectors directly, not through `ExchangeManager`. The audit is their only user today.

### 3.6 What the review found, and what the design does about it

| # | Finding | Design response |
|---|---|---|
| R1 | **The default path has no evidence gate.** Catalogue entries face none, and STRAT-001 shows no gross edge (−0.12% a trade, research §6.1) | The predictive veto is the first evidence-based check that could reach catalogue entries, once it has evidence (§5.8, §6) |
| R2 | **The gate tests the replica, not the thinker.** It replays `pattern_model`'s copy of the thinker's decision (`model_gate.py:206-252`), and the code hashed into a model's record leaves `pt_thinker.py` out (`pt_pattern_trainer.py:1157-1163`). In legacy mode, the gate does not test byte-for-byte what trades | Rule 3: one implementation, hashed (§5.9). Fixing R2 for the thinker is a separate follow-up (§11) |
| R3 | **No interface carries a probability or a size**: `Signal`, `Decision` and `Fitted` | A separate assessment record, with no change to the strategy interface (§5.8) |
| R4 | **The LLM hook is the one place both modes pass,** after their signal and before sizing | The predictive veto goes directly after it; the protective part goes directly after sizing (§5.8) |
| R5 | **The minimum-order raise can exceed the coin budget** | A shrunk entry below the minimum is skipped, never raised (§5.8.4). The raise of an unshrunk entry is unchanged and recorded as an existing limit (§3.7) |
| R6 | **Quote volume is missing on Coinbase.** Base volume is on every connector; per-bar quote volume is not on Coinbase | Features use base volume, scale-free. Dollar volume is used only as a labelled approximation, defined once for every connector (§5.2) |
| R7 | **Two fee rates.** The shared layer charges Coinbase's default of 1.20%; the account reads 0.50% | Costs are read through the exchange layer with their source recorded. Evaluations report both 0.50% and 1.20% (§5.7) |
| R8 | **The harness cannot do what Q1 needs.** It cannot score forecasts or pairs, or report by volatility regime, and phase C has no price-only twin | FDS-MH-001 amendment 1 (Appendix A) for what belongs in the harness; this spec's own code for the rest (§7) |
| R9 | **The volume research looked at the lockbox.** It examined volume against STRAT-001's entries and the pattern model over 2023-11-06 to 2026-11-05 (10 coins, Coinbase), which covers all of batch 1's lockbox (from 2025-05-06) | Every exposure is listed (§6.4.1). Development never scores from 2025-05-06 (§6.4.2), and volume is confirmed on fresh forward data (§6.4.3) |
| R10 | **Dead code.** `pt_neural_processor`, `RiskManager.validate_trade` and `calculate_position_size`, `pt_circuit_breaker` and `trade_proposal_approval` are not used by the trader | They are left alone and not revived (§5.4) |
| R11 | **No stop by default** | Recorded as an existing limit (§3.7). Exits are out of scope (§11) |
| R12 | **The LLM hook lets an entry through on any exception** (`pt_trader.py:1327-1338`). That suits an optional confirmation, not a protective limit | Each part of the assessment has its own failure rule, and there is no blanket handler (§5.8.3) |
| R13 | **`BATCH_1` follows the catalogue** (`model_lab/catalogue.py:60`) | Amendment 1 makes each batch's members an explicit list (Appendix A, AM1-6) |

### 3.7 Existing limits this spec does not resolve

These are facts about `main` today, and they matter most for small accounts. They are recorded so that no result here is read as fixing them. Each needs its own decision, under the strategy or risk work.

1. **An entry can exceed the coin's budget.**
   - The 1% entry is raised to the venue's minimum entry: the minimum order plus room for the spread, two taker fees and a 2% margin (`position_sizing.py:74-106`).
   - The risk check always allows that minimum, even above Max per coin (`pt_trader.py:1680-1689`).
   - **When it binds:** whenever 1% of the account is below the minimum entry, that is, for an account below about 100 × the minimum entry. For example, a $10 minimum order, a 0.50% taker fee and a 0.1% spread give a minimum entry of about $10.31, so the raise binds below about $1,031.
   - This spec changes nothing for an unshrunk entry. It only declines to raise a shrunk one (§5.8.4).
2. **STRAT-001 has no stop.**
   - It ships with no overlay (`pt_settings_manager.py:131-138`), and its only exit is the fast average falling below the slow. A position can keep falling until then.
   - The expected-value veto acts once, at entry. It is not a stop and does not limit a loss.
3. **A halt stops exits too.**
   - At the 8% drawdown level the trader's loop ends, and nothing is sold until the owner resumes trading (`pt_trader.py:3016-3025`).
   - With no stop, open positions stay open, unmanaged, during a halt.
4. **DCA buys are not checked by this spec.**
   - Rule 1 keeps the assessment away from DCA.
   - In the legacy chain a DCA buy is 2× the position's value (`pt_trader.py:2748`), so it can be larger than any entry the liquidity limits checked.
5. **In a small account the shrink acts as a veto.**
   - Where 1% is below the minimum entry, today's entry is the minimum. Any scale below 1 takes it under the minimum, and it is skipped (§5.8.4).
   - §6.3 evaluates the shrink at two account sizes for that reason.
6. **The replays' 100-unit account is not the owner's account.**
   - The gates and FDS-MH-001 replay a 100-unit account (FDS-MH-001 §5.3).
   - The app's paper account starts at $10,000 by default (`trading_mode.py:1044`).
   - This spec does not read the owner's account.

## 4. The evidence so far

| Question | Result | Status |
|---|---|---|
| Volume as a model input | The pattern model with a 20-bar relative-volume dimension equals the base model: p = 0.82 for hit rate, 0.96 for mean return. No timeframe's direction beats its base rate | Exploratory: one window, one encoding (research §6.5) |
| Volume conditioning STRAT-001's 1h entries | At the 1.20% fee, same-hour relative volume above 1.5× gives a hit rate of 21.2%, against 15.6% for all entries (n = 950 vs 4,333), and a mean of −2.10%, against −2.50%. Gross, it adds about +0.3% a trade (95% CI +0.04% to +0.55%) | Exploratory: chosen as the best of 296 tests (research §6.8). It needs fresh data |
| Other volume measures | Rolling 20-bar and 1-day relative volume, OBV, VWAP distance and CMF-20 showed no effect | Exploratory |
| Volume and volatility | Spearman correlation of same-hour relative volume and volatility: 0.31 at 1h, 0.35 at 15m | [TEST] (research appendix B). A price model must hold volatility, or volume would get volatility's credit |
| The literature | No study shows a volume filter surviving retail fees at 15m to 4h. The best study that includes costs finds that volume adds nothing to a trained model | Weak to moderate (research §4) |
| Entry timing in general | No published evidence that any model times crypto entries better than random at our costs | FDS-MH-001, C-evidence |
| Volatility as an entry filter | With no drift, P(+5% before −2.5%) ≈ 0.34 whatever the volatility | Theory (A-classic §3.1) |
| Trading-level power | The pattern model over 181 trades: the smallest detectable edge was 116% of random's median | Gate diagnostic |
| Confidence | No calibrated confidence exists anywhere in the app | Code review, §3.2 |

## 5. Design

### 5.1 Layers

```
features P, V, S, L, from complete bars of the candles the runner reads     (§5.2)
  → predictive part: p̂ = P(M = 1) → payoff model → expected value, costs once (§5.3, §5.5, §5.8.1)
       may veto; when its inputs are unavailable, no effect
  → [today's sizing: 1%, raised to the minimum entry]
  → protective part: volatility shrink, minimum check, spread cap, participation cap (§5.6, §5.7)
       may skip or shrink; when an enabled part lacks its input, skip
  → every existing control, unchanged, in today's order                       (§3.1)
  → order
```

### 5.2 Feature blocks

Every feature comes from complete bars only (§5.2.1), from the candles the runner already reads for the coin (rule 4).

**Every feature is scale-free:** a log, ratio or z-score of the market's own history on the same venue. So coins, and venues of very different sizes, can share one model. Coinbase carries 1–28% of the volume of three venues combined (research §6.7).

**P, price and volatility.**
- FDS-MH-001 §5.5's 26 features, minus its one volume feature: 25 features.
- They cover returns, realised and Parkinson volatility, trend distances, drawdown, the last bar's body and wicks, and BTC's context.
- Volatility belongs in P, so volume gets no credit for standing in for it (§4).

**V, volume.** Base volume only, and a small declared set (decision D3):
- **v1:** log of 24-hour volume over the 30-day daily mean (FDS-MH-001's feature);
- **v2:** log of the hour's volume over the mean volume of the same UTC hour on the 20 previous days. This is the research's main measure, `rv_hod20` (research §5.4). Weekend volume runs at about 0.7×.
- **Excluded for now:** CMF-20 and BTC's one-bar lead are FDS-SIG-001 round-one candidates, so they stay out (§6.4.4).

**S, the volatility forecast.**
- **What it is:** σ̂, a forecast of the next 24 hours' volatility, chosen from declared candidates by QLIKE loss on the development folds (Patton 2011).
- **The candidates:**
  - an EWMA of hourly squared log returns, λ = 0.94 (RiskMetrics 1996);
  - Parkinson range volatility over 24 hours (Parkinson 1980);
  - the last 24 hours' realised volatility, the naive comparator.
- **The rule:** the chosen candidate must beat the naive one, or the naive one is used.

**L, liquidity.**
- **Approximate dollar volume of a bar:** DV̂ = TP × V, where TP = (H + L + C) / 3 is the typical price and V the base volume.
  - It is labelled approximate everywhere and never called quote volume (FDS-SIG-001 §4).
  - **What it approximates:** the bar's true traded value, DV = VWAP × V, where VWAP is the volume-weighted price of the bar's trades. Coinbase does not state it.
  - **Relative error is defined against the true value:** ε = |DV̂ − DV| / DV = |TP − VWAP| / VWAP. The denominator is the true value, because the participation cap asks how large an entry is against what really traded.
  - **Its bound.** All of the bar's trades, so its VWAP, lie between L and H, and so does TP. When L > 0 and V > 0:
    ε ≤ ε̄ = max((TP − L) / L, (H − TP) / H).
    - This is the least bound the bar's OHLC supports. Given only OHLCV, VWAP can lie arbitrarily close to L (nearly all volume at the low) or to H. |TP − VWAP| / VWAP is largest at those ends: (TP − L) / L at the low end, (H − TP) / H at the high end.
    - A simpler bound that also holds is (H − L) / L, and it is never smaller than ε̄.
  - **The bound with the estimate as denominator** is different: |DV̂ − DV| / DV̂ ≤ max(TP − L, H − TP) / TP, which is at most (H − L) / TP. Revision 2 gave (H − L) / TP without saying which denominator it meant. Against the true value it can fail (§12, item 5, case C). This spec uses only ε and ε̄.
  - **No tighter bound is claimed.** Revision 2 also said the error is smaller when summed from finer bars. The data does not establish that, so the claim is removed.
  - **Zero volume:** when V = 0, DV̂ = DV = 0. The hour counts as 0 in sums and medians, and has no ε.
  - **Invalid prices:** a bar with L ≤ 0, H < L, O or C outside [L, H], V < 0, or any value that is not a finite number is invalid. Its DV̂ is missing, never 0. It is left out of medians and counted, and more than 24 invalid hours in a row are a gap that restarts the series (§5.2.1).
  - **On venues that state quote volume** (Binance, KuCoin, and Kraken through VWAP × volume), the stated figure is used only to test the bound. It is never used as an input, so the definition is the same on every connector (rule 4).
- **Hourly liquidity:** the median hourly approximate dollar volume over the 20 previous complete UTC days.
- **The live spread** at the decision: (ask − bid) / mid, from the quote the trader already reads.
- **Fees:** maker and taker rates through the exchange layer, the account's rate first, with the source recorded ("account" or "published default").

**Not inputs** (rule 4: not on every connector, or no history):
- trade count;
- taker-buy volume;
- order-book depth;
- funding rates;
- open interest.

#### 5.2.1 Complete bars and minimum history

**A complete bar.** At a decision time τ, a bar is complete when:
- its close time (its open time plus its length) is at or before τ; and
- the candle layer returned it from a request made after it closed.

The candle layer never returns or caches the still-forming bar (`market_data/candles.py:12-13, 269`), and the runner's row 0 is only a placeholder for it (`market_data/runner_history.py:8-9`).

**Decisions use only complete bars:**
- A decision at the close of hour t uses bars up to and including t, never t + 1.
- The bar just before the forming one must be present, as the runner already requires (`market_data/runner_history.py:115`). If it is missing, the coin has no assessment at that hour.
- A daily value uses the last completed UTC day. A day with a missing hour is a gap, as in FDS-MH-001 (`RUN-LOG-mh-1.md`, "Daily rules").

**Minimum history.** It counts closed hourly bars ending at the decision bar, on one venue, with no gap longer than 24 hours. A longer gap restarts the count, as FDS-MH-001 §5.2 restarts a series.

| Block | Longest look-back | Bars needed |
|---|---|---|
| P | The 50-day average. FDS-MH-001's phase C defines whether it averages 1,200 hourly closes or 50 completed UTC days | up to 1,224 |
| P, BTC context | BTC's 168-hour return and volatility, on the same venue | 169 of BTC's bars |
| V: v1 | the last 24 hours, over the 30 completed UTC days before the decision's day | up to 744 |
| V: v2 | the same UTC hour on each of the 20 previous days | 481 |
| S | the EWMA's burn-in, 168 bars before its first value (0.94^168 ≈ 3 × 10⁻⁵), and 24 more | 192 |
| L | 20 complete UTC days | 480 |

- **The predictive part** needs the largest of its blocks: **1,224 bars (51 days)** for P or P + V. Revision 1's "20 days, which fits in Kraken's 720" ignored P and v1.
- **The protective part** needs 192 bars for the shrink and 480 for the participation cap. The spread cap needs only the live quote.

**Absent and zero-volume hours.**
- **Per connector:** whether each connector returns an hour with no trades as a zero-volume bar, or leaves it out, is recorded in phase B, from fixtures.
- **The definitions are the same either way:** inside a kept gap (24 hours or less), an absent hour counts as zero volume in a sum and is never a decision row.
- **A zero denominator** (in v1, v2 or the participation cap's median) makes that value missing, as CMF abstains in FDS-SIG-002.
- **An invalid bar** (§5.2, under L) is a missing hour for every block: never a decision row, and never counted as zero.

**Revisions after close.**
- A venue may revise a bar after first serving it.
- Live features use the bars the runner had. The confirmation recomputes them from bars fetched again after its window (§6.4.3).
- Phase E's log records every live feature value, so the two can be compared (the revision check, §6.6). The comparison is reported and changes nothing.

#### 5.2.2 Venue limits

- **Kraken** serves only its latest 720 bars (`pt_exchanges.py:198`). That is 30 days, fewer than the predictive part's 1,224 bars.
  - The candle cache keeps what it fetches, per exchange (`market_data/candles.py:2-13`). So a Kraken series reaches 1,224 bars only after the app has fetched that coin from Kraken for about 21 more days, with no break longer than Kraken's 30 days.
  - Until then the predictive part is unavailable on Kraken. Its compatibility test (§5.2.3) needs another 28 days on top.
  - The participation cap (480 bars) and the spread cap work on Kraken from the first fetch.
  - The cache is safe to delete (`market_data/candles.py:71`). Deleting it starts the count again.
- **Late listings** start their count at their first bar: Coinbase's BNB from 2025-10-22 and HYPE from 2026-02-05, and KuCoin's symbols from 2022-09-29.
- **Coinbase** gives no per-bar quote volume, so L's approximation is used on every venue (§5.2).

#### 5.2.3 The venue compatibility test

A model is evaluated on one venue, which its evidence records. It runs on any other venue, Kraken included, only after that venue passes this test for the same model and code hash.

- **Window:** the latest 28 complete days for which both venues have the full 1,224-bar history for the coin.
- **Computed from each venue's own bars:** for every coin and hour in the window, every feature, p̂, and the sign of the expected value as if an entry were wanted.
- **It passes** when all of the following hold (proposed tolerances, D17):
  - each feature's Spearman correlation between the venues, pooled over coins and hours, is at least 0.90;
  - the median absolute difference in p̂ is at most 0.02, and its 95th percentile is at most 0.05;
  - the sign of the expected value agrees on at least 95% of hours.
- **Repeated** every 3 months, and whenever the model changes.
- **Run from** Settings > Training, beside the reports. Its result is stored with the model's evidence.
- **A venue that fails, or has not been tested,** has no predictive part (§5.8.3). The protective part uses each venue's own data and needs no compatibility test.

The volume research ran an agreement check of this kind on Kraken's latest 685 bars (research §6.7).

### 5.3 Targets: T1 and M are different events

| | T1: a barrier event | M: the strategy's profit |
|---|---|---|
| **The event** | From hour t's close, the price reaches the first profit line before the first DCA level, within 336 hours (FDS-MH-001 §5.5) | The trade this strategy would open at this entry ends, under its own exits, with a profit after costs at the evaluated fee |
| **Whose exits** | The legacy chain's: its barriers are the trailing margin's start and the first DCA level | The active catalogue strategy's: for STRAT-001, the crossover exit |
| **Costs** | Already inside the barrier: the profit line includes fees, as the trader computes it | In the event's threshold at the evaluated fee. Never inside the payoff means (§5.8.1) |
| **Rows** | Every stream hour: tens of thousands per coin | One per entry the strategy wants: about 4,333 in 3 years on 10 coins (research §6.1) |
| **Used for** | Q1's forecast test only | The confidence shown, the expected-value veto, Q1's decision test, and Q2 |
| **Never used for** | An expected value, or a confidence shown for a catalogue strategy | The legacy chain (below) |

**T1 is FDS-MH-001's planned target.**
- It is strategy-free and has many rows, so it is the best place to ask whether volume carries any information at all.
- It says nothing about STRAT-001's payoff.
- Its barriers already include the fees, so adding a separate cost to it would count them twice. That is why it never enters an expected value.

**M is defined by the backtester's own fill accounting** (`backtest/engine.py:6-8, 182-218`):
- **Fills:** a signal on bar t's close fills at bar t + 1's open. The trade exits on the strategy's own EXIT, at the next open.
- **Gross return:** r_g = P_exit / P_entry − 1, from the raw opens, before slippage and fees.
- **Net return:** with fee f a side and slippage e a fill, the backtester's accounting gives exactly
  net = (1 + r_g) × m(f, e) − 1, where m(f, e) = (1 − f)² × (1 − e) / (1 + e).
  The entry fee comes out of the amount spent and the exit fee out of the proceeds. This is the research's formula too (research §5.3).
- **M = 1** when the net return is above 0 at the evaluated fee f₀ and e₀ = 0.05%. That is, when r_g > 1 / m(f₀, e₀) − 1.
- **The configuration is part of M.** The strategy's key, parameters, timeframe and overlays belong to M's definition and to the model's evidence. A different configuration is a different M (§5.8.3).

**M under the legacy exits is not used.**
- With DCA and the trailing margin, random entries end in profit about 91% of the time (research §6.4), so M carries no information there.
- The legacy chain therefore gets no expected-value veto. It is judged only by FDS-MH-001's return per capital-day (§6.1).

### 5.4 Forecast models and how sources are combined

- **The model:** a regularised logistic regression, pooled over coins (FDS-MH-001 phase C, "linear").
  - Its penalty is fixed in advance (L2, C = 1), and its features are standardised on the training rows only.
  - **On T1:** the pair M_P and M_PV, and the placebo (§6.1). They form FDS-MH-001 batch PV-1 (Appendix A).
  - **On M:** the meta-models F_P and F_PV, each fitted on the strategy's entries before each fold.
  - Histogram trees (FDS-MH-001 D6) are a secondary, exploratory model class.
- **Fusion is one model over the declared feature blocks.**
  - No stacking of sub-models, no neural fusion, and no weights set by hand.
  - **Why:** the signals are few and weak. More parameters overfit: in the volume research, adding a dimension multiplied the pattern model's memories 2.2–3.3× and gained nothing (§6.5 there).
- **Later sources join only as declared features of a new batch, never as votes.** Such sources are:
  - a rule CONFIRMED under FDS-SIG-001;
  - an LLM signal with a gate pass;
  - a calibrated thinker count (§5.5).
- **Not reused:** `pt_neural_processor`'s confidence-weighted combination (R10).

### 5.5 Confidence: definition, calibration and when it may count (Q2)

**Definition.** A confidence is p̂ = P(M = 1): the calibrated probability that this strategy's trade at this entry ends with a profit after costs at the evaluated fee, for this coin, at this decision time.
- **Shown** in the app as a fact, for example "Chance of a profit after fees at 0.50%: 27%".
- **Scores, not confidences:** the thinker's counts, ADX, the LLM's self-reported 0–100, and a T1 probability.

**Calibration, strictly out of fold.**
- **The default** is Platt scaling (Platt 1999), with two parameters.
- **For fold k,** it is fitted on the out-of-fold predictions of the folds before k. Each of those predictions was made by a fit that saw only bars before its own fold. It never sees fold k's rows.
- **Fold 1** has no calibration and is not scored for Q2.
- **For the forward window,** it is fitted at registration on the out-of-fold predictions of the 3-month folds in the 18 months before registration. It is then frozen (§6.4.3).
- **The climatology** each row is compared with is the base rate of M on that fold's training rows, never on the scored rows.
- **Isotonic regression** is used only through a declared change, with at least 5,000 out-of-fold rows, because it overfits small samples.

**Measures**, on scored rows, pooled, and per coin and per fold. Each is a proper scoring rule, or a diagnostic of one:
- **log loss.** It is strictly proper (Gneiting and Raftery 2007);
- **the Brier score**, and its decomposition into reliability, resolution and uncertainty (Murphy 1973);
- **the Brier skill score:** BSS = 1 − Brier / Brier_clim;
- **a reliability diagram:** 10 equal-count bins, with block-bootstrap bands;
- **calibration in the large, a:** the intercept of a logistic fit of the outcome with logit(p̂) as an offset, the slope held at 1;
- **the calibration slope, b:** the slope of a logistic fit of the outcome on logit(p̂) (Cox 1958);
- **sharpness:** the standard deviation of p̂, and its 10th-to-90th-percentile range.

These recalibration fits are diagnostics only. They never change a forecast.

**When a confidence may affect anything.** All three conditions must hold, both on the development folds and again on the forward window:
1. **Skill.** BSS > 0, one-sided. It is tested by the paired block bootstrap of §6.0 on the per-row differences Brier_clim − Brier, within the Holm family (§6.5).
2. **Calibration within tolerance.** This is an equivalence test: two one-sided tests at 5% (Schuirmann 1987). The 90% block-bootstrap interval of each measure lies wholly inside its pre-registered band (D16):
   - **a** inside [−0.10, +0.10] logit. At a base rate of 0.25 that is about ±1.9 percentage points;
   - **b** inside [0.80, 1.20].
3. **Enough data.** At least 200 scored entries with M = 1, and 200 with M = 0.

**Three outcomes for calibration,** so that imprecision never passes:
- **"Calibrated within tolerance":** both intervals inside their bands.
- **"Miscalibrated":** an interval excludes its ideal value, 0 for a or 1 for b.
- **"Not assessable":** anything else. The interval contains the ideal value but is too wide, or too far from it, to sit inside the band. This includes a model whose p̂ barely varies, so its slope cannot be estimated.

**Why this replaces revision 1's test.**
- Revision 1 asked only that the 95% intervals contain 0 and 1. A small or uninformative sample passes that.
- The new criteria are "weak calibration" in the sense of Van Calster et al. (2016). The reliability diagram shows the rest.

**Planned precision.**
- Before registration, the power simulation (§6.5) estimates both intervals' widths at the planned window.
- If it shows less than an 80% chance that both fit inside their bands, the registration does one of two things:
  - lengthens the window; or
  - records Q2 as "not assessable at this window", in which case no confidence-based effect can come from that window.
- This follows the precision-based approach to validation sample sizes of Riley et al. (2021).

**When the conditions fail:**
- the assessment shows p̂ as "not calibrated";
- the predictive part is unavailable (§5.8.3);
- only the protective part can act.

**Existing scores.** The thinker's counts and the LLM's confidence can be calibrated the same way, as P(M = 1 | score level) estimated on earlier folds. Only then can they become inputs.

**Drift.** The forward window reports calibration month by month, as information. The calibrator is never refitted during the window (§6.4.3).

### 5.6 Volatility (Q3)

- **Not an entry signal.** With no drift, T1's probability does not depend on volatility, and FDS-MH-001 dropped volatility filters for that reason (§4).
- **A forecast input:** in block P, so that no other block gets volatility's credit.
- **A protective shrink.**
  - **The scale:** s_vol = min(1, σ_ref / σ̂). Here σ_ref is the pooled median of σ̂ over the evaluation's training rows, fixed and recorded with the evidence.
  - **It only ever shrinks:** a volatile coin gets a smaller entry, and no entry is ever larger than today's.
  - **Its own setting** (§5.8.3). It can be turned On only after its activation requirements pass (§6.7). Once On, it applies in both modes, and an entry whose σ̂ is missing is skipped.
  - **What it can claim:** less drawdown than the same scales given out at random. It never shows the strategy is profitable (§6.1, F3).
  - **In a small account it acts as a veto** (§3.7, item 5).
- **Reporting:** every result is reported by volatility tercile (cut points from the training rows) and by BTC's 90-day trend (FDS-MH-001's), descriptively.
- **Exits and stops are unchanged.** A volatility-scaled stop exists as OVL-ATR, but changing exits changes the strategy, so it belongs to the strategy project (§11).

### 5.7 Liquidity and costs (Q3)

**Costs are applied once:**
- **Fee:** the taker rate through the exchange layer, the account's rate first, with its source recorded.
- **Execution allowance per fill:** e = max(½ × the live spread, 0.05%). The spread and the slippage allowance are never both charged.
- **In historical evaluation** there is no live spread, so e = 0.05%, as the gates use. An OHLC spread estimate (Abdi and Ranaldo 2017) is reported as a sensitivity.
- **The round trip's costs enter the expected value only through m(f, e)** (§5.8.1).

**Two protective limits.**
- Each is its own setting: Off, Log only or On, with Off the default.
- They need correctness tests, not predictive evidence.
- Before either is turned On, Log only shows how often it would have skipped an entry, per coin and per month (D11).

The limits:
- **Participation:** the entry's dollars must be at most π × the median hourly approximate dollar volume over the 20 previous complete UTC days on that venue. Proposed π = 1%.
  - **The median** is taken over the window's valid hours (§5.2), zero-volume hours included as 0.
  - **π applies to the estimate.** Let ε_max be the largest ε̄ among the median's hours with volume.
    - Each such hour's true value is at least DV̂ / (1 + ε̄) ≥ DV̂ / (1 + ε_max), and a median keeps that order.
    - So against the true median over the same hours, the entry's share is at most (1 + ε_max) × π.
  - **The record** gives ε_max and that figure. No tighter statement is made.
- **Spread:** the live spread must be at most s_max. Proposed s_max = 0.50%.
- **A missing input while On** skips the entry (§5.8.3). So a coin in its first 20 days on a venue cannot be entered while the participation cap is On.
- **Not covered:** DCA buys and sells (rule 1; §3.7, item 4).

**When they bind.** At the default paper balance of $10,000 an entry is $100, which binds only on very thin markets. The limits are meant for thin coins, late listings and larger accounts.

### 5.8 The assessment and its effect on a decision

#### 5.8.1 Expected value, with costs applied once

This applies to an entry that the active catalogue strategy wants.

**The inputs:**
- **p̂ = P(M = 1),** calibrated and eligible under §5.5.
- **The payoff model,** gross, from the same strategy's training trades:
  - W_g(τ): the mean r_g of training trades with M = 1 in volatility tercile τ;
  - Λ_g(τ): the mean r_g of those with M = 0 in τ. It is signed, and usually negative;
  - the terciles' cut points come from the training rows' σ̂. A cell with fewer than 30 trades pools over terciles.

**The calculation:**
- **Expected gross return:** μ̂_g = p̂ × W_g(τ) + (1 − p̂) × Λ_g(τ).
- **Expected net return at the decision's own costs:** EV = (1 + μ̂_g) × m(f, e) − 1, with f and e from §5.7.
- **Veto when EV ≤ 0.** Equivalently, when μ̂_g ≤ 1 / m(f, e) − 1, the break-even gross return.

**Why the costs count once.**
- p̂ and the payoff means describe gross returns. The costs enter once, through m.
- The evaluated fee only sets where M's event is cut; it is not inside the payoff means.
- By the law of total expectation, μ̂_g is the mean gross return whatever the cut, provided p̂ is calibrated and the means are right. So EV stays right when the decision's fee differs from the evaluated one.
- T1, whose barrier already holds the fees, never enters.

**An assumption, checked.**
- The model treats the payoff means as fixed within a class and a tercile.
- Phase C reports the realised mean net return by EV quintile, against the mean predicted EV: the payoff calibration table. It is shown and decides nothing.

#### 5.8.2 The record

One record per entry the existing path wants:

| Field | Content |
|---|---|
| when, coin, venues, source | the decision bar's close; the coin; the candle venue and the venue that prices the order; the strategy and its configuration, or the thinker |
| p̂ | the calibrated probability of M, or "not calibrated" or "unavailable", with the reason |
| model | the model's id, its evidence record and the code hash (§5.9) |
| expected value | μ̂_g, W_g, Λ_g, τ, m and EV |
| costs | the taker fee and its source, the live spread, e |
| volatility | σ̂, σ_ref, s_vol |
| liquidity | the median approximate dollar volume, ε_max and the participation rate's bound against the true median (§5.7), and the spread |
| each part's state | for the veto, the shrink and each cap: Off, Log only or On; available or not, with the reason |
| effect | none, skip or scale, with the part that caused it and the reason |
| live features | every feature value, for the revision check (§5.2.1) |

#### 5.8.3 Settings, and what happens when something is missing (D8)

**Four settings, each Off by default** (§5.10):

| Setting | Values | Can be On only when |
|---|---|---|
| Entry assessment (the predictive veto) | Off, Log only, Veto | the veto's activation requirements (§6.7) have passed for the active strategy configuration, F3's absolute profitability included, and the owner has decided (phase F) |
| Volatility shrink | Off, Log only, On | the shrink's activation requirements (§6.7) have passed, and the owner has decided |
| Participation cap | Off, Log only, On | always: it needs correctness tests only |
| Spread cap | Off, Log only, On | always |

A setting that cannot be On yet is greyed out, with the reason. This mirrors the trainer's rule of publishing only on a gate pass.

**What happens in each case:**

| Case | Examples | Effect on the entry | Recorded and shown |
|---|---|---|---|
| A part is Off | — | None. That part computes nothing | nothing |
| A part is in Log only | any result, any failure | None | each result and failure, with its reason; would-skip counts per coin and month |
| **The predictive veto is On, and its inputs are unavailable** | • No passing evidence for this strategy, parameters, timeframe or overlays<br>• A code-hash mismatch<br>• A venue without a passing compatibility test<br>• Fewer than 1,224 complete bars, a gap, a zero denominator, or data older than its bound<br>• p̂ not calibrated<br>• A calculation error | **Fails open.** No predictive veto: the entry goes on to the next part unchanged, as today | the reason per entry; a notice when more than 20% of a coin's assessments in 7 days were unavailable (D11) |
| **A protective part is On, and its input is missing** | • The shrink without σ̂<br>• The participation cap without 20 complete days of the venue's hourly volume<br>• The spread cap without a usable quote: bid or ask missing, ask ≤ bid, or a quote older than 60 seconds<br>• A calculation error in that part | **Fails closed.** The entry is skipped | the reason per entry, in the table; a notice the first time per coin per day |
| An error not attributable to one part | an exception in the hook itself | Skipped if any protective part is On; otherwise unchanged | the error, per entry |

**Why the two kinds of part fail differently.**
- **The predictive veto** is an optional filter with weak evidence behind it.
  - When its inputs are missing, the entry returns to today's path, which every existing control still guards.
  - Failing closed would let a data fault stop all entries through a part that has no protective role.
- **A protective limit** is something the owner turned on to prevent a kind of entry.
  - If a missing input let that entry through, the limit would be silently bypassed, and exactly when the data is worst.
  - So it skips.

**No blanket handler.**
- The LLM hook lets an entry through on any exception (`pt_trader.py:1327-1338`). The new hook does not.
- Each part is evaluated separately and fails by its own rule.
- No exception from an enabled protective part can become "allow".

**A skip only ever stops an entry.** It never blocks an exit, a sell or a DCA buy (rule 1).

#### 5.8.4 Where it runs, and its effects

**Where it runs:**
- **The predictive veto** runs directly after the LLM hook in the trader's entry loop (`pt_trader.py:2908-2913`), before sizing, in both modes (R4).
- **The protective part** runs directly after the trader's own sizing call (`pt_trader.py:2916-2921`; the sizing itself is `pt_trader.py:2017-2037`), and before `place_buy_order`, which runs the risk check (`pt_trader.py:2922-2930`). It runs in both modes. So it checks the amount the order will actually have.
- DCA buys and exits never consult either part.

**Its effects:**
- **Veto:** when EV ≤ 0 (§5.8.1), with an eligible p̂. Catalogue strategies only.
- **Shrink:** the entry becomes today's amount × s_vol.
- **Minimum check:** **a shrunk entry below the venue's minimum entry is skipped, never raised** (R5).
  - The raise of an unshrunk entry is unchanged (§3.7, item 1).
  - In legacy mode a DCA buy is a multiple of the position's value (`pt_trader.py:2748`), so it shrinks with the entry. Nothing else changes.
- **The spread cap,** then **the participation cap** on the shrunk amount.
- **The first part that skips ends the assessment.** The record names that part.

#### 5.8.5 Invariants

Each is a test (§12):
1. The hook returns only "allow unchanged", "skip", or a scale in (0, 1]. It never creates an entry or raises a size.
2. Whatever it lets through passes every existing check, unchanged: the halt, the drawdown halt, the mode pin, the strategy-settings check, the coin budget, the minimum, the risk check and preview.
3. With every new setting Off, the trader's orders are byte-identical to `main`'s. With any of them in Log only, they are too.
4. Exits, sells, DCA triggers, the trailing margin and stops never read the assessment, and a skip never stops one of them.
5. Every assessment is recorded, with the code hash.
6. A hash mismatch makes the predictive part unavailable.
7. An enabled protective part whose input is missing, stale or in error always skips the entry.
8. No exception path turns an enabled protective part's failure into "allow".

### 5.9 One implementation, two callers

- **One package:** the features, the forecast and the assessment live in one package, proposed as `app/signal_fusion/`. It imports P and V from `model_lab.features` (FDS-MH-001 phase C, amended), so the harness and the trader share one definition.
- **The same functions everywhere:** the harness replay, the backtester and the trader call them.
- **Hashed:** their files are added to the code hash in the record of the model in use, as `CODE_FILES` does for the pattern model (`pt_pattern_trainer.py:1157-1163`).
- **The registered artifact.**
  - For the forward window, one file holds the fitted models, the calibrator, the payoff tables, σ_ref, the tercile cut points and the code hash. Its hash is part of the registration.
  - The live hook loads only that file. Any other file makes the predictive part unavailable (§6.6).

This closes R2 for this spec's own code.

### 5.10 Settings and display

- **Settings > Strategy:** "Entry assessment": Off, Log only, Veto. The model in use is shown, with its evidence status and the strategy configuration it covers.
- **Settings > Risk:** three settings, each Off, Log only or On:
  - "Volatility size reduction";
  - "Largest entry as a share of hourly trading", with π;
  - "Widest spread for an entry", with s_max.
- **Settings > Training:** the Q1, Q2 and Q3 reports (in FDS-MH-001's "Compare models…" window), and the venue compatibility test (§5.2.3).
- **A table in the app:** each assessment, with its time, coin, venue, p̂ or "not calibrated", EV, costs, volatility scale, liquidity figures, each part's state, the effect and the reason. During a registered window it shows no outcomes (§6.6).
- **All text states facts.** No spec names and no caveats about the design.

## 6. Evaluation

### 6.0 Procedures shared by every test

**The block bootstrap.** One scheme serves every test in this spec.
- **Unit:** the UTC calendar day. A forecast row belongs to its hour's day. A trade belongs to its entry's day, with all of its profit and capital-days.
- **Blocks:** circular blocks of L = 28 days (Politis and Romano 1992).
  - Each draw takes ⌈N / L⌉ blocks, where N is the number of days in the scored period.
  - Each block's start day is drawn uniformly from those N days, and blocks wrap round the period's end.
  - The wrap applies only to resampling days of rows that are already scored, for inference. It never moves a feature or a label in time, unlike revision 2's placebo (§6.1).
  - The blocks are joined and cut to N days.
- **Why 28 days:** T1's labels span up to 14 days (336 hours). A block of at least twice the longest label span keeps overlapping labels together (Künsch 1989).
- **A fixed rule for long trades:** if more than 1% of a family's scored trades last longer than 14 days, L = 56 days for every test in that family. The rule is applied mechanically, before any result is read. It replaces revision 1's "blocks of whole weeks" for the decision level.
- **All coins together:** every coin's rows on a day move together, which keeps the dependence between coins.
- **Pairs:** both members of a pair, and the placebo, use the same days in each draw.
- **Ratios:** a draw's return per capital-day is its summed net profit over its summed capital-days.
- **The p-value** for H₀: θ ≤ 0 against θ > 0, where θ̂ is the statistic on the data and θ*_b its value in draw b:
  p = (1 + #{b : θ*_b − θ̂ ≥ θ̂}) / (B + 1). This is the centred bootstrap (Hall and Wilson 1991).
- **Intervals:** percentile intervals of θ*_b.

**Repeated runs.**
- Every p-value and interval in this spec comes from 10 runs of 1,000 draws. Run r is seeded `seed + r`, with the seed declared per test.
- The deciding p-value pools all 10,000 draws: p = (1 + total exceedances) / 10,001.
- Each run's p is shown beside it, and so is the largest minus the smallest.
- The same applies to R3 and R3s.

**Conditions on a claim.**
- Where a claim needs several tests to pass, only its primary test is in the Holm family. Each condition is tested at 5%.
- Requiring every one of them cannot raise the claim's error rate above the primary test's: the intersection-union principle (Berger 1982).

**The portfolio replay.** The decision-level, economic and sizing tests (§6.1's F2 and F3, and §6.3) score STRAT-001's trades in a replay of one shared account that follows the trader's rules.
- **Opportunities:** STRAT-001's ENTER_LONG signals, from the backtester's logic per coin, with its fills and exits (§5.3).
  - STRAT-001 fires once per fresh cross. A coin is flat at every fresh cross, because its last trade exited when the fast average fell below the slow. So every path faces the same opportunities.
  - The one exception is an exact tie between the two averages. Any such case is counted.
- **At each opportunity, in time order:**
  1. the coin must be flat: one trade per coin;
  2. the amount is the trader's own: `position_sizing.entry_usd`, at 1% of the account's value. It is raised to the minimum entry, using today's venue minimum, 2 × the taker fee, the 2% margin, and a spread of 2 × e;
  3. the coin budget of 10% applies, with the minimum entry always allowed (`pt_trader.py:1680-1689`);
  4. an amount above the free cash is skipped, and counted as ineligible in that path;
  5. then the filter, the shrink and the minimum check under test are applied.
- **Each trade** pays the backtester's costs: net = (1 + r_g) × m(f, e) − 1, on its amount.
- **Equity** is marked at every hourly close. The maximum drawdown is taken from that curve, not from single trades.
- **Capital-days:** each trade's amount × days held.
- **Account sizes:**
  - $10,000, the default paper balance, decides;
  - $100, where the minimum binds (§3.7), is shown.
- **The drawdown halt is reported, not modelled.** Resuming after a halt is the owner's action, which a replay cannot know.
  - Each path reports when the 8% level would first have been reached.
  - A variant in which the path ends at that point is shown beside it.
- **A check against the backtester:** with one coin and a 100% size, the replay reproduces `run_backtest`'s per-trade `pnl_pct` exactly (a test, §12).

### 6.1 Q1: does volume add value beyond price?

Q1 has three findings, judged separately. Each one is a different claim:

| Finding | The claim | Compared with | Section |
|---|---|---|---|
| **F1, forecast value** | Volume improves forecasts over price alone | M_P, and a placebo | below |
| **F2, relative trading value** | Volume improves trading results, or reduces losses, against matched controls | F_P's path, and R3 | below |
| **F3, economic viability** | The approach, as it would trade, makes money after the applicable fees and execution allowances | zero: an absolute requirement | below |

F2 never implies F3. A filter can beat price alone and random vetoes while the strategy still loses money.

**The pair.** This is FDS-MH-001 batch PV-1 (Appendix A, its §7a).
- M_P uses block P; M_PV uses P + V.
- Everything else is the same: model class, penalty, target (T1), folds, rows and seeds.

**The placebo: the same coin's volume, from an earlier time.**
- **The transformation.** For variant j (j = 1 to 5), at decision hour t of coin c:
  Ṽ_j(c, t) = V(c, t − δ_j), the same coin's V block as computed at hour t − δ_j.
  - δ_j = 3,840 + 24 a_j + b_j hours, where a_j is an integer from 0 to 9 and b_j an integer from 1 to 23, both seeded and declared (Appendix A, AM1-7). So δ_j is between 3,841 and 4,079 hours: 160 to 170 days.
  - The declared seeds give δ_1 to δ_5 = 3,930, 4,076, 3,850, 4,062 and 3,857 hours.
  - δ_j is never a whole number of days, so the lagged value never comes from t's hour of day.
- **Timestamps.**
  - V(c, t − δ_j) uses only bars that closed by hour t − δ_j (§5.2.1). So every value in a placebo row was available more than 160 days before t, and no row reads anything after its own hour.
  - Why 160 days: it is FDS-MH-001's D (§5.6), far longer than V's 31-day look-back and T1's 14-day horizon. So the lagged block shares no bar with the row's own V block, or with its label.
- **No forward move, and no wrap.** Revision 2 moved V forward and wrapped it round the development period, so a row could carry volume from a later time. That is gone. It would also have failed FDS-MH-001's own look-ahead test.
- **The start of a series, and missing history.**
  - Ṽ_j(c, t) exists only when two things hold: hour t − δ_j belongs to the same series as t (the stretch after the last gap longer than 24 hours, FDS-MH-001 §5.2), and V(c, t − δ_j) exists.
  - Otherwise it is missing. That is the case:
    - at the start of each series, for its first 4,820 hours (about 201 days: the longest declared lag, 4,076 hours, plus V's 744);
    - after a long gap, for the same span again;
    - wherever the lagged hour is a missing or invalid hour.
  - A missing placebo value is never filled in, carried forward, or taken from another coin or time.
- **Paired rows.**
  - M_P, M_PV and the five placebo variants are fitted and scored on one row set: the hours at which P, V and every Ṽ_j exist (the common rows). A row missing any of them is out for every model.
  - The report gives how many rows that removes, per coin.
  - PV-1's trading-level contestants decide only at common hours, and are undecided elsewhere.
- **Folds.**
  - The transformation is the same at every hour and does not depend on where a fold starts.
  - Each fold's fit uses only common rows before the fold, purged as FDS-MH-001 §5.4 sets out, with features standardised on those rows. That fit decides the fold's own common rows.
  - A training row's placebo value comes from before that row, so from before the fold. A test row's comes from before the test row. Neither reads a label from the fold, or any later bar.
- **Fitting:** each variant is fitted exactly as M_PV.
- **What it guards against.**
  - The placebo keeps V's columns, their kind and, roughly, their distribution, but breaks their timing against the row.
  - So it tests whether volume carries information at the row's own time, rather than gaining from extra columns as such, or from a leak.
- **A check, shown:** each V feature's correlation with its lagged copy, pooled. If any is above 0.10 in absolute value, the report says that the placebo still carries some of V's own information. That makes the placebo condition harder to pass, not easier.

**F1, forecast value: the primary test.**
- **Rows:** every common row of PV-1's walk-forward stream whose T1 label resolves inside the stream.
  - Each model's own out-of-fold probability is used: the logistic fit, with no recalibration, from fold 1 on.
  - Probabilities are clipped to [10⁻⁶, 1 − 10⁻⁶], for every model alike.
- **Per row:** d = ℓ(y, p̂_P) − ℓ(y, p̂_PV), where ℓ(y, p) = −[y ln p + (1 − y) ln(1 − p)].
- **Statistic:** D̄, the mean of d over all rows, each row weighted equally. A positive D̄ favours volume.
- **Test:** H₀: E[d] ≤ 0, by §6.0's block bootstrap, in the Holm family.
- **Conditions**, each one-sided at 5% (§6.0):
  - **the placebo:** per row, e = ℓ̄_placebo − ℓ(y, p̂_PV), where ℓ̄_placebo is the mean of the five placebo variants' losses on that row. Then Ē > 0, by the same bootstrap, with the same days;
  - **stability:** D̄ > 0, as a point estimate, in each half of the scored days, split at the middle day.
- **Shown:**
  - D̄ for each placebo variant against M_P, expected to be at most 0;
  - D̄ by coin, by year and by volatility tercile;
  - D̄ before, and from, 2023-11-06, the start of the volume research's look (§6.4.1).

**Trading level, under FDS-MH-001's fixed strategy: secondary, and expected to be underpowered.**
- PV-1's three contestants are scored by FDS-MH-001 against R1 and R2, with PV-1's own Holm over K = 3.
- **Shown, outside the family:** the paired difference in return per capital-day between M_PV and M_P on the hours both cover, by §6.0's block bootstrap, with its smallest detectable difference.
- This is a relative finding, of F2's kind, under the legacy exits. FDS-MH-001's own floor of total profit above 0 for a finalist does not make it F3.

**F2, relative trading value: the decision level.**
- **Opportunities:** STRAT-001 1h at its defaults, on the batch's coins, over the development period (§6.4.2).
- **Two filters**, both on target M: F_PV, with V, and F_P, without.
  - They share the opportunities, the veto rule (§5.8.1), the folds and the calibration procedure.
  - An opportunity with no eligible p̂ in either filter (fold 1, or missing data) is taken in every path, as the live predictive part fails open. R3 never touches it.
- **The deciding statistic:** Δ = RPCD(F_PV's path) − RPCD(F_P's path), from the portfolio replay (§6.0). RPCD is return per capital-day.
  - H₀: Δ ≤ 0, by the paired block bootstrap over entry days, in the Holm family.
- **Condition:** F_PV beats R3 (below), one-sided at 5%.
- **A path with no trades** has an RPCD of 0, and the report gives each filter's veto rate beside its RPCD. At the account's fees STRAT-001 loses money on average, so a filter that vetoes nearly everything shows only that.

**R3: a random veto that keeps the trader's constraints.**
- **What a draw does.** For each coin c, k_c is the number of opportunities the filter vetoed among its assessable, eligible opportunities on that coin. Each R3 draw vetoes k_c of that coin's assessable, eligible opportunities, chosen uniformly without replacement.
- **Each draw is replayed** through the same portfolio replay, with the same sizing, budget, minimum, one trade per coin and free cash.
  - An opportunity that turns ineligible in a draw's own path is skipped there and counted. Only free cash can cause that, and at $10,000 it is not expected to happen.
- **Score:** each draw's RPCD.
  - p_R3 = (1 + #{b : RPCD(R3_b) ≥ RPCD(F)}) / (B + 1), with B = 10,000 drawn as 10 seeded runs (§6.0).
- **Shown:** an R3 that does not stratify by coin, and each draw's realised veto count.
- **Why it works:** with no skill, a filter's RPCD matches random thinning, whatever the shape of the payoff, because both score the strategy's real trades.

**The research's chosen rule:** same-hour relative volume above 1.5×, chosen from 296 tests.
- **Declared now** as a fixed filter on STRAT-001's opportunities: veto an entry whose v2 is at most ln 1.5.
- **Forward:** in the confirmation family (§6.5), against R3. A pass is an F2 finding, not F3.
- **Development:** scored only before 2023-11-06, the part the research never saw. It is shown and decides nothing.

**F3, economic viability: the approach as it would trade.**
- **What is judged:** the path that would be activated, in the portfolio replay (§6.0), at the deciding account size of $10,000. That path is STRAT-001 1h at its defaults with the registered model's veto (F_PV or F_P, §6.2), plus the volatility shrink if the registration includes it.
- **Applicable fees and allowances:**
  - **The fee:** the taker rate the target account's fills will pay, read through the exchange layer with its source recorded. For paper, that is the rate the paper account's fills record (`trading_mode.py:579-584`); where the source is the published default, the published default applies.
  - **The allowance:** e = 0.05% a fill.
  - The registration fixes both (§6.4.3). The 0.50% and 1.20% rows are shown beside them.
- **Requirements** (all five must hold):
  1. **Enough trades:** at least 100 closed trades in the window, and at least 30 in each half. Otherwise the verdict is "Not assessable", with n.
  2. **A profit:** return per capital-day above 0, one-sided by §6.0's block bootstrap, in the Holm family (§6.5). Its sign is the sign of total net profit after fees and allowances.
  3. **Stable:** net profit above 0 in each half of the window, each trade counted in the half of its entry day (as in §6.0).
  4. **Not one coin:** the summed net profit of the path's trades on every coin except the most profitable one is above 0. The trades are summed as they occurred in the path; the path is not replayed without that coin.
  5. **Within the trader's own limit:** the equity curve's maximum drawdown stays below the emergency drawdown level (8% by default). The replay reports the halt rather than modelling it (§6.0), and a path that would have halted the trader is not viable as configured.

  Requirements 1 and 3 split the window into halves at its middle day. Requirements 1, 3 and 4 count every closed trade, including those closed at the window's last close (§6.4.3).
- **Reported; these decide nothing:**
  - **profit:** net profit in dollars, and as a return on starting equity, for the window and annualised;
  - **efficiency:** return per capital-day;
  - **capital use:** time in the market (the share of hours with an open position), mean and peak capital committed as a share of equity, and capital-days;
  - **trades:** the number of trades, the win rate, and the mean and median net return a trade;
  - **drawdown:** the maximum drawdown in dollars and as a share of the peak; its start, trough and recovery (or "not recovered"); the time under water; and the largest loss on one trade;
  - **comparisons:** the same figures for STRAT-001 unfiltered, for F_P's path and for R3's median, and at $100.
- **Development reports F3's figures** for F_PV's path, labelled development. Only the forward window can establish F3.

**Verdicts.** Each line states the score, the comparison's value and n beside the verdict.

| Finding | Passes when | Wording if it passes | Wording otherwise |
|---|---|---|---|
| F1 | the primary test, in the Holm family, and both conditions | "Volume improves forecasts over price alone (Δ log loss = …, n = …)" | "No forecast improvement detected (smallest detectable Δ log loss = …)" |
| F2, with the path's net profit at most 0 | Δ, in the Holm family, and the R3 condition | "Volume reduces losses compared with price alone and with random vetoes. The strategy still loses money after fees (net … over n trades)" | "No improvement over price alone detected (smallest detectable difference = …)" |
| F2, with the path's net profit above 0 | the same | "Volume improves results compared with price alone and with random vetoes. Profitability is shown separately (F3)" | the same |
| F3 | all five requirements | "Profitable after fees in the confirmation window: net …, return per capital-day …, n trades, maximum drawdown …" | "Not shown to be profitable after fees", naming the requirement that failed |
| any | a floor not met | — | "Not assessable", with the floor |

**Wording rules:**
- Only an F3 pass may use the words "profitable" or "makes money". A result that loses less money than its controls is described as reducing losses.
- Development results say "development", and are never described as confirmed (§6.4.2).
- The volatility shrink's result reads "reduces drawdown compared with random sizing" (§6.3). It is never a profitability claim.

### 6.2 Q2: calibration

- **Scored:** F_PV's p̂ on the development folds, from fold 2 on. The registration names the one model a veto would use, F_PV or F_P, and the forward window scores that one.
- **Deciding:** BSS > 0 in the Holm family, together with §5.5's calibration and sample conditions.
- **Shown, not deciding:**
  - the other model;
  - log loss and the Brier decomposition;
  - the reliability diagram;
  - a and b, with their intervals;
  - sharpness;
  - the per-coin and per-fold rows;
  - the payoff calibration table (§5.8.1);
  - how far EV moves when a or b sits at the edge of its band.

### 6.3 Q3: volatility and liquidity

**The volatility shrink**, as a sizing variant in the portfolio replay.
- **The comparison:** every one of STRAT-001's opportunities, sized by s_vol, against the same opportunities unscaled. Skips below the minimum follow §5.8.4.
- **R3s:** each draw takes the set of s_vol values realised at the assessable opportunities and gives them to those same opportunities in a random order, pooled over coins.
  - It replays them with the same skip rule.
  - Because R3s uses the same scales, it separates where the shrink falls from how much it shrinks on average.
  - A shuffle within each coin is shown beside it.
- **Deciding statistic:** the maximum drawdown of the equity curve.
  - p = (1 + #{b : MDD(R3s_b) ≤ MDD(shrink)}) / (B + 1), in the Holm family.
- **Condition, non-inferiority:** the one-sided 95% lower bound of RPCD(shrink) − RPCD(unscaled), by the paired block bootstrap, must be at least −m, where m = 0.01 percentage points per capital-day (D12).
  - Revision 1's test, "not lower beyond its 95% interval", passed whenever the interval was wide. This one does not.
- **Reported at both account sizes:**
  - RPCD;
  - total profit after fees;
  - the maximum drawdown;
  - the spread of per-trade returns;
  - the number of skips.
- **What a pass says:** "reduces drawdown compared with random sizing". It is not a profitability claim, and the absolute figures of §6.1's F3 list are reported beside it (§6.7).

**σ̂'s quality:** QLIKE against the naive forecast, as §5.2 sets out.

**The liquidity limits:**
- **Correctness tests:**
  - the approximation's error against stated quote volume, within ε̄ with the true value as the denominator (§5.2), and the hand-worked cases of §12;
  - the limits on hand-built quotes;
  - every missing-input case of §5.8.3.
- **The would-skip counts** from Log only (§5.7).

### 6.4 Data, earlier exposures and independence

#### 6.4.1 Exposure inventory

This lists every earlier look at the data this spec uses, recorded before any of its own results exist. Code facts (§3) are not exposures.

| # | Look | Data | What was seen | What it means here |
|---|---|---|---|---|
| X1 | The volume research, 2026-11-05 (`docs/research/volume-module.md` §5–§6) | 10 coins (BTC, ETH, XRP, BNB, DOGE, SOL, LTC, ADA, LINK, AVAX); 2023-11-06 to 2026-11-05; Coinbase prices; Coinbase, Binance, KuCoin and aggregated volume | STRAT-001's 1h and 15m trades against 9 volume measures, among them `rv_hod20` (v2) and CMF-20; 296 subset tests; the 1.5× rule chosen as best; STRAT-001's gross −0.12% a trade | • v2's definition came from it.<br>• V's development rows from 2023-11-06 are shown as seen (§6.1).<br>• PV-1's volume contestants get a recorded look (Appendix A).<br>• The 1.5× rule is confirmed only forward.<br>• CMF-20 stays out (§6.4.4) |
| X2 | The same research's Kraken agreement check | Kraken's latest 685 hourly bars, 2026-10-07 to 2026-11-04 | volume agreement between venues | none on outcomes |
| X3 | The same research's model experiment | the pattern model, trained 2023-11-06 to 2026-03-31 and held out 2026-03-31 to 2026-11-05, on 10 coins | the pattern model with and without a relative-volume dimension | already in FDS-MH-001's looks for `pattern` |
| X4 | The gate diagnostic, 2026-11-05 | 13 coins, held out 2026-04-05 to 2026-11-05 | the pattern model against random entries | already in `pattern`'s looks |
| X5 | FDS-MDL Tests A and B | BTC and ETH, 2024-07-01 to 2026-10-01 | the pattern model as STRAT-003 | already in `pattern`'s looks |
| X6 | The entry gate's held-out slices | the coins with a model in use, from about 2026-04 | the pattern model | already in `pattern`'s looks |
| X7 | FDS-MH-001's phase B timing run, batch `20261106-143033` | 13 coins, 2021-01-01 to 2025-05-06, walk-forward only | the 7 rules and the pattern model | its 8 trials stay in the trial log, and count in batch 1's report |
| X8 | FDS-SIG-001's studies | simulated nulls; the exchanges' listing metadata | no price outcome | none |
| X9 | The owner's own paper and live trading | the owner's coins in recent months, in the app | trades and their results | Informal. No choice in this spec used it. It is recorded so that a reader knows the recent months have been watched |

**No trained contestant has been scored on any data** as of 2026-11-07, because FDS-MH-001's phase C is not built. So PV-1 is declared before any result of its kind exists.

#### 6.4.2 Development

- **The period:** PV-1's walk-forward, with folds from 2021-01-01 to 2025-05-06: the same dates as batch 1's timing run. Every development score in this spec, STRAT-001's included, ends on 2025-05-06.
- **Never scored: the bars from 2025-05-06 on.**
  - Batch 1's lockbox is the last 18 months before its freeze, so it starts on or after 2025-05-06, whenever batch 1 is frozen.
  - So no model close to batch 1's own is ever scored on batch 1's lockbox months.
- **The seen part:** for V, the rows from 2023-11-06 were seen by X1, so each V result is shown before and from that date.
- **What development decides:** only whether the forward confirmation is worth registering, and what it registers. A development pass is never evidence for enabling anything.

#### 6.4.3 Forward confirmation

**The registration** (phase D) is committed before the window starts, and fixes:
- **the registered artifact** (§5.9): the models fitted on every bar before the registration, the calibrator (§5.5), the payoff tables, σ_ref, the tercile cut points and the code hash;
- **the features,** the placebo's lags δ_j, the veto rule and the strategy configuration;
- **the procedures:** the block rule, B, the seeds, and the families with their conditions (§6.5);
- **the numbers:** the calibration tolerances (D16), the margin m (D12), F3's five requirements (§6.1) and the account sizes;
- **the scope:** the window's start and end, the coins and the venue;
- **the fees:** F3's applicable fee and its source, as read at registration (§6.1), and the 0.50% and 1.20% rows;
- **the wording** of every verdict, and what each verdict leads to;
- **the analysis code,** in its own frozen worktree (FDS-SIG-001 §12.1).

**How the window runs:**
- **Recent bars are used for fitting only.** The forward models use the bars from 2025-05-06 up to the registration for fitting. None of those fits is scored, and nothing from them is reported except the artifact's hash.
- **The window** starts at the first hour after the registration commit. Its length comes from the power simulation (§6.5).
- **Frozen for the whole window:** no refit and no recalibration (D9).
- **Labels:** forecast rows whose T1 label resolves inside the window, and opportunities inside the window. A trade still open at the end is closed at the window's last close.

**The analysis:**
- It runs once, after the window ends, from refetched public candles and the frozen worktree.
- Its results are committed with a tag, `sig4-confirm-1-results`, as FDS-SIG-001's A7 does.

**A change to anything registered cancels the window.**
- The cancellation is committed, with the reason.
- The changed design needs a new registration, and a new window that starts after it.
- A cancelled window can never confirm the changed design: FDS-SIG-001's `check_confirmation` rule.

#### 6.4.4 Independence from FDS-SIG-001

Until a registered round's results are committed:
- **No candidate features:** none of that round's candidates is in this spec's features. For round one: CMF-20's sign and BTC's one-bar lead.
- **No direction scores:** no report here scores the next bar's direction by those rules on that round's window.
- **No changes:** nothing here touches a research branch or `app/signal_audit/`.

Otherwise the two may share calendar time. They test different targets, and neither reads the other's results before its own are committed. A CONFIRMED rule may later join the features through a declared new batch.

### 6.5 Families, power and repeated runs

| Family | Members | Correction | Data | Role |
|---|---|---|---|---|
| FDS-MH-001 batch 1 | its 14 contestants | as declared: a BH screen, then Holm at 5% | its walk-forward and lockbox | unchanged by this spec |
| FDS-MH-001 batch PV-1 | M_P, M_PV, M_PṼ1 (K = 3) | a BH screen, then Holm at 5%, over these 3 | 2021-01-01 to 2025-05-06 | Q1's trading level, secondary. No lockbox |
| FDS-SIG-004 development | 1. F1, forecast value<br>2. F2, the paired decision test<br>3. Q2 skill of F_PV<br>4. Q3 shrink drawdown<br>5. F3 for F_PV's path<br>(K = 5) | Holm at 5%, plus each claim's conditions | the development period (§6.4.2) | decides only whether to register |
| FDS-SIG-004 confirmation | The same five, with Q2 and F3 on the registered model, plus 6: the research's 1.5× rule against R3 (K = 6) | Holm at 5%, plus each claim's conditions | the registered forward window | the only evidence that can enable an effect |
| Exploratory | trees; per coin; other timeframes; regimes; M's paired log loss; the trading-level paired difference | none, labelled exploratory | any | shown, never deciding |

**Trial accounting.**
- Every scored analysis is logged in FDS-MH-001's trial log, with its kind: "trading", "forecast", "decision", "calibration" or "sizing" (Appendix A).
- Each report states the number of distinct trials of each kind so far, across all batches and this spec.

**Power.**
- Before registration, a local simulation of 10 seeded runs estimates, at candidate window lengths:
  - each confirmation test's smallest detectable effect;
  - the chance that the calibration intervals fit inside their bands (§5.5).
- The registration states them. A result below its smallest detectable effect reads "too few to tell".
- STRAT-001 1h makes about 1,450 entries a year on 10 coins (research §6.1), so expect a window of a year or more.

**Repeated runs:** as §6.0 sets out.

### 6.6 Log-only during the confirmation window

Phase E's log-only hook may run while phase D's window is open. These rules keep it from touching the confirmation:

1. **Separate data.** The confirmation is computed only from public candles fetched again after the window ends, by the frozen code (§6.4.3). Phase E's live log is never an input to it.
2. **Only the registered artifact.** The live hook loads only the registered artifact, checked by its hash. Any other model, calibrator or code makes the predictive part unavailable, so the window cannot quietly be run on an updated model.
3. **No outcomes shown.**
   - During the window, the app shows each assessment's facts: time, coin, p̂, EV, the would-be effect and the reason.
   - It shows no outcome-linked figure: no running hit rate, no profit of entries the veto would have taken or dropped, no calibration chart and no score.
   - The assessment table has no outcome column.
4. **Allowed during the window:** operational counts that use no outcome:
   - the number of assessments;
   - unavailability, and its reasons;
   - the protective limits' would-skip counts;
   - the revision check (§5.2.1);
   - the venue compatibility test.
5. **No interim analysis.** Nothing scores the window, or any part of it, before it ends.
6. **Everything an observation could change is frozen.** The thresholds, features, model, calibrator, payoff tables, veto rule, families and verdict wording are all in the registration. Changing any of them cancels the window (§6.4.3).
7. **Looks are recorded.**
   - The Trade History table still shows the owner's own trades, so the window cannot be fully blind.
   - Any look at outcome-linked information about the assessment during the window is written in the run log, with its date and what was seen. One example is joining the assessment log with trade results.
   - These looks are reported with the results.
8. **The owner's settings do not reach the confirmation.**
   - The confirmation replays STRAT-001 from candles, so the owner may turn the protective limits On during the window without affecting it.
   - The predictive veto cannot be On, because its evidence record does not exist until the window's results do.
9. **Phase E's code during the window.**
   - Changes that leave the hashed files untouched are allowed.
   - A change to a hashed file makes the predictive part unavailable until the window ends.

### 6.7 What activation requires

Nothing here activates by itself: phase F is the owner's decision.
- A setting can be turned On only when its requirements have passed on the registered forward window.
- The decision record must show the absolute figures.

| Setting | Requires, on the forward window |
|---|---|
| Entry assessment: Veto | **All of these, each passing as the confirmation family requires:** its primary test under Holm, and its conditions at 5% (§6.5):<br>• **Q2** for the registered model: skill, calibration within tolerance, and the sample floor (§5.5).<br>• **F2** for that model's path: it beats R3. If the model is F_PV, it must also beat F_P in the paired test.<br>• **F3** for that path, at the applicable fee: all five requirements (§6.1) |
| Volatility shrink: On | **Q3:** a drawdown below R3s, and non-inferiority (§6.3).<br>The decision record shows the strategy's absolute net result, with and without the shrink. The shrink is protective, so F3 is not required. But the record must say plainly whether the strategy makes money |
| Participation cap, Spread cap: On | Correctness tests and the log-only counts (§5.7). These limits make no predictive or economic claim |

**The decision record** for any activation states the following, beside the relative results, for the path that would be activated and at the applicable fee:
- net profit;
- return per capital-day;
- return on starting equity;
- the number of trades;
- the maximum drawdown;
- time in the market.

Relative improvement alone never turns the veto On.

**If F2 passes and F3 fails,** the report says that the filter reduces losses on a strategy that still loses money, and the veto stays unavailable. Whether to keep running STRAT-001 at all is a strategy decision, outside this spec (§11).

## 7. Changes proposed to other specs

These are proposals. Each spec stays as approved until the owner accepts the change.

**FDS-MH-001, amendment 1, with exact text in Appendix A.** Best applied before its phase C is built:
- **Named feature blocks:** P, v1, v2 and V. Batch 1 keeps its 26 features, which are P + v1.
- **Probabilities:** `Fitted.probabilities`, saved with the results. The entry decision does not use them.
- **Batch PV-1:** the pair and the placebo, K = 3, with no lockbox. The placebo is a lag of the same coin's volume, by 160 to 170 days, on common rows.
- **A recorded look** for PV-1's volume contestants, because v2 was seen in X1. Batch 1 gets none.
- **Records:** trial kinds, a spec version per batch, and explicit batch lists, so the catalogue's growth never changes batch 1.
- **10-run reports,** as splits of the existing 10,000 draws. They change no draw and no p-value.

**What moved out of FDS-MH-001,** from revision 1's list:
- R3 and R3s;
- the portfolio replay and the equity-curve drawdown;
- the forecast scoring and the paired statistics;
- the volatility-tercile rows.

They concern STRAT-001's exits or this spec's own tests, while FDS-MH-001 holds the strategy fixed ("models, not strategies"). They are built in `app/signal_fusion/` (phase A), and read PV-1's saved outputs.

**FDS-SIG-001 and FDS-SIG-002:** no change. The independence rules of §6.4.4 apply.

**FDS-MX-001:** none needed for version 1, because L comes from the candles. If daily dollar volume is ever read from a connector, `daily_quote_volume` is routed through `ExchangeManager` first.

**FDS-121:** no change to `run_backtest`. The portfolio replay (§6.0) is new code. It uses `run_backtest`'s fill accounting and is tested against it.

## 8. Implementation sequence

### 8.1 No retrospective change

- **Batch 1** (FDS-MH-001 §7) stays exactly as declared: contestants, K = 14, seeds, draws, fold rule, lockbox and pass rule. A test shows that its rule and pattern trials give byte-identical results before and after amendment 1's code.
- **The phase B timing run's 8 trials** stay in the trial log.
- **FDS-SIG-001, FDS-SIG-002 and round one** are untouched.
- **PV-1** is declared here and in amendment 1, before any trained contestant has been scored anywhere. A change after its freeze is a new batch, PV-2, with new keys. PV-1's trials stay.
- **The FDS-SIG-004 registration** can be changed only by cancelling it (§6.4.3).
- **Amendment 1** applies to batches declared after it. `spec_version` records which rules each batch follows.

### 8.2 The sequence

| Step | What | After | Leaves unchanged |
|---|---|---|---|
| S0 | The owner's decisions on revision 2 (§10) | — | — |
| S1 | FDS-MH-001 amendment 1: a docs-only PR with Appendix A's text | S0 and D14 | batch 1 |
| S2 | FDS-MH-001 phase C, as amended: batch 1's trained contestants, PV-1's three, the named blocks, the explicit batch lists, the saved probabilities and the trial kinds | S1 | batch 1's declaration and trials (byte-identity test) |
| S3 | FDS-SIG-004 phase A: `app/signal_fusion/evaluation` | S0. It may run beside S2: no shared files | every registered item |
| S4 | FDS-SIG-004 phase B: `app/signal_fusion`'s blocks S and L, M, the payoff model, EV and the compatibility test | S2 and S3 | — |
| S5 | FDS-MH-001 phases D and E, as that spec sets out | S2 | — |
| S6 | PV-1 frozen and run, walk-forward only, in a sandbox | S2 | Batch 1. No lockbox is opened, and the two batches may run in either order: both are fully declared, and neither has a choice left that the other's results could inform |
| S7 | FDS-SIG-004 phase C: the development run, and `docs/dev/SIG4-REPORT-dev.md` | S4 and S6 | — |
| S8 | FDS-SIG-004 phase D: the power simulation, the registration commit and the frozen worktree. The window starts | S7 and the owner's go-ahead | — |
| S9 | FDS-SIG-004 phase E: the log-only hook, Settings and the table | S4, with no other `pt_trader.py` change open. Before or during the window, under §6.6 | the trader's orders (invariant 3) |
| S10 | After the window: the one analysis, and its results tag | the end of S8's window | — |
| S11 | Phase F: Veto, and the shrink On, for paper | §6.7's requirements met at S10, F3 included for the veto, and the owner's decision on a record that shows the absolute figures | — |

FDS-SIG-001's research window runs independently throughout (§6.4.4).

### 8.3 Phases (one PR each)

#### Phase A — `app/signal_fusion/evaluation`

- **Builds:**
  - the scoring rules and the block bootstrap;
  - the paired forecast, placebo, decision and sizing tests;
  - R3 and R3s;
  - the portfolio replay and its equity curve;
  - F3's five requirements, and its capital-use and drawdown report (§6.1);
  - the verdict lines and their wording rules (§6.1);
  - the 10-run reports.
- **Tests:**
  - the scoring rules match hand-worked values, and scikit-learn's `log_loss` and `brier_score_loss`;
  - the bootstrap is reproducible from its seed, and keeps pairs on the same days;
  - R3 keeps the per-coin veto counts, on assessable, eligible opportunities only;
  - the portfolio replay matches `run_backtest` (§6.0);
  - F3 and the wording rules on constructed paths (§12, item 10);
  - the 10-run report has a row per run;
  - the block-length rule is applied as declared.

#### Phase B — `app/signal_fusion`

- **Builds:**
  - blocks S and L (P and V come from `model_lab.features`);
  - M and its payoff tables, and EV;
  - the compatibility test;
  - the assessment record.
- **Tests:**
  - no look-ahead: poisoning bars after t changes nothing at t;
  - the complete-bar and minimum-history rules;
  - absent and zero-volume hours, per connector;
  - the dollar-volume approximation: §12's hand-worked cases, and the bound against stated quote volume, with the true value as the denominator (§12, item 5);
  - identical definitions on all four connectors;
  - m(f, e) equals the backtester's net return on every trade;
  - costs enter EV once: changing a fee changes EV only through m.

#### Phase C — the development run and its report

- **How:** in a sandbox, on public candles, at 0.50% and at 1.20%, at both account sizes.
- **Output:** `docs/dev/SIG4-REPORT-dev.md`, with Q1's F1, F2 and F3, Q2 and Q3 on the development period, and the seen part shown apart. Nothing is enabled.

#### Phase D — registration and freeze of the forward confirmation

- **What:** everything in §6.4.3, the window's length from the power simulation, and the frozen worktree.
- **Then:** the window runs. The results go in a report, and the verdicts follow §6.1.

#### Phase E — log-only hook, Settings and table (§5.8, §5.10)

- **Defaults:** every setting Off.
- **Effect:** with Log only it changes no decision, so it can run during phase D's window under §6.6.
- **Constraint:** it is not built in parallel with any other change to `pt_trader.py`.
- **Tests:** invariants 1 to 8, every row of §5.8.3's table, and §6.6's display rules.

#### Phase F — Veto, and the shrink On, for paper

- **Only after:** §6.7's requirements pass for that setting on the forward window. For the veto, that includes F3's absolute profitability at the paper account's applicable fee.
- **The owner decides** on a decision record that shows the absolute figures (§6.7). A relative improvement alone is not enough.
- **Live:** only later, under the live-trading spec's own decision.

## 9. Limits and risks

- **Power.** The trading-level tests will likely read "too few to tell" (§4). A forecast-level gain does not make a trading gain.
- **Relative and absolute.** Beating price alone and random vetoes (F2) can coexist with losing money. Only F3 is a profitability finding, and even F3 covers one window of one market history.
- **One market history.** Development covers 2021 to 2025, a single sequence of regimes. The forward window adds one more.
- **Survivorship.** The coins in the data are those still listed today.
- **Venue.** The research data is Coinbase-centred. Other venues' volume can differ in kind: the 2019 wash-trading estimates are in research §4.5.
- **Fees.** The account's rate can change. Each run records the rate it used.
- **The meta-label's sample.** STRAT-001 1h gives thousands of entries. The legacy thinker gives about 116 in 7 months, too few for M.
- **Exposure.** V's development evidence is partly seen (§6.4.1). Only the forward window confirms.
- **History the app never recorded.** Past exchange minimums and spreads are not stored anywhere, so the replays use today's minimums and a fixed allowance.
- **The halt.** It is reported, not modelled, in the replays (§6.0).
- **The payoff model** assumes fixed means within a class and a tercile (§5.8.1). It is checked, not assumed away.
- **Calibration drift.** The calibrator is frozen during the window, so it can go stale. The drift is reported month by month.
- **The dollar-volume approximation** is bounded per bar, with the bound computed from the bar's own OHLC (§5.2), but its typical size has not been measured here. Phase B measures it on the venues that state quote volume.
- **Coins move together.** The block bootstrap moves all coins together, and R2 keeps cross-coin dependence.
- **The forward window takes months,** probably a year or more. Until it closes, nothing predictive is enabled.
- **Looking during the window:** §6.6.

## 10. Decisions for the owner

**Status key:**
- **Ready:** can be approved as written.
- **Revised:** revision 2 or 3 changed it, so it needs approval of the revised text.
- **Number later:** approve the mechanism now; the number needs log-only or simulation evidence before anything is activated.
- **Principle approved:** D14.

| # | Decision | Status | Recommended |
|---|---|---|---|
| D1 | Targets | Revised | T1 for Q1's forecast test only. M (profit after costs under the strategy's own exits) for the decision test, the confidence shown and the veto. T1 never enters an expected value (§5.3) |
| D2 | The model class | Ready | Regularised logistic regression, one pooled model per set of blocks; trees exploratory |
| D3 | The V block | Ready; exposure recorded | v1 and v2. v2 is the research's own measure, so its development rows from 2023-11-06 are shown as seen, and it is confirmed only forward. CMF-20 only after round one's results |
| D4 | The P block | Ready | FDS-MH-001 §5.5 minus its volume feature: 25 features, volatility included. Minimum history: 1,224 closed hourly bars |
| D5 | Fees and costs | Revised | Costs enter once: EV = (1 + μ̂_g) × m − 1, with m from the backtester's fill accounting. The fee comes from the exchange layer, with its source. The allowance per fill is max(½ live spread, 0.05%). Every report at 0.50% and 1.20% |
| D6 | Settings | Revised | Four separate settings: Entry assessment (Off, Log only, Veto); Volatility shrink, Participation cap and Spread cap (each Off, Log only, On). All Off by default. Veto and the shrink's On are greyed out until their activation requirements pass (§6.7). Scale-up is out of scope |
| D7 | A shrunk entry below the exchange minimum | Ready; consequence added | Skipped, never raised. The consequence, now recorded: where 1% of the account is below the minimum, any shrink skips the entry (§3.7) |
| D8 | Unavailable or failing parts | Revised | Off and Log only: no effect. Predictive inputs missing: fails open, recorded. An enabled protective part with a missing input: fails closed, skipped and shown. No blanket exception rule (§5.8.3) |
| D9 | The confirmation data | Revised; number later | A registered forward window. The registered artifact is fitted on every bar before the registration and frozen for the whole window, with no refits. Its length comes from the power simulation |
| D10 | Where the hook sits | Revised | The predictive veto directly after the LLM hook. The protective part directly after sizing, before the risk check. Both modes |
| D11 | The protective limits' numbers | Number later | Proposed: π = 1%, s_max = 0.50%, a quote no older than 60 seconds, and an unavailability notice at 20% over 7 days. None is turned On until the log-only counts per coin and month have been seen |
| D12 | The volatility shrink | Revised; number later | s_vol = min(1, σ_ref / σ̂), with σ̂ chosen by QLIKE and σ_ref fixed per evaluation. On only after §6.7's requirements pass: Q3, with the absolute net result shown in the decision record. Proposed non-inferiority margin: m = 0.01 percentage points per capital-day, to be confirmed by the power simulation |
| D13 | The veto rule | Revised | EV ≤ 0, with p̂ = P(M = 1) passing §5.5 and the payoff model built from the same strategy's trades. Catalogue strategies with their own exits only. The legacy chain gets no expected-value veto |
| D14 | The FDS-MH-001 changes | Principle approved; amendment text to approve | Approve amendment 1 (Appendix A) through its own docs PR before phase C. It names the blocks, adds probabilities, declares PV-1, records the looks, adds trial kinds, makes batch lists explicit and adds the 10-run report. Batch 1 unchanged. Revision 3 changes the placebo to a lag of 160 to 170 days on common rows (AM1-7), with timing tests (AM1-8) |
| D15 | Independence | Revised | §6.4.4 for FDS-SIG-001, plus §6.6 for phase E during phase D's window |
| D16 (new) | Calibration acceptance | Number later | 90% intervals inside: intercept ±0.10 logit, slope 0.80 to 1.20. At least 200 events and 200 non-events. Three outcomes. The power simulation must show that the window can reach this precision |
| D17 (new) | Venue compatibility | Number later | Over 28 days: Spearman ≥ 0.90 for each feature; median absolute p̂ difference ≤ 0.02, and its 95th percentile ≤ 0.05; EV sign agreement ≥ 95%. Repeated every 3 months |
| D18 (new in revision 3) | Findings and activation | Revised; number later | Q1 reports F1, F2 and F3 separately, and only an F3 pass may say "profitable". The veto can be turned On only with Q2, F2 and F3 on the forward window (§6.7). F3's proposed numbers: at least 100 trades and 30 in each half; profit above 0 overall, in each half and without the best coin; a drawdown below the 8% emergency level. The power simulation must show that the window can reach 100 trades |

**By status:**
- **Ready for approval as written:** D2, D3, D4, D7.
- **Need the revised text approved:** D1, D5, D6, D8, D10, D13 and D15 (revision 2), and D12 and D18 (revision 3).
- **Mechanism now, number later, after log-only or simulation evidence:** D9 (the window's length; its no-refit rule is new too), D11, D12, D16, D17, and D18's trade floor.
- **D14:** approved in principle, and supported by the review. Amendment 1 goes through its own docs PR before FDS-MH-001's phase C. Revision 3 corrects its placebo text.

## 11. Out of scope

- **Exits, stops, the DCA rules and the trailing margin.** These belong to the strategy project. Rule 1 keeps them untouched.
- **The existing limits of §3.7:**
  - the minimum raise of an unshrunk entry;
  - a stop for STRAT-001;
  - a halt's effect on exits.

  Each needs its own decision.
- **Scale-up:** any effect that enlarges an entry. It needs its own spec.
- **Other strategies and timeframes.** The predictive part covers STRAT-001 1h at its defaults. Any other configuration needs its own evaluation.
- **New data:** taker-buy volume, funding, open interest, order-book history and trade counts.
- **Live enabling,** under FDS-LIVE-001's own decisions.
- **Building calibration for the LLM's confidence** (§5.5 says only how it could be done).
- **R2 for the legacy thinker:** hashing `pt_thinker.py`, or making the gate run the thinker's own code. Offered as a separate follow-up.
- **FDS-MH-001's phases D and E,** except as amendment 1 changes phase C.

## 12. Acceptance (for the implementation)

1. **No look-ahead.** No feature, target or assessment at t changes when bars after t are poisoned.
2. **Invariants 1 to 8 (§5.8.5)** are tests, including:
   - property tests showing the hook never returns a scale above 1, and never creates an entry;
   - with every setting Off, and with Log only, the trader's orders are byte-identical to `main`'s on a replayed session;
   - exits, sells and DCA triggers are unchanged, and a skip never stops one of them;
   - every row of §5.8.3's table, including a missing quote, a stale quote, and an exception in each part.
3. **Exchange-neutral.** The same features from all four connectors' fixtures, and the venue compatibility test on fixtures.
4. **Complete bars and history.** The forming bar is never an input. Each block's minimum history is enforced, and a gap longer than 24 hours restarts the count.
5. **The approximation** (§5.2). Relative error is ε = |DV̂ − DV| / DV, with the true value as denominator, and its bound is ε̄ = max((TP − L) / L, (H − TP) / H).
   - **Hand-worked cases.** Each is a unit test with these exact values, to four significant figures. The last two columns are the estimate-denominator form, shown for contrast.

   | Case | H | L | C | TP | V | VWAP | DV | DV̂ | ε | ε̄ | error / DV̂ | its bound |
   |---|---|---|---|---|---|---|---|---|---|---|---|---|
   | A: VWAP near TP | 102 | 98 | 100 | 100 | 10 | 100.5 | 1,005 | 1,000 | 0.4975% | 2.041% | 0.5000% | 2.000% |
   | B: VWAP near the low | 120 | 80 | 118 | 106 | 50 | 82 | 4,100 | 5,300 | 29.27% | 32.50% | 22.64% | 24.53% |
   | C: VWAP near the low, TP near the high | 200 | 100 | 200 | 166.67 | 3 | 101 | 303 | 500 | 65.02% | 66.67% | 39.40% | 40.00% |
   | D: VWAP near the high | 50 | 40 | 41 | 43.667 | 6 | 49.5 | 297 | 262 | 11.78% | 12.67% | 13.36% | 14.50% |
   | E: a flat bar | 10 | 10 | 10 | 10 | 7 | 10 | 70 | 70 | 0 | 0 | 0 | 0 |

   - **Case C** shows why the denominator matters. Revision 2's (H − L) / TP is 60.00% there, below the true ε of 65.02%. So that bound fails against the true value, and must not be used.
   - **Case D** shows the high-side term binding: (H − TP) / H = 12.67% is above (TP − L) / L = 9.167%.
   - **F: zero volume** (H = 10.5, L = 9.5, C = 10, V = 0): DV̂ = 0. The hour counts as 0 in sums and medians, no ε or ε̄ is computed, and nothing divides by zero.
   - **G: invalid bars.** Each of these gives a missing DV̂, never 0 and never an exception: L = 0; L < 0; H = 9 with L = 10; C = 11 with H = 10.5; O outside [L, H]; V = −1; a NaN or infinite price or volume. The hour is left out of the participation median and counted. 25 invalid hours in a row restart the series.
   - **H: the participation bound.** Three hours, with (DV̂, ε̄) of (100, 10%), (200, 20%) and (300, 5%). The median DV̂ is 200 and ε_max is 20%, so the true median is at least 200 / 1.2 = 166.67. An entry of $2 at π = 1% passes on the estimate (2 / 200 = 1.0%), and the record states its share of the true median is at most 1.2 × 1% = 1.2% (2 / 166.67).
   - **On venues that state quote volume:** for every valid bar, |DV̂ − Q| ≤ ε̄ × Q + r, where Q is the stated quote volume and r is half a unit in the last digit the venue states. No test uses DV̂ as the denominator, or claims a bound tighter than ε̄.
6. **Costs once.** m(f, e) equals the backtester's net return on every trade, and T1 never reaches EV.
7. **Scoring and calibration.**
   - The scoring rules match reference values.
   - Calibration is never fitted on the rows it is scored on, and the climatology comes from training rows.
   - The three calibration outcomes come out right on constructed samples: a large calibrated one, a miscalibrated one, and a small one.
8. **Statistics.**
   - The bootstrap, R3 and R3s are reproducible from their seeds.
   - Pairs share the same days in every draw.
   - The portfolio replay reproduces `run_backtest`.
   - Every simulation reports 10 seeded runs, pooled and per run.
9. **The placebo's timing** (§6.1; Appendix A, AM1-8).
   - **Encoded time:** on fixture candles, set each V value to its own source hour. Then every placebo value Ṽ_j(c, t) equals t − δ_j exactly, so it is at least D earlier than t. A forward move or a wrap would show as a value at or after t.
   - **Poisoning at the boundaries:** at every hour t in the fixtures, corrupt every bar after t, prices and volumes alike. Every placebo value at t and before is unchanged, and so is every fit whose training rows end by t. The hours checked include each series' first common hour, the hours just after a gap longer than 24 hours, and the first and last hour of every fold and of the walk-forward.
   - **Start and gaps:** at a series' start, and after a gap longer than 24 hours, Ṽ_j is missing for exactly the declared span. It is never taken from before the gap, from the series' end, or from another coin.
   - **Paired rows:** M_P, M_PV and every placebo variant are fitted and scored on identical row sets in every fold, compared by a hash of the row index.
   - **Offsets:** every δ_j lies from 3,841 to 4,079 hours and is not a multiple of 24, and the seeds reproduce the declared δ_1 to δ_5 (3,930, 4,076, 3,850, 4,062 and 3,857 hours).
10. **Findings and wording** (§6.1, §6.7), on constructed paths:
    - **Loses less, still loses:** a path that beats F_P and R3 but loses money gets F2's "reduces losses" line, and fails F3.
    - **One coin:** a path profitable only through one coin fails F3's requirement 4.
    - **The halt level:** a path that reaches the 8% level fails requirement 5.
    - **Too few trades:** a path with 99 trades, or with 29 in one half, reads "Not assessable".
    - **Activation:** the Veto setting stays greyed out unless F3 has passed.
    - **Wording:** no verdict line except an F3 pass contains "profitable" or "makes money".
11. **Amendment 1.** The tests listed in Appendix A, AM1-8.
12. **During a window,** the app shows no outcome-linked figure (§6.6).
13. **Settings.** Every new key defaults to Off. Saved settings keep their meaning: decisions with the new keys absent equal `main`'s.
14. **The suite.** The full suite passes with 0 failures, Black is clean, and CI's flake8 is clean.

## 13. Remaining ambiguities

What revisions 2 and 3 leave open, and when each will be settled:

1. **Absent hours per connector.** Whether each connector returns an hour with no trades as a zero-volume bar, or leaves it out, is not yet established. Phase B records it from fixtures. Until then the rule is that an absent hour inside a kept gap counts as zero volume.
2. **Revisions after close.** Whether a venue revises a bar's volume after it closes is not measured. Phase E's log compares live values with refetched ones. A large difference would mean the confirmation, which uses refetched bars, does not match what the live hook saw. The report would say so.
3. **The 50-day average.** FDS-MH-001's phase C defines whether P's 50-day average uses hourly closes or completed UTC days. This spec takes the larger need, 1,224 bars.
4. **History the app never recorded.** Past exchange minimums and spreads are not stored anywhere, so the replays use today's minimums and a 0.05% allowance per fill.
5. **The halt in replays.** It is reported, not modelled. The owner may prefer that a halt ends a path; that variant is shown beside the deciding one.
6. **M's base rate at 0.50%.** It has not been measured yet; the research gives 15.6% at 1.20%. A tolerance in logit units means a different probability error at a different base rate, so phase C reports both.
7. **The payoff model's assumption.** The win and loss means are fixed within a volatility tercile. Phase C's payoff calibration table shows whether that holds.
8. **Which model Q2 confirms.** The registration names F_PV or F_P after development. This spec does not decide which.
9. **Changed strategy settings.** Changing STRAT-001's parameters, timeframe or overlays in Settings makes the predictive part unavailable. Evaluating another configuration needs a new batch and a new registration. Whether the owner wants more than the defaults evaluated is open.
10. **The owner's account size.** It is not known to this spec. If the account is small, §6.3's $100 rows are the relevant ones, and the owner can say so.
11. **The window's length.** It is unknown until the power simulation. If the simulation asks for much more than a year, the owner may decide not to proceed.
12. **Coins with no assessable rows.** In the forward window, a coin served only from Kraken, or newly listed, may have no assessable rows. The confirmation reports each coin's counts.
13. **Informal observation (X9).** It is recorded, but cannot be prevented.
14. **The references** below were not re-read for this draft.
15. **What the placebo still carries.** If V is autocorrelated at 160 to 170 days, the lagged placebo carries some of V's own information. §6.1's check shows it, and it can only make the placebo condition harder to pass. Longer lags, if the check fires, would be a later batch's choice, not this one's.
16. **Rows the placebo costs.** Common rows start about 201 days into each series, against 51 days for P alone, so the pair is scored on fewer rows than P and V alone would allow. The report gives the count per coin.
17. **F3 at the paper account's fee.** Which rate paper fills record depends on the fee source at registration: the account's rate or the published default. F3 is judged at that rate. A pass at 0.50% does not carry over to 1.20%, and the report shows both.
18. **F3's numbers** are proposals (D18): 100 trades, 30 in each half, and the 8% level. The power simulation shows whether the window can reach the trade floor.

## References

Standard sources, cited from the literature as commonly given. They were not re-read for this draft. Phase A checks each formula against its source before it is used.

- Abdi, F. and Ranaldo, A. (2017). A simple estimation of bid-ask spreads from daily close, high, and low prices. *Review of Financial Studies* 30(12).
- Berger, R. L. (1982). Multiparameter hypothesis testing and acceptance sampling. *Technometrics* 24(4).
- Cox, D. R. (1958). Two further applications of a model for binary regression. *Biometrika* 45.
- Gneiting, T. and Raftery, A. E. (2007). Strictly proper scoring rules, prediction, and estimation. *JASA* 102.
- Hall, P. and Wilson, S. R. (1991). Two guidelines for bootstrap hypothesis testing. *Biometrics* 47.
- Künsch, H. R. (1989). The jackknife and the bootstrap for general stationary observations. *Annals of Statistics* 17.
- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley, ch. 3 (meta-labelling) and ch. 4 (sample uniqueness).
- Murphy, A. H. (1973). A new vector partition of the probability score. *Journal of Applied Meteorology* 12.
- Parkinson, M. (1980). The extreme value method for estimating the variance of the rate of return. *Journal of Business* 53.
- Patton, A. J. (2011). Volatility forecast comparison using imperfect volatility proxies. *Journal of Econometrics* 160.
- Platt, J. (1999). Probabilistic outputs for support vector machines and comparisons to regularized likelihood methods.
- Politis, D. N. and Romano, J. P. (1992). A circular block-resampling procedure for stationary data. In LePage, R. and Billard, L. (eds.), *Exploring the Limits of Bootstrap*. Wiley.
- Riley, R. D. et al. (2021). Minimum sample size for external validation of a clinical prediction model with a binary outcome. *Statistics in Medicine* 40.
- J.P. Morgan/Reuters (1996). *RiskMetrics: Technical Document*, 4th ed. (EWMA, λ = 0.94).
- Schuirmann, D. J. (1987). A comparison of the two one-sided tests procedure and the power approach for assessing the equivalence of average bioavailability. *Journal of Pharmacokinetics and Biopharmaceutics* 15.
- Van Calster, B. et al. (2016). A calibration hierarchy for risk models was defined: from utopia to empirical data. *Journal of Clinical Epidemiology* 74.

## Appendix A. FDS-MH-001 amendment 1: exact text

**How it is applied:**
- By its own docs-only PR (§8.2, step S1), after the owner accepts D14, and before any of FDS-MH-001's phase C code.
- Each item below gives the place in `docs/dev/specs/FDS-MH-001-multi-model-harness.md`, and the exact text to insert.
- Nothing is deleted. Nothing in batch 1's declaration (§7) is changed: AM1-9 only adds a sentence saying so.
- The keys, seeds and dates are proposals until accepted.
- Replace `YYYY-MM-DD` with the date of acceptance.

### AM1-1 — the header

After the line that begins `**Status:**`, insert:

```markdown
**Amendments:** amendment 1 (proposed in FDS-SIG-004 Appendix A; accepted by the owner on YYYY-MM-DD). It names feature blocks (§5.5), adds probability outputs (§5.5), a report of repeated runs (§5.6), a look at a feature (§5.7), trial kinds, spec versions and explicit batch lists (§5.8), and batch PV-1 (§7a). Batch 1 (§7) and every trial logged before amendment 1 are unchanged.
```

### AM1-2 — §5.5, feature blocks

After the paragraph that begins "That makes 26 features", insert:

```markdown
**Feature blocks** (amendment 1). `features.py` names the features in blocks, and a contestant names the blocks it uses:
- **P:** the 25 features above other than the volume feature.
- **v1:** the volume feature above, log of 24-hour volume over the 30-day daily mean.
- **v2:** log of the hour's volume over the mean volume of the same UTC hour on the 20 previous days. A zero mean makes it missing.
- **V:** v1 and v2.

Batch 1's pooled contestants use P and v1, which are the 26 features above, exactly as §7 declares them. Volume is base-asset volume, defined the same way on every connector. A placebo replaces V with the same coin's V from a fixed number of hours earlier (§7a). No block contains Chaikin Money Flow or BTC's one-hour return, the candidates of FDS-SIG-002's round one.
```

### AM1-3 — §5.5, probability outputs

After the `Fitted` code block, and before "**Thresholds.**", insert:

```markdown
`Fitted` may also give `probabilities(coin, close_s)`: one probability of its target per hour, or `None` (amendment 1). A trained contestant saves them with its results, for FDS-SIG-004's forecast scores. Its entries are still decided only by `entries`, and no pass rule in this spec reads the probabilities.
```

### AM1-4 — §5.6, repeated runs

After the "**Draws.**" bullets, and before "**p-values.**", insert:

```markdown
**Runs** (amendment 1). Every batch's B = 10,000 draws, seeded `seed + b`, are also reported as 10 runs of 1,000 consecutive draws: run r is draws 1,000 r to 1,000 r + 999. Each run's p is shown beside the p-value, which is still computed from all 10,000. This changes no draw and no p-value, batch 1's included.
```

### AM1-5 — §5.7, a look at a feature

At the end of the "**Seen already**" bullets, add:

```markdown
  - **A look at a feature** (amendment 1). When a study looked at how a feature relates to trade outcomes, the look is recorded for every contestant that uses the feature, with the months and coins it covered. The volume research (2026-11-05) looked at v2, as `rv_hod20`, against STRAT-001's trades on 10 coins from 2023-11-06 to 2026-11-05. It is recorded for batch PV-1's `pv.linear.t1.PV.q50` and `pv.linear.t1.PVp.q50`. None of the research's measures is v1, and it looked at no batch 1 contestant's results, so batch 1 gets no new look; its report lists the volume research as related work.
```

### AM1-6 — §5.8, records

After the "**Trial log:**" bullet, insert:

```markdown
- **Kinds of trial** (amendment 1). A trial line may carry `kind`: "trading" for a contestant's trades scored against R1 and R2, or "forecast", "decision", "calibration" or "sizing" for FDS-SIG-004's analyses. A line without `kind` is "trading". The window counts distinct trials of each kind.
- **Spec version** (amendment 1). A batch file records `spec_version`, the version its batch was declared under: "1" for batch 1 (declared in §7 on 2026-11-06), "1.1" for a batch declared by amendment 1 or later. A batch is run by the rules of its own version, whenever it is frozen.
- **Batch membership** (amendment 1). Each batch's contestants are an explicit list in `catalogue.py` (`BATCH_1`, `BATCH_PV_1`). Adding a contestant to the catalogue never adds it to a declared batch.
```

### AM1-7 — a new §7a

After §7 and before §8, insert:

```markdown
## 7a. Batch PV-1 (amendment 1; declared here, before any result)

The price-only and price-plus-volume pair for FDS-SIG-004's Q1, with a placebo. It changes nothing in batch 1.

- **Coins:** batch 1's 13.
- **Window:** from 2020-01-01 00:00 UTC, or each series' first bar if later. Fold 1 starts on 2021-01-01, folds are 3 months on batch 1's dates, and the walk-forward ends at 2025-05-06 00:00 UTC.
- **No lockbox is opened.** No bar from 2025-05-06 on is scored by this batch. Its final check is FDS-SIG-004's registered forward window, so its best verdict here is "Passed; final check not run".
- **Trade rules and fees:** as batch 1's (§7): the trader's defaults with neural DCA off, and 0.50% plus 0.05% slippage.
- **Target and model:** T1 (§5.5). Logistic regression with an L2 penalty, C = 1, features standardised on training rows; entries at the top 50%. Each fit saves its probabilities (§5.5).
- **Seeds:** R1 from 500000, R2 from 600000, fits from 0. The placebo's lags: for j = 1 to 5, with r = `random.Random(700000 + j)`, first a_j = `int(10 * r.random())`, then b_j = `1 + int(23 * r.random())`.
- **The placebo, a lag.**
  - At decision hour t of coin c, Ṽ_j(c, t) = V(c, t − δ_j): the same coin's V block as computed at hour t − δ_j.
  - δ_j = 3,840 + 24 a_j + b_j hours. That is 160 to 170 days, at least D (§5.6), and never a whole number of days.
  - The seeds give δ_1 to δ_5 = 3,930, 4,076, 3,850, 4,062 and 3,857 hours.
  - It uses only bars that closed by hour t − δ_j. Nothing is moved forward, and nothing wraps. So it never reads a bar after its own hour, and none from 2025-05-06 on.
- **Missing history.** Ṽ_j(c, t) exists only when hour t − δ_j is in the same series as t (§5.2: after the last gap longer than 24 hours) and V exists at that hour. Otherwise it is missing. A missing value is never filled in, carried forward, or taken from another coin or time.
- **Common rows.**
  - The three contestants and placebo variants 2 to 5 are fitted and scored only at the hours where P, V and every Ṽ_j exist. Elsewhere they are undecided (−1), so every comparison in this batch uses the same hours.
  - Each fold's fit uses only common rows before the fold, purged as §5.4 sets out.
  - A coin joins once it has common rows, about 201 days after its series starts.

| # | Key | Blocks | Tested here |
|---|---|---|---|
| 1 | `pv.linear.t1.P.q50` | P | yes |
| 2 | `pv.linear.t1.PV.q50` | P + V | yes |
| 3 | `pv.linear.t1.PVp.q50` | P + Ṽ_1 | yes |
| — | placebo variants 2 to 5 | P + Ṽ_2 to Ṽ_5 | forecast scores only, logged as "forecast" trials |

K = 3. The Benjamini-Hochberg screen and Holm run over these 3, separately from batch 1. FDS-SIG-004 §6.5 lists every family.

**Order.** PV-1 is frozen only after amendment 1's code is merged. It and batch 1 may run in either order: both are fully declared, and PV-1 opens no lockbox.
```

### AM1-8 — §8, phase C

After phase C's **Tests:** list, insert:

```markdown
**Amendment 1 adds:**
- `features.py`: the named blocks (§5.5) and the placebo's lag (§7a).
- `contestants.py`: `Fitted.probabilities`, and PV-1's three contestants.
- `catalogue.py`: `BATCH_1` as the explicit list of §7's keys, and `BATCH_PV_1`; the look of §5.7.
- `batch.py`: `kind` and `spec_version`; saved probabilities; the report of 10 runs.

**Amendment 1's tests:**
- `BATCH_1` equals §7's 14 keys and the reference, in order, and adding a contestant to the catalogue leaves it unchanged;
- on the phase B fixtures, the seven rules and the pattern model give byte-identical `results.json` before and after amendment 1's code;
- a trial line without `kind` reads as "trading";
- the placebo's timing:
  - with each V value set to its own source hour, every Ṽ_j(c, t) equals t − δ_j;
  - corrupting every bar after any hour t changes no placebo value at or before t, and no fit whose training rows end by t. The hours checked include each series' first common hour, the hours after a gap longer than 24 hours, and the first and last hours of every fold;
  - Ṽ_j is missing for exactly the declared span at a series' start and after a long gap, and is never taken from the series' end or from another coin;
- every δ_j lies from 3,841 to 4,079 hours and is not a multiple of 24, and the seeds reproduce δ_1 to δ_5 = 3,930, 4,076, 3,850, 4,062 and 3,857 hours;
- the three contestants and the placebo variants use identical row sets in every fold;
- phase B's look-ahead test (a decision from bars cut at an hour equals the decision from all bars) passes for `pv.linear.t1.PVp.q50`;
- P has 25 features, P with v1 is batch 1's 26, and no block contains Chaikin Money Flow or BTC's one-hour return;
- the 10-run report's runs pool to the batch's p-value exactly.
```

### AM1-9 — §7, batch 1

After "K = 14.", insert:

```markdown
Amendment 1 leaves this batch as declared: its contestants, K, seeds, draws, fold dates, lockbox and pass rule.
```

### AM1-10 — §10, decisions

Add a row at the end of the table:

```markdown
| D12 | Amendment 1 (FDS-SIG-004 Appendix A) | **Accepted by the owner, YYYY-MM-DD.** Batch 1 is unchanged; batch PV-1 is added (§7a) |
```

### AM1-11 — §12, acceptance

In "**Phases B and C:**", add a bullet:

```markdown
  - amendment 1's tests (§8, phase C) pass, batch 1's byte-identity test included;
```
