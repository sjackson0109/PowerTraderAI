# Volume module: Stage 1 research and evidence

| | |
|---|---|
| Status | Research only. No feature code; no trading change. |
| Date | 2026-11-05 |
| Branch | `research/volume` (from main d490690) |
| Scope | The owner's brief, Sub-agent 1: literature review, code audit, empirical test, recommendation |
| Labels | **[TEST]** a test result from this research (data or code). **[SOURCE]** taken from a cited source, graded. **[UNVERIFIED]** no source or test supports it. |

## 1. Verdict

**Do not build a volume module to improve profits now. At the app's assumed fee no volume rule makes a trade profitable.**

- **STRAT-001 at the app's fee.** The best volume rule (Coinbase volume above 1.5× its same-hour-of-day average)
  lifts the STRAT-001 1h hit rate after fees to 21.2%, against a 15.6% base rate (n = 950 vs 4,333, p < 0.001). Its
  trades still lose 2.10% each on average (95% CI −2.35% to −1.85%), against −2.50% for all entries. No rule comes
  near the training gate's 55%.
- **The volume effect is real but small** **[TEST]**. High-volume entries beat the rest in 9 of 10 coins and, on hit rate,
  in both halves of the window; it is not just volatility.
  - About +0.3% a trade gross at 1h (95% CI +0.04% to +0.55%), against a 2.40% round trip at the app's assumed Coinbase
    taker fee.
  - At 15m it is smaller still, and gross-negative even in the best bucket.
- **The neural trade-start entries and the pattern model show no skill above a model-free base rate** **[TEST]**.
  - Trade-start entries: 90.5% fee-adjusted hit rate, n = 116, against 90.9% for random entries with the same legacy
    exits.
  - Adding volume to the model changed nothing: 91.6% against 90.5% (p = 0.82); 1hour direction 50.6% against a 50.3%
    base rate (n = 51,514, p = 0.064).
- **The literature agrees** **[SOURCE, weak–moderate]**:
  - no study shows a volume filter surviving retail fees at 15m–4h;
  - the sign of the high-volume effect is disputed;
  - the best cost-inclusive study finds volume adds nothing to a trained model.

**What would change the answer:**
- **A much lower fee.** At ≤ 0.10% a side the high-volume STRAT-001 subset breaks even (+0.09%, 95% CI −0.16% to
  +0.34%). So first verify the owner's real Coinbase tier and consider maker orders.
- **A strategy with a gross edge for the filter to sharpen.** None of today's has one.

## 2. Answers at a glance

| Brief question | Answer | Grade / basis |
|---|---|---|
| a. Does volume improve 15m–4h entries vs daily+? | No direct evidence either way at 15m–4h. Daily evidence is in-sample and contradictory. Here it helped STRAT-001 1h a little, 15m less, and neither after fees. | weak [SOURCE]; [TEST] §6.2–6.3 |
| b. Require high volume, block low volume, or neither? | No study tests either rule. Here "require > 1.5×" has the larger per-trade effect; "block < 0.7×" keeps more trades but helps less. **Neither makes a trade profitable after the app's fees.** | weak [SOURCE]; [TEST] §6.2 |
| c. How to measure relative volume? | Against the same hour of day (and weekday), per exchange, over about 20 days or more. A rolling 20-bar or 1-day baseline mostly measures the clock and carried no information here. | moderate (seasonality) [SOURCE]; [TEST] §6.2, §6.6 |
| d. Which measures have evidence? | Relative/abnormal volume: moderate, sign disputed. Volume MACD/CMF: weak. OBV, VWAP, divergence: unverified in the literature, and no help here. Spikes before reversals: weak and contradictory. | [SOURCE] §4.4; [TEST] §6.2 |
| e. Single vs aggregated; wash trading; USD/USDT | Wash trading was heavy on unregulated venues (2019); regulated venues showed none. Coinbase alone gave the same result as the aggregate for the majors. Exclude KuCoin. Base-unit volume needs no USD/USDT conversion. | moderate–strong (wash) [SOURCE]; [TEST] §6.7 |
| f. Volume as an input to learned models | Little incremental value; overfitting and regime risk documented. Here the pattern model gained nothing on the holdout. | moderate [SOURCE]; [TEST] §6.5 |
| g. Does any benefit survive retail fees? | No study shows it at a 1–2.4% round trip. Here: no, at any fee from 0.40% a side up. | weak [SOURCE]; [TEST] §6.1–6.2 |

## 3. Code audit (read-only, main at d490690)

All paths are under `app/` unless stated. Line numbers are at d490690.

### 3.1 Does anything in training, thinking, pattern detection, the signal engine or the strategies use volume?

**[TEST: code read] No part of the decision path uses volume.** The candle layer carries a volume column, but no
trainer, runner, strategy or pattern detector reads it.

| Component | What it reads | Evidence |
|---|---|---|
| Trainer (`pt_pattern_trainer.py`) | open, close, high, low. Volume is read from the cache only to hash the candles for provenance. | `BarLoader._load` returns `open, close, high, low` (lines 517–523); the pattern is the last candle's body % only (lines 815–818); `candle_sha256` hashes volume for the manifest only (lines 584–598) |
| Model (`pattern_model.py`) | open and close of the last closed bar | `TimeframeModel.predict(open_price, close_price)` (lines 154–156); `score_timeframe` reads open/high/low/close (lines 375–377) |
| Neural runner (`pt_thinker.py`) | time, open and close of the last closed bar | `_last_closed_bar` returns `(time, open, close)` (lines 494–503); the body % pattern (lines 896–898). No "volume" anywhere in the file. |
| Trader (`pt_trader.py`) | neural long/short counts, or the signal engine's decision; prices | trade start: long ≥ `trade_start_level` and short = 0 (lines 2892–2906); catalogue entry (2882–2891); DCA (2704–2805); trailing PM (2593–2702). No "volume" anywhere in the file. |
| Signal engine (`signal_engine.py`) | the active strategy's decision on closed candles | no "volume" in the file; decisions come from `StrategyRunner.evaluate` (lines 320–322) |
| Strategies (`strategies/*.py`) | close (STRAT-000), close/high/low with ADX (STRAT-001), high/low/close (STRAT-002), the pattern model's open/close (STRAT-003) | "volume" appears only in the candle column list, `strategies/base.py` lines 7 and 28. `trend_crossover.py` lines 41–73; `supertrend.py` lines 31–50; `model_strategy.py` lines 191–198. |
| Candlestick patterns (`candlestick_patterns.py`, `pt_chart_patterns.py`) | open, high, low, close | `Bar = namedtuple("Bar", "ts open high low close")` (`candlestick_patterns.py` line 20) |

**The existing spec already says this.** FDS-SIG-001 (`docs/dev/specs/FDS-SIG-001-signal-candidate-audit.md`, line
85): "none of them uses volume". FDS-SIG-002 proposes a volume candidate, the CMF-20 sign (SIG-A, lines 81–89); it is a
spec only, with no code.

**Three places that mention volume but do not reach a trade by default:**
1. **`pt_neural_network.py` lines 248–252** build `volume_sma` and `volume_ratio` features. **[TEST: grep] Nothing
   outside `tests/` and `archive/legacy/` imports `pt_neural_network.py` or `pt_neural_processor.py`.** They are dead
   code for trading.
2. **The LLM research snapshot** writes the 24-hour volume into the LLM prompt (`llm_research_engine.py` lines 173 and
   254).
   - An LLM signal can confirm or veto an entry the strategy or the neural levels already want (`pt_trader.py` lines
     2908–2913).
   - It does so only in the `confirm` / `veto` modes, and only after the LLM gate has passed (`llm_gate.py` lines
     15–30).
   - The default mode is `log_only` (`llm_settings.py` line 75), so by default it never changes a trade.
3. **`candle_sha256`** (above) hashes volume for provenance only.

### 3.2 Do candlestick pattern detections feed any trading decision?

**[TEST: code read + grep] No. They are chart overlays only.**

- **The modules say so:**
  - `candlestick_patterns.py` lines 2 and 10: "Display only… Nothing here feeds a strategy, the trainer, the runner
    or the trader".
  - `pt_chart_patterns.py` lines 1–4: "Display only: nothing here reaches a strategy, the trainer, the runner or the
    trader".
- **The imports agree:**
  - `candlestick_patterns`, `pt_chart_patterns` and `chart_settings` are imported only by `pt_hub.py` (lines 39, 854,
    1212, 1278, 2093, 7313), by each other, and by `real_time_market_data_gui.py` line 114 (`chart_settings`).
  - The trader, runner, trainer, signal engine and strategies import none of them.
- **The one link to trades runs the other way.** `PatternLayer.trade_ts` (`pt_chart_patterns.py` line 137) ranks
  pattern labels near the chart's own trades. Trades shape the display; patterns never shape trades.

### 3.3 Is "the old (untrained, mock) trainer files" still accurate for the neural engine?

**[TEST: code read] No. It is out of date since the trainer rework (FDS-MDL, PR #154; every bar, PR #205).**

**The wording:**
- `pt_settings_manager.py` lines 128–130: `"legacy_neural" = the old (untrained, mock) trainer files`.

**What the code does now:**
- **The trainer is real.** The default trainer is `pt_pattern_trainer.py` (`pt_settings_manager.py` lines 85–88;
  `pt_hub.py` lines 557–560). It is a port of upstream's pattern-matching trainer that learns from exchange candles; the
  copy is byte-identical in upstream mode (TRAINER-AUDIT).
- **The mock is refused.** The old `pt_trainer.py` is marked `# MOCK - DO NOT USE FOR DECISIONS` (`pt_trainer.py`
  line 2). The hub refuses to run it unless `allow_mock_trainer` is true (`pt_hub.py` lines 4973–4990).
- **Only published models are used.** The neural runner uses a coin's model files only when a published manifest
  matches them byte for byte; otherwise the coin is held like an untrained one (`pt_thinker.py` lines 274–330).
- **So `legacy_neural` now trades on a trained model or not at all.** It never trades on mock files.

**What would be accurate:**
> "legacy_neural" = the pattern-memory model trained by `pt_pattern_trainer.py`, with the legacy DCA and trailing-PM
> rules.

**Caveats that belong beside that wording:**
- **Test A** (`docs/dev/BACKTEST-REPORT-model-1.md`) found **no evidence of an edge**.
- **The saved weights never move.** Every saved memory weight stays 1.0, an upstream quirk kept on purpose
  (`pt_pattern_trainer.py` lines 28–29). The model is a nearest-neighbour lookup on one feature: the candle body %.
- **No performance gate exists yet.** `training_settings.py` lines 8–9 call the model gate "planned", and design 2b is
  not built.

**The same stale wording appears in:**
- `strategies/settings.py` lines 71–72: the hub strip shows `SIGNALS: LEGACY (UNTRAINED)`;
- `pt_trader.py` lines 2212–2213 (comment);
- `pt_hub.py` lines 5919–5920 (docstring);
- `docs/technical/ARCHITECTURE.md` lines 131, 140 and 147.

**This report changes none of them.** No feature code was written.

## 4. Literature review

**How this section was produced.** Public web search and fetch only. Each source below records what was actually
read: **FULL** (the full text, sometimes via a PDF-to-text extract and targeted reading), **ABS** (abstract, catalogue
record or search snippet only) or **SEC** (secondary coverage only). A finding that rests only on ABS or SEC sources
is no stronger than **weak**. A source that could not be read at all is **unverified** (§4.10).

**Evidence grades.**

| Grade | Meaning |
|---|---|
| strong | Several independent peer-reviewed studies, out of sample, agree, and the setting matches (crypto, intraday or near it). |
| moderate | At least one solid peer-reviewed or well-documented study in a matching setting, or several in a nearby setting (daily crypto, or intraday equities), with some disagreement. |
| weak | A single study, in-sample only, a different market or horizon, a working paper, or practitioner/blog evidence. |
| unverified | Could not be fetched or read, or the claim has no source. |

**[SOURCE] Bottom line.**
- No study found tests a volume filter on 15m–4h spot-crypto entries, out of sample and after costs.
- The strongest out-of-sample, cost-inclusive study that isolates volume (Fieberg et al. 2025, CTREND, weekly) finds
  volume indicators add no measurable incremental value. Removing all ten volume indicators gave a median Sharpe of
  1.39, against 1.30 with them.
- The intraday ML study that includes costs (Jaquart et al. 2021, 1–60 min) turns negative at a 30 bps round trip.
  That is far below the app's assumed Coinbase taker round trip of 2.40% (1.20% a side, §5.3).

### 4.1 a. Does volume improve short-horizon (15m–4h) entry signals, versus daily and longer?

**Grade: weak.** There is no direct out-of-sample, cost-inclusive evidence at 15m–4h. What exists is daily,
in-sample, nonlinear, or a working paper.

- **Daily BTC, Bitstamp 2011–2016** [S2] (FULL):
  - a linear Granger test finds nothing (χ²(7) = 9.43, p = 0.22);
  - a nonparametric quantile test finds volume predicts returns only around the median (quantiles 0.25–0.75), not in
    bull or bear tails.
- **Seven coins, daily** [S1] (FULL manuscript) finds the opposite: causality only in the tails (1–10% and 90–99%).
- **Abstract level:**
  - [S3]: price-based technical signals predict daily and weekly returns; volume-based signals predict monthly returns.
  - [S15]: BTC intraday momentum (the first half-hour predicts the last) is strongest in the highest-volume or
    highest-volatility sessions, out of sample.
- **Intraday ML:**
  - [S21] (FULL): volume features included at 15/30/60 min; 55–65% accuracy, but no costs, and volume never isolated.
  - [S20] (FULL): 1–60 min with no volume features at all; 51.5–55.8% accuracy.
- **Weekly:** [S4] (FULL): removing all volume indicators did not hurt.

**Disagreements:**
- [S2] (median only, BTC) and [S1] (tails only, including BTC) contradict each other directly.
- [S3] (volume useful at long horizons) versus [S15] (volume conditions intraday predictability).
- [S28] (ABS): intraday rules lose to buy-and-hold, while daily SMAs work.

### 4.2 b. Require above-average volume, block unusually low volume, or neither?

**Grade: weak.** No crypto study tests either rule as an entry filter, and the nearby evidence conflicts on sign.
**Inference, not a finding:** blocking low-volume entries is more defensible for trend or breakout entries than
requiring high volume.

- **For blocking low volume** ([S5], FULL working paper; daily, aggregated across exchanges, 2017–2022):
  - reversal (liquidity-provision) returns concentrate in low-volume pairs;
  - the interaction of lagged return and volume shock is positive: moves on high abnormal volume continue, moves on
    low volume revert.
- **Against requiring high volume to buy** ([S6], FULL; Binance spot, BTC-quoted pairs, 2018–2021):
  - high abnormal turnover (the paper's DISAGREE proxy) predicts lower next-day returns: the high-minus-low quintile
    spread is −0.473% a day (t = −6.98), after controlling for turnover variability;
  - this holds only while a coin cannot be shorted, and disappears once Binance enables margin trading;
  - this app trades long-only on Coinbase spot, so this is the relevant case.
- **[S4] Table 2** (FULL): coins whose current volume is high relative to their 50–200-day average earned more the
  following week. The volsma_50d high-minus-low spread is −1.58% a week (t = −2.2), where a high volsma means low
  current volume. It is not significant after the Liu-Tsyvinski-Wu three-factor model [S7].
- **Equities:**
  - [S9]: a positive high-volume return premium.
  - [S14] (ABS): high-turnover stocks earn less later, and high-volume winners reverse faster.
  - [S11] (ABS): autocorrelation falls with volume.
  - [S10] (ABS): continuation if trading is informed, reversal if it is hedging.

**Disagreements:** the sign of the high-volume effect.
- Crypto: [S5] (continuation) versus [S6] (later underperformance).
- Equities: [S9] (premium) versus [S14] (lower returns).

### 4.3 c. How should relative volume be measured?

**Grades:**
- **Moderate** that crypto volume has strong intraday and weekly seasonality, Coinbase included.
- **Weak/unverified** on which baseline gives better signals.

**Seasonality is documented:**
- [S16] (ABS; Bitstamp, 5-min): volume builds during the day and falls from about 4pm to midnight.
- [S17] (ABS; 7 exchanges): volume is persistently lower in local evening hours and at weekends.
- [S18] (ABS plus a practitioner summary; Coinbase Pro and Binance): day-of-week, hour-of-day and within-hour
  periodicity, growing stronger over time.
  - Coinbase has much less volume from 05:00 to 12:00 UTC, with spikes at 00:00 and 16:00 UTC.
  - Bursts at minutes 0, 15, 30 and 45.
  - Lower volume at weekends, Saturday lowest.
  - Binance volume is spread more evenly through the day.

**Implication:** a plain rolling N-bar average on 15m or 1h bars will routinely label overnight-UTC hours "low volume".
This evidence justifies a same-hour-of-day (and weekday/weekend) baseline per exchange. **No study shows it predicts
better.** §6.6 checks the seasonality on this project's Coinbase data.

**Lookbacks used in the literature:**
- 30 days: log deviation standardised by the 30-day SD [S5]; [S6].
- 49-day reference window, top or bottom 10% [S9].
- 3/5/10/20/50/100/200-day SMAs divided by current volume [S4].
- Full-sample quadratic detrending [S1]; [S2]. This uses future data and cannot be used live.

**Disagreements:** intraday profiles differ by venue (Coinbase versus Binance), so a pooled baseline is wrong for a
single exchange.

### 4.4 d. Which volume measures have evidence?

| Measure | Grade | Evidence |
|---|---|---|
| Relative / abnormal volume | **moderate** that it carries information; its **sign depends on context** | [S5]; [S6]; [S9] (equities); [S4] volsma (weak) |
| Volume MACD / PVO, Chaikin money flow | **weak** | [S4] (FULL): volmacd high-minus-low +2.01%/wk (t 2.38), but its alpha is not significant (0.72, t 0.94); Chaikin 1.12%/wk, t 1.68, not significant |
| Dollar-volume level | **weak** as a timing signal; it acts as a size/liquidity effect | [S7]: low-dollar-volume coins beat high ones by 3.2%/wk, fully explained by the 3-factor model |
| Order flow / VPIN | **weak** | [S38] (ABS): signed volume explains 80% of BTC returns contemporaneously, not predictively. [S23] (WP, FULL): VPIN and the Roll measure predict 1-min price-dynamics variables at AUC 0.54–0.61. [S19] (WP, ABS): opening order imbalance predicts 4–12h returns (Binance perpetuals). |
| OBV | **unverified** | No OBV-specific crypto result found. [S27] reportedly includes OBV rules (secondary claim only). Whether [S24]'s rule set includes OBV is unverified. Granville [S41] not fetched. |
| VWAP as a signal | **unverified** | No study found. VWAP appears only as a price input in [S22]. |
| Volume-price divergence | **unverified** | No crypto study found. |
| Volume spikes before reversals | **weak** | Supported for coins that cannot be shorted [S6]; [S5] finds the opposite (high-volume moves continue). |
| Volume → volatility | **weak** | [S2] appendix: volume does not predict squared-return volatility but does predict GARCH volatility, so the result depends on the measure. |

**Disagreements:** the sign of the high-volume return premium: positive in equities [S9], negative in non-shortable
crypto [S6].

### 4.5 e. Single exchange versus aggregated volume; wash trading; USD and USDT

**Grades:**
- **Moderate–strong** that heavy wash trading existed on unregulated venues: several peer-reviewed studies, on
  2018–2019 data.
- **Weak** on which exchanges are clean today: industry benchmarks, with methods not fully public.

**[S31]** (Management Science 2023; FULL working-paper text):
- 29 exchanges, July–November 2019.
- On unregulated exchanges, wash trading averaged 77.5% of volume (median 79.1%): Tier-1 53.4%, Tier-2 81.7%.
- No systematic wash trading on regulated exchanges (NY BitLicense holders; Coinbase is one).
  - Caveat: the text anonymises the three regulated exchanges as R1–R3. That they are Bitstamp, Coinbase and Gemini
    comes from secondary coverage.
- Binance is "UT1", a Tier-1 unregulated exchange, with an estimated wash share above 50%.
- Kraken and KuCoin were not found in the text.
- Wash trading is positively predicted by returns, so it contaminates volume-return signals.

**[S35]** Bitwise's 2019 SEC filing (FULL):
- 95% of reported volume was fake, on 71 of 81 exchanges: about $270m a day real against $6bn reported.
- Its "real 10" list, from secondary coverage: Binance, Bitfinex, bitFlyer, Bitstamp, Bittrex, Coinbase Pro, Gemini,
  itBit, Kraken, Poloniex. **KuCoin is absent.**

**[S37]** CoinDesk Data (CCData) Exchange Benchmark:
- April 2025 (FULL page): AA spot grades for Binance (90.1), Coinbase (89.8), Bitstamp (88.4) and Kraken (84.5).
- KuCoin's grade was not found (unverified).

**Mixing USD and USDT** ([S40], FULL):
- USDT deviated from $1 with an SD of about 129 bps (extremes −960 / +571 bps) and a half-life of 6.4 days, 2017–2020.
- Converting USDT volume at the market USDT/USD rate is enough for normalisation; the error is tens of bps on most days.
- **[TEST] This project's candles carry base-asset volume** (BTC, not dollars) on all four connectors (§5.1). Summing
  base volume across USD and USDT pairs needs no conversion at all; only quote (dollar) volume would.

**Market structure:**
- [S38]: large recurring price gaps across exchanges; exchange-specific volume explains the spreads, so single-exchange
  volume carries venue noise.
- [S5] aggregated only exchanges CryptoCompare graded AA–B, volume-weighted, and treated USDT as equal to USD.

**Disagreements:**
- Binance: "real" for Bitwise and the Blockchain Transparency Institute [S36], AA for CCData, yet [S31] estimates a
  wash share above 50% in 2019.
- Bitwise's real-volume figure is reported inconsistently: $270m (the SEC filing) versus $554m (secondary coverage).

### 4.6 f. Does volume improve learned price models, and what are the risks?

**Grades:**
- **Moderate** that volume adds little incremental value in learned models.
- **Weak** at intraday horizons.

**What the studies show:**
- **[S4]** (FULL):
  - an elastic net over 28 indicators, 10 of them volume-based;
  - removing all volume indicators: median Sharpe 1.39 without, against 1.30 with;
  - the most important features are price-based (Bollinger mid-band, CCI, MACD);
  - holding out a true validation sample cut the median Sharpe from 1.47 to 1.19, a sign of overfitting;
  - performance declined over time: 4.47% a week in the first half, 3.26% in the second.
- **[S21]** (FULL): includes volume features but never isolates them.
- **[S22]** (FULL):
  - includes volume, with no feature-importance analysis;
  - validated in a bubble and tested in a bear market;
  - 5 of 18 models scored below 50% in the test period.
- **[S20]** (FULL): reaches 51–56% accuracy without volume.

**Risks documented in the sources:**
- structural breaks ([S2]: April and December 2013);
- regime shifts [S22];
- data snooping ([S24] corrected for it; [S4] tested 55,296 design variants);
- no out-of-sample predictability for BTC ([S24], ABS);
- wash-trading contamination of volume features [S31].

**Disagreements:** [S3] (ABS) reports that ML improves volume and price indicators out of sample. [S21] says volume is
useful, without an ablation test.

### 4.7 g. Does any volume-based benefit survive retail fees?

**Grade: weak.** No study shows a volume-based entry rule surviving a 1.2–2.4% round trip at 15m–4h.

- **[S20]:** 1–60 min ML returns up to 39% a month gross, negative after a 30 bps round trip.
- **[S22]:** daily, long-only, 0.5% round trip: ETH +9.6% and LTC +5.7% a year, BTC −23.7%.
- **[S4]:**
  - break-even 1.41% per unit of turnover (0.88% for 5% significance), with 68% weekly turnover;
  - but it is weekly, long-short and multi-coin, and it does not need volume.
- **[S5]:** at 30/40 bps the equal-weighted reversal survives, value-weighted alphas become insignificant, and the
  volume-sorted long-short is zero after costs.
- **[S24]** (ABS): break-even costs "well above" typical levels; the numbers were not seen.
- **Coinbase fees** at the tier this app assumes: 0.60% maker / 1.20% taker, from `pt_exchange_abstraction.py`
  lines 203–213, which cite help.coinbase.com. The official page returned 403 to the literature fetch, and third-party
  sources disagree (0.60% taker at the lowest tier in some).
  - Either way, the round trip is above every cost level at which intraday edges were tested.

**Disagreements:**
- [S29] (ABS): costs change rule profitability differently by coin.
- [S28] (ABS): intraday rules lose to buy-and-hold even before costs.

### 4.8 Source records

"OOS" = out-of-sample test; "Costs" = transaction costs included; "Access" as defined at the start of §4.

| # | Title (short) | Authors | Year | Venue | Link used | Access | Coins | Period | Freq | Method | Key finding | Qs | OOS | Costs |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| S1 | Trading volume and the predictability of return and volatility in the cryptocurrency market (manuscript title: "Copula-quantile causality…") | Bouri, Lau, Lucey, Roubaud | 2019 | Finance Research Letters 29:340–346 | pure.hud.ac.uk/ws/portalfiles/portal/14425624/REVSED_for_editing_finished_NO_INFO.pdf ; doi 10.1016/j.frl.2018.08.015 | FULL (accepted manuscript, tables omitted) | BTC, XRP, ETH, LTC, XEM, DASH, XLM | not stated in manuscript | daily (CoinMarketCap) | copula-quantile Granger causality, detrended volume | volume causes returns in both tails for all 7 coins; volatility only LTC/XEM/DASH at low volatility, squared returns only | a, d | no (in-sample causality) | no |
| S2 | Can volume predict Bitcoin returns and volatility? A quantiles-based approach | Balcilar, Bouri, Gupta, Roubaud | 2017 | Economic Modelling 64:74–81 | repository.up.ac.za/bitstream/handle/2263/60028/Balcilar_Can_2017.pdf | FULL | BTC (Bitstamp) | 19 Dec 2011–25 Apr 2016 (1,587 obs) | daily | nonparametric causality-in-quantiles, 7 lags | linear: none (p = 0.22); quantiles 0.25–0.75 significant, tails not; no causality to squared-return volatility; GARCH volatility yes | a, b, d, f | no | no |
| S3 | Trend-based forecast of cryptocurrency returns | Tan, Tao | 2023 | Economic Modelling 124:106323 | doi 10.1016/j.econmod.2023.106323 (Crossref); SSRN 4222864 (403) | ABS | ~3,000 coins | 2013–2022 | daily, weekly, monthly | technical indicators + PCA/PLS/sPCA/sSUFF | price signals predict daily/weekly; volume signals predict monthly; ML improves in and out of sample | a, d, f | yes (per abstract) | not stated |
| S4 | A trend factor for the cross section of cryptocurrency returns (CTREND) | Fieberg, Liedtke, Poddig, Walker, Zaremba | 2025 | JFQA 60(7):3116–3153 | cambridge.org/core/services/aop-cambridge-core/content/view/S0022109024000747 | FULL | 3,245 coins | Apr 2015–May 2022 | weekly rebalance, daily inputs | 28 indicators incl. 10 volume; cross-sectional elastic net, 52-week rolling | 3.87%/wk (t 5.19), Sharpe 1.94; volume indicators weak alone; excluding them does not hurt (median Sharpe 1.39 vs 1.30); break-even 1.41%; turnover 68%/wk | a, b, c, d, e, f, g | yes (rolling) | yes |
| S5 | Trading volume and liquidity provision in cryptocurrency markets | Bianchi, Babiak, Dickerson | 2022 | J. Banking & Finance 142:106547 (read as Riksbank WP 413) | riksbank.se (WP no. 413 PDF) | FULL (working paper) | USD pairs, CryptoCompare aggregate (exchanges graded AA–B) | Mar 2017–Mar 2022 | daily | volume shock = log V − log mean(30d), standardised; sorts, panel regressions | reversal concentrated in low-volume pairs; positive return × volume-shock interaction; volume-sorted long-short zero after costs | b, c, d, e, g | partly (recursive) | yes (30/40 bps) |
| S6 | Disagreement and returns: the case of cryptocurrencies | Garfinkel, Hsiao, Hu | 2025 | Financial Management (doi 10.1111/fima.12491) | biz.uiowa.edu/faculty/jgarfinkel/pubs/crypto_divop.pdf | FULL | Binance spot, BTC-quoted pairs | Aug 2018–Dec 2021 | daily (from hourly) | abnormal turnover (30-day mean/SD) sorts | high-minus-low −0.473%/day (t −6.98); vanishes once margin trading is enabled | b, c, d, e | no | not found |
| S7 | Common risk factors in cryptocurrency | Liu, Tsyvinski, Wu | 2022 (read the 2019 WP) | Journal of Finance 77(2):1133–1177 | cowles.yale.edu (2019 WP PDF) | FULL (WP) | 1,707 coins | 2014–2018 (WP) | weekly | quintile factor sorts | dollar-volume high-minus-low −3.2%/wk; other volume factors not significant; all explained by 3 factors | d | no | no |
| S8 | Risks and returns of cryptocurrency | Liu, Tsyvinski | 2021 | Review of Financial Studies 34(6):2689–2727 | econpapers RePEc:oup:rfinst:v34 | ABS | BTC, XRP, ETH | not stated | daily/weekly | time-series predictors | strong time-series momentum; attention proxies predict | a | not stated | not stated |
| S9 | The high-volume return premium | Gervais, Kaniel, Mingelgrin | 2001 | Journal of Finance 56(3):877–919 | rodneywhitecenter.wharton.upenn.edu (WP 9901 PDF) | FULL (WP, targeted reading) | NYSE stocks | Aug 1963–Dec 1996 | daily/weekly | 49-day reference + formation day; top/bottom 10% | high volume → higher returns over the following month | b, c, d | n/a | not verified |
| S10 | Dynamic volume-return relation of individual stocks | Llorente, Michaely, Saar, Wang | 2002 | Review of Financial Studies 15(4):1005–1047 | econpapers RePEc:oup:rfinst:v15:i4 | ABS | NYSE/AMEX | not stated | daily | model + volume-autocorrelation regressions | hedging trades → reversal; informed trades → continuation | b, d | no | no |
| S11 | Trading volume and serial correlation in stock returns | Campbell, Grossman, Wang | 1993 | QJE 108(4):905–939 | econpapers RePEc:oup:qjecon:v108 | ABS | indexes, large stocks | not stated | daily | model + regressions | autocorrelation declines with volume | b, d | no | no |
| S12 | Market statistics and technical analysis: the role of volume | Blume, Easley, O'Hara | 1994 | Journal of Finance 49(1):153–181 | econpapers RePEc:bla:jfinan:v49 | ABS | theory | – | – | equilibrium model | volume conveys information on signal quality not in price | d | – | – |
| S13 | Foundations of technical analysis | Lo, Mamaysky, Wang | 2000 | Journal of Finance 55(4):1705–1765 | web.mit.edu/~alo/www/Papers/techanal.html (snippet) | ABS | US stocks | 1962–1996 | daily | kernel-regression patterns | some patterns carry incremental information; volume-conditioning details not verified | d | not verified | no |
| S14 | Price momentum and trading volume | Lee, Swaminathan | 2000 | Journal of Finance 55(5):2017–2069 | econpapers RePEc:bla:jfinan:v55:i5 | ABS | US stocks | not stated | monthly | turnover × momentum sorts | high turnover → lower future returns; high-volume winners reverse faster | b, d | no | not stated |
| S15 | Bitcoin intraday time series momentum | Shen, Urquhart, Wang | 2022 | Financial Review 57(2):319–344 | research.birmingham.ac.uk (abstract) | ABS | BTC | not stated | half-hourly | first half-hour predicts the last; volume as a market-time proxy | predictability strongest in the highest-volume/volatility sessions; economic gains | a, b, c | yes | not verified |
| S16 | The intraday dynamics of bitcoin | Eross, McGroarty, Urquhart, Wolfe | 2019 | RIBAF 49:71–81 | econpapers RePEc:eee:riibaf:v49 | ABS | BTC (Bitstamp) | 4 years (dates not stated) | 5-min | intraday patterns, Granger | volume builds through the day, falls ~4pm–midnight; liquidity highest at major stock-market opens | c | no | no |
| S17 | Bitcoin time-of-day, day-of-week and month-of-year effects in returns and trading volume | Baur, Cahill, Godfrey, Liu | 2019 | Finance Research Letters 31:78–92 | econpapers RePEc:eee:finlet:v31:p78 | ABS | BTC, 7 exchanges | not stated | intraday | calendar tests | return anomalies not persistent; volume lower in local evening/weekends, persistent | c | – | no |
| S18 | Periodicity in cryptocurrency volatility and liquidity | Hansen, Kim, Kimbrough | 2024 | J. Financial Econometrics 22(1):224–251 | arxiv.org/abs/2109.12142 ; quantpedia summary | ABS + practitioner summary | BTC, ETH; Coinbase Pro, Binance, Uniswap V2 | not stated | intraday/minute | periodicity analysis, GARCH | day/hour/within-hour periodicity, intensifying; Coinbase low volume 05–12 UTC; spikes 00/16 UTC; minute 0/15/30/45 bursts | c | yes (GARCH forecasts) | no |
| S19 | The quarter-hour effect | Kim, Hansen | 2026 | arXiv 2607.09426 (WP) | arxiv.org/abs/2607.09426 | ABS | 6 Binance perpetuals | not stated | trade-level | autocorrelation map | opening order imbalance predicts 4–12h returns out of sample | a, c, d | yes | not stated |
| S20 | Short-term bitcoin market prediction via machine learning | Jaquart, Dann, Weinhardt | 2021 | J. Finance & Data Science 7:45–66 | publikationen.bibliothek.kit.edu/1000150665/149388567 | FULL | BTC (Bloomberg) | Mar–Dec 2019 | 1-min; horizons 1/5/15/60 min | GRU, LSTM, GBC, RF, LR, FNN | no BTC volume feature; ensemble accuracy 0.515/0.526/0.538/0.558; negative after a 30 bps round trip | a, f, g | yes | yes |
| S21 | Prediction of cryptocurrency returns using machine learning | Akyildirim, Goncu, Sensoy | 2021 | Annals of OR 297:3–36 | repository.bilkent.edu.tr (PDF) | FULL | 12 coins (Bitfinex via Kaiko) | Aug 2017–Jun 2018 | 15/30/60-min, daily | SVM, LR, ANN, RF; 40 features incl. volume and buyer-initiated volume | 55–65% accuracy; volume claimed useful, not isolated | a, f | yes | no |
| S22 | Forecasting and trading cryptocurrencies with machine learning under changing market conditions | Sebastião, Godinho | 2021 | Financial Innovation 7 (doi 10.1186/s40854-020-00217-x) | pmc.ncbi.nlm.nih.gov/articles/PMC7785332/ | FULL (first ~100k characters) | BTC, ETH, LTC | Aug 2015–Mar 2019; test from Apr 2018 | daily | linear/RF/SVM ensembles; 50 inputs incl. volume | after a 0.5% round trip: ETH +9.6%, LTC +5.7%, BTC −23.7% a year; no feature importance | f, g | yes | yes |
| S23 | Microstructure and market dynamics in crypto markets | Easley, O'Hara, Yang, Zhang | 2024 | SSRN 4814346 (WP) | stoye.economics.cornell.edu/docs/Easley_ssrn-4814346.pdf | FULL | 5 coins (Binance) | Jan 2021–Jul 2023 | 1-min bars | random forest, mean decrease in accuracy | AUC 0.54–0.61; Roll and VPIN dominate | d, f | yes (train/test) | no |
| S24 | Technical trading and cryptocurrencies | Hudson, Urquhart | 2021 | Annals of OR 297:191–220 | centaur.reading.ac.uk/85715 (snippet) | ABS | 2 BTC markets + 3 coins | not stated | not stated | ~15,000 rules, multiple-testing correction | predictability in all classes; break-even costs well above typical; BTC none out of sample; OBV inclusion unverified | d, g | yes | yes (break-even) |
| S25 | The effectiveness of technical trading rules in cryptocurrency markets | Corbet, Eraslan, Lucey, Sensoy | 2019 | Finance Research Letters 31:32–37 | econpapers RePEc:eee:finlet:v31:p32 | ABS | BTC | 2,341,440 minutes | 1-min | MA oscillator, range breakout | variable-length MA best (price-only baseline) | a | not stated | not stated |
| S26 | Technical trading rules in the cryptocurrency market | Grobys, Ahmed, Sapkota | 2020 | Finance Research Letters 32:101396 | osuva.uwasa.fi/handle/11111/619 | ABS | 11 coins | 2016–2018 | daily | variable MA | 20-day variable MA works; excluding BTC 8.76% p.a. excess | a | not stated | not stated |
| S27 | The profitability of technical trading rules in the Bitcoin market | Gerritsen, Bouri, Ramezanifar, Roubaud | 2020 | Finance Research Letters 34:101263 | research-portal.uu.nl (abstract) | ABS | BTC | Jul 2010–Jan 2019 | daily | 7 trend indicators, bootstrap Sharpe | range breakout best; OBV inclusion only from secondary coverage | d | no | no (per secondary) |
| S28 | Technical analysis on the Bitcoin market: trading opportunities or investors' pitfall? | Resta, Pagnottoni, De Giuli | 2020 | Risks 8(2):44 | econpapers RePEc:gam:jrisks:v8 | ABS | BTC | Jan 2012–Aug 2019 | 5-min, daily | trend/mean-reversion rules | intraday: buy-and-hold wins; daily: SMA best | a, g | not stated | not stated |
| S29 | Technical analysis in cryptocurrency markets: do transaction costs and bubbles matter? | Svogun, Bazán-Palomino | 2022 | JIFMIM 79:101601 | ideas.repec.org (abstract) | ABS | BTC, ETH, XRP, LTC | 2016–2021 | daily, 1-min | 69 MA/breakout rules | costs lower profitable-rule odds for XRP/LTC, raise them for BTC/ETH (as reported) | g | not stated | yes |
| S30 | Liquidity and market efficiency in cryptocurrencies | Wei | 2018 | Economics Letters 168:21–24 | econpapers RePEc:eee:ecolet:v168 | ABS | 456 coins | not stated | daily | autocorrelation, Hurst vs liquidity | predictability diminishes with liquidity; BTC relatively efficient | a, e | no | no |
| S31 | Crypto wash trading | Cong, Li, Tang, Yang | 2023 | Management Science 69(11):6427–6454 | arxiv.org/pdf/2108.10984 (Jul 2021 draft) | FULL (WP) + published abstract | BTC, ETH, LTC, XRP; 29 exchanges | 9 Jul–3 Nov 2019 | trade-level | Benford, round-size clustering, power-law tails | unregulated wash share avg 77.5% (Tier-1 53.4%, Tier-2 81.7%); none on regulated; Binance = UT1 | e | n/a | n/a |
| S32 | Direct evidence of bitcoin wash trading | Aloosh, Li | 2024 | Management Science 70(12):8875–8921 | econpapers RePEc:inm:ormnsc:v70 | ABS (+SEC) | BTC (Mt. Gox) | 2011–2013 | trade-level | leaked account data | ~2.1% of transactions wash (SEC); Benford/size-clustering detectors useful | e | n/a | n/a |
| S33 | Wash trading at cryptocurrency exchanges | Le Pennec, Fiedler, Ante | 2021 | Finance Research Letters 43:101982 | econbiz record | bibliographic only; findings SEC | not verified | not verified | – | web traffic / liquidity vs reported volume | "96–98% questionable" at suspect exchanges (SEC, unverified) | e | – | – |
| S34 | Trading volume manipulation and competition among centralized crypto exchanges | Amiram, Lyandres, Rabetti | 2025 | Management Science 71(10):8604–8622 | ideas.repec.org (abstract) | ABS | exchanges | not stated | – | competition vs volume inflation | competition associated with inflation; manipulators punished in the long run | e | – | – |
| S35 | Bitwise presentation to the SEC (free writing prospectus) | Bitwise Asset Management | 2019 | SEC filing (FWP, 27 Mar 2019) | sec.gov/Archives/edgar/data/1763415/000149315219004052/fwp.htm | FULL (filing text); "real 10" list SEC | BTC | early Mar 2019 | – | order books, spreads, trade-size histograms | 95% of reported volume fake; 71/81 exchanges; ~$270m real vs ~$6bn reported a day | e | – | – |
| S36 | BTI wash-trading report | Blockchain Transparency Institute | 2018 | industry report | theblock.co coverage | SEC | BTC pairs | Dec 2018 | – | undisclosed | >80% of CoinMarketCap top-25 BTC-pair volume wash; Binance, Bitfinex not "grossly" | e | – | – |
| S37 | Exchange Benchmark | CCData / CoinDesk Data | 2024–2025 | industry report | coindesk.com/research/exchange-benchmark-april-2025 | FULL (Apr 2025 page); Nov 2024 ABS | spot exchanges | Apr 2025; Nov 2024 | – | 100+ metrics, AA–F | AA: Binance 90.1, Coinbase 89.8, Bitstamp 88.4, Kraken 84.5; KuCoin not found | e | – | – |
| S38 | Trading and arbitrage in cryptocurrency markets | Makarov, Schoar | 2020 | JFE 135(2):293–319 | econpapers RePEc:eee:jfinec:v135 | ABS | BTC etc.; 34 exchanges, 19 countries | not stated | tick | signed-volume decomposition | recurrent cross-exchange gaps; common signed volume explains 80% of returns (contemporaneous) | d, e | no | no |
| S39 | Is Bitcoin really un-Tethered? | Griffin, Shams | 2020 | Journal of Finance 75(4):1913–1964 | econpapers RePEc:bla:jfinan:v75:i4 | ABS + SEC | BTC, USDT (Bitfinex) | Mar 2017–Mar 2018 (SEC) | intraday flows | blockchain flows | Tether purchases follow BTC declines (SEC) | e | – | – |
| S40 | What keeps stablecoins stable? | Lyons, Viswanath-Natraj | 2023 | JIMF 131:102777 | wrap.warwick.ac.uk/173269/1/ (PDF) | FULL (targeted reading) | USDT and others | ~2017–Mar 2020 | daily | peg deviation, redemption arbitrage | USDT deviation SD 128.9 bps, range −960/+571, half-life 6.4 days; ~50% smaller after the ETH migration | e | – | – |
| S41 | On-balance volume (Granville) | Granville | 1963 (book) | book | – | not fetched | – | – | – | – | – | d | – | – |

Some figures quoted above (Garfinkel −0.473%/day, Cong 77.5% / 53.4% / 81.7%, Jaquart's 30 bps round trip) were
re-checked against the saved full-text extracts while writing this document.

### 4.9 Numbers a builder can use (each with its source)

**Relative-volume windows:**
- 30-day: log(V_t) − log(mean of the last 30 days' V), divided by the 30-day SD [S5].
- 30-day: (turnover − prior 30-day mean) / 30-day SD [S6].
- 49-day reference window; high/low volume = top/bottom 10% [S9].
- SMAs of dollar volume over 3/5/10/20/50/100/200 days divided by current volume [S4].

**Thresholds:**
- Studies use deciles [S9] and quintiles ([S4], [S7], [S6], [S5]).
- **No paper tests 1.5× or 2× average volume.** Those are practitioner conventions: **unverified**.

**Coinbase seasonality** [S18] (via a practitioner summary):
- volume much lower 05:00–12:00 UTC;
- spikes at 00:00 and 16:00 UTC;
- within-hour bursts at minutes 0/15/30/45;
- weekends lower, Saturday lowest.

**To avoid:** full-sample detrending ([S1], [S2]) uses future data.

**Effect sizes:**
- abnormal volume, high-minus-low quintile −0.473% a day [S6];
- dollar volume, high-minus-low −3.2% a week [S7];
- volsma_50d −1.58% a week raw, not significant after factors [S4];
- volume MACD +2.01% a week raw, not significant after factors [S4].

**Wash trading:**
- 2019 unregulated exchanges: 77.5% average, 79.1% median; Tier-1 53.4%, Tier-2 81.7% [S31];
- Bitwise 2019: 95% fake [S35];
- BTI 2018: above 80% of top-25 BTC-pair volume (secondary) [S36].

**Vetted venues:**
- Bitwise "real 10" (2019): Binance, Bitfinex, bitFlyer, Bitstamp, Bittrex, Coinbase Pro, Gemini, itBit, Kraken,
  Poloniex [S35];
- CoinDesk Data AA (April 2025): Binance, Coinbase, Bitstamp, Kraken [S37];
- **KuCoin is on none of these** (its CCData grade was not found: unverified).

**USDT versus USD:** deviation SD about 129 bps, extremes −960 / +571 bps, half-life 6.4 days (2017–2020) [S40].

**Costs at which edges vanish:**
- a 30 bps round trip turns 1–60 min ML negative [S20];
- a 0.5% round trip turns daily BTC ML negative [S22];
- CTREND break-even 1.41% per unit of turnover [S4];
- value-weighted reversal alphas are insignificant at 30/40 bps [S5].

### 4.10 Sources tried but not read (claims resting only on these are unverified)

| Source | Reason |
|---|---|
| S3 Tan & Tao, full text | ScienceDirect and SSRN returned 403; abstract from search snippets only |
| S15 Shen et al., full text | repository bot-blocked; eprints host DNS failure |
| S16 Eross et al., full text | core.ac.uk 403; Southampton 403 |
| S24 Hudson & Urquhart, full text | Hull repository 403; Springer login; OBV inclusion unverified |
| S27 Gerritsen et al., full text | Utrecht repository 403 |
| S28 Resta et al., full text | MDPI 403 |
| S31 Cong et al., published version | used the arXiv/NBER working paper instead |
| S33 Le Pennec et al. | no abstract retrieved; all numbers secondary |
| S32 Aloosh & Li, full text | abstract plus secondary only |
| S36 BTI original reports | not found; coverage only |
| Kaiko exchange ranking | not verified; KuCoin grade unknown |
| CCData Nov 2024 report page | 404 |
| Coinbase official fee page | 403; fee figures from the app's own source comment and third-party sites |
| Anghel 2021; Wen, Bouri, Xu, Zhao 2022 | abstract not usable / not retrieved |
| S41 Granville OBV book | not fetched |
| Aharon & Qadan; Kristjanpoller | not checked (time budget) |

## 5. Empirical test: data and method

### 5.1 Data actually used

**Coins.**
- **Default list:** BTC, ETH, XRP, BNB, DOGE. This is the app's default coin list (`pt_hub.py` line 510;
  `exchange_check.settings_coins` falls back to it).
- **Extended set:** SOL, LTC, ADA, LINK, AVAX, added only for sample size. They are **not** the owner's list.
- **The owner's own coin list was not read.** It lives in the real app-data folder, which is off-limits.
- Every table is pooled over the 10 coins unless it says otherwise, and one table repeats the main split for the 5
  default coins alone.

**Window.**
- 3 years: 2023-11-06 00:00 to 2026-11-05 00:00 UTC (1,095 days), the trainer's default `3y` window.
- **BNB-USD has Coinbase bars only from October 2025.** About 9,067 hourly bars; the cache records that Coinbase has
  none before.

**Timeframes.**
- 1h and 15m Coinbase bars for entries, volume measures and exits.
- 2h, 4h, 8h, 12h and 1w built from 1h, and native 1d: the trainer's seven timeframes, through the app's own
  `ExchangeFetcher` build path.

**Exchanges** (public, unauthenticated candle requests through the app's own `market_data/candles.py`
`exchange_candles`, into a sandboxed cache; each connector's request pacing applied):

| Exchange | Market | Answered from this machine | Coverage used |
|---|---|---|---|
| Coinbase (primary) | `<COIN>-USD` | yes | full 3 years, 1h and 15m (BNB from Oct 2025) |
| Binance | `<COIN>USDT` | yes | full 3 years, 1h and 15m |
| KuCoin | `<COIN>-USDT` | yes | full 3 years, 1h and 15m |
| Kraken | `XBTUSD` for BTC, `<COIN>USD` otherwise | yes | **its latest 720 bars only** (the connector says so): about 28 days of 1h and 7 days of 15m. Used for an agreement check, not in the 3-year aggregate. |

- **[TEST] All four connectors return base-asset volume** (BTC, not dollars).
- **The "aggregated" volume** is the sum of Coinbase, Binance and KuCoin base volume on the same bar, and is missing
  where any of the three is missing. No USD/USDT conversion is needed for base units.

**Trade History entries: not available.** They are in the real app-data folder (holdings.db / trade history), which
is off-limits. No Trade History entry is used or fabricated; the owner may supply an export later.

### 5.2 Entries replayed

1. **STRAT-001, as the app ships it.**
   - Catalogue defaults: TEMA 12/48, persistence 2, ADX(14) ≥ 20, no overlays (`strategies/settings.py` defaults).
   - Run through the app's own backtester (`backtest/engine.run_backtest`): a signal on bar t's close fills at bar
     t+1's open, and exits on the strategy's own EXIT.
   - Run on 1h (the default timeframe) and on 15m (a timeframe Settings allows).
   - The whole 3-year window, per coin.
2. **The neural trade-start condition.**
   - The pattern model was trained on the first 80% of the window (2023-11-06 to 2026-03-31; the repo's
     `validation_cut`) and replayed on every held-out hour (2026-03-31 to 2026-11-05, 5,251 hours a coin).
   - At each hour's close every timeframe predicts from its last closed bar, exactly as STRAT-003 / `pt_thinker` do in
     steady state (`pattern_model.thinker_decision`, price = the 1h close).
   - A signal is ≥ 3 timeframes long and none short (`trade_start_level` 3).
   - Each signal taken while flat is replayed with the legacy trade rules, as in the training-gate design of
     2026-11-03:
     - entry of 1% of a 100-unit account;
     - DCA at the hard levels (−2.5%, −5%, −10%, …) or at the neural level (4–7) while below cost, at 2× the current
       value, at most 2 in 24 h, within Max per coin 10%;
     - trailing PM: start +5% (+2.5% after a DCA), 0.5% gap, sell on a cross from above;
     - fees on every fill.
   - The exit path is the 15-minute closes.
   - A trade open at the end of the holdout is closed at the last close, and counts as a loss if it was open more than
     7 days.

### 5.3 Scoring (the training gate's fee-adjusted rule)

- **The design is not implemented.** The model gate (design 2b) is not in the code yet (`training_settings.py`
  lines 8–9), so its rule is implemented here as the design states it.
- **Net return:** `net = (1 − f) × (exit_fill / entry_fill) × (1 − f) − 1`, the same formula as
  `llm_signals.net_return` and the backtester's `pnl_pct`.
  - Fills include the backtester's 5 bps slippage.
  - For DCA trades: net P&L over all capital committed.
- **A win** is a net return above zero ("a win means the net gain beats the fees").
- **Fee `f` (primary):** **1.20% per side**, Coinbase taker at the $0–1K tier. This is what the app assumes
  (`pt_exchange_abstraction.DEFAULT_TRADING_FEES`, lines 203–213), and the trader places market orders, so taker.
- **The owner's real Coinbase tier is unverified.** Sensitivity, labelled as such: 0.60%, 0.40% and 0.10% (the
  backtester's default) per side, and gross (0%).

### 5.4 Volume measures and how look-ahead was excluded

Every measure for an entry is taken **at the signal bar t**, which has closed when the decision is made; the fill is
at bar t+1's open. Averages use bars **strictly before t** (`shift(1)`), so bar t is compared only with its own past.
No full-sample detrending, ranking or threshold fitted on the data is used. The buckets are fixed thresholds chosen
before looking at results (low < 0.7×, normal 0.7–1.5×, high > 1.5×); the quintile tables are descriptive only.

| Measure | Definition (at signal bar t) |
|---|---|
| `rv_hod20` (main) | V_t / mean of V at the same UTC time of day on the previous 20 days |
| `rv20` | V_t / mean of the previous 20 bars |
| `rv1d`, `rv7d` | V_t / mean of the previous 1 day / 7 days of bars |
| OBV rising | OBV_t − OBV_{t−20} > 0 |
| Price/OBV divergence | price up over 20 bars while OBV fell (bearish), or the reverse |
| VWAP distance | close_t / rolling 1-day VWAP (typical price) − 1 |
| Spike | max `rv20` over bars t−4 … t ≥ 3 |
| CMF-20 | Chaikin money flow over bars t−19 … t (FDS-SIG-002 candidate A) |

Each measure is computed from Coinbase volume alone and from the aggregate; the main measure also from Binance alone
and KuCoin alone. Prices are always Coinbase's.

### 5.5 Model experiment

- **Same windows, same holdout.** The repo trainer's `run_pass` and `train` were copied from the unmodified module at
  run time and changed in one place: the pattern gets a second dimension, the bar's relative volume (V / mean of the 20
  bars before it, same timeframe).
  - Matching uses the trainer's own per-dimension difference, averaged, against the adaptive threshold. This is how
    upstream's multi-candle patterns combine dimensions.
- **[TEST] Faithful copy.** With the volume dimension off, the copy wrote **35 of 35 model files byte-identical** to
  the repo `train()` on the same window (BTC).
- **[TEST] Faithful predictor.** The generalised predictor matched the repo's `TimeframeModel.predict` on 1,230 of
  1,230 held-out bars per coin (all 10 coins, 0 mismatches).
- **Both models are scored the same way:**
  - direction hit rate per timeframe, against the "always up" base rate;
  - the legacy replay of their signals after fees (§5.2 item 2).

## 6. Empirical results (all [TEST])

Every number in this section is a test result from the research harness on the data in §5.1. "Hit" means the
fee-adjusted hit rate (net return > 0). The base rate is always all entries of the same kind, with n beside it.
p-values compare a subset with the remaining entries: Fisher's exact test for hit rates, Welch's t-test for mean
returns. The full generated tables are in Appendix B.

### 6.1 STRAT-001 at the app's fees: nothing makes it profitable

| STRAT-001, all entries | n | Hit, 1.20%/side (default) | Mean, 1.20% | Mean, 0.60% (sens.) | Mean, 0.40% (sens.) | Mean, 0.10% (sens.) | Mean, gross |
|---|---:|---:|---:|---:|---:|---:|---:|
| 1h, 10 coins, 3 years | 4,333 | 15.6% (95% CI 14.6–16.7%) | −2.50% | −1.31% | −0.92% | −0.32% | −0.12% |
| 15m, 10 coins, 3 years | 16,622 | 6.6% (6.2–7.0%) | −2.50% | −1.31% | −0.92% | −0.32% | −0.12% |

**What this shows:**
- **STRAT-001 has no gross edge.** Its mean is −0.12% a trade before fees (95% CI −0.22% to −0.01% at 1h).
- **Fees dominate.** At the app's assumed 1.20% taker fee each trade loses about 2.5%.
- **No volume subset changes that.** The best is −2.10% a trade (below).

### 6.2 STRAT-001 1h: entries split by volume at the signal bar

**Main measure:** Coinbase same-hour-of-day relative volume (`rv_hod20`), fee 1.20% a side.

| Subset | n | Hit after fees (95% CI) | Mean after fees | Std | p hit vs rest | p mean vs rest | Gross hit | Gross mean |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| All entries (base rate) | 4,333 | 15.6% (14.6–16.7%) | −2.50% | 3.5% | | | 36.1% | −0.12% |
| Low volume (< 0.7×) | 1,719 | 13.0% (11.5–14.7%) | −2.74% | 3.0% | <0.001 | <0.001 | 33.6% | −0.37% |
| Normal (0.7–1.5×) | 1,608 | 14.7% (13.1–16.6%) | −2.5% | 3.7% | 0.316 | 0.986 | 35.3% | −0.1% |
| High volume (> 1.5×) | 950 | 21.2% (18.7–23.9%) | −2.10% | 3.9% | <0.001 | <0.001 | 41.3% | +0.29% |

56 entries had too little history for the measure.

**The same split, with the other baselines and sources** (hit after fees / mean after fees, 1.20% a side):

| Volume measure | Low (< 0.7×) | High (> 1.5×) | Effect? |
|---|---|---|---|
| Coinbase, same hour of day, 20 days | 13.0% / −2.74% (n 1,719) | 21.2% / −2.10% (n 950) | yes |
| Coinbase, rolling 7 days | 13.9% / −2.7% (n 1,853) | 19.9% / −2.2% (n 979) | yes |
| Coinbase, rolling 20 bars | 15.5% / −2.7% (n 1,854) | 16.3% / −2.4% (n 933) | **no** (p hit 0.93 / 0.51) |
| Coinbase, rolling 1 day | 15.9% / −2.6% (n 1,829) | 15.8% / −2.4% (n 916) | **no** (p hit 0.70 / 0.84) |
| Aggregate (CB + Binance + KuCoin), same hour | 12.8% / −2.8% (n 1,636) | 20.1% / −2.2% (n 894) | yes, same as Coinbase alone |
| Binance alone, same hour | 12.5% / −2.7% (n 1,693) | 19.4% / −2.3% (n 900) | yes |
| KuCoin alone, same hour | 12.8% / −2.7% (n 1,687) | 18.4% / −2.4% (n 944) | yes, weakest |

**Robustness of the main measure** (tests that do not assume entries are independent):
- **Per coin:** the high-volume bucket beat the coin's own base hit rate in **9 of 10 coins** (sign test p = 0.021) and
  its mean in 9 of 10 (p = 0.021). The low bucket fell below on hit in 9 of 10 and on mean in 10 of 10 (p = 0.002).
- **Week-clustered bootstrap** (high minus rest): hit +3.6 to +11.0 points; mean return +0.2 to +0.9 points (95% CIs).
- **Both halves of the window** (split 2025-05-31):
  - first half: high 23.8% vs base 17.1% (n 488 / 2,164);
  - second half: high 18.4% vs base 14.1% (n 462 / 2,169). The second-half mean difference is not significant
    (p = 0.17).
- **Default-list coins only** (BTC, ETH, XRP, BNB, DOGE): high 19.0% vs base 13.1% (n 457 / 2,032), mean −2.1% vs
  −2.5%.
- **Not just volatility.** Within terciles of recent volatility (20-bar return SD, per coin), high-volume entries
  still had higher gross means:
  - mid volatility: +0.54 points (p = 0.023);
  - high volatility: +0.88 points (p < 0.001), at the same average move size (3.18% vs 3.20%);
  - low volatility: +0.24 points (p = 0.36).
- **Monotonic.** By quintile of `rv_hod20` the hit rate rises 11.6% → 14.5% → 14.9% → 15.4% → 21.0%, and the mean
  rises −2.8% → −2.1%. The cut points come from the pooled sample, so this table is descriptive only.

**The candidate rules as filters** (Coinbase `rv_hod20`, fee 1.20%):

| Rule | Entries kept | Hit after fees | Mean after fees | Mean change vs no filter (95% bootstrap CI) | Mean at 0.40% (sens.) | Mean at 0.10% (sens.) | Gross mean |
|---|---:|---:|---:|---|---:|---:|---:|
| No filter (base rate) | 4,333 | 15.6% | −2.50% | | −0.92% | −0.32% | −0.12% |
| Require above average (> 1.0×) | 1,766 | 17.8% | −2.3% | +0.2 (−0.0 to +0.4) | | | |
| Require high volume (> 1.5×) | 950 | 21.2% | −2.10% | +0.4 (+0.1 to +0.7) | −0.51% | +0.09% (95% CI −0.16 to +0.34) | +0.29% (+0.04 to +0.55) |
| Block low volume (drop < 0.7×) | 2,558 | 17.1% | −2.36% | +0.1 (−0.0 to +0.3) | −0.77% | −0.17% | +0.03% |

**Other volume measures at 1h** (Coinbase; with / without the condition; fee 1.20%). None improves both the hit rate
and the mean:

| Condition at the signal bar | Hit with / without | Mean with / without | p hit | p mean |
|---|---|---|---:|---:|
| OBV rising over 20 bars | 13.2% / 17.4% (n 1,868 / 2,465) | −2.4% / −2.6% | <0.001 | 0.061 |
| Price/OBV bearish divergence | 12.6% / 15.9% (n 435 / 3,898) | −2.6% / −2.5% | 0.081 | 0.57 |
| Close above 1-day VWAP | 14.5% / 17.6% (n 2,789 / 1,544) | −2.4% / −2.6% | 0.010 | 0.093 |
| Volume spike ≥ 3× in the last 5 bars | 15.1% / 15.7% (n 897 / 3,436) | −2.3% / −2.6% | 0.64 | 0.026 |
| CMF-20 > 0 (FDS-SIG-002 candidate A) | 15.2% / 16.1% (n 2,503 / 1,830) | −2.5% / −2.6% | 0.42 | 0.28 |

"OBV rising" and "close above VWAP" go with a *lower* hit rate, so as confirmation filters they would make entries
worse. One possible reason is that a move that has already happened leaves less room before the fee hurdle
(interpretation, not tested).

### 6.3 STRAT-001 15m: the same pattern, smaller

| Subset (Coinbase `rv_hod20`, fee 1.20%) | n | Hit after fees (95% CI) | Mean after fees | Gross mean |
|---|---:|---|---:|---:|
| All entries (base rate) | 16,622 | 6.6% (6.2–7.0%) | −2.50% | −0.12% |
| Low volume (< 0.7×) | 7,711 | 4.8% (4.3–5.3%) | −2.55% | −0.17% |
| Normal | 4,931 | 6.6% (5.9–7.3%) | −2.5% | −0.1% |
| High volume (> 1.5×) | 3,652 | 10.2% (9.2–11.2%) | −2.42% | −0.04% |

- **Per coin:** high > base hit in 10 of 10 coins (p = 0.002) and on mean in 9 of 10.
- **Week-clustered CI:** hit +3.0 to +6.2 points; mean −0.0 to +0.2 points.
- **Mostly volatility at 15m.** Within volatility terciles the effect appears only in the high-volatility third: hit
  +5.5 points, gross mean +0.16 points (p = 0.030), with larger moves (1.93% vs 1.51%).
- **Rolling baselines show nothing:**
  - rolling 20-bar RV: high 6.8% vs base 6.6% (p = 0.53);
  - rolling 1-day RV: high 7.5% vs base 6.6%, mean unchanged.
- **Even gross**, the high-volume subset's mean is −0.04%, so at 15m the filter **never** produces a positive mean at
  any fee level.

### 6.4 Neural trade-start entries (held-out 7 months), legacy rules replayed

**Signals and trades:**
- Signal hours, base model: 2,128 across the 10 coins (119–295 per coin).
- Trades taken while flat: **116** at 1.20% a side.
- **The trades are long.** DCA was used in 84% of them, the mean holding time was 390 hours, and 10 were still open
  at the end of the holdout.

| Neural trade-start (base model), fee 1.20% | n | Hit after fees (95% CI) | Mean return a trade | Median | Worst drawdown from cost |
|---|---:|---|---:|---:|---:|
| Model signals | 116 | 90.5% (83.8–94.6%) | +0.73% | +1.51% | −45.7% |
| **Baseline:** random entry hours, same count per coin, same rules (100 draws) | ~130 a draw | median 90.9% (5–95%: 89.2–92.4%) | median +0.65% (5–95%: +0.38 to +0.86%) | | |
| **Baseline:** enter at every hour when flat | 142 | 90.8% | +0.38% | | |

**[TEST] The 90% hit rate comes from the exit rules, not the signal.**
- The trailing PM only sells in profit, and DCA lowers the cost basis.
- Random entries with the same rules score the same: the model sits at the 33rd percentile of random draws on hit rate
  and the 78th on mean.
- **No skill above a model-free base rate.**

**Entries split by Coinbase `rv_hod20` at the signal hour (fee 1.20%):**

| Bucket | n | Hit (95% CI) | Mean |
|---|---:|---|---:|
| High (> 1.5×) | 81 | 93.8% (86.4–97.3%) | +1.7% |
| Normal | 27 | 81.5% (63.3–91.8%) | −2.2% |
| Low (< 0.7×) | 8 | 87.5% (52.9–97.8%) | +0.8% |

- 70% of the neural entries (81 of 116) fall on high-volume hours. The runner signals LONG after sharp drops, which come with heavy
  volume.
- The high-vs-rest differences are not significant: p = 0.085 for hit, 0.040 for mean, against a random baseline that
  already scores about 91%.
- **Too small to separate volume buckets.** The Trade History check could not be run (§5.1).

### 6.5 Model experiment: the pattern model with and without a volume dimension

**Setup:** same windows, same holdout (first 80% fit, last 20% scored), same signal rule, same exit replay, all 10
coins.

| Model | Trades (1.20%) | Hit after fees (95% CI) | Mean a trade | Rank among 100 random-entry draws: hit / mean | Trades (gross) | Gross hit | Gross mean |
|---|---:|---|---:|---|---:|---:|---:|
| Base (body % only) | 116 | 90.5% (83.8–94.6%) | +0.73% | 33rd / 78th percentile | 159 | 94.3% | +2.84% |
| With volume (body % + 20-bar RV) | 119 | 91.6% (85.2–95.4%) | +0.77% | 76th / 84th percentile | 174 | 96.0% | +3.02% |

**Volume model against the base model, at 1.20%:** p = 0.82 for hit rate and 0.96 for mean return. **No
difference.**

**Gross:** the volume model's 96.0% hit was matched or beaten by 1 of 100 random draws, and its mean by 8 of 100. This
is one of four model-versus-random comparisons, and it does not hold at the app's fee. Treat it as noise unless a
fresh window repeats it.

**Direction on held-out bars** (pooled over 10 coins; base rate = the larger of the up and down shares; one-sided
binomial p):

| Timeframe | Base model: n / hit / base rate / p | Volume model: n / hit / base rate / p |
|---|---|---|
| 1hour | 51,617 / 50.03% / 50.29% / 0.88 | 51,514 / 50.64% / 50.30% / 0.064 |
| 2hour | 25,933 / 49.39% / 50.01% / 0.98 | 25,870 / 50.04% / 50.01% / 0.47 |
| 4hour | 12,982 / 50.49% / 50.44% / 0.46 | 12,907 / 50.02% / 50.41% / 0.82 |
| 8hour | 6,492 / 50.40% / 50.26% / 0.42 | 6,286 / 50.75% / 50.14% / 0.17 |
| 12hour | 4,328 / 49.26% / 50.67% / 0.97 | 4,078 / 50.02% / 50.69% / 0.81 |
| 1day | 2,125 / 49.13% / 50.07% / 0.81 | 1,900 / 51.32% / 50.37% / 0.21 |
| 1week | 168 / 50.60% / 52.38% / 0.71 | 21 / 66.67% / 52.38% / 0.14 |

- **No timeframe beats its base rate for either model.** The smallest p is 0.064, one of 14 tests.
- The base model's result matches Test A (no evidence of an edge).
- **The volume dimension made matching harder.** For BTC it multiplied the memories 2.2–3.3× (1hour 291 → 739, 4hour 384 → 1,227) and cut the
  signal hours by 27% (2,128 → 1,560), with no gain in accuracy.

### 6.6 How Coinbase volume moves through the day (supports §4.3)

**Coinbase hourly volume as a share of that day's average hour** (mean over 10 coins, 3 years, UTC):

| 00 | 01 | 02 | 03 | 04 | 05 | 06 | 07 | 08 | 09 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 | 21 | 22 | 23 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1.09 | 1.02 | 0.93 | 0.83 | 0.75 | 0.71 | 0.68 | 0.68 | 0.71 | 0.69 | 0.68 | 0.72 | 0.94 | 1.26 | 1.57 | 1.54 | 1.41 | 1.27 | 1.21 | 1.20 | 1.13 | 0.99 | 1.02 | 0.96 |

- **Daily cycle:** every coin's quietest hour is between 06:00 and 10:00 UTC, and every coin's busiest is 14:00 or
  15:00 UTC.
- **Weekends:** Saturday and Sunday volume is 0.69× and 0.72× the average day; weekdays are 1.08–1.17×.

**The baseline choice decides which hours get labelled "low"** (share of bars labelled low, < 0.7×):

| Baseline | 04–11 UTC | 14–16 UTC |
|---|---|---|
| Rolling 20-bar | **0.60–0.69** | **0.11–0.12** |
| Same hour of day, 20 days | 0.46–0.47 | 0.42–0.44 |

- **The rolling baseline mostly measures the clock.** That fits it carrying no information about STRAT-001 outcomes
  (§6.2).
- **A mean baseline is skewed.** Because volume is right-skewed, V / mean is below 0.7 on about 46% of bars even with
  the same-hour baseline. A median baseline would give more balanced buckets (not tested).

### 6.7 Coinbase against other exchanges (1h, base-asset volume)

| Coin | Coinbase share of CB+BN+KC (median) | Binance share | KuCoin share | corr(log vol) CB–Binance | CB–KuCoin | CB–aggregate | Spearman `rv_hod20` CB–aggregate | Same bucket CB vs aggregate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC | 0.23 | 0.68 | 0.07 | 0.83 | 0.71 | 0.92 | 0.91 | 79% |
| ETH | 0.18 | 0.70 | 0.10 | 0.83 | 0.71 | 0.90 | 0.90 | 79% |
| XRP | 0.28 | 0.61 | 0.09 | 0.69 | 0.77 | 0.83 | 0.93 | 83% |
| BNB | **0.01** | 0.93 | 0.05 | 0.52 | 0.40 | 0.55 | 0.61 | **59%** |
| DOGE | 0.18 | 0.76 | 0.05 | 0.88 | 0.76 | 0.93 | 0.90 | 79% |
| SOL | 0.20 | 0.72 | 0.06 | 0.81 | 0.73 | 0.89 | 0.89 | 78% |
| LTC | 0.23 | 0.64 | 0.10 | 0.81 | 0.53 | 0.89 | 0.88 | 77% |
| ADA | 0.21 | 0.70 | 0.07 | 0.80 | 0.65 | 0.88 | 0.89 | 78% |
| LINK | 0.28 | 0.61 | 0.08 | 0.82 | 0.50 | 0.91 | 0.90 | 79% |
| AVAX | 0.17 | 0.73 | 0.08 | 0.82 | 0.50 | 0.87 | 0.85 | 74% |

**Kraken** (its latest 685 hourly bars, 2026-10-07 to 2026-11-04):
- correlation of log volume with Coinbase 0.56–0.84;
- volume 0.24–0.60× Coinbase's, except BNB (1.03×);
- no zero-volume hourly bars.

**What this shows:**
- **For the majors,** Coinbase-only and aggregated RV agree on the bucket 74–83% of the time and give the same
  STRAT-001 result (§6.2).
- **Where Coinbase is a small venue for the coin** (BNB, 1% of the three-exchange volume), Coinbase volume tracks the
  market poorly.
- **KuCoin agrees least with Coinbase** on every coin but XRP.

### 6.8 Multiple comparisons

296 subset tests were run on the STRAT-001 and neural entries. 138 had p < 0.05, about 15 expected by chance, and 50
pass a Bonferroni threshold (p < 0.00017).

**Almost all of the 50 are one family:** same-hour-of-day (or 7-day) relative volume, high or low bucket, on the
STRAT-001 entries, whatever the volume source. The tests overlap heavily (the same entries in many splits), so the
count overstates the independent evidence. The per-coin sign tests and the week-clustered bootstrap (§6.2) are the
better guide.

## 7. Limitations

**How the owner's safety rules changed the brief:**
1. **Coins.** The owner's coin list lives in the real app-data folder and was not read.
   - The app's default list (BTC, ETH, XRP, BNB, DOGE) was used, plus SOL, LTC, ADA, LINK and AVAX for sample size.
   - Results for the owner's own coins may differ.
2. **Exchanges in Settings** were not read either.
   - "Single exchange" means Coinbase, the owner's primary.
   - "Aggregated" means Coinbase + Binance + KuCoin, the connectors that serve 3 years of public candles and answered
     from this machine.
   - Kraken answered, but serves only its latest 720 bars, so it appears only in the 28-day agreement check (§6.7).
3. **Trade History entries** are in the real app-data folder: **not used, not fabricated.** The owner may supply an
   export later.
4. **The candle cache** is a fresh, sandboxed fetch through the app's own `exchange_candles`, not the owner's cache.
   - Its request pacing ran in the sandbox, so it did not coordinate with the owner's running app on the same IP. The
     fetch stayed within each connector's published rate: about 2–4 requests a second to Coinbase in total, latency-bound.

**Sample sizes and independence:**
- The STRAT-001 samples are large (thousands of entries), but **they are not independent.**
  - Coins move together, and many entries fall in the same weeks.
  - The tables therefore add a per-coin sign test (10 coins, so it can only detect a very consistent effect) and a
    cluster bootstrap over calendar weeks.
- **The neural sample is small:** 116 trades over 7 months (§6.4), 81 of them in one volume bucket. It cannot tell volume buckets apart.

**Multiple comparisons.**
- Hundreds of subset tests were run (§6.8).
- About 5% of them would show p < 0.05 by chance, and the tests overlap heavily.
- Only results that hold across fee levels, both baselines, the per-coin view and the week-clustered bootstrap are
  treated as findings.

**Look-ahead.**
- Every volume measure uses bars up to and including the signal bar, which has closed at the decision; baselines use
  strictly earlier bars; fills are at the next bar's open.
- The bucket thresholds (0.7×, 1.5×) were fixed before the results were seen. The quintile tables use cut points from
  the pooled sample and are **descriptive only**: a live rule could not know them in advance.
- The model experiment trains on the first 80% and scores only the last 20%.

**Survivorship.**
- All ten coins are large, still listed and liquid today. Coins that were delisted or collapsed in 2023–2026 are absent.
- BNB has only about 13 months of Coinbase history.

**Market regimes covered.** One 3-year window, so one sequence of regimes:
- BTC rose from $35.1k (Nov 2023) to a $124.7k peak (6 Oct 2025);
- fell to $58.5k (30 Jun 2026);
- ended at $80.4k (4 Nov 2026).
- The neural holdout (2026-03-31 to 2026-11-05) is a single drawdown-and-recovery leg ($68.2k → $58.5k on 30 Jun → $80.4k).

**Fees.**
- The Coinbase tier the app assumes (1.20% taker) is unverified against the owner's account.
- The lower-fee columns are sensitivity, not a claim about the owner's costs.
- Spread is not modelled beyond 5 bps of slippage. That understates costs for thin coins and hours, which are exactly
  the low-volume hours.

**Exit replay approximations.**
- STRAT-001 exits come from the app's backtester (next open after the EXIT bar).
- The legacy replay uses 15-minute closes as the price path, where the trader polls about twice a second, so trailing
  exits are coarser than live.

**Model experiment scope.**
- One volume feature (20-bar relative volume), one way of adding it (a second matching dimension), one window.
- A different feature or encoding could behave differently.

## 8. Recommendation

### 8.1 Whether to build

**Not now, as a way to make the current strategies profitable.**
- **[TEST]** No volume rule turns STRAT-001 or the neural trade start profitable at the app's assumed fee (§6.1–6.4).
- **[SOURCE]** No study shows it at retail costs (§4.7).

**The binding constraint is cost.** STRAT-001's gross mean is about zero (−0.12% a trade) and the assumed round trip
is 2.40%. Do these first; they are outside this module:
1. **Verify the owner's real Coinbase fee tier.** This is design 2c, `trading_fees()` from the account. The 1.20% taker
   rate is the app's assumption and is unverified.
2. **Consider maker (limit) orders.** The app's table has a 0.60% maker rate.
3. **Prefer fewer, longer trades.** This is an inference from the fee arithmetic, not a test.

**If the owner wants the capability anyway** (for example, to track it for later), build only the small piece below:
off by default, and judged by the same fee-adjusted holdout gate as everything else.

### 8.2 Measures and rules

| Use | Measure | Rule | Evidence |
|---|---|---|---|
| **Yes: candidate entry filter** | Same-hour-of-day relative volume: bar t's volume ÷ mean volume of the same UTC hour on the previous 20 days | "Require > 1.5×" (stronger, keeps ~22% of entries) or "block < 0.7×" (weaker, keeps ~59%) | [TEST] §6.2: robust across coins, halves and volatility at 1h; small. [SOURCE] seasonality §4.3. |
| Check only | Rolling 7-day relative volume | same thresholds | [TEST] §6.2: similar, slightly weaker |
| **No** | Rolling 20-bar or 1-day relative volume | – | [TEST] §6.2, §6.6: no effect; mostly the time of day |
| **No** | OBV trend, price/OBV divergence, close vs VWAP, volume spike, CMF-20 | – | [TEST] §6.2: none improves hit rate and mean together; OBV-up and above-VWAP go with lower hit rates. [SOURCE] §4.4: unverified or weak. |

**Thresholds and lookbacks:**
- **20-day same-hour baseline:** 480 hourly bars, or 1,920 at 15m. Use only bars before the signal bar.
- **0.7× / 1.5× cut points:** fixed in advance here, never fitted. The literature uses deciles and quintiles; 1.5×/2×
  are practitioner conventions (unverified, §4.9).
- **A median baseline may balance the buckets better** (§6.6, not tested).
- **Add a weekday/weekend term** if the baseline is ever extended (§6.6: weekend volume ≈ 0.7×).

### 8.3 Single versus aggregated volume, and exclusions

- **Use Coinbase's own volume for Coinbase trading.**
  - **[TEST]** For the majors it agrees with the three-exchange aggregate on the bucket 74–83% of the time and gave the
    same STRAT-001 result (§6.2, §6.7).
  - **[SOURCE]** Coinbase is a regulated venue that showed no systematic wash trading in 2019 (S31) and is graded AA
    (S37).
- **Do not aggregate by default.** No test here showed a gain.
- **Coins where Coinbase is a tiny venue are the exception.** For BNB (1% of the three-exchange volume), Coinbase volume
  tracked the market poorly (bucket agreement 59%). An aggregate of reputable venues may be better there, but the
  benefit is untested; such coins could also simply be left unfiltered.
- **If aggregating:**
  - sum base-asset volume (no USD/USDT conversion needed);
  - include only vetted venues: Coinbase, Kraken, Bitstamp (graded AA, S37; Bitstamp's connector was not checked for
    candles here), and Binance with caution (AA in 2025, but S31 estimated >50% wash trading in 2019);
  - **exclude KuCoin.** It is on no vetted list found (S35, S37; its CCData grade is unverified), and it agreed least
    with Coinbase here (§6.7).
- **Kraken through this connector** serves only its latest 720 bars. That is enough for a live 20-day hourly baseline
  (480 bars), but not for backtests.
- **Route any exchange lookup through the existing exchange layer, primary first** (the multi-exchange design rule).
  Never hard-code one exchange.

### 8.4 Where volume should go

| Place | Recommendation | Basis |
|---|---|---|
| **Model input in training** (pattern trainer) | **No.** | [TEST] §6.5: no holdout gain in direction or after-fee trades; more memories, fewer signals. [SOURCE] §4.6: little incremental value, overfitting risk. |
| **Signal in thinking** (a volume-driven entry or direction signal) | **No.** | [SOURCE] §4.2/4.4: the sign of the volume effect is disputed. [TEST]: volume conditions how well an existing entry does, but was never tested as a stand-alone signal here. |
| **Confirmation filter at entry** (rule-based strategies) | **Only as an optional, off-by-default filter**, and only if built at all (§8.1). It must earn its place through the planned model gate on its own fee-adjusted holdout record. Today it fails the gate (21.2% against 55%). | [TEST] §6.2 |
| Combination | No. | nothing above supports more than the filter |

### 8.5 Two findings for the training-gate design (2b), outside the brief

1. **[TEST] A hit-rate gate cannot judge the legacy DCA + trailing-PM rules.**
   - Random entries score about 91% fee-adjusted hit with those exits (§6.4), because the trailing PM sells only in
     profit and DCA lowers the cost basis.
   - Any signal would "pass" a 55% hit-rate test while carrying deep open drawdowns (worst −45.7% here).
   - The gate should compare a model with a random-entry baseline under the same rules, and weigh drawdown and open
     trades, as the design's logging already hints.
2. **Fees decide the result.**
   - **[TEST]** At the app's assumed Coinbase taker fee every STRAT-001 variant tested loses about 2.1–2.7% a trade,
     where gross they are near zero (§6.1–6.2).
   - **[UNVERIFIED here]** An earlier project note says paper fills charge no fee. If so, paper results overstate live
     ones by about the round-trip fee, and paper results should not be used to judge a volume filter.

## 9. Everything left unverified

**Literature:**
- the full texts of S3, S15, S16, S24, S27, S28;
- the published version of S31;
- S32 and S33 (beyond abstract or secondary coverage);
- the original BTI reports (S36);
- the Kaiko exchange ranking;
- KuCoin's CCData grade;
- whether S24 or S27 include OBV rules;
- Granville's OBV (S41);
- Aharon & Qadan; Kristjanpoller;
- every OBV, VWAP and price/volume-divergence claim (no source found).

**Thresholds:** the 1.5×/2× relative-volume thresholds as published rules (practitioner convention only).

**Fees:** the owner's real Coinbase fee tier and region. The official fee page could not be fetched; the 1.20% taker
rate is the app's assumption.

**Exchange identities:** R1–R3 = Bitstamp, Coinbase, Gemini in S31 (secondary coverage).

**Not tested here:**
- a median baseline, or a weekday-aware baseline;
- volume as a stand-alone signal;
- any other volume encoding in the model;
- coins outside the ten;
- any window other than 2023-11-06 to 2026-11-05;
- Trade History entries (not available).

**Paper fills charge no fee:** from earlier project notes, not re-tested here.

## 10. Reproduction, and what could not be done

**How to reproduce.**
- **Where everything lives:** the research harness, fetched candles and raw outputs are in the session scratch folder
  (`scratchpad/volume-research/`). They are **not** committed: the brief allows one docs file only.
- **Sandbox:** every script imports `sbx.py` first. It points `POWERTRADER_HOME`, `APPDATA` and `LOCALAPPDATA` into
  the scratch folder, fails the keyring, and requires `PYTHONNOUSERSITE=1`.
- **Scripts:**

| Script | What it does |
|---|---|
| `fetch_candles.py` | public candles through `market_data/candles.exchange_candles` |
| `common.py` | volume measures, fees, statistics |
| `replay_strat001.py` | STRAT-001 through `backtest/engine.run_backtest` |
| `vtrainer.py`, `train_models.py` | the trainer copy with an optional volume dimension; the byte-identity check against the repo trainer |
| `replay_neural.py` | holdout signals, legacy replay, random baselines |
| `analyze.py`, `vol_control.py`, `exchange_check.py` | the tables |

- **Data:** the exact bars are identified by the hashes in Appendix A, in the trainer's `candle_sha256` format.

**Not done, and why:**
- **Trade History entries.** They are in the real app-data folder, which is off-limits. Not used, not fabricated.
- **The owner's coin list and exchanges in Settings.** Same reason; the defaults were used (§5.1).
- **A 3-year Kraken aggregate.** The connector serves only Kraken's latest 720 bars.
- **The training gate's own code.** Design 2b is not implemented in the repo, so its fee-adjusted rule was implemented
  in the harness, following the design (§5.3).
- **No authenticated or API-key request and no LLM-provider request was made.** No repo file other than this document
  was changed, and no repo test was run (no code changed).

## Appendix A. Candle series used (Coinbase, Binance, KuCoin; 1h and 15m)

Each row identifies the exact bars used, by SHA-256 in the trainer's `candle_sha256` format. Kraken: its latest 685
hourly bars (2026-10-07 11:00 to 2026-11-04 23:00 UTC) and 638 15-minute bars, agreement check only. The trainer's
2h/4h/8h/12h/1w bars were built from these Coinbase 1h bars; its 1d bars are Coinbase's native daily bars.
| Exchange | Coin | TF | Bars | First open (UTC) | Last open (UTC) | SHA-256 (trainer's `candle_sha256` format) |
|---|---|---|---:|---|---|---|
| coinbase | BTC | 1h | 26270 | 2023-11-06 00:00 | 2026-11-04 23:00 | `bd1105c3be818aed4669e0b430e62943b612beab0e5454bba93b9154a29397e2` |
| coinbase | BTC | 15m | 105063 | 2023-11-06 00:00 | 2026-11-04 23:45 | `ea52b3b158a6ee9bc87d03119cb5cad01cc3db9c2a3b66fb1e6ed5b5bc36869d` |
| binance | BTC | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `05636e3a3e72600563eda6e1dc504860c2450ce3943a2c313c06a608cc1e162a` |
| binance | BTC | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `7d77e4e6b955e04b8b0ecb173a6a4514b57152b6b82d1e878e9ce1e6410301af` |
| kucoin | BTC | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `c4cd3a07a66f6202e4ae1436fdf80862dd40da29c4a2b1731371dea056da4dbe` |
| kucoin | BTC | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `7c93d604fc8308de9019b83fd5c56b41de5123c563ad5e4481db6a01e264a767` |
| coinbase | ETH | 1h | 26270 | 2023-11-06 00:00 | 2026-11-04 23:00 | `1c78130f0905c5258124a95c0896d68c70269bb9f7efacf88a4c64d4fd41c3db` |
| coinbase | ETH | 15m | 105061 | 2023-11-06 00:00 | 2026-11-04 23:45 | `cbeec5fe5d7d987c788001b7f6b6de9f09100a7f448472fb1ce78b5651d36791` |
| binance | ETH | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `a9f67757a43bfbf000c3723f105b2a2fe823845d59e3e9ae06707312aa849e5a` |
| binance | ETH | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `bad03526b8d648d958ca92d65f481c33d9b47229d6703725e1d4c30ac2d9f657` |
| kucoin | ETH | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `14f26ce524a5a38403e4380a3075ca9a01c09ddd5a7b47ddb81753e5cdb6d70f` |
| kucoin | ETH | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `61dd90daae1c7898de406ab47b1ea5f0c620d281e9b9ca52dbc627f52da46edd` |
| coinbase | XRP | 1h | 26270 | 2023-11-06 00:00 | 2026-11-04 23:00 | `49e587aa5029305d504f18cce7fe6de438d0ac3cee36f176769a7738f130ad93` |
| coinbase | XRP | 15m | 105062 | 2023-11-06 00:00 | 2026-11-04 23:45 | `bbf0520099c78886df5a13fa8ceba27b93acfb01c46aa4d7f433f87c3013a8ab` |
| binance | XRP | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `74dc497259f45da96fe5441db16733684a996d71e61e1a044c1819f732a9583c` |
| binance | XRP | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `926d52384db714a41328a60a17a938310cf82af7d0bbc7bc193198d0df676fbc` |
| kucoin | XRP | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `3edcf2ee41b8c4b6d237d5e5cace1475096665e1b739849941dca9f241a32282` |
| kucoin | XRP | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `26b7515c371407db881382238b43a315bb412b6b2cc8839dd6cdb6ee4e1601bd` |
| coinbase | BNB | 1h | 9067 | 2025-10-22 18:00 | 2026-11-04 23:00 | `96340add1189f36314509f8ef5ab453e78af65d9292b7c0692c000d4b22eaf34` |
| coinbase | BNB | 15m | 36258 | 2025-10-22 18:45 | 2026-11-04 23:45 | `ae47d27339d2e433e91fef27ed0b2f8e0cb67395b912b6a05865880bf153fb3d` |
| binance | BNB | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `04f61114fb0f4bfca6c59c45007aff80c01e96a76759be268e310c6b4f34773c` |
| binance | BNB | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `4a10e8de15f87a5e4abfc2f129132c3092c7ef7fa10309cc5cfc80fe85a2ca47` |
| kucoin | BNB | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `8e9bad2135b80d6fcfc9fabb37800582a57fc7f0f67a014592ee2f036cd53b60` |
| kucoin | BNB | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `14fc3f7a520aed61f66901a65b6e29c32ac3d3ab3ae94a59ba011bfbb72393db` |
| coinbase | DOGE | 1h | 26270 | 2023-11-06 00:00 | 2026-11-04 23:00 | `fa18934ab6819858880cd4af1d74346268703a3ce7fff62fb319e97e7e3bb983` |
| coinbase | DOGE | 15m | 105063 | 2023-11-06 00:00 | 2026-11-04 23:45 | `1053704a812e8bd09aeffeca4f41b86bb99341839e366257217613fa11a21e26` |
| binance | DOGE | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `48d284971fd765e2180dd8f2c254829da76ae7484c67140b2cca2a97da21c5bc` |
| binance | DOGE | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `c7e9b0351b3edb0952cace9c0fa5ea4c84616877e5598813a12700992e10f4f5` |
| kucoin | DOGE | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `fb88b7027bb6c56808efa60e8b718be89ca561804d09efc24a3629008a4c26e3` |
| kucoin | DOGE | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `fac73c9a2c861f5a0ccd5967b4d468f940b306bd3a7a00cb0a68b2ec02ac03fd` |
| coinbase | SOL | 1h | 26270 | 2023-11-06 00:00 | 2026-11-04 23:00 | `7b00a2a6de7b3d351974c4508023199398ec2f3f8452a7a33738e7913901b785` |
| coinbase | SOL | 15m | 105062 | 2023-11-06 00:00 | 2026-11-04 23:45 | `042e7ca98d0373e7646f3fb64a5b7e1cdfbab33cce1ba22a9cb13353e410e014` |
| binance | SOL | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `04e8382f5a776af85e2ec3c2a13d39e13022768eac4a4bcea0f2e4ca6a46fb76` |
| binance | SOL | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `9c570a6501d82c17a5e5097ad7aed1211c8a5baaa4525b673048f024bd350f93` |
| kucoin | SOL | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `9c8a383cd144dd10eaebdcae174b9fb6126b6d6d33178d9f2984d782e63eb4a1` |
| kucoin | SOL | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `4fb83fe6737d2a8c307700f30eb765bc4063a2f95502bd515f79cdb9d37301a5` |
| coinbase | LTC | 1h | 26270 | 2023-11-06 00:00 | 2026-11-04 23:00 | `968a793e7955683ccb8a81bde5732e01c60b19367824b236be21580e5fd24211` |
| coinbase | LTC | 15m | 105063 | 2023-11-06 00:00 | 2026-11-04 23:45 | `9ed305de63281df27f6c2ba4c6b5658e13b4c761583c37b54664499b916fac09` |
| binance | LTC | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `7b461103b6f82270f928bc0ecf9b242c93f5a76e3962a604f130139c48ac29ab` |
| binance | LTC | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `34b2379d8054aa417b930a1ffdd1b004628c46ea31693f2c0f5dbcd4a453a0a7` |
| kucoin | LTC | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `0548cc892f68ed4b99735c063ae6c5cd5be82f155687fb829a0c7302ce150e8c` |
| kucoin | LTC | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `d8e2f16a4e05935f6d5e0ed9eb5063907b22cb4f34a2908d6bee7629075a3d52` |
| coinbase | ADA | 1h | 26270 | 2023-11-06 00:00 | 2026-11-04 23:00 | `ff8507d749da1c8de3f864adcfde051874e51a3ed1389b2e7ba58f349414d606` |
| coinbase | ADA | 15m | 105062 | 2023-11-06 00:00 | 2026-11-04 23:45 | `61ac030f08fb4fbccd95628eee7928d2d0f92823e1980c16ca8edf96ee44663b` |
| binance | ADA | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `4a6fb8bd8a8cbb6fea7c1268ff2b2f75858ea4f70ec7c52d760f8dd07fcabb3c` |
| binance | ADA | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `45b22ae39889b16e898af82cafd5b60a46eaa518a63ad007e2a0f0ad468a76f7` |
| kucoin | ADA | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `ed78395c200b708f16eba83d2e59e795082ca058fda6632dec68a78f6ad9e237` |
| kucoin | ADA | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `1333c46f204ee9b3fc84de1de776986969b4b7de548c2fdd886f195efdba1f8c` |
| coinbase | LINK | 1h | 26270 | 2023-11-06 00:00 | 2026-11-04 23:00 | `5d75fa74fb3883286b38fa43ad0774af411ecc177b12b4758c387e1323111e26` |
| coinbase | LINK | 15m | 105063 | 2023-11-06 00:00 | 2026-11-04 23:45 | `c43ed07228900aeb84559b0747459048a3358810260e92c11b4ca284387bc789` |
| binance | LINK | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `c86974aa40f2e6b5b30c3fd34f3b135f219d9d75abca35b547170360e8db25e1` |
| binance | LINK | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `fb16872a5f02c952fc9bb896901a54158d08df06c3d2e089735742240173501e` |
| kucoin | LINK | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `650ab2ead6fbd6ef3d1ed5fea9dfc635de37e6a79cc98e1401457fbf5bbf2897` |
| kucoin | LINK | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `d5c61c2e8e4e9b6166b60b769f70860660440b071c0269ecdfa2e39c4c2b1081` |
| coinbase | AVAX | 1h | 26270 | 2023-11-06 00:00 | 2026-11-04 23:00 | `8a75b1fcea42b78b624aa69dfa296231b7b5f70e9335531989d75520eba887fd` |
| coinbase | AVAX | 15m | 105049 | 2023-11-06 00:00 | 2026-11-04 23:45 | `bf3001573019457dd958f17ae4b9000edabfff52fd2197ea182450ad199aa9a2` |
| binance | AVAX | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `75cfdf0bb1b015f8f8bf4fff5c217bf7154572608a0083ba410d737c11247e98` |
| binance | AVAX | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `604192b534477adc8152b4294169eff48eec7c440974106f2f5a1b6526289fa8` |
| kucoin | AVAX | 1h | 26280 | 2023-11-06 00:00 | 2026-11-04 23:00 | `0f064ed53b8f5b95ce55063c61d0b40fcddad78e9c86806419600cc5820535ea` |
| kucoin | AVAX | 15m | 105120 | 2023-11-06 00:00 | 2026-11-04 23:45 | `9099019b5af37514decf807f182996a4228c9d577365da25cefacf883a3b04e9` |

## Appendix B. Generated tables (unedited output of the harness)

These are the raw tables behind section 6, as `analyze.py` wrote them. Fee labels: `coinbase_default_taker_1.20%` is the primary fee; the `sens_*` levels are sensitivity only; `gross_0%` is before fees. Pooled p-values here assume independent entries: see §6.8.

Primary fee: coinbase_default_taker_1.20% per side plus 0.05% slippage per fill. A win is a net return above zero.

### STRAT-001 entries, 1h bars, Coinbase prices

Coins: ADA, AVAX, BNB, BTC, DOGE, ETH, LINK, LTC, SOL, XRP. Entries: 4333.

**All entries at each fee level**

| Fee level (per side) | n | Hit rate (95% CI) | Mean return | Median return |
|---|---:|---|---:|---:|
| coinbase_default_taker_1.20% | 4333 | 15.6% (14.6%-16.7%) | -2.5% | -3.0% |
| sens_taker_0.60% | 4333 | 23.2% (21.9%-24.5%) | -1.3% | -1.8% |
| sens_taker_0.40% | 4333 | 26.7% (25.5%-28.1%) | -0.9% | -1.4% |
| sens_0.10%_backtester_default | 4333 | 32.8% (31.4%-34.2%) | -0.3% | -0.8% |
| gross_0% | 4333 | 36.1% (34.7%-37.5%) | -0.1% | -0.7% |

**1h: Coinbase volume alone, same-hour-of-day relative volume (20 days); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 4333 | 15.6% (14.6%-16.7%) | -2.5% | 3.5% | | |
| Low volume (< 0.7x) | 1719 | 13.0% (11.5%-14.7%) | -2.7% | 3.0% | <0.001 | <0.001 |
| Normal (0.7x-1.5x) | 1608 | 14.7% (13.1%-16.6%) | -2.5% | 3.7% | 0.316 | 0.986 |
| High volume (> 1.5x) | 950 | 21.2% (18.7%-23.9%) | -2.1% | 3.9% | <0.001 | <0.001 |

(56 entries had no value for this measure: not enough history, or no data from that exchange.)

**1h: Coinbase volume alone, same-hour-of-day relative volume (20 days); fee level gross_0%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 4333 | 36.1% (34.7%-37.5%) | -0.1% | 3.6% | | |
| Low volume (< 0.7x) | 1719 | 33.6% (31.4%-35.8%) | -0.4% | 3.0% | 0.009 | <0.001 |
| Normal (0.7x-1.5x) | 1608 | 35.3% (33.0%-37.6%) | -0.1% | 3.8% | 0.511 | 0.986 |
| High volume (> 1.5x) | 950 | 41.3% (38.2%-44.4%) | 0.3% | 4.0% | <0.001 | <0.001 |

(56 entries had no value for this measure: not enough history, or no data from that exchange.)

**1h: Coinbase volume alone, rolling relative volume (20 bars); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 4333 | 15.6% (14.6%-16.7%) | -2.5% | 3.5% | | |
| Low volume (< 0.7x) | 1854 | 15.5% (14.0%-17.3%) | -2.7% | 3.5% | 0.933 | 0.006 |
| Normal (0.7x-1.5x) | 1546 | 15.3% (13.6%-17.1%) | -2.4% | 3.5% | 0.662 | 0.093 |
| High volume (> 1.5x) | 933 | 16.3% (14.1%-18.8%) | -2.4% | 3.4% | 0.508 | 0.158 |

**1h: Coinbase volume alone, rolling relative volume (1 day); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 4333 | 15.6% (14.6%-16.7%) | -2.5% | 3.5% | | |
| Low volume (< 0.7x) | 1829 | 15.9% (14.3%-17.6%) | -2.6% | 3.5% | 0.703 | 0.019 |
| Normal (0.7x-1.5x) | 1588 | 15.2% (13.5%-17.0%) | -2.4% | 3.5% | 0.572 | 0.109 |
| High volume (> 1.5x) | 916 | 15.8% (13.6%-18.3%) | -2.4% | 3.4% | 0.838 | 0.340 |

**1h: Coinbase volume alone, rolling relative volume (7 days); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 4333 | 15.6% (14.6%-16.7%) | -2.5% | 3.5% | | |
| Low volume (< 0.7x) | 1853 | 13.9% (12.4%-15.5%) | -2.7% | 3.2% | 0.007 | 0.009 |
| Normal (0.7x-1.5x) | 1501 | 14.9% (13.2%-16.8%) | -2.5% | 3.6% | 0.379 | 0.660 |
| High volume (> 1.5x) | 979 | 19.9% (17.5%-22.5%) | -2.2% | 3.8% | <0.001 | <0.001 |

**1h: candidate filters on Coinbase volume alone (same-hour-of-day RV), fee coinbase_default_taker_1.20%**

| Rule | Entries kept | Hit rate after fees | Mean return after fees | Mean return change vs all (95% bootstrap CI) | p (kept vs dropped, hit) |
|---|---:|---:|---:|---|---:|
| No filter (base rate) | 4333 | 15.6% | -2.5% | | |
| Require above-average volume (> 1.0x) | 1766 | 17.8% | -2.3% | 0.2% (-0.0% to 0.4%) | <0.001 |
| Require high volume (> 1.5x) | 950 | 21.2% | -2.1% | 0.4% (0.1% to 0.7%) | <0.001 |
| Block low volume (drop < 0.7x) | 2558 | 17.1% | -2.4% | 0.1% (-0.0% to 0.3%) | <0.001 |

**1h: quintiles of Coinbase volume alone same-hour-of-day RV, fee coinbase_default_taker_1.20%**

| Quintile of the measure | Range | n | Hit rate after fees | Mean return after fees |
|---|---|---:|---:|---:|
| Q1 | 0.08-0.45 | 856 | 11.6% | -2.8% |
| Q2 | 0.45-0.70 | 855 | 14.5% | -2.7% |
| Q3 | 0.70-1.03 | 855 | 14.9% | -2.5% |
| Q4 | 1.03-1.60 | 855 | 15.4% | -2.5% |
| Q5 | 1.60-34.22 | 856 | 21.0% | -2.1% |

**STRAT-001 1h Coinbase volume alone: other volume measures (subset vs the rest)**

| Condition at the signal bar | n with | Hit with | Mean with | n without | Hit without | Mean without | p (hit) | p (return) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OBV rising over 20 bars | 1868 | 13.2% | -2.4% | 2465 | 17.4% | -2.6% | <0.001 | 0.061 |
| Price/OBV bearish divergence (price up, OBV down) | 435 | 12.6% | -2.6% | 3898 | 15.9% | -2.5% | 0.081 | 0.567 |
| Close above 1-day VWAP | 2789 | 14.5% | -2.4% | 1544 | 17.6% | -2.6% | 0.010 | 0.093 |
| Volume spike (>= 3x) in the last 5 bars | 897 | 15.1% | -2.3% | 3436 | 15.7% | -2.6% | 0.642 | 0.026 |
| CMF-20 > 0 | 2503 | 15.2% | -2.5% | 1830 | 16.1% | -2.6% | 0.421 | 0.280 |

**1h: Aggregated volume (Coinbase + Binance + KuCoin, base units), same-hour-of-day relative volume (20 days); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 4333 | 15.6% (14.6%-16.7%) | -2.5% | 3.5% | | |
| Low volume (< 0.7x) | 1636 | 12.8% (11.2%-14.5%) | -2.8% | 3.0% | <0.001 | <0.001 |
| Normal (0.7x-1.5x) | 1747 | 15.6% (14.0%-17.4%) | -2.4% | 3.6% | 0.830 | 0.155 |
| High volume (> 1.5x) | 894 | 20.1% (17.6%-22.9%) | -2.2% | 3.9% | <0.001 | 0.020 |

(56 entries had no value for this measure: not enough history, or no data from that exchange.)

**1h: Aggregated volume (Coinbase + Binance + KuCoin, base units), rolling relative volume (20 bars); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 4333 | 15.6% (14.6%-16.7%) | -2.5% | 3.5% | | |
| Low volume (< 0.7x) | 1788 | 16.4% (14.7%-18.2%) | -2.6% | 3.6% | 0.234 | 0.135 |
| Normal (0.7x-1.5x) | 1737 | 14.0% (12.5%-15.8%) | -2.5% | 3.3% | 0.021 | 0.640 |
| High volume (> 1.5x) | 808 | 17.2% (14.8%-20.0%) | -2.4% | 3.6% | 0.163 | 0.192 |

**1h: Aggregated volume (Coinbase + Binance + KuCoin, base units), rolling relative volume (1 day); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 4333 | 15.6% (14.6%-16.7%) | -2.5% | 3.5% | | |
| Low volume (< 0.7x) | 1772 | 16.6% (14.9%-18.4%) | -2.5% | 3.7% | 0.136 | 0.471 |
| Normal (0.7x-1.5x) | 1768 | 13.9% (12.3%-15.5%) | -2.5% | 3.2% | 0.009 | 0.592 |
| High volume (> 1.5x) | 793 | 17.3% (14.8%-20.1%) | -2.3% | 3.6% | 0.159 | 0.120 |

**1h: Aggregated volume (Coinbase + Binance + KuCoin, base units), rolling relative volume (7 days); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 4333 | 15.6% (14.6%-16.7%) | -2.5% | 3.5% | | |
| Low volume (< 0.7x) | 1739 | 14.1% (12.6%-15.9%) | -2.6% | 3.3% | 0.033 | 0.038 |
| Normal (0.7x-1.5x) | 1702 | 14.6% (13.0%-16.4%) | -2.5% | 3.6% | 0.158 | 0.547 |
| High volume (> 1.5x) | 892 | 20.3% (17.8%-23.1%) | -2.2% | 3.7% | <0.001 | 0.002 |

**1h: candidate filters on Aggregated volume (Coinbase + Binance + KuCoin, base units) (same-hour-of-day RV), fee coinbase_default_taker_1.20%**

| Rule | Entries kept | Hit rate after fees | Mean return after fees | Mean return change vs all (95% bootstrap CI) | p (kept vs dropped, hit) |
|---|---:|---:|---:|---|---:|
| No filter (base rate) | 4333 | 15.6% | -2.5% | | |
| Require above-average volume (> 1.0x) | 1752 | 18.6% | -2.3% | 0.2% (-0.0% to 0.4%) | <0.001 |
| Require high volume (> 1.5x) | 894 | 20.1% | -2.2% | 0.3% (-0.0% to 0.5%) | <0.001 |
| Block low volume (drop < 0.7x) | 2641 | 17.2% | -2.4% | 0.1% (-0.0% to 0.3%) | <0.001 |

**1h: quintiles of Aggregated volume (Coinbase + Binance + KuCoin, base units) same-hour-of-day RV, fee coinbase_default_taker_1.20%**

| Quintile of the measure | Range | n | Hit rate after fees | Mean return after fees |
|---|---|---:|---:|---:|
| Q1 | 0.09-0.50 | 856 | 11.2% | -2.9% |
| Q2 | 0.50-0.72 | 855 | 14.5% | -2.6% |
| Q3 | 0.72-1.02 | 855 | 14.6% | -2.5% |
| Q4 | 1.02-1.54 | 855 | 16.6% | -2.4% |
| Q5 | 1.54-29.03 | 856 | 20.4% | -2.2% |

**STRAT-001 1h Aggregated volume (Coinbase + Binance + KuCoin, base units): other volume measures (subset vs the rest)**

| Condition at the signal bar | n with | Hit with | Mean with | n without | Hit without | Mean without | p (hit) | p (return) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OBV rising over 20 bars | 1843 | 13.5% | -2.4% | 2490 | 17.1% | -2.6% | 0.001 | 0.094 |
| Price/OBV bearish divergence (price up, OBV down) | 406 | 12.6% | -2.6% | 3927 | 15.9% | -2.5% | 0.084 | 0.724 |
| Close above 1-day VWAP | 2757 | 14.7% | -2.4% | 1576 | 17.2% | -2.6% | 0.030 | 0.045 |
| Volume spike (>= 3x) in the last 5 bars | 793 | 15.6% | -2.3% | 3540 | 15.6% | -2.5% | 0.957 | 0.083 |
| CMF-20 > 0 | 2519 | 15.2% | -2.4% | 1814 | 16.1% | -2.6% | 0.445 | 0.156 |

**1h: Binance volume alone, same-hour-of-day relative volume (20 days); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 4333 | 15.6% (14.6%-16.7%) | -2.5% | 3.5% | | |
| Low volume (< 0.7x) | 1693 | 12.5% (11.0%-14.2%) | -2.7% | 3.1% | <0.001 | <0.001 |
| Normal (0.7x-1.5x) | 1684 | 16.3% (14.6%-18.2%) | -2.4% | 3.6% | 0.226 | 0.074 |
| High volume (> 1.5x) | 900 | 19.4% (17.0%-22.2%) | -2.3% | 3.9% | <0.001 | 0.060 |

(56 entries had no value for this measure: not enough history, or no data from that exchange.)

**1h: KuCoin volume alone, same-hour-of-day relative volume (20 days); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 4333 | 15.6% (14.6%-16.7%) | -2.5% | 3.5% | | |
| Low volume (< 0.7x) | 1687 | 12.8% (11.3%-14.5%) | -2.7% | 3.2% | <0.001 | <0.001 |
| Normal (0.7x-1.5x) | 1646 | 16.5% (14.8%-18.4%) | -2.4% | 3.5% | 0.140 | 0.031 |
| High volume (> 1.5x) | 944 | 18.4% (16.1%-21.0%) | -2.4% | 3.8% | 0.005 | 0.217 |

(56 entries had no value for this measure: not enough history, or no data from that exchange.)

**1h: per coin, Coinbase same-hour-of-day RV, fee coinbase_default_taker_1.20%**

| Coin | All: n | All: hit | All: mean | Low (<0.7x): n / hit / mean | Normal: n / hit / mean | High (>1.5x): n / hit / mean |
|---|---:|---:|---:|---|---|---|
| ADA | 472 | 17.6% | -2.6% | 195 / 15.4% / -2.8% | 166 / 17.5% / -2.7% | 107 / 20.6% / -2.1% |
| AVAX | 476 | 16.2% | -2.8% | 228 / 13.2% / -3.1% | 140 / 15.7% / -2.7% | 105 / 23.8% / -2.0% |
| BNB | 143 | 7.0% | -2.5% | 67 / 6.0% / -2.7% | 38 / 10.5% / -2.2% | 33 / 6.1% / -2.1% |
| BTC | 478 | 10.5% | -2.5% | 153 / 6.5% / -2.5% | 206 / 8.3% / -2.7% | 114 / 19.3% / -2.2% |
| DOGE | 476 | 17.2% | -2.4% | 212 / 12.7% / -2.9% | 150 / 20.0% / -2.2% | 106 / 22.6% / -1.7% |
| ETH | 480 | 12.9% | -2.5% | 180 / 11.1% / -2.6% | 195 / 12.8% / -2.5% | 100 / 15.0% / -2.1% |
| LINK | 442 | 19.7% | -2.5% | 183 / 16.9% / -2.6% | 155 / 17.4% / -2.6% | 100 / 27.0% / -2.3% |
| LTC | 456 | 14.9% | -2.5% | 167 / 12.0% / -2.7% | 190 / 16.3% / -2.3% | 90 / 17.8% / -2.7% |
| SOL | 455 | 20.7% | -2.3% | 160 / 21.2% / -2.7% | 197 / 16.8% / -2.6% | 91 / 26.4% / -1.4% |
| XRP | 455 | 13.8% | -2.5% | 174 / 10.3% / -2.6% | 171 / 11.1% / -2.4% | 104 / 23.1% / -2.4% |

**1h: robustness, cb rv_hod20 (per-coin sign test; week-cluster bootstrap), fee coinbase_default_taker_1.20%**

| Bucket | Coins with hit above the coin's base / coins | sign-test p | Coins with mean above / coins | sign-test p | Week-cluster bootstrap 95% CI, hit (bucket - rest) | same, mean return |
|---|---|---:|---|---:|---|---|
| Low volume (< 0.7x) | 1/10 | 0.021 | 0/10 | 0.002 | -6.8% to -1.5% | -0.7% to -0.1% |
| Normal (0.7x-1.5x) | 5/10 | 1.000 | 5/10 | 1.000 | -3.9% to 1.5% | -0.2% to 0.2% |
| High volume (> 1.5x) | 9/10 | 0.021 | 9/10 | 0.021 | 3.6% to 11.0% | 0.2% to 0.9% |

**1h: robustness, cb rv20 (per-coin sign test; week-cluster bootstrap), fee coinbase_default_taker_1.20%**

| Bucket | Coins with hit above the coin's base / coins | sign-test p | Coins with mean above / coins | sign-test p | Week-cluster bootstrap 95% CI, hit (bucket - rest) | same, mean return |
|---|---|---:|---|---:|---|---|
| Low volume (< 0.7x) | 5/10 | 1.000 | 2/10 | 0.109 | -3.4% to 3.0% | -0.6% to 0.1% |
| Normal (0.7x-1.5x) | 4/10 | 0.754 | 6/10 | 0.754 | -3.2% to 2.0% | -0.1% to 0.5% |
| High volume (> 1.5x) | 5/10 | 1.000 | 7/10 | 0.344 | -2.7% to 4.6% | -0.2% to 0.5% |

**1h: robustness, agg rv_hod20 (per-coin sign test; week-cluster bootstrap), fee coinbase_default_taker_1.20%**

| Bucket | Coins with hit above the coin's base / coins | sign-test p | Coins with mean above / coins | sign-test p | Week-cluster bootstrap 95% CI, hit (bucket - rest) | same, mean return |
|---|---|---:|---|---:|---|---|
| Low volume (< 0.7x) | 1/10 | 0.021 | 1/10 | 0.021 | -6.8% to -1.8% | -0.6% to -0.1% |
| Normal (0.7x-1.5x) | 6/10 | 0.754 | 8/10 | 0.109 | -2.5% to 2.9% | -0.1% to 0.4% |
| High volume (> 1.5x) | 10/10 | 0.002 | 9/10 | 0.021 | 1.8% to 10.0% | -0.1% to 0.7% |

**1h: robustness, agg rv20 (per-coin sign test; week-cluster bootstrap), fee coinbase_default_taker_1.20%**

| Bucket | Coins with hit above the coin's base / coins | sign-test p | Coins with mean above / coins | sign-test p | Week-cluster bootstrap 95% CI, hit (bucket - rest) | same, mean return |
|---|---|---:|---|---:|---|---|
| Low volume (< 0.7x) | 8/10 | 0.109 | 3/10 | 0.344 | -1.8% to 4.8% | -0.5% to 0.2% |
| Normal (0.7x-1.5x) | 3/10 | 0.344 | 6/10 | 0.754 | -5.0% to -0.1% | -0.2% to 0.3% |
| High volume (> 1.5x) | 6/10 | 0.754 | 6/10 | 0.754 | -2.0% to 6.0% | -0.2% to 0.6% |

**1h: default-list coins only (BTC, ETH, XRP, BNB, DOGE), Coinbase same-hour-of-day RV, fee coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 2032 | 13.1% (11.7%-14.7%) | -2.5% | 3.2% | | |
| Low volume (< 0.7x) | 786 | 10.1% (8.1%-12.4%) | -2.7% | 2.7% | 0.001 | 0.009 |
| Normal (0.7x-1.5x) | 760 | 12.5% (10.3%-15.0%) | -2.4% | 3.3% | 0.632 | 0.899 |
| High volume (> 1.5x) | 457 | 19.0% (15.7%-22.9%) | -2.1% | 3.7% | <0.001 | 0.015 |

(29 entries had no value for this measure: not enough history, or no data from that exchange.)

**1h: first half of the entries (split at 2025-05-31 09:00:00+00:00), Coinbase same-hour-of-day RV, fee coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 2164 | 17.1% (15.6%-18.7%) | -2.5% | 3.8% | | |
| Low volume (< 0.7x) | 844 | 12.4% (10.4%-14.8%) | -3.0% | 3.0% | <0.001 | <0.001 |
| Normal (0.7x-1.5x) | 781 | 17.3% (14.8%-20.1%) | -2.5% | 4.1% | 0.718 | 0.494 |
| High volume (> 1.5x) | 488 | 23.8% (20.2%-27.7%) | -1.9% | 4.3% | <0.001 | <0.001 |

(51 entries had no value for this measure: not enough history, or no data from that exchange.)

**1h: second half of the entries (split at 2025-05-31 09:00:00+00:00), Coinbase same-hour-of-day RV, fee coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 2169 | 14.1% (12.7%-15.6%) | -2.5% | 3.1% | | |
| Low volume (< 0.7x) | 875 | 13.6% (11.5%-16.0%) | -2.5% | 2.9% | 0.572 | 0.695 |
| Normal (0.7x-1.5x) | 827 | 12.3% (10.3%-14.8%) | -2.5% | 3.3% | 0.065 | 0.415 |
| High volume (> 1.5x) | 462 | 18.4% (15.1%-22.2%) | -2.3% | 3.4% | 0.004 | 0.174 |

(5 entries had no value for this measure: not enough history, or no data from that exchange.)

### STRAT-001 entries, 15m bars, Coinbase prices

Coins: ADA, AVAX, BNB, BTC, DOGE, ETH, LINK, LTC, SOL, XRP. Entries: 16622.

**All entries at each fee level**

| Fee level (per side) | n | Hit rate (95% CI) | Mean return | Median return |
|---|---:|---|---:|---:|
| coinbase_default_taker_1.20% | 16622 | 6.6% (6.2%-7.0%) | -2.5% | -2.7% |
| sens_taker_0.60% | 16622 | 13.9% (13.4%-14.4%) | -1.3% | -1.6% |
| sens_taker_0.40% | 16622 | 18.3% (17.7%-18.9%) | -0.9% | -1.2% |
| sens_0.10%_backtester_default | 16622 | 28.5% (27.8%-29.2%) | -0.3% | -0.6% |
| gross_0% | 16622 | 33.6% (32.9%-34.3%) | -0.1% | -0.4% |

**15m: Coinbase volume alone, same-hour-of-day relative volume (20 days); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 16622 | 6.6% (6.2%-7.0%) | -2.5% | 1.7% | | |
| Low volume (< 0.7x) | 7711 | 4.8% (4.3%-5.3%) | -2.6% | 1.4% | <0.001 | <0.001 |
| Normal (0.7x-1.5x) | 4931 | 6.6% (5.9%-7.3%) | -2.5% | 1.7% | 0.863 | 0.386 |
| High volume (> 1.5x) | 3652 | 10.2% (9.2%-11.2%) | -2.4% | 2.3% | <0.001 | 0.009 |

(328 entries had no value for this measure: not enough history, or no data from that exchange.)

**15m: Coinbase volume alone, same-hour-of-day relative volume (20 days); fee level gross_0%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 16622 | 33.6% (32.9%-34.3%) | -0.1% | 1.8% | | |
| Low volume (< 0.7x) | 7711 | 31.4% (30.4%-32.5%) | -0.2% | 1.4% | <0.001 | <0.001 |
| Normal (0.7x-1.5x) | 4931 | 34.5% (33.2%-35.9%) | -0.1% | 1.8% | 0.074 | 0.386 |
| High volume (> 1.5x) | 3652 | 36.6% (35.0%-38.1%) | -0.0% | 2.3% | <0.001 | 0.009 |

(328 entries had no value for this measure: not enough history, or no data from that exchange.)

**15m: Coinbase volume alone, rolling relative volume (20 bars); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 16622 | 6.6% (6.2%-7.0%) | -2.5% | 1.7% | | |
| Low volume (< 0.7x) | 7653 | 7.1% (6.6%-7.7%) | -2.5% | 1.8% | 0.006 | 0.317 |
| Normal (0.7x-1.5x) | 5682 | 5.7% (5.1%-6.3%) | -2.5% | 1.6% | <0.001 | 0.830 |
| High volume (> 1.5x) | 3287 | 6.8% (6.0%-7.7%) | -2.5% | 1.8% | 0.530 | 0.320 |

**15m: Coinbase volume alone, rolling relative volume (1 day); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 16622 | 6.6% (6.2%-7.0%) | -2.5% | 1.7% | | |
| Low volume (< 0.7x) | 7174 | 5.9% (5.4%-6.5%) | -2.5% | 1.6% | 0.004 | 0.075 |
| Normal (0.7x-1.5x) | 5704 | 6.7% (6.1%-7.4%) | -2.5% | 1.8% | 0.510 | 0.854 |
| High volume (> 1.5x) | 3744 | 7.5% (6.7%-8.4%) | -2.5% | 1.9% | 0.009 | 0.078 |

**15m: Coinbase volume alone, rolling relative volume (7 days); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 16622 | 6.6% (6.2%-7.0%) | -2.5% | 1.7% | | |
| Low volume (< 0.7x) | 7961 | 5.3% (4.8%-5.8%) | -2.5% | 1.5% | <0.001 | 0.017 |
| Normal (0.7x-1.5x) | 4853 | 6.7% (6.0%-7.4%) | -2.5% | 1.7% | 0.704 | 0.561 |
| High volume (> 1.5x) | 3722 | 9.1% (8.3%-10.1%) | -2.5% | 2.2% | <0.001 | 0.063 |

(86 entries had no value for this measure: not enough history, or no data from that exchange.)

**15m: candidate filters on Coinbase volume alone (same-hour-of-day RV), fee coinbase_default_taker_1.20%**

| Rule | Entries kept | Hit rate after fees | Mean return after fees | Mean return change vs all (95% bootstrap CI) | p (kept vs dropped, hit) |
|---|---:|---:|---:|---|---:|
| No filter (base rate) | 16622 | 6.6% | -2.5% | | |
| Require above-average volume (> 1.0x) | 6025 | 8.9% | -2.4% | 0.1% (-0.0% to 0.1%) | <0.001 |
| Require high volume (> 1.5x) | 3652 | 10.2% | -2.4% | 0.1% (0.0% to 0.2%) | <0.001 |
| Block low volume (drop < 0.7x) | 8583 | 8.1% | -2.5% | 0.0% (-0.0% to 0.1%) | <0.001 |

**15m: quintiles of Coinbase volume alone same-hour-of-day RV, fee coinbase_default_taker_1.20%**

| Quintile of the measure | Range | n | Hit rate after fees | Mean return after fees |
|---|---|---:|---:|---:|
| Q1 | 0.01-0.35 | 3259 | 4.4% | -2.5% |
| Q2 | 0.35-0.60 | 3259 | 5.1% | -2.6% |
| Q3 | 0.60-0.93 | 3258 | 5.6% | -2.5% |
| Q4 | 0.93-1.64 | 3259 | 7.2% | -2.5% |
| Q5 | 1.64-62.40 | 3259 | 10.4% | -2.4% |

**STRAT-001 15m Coinbase volume alone: other volume measures (subset vs the rest)**

| Condition at the signal bar | n with | Hit with | Mean with | n without | Hit without | Mean without | p (hit) | p (return) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OBV rising over 20 bars | 7028 | 6.0% | -2.5% | 9594 | 7.0% | -2.5% | 0.008 | 0.026 |
| Price/OBV bearish divergence (price up, OBV down) | 1553 | 5.1% | -2.5% | 15069 | 6.7% | -2.5% | 0.011 | 0.196 |
| Close above 1-day VWAP | 6429 | 5.4% | -2.5% | 10193 | 7.3% | -2.5% | <0.001 | 0.002 |
| Volume spike (>= 3x) in the last 5 bars | 3398 | 6.8% | -2.5% | 13224 | 6.5% | -2.5% | 0.614 | 0.047 |
| CMF-20 > 0 | 8808 | 6.0% | -2.5% | 7814 | 7.2% | -2.5% | 0.002 | 0.452 |

**15m: Aggregated volume (Coinbase + Binance + KuCoin, base units), same-hour-of-day relative volume (20 days); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 16622 | 6.6% (6.2%-7.0%) | -2.5% | 1.7% | | |
| Low volume (< 0.7x) | 7182 | 4.8% (4.3%-5.3%) | -2.5% | 1.4% | <0.001 | 0.006 |
| Normal (0.7x-1.5x) | 5583 | 6.3% (5.7%-7.0%) | -2.5% | 1.7% | 0.423 | 0.786 |
| High volume (> 1.5x) | 3529 | 10.5% (9.5%-11.6%) | -2.4% | 2.3% | <0.001 | 0.005 |

(328 entries had no value for this measure: not enough history, or no data from that exchange.)

**15m: Aggregated volume (Coinbase + Binance + KuCoin, base units), rolling relative volume (20 bars); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 16622 | 6.6% (6.2%-7.0%) | -2.5% | 1.7% | | |
| Low volume (< 0.7x) | 7225 | 7.4% (6.8%-8.0%) | -2.5% | 1.8% | <0.001 | 0.653 |
| Normal (0.7x-1.5x) | 6377 | 5.5% (5.0%-6.1%) | -2.5% | 1.6% | <0.001 | 0.696 |
| High volume (> 1.5x) | 3020 | 6.9% (6.0%-7.8%) | -2.5% | 1.7% | 0.441 | 0.283 |

**15m: Aggregated volume (Coinbase + Binance + KuCoin, base units), rolling relative volume (1 day); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 16622 | 6.6% (6.2%-7.0%) | -2.5% | 1.7% | | |
| Low volume (< 0.7x) | 6619 | 5.8% (5.2%-6.4%) | -2.5% | 1.6% | <0.001 | 0.011 |
| Normal (0.7x-1.5x) | 6538 | 6.8% (6.2%-7.5%) | -2.5% | 1.8% | 0.305 | 0.094 |
| High volume (> 1.5x) | 3465 | 7.6% (6.8%-8.6%) | -2.5% | 1.9% | 0.006 | 0.351 |

**15m: Aggregated volume (Coinbase + Binance + KuCoin, base units), rolling relative volume (7 days); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 16622 | 6.6% (6.2%-7.0%) | -2.5% | 1.7% | | |
| Low volume (< 0.7x) | 7294 | 5.2% (4.7%-5.7%) | -2.5% | 1.5% | <0.001 | 0.016 |
| Normal (0.7x-1.5x) | 5709 | 6.6% (6.0%-7.3%) | -2.5% | 1.8% | 0.817 | 0.314 |
| High volume (> 1.5x) | 3533 | 9.2% (8.3%-10.2%) | -2.5% | 2.1% | <0.001 | 0.157 |

(86 entries had no value for this measure: not enough history, or no data from that exchange.)

**15m: candidate filters on Aggregated volume (Coinbase + Binance + KuCoin, base units) (same-hour-of-day RV), fee coinbase_default_taker_1.20%**

| Rule | Entries kept | Hit rate after fees | Mean return after fees | Mean return change vs all (95% bootstrap CI) | p (kept vs dropped, hit) |
|---|---:|---:|---:|---|---:|
| No filter (base rate) | 16622 | 6.6% | -2.5% | | |
| Require above-average volume (> 1.0x) | 6192 | 8.8% | -2.4% | 0.1% (-0.0% to 0.1%) | <0.001 |
| Require high volume (> 1.5x) | 3529 | 10.5% | -2.4% | 0.1% (0.0% to 0.2%) | <0.001 |
| Block low volume (drop < 0.7x) | 9112 | 7.9% | -2.5% | 0.0% (-0.0% to 0.1%) | <0.001 |

**15m: quintiles of Aggregated volume (Coinbase + Binance + KuCoin, base units) same-hour-of-day RV, fee coinbase_default_taker_1.20%**

| Quintile of the measure | Range | n | Hit rate after fees | Mean return after fees |
|---|---|---:|---:|---:|
| Q1 | 0.05-0.42 | 3259 | 4.1% | -2.6% |
| Q2 | 0.42-0.64 | 3259 | 5.5% | -2.5% |
| Q3 | 0.64-0.96 | 3258 | 5.8% | -2.5% |
| Q4 | 0.96-1.57 | 3259 | 6.6% | -2.5% |
| Q5 | 1.57-39.24 | 3259 | 10.8% | -2.4% |

**STRAT-001 15m Aggregated volume (Coinbase + Binance + KuCoin, base units): other volume measures (subset vs the rest)**

| Condition at the signal bar | n with | Hit with | Mean with | n without | Hit without | Mean without | p (hit) | p (return) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OBV rising over 20 bars | 6829 | 6.0% | -2.5% | 9793 | 7.0% | -2.5% | 0.016 | 0.005 |
| Price/OBV bearish divergence (price up, OBV down) | 1435 | 5.3% | -2.5% | 15187 | 6.7% | -2.5% | 0.039 | 0.220 |
| Close above 1-day VWAP | 6431 | 5.4% | -2.5% | 10191 | 7.3% | -2.5% | <0.001 | 0.001 |
| Volume spike (>= 3x) in the last 5 bars | 2908 | 6.8% | -2.4% | 13714 | 6.5% | -2.5% | 0.621 | 0.034 |
| CMF-20 > 0 | 8750 | 6.0% | -2.5% | 7872 | 7.2% | -2.5% | 0.001 | 0.349 |

**15m: Binance volume alone, same-hour-of-day relative volume (20 days); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 16622 | 6.6% (6.2%-7.0%) | -2.5% | 1.7% | | |
| Low volume (< 0.7x) | 7387 | 5.0% (4.5%-5.5%) | -2.5% | 1.4% | <0.001 | 0.011 |
| Normal (0.7x-1.5x) | 5347 | 6.3% (5.6%-6.9%) | -2.5% | 1.7% | 0.328 | 0.783 |
| High volume (> 1.5x) | 3560 | 10.2% (9.3%-11.3%) | -2.4% | 2.3% | <0.001 | 0.008 |

(328 entries had no value for this measure: not enough history, or no data from that exchange.)

**15m: KuCoin volume alone, same-hour-of-day relative volume (20 days); fee level coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 16622 | 6.6% (6.2%-7.0%) | -2.5% | 1.7% | | |
| Low volume (< 0.7x) | 7511 | 5.1% (4.6%-5.6%) | -2.5% | 1.5% | <0.001 | 0.061 |
| Normal (0.7x-1.5x) | 5159 | 6.6% (6.0%-7.3%) | -2.5% | 1.7% | 0.759 | 0.672 |
| High volume (> 1.5x) | 3624 | 9.4% (8.5%-10.4%) | -2.5% | 2.2% | <0.001 | 0.151 |

(328 entries had no value for this measure: not enough history, or no data from that exchange.)

**15m: per coin, Coinbase same-hour-of-day RV, fee coinbase_default_taker_1.20%**

| Coin | All: n | All: hit | All: mean | Low (<0.7x): n / hit / mean | Normal: n / hit / mean | High (>1.5x): n / hit / mean |
|---|---:|---:|---:|---|---|---|
| ADA | 1734 | 8.8% | -2.5% | 865 / 7.5% / -2.5% | 474 / 8.0% / -2.5% | 359 / 13.9% / -2.3% |
| AVAX | 1761 | 9.1% | -2.5% | 902 / 7.6% / -2.6% | 461 / 8.5% / -2.5% | 367 / 12.3% / -2.5% |
| BNB | 590 | 2.4% | -2.5% | 320 / 2.5% / -2.5% | 122 / 0.8% / -2.4% | 120 / 2.5% / -2.6% |
| BTC | 1769 | 2.8% | -2.5% | 749 / 1.7% / -2.5% | 531 / 3.0% / -2.4% | 459 / 4.1% / -2.5% |
| DOGE | 1817 | 7.9% | -2.5% | 889 / 5.1% / -2.6% | 478 / 8.2% / -2.6% | 418 / 13.6% / -2.4% |
| ETH | 1836 | 5.4% | -2.5% | 780 / 3.3% / -2.5% | 604 / 5.8% / -2.5% | 426 / 8.7% / -2.3% |
| LINK | 1736 | 7.9% | -2.5% | 791 / 5.4% / -2.6% | 517 / 9.1% / -2.4% | 396 / 10.9% / -2.4% |
| LTC | 1757 | 5.7% | -2.5% | 793 / 4.3% / -2.6% | 601 / 6.3% / -2.4% | 325 / 8.3% / -2.5% |
| SOL | 1821 | 7.5% | -2.5% | 802 / 4.6% / -2.6% | 578 / 7.4% / -2.5% | 405 / 12.1% / -2.5% |
| XRP | 1801 | 5.6% | -2.5% | 820 / 3.7% / -2.5% | 565 / 5.1% / -2.5% | 377 / 10.9% / -2.4% |

**15m: robustness, cb rv_hod20 (per-coin sign test; week-cluster bootstrap), fee coinbase_default_taker_1.20%**

| Bucket | Coins with hit above the coin's base / coins | sign-test p | Coins with mean above / coins | sign-test p | Week-cluster bootstrap 95% CI, hit (bucket - rest) | same, mean return |
|---|---|---:|---|---:|---|---|
| Low volume (< 0.7x) | 1/10 | 0.021 | 0/10 | 0.002 | -4.5% to -2.3% | -0.2% to -0.0% |
| Normal (0.7x-1.5x) | 6/10 | 0.754 | 6/10 | 0.754 | -0.7% to 0.9% | -0.0% to 0.1% |
| High volume (> 1.5x) | 10/10 | 0.002 | 9/10 | 0.021 | 3.0% to 6.2% | -0.0% to 0.2% |

**15m: robustness, cb rv20 (per-coin sign test; week-cluster bootstrap), fee coinbase_default_taker_1.20%**

| Bucket | Coins with hit above the coin's base / coins | sign-test p | Coins with mean above / coins | sign-test p | Week-cluster bootstrap 95% CI, hit (bucket - rest) | same, mean return |
|---|---|---:|---|---:|---|---|
| Low volume (< 0.7x) | 9/10 | 0.021 | 2/10 | 0.109 | 0.1% to 2.0% | -0.1% to 0.1% |
| Normal (0.7x-1.5x) | 1/10 | 0.021 | 6/10 | 0.754 | -2.1% to -0.6% | -0.0% to 0.1% |
| High volume (> 1.5x) | 6/10 | 0.754 | 7/10 | 0.344 | -0.8% to 1.4% | -0.1% to 0.1% |

**15m: robustness, agg rv_hod20 (per-coin sign test; week-cluster bootstrap), fee coinbase_default_taker_1.20%**

| Bucket | Coins with hit above the coin's base / coins | sign-test p | Coins with mean above / coins | sign-test p | Week-cluster bootstrap 95% CI, hit (bucket - rest) | same, mean return |
|---|---|---:|---|---:|---|---|
| Low volume (< 0.7x) | 1/10 | 0.021 | 0/10 | 0.002 | -4.4% to -2.0% | -0.2% to 0.0% |
| Normal (0.7x-1.5x) | 5/10 | 1.000 | 2/10 | 0.109 | -1.3% to 0.6% | -0.1% to 0.1% |
| High volume (> 1.5x) | 9/10 | 0.021 | 9/10 | 0.021 | 3.4% to 6.7% | -0.0% to 0.2% |

**15m: robustness, agg rv20 (per-coin sign test; week-cluster bootstrap), fee coinbase_default_taker_1.20%**

| Bucket | Coins with hit above the coin's base / coins | sign-test p | Coins with mean above / coins | sign-test p | Week-cluster bootstrap 95% CI, hit (bucket - rest) | same, mean return |
|---|---|---:|---|---:|---|---|
| Low volume (< 0.7x) | 10/10 | 0.002 | 4/10 | 0.754 | 0.3% to 2.5% | -0.1% to 0.1% |
| Normal (0.7x-1.5x) | 1/10 | 0.021 | 3/10 | 0.344 | -2.6% to -0.8% | -0.1% to 0.0% |
| High volume (> 1.5x) | 7/10 | 0.344 | 7/10 | 0.344 | -0.8% to 1.7% | -0.1% to 0.1% |

**15m: default-list coins only (BTC, ETH, XRP, BNB, DOGE), Coinbase same-hour-of-day RV, fee coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 7813 | 5.2% (4.7%-5.7%) | -2.5% | 1.5% | | |
| Low volume (< 0.7x) | 3558 | 3.4% (2.9%-4.1%) | -2.5% | 1.2% | <0.001 | 0.021 |
| Normal (0.7x-1.5x) | 2300 | 5.2% (4.4%-6.2%) | -2.5% | 1.5% | 1.000 | 0.686 |
| High volume (> 1.5x) | 1800 | 8.7% (7.5%-10.1%) | -2.4% | 2.1% | <0.001 | 0.015 |

(155 entries had no value for this measure: not enough history, or no data from that exchange.)

**15m: first half of the entries (split at 2025-05-15 04:45:00+00:00), Coinbase same-hour-of-day RV, fee coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 8311 | 7.7% (7.2%-8.3%) | -2.5% | 2.0% | | |
| Low volume (< 0.7x) | 3790 | 5.2% (4.5%-6.0%) | -2.6% | 1.5% | <0.001 | <0.001 |
| Normal (0.7x-1.5x) | 2411 | 8.0% (7.0%-9.2%) | -2.4% | 2.0% | 0.494 | 0.152 |
| High volume (> 1.5x) | 1810 | 12.6% (11.1%-14.2%) | -2.3% | 2.6% | <0.001 | 0.007 |

(300 entries had no value for this measure: not enough history, or no data from that exchange.)

**15m: second half of the entries (split at 2025-05-15 04:45:00+00:00), Coinbase same-hour-of-day RV, fee coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 8311 | 5.4% (4.9%-5.9%) | -2.5% | 1.5% | | |
| Low volume (< 0.7x) | 3921 | 4.4% (3.8%-5.1%) | -2.5% | 1.3% | <0.001 | 0.774 |
| Normal (0.7x-1.5x) | 2520 | 5.2% (4.4%-6.1%) | -2.5% | 1.4% | 0.634 | 0.651 |
| High volume (> 1.5x) | 1842 | 7.8% (6.6%-9.1%) | -2.5% | 1.8% | <0.001 | 0.481 |

(28 entries had no value for this measure: not enough history, or no data from that exchange.)

### Neural trade-start entries (held-out 20%), legacy trade rules replayed

| Coin | Held-out hours | Signal hours, base model | Signal hours, volume model | Trades, base | Trades, volume |
|---|---:|---:|---:|---:|---:|
| ADA | 5251 | 295 | 263 | 12 | 10 |
| AVAX | 5251 | 266 | 236 | 12 | 15 |
| BNB | 5251 | 119 | 37 | 11 | 11 |
| BTC | 5251 | 156 | 96 | 8 | 7 |
| DOGE | 5251 | 266 | 189 | 6 | 5 |
| ETH | 5251 | 226 | 154 | 14 | 14 |
| LINK | 5251 | 237 | 166 | 15 | 16 |
| LTC | 5251 | 209 | 156 | 10 | 12 |
| SOL | 5251 | 155 | 110 | 13 | 13 |
| XRP | 5251 | 199 | 153 | 15 | 16 |

**Model experiment: trades from each model's signals, after fees**

| Model | Fee level | Trades | Hit rate (95% CI) | Mean return per trade | Median | Trades with a DCA | Open at the end |
|---|---|---:|---|---:|---:|---:|---:|
| base | coinbase_default_taker_1.20% | 116 | 90.5% (83.8%-94.6%) | 0.7% | 1.5% | 97 | 10 |
| base | sens_taker_0.60% | 129 | 91.5% (85.4%-95.2%) | 1.6% | 1.8% | 98 | 10 |
| base | sens_taker_0.40% | 133 | 93.2% (87.6%-96.4%) | 1.8% | 2.0% | 96 | 9 |
| base | sens_0.10%_backtester_default | 158 | 94.3% (89.5%-97.0%) | 2.7% | 2.7% | 107 | 9 |
| base | gross_0% | 159 | 94.3% (89.6%-97.0%) | 2.8% | 2.9% | 104 | 9 |
| vol | coinbase_default_taker_1.20% | 119 | 91.6% (85.2%-95.4%) | 0.8% | 1.4% | 101 | 10 |
| vol | sens_taker_0.60% | 129 | 91.5% (85.4%-95.2%) | 1.8% | 2.0% | 99 | 10 |
| vol | sens_taker_0.40% | 129 | 92.2% (86.3%-95.7%) | 2.0% | 2.1% | 97 | 10 |
| vol | sens_0.10%_backtester_default | 170 | 95.9% (91.7%-98.0%) | 2.9% | 2.6% | 116 | 8 |
| vol | gross_0% | 174 | 96.0% (91.9%-98.0%) | 3.0% | 2.9% | 115 | 7 |

Volume model vs base model at coinbase_default_taker_1.20%: p (hit) = 0.822, p (mean return) = 0.960.

**Direction hit rate on held-out bars, per timeframe (pooled over coins): model vs the 'always up' base rate**

| Timeframe | Base model: n | hit | up share | Volume model: n | hit | up share |
|---|---:|---:|---:|---:|---:|---:|
| 1hour | 51617 | 50.0% | 50.3% | 51514 | 50.6% | 50.3% |
| 2hour | 25933 | 49.4% | 50.0% | 25870 | 50.0% | 50.0% |
| 4hour | 12982 | 50.5% | 49.6% | 12907 | 50.0% | 49.6% |
| 8hour | 6492 | 50.4% | 50.3% | 6286 | 50.7% | 50.1% |
| 12hour | 4328 | 49.3% | 50.7% | 4078 | 50.0% | 50.7% |
| 1day | 2125 | 49.1% | 50.1% | 1900 | 51.3% | 49.6% |
| 1week | 168 | 50.6% | 47.6% | 21 | 66.7% | 52.4% |

**Neural trade-start entries (base model), Coinbase same-hour-of-day RV, fee coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 116 | 90.5% (83.8%-94.6%) | 0.7% | 6.1% | | |
| Low volume (< 0.7x) | 8 | 87.5% (52.9%-97.8%) | 0.8% | 5.0% | 0.561 | 0.949 |
| Normal (0.7x-1.5x) | 27 | 81.5% (63.3%-91.8%) | -2.2% | 9.1% | 0.125 | 0.045 |
| High volume (> 1.5x) | 81 | 93.8% (86.4%-97.3%) | 1.7% | 4.5% | 0.085 | 0.040 |

**Neural trade-start entries (base model), aggregated same-hour-of-day RV, fee coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 116 | 90.5% (83.8%-94.6%) | 0.7% | 6.1% | | |
| Low volume (< 0.7x) | 4 | 75.0% (30.1%-95.4%) | -1.4% | 6.7% | 0.332 | 0.560 |
| Normal (0.7x-1.5x) | 28 | 82.1% (64.4%-92.1%) | -1.5% | 9.2% | 0.131 | 0.107 |
| High volume (> 1.5x) | 84 | 94.0% (86.8%-97.4%) | 1.6% | 4.3% | 0.069 | 0.065 |

**Neural trade-start entries (base model), Coinbase rolling 20-bar RV, fee coinbase_default_taker_1.20%**

| Subset | n | Hit rate after fees (95% CI) | Mean return after fees | Std of return | p (hit vs rest) | p (return vs rest) |
|---|---:|---|---:|---:|---:|---:|
| All entries (base rate) | 116 | 90.5% (83.8%-94.6%) | 0.7% | 6.1% | | |
| Low volume (< 0.7x) | 9 | 100.0% (70.1%-100.0%) | 2.0% | 1.8% | 0.598 | 0.110 |
| Normal (0.7x-1.5x) | 31 | 83.9% (67.4%-92.9%) | -1.3% | 9.6% | 0.160 | 0.126 |
| High volume (> 1.5x) | 76 | 92.1% (83.8%-96.3%) | 1.4% | 4.1% | 0.509 | 0.177 |

**Neural trade-start (base model), Coinbase volume: other volume measures (subset vs the rest)**

| Condition at the signal bar | n with | Hit with | Mean with | n without | Hit without | Mean without | p (hit) | p (return) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| OBV rising over 20 bars | 33 | 90.9% | 0.8% | 83 | 90.4% | 0.7% | 1.000 | 0.905 |
| Price/OBV bearish divergence (price up, OBV down) | 7 | 85.7% | -2.5% | 109 | 90.8% | 0.9% | 0.512 | 0.505 |
| Close above 1-day VWAP | 6 | 100.0% | 1.3% | 110 | 90.0% | 0.7% | 1.000 | 0.374 |
| Volume spike (>= 3x) in the last 5 bars | 43 | 95.3% | 2.2% | 73 | 87.7% | -0.2% | 0.208 | 0.013 |
| CMF-20 > 0 | 33 | 93.9% | 1.2% | 83 | 89.2% | 0.6% | 0.726 | 0.619 |

### Multiple comparisons

296 subset tests were run; 138 had p < 0.05 (about 15 expected by chance alone if no effect exists); 50 pass a Bonferroni threshold of p < 0.00017.

Tests with p < 0.05:

- STRAT-001 15m agg rv_hod20 coinbase_default_taker_1.20% High volume (> 1.5x): p = <0.001
- STRAT-001 15m agg rule Require high volume (> 1.5x): p = <0.001
- STRAT-001 15m bi rv_hod20 coinbase_default_taker_1.20% High volume (> 1.5x): p = <0.001
- STRAT-001 15m cb rv_hod20 coinbase_default_taker_1.20% High volume (> 1.5x): p = <0.001
- STRAT-001 15m cb rule Require high volume (> 1.5x): p = <0.001
- STRAT-001 15m cb rule Require above-average volume (> 1.0x): p = <0.001
- STRAT-001 15m agg rule Require above-average volume (> 1.0x): p = <0.001
- STRAT-001 15m cb rv_hod20 coinbase_default_taker_1.20% Low volume (< 0.7x): p = <0.001
- STRAT-001 15m cb rule Block low volume (drop < 0.7x): p = <0.001
- STRAT-001 15m first half High volume (> 1.5x): p = <0.001
- STRAT-001 15m agg rv_hod20 coinbase_default_taker_1.20% Low volume (< 0.7x): p = <0.001
- STRAT-001 15m agg rule Block low volume (drop < 0.7x): p = <0.001
- STRAT-001 15m first half Low volume (< 0.7x): p = <0.001
- STRAT-001 15m ku rv_hod20 coinbase_default_taker_1.20% High volume (> 1.5x): p = <0.001
- STRAT-001 15m bi rv_hod20 coinbase_default_taker_1.20% Low volume (< 0.7x): p = <0.001
- STRAT-001 15m default5 High volume (> 1.5x): p = <0.001
- STRAT-001 15m cb rv7d coinbase_default_taker_1.20% High volume (> 1.5x): p = <0.001
- STRAT-001 15m agg rv7d coinbase_default_taker_1.20% High volume (> 1.5x): p = <0.001
- STRAT-001 15m ku rv_hod20 coinbase_default_taker_1.20% Low volume (< 0.7x): p = <0.001
- STRAT-001 15m default5 Low volume (< 0.7x): p = <0.001
- STRAT-001 15m cb rv7d coinbase_default_taker_1.20% Low volume (< 0.7x): p = <0.001
- STRAT-001 15m agg rv7d coinbase_default_taker_1.20% Low volume (< 0.7x): p = <0.001
- STRAT-001 15m cb rv_hod20 gross_0% Low volume (< 0.7x): p = <0.001
- STRAT-001 1h cb rv_hod20 coinbase_default_taker_1.20% High volume (> 1.5x): p = <0.001
- STRAT-001 1h cb rule Require high volume (> 1.5x): p = <0.001
- STRAT-001 15m Coinbase volume alone Close above 1-day VWAP: p = <0.001
- STRAT-001 15m Aggregated volume (Coinbase + Binance + KuCoin, base units) Close above 1-day VWAP: p = <0.001
- STRAT-001 15m second half High volume (> 1.5x): p = <0.001
- STRAT-001 1h first half Low volume (< 0.7x) (return): p = <0.001
- STRAT-001 1h agg rule Require above-average volume (> 1.0x): p = <0.001
- STRAT-001 1h first half High volume (> 1.5x): p = <0.001
- STRAT-001 1h first half Low volume (< 0.7x): p = <0.001
- STRAT-001 15m cb rv_hod20 gross_0% High volume (> 1.5x): p = <0.001
- STRAT-001 15m agg rv20 coinbase_default_taker_1.20% Normal (0.7x-1.5x): p = <0.001
- STRAT-001 1h bi rv_hod20 coinbase_default_taker_1.20% Low volume (< 0.7x): p = <0.001
- STRAT-001 15m first half Low volume (< 0.7x) (return): p = <0.001
- STRAT-001 1h agg rv_hod20 coinbase_default_taker_1.20% High volume (> 1.5x): p = <0.001
- STRAT-001 1h agg rule Require high volume (> 1.5x): p = <0.001
- STRAT-001 1h agg rv7d coinbase_default_taker_1.20% High volume (> 1.5x): p = <0.001
- STRAT-001 1h default5 High volume (> 1.5x): p = <0.001
- STRAT-001 1h cb rv7d coinbase_default_taker_1.20% High volume (> 1.5x): p = <0.001
- STRAT-001 1h ku rv_hod20 coinbase_default_taker_1.20% Low volume (< 0.7x): p = <0.001
- STRAT-001 1h agg rv_hod20 coinbase_default_taker_1.20% Low volume (< 0.7x): p = <0.001
- STRAT-001 1h agg rule Block low volume (drop < 0.7x): p = <0.001
- STRAT-001 1h cb rv_hod20 gross_0% High volume (> 1.5x): p = <0.001
- STRAT-001 1h first half High volume (> 1.5x) (return): p = <0.001
- STRAT-001 1h cb rv_hod20 coinbase_default_taker_1.20% High volume (> 1.5x) (return): p = <0.001
- STRAT-001 1h cb rv_hod20 gross_0% High volume (> 1.5x) (return): p = <0.001
- STRAT-001 1h agg rv_hod20 coinbase_default_taker_1.20% Low volume (< 0.7x) (return): p = <0.001
- STRAT-001 1h Coinbase volume alone OBV rising over 20 bars: p = <0.001
- STRAT-001 15m second half Low volume (< 0.7x): p = <0.001
- STRAT-001 1h cb rv_hod20 gross_0% Low volume (< 0.7x) (return): p = <0.001
- STRAT-001 1h cb rv_hod20 coinbase_default_taker_1.20% Low volume (< 0.7x) (return): p = <0.001
- STRAT-001 1h bi rv_hod20 coinbase_default_taker_1.20% Low volume (< 0.7x) (return): p = <0.001
- STRAT-001 1h bi rv_hod20 coinbase_default_taker_1.20% High volume (> 1.5x): p = <0.001
- STRAT-001 15m agg rv20 coinbase_default_taker_1.20% Low volume (< 0.7x): p = <0.001
- STRAT-001 1h cb rv_hod20 coinbase_default_taker_1.20% Low volume (< 0.7x): p = <0.001
- STRAT-001 1h cb rule Block low volume (drop < 0.7x): p = <0.001
- STRAT-001 15m cb rv_hod20 coinbase_default_taker_1.20% Low volume (< 0.7x) (return): p = <0.001
- STRAT-001 15m cb rv_hod20 gross_0% Low volume (< 0.7x) (return): p = <0.001
- STRAT-001 1h cb rule Require above-average volume (> 1.0x): p = <0.001
- STRAT-001 15m cb rv20 coinbase_default_taker_1.20% Normal (0.7x-1.5x): p = <0.001
- STRAT-001 1h ku rv_hod20 coinbase_default_taker_1.20% Low volume (< 0.7x) (return): p = <0.001
- STRAT-001 1h cb rv7d coinbase_default_taker_1.20% High volume (> 1.5x) (return): p = <0.001
- STRAT-001 15m agg rv1d coinbase_default_taker_1.20% Low volume (< 0.7x): p = <0.001
- STRAT-001 1h Aggregated volume (Coinbase + Binance + KuCoin, base units) OBV rising over 20 bars: p = 0.001
- STRAT-001 15m Aggregated volume (Coinbase + Binance + KuCoin, base units) Close above 1-day VWAP (return): p = 0.001
- STRAT-001 15m Aggregated volume (Coinbase + Binance + KuCoin, base units) CMF-20 > 0: p = 0.001
- STRAT-001 1h default5 Low volume (< 0.7x): p = 0.001
- STRAT-001 1h cb rv_hod20 Low volume (< 0.7x) sign test mean: p = 0.002
- STRAT-001 1h agg rv_hod20 High volume (> 1.5x) sign test hit: p = 0.002
- STRAT-001 15m cb rv_hod20 Low volume (< 0.7x) sign test mean: p = 0.002
- STRAT-001 15m cb rv_hod20 High volume (> 1.5x) sign test hit: p = 0.002
- STRAT-001 15m agg rv_hod20 Low volume (< 0.7x) sign test mean: p = 0.002
- STRAT-001 15m agg rv20 Low volume (< 0.7x) sign test hit: p = 0.002
- STRAT-001 15m Coinbase volume alone Close above 1-day VWAP (return): p = 0.002
- STRAT-001 15m Coinbase volume alone CMF-20 > 0: p = 0.002
- STRAT-001 1h agg rv7d coinbase_default_taker_1.20% High volume (> 1.5x) (return): p = 0.002
- STRAT-001 15m cb rv1d coinbase_default_taker_1.20% Low volume (< 0.7x): p = 0.004
- STRAT-001 1h second half High volume (> 1.5x): p = 0.004
- STRAT-001 1h ku rv_hod20 coinbase_default_taker_1.20% High volume (> 1.5x): p = 0.005
- STRAT-001 15m Aggregated volume (Coinbase + Binance + KuCoin, base units) OBV rising over 20 bars (return): p = 0.005
- STRAT-001 15m agg rv_hod20 coinbase_default_taker_1.20% High volume (> 1.5x) (return): p = 0.005
- STRAT-001 1h cb rv20 coinbase_default_taker_1.20% Low volume (< 0.7x) (return): p = 0.006
- STRAT-001 15m agg rv1d coinbase_default_taker_1.20% High volume (> 1.5x): p = 0.006
- STRAT-001 15m cb rv20 coinbase_default_taker_1.20% Low volume (< 0.7x): p = 0.006
- STRAT-001 15m agg rv_hod20 coinbase_default_taker_1.20% Low volume (< 0.7x) (return): p = 0.006
- STRAT-001 1h cb rv7d coinbase_default_taker_1.20% Low volume (< 0.7x): p = 0.007
- STRAT-001 15m first half High volume (> 1.5x) (return): p = 0.007
- STRAT-001 15m bi rv_hod20 coinbase_default_taker_1.20% High volume (> 1.5x) (return): p = 0.008
- STRAT-001 15m Coinbase volume alone OBV rising over 20 bars: p = 0.008
- STRAT-001 15m cb rv1d coinbase_default_taker_1.20% High volume (> 1.5x): p = 0.009
- STRAT-001 1h cb rv7d coinbase_default_taker_1.20% Low volume (< 0.7x) (return): p = 0.009
- STRAT-001 15m cb rv_hod20 coinbase_default_taker_1.20% High volume (> 1.5x) (return): p = 0.009
- STRAT-001 15m cb rv_hod20 gross_0% High volume (> 1.5x) (return): p = 0.009
- STRAT-001 1h default5 Low volume (< 0.7x) (return): p = 0.009
- STRAT-001 1h cb rv_hod20 gross_0% Low volume (< 0.7x): p = 0.009
- STRAT-001 1h agg rv1d coinbase_default_taker_1.20% Normal (0.7x-1.5x): p = 0.009
- STRAT-001 1h Coinbase volume alone Close above 1-day VWAP: p = 0.010
- STRAT-001 15m agg rv1d coinbase_default_taker_1.20% Low volume (< 0.7x) (return): p = 0.011
- STRAT-001 15m bi rv_hod20 coinbase_default_taker_1.20% Low volume (< 0.7x) (return): p = 0.011
- STRAT-001 15m Coinbase volume alone Price/OBV bearish divergence (price up, OBV down): p = 0.011
- Neural trade-start (base model), Coinbase volume Volume spike (>= 3x) in the last 5 bars (return): p = 0.013
- STRAT-001 1h default5 High volume (> 1.5x) (return): p = 0.015
- STRAT-001 15m default5 High volume (> 1.5x) (return): p = 0.015
- STRAT-001 15m Aggregated volume (Coinbase + Binance + KuCoin, base units) OBV rising over 20 bars: p = 0.016
- STRAT-001 15m agg rv7d coinbase_default_taker_1.20% Low volume (< 0.7x) (return): p = 0.016
- STRAT-001 15m cb rv7d coinbase_default_taker_1.20% Low volume (< 0.7x) (return): p = 0.017
- STRAT-001 1h cb rv1d coinbase_default_taker_1.20% Low volume (< 0.7x) (return): p = 0.019
- STRAT-001 1h agg rv_hod20 coinbase_default_taker_1.20% High volume (> 1.5x) (return): p = 0.020
- STRAT-001 1h agg rv20 coinbase_default_taker_1.20% Normal (0.7x-1.5x): p = 0.021
- STRAT-001 15m default5 Low volume (< 0.7x) (return): p = 0.021
- STRAT-001 1h cb rv_hod20 Low volume (< 0.7x) sign test hit: p = 0.021
- STRAT-001 1h cb rv_hod20 High volume (> 1.5x) sign test hit: p = 0.021
- STRAT-001 1h cb rv_hod20 High volume (> 1.5x) sign test mean: p = 0.021
- STRAT-001 1h agg rv_hod20 Low volume (< 0.7x) sign test hit: p = 0.021
- STRAT-001 1h agg rv_hod20 Low volume (< 0.7x) sign test mean: p = 0.021
- STRAT-001 1h agg rv_hod20 High volume (> 1.5x) sign test mean: p = 0.021
- STRAT-001 15m cb rv_hod20 Low volume (< 0.7x) sign test hit: p = 0.021
- STRAT-001 15m cb rv_hod20 High volume (> 1.5x) sign test mean: p = 0.021
- STRAT-001 15m cb rv20 Low volume (< 0.7x) sign test hit: p = 0.021
- STRAT-001 15m cb rv20 Normal (0.7x-1.5x) sign test hit: p = 0.021
- STRAT-001 15m agg rv_hod20 Low volume (< 0.7x) sign test hit: p = 0.021
- STRAT-001 15m agg rv_hod20 High volume (> 1.5x) sign test hit: p = 0.021
- STRAT-001 15m agg rv_hod20 High volume (> 1.5x) sign test mean: p = 0.021
- STRAT-001 15m agg rv20 Normal (0.7x-1.5x) sign test hit: p = 0.021
- STRAT-001 1h Coinbase volume alone Volume spike (>= 3x) in the last 5 bars (return): p = 0.026
- STRAT-001 15m Coinbase volume alone OBV rising over 20 bars (return): p = 0.026
- STRAT-001 1h Aggregated volume (Coinbase + Binance + KuCoin, base units) Close above 1-day VWAP: p = 0.030
- STRAT-001 1h ku rv_hod20 coinbase_default_taker_1.20% Normal (0.7x-1.5x) (return): p = 0.031
- STRAT-001 1h agg rv7d coinbase_default_taker_1.20% Low volume (< 0.7x): p = 0.033
- STRAT-001 15m Aggregated volume (Coinbase + Binance + KuCoin, base units) Volume spike (>= 3x) in the last 5 bars (return): p = 0.034
- STRAT-001 1h agg rv7d coinbase_default_taker_1.20% Low volume (< 0.7x) (return): p = 0.038
- STRAT-001 15m Aggregated volume (Coinbase + Binance + KuCoin, base units) Price/OBV bearish divergence (price up, OBV down): p = 0.039
- neural cb High volume (> 1.5x) (return): p = 0.040
- STRAT-001 1h Aggregated volume (Coinbase + Binance + KuCoin, base units) Close above 1-day VWAP (return): p = 0.045
- neural cb Normal (0.7x-1.5x) (return): p = 0.045
- STRAT-001 15m Coinbase volume alone Volume spike (>= 3x) in the last 5 bars (return): p = 0.047

### Volatility control (`vol_control.py`)


#### STRAT-001 1h: n = 4277; Spearman(rv_hod20, vol20) = 0.31

| Volatility tercile (within coin) | RV | n | Hit after fees | Mean after fees | Gross hit | Gross mean | Mean abs gross move |
|---|---|---:|---:|---:|---:|---:|---:|
| low vol | high (>1.5x) | 166 | 15.1% | -2.14% | 35.5% | 0.25% | 1.93% |
| low vol | rest | 1275 | 12.6% | -2.38% | 34.2% | 0.01% | 1.74% |
| mid vol | high (>1.5x) | 264 | 17.0% | -2.16% | 37.5% | 0.23% | 2.30% |
| mid vol | rest | 1159 | 11.8% | -2.69% | 32.3% | -0.31% | 2.24% |
| high vol | high (>1.5x) | 520 | 25.2% | -2.06% | 45.0% | 0.34% | 3.18% |
| high vol | rest | 893 | 18.3% | -2.92% | 37.4% | -0.55% | 3.20% |

Within each volatility tercile, high RV minus the rest:

- low vol: hit after fees +2.4% (Fisher p = 0.389); gross mean return +0.24% (Welch p = 0.355)
- mid vol: hit after fees +5.2% (Fisher p = 0.025); gross mean return +0.54% (Welch p = 0.023)
- high vol: hit after fees +6.9% (Fisher p = 0.002); gross mean return +0.88% (Welch p = 0.000)

#### STRAT-001 15m: n = 16294; Spearman(rv_hod20, vol20) = 0.35

| Volatility tercile (within coin) | RV | n | Hit after fees | Mean after fees | Gross hit | Gross mean | Mean abs gross move |
|---|---|---:|---:|---:|---:|---:|---:|
| low vol | high (>1.5x) | 583 | 3.1% | -2.57% | 26.8% | -0.19% | 0.78% |
| low vol | rest | 4903 | 3.4% | -2.52% | 28.6% | -0.14% | 0.77% |
| mid vol | high (>1.5x) | 1066 | 5.9% | -2.47% | 32.6% | -0.08% | 1.07% |
| mid vol | rest | 4378 | 5.2% | -2.54% | 33.0% | -0.16% | 1.04% |
| high vol | high (>1.5x) | 2003 | 14.5% | -2.35% | 41.5% | 0.03% | 1.93% |
| high vol | rest | 3361 | 9.0% | -2.51% | 38.1% | -0.12% | 1.51% |

Within each volatility tercile, high RV minus the rest:

- low vol: hit after fees -0.3% (Fisher p = 0.808); gross mean return -0.05% (Welch p = 0.354)
- mid vol: hit after fees +0.7% (Fisher p = 0.323); gross mean return +0.08% (Welch p = 0.177)
- high vol: hit after fees +5.5% (Fisher p = 0.000); gross mean return +0.16% (Welch p = 0.030)

### Neural replay against model-free baselines (`replay_neural.py` output, summarised)

```text
== coinbase_default_taker_1.20%
model base: trades 116 hit 90.5% mean +0.73% median +1.51% open_at_end 10 dca_share 84% max_dd_median -3.1% worst_dd -45.7% mean_age_h 390 committed_mean 4.77
model vol: trades 119 hit 91.6% mean +0.77% median +1.38% open_at_end 10 dca_share 85% max_dd_median -3.4% worst_dd -47.1% mean_age_h 376 committed_mean 4.98
every-hour baseline: trades 142 hit 90.8% mean +0.38% open_at_end 10 dca_share 90%
random baseline (100 draws, same signal count per coin): trades per draw median 130; hit median 90.9% (5-95%: 89.2%-92.4%); mean median +0.65% (5-95%: +0.38%..+0.86%)
   base: share of random draws with hit >= model: 0.67; with mean >= model: 0.22
   vol: share of random draws with hit >= model: 0.24; with mean >= model: 0.16
== gross_0%
model base: trades 159 hit 94.3% mean +2.84% median +2.89% open_at_end 9 dca_share 65% max_dd_median -2.2% worst_dd -44.3% mean_age_h 268 committed_mean 3.82
model vol: trades 174 hit 96.0% mean +3.02% median +2.91% open_at_end 7 dca_share 66% max_dd_median -2.3% worst_dd -44.3% mean_age_h 241 committed_mean 3.93
every-hour baseline: trades 201 hit 94.5% mean +2.76% open_at_end 10 dca_share 73%
random baseline (100 draws, same signal count per coin): trades per draw median 172; hit median 94.4% (5-95%: 93.4%-95.3%); mean median +2.86% (5-95%: +2.63%..+3.04%)
   base: share of random draws with hit >= model: 0.53; with mean >= model: 0.57
   vol: share of random draws with hit >= model: 0.01; with mean >= model: 0.08
```
