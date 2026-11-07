# FDS-SIG-004 — Price-Volume Signal Fusion, Confidence and Volatility Assessment

**Issue:** none yet. Raise "Assess entries with price, volume, confidence, volatility and liquidity, behind the existing controls" and link it here.
**Target repo:** `sjackson0109/powertraderai`
**Branch:** this spec is on `docs/fds-sig-004`, cut from `main` at `e0d837a` (PR #228 merged). Each phase is built on its own `feat/sig4-<letter>-…` branch, cut from `main` after the previous phase is merged.
**Recommended model:** Claude Opus 5.5, effort high, for phases A to D (statistics, look-ahead, the replays). Sonnet 5.5, effort high, for phase E (the hook, Settings and the table).
**Run log:** `docs/dev/RUN-LOG-sig4-1.md`, from phase A.
**Status:** draft for the owner's review, 2026-11-07. Nothing is implemented. This document changes no code, trainer, strategy, runner or trader, and it registers nothing. §10 lists the decisions, each with a recommended answer.
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

---

## 1. Objective

Answer three questions with evidence, and define one design that combines the answers without weakening any existing control.

1. **Q1: does volume add predictive value beyond price?**
   - Compare a price-only model with the same model plus volume, with everything else held the same.
   - Judge it first by forecast quality, then by trading results after fees.
2. **Q2: how should confidence be calibrated?**
   - Define a confidence as a calibrated probability.
   - Measure it with proper scoring rules.
   - Allow it to affect a decision only when it is shown to carry information beyond the base rate.
3. **Q3: how should volatility and liquidity influence trading decisions?**
   - Volatility: as a forecast input and a risk-based size reduction, never as an entry signal.
   - Liquidity: as a cost and a hard limit, never as a signal.

**The design** is one assessment per entry, computed from price, volume, volatility and liquidity.
- It may only **veto**, or **shrink**, an entry that the active strategy or the thinker already wants.
- Every existing control still applies after it, in today's order.

**What this spec produces:** a design, an evaluation protocol and a staged plan. It wires nothing to trading. As with FDS-SIG-001 §14 and FDS-MH-001 D10, enabling any effect is a later decision for the owner (§8, phase F).

**It runs alongside FDS-SIG-001.** It develops and evaluates its design while FDS-SIG-001's research window runs, without touching that window (§6.4).

## 2. Rules

1. **Only veto or shrink.**
   - Volume, confidence, volatility and liquidity never open a trade or make one larger.
   - They never delay or block an exit, never trigger or change a DCA buy, and never move a stop.
   - They may only veto, or shrink, an entry the existing path already wants.
2. **Existing controls stay.** Every existing control applies after the assessment, unchanged and in today's order (§3.1).
3. **One implementation.**
   - The harness, the backtester and the trader call the same assessment code, and its files are hashed into the record of the model in use.
   - When the hash differs from the evaluated one, the assessment counts as unavailable (§5.9).
4. **Exchange-neutral.**
   - Every input is defined the same way on every connector. It is computed from the candles and quote of the venue that prices the order, read through the exchange layer, primary exchange first, then the fallbacks (FDS-MX-001).
   - Nothing that only some connectors offer is an input.
5. **Evidence first.**
   - An effect is enabled only after its evidence has passed on data no one had looked at.
   - Every earlier look is recorded, as FDS-MH-001 §5.7 does.
6. **A confidence is a calibrated probability** of a declared event, or it is not called a confidence.
7. **Simulations run locally, as 10 seeded runs,** reported pooled and per run (owner, 2026-11-06).
8. **Settings, not files.**
   - Every option is reachable from Settings.
   - In-app text states facts only: no spec names and no design caveats.
9. **Off by default.** Every new setting defaults to off, and saved settings keep their meaning.

## 3. The review: three components today (`main` at `e0d837a`)

File references are relative to `app/`.

### 3.1 One entry, end to end

| Step | Legacy chain (`strategy.engine = "legacy_neural"`) | Strategy catalogue (the default: STRAT-001, 1h, no overlays; `pt_settings_manager.py:131-137`) |
|---|---|---|
| Signal | The thinker matches the last closed bar's body % against the trainer's memories, per timeframe (`pt_thinker.py:929-931, 1033`). It writes long and short counts, 0 to 7 (`pt_thinker.py:1521`). An entry needs long ≥ `trade_start_level` (3) and short = 0 (`pt_trader.py:2894-2905`) | `SignalEngine.decide` runs STRAT-001 on the last closed 1h bars (`signal_engine.py:261-330`). STRAT-001's defaults are a TEMA 12/48 crossover, held for 2 confirmation bars, that holds while ADX < 20 (`strategies/catalogue.json:29-37`; `strategies/trend_crossover.py:45-72`) |
| Evidence gate | The entry gate, at training time: a random-entry baseline, scored by return per capital-day. A model is published only on a pass (`pt_pattern_trainer.py:1615-1623`) | **None.** `signal_engine.py` and `strategies/` import neither `entry_gate` nor `model_gate` |
| LLM hook | Both modes, after the signal and before sizing (`pt_trader.py:2908-2913`). It can only confirm or veto, never create; any failure lets the entry go ahead (`pt_trader.py:1327-1338`). The default mode is `log_only` (`llm_settings.py:75`) | same |
| Size | 1% of the account (Start allocation). When that is below the exchange's minimum, it is raised to the minimum plus room for the spread, two taker fees and a 2% margin (`position_sizing.py:91-106`; `pt_trader.py:2017-2037`) | same |
| Risk check | The coin budget (Max per coin 10%) caps a buy, except that the minimum is always allowed, even above the budget (`pt_trader.py:1680-1689`). A saved halt, and the drawdown levels 3%, 5% and 8%, where 8% halts trading (`pt_settings_manager.py:123-127`) | same |
| Placement | Pinned to the mode the trader started in. Preview places nothing. Paper fills pay the taker or maker rate of the venue whose quote priced them (`trading_mode.py:579-583, 773-795`) | same |
| Exits | DCA buys of ×2 at −2.5%, −5%, −10% and further levels. The trailing profit margin starts at +5% (+2.5% after a DCA) with a 0.5% gap (`pt_trader.py:2593-2735`) | STRAT-001's exit when the averages cross back. DCA and the trailing margin are skipped (`pt_trader.py:2591`). **No stop** unless an overlay is added |

### 3.2 What the decisions use

| Information | Used today | Where |
|---|---|---|
| Price | Thinker: open and close only. Trainer: open, close, high and low. STRAT-001: close, plus high and low for ADX | `pt_thinker.py:494-503`; `pt_pattern_trainer.py:538-545`; `strategies/trend_crossover.py:45-66` |
| Volume | **No decision reads candle volume.**<br>• The runner's rows carry it, but the thinker never reads it: `pt_thinker.py` contains no "volume".<br>• The trainer only hashes it.<br>• No catalogue strategy uses it.<br>• The one route is the 24-hour volume in the LLM's prompt, which matters only in the LLM's confirm and veto modes | `market_data/runner_history.py:99-114`; `pt_pattern_trainer.py:605-617`; `llm_research_engine.py:254` |
| Confidence | **None is calibrated, and none changes a size.**<br>• The thinker's counts and STRAT-001's ADX are thresholds.<br>• The LLM's 0–100 confidence is self-reported, and is shown and filtered on only.<br>• `Signal` and `Decision` have no confidence or size field.<br>• A harness contestant returns 1, 0 or −1 per hour.<br>• `pt_neural_processor.py` has a confidence-weighted combination, but nothing imports it | `llm_signals.py:94-101`; `llm_gate.py:344-368`; `strategies/base.py:37-42`; `strategies/runner.py:133-143`; `model_lab/contestants.py:45-47` |
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
- **Repeated runs:** a batch is evaluated once, not as 10 seeded runs.
- **Not built yet:** the lockbox opening. Phases C, D and E.

### 3.4 FDS-SIG-001 and FDS-SIG-002, the audit (merged `e0d837a`)

- **The test:** a pre-registered test, per coin and per timeframe, of whether a rule calls the next bar's direction better than the best constant.
  - Holm over the family, F = 76 for round one.
  - Fresh windows only, and a confirmation round.
  - Each round is run from its own frozen worktree (§12.1).
- **Round one:**
  - SIG-A, the sign of Chaikin Money Flow over 20 bars. It is a volume rule.
  - SIG-B, BTC's one-bar lead.
  - It is not registered, and decisions 1 to 6 are open.
- **The order is fixed (§14):**
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
| History | years | years | **latest 720 bars** | years (some symbols from 2022-09-29) |
| Trading fees | the account's rate with a key, else the published default | the account's rate with a key, else the published default | public | the published default only |

- **No order-book or trade history is stored anywhere.**
- **The shared market-data manager connects with empty credentials** (`pt_multi_exchange.py:486-490`), so its Coinbase fee falls back to the published 1.20% taker rate (`pt_exchange_abstraction.py:268-273`). The owner's account reads 0.50%.
- **The audit's market methods** (`spot_markets`, `daily_quote_volume`) are called on connectors directly, not through `ExchangeManager`. The audit is their only user today.

### 3.6 What the review found, and what the design does about it

| # | Finding | Design response |
|---|---|---|
| R1 | **The default path has no evidence gate.** Catalogue entries face none, and STRAT-001 shows no gross edge (−0.12% a trade, research §6.1) | The assessment is the first evidence-based check that could reach catalogue entries, once it has evidence (§5.8, §6) |
| R2 | **The gate tests the replica, not the thinker.** It replays `pattern_model`'s copy of the thinker's decision (`model_gate.py:206-252`), and the code hashed into a model's record leaves `pt_thinker.py` out (`pt_pattern_trainer.py:1157-1163`). In legacy mode, the gate does not test byte-for-byte what trades | Rule 3: one implementation, hashed (§5.9). Fixing R2 for the thinker is a separate follow-up (§11) |
| R3 | **No interface carries a probability or a size**: `Signal`, `Decision` and `Fitted` | A separate assessment record, with no change to the strategy interface (§5.8) |
| R4 | **The LLM hook is the one place both modes pass,** after their signal and before sizing | The assessment hook goes directly after it (§5.8) |
| R5 | **The minimum-order raise can exceed the coin budget** | A shrunk entry below the minimum is skipped, never raised (§5.8) |
| R6 | **Quote volume is missing on Coinbase.** Base volume is on every connector; per-bar quote volume is not on Coinbase | Features use base volume, scale-free. Dollar volume is used only as a labelled approximation, defined once for every connector (§5.2) |
| R7 | **Two fee rates.** The shared layer charges Coinbase's default of 1.20%; the account reads 0.50% | Costs are read through the exchange layer with their source recorded. Evaluations report both 0.50% and 1.20% (§5.7) |
| R8 | **The harness cannot do what Q1 needs.** It cannot score forecasts or pairs, or report by volatility regime, and phase C has no price-only twin | Amendments to FDS-MH-001, proposed in §7 |
| R9 | **The volume research looked at the lockbox.** It examined volume against STRAT-001's entries and the pattern model over 2023-11-06 to 2026-11-05 (10 coins, Coinbase), which covers all of batch 1's lockbox (from 2025-05-06) | Every contestant with volume features gets that look recorded, and volume is confirmed on fresh forward data (§6.4) |
| R10 | **Dead code.** `pt_neural_processor`, `RiskManager.validate_trade` and `calculate_position_size`, `pt_circuit_breaker` and `trade_proposal_approval` are not used by the trader | They are left alone and not revived (§5.4) |
| R11 | **No stop by default** | Exits are out of scope (§11) |

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
candles and quote of the venue that prices the order (exchange layer, primary first)
  → features: P (price and volatility), V (volume), S (volatility forecast), L (liquidity)
  → forecast: p̂, a calibrated probability of a declared event                (§5.3–5.5)
  → assessment: expected value after costs, volatility scale, liquidity limits (§5.6–5.8)
  → effect: off | log only | veto | veto and shrink                           (§5.8)
  → every existing control, unchanged, in today's order                        (§3.1)
  → order
```

### 5.2 Feature blocks

Every feature comes from closed bars only, on the venue that prices the order.

**Every feature is scale-free:** a log, ratio or z-score of the market's own history on the same venue. So coins, and venues of very different sizes, can share one model. Coinbase carries 1–28% of the volume of three venues combined (research §6.7).

**P, price and volatility.**
- FDS-MH-001 §5.5's 26 features, minus its one volume feature: 25 features.
- They cover returns, realised and Parkinson volatility, trend distances, drawdown, the last bar's body and wicks, and BTC's context.
- Volatility belongs in P, so volume gets no credit for standing in for it (§4).

**V, volume.** Base volume only, and a small declared set (decision D3):
- **v1:** log of 24-hour volume over the 30-day daily mean (FDS-MH-001's feature);
- **v2:** log of the bar's volume over the mean volume of the same UTC hour on the 20 previous days (the research's main measure, research §5.4). Weekend volume runs at about 0.7×.

How V is computed:
- **Warm-up:** 20 days, which is 480 hourly bars. That fits in Kraken's 720.
- **Zero or missing volume:** a zero denominator or a missing bar makes the feature missing. The row then has no assessment, as CMF abstains in FDS-SIG-002.
- **Excluded for now:** CMF-20 and BTC's one-bar lead are FDS-SIG-001 round-one candidates, so they stay out (§6.4).

**S, the volatility forecast.**
- **What it is:** σ̂, a forecast of the next 24 hours' volatility, chosen from declared candidates by QLIKE loss on the development folds (Patton 2011).
- **The candidates:**
  - an EWMA of hourly squared log returns, λ = 0.94 (RiskMetrics 1996);
  - Parkinson range volatility over 24 hours (Parkinson 1980);
  - the last 24 hours' realised volatility, the naive comparator.
- **The rule:** the chosen candidate must beat the naive one, or the naive one is used.

**L, liquidity.**
- **Approximate dollar volume of a bar:** typical price (H + L + C) / 3 × base volume.
  - It is labelled approximate everywhere and never called quote volume (FDS-SIG-001 §4).
  - **Its error:** the bar's true VWAP and its typical price both lie between its low and high. So the relative error is at most (H − L) / typical price for a bar, and smaller when summed from finer bars.
  - **On venues that state quote volume** (Binance, KuCoin, and Kraken through VWAP × volume), the stated figure is used only to measure this error, in a test. It is never used as an input, so the definition is the same on every connector (rule 4).
- **Hourly liquidity:** the median hourly approximate dollar volume over the 20 previous days.
- **The live spread** at the decision: (ask − bid) / mid, from the quote the trader already reads.
- **Historical cost:** 0.05% slippage a fill, as the gates use. An OHLC estimate of the spread (Abdi and Ranaldo 2017) is reported as a sensitivity.
- **Fees:** maker and taker rates through the exchange layer, the account's rate first, with the source recorded ("account" or "published default").

**Not inputs** (rule 4: not on every connector, or no history):
- trade count;
- taker-buy volume;
- order-book depth;
- funding rates;
- open interest.

### 5.3 Targets

- **T1, market level.** FDS-MH-001's "clean win": from hour t's close, the price reaches the first profit line before the first DCA level, within 336 hours.
  - Both barriers come from the batch's trade rules, and hits are judged on hourly highs and lows. The base rate is about 0.34.
  - **Used for:** Q1's primary test. It has many rows, does not depend on the strategy, and is already planned for phase C.
- **M, decision level** (a meta-label, López de Prado 2018, ch. 3).
  - **What it is:** for each entry the active source would make, y = 1 when that trade's net return after fees, under that strategy's own exits, is above 0. The sources are STRAT-001's ENTER_LONG and the thinker's start.
  - **Where it is computed:** in the backtester (catalogue mode) or `model_gate.replay` (legacy mode).
  - **What it is for:** it is the probability a veto would use. A meta-model only decides whether to act on a primary signal, never its direction, which fits rule 1.
  - **Its size:** STRAT-001 1h gives about 4,333 entries over 3 years on 10 coins (research §6.1).
- **M under the legacy exits** is not informative. With DCA and the trailing margin, random entries end in profit about 91% of the time (research §6.4).
  - So in legacy mode an effect is judged only by FDS-MH-001's return per capital-day against its baselines (§6.1), and the expected-value veto of §5.8 applies only to strategies whose trades close by their own exit rule.

### 5.4 Forecast models and how sources are combined

- **The model:** a regularised logistic regression, pooled over coins (FDS-MH-001 phase C, "linear").
  - Its penalty is fixed in advance, and its features are standardised on the training rows only.
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

**Definition.** A confidence is p̂: the calibrated probability of a declared target (T1 or M), for this coin, at this decision time.
- These are scores, not confidences: the thinker's counts, ADX, and the LLM's self-reported 0–100.

**Calibration.**
- **Default:** Platt scaling (Platt 1999), two parameters, fitted on out-of-fold predictions from earlier folds only.
- **Fold 1** is not scored for calibration.
- **Isotonic regression** is used only by a declared change, with at least 5,000 out-of-fold rows, because it overfits small samples.
- **Calibration is never fitted on rows it is then scored on.**

**Measures**, on held-out folds, pooled, and per coin and per fold:
- **log loss**, the primary measure. It is strictly proper (Gneiting and Raftery 2007);
- **the Brier score** and its decomposition into reliability, resolution and uncertainty (Murphy 1973);
- **the Brier skill score** against climatology: the coin's base rate on the training rows;
- **a reliability diagram:** 10 equal-count bins, with bootstrap bands;
- **calibration intercept and slope**, by logistic recalibration (Cox 1958);
- **sharpness:** the standard deviation of p̂, and its 10th-to-90th-percentile range.

**When a confidence may affect anything.** Both must hold, on the development folds and again on the forward window (§6.4):
1. **Skill:** the Brier skill score is above 0, one-sided, by the block bootstrap of §6.1, within the Holm family (§6.5);
2. **Calibration:** the 95% interval for the intercept contains 0, and the one for the slope contains 1.

Otherwise:
- the assessment shows p̂ as "not calibrated";
- no confidence-based effect is available;
- only the liquidity limits can act (§5.7).

**Existing scores.** The thinker's counts and the LLM's confidence can be calibrated the same way, as P(target | score level) estimated on earlier folds. Only then can they become inputs.

**Drift.**
- The forward window reports calibration month by month.
- Calibration is refitted only at the declared 3-month refits, never in reaction to a result.

### 5.6 Volatility (Q3)

- **Not an entry signal.** With no drift, T1's probability does not depend on volatility, and FDS-MH-001 dropped volatility filters for that reason (§4).
- **A forecast input:** in block P, so that no other block gets volatility's credit.
- **Risk-based shrink.**
  - The scale is s_vol = min(1, σ_ref / σ̂), where σ_ref is the pooled median of σ̂ over the batch's training rows, fixed per batch and recorded.
  - It only ever shrinks: a volatile coin gets a smaller entry, and no entry is ever larger than today's.
- **Reporting:** every result is reported by volatility tercile (cut points from the training rows) and by BTC's 90-day trend (FDS-MH-001's), descriptively.
- **Exits and stops are unchanged.** A volatility-scaled stop exists as OVL-ATR, but changing exits changes the strategy, so it belongs to the strategy project (§11).

### 5.7 Liquidity and costs (Q3)

**The cost of a round trip:** c = 2 × the taker fee + the live spread + 2 × 0.05% slippage.
- The fee comes from the exchange layer, with its source recorded.
- In historical evaluation, the spread is folded into the 0.05%, with the OHLC estimate as a sensitivity.

**Two limits.** They are vetoes, not signals, so they need correctness tests, not predictive evidence:
- **Participation:** the entry's dollars must be at most π × the median hourly approximate dollar volume over the 20 previous days. Proposed π = 1% (decision D11).
- **Spread:** the live spread must be at most s_max. Proposed s_max = 0.50% (D11).

**At today's sizes they rarely bind.** An entry is 1% of a $100 paper account, raised to the exchange minimum. The limits protect thin coins and late listings now, and larger accounts later. Log-only mode counts how often each would have acted, per coin and per month, before the owner turns them on.

### 5.8 The assessment and its effect on a decision

**The record**, one per entry the existing path wants:

| Field | Content |
|---|---|
| when, coin, venue, source | the decision bar's close; the coin; the venue that prices the order; STRAT-001 or the thinker |
| p̂ | the calibrated probability, or "not calibrated" or "unavailable", with the reason |
| model | the model's id, its batch and the code hash (§5.9) |
| expected value | EV = p̂ · W̄ − (1 − p̂) · L̄, where W̄ and L̄ are the mean net win and the mean net loss (as magnitudes) of the training rows' trades at the fee in use |
| costs | the taker fee and its source, the live spread, the slippage allowance |
| volatility | σ̂, σ_ref, s_vol |
| liquidity | the median approximate dollar volume, the participation rate, the spread |
| effect | none, veto or shrink, with the scale and the reason |

**The hook.**
- It runs directly after the LLM hook in the trader's entry loop (`pt_trader.py:2908-2913`), before sizing, in both modes (R4).
- DCA buys and exits never consult it.

**Modes** (Settings, §5.10):
- **Off** is the default. Nothing is computed.
- **Log only:** computed and recorded, with no effect.
- **Veto.**
- **Veto and shrink.**

Veto and Veto and shrink can be chosen only when the assessment in use has a passing evidence record (§6). Otherwise they are greyed out, with the reason. This mirrors the trainer's rule of publishing only on a gate pass.

**Effects:**
- **Veto:**
  - when EV ≤ 0 (only with an eligible p̂, §5.5, and only for strategies with their own exits, §5.3);
  - or when a liquidity limit fails.
- **Shrink:**
  - the entry becomes today's amount × s_vol;
  - **a shrunk entry below the venue's minimum entry is skipped, never raised** (R5);
  - in legacy mode a DCA buy is a multiple of the position's value (`pt_trader.py:2748`), so it shrinks with the entry. Nothing else changes.
- **Unavailable** (no data, stale data, a hash mismatch, a calculation error): no effect, as today. The reason is recorded. This matches the LLM hook, where any failure lets the entry go ahead (D8).

**Invariants.** Each is a test (§12):
1. The hook returns only "allow unchanged", "skip" or a scale of at most 1. It never creates an entry or raises a size.
2. Whatever it lets through passes every existing check, unchanged: the halt, the drawdown halt, the mode pin, the strategy-settings check, the coin budget, the minimum, the risk check and preview.
3. With the mode Off, the trader's orders are byte-identical to `main`'s. With Log only, they are too.
4. Exits, DCA triggers, the trailing margin and stops never read it.
5. Every assessment is recorded, with the code hash.
6. A hash mismatch makes it unavailable.

### 5.9 One implementation, two callers

- **One package:** the features, the forecast and the assessment live in one package, proposed as `app/signal_fusion/`. `model_lab` imports its features, so FDS-MH-001's phase C would use them too (§7).
- **The same functions everywhere:** the harness replay, the backtester and the trader call them.
- **Hashed:** their files are added to the code hash in the record of the model in use, as `CODE_FILES` does for the pattern model (`pt_pattern_trainer.py:1157-1163`).

This closes R2 for this spec's own code.

### 5.10 Settings and display

- **Settings > Strategy:** "Entry assessment": Off, Log only, Veto, Veto and shrink. The chosen model is shown with its evidence status.
- **Settings > Risk:** the two liquidity limits, each off by default, with π and s_max.
- **Settings > Training > "Compare models…"** (FDS-MH-001 phase D): the Q1, Q2 and Q3 reports.
- **A table in the app:** each assessment, with its time, coin, venue, p̂ or "not calibrated", EV, costs, volatility scale, liquidity figures, effect and reason.
- All text states facts. No spec names and no caveats about the design.

## 6. Evaluation

### 6.1 Q1: does volume add predictive value?

**The pair.**
- M_P uses block P; M_PV uses P + V.
- Everything else is the same: model class, penalty, target, folds, rows and seeds. The only difference is V.

**The placebo.**
- M_PṼ, where Ṽ is the same coin's V block moved by one offset of at least 160 days (as R2 moves a schedule).
- It keeps V's distribution and breaks its timing. This guards against a gain from extra columns as such, or from a leak.

**Forecast level: the primary test.**
- For every held-out row, take the paired log-loss difference d = ℓ(M_P) − ℓ(M_PV). A positive mean d̄ favours volume.
- **The test:** a one-sided moving-block bootstrap over calendar time (Künsch 1989).
  - All coins' rows in a block move together, which keeps the dependence between coins.
  - Blocks are at least 2 × 336 hours (28 days), because T1's labels overlap for up to 336 hours.
- **Required, all three:**
  - d̄ > 0;
  - d̄ − d̄_placebo > 0;
  - d̄ > 0 in both halves of the walk-forward.

**Trading level: secondary, and expected to be underpowered.**
- Both models run as FDS-MH-001 contestants under the fixed strategy, each against R1 and R2.
- A new paired statistic gives the difference in return per capital-day on shared hours, with its smallest detectable edge.

**Decision level.**
- STRAT-001's entries, filtered by two meta-models (target M): one with V and one without V. Both use the same entries, the same veto rule (§5.8) and the same folds.
- **The deciding statistic** is paired: the return per capital-day of the trades the V filter keeps, minus that of the trades the no-V filter keeps. It is tested one-sided by the calendar block bootstrap above, with blocks of whole weeks of entries.
- **Shown beside it:** each filter against **R3, a random veto at the same rate.** The same number of entries is dropped, at random, over B draws. Under no skill, a filter's return per capital-day matches random thinning. This handles any shape of payoff, because it scores the strategy's real trades.

**The research's best rule gets its own test.** Same-hour relative volume above 1.5× was chosen from 296 tests, so it is declared as a filter and tested only on the forward window (§6.4).

**Verdicts.** Each verdict line states the score, the base rate and n beside the verdict:
- "No added value detected (smallest detectable Δ log loss = …)";
- "Adds forecast skill; not shown in trading results (smallest detectable edge = …)";
- "Adds forecast skill and trading value". This needs both levels and the forward confirmation;
- "Not assessable", when a floor is not met.

### 6.2 Q2: calibration

- **Measured** as §5.5 sets out, on M_PV and on M_P, and on whichever model an effect would use.
- **The deciding test** is that model's Brier skill score, in the Holm family (§6.5).
- **Shown, not deciding:** the reliability diagram, the intercept and slope, sharpness, and the per-coin and per-fold rows.

### 6.3 Q3: volatility and liquidity

**Volatility shrink**, as a sizing variant: the same entries, sized by s_vol, against unscaled.
- **Reported:**
  - return per capital-day;
  - total profit after fees;
  - an equity-curve maximum drawdown (new in the harness, §7);
  - the spread of per-trade returns.
- **The comparison:** R3s, the same scale factors given to the same entries in random order.
- **It passes** when the equity-curve drawdown is lower than R3s at the 5% level, and return per capital-day is not lower beyond its 95% interval.

**σ̂'s quality:** QLIKE against the naive forecast, as §5.2 sets out.

**Liquidity limits:**
- correctness tests: the approximation's error against stated quote volume, and the limits on hand-built quotes;
- the counts from log-only mode (§5.7).

### 6.4 Data windows, earlier looks and independence

- **Development:** FDS-MH-001's walk-forward folds (batch 1's calendar: 2021-01-01 to 2025-05-06). Never the lockbox.
- **The earlier look (R9).**
  - Every contestant with a V block gets a `LOOKS` entry: the volume research, 2023-11-06 to 2026-11-05, 10 coins, Coinbase.
  - That covers batch 1's lockbox. Under FDS-MH-001 §5.7, such contestants cannot get "Beats random entries" there. Price-only contestants are unaffected.
- **Confirmation: a registered forward window.** Its bars close after its registration commit, as in FDS-SIG-001 §11 and §12. The registration fixes in advance:
  - the models;
  - the features;
  - the veto rule;
  - σ_ref;
  - the window.

  The window's length comes from the power simulation (§6.5). The frozen code runs from its own worktree (FDS-SIG-001 §12.1), and the process and refusal rules are reused.
- **Independence from FDS-SIG-001.** Until a registered round's results are committed:
  - **No candidate features:** none of that round's candidates is in this spec's features. For round one: CMF-20's sign and BTC's one-bar lead.
  - **No direction scores:** no report here scores the next bar's direction by those rules on that round's window.
  - **No changes:** nothing here touches a research branch or `app/signal_audit/`.

  Otherwise the two may share calendar time. They test different targets, and neither reads the other's results before its own are committed. A CONFIRMED rule may later join the features through a declared new batch.
- **Kraken.**
  - Its 720 bars cannot serve development or confirmation.
  - A model runs live on Kraken only if a venue check passes: the features computed on Kraken and on a long-history venue, over the same 28 days, agree within a declared tolerance.

### 6.5 Multiple comparisons, power and repeated runs

**The primary family**, Holm at 5%, K = 4:
1. Q1's forecast test on T1 with the logistic model, at 1h decisions;
2. Q1's decision-level test on STRAT-001 1h: the paired difference between the meta-filters with and without V (§6.1);
3. Q2's Brier skill score for the model an effect would use;
4. Q3's volatility-shrink drawdown test.

**Exploratory, and labelled so:** the trees, per-coin rows, other timeframes and regime rows.

**Power.**
- Before registration, a local simulation of 10 seeded runs gives each primary test's smallest detectable effect at the planned window.
- The registration states those effects. A result below them reads "too few to tell".

**Repeated runs.**
- Every bootstrap or random-baseline p-value is computed as 10 independent seeded runs of B draws each, and reported pooled and per run.
- Fits that involve randomness (the trees) use 10 seeds as well.

## 7. Changes proposed to other specs

These are proposals. Each spec stays as approved until the owner accepts the change.

**FDS-MH-001** (best decided before phase C is built):
1. **Split the features.** Divide §5.5's features into P (25) and V blocks. Phase C builds a linear P contestant, a linear P + V contestant and the placebo. Batch 1's K grows to match.
2. **Return probabilities.** `Fitted` may also return a probability per hour, which the entry decision does not use.
3. **Score forecasts.** A forecast-scoring module: log loss, Brier and its decomposition, the skill score, reliability, and intercept and slope.
4. **Pair contestants.** A paired statistic on shared hours.
5. **Add R3 and R3s.** The random veto at the same rate, and random scale factors in random order.
6. **Report risk.** An equity-curve drawdown, and volatility-tercile reporting.
7. **Run 10 times.** The 10-seeded-runs reporting.
8. **Record the look.** The `LOOKS` entry for contestants with volume features (§6.4).

**FDS-SIG-001 and FDS-SIG-002:** no change. The independence rules of §6.4 apply.

**FDS-MX-001:** none needed for version 1, because L comes from the candles. If daily dollar volume is ever read from a connector, `daily_quote_volume` is routed through `ExchangeManager` first.

**FDS-121:** the backtester replays STRAT-001's entries for the meta-label, and draws R3.

## 8. Phases (one PR each)

### Phase 0 — this spec

The owner's decisions (§10).

### Phase A — the harness extensions (§7, items 2 to 8)

- **Where:** `app/model_lab/`, coordinated with FDS-MH-001 phase C.
- **Tests:**
  - the scoring rules match hand-worked values and scikit-learn's `log_loss` and `brier_score_loss`;
  - the bootstrap is reproducible from its seed;
  - R3 keeps the veto count;
  - the 10-run report has a row per run.

### Phase B — `app/signal_fusion/`

- **Changes:** the P, V, S and L blocks (§5.2), T1 (with FDS-MH-001 phase C) and the meta-label M.
- **Tests:**
  - no look-ahead: poisoning bars after t changes nothing at t;
  - the zero-volume and missing-bar rules;
  - the approximate dollar volume's error against the stated quote volume, within its bound;
  - identical definitions on all four connectors.

### Phase C — the development run and its report

- **How:** in a sandbox, on public candles, at 0.50% and at 1.20%.
- **Output:** `docs/dev/SIG4-REPORT-dev.md`, with Q1, Q2 and Q3 on the development folds. Nothing is enabled.

### Phase D — registration and freeze of the forward confirmation

- **What:** the exact models, features, veto rule, σ_ref and window, the window taken from the power simulation, and the frozen worktree.
- **Then:** the window runs. The results go in a report, and the verdicts follow §6.1.

### Phase E — log-only hook, Settings and table (§5.8, §5.10)

- **Defaults:** off.
- **Effect:** with Log only, it changes no decision, so it can run during phase D's window and collect the forward log.
- **Constraint:** it is not built in parallel with any other change to `pt_trader.py`.
- **Tests:** invariants 1 to 6.

### Phase F — Veto, and Veto and shrink, for paper

- **Only after:** phase D's primary tests pass, and the owner decides.
- **Live:** only later, under the live-trading spec's own decision.

## 9. Limits and risks

- **Power.** The trading-level tests will likely read "too few to tell" (§4). A forecast-level gain does not make a trading gain.
- **One market history.** Development covers 2021 to 2025, a single sequence of regimes. The forward window adds one more.
- **Survivorship.** The coins in the data are those still listed today.
- **Venue.** The research data is Coinbase-centred. Other venues' volume can differ in kind: the 2019 wash-trading estimates are in research §4.5.
- **Fees.** The account's rate can change. Each run records the rate it used.
- **The meta-label's sample.** STRAT-001 1h gives thousands of entries. The legacy thinker gives about 116 in 7 months, too few for M.
- **Calibration drift.** A calibration fitted on old folds goes stale. It is reported monthly and refitted only on the declared schedule.
- **The dollar-volume approximation** is bounded per bar, but its size has not been measured here. Phase B measures it.
- **Coins move together.** The block bootstrap moves all coins together, and R2 keeps cross-coin dependence.
- **The forward window takes months.** Until it closes, nothing is enabled.
- **Looking during the window.** Phase E's log is shown in the app. Its rows are facts per entry. No interim result is scored during the window, and the window's analysis runs once, at the end.

## 10. Decisions for the owner

| # | Decision | Recommended |
|---|---|---|
| D1 | Q1's primary target | T1 (FDS-MH-001's clean win) for the forecast test; the meta-label M on STRAT-001's entries for the decision test |
| D2 | The model class of the primary pair | Regularised logistic regression; trees exploratory |
| D3 | The V block | v1 (24-hour over the 30-day daily mean) and v2 (same-hour relative volume over 20 days). CMF-20 only after round one's results |
| D4 | The P block | FDS-MH-001 §5.5 minus its volume feature: 25 features, volatility included |
| D5 | The fee for deciding | The account's rate through the exchange layer, falling back to the published default with the source shown; every report at 0.50% and 1.20% |
| D6 | Modes, and their order | Off, Log only, Veto, Veto and shrink. Scale-up is out of scope |
| D7 | A shrunk entry below the exchange minimum | Skipped, never raised |
| D8 | An unavailable assessment | No effect, as today, with the reason recorded (the LLM hook's rule) |
| D9 | The confirmation data | A registered forward window, because the volume research looked at batch 1's whole lockbox |
| D10 | Where the hook sits | Directly after the LLM hook, for both modes |
| D11 | The liquidity limits | π = 1% of the 20-day median hourly approximate dollar volume; spread ≤ 0.50%; both off until log-only counts are seen |
| D12 | The volatility shrink | s_vol = min(1, σ_ref / σ̂), with σ̂ chosen by QLIKE and σ_ref fixed per batch; shrink only |
| D13 | The veto rule | EV ≤ 0 from a calibrated p̂, for strategies with their own exits; the legacy chain is judged only by FDS-MH-001's per-day score |
| D14 | The FDS-MH-001 amendments (§7) | Accept them before phase C is built, so the price-only twin and the forecast scores are part of it |
| D15 | Independence from FDS-SIG-001 (§6.4) | Accept as written |

## 11. Out of scope

- **Exits, stops, the DCA rules and the trailing margin.** These belong to the strategy project. Rule 1 keeps them untouched.
- **Scale-up:** any effect that enlarges an entry. It needs its own spec.
- **New data:** taker-buy volume, funding, open interest, order-book history and trade counts.
- **Live enabling,** under FDS-LIVE-001's own decisions.
- **Building calibration for the LLM's confidence** (§5.5 says only how it could be done).
- **R2 for the legacy thinker:** hashing `pt_thinker.py`, or making the gate run the thinker's own code. Offered as a separate follow-up.
- **FDS-MH-001's phases D and E,** except as §7 amends them.

## 12. Acceptance (for the implementation)

1. **No look-ahead.** No feature, target or assessment at t changes when bars after t are poisoned.
2. **Invariants 1 to 6 (§5.8)** are tests, including:
   - property tests showing the hook never returns a scale above 1 or creates an entry;
   - with Off and with Log only, the trader's orders are byte-identical to `main`'s on a replayed session;
   - exits and DCA triggers are unchanged.
3. **Exchange-neutral.** The same features from all four connectors' fixtures. The venue check for Kraken.
4. **The approximation.** Approximate dollar volume is within its bound of the stated quote volume, on the venues that state it.
5. **Scoring.** The scoring rules match reference values. Calibration is never fitted on the rows it is scored on.
6. **Statistics.**
   - The bootstrap, R3 and R3s are reproducible from their seeds.
   - Every simulation reports 10 seeded runs, pooled and per run.
7. **The `LOOKS` entry** for volume contestants exists, and a batch records it at freeze.
8. **Settings.** Every new key defaults to off. Saved settings keep their meaning: decisions with the new keys absent equal `main`'s.
9. **The suite.** The full suite passes with 0 failures, Black is clean, and CI's flake8 is clean.

## References

Standard sources, cited from the literature as commonly given. They were not re-read for this draft. Phase A checks each formula against its source before it is used.

- Abdi, F. and Ranaldo, A. (2017). A simple estimation of bid-ask spreads from daily close, high, and low prices. *Review of Financial Studies* 30(12).
- Cox, D. R. (1958). Two further applications of a model for binary regression. *Biometrika* 45.
- Gneiting, T. and Raftery, A. E. (2007). Strictly proper scoring rules, prediction, and estimation. *JASA* 102.
- Künsch, H. R. (1989). The jackknife and the bootstrap for general stationary observations. *Annals of Statistics* 17.
- López de Prado, M. (2018). *Advances in Financial Machine Learning*. Wiley, ch. 3 (meta-labelling) and ch. 4 (sample uniqueness).
- Murphy, A. H. (1973). A new vector partition of the probability score. *Journal of Applied Meteorology* 12.
- Parkinson, M. (1980). The extreme value method for estimating the variance of the rate of return. *Journal of Business* 53.
- Patton, A. J. (2011). Volatility forecast comparison using imperfect volatility proxies. *Journal of Econometrics* 160.
- Platt, J. (1999). Probabilistic outputs for support vector machines and comparisons to regularized likelihood methods.
- J.P. Morgan/Reuters (1996). *RiskMetrics: Technical Document*, 4th ed. (EWMA, λ = 0.94).
