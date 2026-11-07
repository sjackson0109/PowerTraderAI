# FDS-MH-001 — Multi-Model Harness: Comparing Entry Models Under the Fixed Strategy

**Issue:** none yet. Raise "Compare entry models fairly: walk-forward, random baselines, pooled coins" and link it here.
**Target repo:** `sjackson0109/powertraderai`
**Branch:** this spec is on `docs/fds-mh-001-model-harness`, cut from `main` at `500a355`. Each phase is built on its own `feat/mh-<letter>-…` branch, cut from `main` after the previous phase is merged.
**Recommended model:** Claude Opus 5.5, effort high, for phases A, B and C (statistics, look-ahead, the replay). Sonnet 5.5, effort high, for phase D (the window).
**Run log:** `docs/dev/RUN-LOG-mh-1.md`.
**Status:** draft for the owner's approval, 2026-11-06. On 2026-11-05 the owner agreed the scope: models only, with the strategy held fixed. On 2026-11-06 the owner asked for the harness to be written first and then built, as recommended (gate fix included, batch 1 as in §7). §10 lists the decisions with the recommended answers. On 2026-11-06 the owner set the lockbox to 18 months (D11), after phase B found that R2 cannot be drawn on 6 months.
**Amendments:** amendment 1 (proposed in FDS-SIG-004 Appendix A; accepted by the owner on 2026-11-07). It names feature blocks (§5.5), adds probability outputs (§5.5), a report of repeated runs (§5.6), a look at a feature (§5.7), trial kinds, spec versions and explicit batch lists (§5.8), and batch PV-1 (§7a). Batch 1 (§7) and every trial logged before amendment 1 are unchanged.
**Related:**
- FDS-MDL: the pattern model and its single-split test.
- PR #224: the entry gate.
- FDS-MX-001: market data through the exchange layer.
- FDS-121: the strategy backtester, where strategies (not entry models) are judged.

**Evidence:**
- `docs/dev/model-research/A-classic.md`, `B-deep.md` and `C-evidence.md`: three research reports, 2026-11-05.
- `docs/dev/GATE-DIAGNOSTIC-2026-11-05.md`.

> **Read this first.** No published study shows a model that times crypto entries better than random after costs like ours (C-evidence §1). No study tests our exact setup either: random-entry baselines with DCA and trailing exits. This harness answers that question for our strategy and coins. Expect most results to read "no better than random entries" or "too few trades to tell". A harness that says so is working.

---

## 1. Objective

Find out whether any entry model makes the trader's fixed strategy earn more than random entries do, after fees. Say so only when the data can show it.

The harness:
- runs many entry models ("contestants") on the same candles, with the same trade rules and fees;
- scores each one walk-forward, over years, on bars it was not trained on;
- compares each with random entries that keep its patience, pooled over coins;
- corrects for the number of contestants tried;
- keeps the last 18 months locked until finalists are chosen;
- reports "too few trades to tell" when the test could not have seen a realistic edge.

It also fixes the entry gate's random baseline and score (§6), which the diagnostic found biased.

## 2. Rules

- **Models, not strategies** (owner, 2026-11-05). A contestant decides only *when to enter*. Exits, DCA, sizing and fees are the trader's, and the same for every contestant. Strategies are a separate, later project.
- **Multiple exchanges, primary preferred** (owner, 2026-10-25): "never deviate from this design". Candles come only from `market_data.candles.exchange_candles`: the primary exchange first, then the others in their Settings order. No harness code names an exchange.
- **Every option in Settings** (owner, 2026-10-28). The harness runs from Settings > Training. Nothing needs a terminal or a hand-edited file.
- **UI text states facts only.** No spec names, test names or design caveats on screen.
- **Declared before it runs.** A batch's contestants, data, rules, fees and pass rule are frozen and saved before any of its results exist. Every scored contestant is logged as a trial. No parameter or threshold is chosen on held-out bars.
- **Nothing changes in trading.** The harness reads candles and writes its own files. It never places an order, publishes a model or changes a setting.

## 3. Today (code read on 2026-11-06, `main` `500a355`)

| # | Fact | Where |
|---|---|---|
| 1 | The trader enters a coin when its long count is at least `trade_start_level` (3), its short count is 0, and no trade in the coin is open. | `model_gate.py` docstring; `pt_trader.py` |
| 2 | The long count also triggers DCA buys ("neural DCA"): for the first four stages, below cost, at a long count of at least stage + 4. | `model_gate.replay`, `NEURAL_DCA_STAGES` |
| 3 | The exits and DCA (defaults): a trailing profit margin from +5% (+2.5% after a DCA) with a 0.5% gap; DCA at −2.5/−5/−10/−20/−30/−40/−50%, each 2× the position, at most 2 per 24 h, within 10% of the account per coin. | `model_gate.TRADER_DEFAULTS` |
| 4 | The trainer holds out the last 20% of the training window (about 7 months of 3 years). It publishes a model only when the entry gate passes on that slice. | `VALIDATION_FRACTION`, `validation_cut`, `pt_pattern_trainer.py:1593` |
| 5 | The gate's random baseline draws as many distinct held-out hours as the model made entries, and replays each as a trade of its own, so random trades overlap. It scores mean return after fees per trade. | `entry_gate.run_baseline`, `entry_gate.decide` |
| 6 | A failing model already in use keeps trading: the runner refuses a coin only when no model is kept. | `pt_thinker._refused_by_gate` (`pt_thinker.py:690`) |
| 7 | The LLM signal gate uses the same baseline. Each LLM signal is scored as a trade of its own (signals can overlap), so for it the overlapping baseline is right. | `llm_gate.py` |
| 8 | Fees: the primary exchange's taker rate, read from the account where the saved key allows (source "exchange"), else its published rate (source "default"; 1.20% for Coinbase). Plus 0.05% slippage per fill. The owner's account reads 0.50%. | `entry_gate.trading_fees`; owner's check window, 2026-11-05 |
| 9 | Candles: `exchange_candles` gives one series per coin, from the first exchange that can serve the range. It is cached per exchange, and gaps are reported, never filled. A pair listed after the window starts is served from its first bar. On Coinbase, BNB-USD starts 2025-10-22 and HYPE-USD 2026-02-05. | `market_data/candles.py`; sandbox cache, 2026-11-05 |
| 10 | Dependencies: numpy, pandas, scipy. No scikit-learn, LightGBM or PyTorch. Python 3.11 or later (CI runs 3.11 and 3.12). | `app/requirements.txt`, `README.md`, `.github/workflows/ci-cd.yml` |
| 11 | One pattern-model fit (3 years of one coin) takes about 25 s from cached candles, and up to 78 s with downloads. | sandbox trainer logs, 2026-11-05 |
| 12 | Settings > Training has the four gate fields and a "Check the models in use…" button, which runs `--check-gate` per coin off the Tk thread. | `pt_hub.py:7811`, `gate_check_ui.py` |

## 4. What the diagnostic found (2026-11-05)

Full report: `docs/dev/GATE-DIAGNOSTIC-2026-11-05.md`. Setup:
- pattern models trained as the models in use are, on 13 coins;
- Coinbase candles from 2023-11-06 to 2026-11-05;
- 0.50% + 0.05% per fill and the default trade rules.

Every replayed trade matched `model_gate.replay`, and the gate's recorded percentile was reproduced for every coin.

1. **The gate's baseline is biased against any trader that holds one trade at a time.** Overlapping random entries include buys made part-way down a drawdown, while a real trade would still be open, and those recover well. Pooled over the owner's 9 coins, random entries earned +0.149% per capital-day under the gate's baseline. When random entries also wait until flat, they earned +0.071%.
2. **Against a fair baseline, the pattern model's timing is no better than random, and not worse.** The fair baseline is "same waits, random order" (R1 below). Pooled over 13 coins (181 trades), the model's return per capital-day sits at the 48th percentile: +0.047% against +0.048%.
3. **Per-trade and per-day scores disagree.** Over 9 coins the model is at the 10th percentile per trade and the 67th per capital-day. Mean return per trade ignores how long capital is tied up, so it is the wrong score for these exits.
4. **The exits leave entries little room.** The model is in a trade 74–94% of hours, and trades last about 10 days. Entry timing can only matter in the hours when no trade is open.
5. **Power.** One trade's return under these rules has a spread of about 4.6%, measured over every 4th held-out hour of the 13 coins. Pooled over 13 coins (about 176 trades), the fair test can only detect a model that roughly doubles the return per capital-day of random entries. Its smallest detectable edge is 116% of the random median, at 80% power and one-sided 5%. Without changing the strategy, the only way to get more trades is walk-forward over several years.

## 5. Design

### 5.1 Terms

- **Series:** one coin's 1-hour candles over a window, from one exchange (§5.2).
- **Contestant:** one entry model with fixed parameters, for example "daily close above its 50-day average". Changing a parameter makes a different contestant.
- **Batch:** a set of contestants, run on a set of series with one set of trade rules and fees. It is frozen before it runs (§5.8).
- **Trial:** one contestant scored on one batch's held-out bars. Every trial is logged.
- **Stream:** for one coin, the walk-forward held-out hours joined end to end. Each hour is decided by a fit that saw only earlier bars (§5.4).
- **Lockbox:** the last 18 months of every series, held back until finalists are chosen (§5.7).

### 5.2 Data series

- **Source.** `exchange_candles(coin, "1h", start, end)`: the primary exchange first, then the others in Settings order. Each series comes from one exchange. It records:
  - its `exchange` and `pair`;
  - its first and last bar;
  - the SHA-256 of the bars it uses, in the candle cache's CSV format. The cache file is shared and grows, so its own hash would not identify them; the trainer's `candle_sha256` works the same way;
  - its gap report.

  A frozen batch reads each series again from the exchange it came from.
- **Higher timeframes.** Daily, 4-hour and weekly values are built from the 1-hour bars (`market_data.resample.build_candles`), aligned to UTC.
  - A value at an hour uses only bars that have closed by that hour.
  - A daily value uses the last *completed* UTC day.
  - Why this matters: a multi-timeframe alignment bug inflated AUC by about 0.20 in Sobreiro et al. 2026 (A-classic §2.2).
  - The pattern model keeps its own candle frames, loaded the way the trainer loads them.
- **Window.** It runs from the batch's start date, or from the series' first bar if later, to the last closed hour when the batch is frozen. A late listing is handled as the trainer handles it (PR #159).
- **Gaps.**
  - A gap of up to 24 hours is kept. No entry is made inside it, and an open trade carries on at the next close.
  - A longer gap ends the earlier part: the series is the stretch after the last such gap. For example, if an exchange halted a coin for months, only the part after the halt is used.
- **Survivorship.** A coin later blocked as delisted (`market_status.json`) may still be included, where an exchange still serves its history. The report lists each coin and why it was included.

### 5.3 The fixed strategy and the replay

- **Replay.** Trades are replayed with `model_gate.replay` and the batch's trade rules (`model_gate.trade_rules`). That covers:
  - the trader's exits, DCA and sizing;
  - the 24-hour DCA cap and the per-coin budget;
  - the fee and slippage on every fill.

  Each coin holds one trade at a time. A trade that ends at an hour's close leaves that hour free for the next entry.
- **Neural DCA is off for every contestant** (D1). It reads the pattern model's long count, which other contestants don't have; with it on, the exits would differ between contestants.
  - The pattern model is also reported with neural DCA on, against random entries whose DCA reads the same counts (as the gate does today).
  - That line is shown and decides nothing.
- **Trade cache.** With neural DCA off, a trade depends only on its entry hour. So each coin's trade from every stream hour is replayed once and cached, and every contestant and every random draw reuses it.
- **Account.** Each coin trades a 100-unit account, not compounded, as in the gate. A trade still open when its stream ends is sold at the last close, exit fee included.

### 5.4 Walk-forward

- **Calendar.** Fold 1 starts 12 months after the batch's start date. Each fold is 3 months, on the same dates for every coin. The last fold ends where the lockbox starts, so it may be shorter.
- **Fits.**
  - A trained contestant is fitted at the start of each fold on every bar before it (an expanding window). That fit, frozen, decides the fold's hours.
  - A pooled contestant fits once per fold on all coins. A per-coin contestant (the pattern model) fits once per coin per fold.
  - The cadence is 3 months, not monthly, because each pattern-model fit takes 25–78 s (§3 row 11). At 3 months that is 18 folds × 13 coins for batch 1.
- **Purge.** Training rows whose label looks past the fold's start are dropped: that is the last H hours before the fold, where H is the label's horizon (§5.5). Training never comes after a test fold, so no embargo is needed.
- **Joining late.**
  - A coin joins the stream once it has the history its contestants need: 100 days for the longest rule, 50 days for the features.
  - A per-coin contestant joins once the coin has 12 months of bars.
  - Every comparison uses only the hours both sides cover.
- **Untrained rules** have nothing to fit. They decide every stream hour from the bars before it.

### 5.5 Contestants and targets

Every contestant implements one interface (`app/model_lab/contestants.py`):

```python
class Contestant:
    key: str          # stable id, e.g. "rule.sma50"; part of every trial id
    family: str       # "reference", "rule", "pattern", "linear" or "trees"
    params: dict      # fixed; shown in the report
    pooled: bool      # one fit for all coins, or one per coin

    def fit(self, data, until) -> "Fitted": ...   # a rule has nothing to fit


class Fitted:
    def entries(self, coin, close_s) -> "numpy.ndarray": ...
    # one value per hour: 1 = enter if flat, 0 = don't, -1 = undecided
```

`Fitted` may also give `probabilities(coin, close_s)`: one probability of its target per hour, or `None` (amendment 1). A trained contestant saves them with its results, for FDS-SIG-004's forecast scores. Its entries are still decided only by `entries`, and no pass rule in this spec reads the probabilities.

**Thresholds.** A trained contestant's threshold is part of its fit. It enters when its score is in the top q of the scores it gave its own training rows, where q is a fixed parameter. Nothing is chosen on held-out bars.

**Targets.** Each trained contestant names one.
- **T1, clean win.** From the close of hour t, does the price reach the first profit line before the first DCA level, within H = 336 hours (14 days)?
  - The profit line is `pm_start_pct_no_dca` above the entry's average cost, fees included, as the trader computes it. The DCA level is `dca_levels[0]` below that cost.
  - Both barriers come from the batch's trade rules, not from constants.
  - Hits are judged on hourly highs and lows. A bar that touches both barriers counts as a loss, and so does reaching neither within H.
  - Expect a base rate near 0.34. With no drift, P(+5% before −2.5%) ≈ 0.34 whatever the volatility (A-classic §3.1).
- **T2, trade return per capital-day.** The replayed trade's (§5.3) net return divided by its capital-days.
  - A trade still open after 30 days (H = 720 hours) is marked at that close.
  - Values are winsorised at the training rows' 1st and 99th percentiles.
- **Weights.** Labels overlap, so each row is weighted by its average uniqueness (López de Prado 2018, ch. 4; A-classic §3.2).

**Features** (pooled contestants only). They are scale-free, so coins can share one model, and come only from completed bars:
- log returns over 1, 4, 12, 24, 72, 168 and 336 hours;
- realised volatility over 24 and 168 hours, and the ratio of the two;
- Parkinson range volatility over 24 hours;
- log of the close over its average across 24 hours, 7, 30 and 50 days;
- the drawdown from the 30-day high and the distance from the 30-day low;
- log of 24-hour volume over the 30-day daily mean;
- the last bar's body and wicks, each as a share of its range;
- BTC's 24- and 168-hour returns and its 168-hour volatility;
- the coin's 24- and 168-hour returns minus BTC's.

That makes 26 features, with a longest look-back of 50 days (A-classic §2.2). The evidence for BTC-lead features is weak.

**Feature blocks** (amendment 1). `features.py` names the features in blocks, and a contestant names the blocks it uses:
- **P:** the 25 features above other than the volume feature.
- **v1:** the volume feature above, log of 24-hour volume over the 30-day daily mean.
- **v2:** log of the hour's volume over the mean volume of the same UTC hour on the 20 previous days. A zero mean makes it missing.
- **V:** v1 and v2.

Batch 1's pooled contestants use P and v1, which are the 26 features above, exactly as §7 declares them. Volume is base-asset volume, defined the same way on every connector. A placebo replaces V with the same coin's V from a fixed number of hours earlier (§7a). No block contains Chaikin Money Flow or BTC's one-hour return, the candidates of FDS-SIG-002's round one.

### 5.6 Random baselines, scores and tests

**Scores.** These are computed over a contestant's trades on all coins and all folds.
- **Return per capital-day** is the score that decides: total net profit after fees, divided by the sum over trades of capital committed × days held.
- **Shown, not deciding:**
  - total profit, mean return per trade and worst drawdown;
  - the number of trades and the time spent in a trade;
  - the same figures by coin;
  - the same figures in rising and falling markets (BTC above or below its close 90 days earlier, at the entry hour);
  - the same figures at half and at double the fee rate. These replay only the contestant's own schedule.

**Two random baselines.** Both keep the contestant's patience.
- **R1, same waits, random order.** Per coin, one trade at a time:
  - from the stream's start, and after each exit, wait one of the contestant's own waits, drawn at random with replacement, then enter;
  - a wait is the time from being free to entering. The time after the contestant's last exit is not a wait, because it never ended;
  - R1's entry count varies around the contestant's.
- **R2, same schedule, other dates.**
  - The contestant's entry signal for every coin is moved by one random offset δ, then replayed one trade at a time. δ is the same for every coin in a draw, and wraps round each coin's stream.
  - This keeps how its entries cluster in time and across coins, which R1 does not.
  - δ stays at least D = 160 days from 0 and from the stream's length. D is the longest look-back (100 days) plus 60 days for a trade. So a moved signal is never built from the prices of the trade it starts.
  - A draw takes one number u in [0, 1). Each coin's δ is that share of its own allowed range, from D to its stream's length minus D. Coins whose streams have the same length, as most do, move by the same δ.
  - A coin whose stream is shorter than 2D takes no part in R2. The report lists it. R2 is compared with the contestant's trades on the coins that do take part.
- **Draws.** There are B = 10,000 draws of each baseline, seeded `seed + b`. In draw b, R2 uses the same offset for every contestant.
  - Draws use only `random()`, as the gate's do, so a seed repeats exactly across Python versions.

**Runs** (amendment 1). Every batch's B = 10,000 draws, seeded `seed + b`, are also reported as 10 runs of 1,000 consecutive draws: run r is draws 1,000 r to 1,000 r + 999. Each run's p is shown beside the p-value, which is still computed from all 10,000. This changes no draw and no p-value, batch 1's included.

**p-values.** p₁ = (1 + the number of R1 draws scoring at least the contestant's score) / (B + 1) (Phipson & Smyth 2010). p₂ is computed the same way for R2. A contestant's p is the larger of the two, because it must beat both.
- When no coin's stream is long enough for R2, p₂ = 1.
- Every tested contestant counts in K. One that made no entries counts at p = 1.

**Pass rule.** For a batch of K contestants:
1. **Screen.** Benjamini-Hochberg at q = 0.10 over the batch's K p-values. Shown, decides nothing.
2. **Finalist.** Holm at 5% family-wise error over the K p-values, *and* all of the following:
   - total profit after fees above 0;
   - at least 100 trades pooled;
   - worst drawdown no worse than R1's median;
   - for a trained or pattern contestant only: return per capital-day and total profit both above those of the batch's best untrained rule, on the hours both cover;
   - the batch's probability of backtest overfitting at most 0.5. That is CSCV over 16 time blocks of the stream, on each contestant's return per capital-day (Bailey et al. 2017; C-evidence §4.4).
3. **Lockbox** (§5.7).

**Why Holm, not SPA/StepM.** Holm is valid whatever the dependence between contestants, and needs nothing beyond the p-values. StepM can replace it later for more power (C-evidence §4.2). The deflated Sharpe ratio is left out: it tests against a Sharpe of 0, not against random entries, and the permutation test already copes with non-normal returns. The trial count it rests on is reported instead (C-evidence §4.3).

**Smallest detectable edge.** For each contestant it is (z at 1 − 0.05/K, plus z at 0.8) × the larger of R1's and R2's standard deviation of draw scores. That is the edge the contestant would have had an 80% chance to pass at the Holm level. If it is more than 50% of R1's median return per capital-day, the result is "too few trades to tell", not "no better than random".

**Verdicts shown.** Facts only, no jargon:

| Verdict | When |
|---|---|
| "Beats random entries" | A finalist that passed the lockbox |
| "Passed; final check not run" | A finalist before its lockbox |
| "Better than random entries here, not by enough to pass" | Passed the screen, not a finalist |
| "No better than random entries" | Not past the screen, and its smallest detectable edge is at most 50% of R1's median |
| "Too few trades to tell: this test could only see an edge above X" | Its smallest detectable edge is above that |
| "Worse than random entries" | Its lower-tail p, on the same draws against both baselines, is at most 0.05/K |

### 5.7 The lockbox

- **What it is.** The last 18 months of the batch's window, for every coin (D11). No fit, threshold or choice uses it before it is opened. 18 months is longer than 2D (320 days), so R2 can be drawn on its hours.
- **Opening.** It is opened once per finalist, for at most 3 finalists per batch, smallest p first.
  - The finalist is refitted at the lockbox's start on everything before it, and keeps its 3-month cadence inside.
  - It is replayed with the same rules, and R1 and R2 are drawn on the lockbox's hours.
- **Passing.** It passes when its return per capital-day is above the medians of R1 and R2, and its total profit after fees is above 0.
  - Eighteen months pooled is about three times the 50–150 trades C-evidence §4.6 gives for six. The lockbox catches overfitting and leaks; the walk-forward test carries the evidence.
- **Failing.** A finalist that fails is retired. A changed version is a new contestant in a new batch.
- **Limits.** Every opening is logged with its months. Each month can be in at most 5 openings, across all batches. A batch whose last 18 months include a month opened 5 times waits for newer data (C-evidence §4.6; Dwork et al. 2015).
- **Seen already** (`model_lab/catalogue.py`, `LOOKS`; owner's review, 2026-11-06). Every earlier look at a contestant's results is recorded in code, with the months it covered and where it is written up; adding one is a reviewed change.
  - A batch records, when it is frozen, which of them cover any of its lockbox.
  - A contestant with any is never given "Beats random entries". A finalist's verdict is "Passed; its lockbox was seen before, so a final check would not be unseen evidence", and its final check is shown, not counted as evidence.
  - **The pattern model's looks:**
    - FDS-MDL Tests A and B (BTC and ETH, 2024-07-01 to 2026-10-01, as STRAT-003 with that strategy's exits);
    - the volume research (10 coins, 2026-03-31 to 2026-11-05);
    - the entry gate's held-out slices of the models in use (from about 2026-04);
    - the gate diagnostic (13 coins, 2026-04-05 to 2026-11-05).

    With batch 1's lockbox (from 2025-05-06), its final check cannot be unseen evidence for it.
  - **The seven rules and the pattern model:** the phase B timing run (2021-01-01 to 2025-05-06), which read the walk-forward only. Its 8 trials count in phase E's report.
  - **A look at a feature** (amendment 1). When a study looked at how a feature relates to trade outcomes, the look is recorded for every contestant that uses the feature, with the months and coins it covered. The volume research (2026-11-05) looked at v2, as `rv_hod20`, against STRAT-001's trades on 10 coins from 2023-11-06 to 2026-11-05. It is recorded for batch PV-1's `pv.linear.t1.PV.q50` and `pv.linear.t1.PVp.q50`. None of the research's measures is v1, and it looked at no batch 1 contestant's results, so batch 1 gets no new look; its report lists the volume research as related work.

### 5.8 Batches, the trial log and results

- **Catalogue.** Contestants and their parameter variants are defined in code (`app/model_lab/catalogue.py`).
  - Adding or changing one is a reviewed code change, and makes new contestants.
  - The window has no parameter fields, so results cannot be tuned by trying values on screen.
- **A batch** is chosen in the window: contestants (ticked from the catalogue), coins and start date. On Run it is frozen and saved before any result exists, with:
  - its contestants;
  - its series (exchange, pair, SHA-256);
  - its trade rules;
  - its fees (rate, order type, exchange, source);
  - its seeds, fold dates and lockbox dates;
  - the file's own SHA-256.
- **Refusals.** A batch whose file, code or candles have changed since it was frozen is refused.
- **Trial log:** `<data dir>/model_lab/trials.jsonl` (`pt_paths.data_dir()`), one line per trial. A trial is logged as soon as it is scored, so a stopped batch's scored trials stay counted. The window shows the count of distinct trials.
- **Kinds of trial** (amendment 1). A trial line may carry `kind`: "trading" for a contestant's trades scored against R1 and R2, or "forecast", "decision", "calibration" or "sizing" for FDS-SIG-004's analyses. A line without `kind` is "trading". The window counts distinct trials of each kind.
- **Spec version** (amendment 1). A batch file records `spec_version`, the version its batch was declared under: "1" for batch 1 (declared in §7 on 2026-11-06), "1.1" for a batch declared by amendment 1 or later. A batch is run by the rules of its own version, whenever it is frozen.
- **Batch membership** (amendment 1). Each batch's contestants are an explicit list in `catalogue.py` (`BATCH_1`, `BATCH_PV_1`). Adding a contestant to the catalogue never adds it to a declared batch.
- **Results:** `<data dir>/model_lab/batches/<id>/`, holding `batch.json`, `results.json` and `report.md`.
- **Deterministic.** The same batch on the same cached candles gives the same results.
- **Running.** The harness runs off the Tk thread, as "Check the models in use…" does, and can be stopped. A stopped batch keeps its frozen record and is marked as stopped.

### 5.9 Settings > Training, "Compare models…"

- **Data:**
  - coins, as ticks, with the coin list first and other coins typed in;
  - the start date;
  - a read-only line saying where candles come from: the primary exchange, then the others.
- **Contestants:** the catalogue, with each one's fixed parameters in plain words. The last batch's choices are ticked.
- **Run / Stop,** with progress: folds, coins and draws.
- **Results:** a table per batch (`ui_table.DataTable`) with:
  - contestant, trades and return per capital-day;
  - R1 and R2 percentiles and the smallest detectable edge;
  - the verdict, total profit, worst drawdown and time in a trade.

  Selecting a row shows its per-coin, rising/falling and fee lines.
- **Final check…** on a finalist: a confirmation that it can be done only once, then the lockbox result.
- **Also shown:** the trial count, and the reference line "Enter whenever flat" (§7).

## 6. The gate fix (phase A)

The trainer's per-coin gate keeps its place and its Settings fields, and changes as follows (D2):

- **Its random baseline becomes R1** (same waits, random order), on the coin's held-out hours. It no longer uses distinct hours replayed as overlapping trades.
- **Its score becomes return per capital-day.**
  - Rule b (the minimum return), rule d (beat the percentile) and rule f (no worse than the model in use) use the new score.
  - Rules a (minimum entries), c (capital-weighted return above 0) and e (drawdown no worse than random's median) stay as they are.
- **A trained model gets a minimum of its own.**
  - "Minimum return per day held after fees %" (`gate_min_return_per_day`, default 0) is rule b's minimum for a trained model. A saved per-trade value is never turned into it, because it measured something else.
  - The per-trade minimum, `gate_min_return_after_fees`, stays as saved, as the LLM signals' rule b ("Minimum mean return per LLM signal after fees %"). An LLM gate decision is the same as before for any saved value (owner's review, 2026-11-06: the first version of phase A fixed it at 0%, which changed decisions for anyone who had saved another value).
  - A model in use whose record has no per-day score skips rule f once, and the check window says it has none recorded.
- **The check window and `model_gate.json`** add the smallest detectable edge. When that edge is above 50% of the random median, they say "too few trades to tell".
- **Entry counts.** R1's entry count varies around the model's, so "the same number of entries as the model" no longer holds. The decision records both counts.
- **R2 is not used here,** because a 7-month held-out slice is shorter than 2D.
- **The LLM signal gate is unchanged** (§3 row 7): the same score, baseline and settings, its per-trade minimum included. Its decisions are checked against main's at the default and at other saved settings.
- **Settings text.** Settings > Training's description changes to match: "per day held", "random entries made with the same waits".

## 7. Batch 1 (declared here, before any result)

- **Coins:** 13 in all.
  - The owner's: BTC, ETH, XRP, BNB, DOGE, SOL, ZEC, DASH, HYPE.
  - The diagnostic's four others: ADA, AVAX, LINK, LTC.
- **Window:**
  - from 2020-01-01 00:00 UTC, or each series' first bar if later, to the last closed hour when frozen;
  - fold 1 starts 2021-01-01;
  - the last 18 months are locked (D11). Frozen on 2026-11-06, that would be from 2025-05-06.
- **Trade rules:** the trader's defaults (`model_gate.TRADER_DEFAULTS`), with neural DCA off.
- **Fees:** for each coin, the taker rate `entry_gate.trading_fees` gives, plus 0.05% slippage. The report run cannot read the account, so it uses 0.50%: the owner's account rate, from the check window on 2026-11-05.
- **Seeds:** R1 from 300000, R2 from 400000, fits from 0.

| # | Key | Contestant | Parameters |
|---|---|---|---|
| — | `ref.always` | Enter whenever flat. Reference only, not tested: its random baselines are itself | — |
| 1 | `rule.sma20` | Daily close above its 20-day average | completed UTC days |
| 2 | `rule.sma50` | Daily close above its 50-day average | completed UTC days |
| 3 | `rule.sma100` | Daily close above its 100-day average | completed UTC days |
| 4 | `rule.mom14` | Daily close above its close 14 days earlier | completed UTC days |
| 5 | `rule.high20` | Daily close at or above the highest of the previous 20 daily closes | completed UTC days |
| 6 | `rule.btc50` | BTC's daily close above its 50-day average (used for every coin) | completed UTC days |
| 7 | `rule.dip24` | 24-hour return below the coin's own 10th percentile of the last 90 days | hourly |
| 8 | `pattern` | The pattern model, as the trader uses it (long ≥ 3, short 0) | the trainer's fit, per coin |
| 9 | `linear.t1.q50` | Logistic regression on T1, top 50% | L2 penalty, C = 1, features standardised on training rows |
| 10 | `linear.t1.q20` | Logistic regression on T1, top 20% | as 9 |
| 11 | `trees.t1.q50` | Gradient-boosted trees on T1, top 50% | see below |
| 12 | `trees.t1.q20` | Gradient-boosted trees on T1, top 20% | see below |
| 13 | `trees.t2.q50` | Gradient-boosted trees on T2, top 50% | see below |
| 14 | `trees.t2.q20` | Gradient-boosted trees on T2, top 20% | see below |

K = 14.

Amendment 1 leaves this batch as declared: its contestants, K, seeds, draws, fold dates, lockbox and pass rule.

**Trees settings.** scikit-learn's `HistGradientBoostingClassifier` (T1) or `HistGradientBoostingRegressor` (T2), with:
- learning rate 0.05 and 300 iterations;
- 15 leaves and at least 200 rows a leaf;
- L2 regularisation 1.0;
- no early stopping, `random_state` 0;
- uniqueness weights.

Under D6, these histogram trees are used instead of LightGBM: it is the same method, with one dependency fewer (A-classic §2.2).

**Evidence for each:**
- **Rules 1–6:** the best-supported published signals. They are mostly daily and mostly in rising markets, and one large test found none for BTC out of sample (A-classic §2.1; C-evidence §2, "What survives").
- **Rule 7:** the opposite sign, and what DCA itself bets on. For large coins the evidence points against it (A-classic §2.4).
- **Contestants 9–14:** A-classic §2.2–2.3.

**Batch 2** would be a later addendum, proposed only if the owner wants it after seeing batch 1's report. It would test:
- a small GRU/TCN on T1;
- Kronos-mini/small;
- Chronos-2 forecasts as features (B-deep).

They need PyTorch, which is a large install.

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

## 8. Phases (one PR each)

### Phase A — the gate fix (§6)

**Changes:**
- `model_gate.py`: R1 draws on a coin's held-out hours, capital-days on each trade, and the per-day score.
- `entry_gate.py`:
  - `Trade` gains capital-days, and `score` gains return per capital-day;
  - `decide` takes the score to use;
  - the LLM gate keeps the per-trade score and its baseline.
- `training_settings.py`: the new per-day setting.
- `gate_check_ui.py`, the Settings text and `model_gate.json`: the smallest detectable edge and both entry counts.

**Tests:**
- R1 on a hand-built price path: a known wait list gives known entries;
- the per-day score on two hand-checked trades;
- the LLM gate's decisions are unchanged on its existing fixtures;
- a contestant that is itself an R1 draw ranks above R1's 95th percentile in about 5% of 200 seeds.

**Check:** with seed 200000, the 13 diagnostic coins' held-out hours (captured in a sandbox) give exactly the diagnostic's B3 percentiles when R1 is fed the diagnostic's own picks. The diagnostic drew a wait with `rng.choice`, while the gate draws with `random()` alone (§5.6), so the gate's own draws match only within the noise between two sets of 1,000 draws.

Capital-days count each hour by its length in clock time, so a gap in the candles still counts its time.

### Phase B — the harness core, no new dependency

**Package `app/model_lab/`:**
- `series.py` (§5.2) and `replay.py` (§5.3, the trade cache);
- `walkforward.py` (§5.4) and `baselines.py` (R1, R2);
- `stats.py`: p-values, Benjamini-Hochberg, Holm, the smallest detectable edge and PBO;
- `catalogue.py`, and `contestants.py` with rules 1–7, `ref.always` and `pattern`;
- `batch.py`: freeze, run, the trial log, results and the report.

There is no command line for users (§2); tests drive the package.

**Tests** (no network, fixture candles):
- every rule computed from bars cut at an hour equals the same rule from all bars (no look-ahead);
- R2 never moves a signal less than D;
- a batch run twice gives identical results;
- a frozen batch whose file has changed is refused;
- on a random-walk price path, R1 and R2 pass a no-skill contestant at about the nominal rate;
- the pattern contestant's fold-1 entries equal the trainer's sibling fit on the same window.

**Measure:** the time to build the trade cache, and a full batch-1 run without the trained contestants.

### Phase C — trained contestants

**Changes:**
- `app/requirements.txt`: `scikit-learn>=1.5` (BSD-3-Clause).
- `app/model_lab/features.py` (§5.5).
- `app/model_lab/targets.py`: T1, T2, the purge and uniqueness weights.
- `contestants.py`: the linear and trees contestants.

**Tests:**
- feature look-ahead, as in phase B;
- T1 on hand-built paths: up first, down first, both in one bar, neither;
- the purge removes exactly the rows whose label crosses the fold;
- thresholds come from training rows only: changing a held-out bar changes neither the fit nor the threshold.

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

### Phase D — Settings > Training, "Compare models…" (§5.9)

**Changes:** `model_lab_ui.py`, and the button in `pt_hub.py`. The work runs off the Tk thread.

**Tests:**
- the window with a fake runner, as in `gate_check_ui`'s tests;
- the Final check confirmation;
- facts-only text.

**Screenshot** through the hub screenshot harness.

### Phase E — run batch 1 and report

- **Run** batch 1 (§7) in a sandbox, on public candles, with Coinbase as the primary exchange (the owner's trading exchange).
- **Write** `docs/dev/MODEL-LAB-REPORT-batch-1.md`, with:
  - the data: series, exchange and SHA-256;
  - each contestant's earlier looks (§5.7), and the trials logged before this run;
  - the frozen batch file and every trial's lines;
  - the verdicts, the smallest detectable edges and PBO;
  - the per-coin, rising/falling and fee lines;
  - one plain paragraph on what was found, with its caveat in the same sentence.
- **Order:** the walk-forward section is committed first. The lockbox is opened after that, and only for finalists.

## 9. Limits and risks

- **Power.** Even over years, a realistic edge may be too small to see (§4 item 5; C-evidence §4.10). "Too few trades to tell" is an honest answer, not a failure of the harness.
- **One strategy.** Every result holds for these exits only. A model that is no better than random here could still matter under other exits. That belongs to the strategy project.
- **R2 and trained contestants.** A signal moved forward comes from a fit that saw later bars. Its effect on one hour's decision is expected to be negligible (that hour is one of tens of thousands of training rows), and it is not corrected.
- **Coins move together.** R2 keeps that dependence and R1 does not, so requiring both guards against it.
- **Late coins.** BNB and HYPE have short Coinbase histories: on Coinbase they start after the lockbox does, so they add no walk-forward trades. They join the final check only, where their streams are shorter than 2D, so they take no part in R2 there.
- **Fees.** The account's rate can change. Each batch records the rate it used.
- **Run time.** Measured in phase B on the sandbox machine (`docs/dev/RUN-LOG-mh-1.md`): batch 1 without the trained contestants took 86 minutes. That is 155 pattern fits in 59 minutes, the trade cache (380,539 replays) in 4, and 10,000 draws of R1 and R2 for 8 contestants in 22. Phase C adds pooled fits: 6 contestants × 18 folds.

## 10. Decisions for the owner

| # | Decision | Recommended |
|---|---|---|
| D1 | Neural DCA in the comparison | Off for every contestant, so the exits are the same for all. The pattern model is also shown with it on |
| D2 | The gate fix (§6) | R1 baseline and per-day score in the trainer's gate; the LLM gate unchanged. Included in the recommendation the owner accepted on 2026-11-06 |
| D3 | Random baselines | A contestant must beat both R1 and R2 |
| D4 | Walk-forward | From 2020-01-01, 12 months before the first fold, 3-month folds, the last 18 months locked (D11) |
| D5 | Pass rule | B = 10,000; Benjamini-Hochberg q = 0.10 as a screen; finalists by Holm at 5% plus the conditions in §5.6; "too few trades to tell" above 50% of random's median |
| D6 | Trees library | scikit-learn's histogram trees (one new dependency, BSD-3-Clause). LightGBM later, only if the trees show something |
| D7 | Batch 1 | As in §7: 14 contestants and the reference |
| D8 | Where it lives | Settings > Training > "Compare models…". Contestants are fixed in code, with no parameter fields on screen |
| D9 | The report run | In a sandbox, on public candles, at 0.50%, with the default trade rules. The owner can repeat it in the app, with the account's rate and their own trade rules; if either differs, that is a different trial |
| D10 | A winner | Not wired into trading by this spec. A passing contestant gets its own spec |
| D11 | R2 on the lockbox (found in phase B) | **Decided by the owner, 2026-11-06: an 18-month lockbox**, so R1 and R2 are both drawn on it. (R2 needs a stream of at least 2D, 320 days; 6 months was too short. The alternative offered was R1 only.) |
| D12 | Amendment 1 (FDS-SIG-004 Appendix A) | **Accepted by the owner, 2026-11-07.** Batch 1 is unchanged; batch PV-1 is added (§7a) |

## 11. Out of scope

- Strategies (exits, DCA, sizing): a separate project.
- Wiring any contestant into the runner or the trader.
- Batch 2 models, and PyTorch.
- Shorting; other data (order books, funding rates, on-chain, sentiment); hosted model APIs.
- Changes to the LLM signal gate.

## 12. Acceptance

- **Phase A:** the §8 tests pass; the 13 coins' R1 percentiles match the diagnostic report; the full suite has 0 failures; Black is clean.
- **Phases B and C:**
  - the §8 tests pass;
  - a batch run twice gives identical `results.json`;
  - no harness file names an exchange (`test_exchange_hosts_only_in_connectors.py` passes);
  - amendment 1's tests (§8, phase C) pass, batch 1's byte-identity test included;
  - the full suite has 0 failures.
- **Phase D:**
  - a screenshot of the window;
  - every option reachable from Settings;
  - facts-only text.
- **Phase E:** the report, its frozen batch file and the trial log are committed before any lockbox is opened.
