# FDS-SR-001 — Strategy Research, Catalogue Expansion and Strategy–Model Evaluation

**Issue:** none yet. Raise "Strategy research: a small, evidence-backed catalogue, tested with and without models" and link it here.
**Target repo:** `sjackson0109/powertraderai`.
**Branch:** this spec is on `docs/fds-sr-001-strategy-research`, cut from `main` at `cdae9c9`. Each milestone (§8) is built on its own branch, cut from `main` after the previous one is merged.
**Status:** draft for the owner's approval, 2026-11-07. Documentation only: nothing here is built, registered, enabled or activated.
**Authority** (owner, 2026-11-07):
- **Authorised:** research, repository inspection, this specification and its plan, as one documentation-only draft PR.
- **Not authorised:**
  - merging;
  - registering experiments;
  - activating strategies;
  - changing live trading;
  - deploying new execution behaviour.

**Identifier.** The repository uses two schemes:
- issue numbers (FDS-087 to FDS-129, from the strategy batch of 2026-10; their files were never committed);
- area tags with a sequence (FDS-MH-001, FDS-SIG-001 to -004, FDS-MX-001, FDS-LIVE-001, FDS-CHART-001).

There is no issue for this work, so it takes an area tag. "SR" (strategy research) is used rather than "STRAT", which would read as the strategy ID STRAT-001.

**Companion documents** (this PR):
- `docs/dev/strategy-research/A-research-report.md`: the literature, family by family (deliverable A).
- `docs/dev/strategy-research/B-architecture-assessment.md`: what the code does today (deliverable B).
- `docs/dev/strategy-research/E-decision-record.md`: the first candidates, the evidence they need, the risks and the owner's decisions (deliverable E).
- The implementation roadmap (deliverable D) is §8 of this spec.

**Related:**
- FDS-121/122/123/129: the strategy runtime, catalogue, STRAT-001, STRAT-002 and the overlays. Built; recorded in `docs/dev/RUN-LOG-strategy-batch-1.md`.
- FDS-MDL: STRAT-003.
- FDS-MH-001 with amendment 1: the model lab.
- FDS-SIG-004: signal fusion and its evaluation.
- FDS-MX-001: market data through the exchange layer.
- FDS-LIVE-001: live trading.

> **Read this first.**
> - **This spec asks which strategies are worth testing, and how to test them so that the answer means something.** It does not assume that better predictions make a strategy better (owner, 2026-11-07).
> - **Costs come first.** At 0.50% taker plus 0.05% slippage, a round trip costs 1.10%. Every published crypto rule was tested at lower costs (A §2). The candidates therefore decide on daily bars and hold for weeks.
> - **Expect few trades.** A daily strategy makes a few trades per coin a year: perhaps 150 to 300 over 4.3 years of development on 11 coins. Many results will read "too few trades to tell". That is a correct answer, not a failure.
> - **Volume has been tested already.** FDS-SIG-004's development run found no improvement from volume for STRAT-001 (`docs/dev/SIG4-REPORT-dev.md`). This spec reuses its tools; it does not reopen its decisions.

---

## 1. Objective

Establish a small, diverse, evidence-backed strategy catalogue. Then determine which combinations of strategy, model, market conditions and risk controls give demonstrably better decisions after costs. Each finding states which of three things it shows:
- **better predictions:** a forecast scores better;
- **better trading outcomes:** a strategy or filter beats its matched baseline;
- **economic viability:** a profit after fees, slippage and the account's constraints.

The spec:
- recommends four to six candidate strategies, and the first two or three to build (§5.4, §5.5);
- extends the catalogue with a lifecycle, so that being in the catalogue, enabled for research, eligible for paper and selected for trading are four different things (§5.2, §5.3);
- designs the strategy administration in Settings (§5.8);
- defines how models are evaluated against several strategies, one factor at a time (§5.9, §6);
- defines the portfolio simulation at £50, £500 and £10,000 from one data load (§5.10);
- defines paper-trading observation and the evidence it records (§5.11);
- sets out the milestones (§8) and the owner's decisions (§10, and E).

## 2. Rules

**Inherited.** These are unchanged, and every milestone keeps them:
- **Multiple exchanges, primary preferred** (owner, 2026-10-25). Candles, quotes, fees and minimums come only through the exchange layer, primary first. No strategy or evaluation code names an exchange.
- **Every option in Settings** (owner, 2026-10-28). Nothing needs a terminal or a hand-edited file.
- **UI text states facts only:** no spec names, test names or design caveats on screen.
- **Closed candles only.** A decision at bar t uses bars that closed at or before t. Fills are at the next bar's open, as today (`strategies/runner.py:16`).
- **Deterministic strategies.** No I/O, randomness or clock inside `on_bar` (`strategies/base.py:9`).
- **Declared before it runs.** An experiment's strategy, model, parameters, data, fees, baselines, tests and family are frozen before any of its results exist. Every scored configuration is a trial.
- **Existing behaviour is preserved:**
  - STRAT-000 to STRAT-003, the overlays, their identifiers and parameters, and the legacy neural engine with its DCA behave exactly as today.
  - FDS-MH-001's batches and trials, and FDS-SIG-004's results and provenance, are not changed.
- **New functionality is off by default.** New strategies start research-only and are not enabled for research.
- **The owner holds activation:**
  - raising a strategy's authorisation is a reviewed code change made on the owner's recorded decision;
  - no milestone raises one;
  - live trading is never changed by this spec.

**New in this spec:**
- **A strategy is not a model, and DCA is not a strategy.**
  - A strategy decides entries and exits.
  - A model estimates an outcome, and can only filter or size a strategy's entries here.
  - An execution policy, such as the legacy DCA ladder or periodic accumulation, decides how a position is bought.
  - A baseline is a reference, never traded.
  - The four are recorded separately in every experiment (§5.1).
- **One factor at a time.** A tested contrast changes either the strategy or the model, never both. A comparison that changes both is shown, and is labelled so.
- **No duplicates.** A new strategy must differ from every catalogue strategy in its entry rule, its exit rule or its decision horizon, and state how (§5.4).
- **Reserved months stay unread.** FDS-MH-001's lockbox (from 2025-05-06) and every month after it are read only by a declared evaluation's final check, within FDS-MH-001's opening limits (§6.1). Research backtests in Settings use the development period only.

## 3. Today

B is the full account. The points that shape this design:

1. **The strategies are all trend crossovers or trailing rules:**
   - STRAT-000: EMA 20/50, 1h.
   - STRAT-001: TEMA 12/48 with ADX ≥ 20, 1h. This is the default.
   - STRAT-002: Supertrend ATR 10 × 3, 4h.
   - STRAT-003: the pattern model, which cannot be selected.

   There is no breakout, momentum-ranking, mean-reversion or regime strategy (B §3.4).
2. **One strategy trades every coin.** The trader holds one runner, one timeframe and one overlay set (`signal_engine.py:81, 125`). Positions are keyed by coin, with no owning strategy (B §4.6).
3. **The backtester** runs one coin with no minimum, budget or halt (`backtest/engine.py`). **The portfolio replay** has all three and any account size, but takes only STRAT-001's 1h opportunities (`signal_fusion/labels.py:35`; B §5.3).
4. **The model lab** scores models only under the legacy exits (`model_lab/replay.py:60`). No other strategy's exits can be used (B §5.2).
5. **An overlay's entry gate cannot see candles** (`strategies/runner.py:129`), so a market-regime gate cannot be an overlay yet.
6. **No GUI runs the real backtester.** The hub's "Backtesting Framework" tab runs a separate engine with "MA Cross" and "RSI Strategy" on file or synthetic data (`backtesting_gui.py:220-228, 666-690`).
7. **A halt stops the trader**, exits included, until the owner resumes (`pt_trader.py:3096-3115`; FDS-SIG-004 §3.7 item 3).
8. **Paper fills at the top of the book** with the pricing exchange's fee, and no size slippage (`trading_mode.py:464-506, 717-741`).

## 4. The evidence

A is the full account. In short:
- **The trend family.** Time-series momentum, moving averages and breakouts have the strongest general evidence.
  - In crypto, the positive results are mostly before costs or at 0.10–0.50%, and out-of-sample tests are mixed (A §3, §4).
  - Moving-average crossovers and time-series momentum are the same family (Levine and Pedersen 2016). A breakout is a different, non-linear member.
- **Long-only is supported.** Most futures trend returns come from long signals, and the one direct crypto comparison found long-only better (A §3.10, §4.10).
- **Volatility scaling** is contested as a source of return. It is better treated as a risk control (A §5).
- **A slow regime filter** cuts drawdowns, with a risk of data snooping in choosing its length (A §6).
- **Mean reversion goes against the evidence for large coins:** they continue at daily and weekly horizons (A §7).
- **Long-only relative strength on 12 coins** forgoes most of the published alpha (A §8).
- **DCA** is a risk preference, not a source of return (A §9).
- **The repository's own results:**
  - STRAT-001 and STRAT-002 lost out of sample at 0.10% + 0.05% (`docs/dev/BACKTEST-REPORT-batch-1.md`).
  - STRAT-001 lost $5,191 of $10,000 at 0.50% in development (`docs/dev/SIG4-REPORT-dev.md`).

## 5. Design

### 5.1 Layers and terms

A decision passes through five layers. Each is versioned and recorded separately:

| Layer | Decides | Examples | Where |
|---|---|---|---|
| Strategy | Whether to be long or flat: entry and exit | STRAT-000 to STRAT-005 | `strategies/` catalogue, class `main` |
| Risk overlay and entry gate | Extra exits (stops) or vetoes on entries | OVL-ATR, OVL-COOLDOWN, OVL-REGIME | `strategies/` catalogue, class `risk_overlay` |
| Model filter | Whether to take an entry the strategy offered | A lab T1 model; F_P and F_PV | `model_lab`, `signal_fusion` |
| Sizing policy | The size of an entry | The fixed 1% entry; the volatility shrink | `position_sizing`; `signal_fusion/volatility.py` |
| Execution policy | How a position is bought | Market order at the next open; the legacy DCA ladder; periodic accumulation (a baseline) | `pt_trader.py`; evaluation only |

**Baselines** (§5.4.1) are evaluation references and never appear in the catalogue:
- REF-HOLD: buy-and-hold;
- REF-CASH: cash;
- REF-RANDOM: matched random entries;
- REF-ACCUM: periodic accumulation.

### 5.2 Catalogue extension

The catalogue keeps its fields, its registry cross-check and its fail-loudly loading (`strategies/catalogue.py:174-226`). Milestone M2 adds:

| Field | Values | Meaning | For existing entries |
|---|---|---|---|
| `authorisation` (required) | `research`, `paper`, `live` | The highest use the strategy may be selected for. `research`: backtests and evaluations only. `paper`: also selected for paper trading. `live`: also for live, within FDS-LIVE-001's guards | STRAT-000, -001, -002 and the four overlays: `live`, as today. STRAT-003: `research` (it cannot trade today, `strategies/settings.py:105-117`) |
| `timeframes_permitted` | Timeframes from `TIMEFRAME_SECONDS` | Timeframes the strategy may trade on. Research may use any timeframe | Every timeframe, as today |
| `deterministic` | `true` / `false` | `false` when the strategy needs a trained model | `true`, except STRAT-003 |
| `data_requirements` | `{"coins": "own" \| "own+reference" \| "all"}` | Which coins' bars a decision needs | `own` |
| `research_refs` | A list of section references into A | Where its evidence is described | `[]` |

**Families.** `FAMILIES` gains `breakout`, `momentum`, `regime`, `mean_reversion` and `relative_strength` (`strategies/catalogue.py:35`).

**Versions.** `version` is semantic:
- a change to a rule or a default raises the minor or major version;
- every result records the strategy's ID, version and a SHA-256 of its full parameters.

**Raising `authorisation`** is a reviewed code change. Its PR cites the owner's decision and the evidence (§6.7). No milestone in this spec raises one.

### 5.3 The lifecycle: four separate states

| State | Means | Recorded in | Changed by | Default for a new strategy |
|---|---|---|---|---|
| In the catalogue | Built, tested and listed | `catalogue.json` plus its class | A reviewed PR | — |
| Enabled for research | Offered by the research windows (§5.8) and declarable in an evaluation | `strategy.research_enabled` (a list of IDs) | The owner, in Settings > Strategy | **Not enabled.** STRAT-000, -001 and -002 are enabled by default, so the existing strategies stay usable |
| Eligible for paper trading | Its `authorisation` is `paper` or `live` | `catalogue.json` | A reviewed PR, on the owner's decision | **No** (`research`) |
| Selected for execution | `strategy.active_id`, as today | `pt_config.json` | The owner, in Settings > Strategy | — |

**The trader fails closed** (M2): a selected strategy whose `authorisation` does not cover the trading mode places no orders, and is reported as the settings problem it is (`pt_trader.py:1756-1766`).
- A `research` strategy can never be selected.
- A `paper` strategy cannot be selected in live mode.
- This changes nothing for today's strategies, whose authorisation is `live`.

### 5.4 Candidate strategies

#### 5.4.1 Baselines, including the existing strategies

| ID | Role | Notes |
|---|---|---|
| REF-HOLD | Buy-and-hold: each coin bought once at its first eligible bar, equal amounts, the same costs | Per coin and as a portfolio. Exists per coin (`backtest.engine.buy_and_hold`) |
| REF-CASH | No trades | Net 0; the floor for "economically viable" |
| REF-RANDOM | Matched random entries: the strategy's coins and number of entries per coin, holding times resampled from its own trades, the same costs and account | Extends `backtest.random_baseline` (mean hold only) to the portfolio replay. B = 10,000 as 10 runs × 1,000 |
| REF-ACCUM | Periodic accumulation: a fixed amount each week into each coin, held | An execution-policy baseline, not a strategy (A §9) |
| STRAT-000 | EMA cross 20/50, 1h | A trend baseline |
| STRAT-001 | TEMA cross 12/48 with ADX, 1h | The strategy in use; FDS-SIG-004's subject |
| STRAT-002 | Supertrend with an ATR trailing exit, 4h | A trend baseline with a trailing exit |
| STRAT-003 | The pattern model, as a strategy | The model-dependent reference; research only |
| Legacy neural engine | Neural levels, the DCA ladder, trailing profit margin | An engine, not a catalogue entry; FDS-MH-001's fixed strategy |

#### 5.4.2 The shortlist

| Priority | ID (provisional) | Name | Family | Deterministic | Timeframe | How it differs from the catalogue | Complexity |
|---|---|---|---|---|---|---|---|
| 1 | STRAT-004 | Donchian breakout | breakout | Yes | 1d | Entry on a new 55-day closing high, exit on a 20-day closing low. A non-linear, asymmetric rule (A §4.1), held for weeks to months. No catalogue strategy enters on a new high | S |
| 2 | OVL-REGIME | Market regime gate | regime | Yes | Any (reads daily bars) | A veto on new entries while the reference coin is below its long average. Usable with every strategy, the current STRAT-001 included | M (§5.6) |
| 3 | STRAT-005 | Time-series momentum, long or cash | momentum | Yes | 1d, decided weekly | The published 1-, 3- and 12-month rule (Hurst et al. 2017), decided weekly. The same family as STRAT-000 and -001 (A §3.1), but horizons of months, not hours, and a fixed weekly decision schedule | S |
| 4 | STRAT-006 | Volatility-band reversion in an uptrend | mean_reversion | Yes | 1d | The only contrarian candidate. Buys below the lower band while above the long average, and exits at the middle band or after 10 bars | S, plus a time-stop overlay |
| 5 | STRAT-007 | Relative-strength rotation | relative_strength | Yes | 1d, weekly | Holds the strongest k coins with a positive trend. The only cross-sectional candidate | L: a new portfolio interface (B §9 item 5) |
| — | (sizing policy) | The volatility shrink | volatility | Yes | — | Not a strategy: FDS-SIG-004's `min(1, σ_ref ÷ σ̂)`, evaluated across strategies (§5.9). Nothing is rebuilt | — |

#### 5.4.3 The candidates in detail

**STRAT-004 — Donchian breakout** (priority 1).

| | |
|---|---|
| Entry | On the closed daily bar t: `close[t] > max(close[t−n … t−1])`, where n = `entry_days` (a new n-day closing high), and the coin is flat |
| Exit | `close[t] < min(close[t−m … t−1])`, where m = `exit_days` (a new m-day closing low), or an overlay's stop |
| Defaults (bounds) | `entry_days` 55 (20–250); `exit_days` 20 (5–120); rule: `exit_days < entry_days` |
| Lookbacks in days | Parameters are calendar days, converted to bars by the run's bar length. So 12h and 4h runs use the same calendar span (§6.4) |
| Warm-up | `entry_days` + 1 days |
| Overlays | OVL-ATR (a volatility stop) and OVL-REGIME, both optional; none by default |
| Data | The coin's own daily closes |
| Trades | About 3 to 8 per coin a year (Zarattini et al.: BTC, 2015–2025, at 30 and 60 days; A §4.5) |
| Evidence | Gerritsen et al. 2020 [P]; Szakmary et al. 2010 [P]; Zarattini et al. 2025 [P, WP]; the Turtle rules [PR] (A §4) |
| Against | Wei et al. 2024: short channel rules fail out of sample. No test exists at these costs |
| Defaults' source | The Turtle System 2 rule (55/20), not a tuned value. Zarattini et al.'s ratcheting-midline exit needs position state. It is the deferred overlay OVL-MIDLINE (§13) |

**OVL-REGIME — market regime gate** (priority 2).

| | |
|---|---|
| Gate | Allows an entry only while the reference coin's last closed daily close is above its `sma_days`-day simple average |
| Exit | None. It never forces an exit, so it can only remove round trips (A §6.5) |
| Defaults (bounds) | `reference` "BTC" (values: "BTC", "self"); `sma_days` 200 (50–400) |
| Source of the default | 200 days is a practitioner convention [PR]. Faber's 10 months is about 300 daily crypto bars [S]. Bitcoin evidence covers 5 to 100 days [S]. The default is not evidence-derived, so 100, 200 and 300 are declared robustness trials, reported with PBO (§6.5) |
| Needs | The entry-gate context (§5.6) |
| Evidence | Faber [S]; Detzel et al. [S]; Hurst et al. Panel B [P] (timing is hard) (A §6) |

**STRAT-005 — time-series momentum, long or cash** (priority 3).

| | |
|---|---|
| Decision days | Only on bars whose UTC open falls on a decision day: every `rebalance_days` days from 2020-01-06, a Monday. Between them it returns HOLD, so overlays can still exit |
| Entry | On a decision day, at least `min_agree` of the three returns `close[t] ÷ close[t − Lᵢ] − 1` (Lᵢ in days) are positive, and the coin is flat |
| Exit | On a decision day, fewer than `min_agree` are positive, or an overlay's stop |
| Defaults (bounds) | `lookback_1` 30 (5–120); `lookback_2` 90 (20–200); `lookback_3` 365 (60–400); `min_agree` 2 (1–3); `rebalance_days` 7 (1–30); rule: lookbacks strictly increasing |
| Warm-up | `lookback_3` + 1 days. A coin joins once it has a year of daily bars |
| Data | The coin's own daily closes |
| Trades | A few switches per coin a year [R] |
| Evidence | Moskowitz et al. 2012 and Hurst et al. 2017 [P] (1-, 3- and 12-month signals); Liu and Tsyvinski 2021 [P] (crypto) (A §3) |
| Against | Huang et al. 2020; Kim, Tse and Wald 2016 (without volatility scaling it is close to buy-and-hold); Hudson and Urquhart 2021 |
| Not a renamed STRAT-000 | Its horizons are 30 to 365 days against 20 to 50 hours. It decides on a fixed weekly schedule, and votes across three horizons |

**STRAT-006 — volatility-band reversion in an uptrend** (priority 4, deferred).

| | |
|---|---|
| Entry | `close[t] < SMA20 − 2 × SD20` and `close[t] > SMA200` (daily), while flat |
| Exit | `close[t] ≥ SMA20`, or after `max_hold` bars (a time-stop overlay, OVL-TIMESTOP, using the position's entry time) |
| Defaults | 20, 2.0, 200, `max_hold` 10 |
| Evidence | Against it for large coins: Zaremba et al. 2021; Fičura 2023; Lento et al. 2007 (A §7) |
| Why listed | It is the only contrarian behaviour. Testing it would answer whether the published continuation holds here. A falsification test, not a candidate expected to pass |

**STRAT-007 — relative-strength rotation** (priority 5, deferred).

| | |
|---|---|
| Rule | Every 7 days, rank the coins by their 28-day return. Hold the top k = 3 that also have a positive 28-day return, equal-weighted; cash otherwise. A coin is swapped only when another leads it by a margin |
| Needs | A strategy interface that sees every coin at the same closed bar and decides for the portfolio, and an execution path for portfolio decisions. Neither exists (B §9 item 5) |
| Evidence | Weak for long-only on 12 coins (A §8) |
| Why deferred | Large, new execution behaviour, for the weakest evidence. It needs its own spec |

### 5.5 Recommendation: what to build first

Build **STRAT-004** (Donchian breakout) and **STRAT-005** (time-series momentum), each research-only and not enabled. With them, build **OVL-REGIME** (the regime gate) and its context extension.

- **Evidence:** the trend family has the best evidence, and long-only is supported in it.
- **Costs:** both decide on daily bars and trade a few times per coin a year, the only regime where 1.10% round trips leave a margin (A §2).
- **Different behaviour:**
  - STRAT-004 enters on strength and exits on a channel low, with an asymmetric, path-dependent rule.
  - STRAT-005 votes across months on a weekly schedule.
  - OVL-REGIME composes with every strategy, so it also tests the strategy in use today.
- **Complexity:** small. Each is one class and one catalogue entry with tests. The context extension is the one interface change.
- **Why not mean reversion** (STRAT-006) as the second strategy: it is the most diverse, but the evidence for these coins points against it. If the owner prefers diversity over evidence, STRAT-006 replaces STRAT-005 (decision E-D1).

### 5.6 The entry-gate context (M3)

- **The interface.** `Overlay` gains a declaration of the extra bars it needs: `context_needs()` returns pairs of (`reference`, `timeframe`), where `reference` is "self" or a coin. `allow_entry` gains an optional `context` argument.
  - Existing overlays declare nothing and ignore `context`, so they are unchanged.
- **The data.** The context holds each declared series' bars that **closed at or before** the decision bar's close.
  - The backtester slices them from the same cached frames.
  - The signal engine fetches them through the same closed-only provider (`signal_engine.py:50-60`).
  - A missing or stale reference series blocks the entry (fail closed), with a stated reason: an entry gate that cannot decide does not allow.
- **Determinism.** The same bars give the same decision in the backtest and in paper. A test replays one session through both (§12).

### 5.7 Execution: one selected strategy

- **The same strategy for every coin, as today.** Research may run any number of strategies in one process, on cached candles. Execution keeps one selected strategy for every coin, in paper and in live. This spec builds no multi-strategy execution.
- **Defined now, built later.** These rules are recorded so that any later proposal starts from them:
  1. **Assignment.** Each coin is assigned to at most one strategy, so no coin has two owners.
  2. **Ownership.**
     - Every position records its owner's strategy ID, version and parameter hash at entry.
     - Only the owner, with its own overlays, exits it.
     - Positions the trader did not open are never owned.
  3. **Cash.** Each strategy has a sleeve, a share of the account. It sizes entries within its sleeve, and a sleeve's unused cash is not lent to another.
  4. **Arbitration.** None is needed under exclusive assignment. A portfolio strategy (STRAT-007) owns its sleeve's coins exclusively.
  5. **Conflicting exits** cannot arise with one owner per position. The account-wide halt applies to every strategy.
  6. **Switching.** A strategy removed from a coin drains: no new entries, and its open positions exit by its own rules. Today a switch hands open positions to the new strategy (`signal_engine.py:118-139`). That behaviour is unchanged here, and is noted for the owner (E-D4).

### 5.8 The strategy administration in Settings

**Settings > Strategy** (milestone M2b) becomes a catalogue view. Everything in it is a fact the catalogue or the settings already hold.
- **The list:** every main strategy, showing:
  - name, family and primary timeframe;
  - **Use:** "Research only", "Paper" or "Paper and live";
  - **Research:** a tick for enabled;
  - **In use:** a mark on the selected one.
- **The details of the highlighted strategy:**
  - its description, entry rule and exit rule (from `strategies/descriptions.py`);
  - its parameters, bounded by `param_bounds`, as today;
  - its timeframe, from `timeframes_permitted`;
  - its compatible overlays and gates, with their parameters;
  - its evidence references.
- **"Use for trading"** saves it as `strategy.active_id`, with the rest of the window, as Save does today (`strategy_settings_ui.py:260-304`). It is offered only when the strategy's `authorisation` covers the current trading mode. Otherwise the row states which mode it can be used in.
- **Coins for trading** stay in Settings > Trading, with the paper override in Settings > Paper trading (`paper_coins.py`). A per-strategy coin set for trading belongs to multi-strategy execution (§5.7), and is not built.
- **Buttons:** "Run a backtest…", "Compare results…", "Model evidence…" (M5).

**Run a backtest…** (M5a), a new window:
- **Inputs:**
  - a strategy that is enabled for research, with its parameters (defaults shown, bounds enforced), overlays, gate and timeframe;
  - coins, ticked from the coins in Settings;
  - a period inside the development period (2021-01-01 to 2025-05-06), with later dates not offered;
  - an account (£50, £500, £10,000 or another amount above the minimum entry);
  - fees (the account's, the exchange's standard rate, or an entered rate) and slippage.
- **Running:** from cached candles through the exchange layer, off the Tk thread, and stoppable. It runs the portfolio simulation of §5.10.
- **Results:**
  - per coin and for the portfolio: net, return per capital-day, maximum drawdown and recovery, trades, holding time, capital used;
  - beside REF-HOLD, REF-CASH and REF-RANDOM;
  - an equity chart and the trade list.
- **Saved:** to `<data dir>/strategy_lab/runs/<id>/`, with its full configuration and candle SHA-256s.
- **Logged:** each run is logged as an exploratory trial with the months it read (§6.1), and the window shows the count. An exploratory run is never evidence.

**Compare results…** (M5a): saved runs and declared reports side by side, filtered by strategy, coin, timeframe and account. Facts only.

**Model evidence…** (M5b): for the highlighted strategy, the frozen results of declared evaluations, one line per model condition.
- Prediction, trading and economic lines are kept apart (§6.6).
- With none: "No model has been evaluated with this strategy."

**The legacy "Backtesting Framework" tab** is left as it is. Its replacement or relabelling is a backlog item (§13), because it runs strategies outside the catalogue on file or synthetic data.

### 5.9 Strategies against models: the comparison matrix

**The question each contrast answers:**

| Contrast | Holds fixed | Changes | Answers |
|---|---|---|---|
| S vs REF-RANDOM(S) | Strategy S's exits, coins, holding times | Entry timing: the strategy against random | Does S time entries better than chance? |
| S vs REF-CASH, REF-HOLD | — | — | Is S economically viable, and against holding? |
| S + gate vs S + random veto | S | The regime gate against random vetoes at the same per-coin counts (R3) | Does the regime gate add value to S? |
| S + model vs S + random veto | S and its exits | The model's veto against random vetoes at the same per-coin counts (R3) | Does the model improve S's entries, exits unchanged? |
| S + PV model vs S + P model | S, the model family, the threshold rule | Feature blocks | Does volume add to price, for S? |
| S + shrink vs S + random sizing | S | Sizing: the shrink against the same scales in random order (R3s) | Does volatility assessment add value? |
| Calibration of a strategy-specific model | S | — | Is its confidence calibrated (FDS-SIG-004 §5.5)? |
| The same model column across strategies | The model | The strategy | Does a model's effect hold for several strategies? |
| A deterministic S against a model-assisted S′ | — | Both | **Shown only**, labelled "two factors changed" |

**Models used** (each has a version and provenance):
- **Generic forecast filters:** the lab's T1 contestants `pv.linear.t1.P.q50` and `pv.linear.t1.PV.q50`.
  - Their saved out-of-fold probabilities (batch PV-1, `20261107-175558`; SHA-256s in `docs/dev/RUN-LOG-sig4-1.md`) are mapped to the hour of each entry decision. The veto uses each fold's own threshold.
  - They forecast a T1 barrier outcome, not the strategy's trade. That is what makes them generic.
- **Strategy-specific models:** F_P and F_PV (`signal_fusion/meta.py`), retrained on the strategy's own opportunities, with labels from its own exits (§5.10). They need enough events: a cell's scored opportunities must hold at least 200 events and 200 non-events (FDS-SIG-004's calibration floor, D16), or it reads "not assessable".
  - **Daily strategies may not reach it:** they make a few hundred trades in development.
- **No model:** the strategy alone.
- **The volatility shrink:** FDS-SIG-004's sizing policy (`signal_fusion/volatility.py`), evaluated per strategy.

**Rows:**
- STRAT-001 (1h), STRAT-004 (1d) and STRAT-005 (1d), with and without OVL-REGIME;
- STRAT-000 and STRAT-002, shown.

**Every experiment's record** is frozen before any result:
- **Strategy:** its ID, version, full parameters and their SHA-256, and its timeframe.
- **Layers:** the overlays and gates (IDs, versions, parameters); the model (lab key and batch ID with the probabilities' SHA-256, or the meta-model's specification and seed); the threshold rule; the sizing policy; the execution assumptions (market order at the next open).
- **Market:** the exchange order from Settings at freeze, the coins, the timeframes, and the series SHA-256s.
- **Windows:** development folds, the lockbox dates (unread), and any final check.
- **Costs:** fee rates with their source, slippage, minimum orders and lot sizes.
- **Accounts:** the sizes and the GBP-to-USD rate (§5.10).
- **Tests:** baselines with their seeds and draws; the tests, the family, Holm or BH.
- **Code:** the hash covers `strategies/`, `backtest/`, `signal_fusion/` and `model_lab/`, plus library versions.

### 5.10 The portfolio simulation and the three accounts

One data load serves every strategy, model, account and baseline in an experiment:
1. **Candles.**
   - Each (coin, timeframe) is read once from the cache, through the exchange layer; any missing range is fetched once.
   - Daily bars come from the exchange through `exchange_candles`, like every other timeframe. Only 2h, 4h, 8h, 12h and 1w are built from smaller cached bars (`market_data/candles.py:366-433`).
   - Nothing is fetched per account, strategy or draw, and no extra API request is made per account.
2. **Candidate trades** (M4a), the generalisation of `signal_fusion/labels.py` and the lab's trade cache (FDS-MH-001 §5.3):
   - For every bar at which the strategy signals ENTER while flat, the trade from that bar is replayed once through `run_backtest`'s rules at zero cost: entry at the next open, then exit by the strategy's and its overlays' rules.
   - The trade is cached as (coin, entry time and price, exit time and price).
   - A path takes a coin's first candidate after the coin is flat. So a skipped entry (no cash, or below the minimum) lets the next signal be taken, as the trader would.
3. **The replay** (`signal_fusion.evaluation.replay`): one call per account, with `Account(start=…)` and `Costs(fee, allowance, minimum_usd)`, sharing the candidate trades.
   - It follows the trader's own sizing:
     - `entry_usd` at 1% of the account's value;
     - the raise to the minimum entry;
     - the 10% coin budget, with the minimum always allowed;
     - one trade per coin;
     - the cash check.
   - Equity is marked at every close of the run's timeframe.

**Accounts.**
- £50, £500 and £10,000. £10,000 decides; £500 and £50 are shown (E-D5).
- The pairs are USD-quoted, so each account is converted to USD at one GBP-to-USD rate. The rate is declared in the experiment's record, entered by the owner, and never read live (E-D6).

**What a small account changes, and must show:**
- **The minimum entry:** below about 100 × the minimum entry, every entry is the minimum, above 1% (FDS-SIG-004 §3.7 item 1).
- **Lot sizes:** an order's quantity is rounded down to the product's base increment, from the exchange layer's public product data (cached). A rounded order below the minimum is skipped and counted. This matters at $1 orders: a 0.1-coin increment at $0.15 is 1.5% of the order.
- **Fees** are proportional, with no fixed fee per order [R]. This is an assumption, recorded per experiment.
- **Reported per account:** how many entries were raised, rounded or skipped.

**The halt is reported, not modelled**, as in FDS-SIG-004 §6.0. Each path reports:
- the first time the 8% level would have been reached;
- the variant that ends there;
- **new:** the value of the positions open at that moment, and their worst further loss over the next 30 days. A halted trader manages nothing (B §4.3).

**A check against the backtester** (a test, §12): with one coin and a 100% size, the replay reproduces `run_backtest`'s per-trade returns exactly, for every new strategy. This extends FDS-SIG-004's check for STRAT-001.

### 5.11 Paper-trading observation and evidence capture (M6)

- **Trade records** gain `strategy_id`, `strategy_version`, `params_sha256`, `timeframe` and the overlays' IDs and versions.
  - These are records only. A test shows the orders placed are byte-identical with and without them (the FDS-SIG-004 phase E method).
- **An observation segment** starts when the owner presses "Start an observation" in Settings > Paper trading.
  - It saves a frozen snapshot, with its SHA-256, of the settings that decide trades:
    - the strategy, parameters, overlays and timeframe;
    - the coins and the paper override;
    - sizing and risk;
    - the fee source.
  - Changing any of them ends the segment, logged with the time and the change. A new segment starts only when the owner presses the button again.
- **Reconcile…** replays a segment's closed candles, from the cache, through the same runner and compares trade by trade:
  - matched (the same entry and exit bars);
  - timing differences;
  - missed entries, with the trader's reason (cash, minimum, price unavailable, halt);
  - extra entries;
  - the fill price against the next open (paper's slippage);
  - the fee charged against the fee assumed.
- **What a segment is.** It is operational evidence: does paper do what the backtest says?
  - It is not a registered forward confirmation.
  - Registering one is a separate owner decision under a later spec, and is not authorised now.
- **New strategies cannot be observed in paper** until the owner raises their `authorisation` (§6.7).

## 6. Evaluation

### 6.0 Procedures shared with FDS-SIG-004 and FDS-MH-001

These apply unchanged unless stated:
- **The day-block bootstrap:** day units; circular blocks; all coins together; pairs on the same days; 10 runs of 1,000 draws seeded `seed + r`, using `random()` only (FDS-SIG-004 §6.0).
- **Holm and BH:** `model_lab.stats`.
- **PBO:** CSCV over 16 blocks.
- **The centred p-value**, and the trial log by kind.

**Block length for long trades** extends FDS-SIG-004's fixed rule: L = 28 × 2^k days, with k the smallest integer ≥ 0 for which at most 1% of the family's scored trades last longer than L ÷ 2 days.
- It is applied mechanically, before any result is read.
- Daily trend trades can last months, so L may reach 112 or 224 days, which leaves few blocks in 4.3 years. Power falls. That is reported, not avoided.

### 6.1 Data windows and earlier exposures

| Window | Dates | Used for |
|---|---|---|
| History before development | from 2020-01-01, fetched once into the candle cache | Warm-up only |
| Development | 2021-01-01 to 2025-05-06 | Everything declared in this spec: walk-forward folds for trained models, and the whole period for deterministic strategies at their declared defaults |
| Lockbox | 2025-05-06 to 2026-11-06 (FDS-MH-001's) | One final check per finalist, at most 3 finalists per family, within FDS-MH-001 §5.7's limit of 5 openings per month across all batches |
| After 2026-11-06 | — | Reserved for a registered forward confirmation (not authorised) |

**Earlier exposures, recorded before any result:**
- **STRAT-001 and STRAT-002:**
  - `docs/dev/BACKTEST-REPORT-batch-1.md` read BTC and ETH from 2023-01-01 to 2026-09-30, Binance, at 1h and 4h. That includes the lockbox's months, so their lockbox checks cannot be unseen evidence.
  - FDS-SIG-004's development run read STRAT-001 at 1h on 11 coins over the development period.
- **The entry signals of STRAT-004 and STRAT-005:** the lab's `rule.high20` and `rule.mom14` are related entry signals. Their development walk-forward results were read under the legacy exits (FDS-MH-001 §5.7, the phase B timing run). They are recorded as related looks at the entries, not at these strategies.
- **The strategies STRAT-004, STRAT-005 and OVL-REGIME:** no looks. **No backtest of them was run for this spec**, so that their development period stays unseen until a declared evaluation.
- **Strategy looks register:** like the lab's `LOOKS`, strategy-level looks are recorded in code (M4b): a reviewed change, with months, coins and where each is written up. Exploratory runs from Settings are recorded in the data folder's trial log, with their months.

### 6.2 Questions and families

Each family is declared before it runs; its members are fixed at freeze.

**Family S: strategies alone** (proposed for the first evaluation, E1; K = 4, Holm at 5%):

| Member | Test | Passes when |
|---|---|---|
| S1 | STRAT-004 vs REF-RANDOM | Its return per capital-day is above the matched random draws: p = (1 + #{draws ≥ STRAT-004}) ÷ (B + 1) |
| S2 | STRAT-005 vs REF-RANDOM | The same |
| S3 | STRAT-004 economic | FDS-SIG-004 F3's requirements (its §6.1 and D18), at £10,000 and 0.50%: at least 100 trades and 30 in each half (otherwise "Not assessable"); return per capital-day above 0 by the day-block bootstrap; net profit above 0 overall, in each half and without the best coin; a drawdown below the 8% halt level. The bootstrap is the family member; the rest are conditions |
| S4 | STRAT-005 economic | The same |

**Family G: the regime gate** (E1; K = 3): for S ∈ {STRAT-001, STRAT-004, STRAT-005}, S + OVL-REGIME against S + R3 at the gate's per-coin veto counts (return per capital-day). STRAT-000 and STRAT-002 are shown.

**Family M: models with strategies** (E1; K = 2): for S ∈ {STRAT-004, STRAT-005}, S + `pv.linear.t1.PV.q50` against S + R3 at the model's per-coin veto counts.
- Every other cell of §5.9 is exploratory: BH at q = 0.10, shown, never "passes". That includes the P model, the strategy-specific models, the shrink, calibration and STRAT-001's cells, which FDS-SIG-004 has already examined.

**Why so few** (A §11): with 4.3 years of development, an honest search allows a few dozen independent configurations across the whole initiative. E1 declares 9 tested members. Robustness variants are trials, reported with PBO.

### 6.3 Metrics, for every cell, account and coin

- **Net profit** after fees and slippage, in USD, with the GBP equivalent.
- **Return per capital-day:** summed net ÷ summed (amount × days held). This is the deciding score, as in the lab and FDS-SIG-004.
- **Return on the account** and annualised.
- **Maximum drawdown** from the marked equity curve, and the time to recover it.
- **Trades:**
  - count, by half and by year;
  - holding times (median, 90th percentile);
  - win rate;
  - largest single loss.
- **Capital:**
  - time in the market;
  - mean and peak capital committed;
  - entries raised, rounded or skipped.
- **By coin, and by regime:**
  - BTC above or below its 200-day average;
  - rising or falling;
  - volatility terciles;
  - year.
- **The halt report** (§5.10).
- **The smallest detectable effect** at the family's Holm level and 80% power (`model_lab.stats.smallest_edge`).

### 6.4 Robustness, shown

These are shown and never decide:
- **Timeframes:** 12h and 4h, with the lookbacks kept in calendar days (§5.4.3).
- **Exchanges:** the second exchange in Settings order, for the coins it lists.
- **Coins:** BTC and ETH only; and the coins with history from 2021-01-01 only, against today's selection (survivorship, §9).
- **Fees:** 1.20% taker, and 0.60% (the standard maker rate) as a "limit orders" scenario. Orders are not changed.
- **Parameters:** the declared variants:
  - STRAT-004: `entry_days` {20, 55, 100}, `exit_days` {10, 20};
  - STRAT-005: `rebalance_days` {7, 28};
  - OVL-REGIME: `sma_days` {100, 200, 300}.

  Each is a trial, and PBO is computed across them.

### 6.5 Power, and "too few trades to tell"

Each family reports its smallest detectable effect before its result (FDS-MH-001's convention). A member whose test could not have seen a realistic effect reads "Too few trades to tell", with the effect it could have seen. **This is expected to be common for the daily strategies** (§9).

### 6.6 Verdict lines

Prediction, trading and economic findings are separate lines, each with its caveat. The wording rule follows FDS-SIG-004 §6.1, as corrected in its run log: only an economic line may use "profitable".

| Finding | Pass | Fail |
|---|---|---|
| Prediction | "Forecasts improved: …" | "No forecast improvement detected (… n = …)" |
| Trading | "Beats random entries (…)"; "The gate adds value over random vetoes (…)" | "No better than random entries (…)" / "Too few trades to tell (…)" |
| Economic | "Profitable after fees at … (…), development only" | "Not shown to be profitable after fees (…)" |

Every line from the development period ends "Development only: not evidence for enabling anything."

### 6.7 What raising a strategy's authorisation requires

These are the owner's decisions, recorded with the evidence. E-D8 proposes the evidence:
- **To `paper`:**
  - its milestone's tests pass, including the backtest–paper parity test;
  - a declared development evaluation has reported, whatever its result;
  - the owner decides.

  Paper is for operational evidence (§5.11), so a strategy need not have passed its tests to be observed in paper. The record states the result it had.
- **To `live`:** this spec gives no route. It needs a passed final check on unseen months (the lockbox or a registered forward window), and the owner's decision, under a later spec.

## 7. Changes proposed to other specs

None to the approved parts of FDS-MH-001 or FDS-SIG-004.
- This spec reuses their tools: the replay, R3, R3s, the bootstrap, Holm, PBO, the trial log and the meta-models.
- It adds a strategy field to its own experiment records, not to theirs.
- **The one shared resource is FDS-MH-001's lockbox:** this spec's final checks count against its per-month opening limit (§6.1).
- **The wording rule:** the correction of FDS-SIG-004 §12 item 10 recorded in `docs/dev/RUN-LOG-sig4-1.md` applies here too (§6.6).

## 8. Implementation roadmap (deliverable D)

Each item is one PR, independently testable. The owner merges. Nothing below is authorised by this spec: each milestone starts on the owner's approval.

| # | Milestone | PRs | Depends on | Changes trading? |
|---|---|---|---|---|
| M1 | Research and specification | This PR (A, B, this spec, E) | — | No |
| M2 | Catalogue lifecycle and Settings > Strategy | **2a** the catalogue fields, families, the lifecycle and the fail-closed authorisation check (§5.2, §5.3). **2b** the catalogue view (§5.8) | M1 approved | No. Existing strategies are `live` and behave as today; a test proves it |
| M3 | First new strategies | **3a** STRAT-004. **3b** STRAT-005. **3c** OVL-REGIME and the entry-gate context (§5.6) | M2a | No. Research-only and not enabled |
| M4 | Strategy–model evaluation support | **4a** candidate trades for any strategy, the portfolio simulation, REF baselines, accounts, lot sizes (§5.10). **4b** experiment records, freeze, trial log and strategy looks (§5.9, §6.1). **4c** the model cells: the generic filter mapping, strategy-specific meta-models, R3 and R3s (§5.9) | M3 (and M2a) | No |
| M5 | Historical evaluation and reports | **5a** "Run a backtest…" and "Compare results…" (§5.8). **5b** "Model evidence…". **5c** the declared evaluation E1 and its report, **only on the owner's separate approval to register it** | M4 | No |
| M6 | Paper observation and evidence capture | **6a** the strategy fields in trade records (§5.11); this can follow M2a at any time. **6b** observation segments and "Reconcile…" | M2a; M4a for 6b | Records only, proven byte-identical |

**Each milestone's acceptance** is in §12. **Order:**
- M2a and then M3a/3b/3c can run in parallel.
- M4 needs at least one new strategy, and can start with STRAT-001.
- M5c is the first point that reads development results for the new strategies.

## 9. Limits and risks

1. **Few trades, low power.** Daily strategies give perhaps 150 to 300 trades in development and fewer in the lockbox. Long trades lengthen the bootstrap's blocks (§6.0). Many verdicts will be "too few trades to tell".
2. **The costs are untested in the literature.** No study tests these rules at 0.55% a side. A result here is the first evidence at these costs, for this coin set only.
3. **Survivorship.** The coins are today's coins in Settings; there is no point-in-time universe. Robustness on coins with history from 2021 and on BTC and ETH only is shown (§6.4).
4. **One market history** from 2021 to 2025, two or three cycles, mostly bullish for the coins that survived.
5. **Multiple testing grows fast.** Strategies × models × gates × accounts × timeframes × fees is a large grid. Only declared family members decide, and every other cell is a trial (A §11).
6. **Lockbox reuse.** This spec shares FDS-MH-001's lockbox and its opening limit. STRAT-001 and STRAT-002 have already seen it (§6.1).
7. **The halt does not exit.** A halted trader leaves positions unmanaged. The simulation reports the exposure at the halt; it cannot model the owner's resume (§5.10).
8. **Paper is not live.** Paper fills at the top of the book with no size slippage and no queueing (B §4.4). The reconciliation reports the gap; it cannot remove it.
9. **Account-level returns are small at 1% entries.** Return per capital-day is the efficiency measure; the account's return will look tiny. Both are reported (§6.3).
10. **Defaults not derived from evidence:** OVL-REGIME's 200 days and STRAT-004's 55/20. Their variants are trials (§6.4).
11. **Generic models are not strategy-specific.** A T1 filter forecasts a barrier outcome under the legacy rules, not the strategy's trade. A null result there does not rule out a strategy-specific model; the strategy-specific cells test that, where there are enough events.

## 10. Decisions for the owner

These are listed with their recommended answers in `docs/dev/strategy-research/E-decision-record.md`, items E-D1 to E-D12. The ones that cannot reasonably be deferred, because M2 or M3 depends on them, are:
- E-D1: the shortlist and the first three builds;
- E-D2: the identifiers;
- E-D3: the authorisation levels of the existing strategies;
- E-D4: single-strategy execution;
- E-D7: the research windows;
- E-D9: the parameter policy.

## 11. Out of scope

- Live trading, and any change to FDS-LIVE-001's guards.
- Activating any veto, gate or sizing control in paper or live. OVL-REGIME is research-only like the strategies.
- Registering a forward window, or any experiment (M5c needs a separate approval).
- Multi-strategy execution (§5.7 defines it; nothing builds it).
- Short selling, leverage and derivatives.
- Changing the legacy neural engine, its DCA ladder or trailing exit, the halt's behaviour, or paper's fill model.
- STRAT-006, STRAT-007, OVL-MIDLINE and OVL-TIMESTOP (deferred, §5.4.2, §13).
- Re-reviewing FDS-MH-001's or FDS-SIG-004's approved design.

## 12. Acceptance (for the implementation)

**M2:**
1. With today's settings, a replayed trader session places byte-identical orders before and after M2a (the FDS-SIG-004 phase E method). This covers STRAT-000, -001 and -002 with every overlay combination, and the legacy engine.
2. Selecting a `research` strategy places no orders and reports the problem. A `paper` strategy in live mode is refused too.
3. The catalogue refuses an entry without `authorisation`, with an unknown family, or with a `timeframe_primary` outside `timeframes_permitted`.
4. New research-enabled settings default as §5.3 says.
5. The catalogue view's text states facts only (the existing UI test method), and offers "Use for trading" only where the authorisation allows.

**M3:** for each new strategy and the gate:
1. Hand-worked signals on constructed bars: entries, exits and holds, including ties, warm-up, missing bars and the decision schedule.
2. **No look-ahead:** appending bars after t never changes the decision at t; a bar that has not closed is never used; the gate's reference bars closed at or before the decision.
3. **Parity:** the signal engine and the backtester give the same decisions on the same bars.
4. Parameter bounds and rules are enforced. The descriptions cover every parameter (`tests/test_strategy_settings_ui.py`'s check).
5. Each is `research`, not enabled for research, and refused for selection.

**M4:**
1. The replay with one coin at 100% reproduces `run_backtest`'s per-trade returns for STRAT-001, -002, -004 and -005.
2. **Candidate trades:**
   - every skipped entry lets the next signal be taken;
   - the candidate table is the same whatever the account;
   - one data load serves three accounts, with no extra requests (a counting test on the candle provider).
3. Lot-size rounding and minimum skips are counted per account.
4. **Freezing:** a frozen experiment refuses to run if its code, candles or record changed. Each scored cell logs a trial. Looks are recorded.
5. REF-RANDOM matches the strategy's coins, entry counts and holding times. Its draws repeat exactly for a seed.

**M5:**
1. The backtest window cannot read dates outside the development period. Every run is logged with its months.
2. The windows run off the Tk thread, can be stopped, and their text states facts only.
3. E1's report (M5c) separates prediction, trading and economic lines, and follows §6.6's wording.

**M6:**
1. Orders are byte-identical with and without the new record fields.
2. A segment ends on any deciding settings change.
3. "Reconcile…" on a recorded session classifies every trade (matched, timing, missed with a reason, extra) and reports price and fee differences.

## 13. Backlog (retrospective, not blocking)

These were found or deferred while preparing this spec. None is reopened here:
- **OVL-MIDLINE:** Zarattini et al.'s ratcheting Donchian-midline stop, as an overlay. The runner already ratchets stops.
- **OVL-TIMESTOP:** an exit after `max_hold` bars, for STRAT-006.
- **The legacy "Backtesting Framework" tab:** retire or relabel it once M5a exists. It runs strategies outside the catalogue on file or synthetic data.
- **The missing spec files:** FDS-121, -122, -123 and -129 were never committed. Code comments cite their sections.
- **The neural DCA trigger and its display disagree** when `trade_start_level` ≠ 3 (`pt_trader.py:2781` against `2438-2442`).
- **`paper_mode_balance`** in `gui_settings.json` is not read by the trader.
- **Settings > Training** has no field for the trainer's training window (`pt_pattern_trainer.py:116-118`).
- **The candle cache** has no in-process memo and no cross-process write lock (B §5.4).
- **FDS-MH-001 phase D** (the model lab window) and the lockbox's final check are not built yet. M5's windows should share their design.
- **Paper slippage:** a size-aware fill model for paper, if the reconciliation (§5.11) shows the gap matters.
- **FDS-SIG-004 §12 item 10's wording,** and the speed items listed in `docs/dev/RUN-LOG-sig4-1.md`.

## References

See `docs/dev/strategy-research/A-research-report.md` §12. Code references are to `main` at `cdae9c9`.
