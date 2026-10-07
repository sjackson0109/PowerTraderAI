# Backtest report — trained pattern model (STRAT-003), model 1

**Status: pre-declared header only.** Everything below was written and committed before any backtest of STRAT-003 was
run (FDS-MDL section 10: the declared settings and the verdict rule in their own commit before Test A; here `51e499e`
and the owner's amendment on top of it, both before Test A and neither changing code). No result has been seen.
`docs/dev/run_backtest_model1.py report` will append the results under this header, and must not change it.

**Amended 2026-10-07 in its own commit on top of `51e499e`, still before any backtest,** after the owner's review of
that commit: the owner confirmed the interpretations below as written; each combination's Test B median is shown
beside the pooled one, for information only; the last Test B window's 1h and 4h coverage is confirmed; the random
baseline's seeds are fixed and recorded; and two counts for the legacy-runner quirks E1 and E2 are added to the
output, with E2 flagged in the verdict line if it is not zero.

Specs: `docs/dev/specs/FDS-MDL-trained-model-strategy.md` section 7, as amended by
`docs/dev/specs/FDS-MDL-A-addendum-after-108a.md` (the addendum wins on conflict). Strategy: STRAT-003
(`app/strategies/model_strategy.py`, FDS-MDL Phase 3). Model: the pattern trainer `app/pt_pattern_trainer.py`
(the port of upstream `ba62130`, FDS-MDL Phase 1), whose models are published with manifests (FDS-MDL Phase 2).

## Declared before any result is seen

A **combination** is a symbol and a primary timeframe (four of them); a **run** is a combination with an overlay set.

### Data

- **Symbols and timeframes:** BTCUSDT and ETHUSDT; primary (traded) timeframes 1h and 4h.
- **Window:** 2023-01-01 00:00 to 2026-10-01 00:00 UTC (end exclusive; the last 1h bar opens 2026-09-30 23:00), as
  batch 1.
- **Same candles as batch 1, verified by SHA-256.** `run_backtest_model1.py fetch` fetches the window, all seven
  timeframes, from Binance's public klines into the scratch home's candle cache, which is empty when the first `fetch`
  starts (so each file holds exactly the window). Each 1h and 4h file must hash to batch 1's value:

  | Symbol | TF | SHA-256 of the cached file (batch 1) |
  |---|---|---|
  | BTCUSDT | 1h | `7171bc667f3db6032a721770c6128545b2bc3f089432e8861181034493171893` |
  | BTCUSDT | 4h | `f58fee86fa7e7c6aa69096b75ddeb3156a592c9f55059383da7d95506266836f` |
  | ETHUSDT | 1h | `2bd3369c64bc6ce400ba5d91519c68524ae0cc4a41d8f139ad46eb256e3d4eb8` |
  | ETHUSDT | 4h | `11c6946a168f25bb96d2f6b6415db9990c3a53b70c1585864cd3ab8f5dce8722` |

  If any differs, nothing is scored: the run stops and the report records the mismatch. No other data is substituted.
- **The model's other timeframes** (2h, 8h, 12h, 1d, 1w) are not in batch 1. Their SHA-256 values are recorded in the
  report (there is nothing in batch 1 to compare them with).
- **No silent gaps.** STRAT-003 holds, with a reason, when it cannot apply its rule: `BARS_MISSING:<tf>` (the bar it
  needs is missing), `TIMEFRAME_UNKNOWN` (the strategy was never given its timeframe; it cannot occur in
  `run_backtest`, which always sets it) and `BOUNDS_NOT_CONVERGED` (the gap pass has not ended after 100,000 steps; on
  two zero bounds the legacy runner loops for ever). Each is counted per window from the runner's decision reasons in
  the runs without overlays (where a hold's reason is passed through unchanged; `RunResult.bars_missing` counts only
  `BARS_MISSING`), and reported.
  - A `BARS_MISSING` or `TIMEFRAME_UNKNOWN` hold is a data or set-up problem, not a result: a combination with one in its
    Test A out-of-sample window counts as not meeting criterion 1 below, and one in any Test B window fails criterion
    3. Whatever the verdict, the verdict line then ends (before the E2 note, if any) with "(not assessable: *k*
    decisions held for missing bars or an unknown timeframe: *combination*, *window*, *count*; …)", listing each
    window that has one.
  - A `BOUNDS_NOT_CONVERGED` hold is the strategy's own decision (Phase 3 design): reported, and it does not by itself
    change the verdict. Any at all are flagged in the verdict line (E2, below).
  - The only gap known when this was written: the 1h bar of 2023-03-24 13:00 is missing on both symbols. It is batch 1's
    one missing hourly bar (32,855 of 32,856), and it precedes every scored window. In the scratch candle cache of
    Phases 1-2 (2023-01-01 to 2025-12-31) the 2h to 1w bars have none.

### Costs, fills, sizing and KPIs (as batch 1)

10 bps fee and 5 bps slippage on every fill; 100% of equity per entry; long-only spot; $10,000 start. A signal on a
closed bar fills at the next bar's open; a position still open on the last bar is closed at that bar's close, with
costs. Benchmark: buy-and-hold over the identical window, one buy at the first tradable open and one sell at the last
close, with the same costs. Sharpe and Sortino are annualised per bar, risk-free rate 0. *vs buy-and-hold* is the
strategy's total return minus buy-and-hold's, in percentage points.

### Overlay sets (as batch 1)

None, and `OVL-ATR` + `OVL-COOLDOWN` at their defaults.

### Model and strategy parameters

- **Trainer:** its defaults, seed 0. **Nothing is tuned on anything.** Every training window starts at 2023-01-01
  00:00 UTC (the data start), not at the trainer's default of 1,095 days before its end; each ends where the test
  below says, exclusive (the trainer reads only bars closed by `train_end`).
- **STRAT-003:** its catalogue defaults, `min_tf_agree` 3 and all seven timeframes counted, with the legacy runner's
  rule as Phase 3 reproduces it. A decision at the close of bar *t* uses each timeframe's last bar closed strictly
  before *t*, and the close of bar *t* as the current price. EXIT on SHORT on the traded timeframe; otherwise ENTER on
  at least 3 LONG timeframes and no SHORT one. The runner's 14-day freshness gate does not apply (a fixed model is
  scored on later bars by design).
- **Every model used** is published with its manifest; the manifests are copied into `docs/dev/backtest-model-1/`.
- **A failed training:** if any of the 20 trainings (2 for Test A, 18 for Test B) fails, nothing is scored until the
  cause is fixed under the code rule below. A model whose validation is unavailable is scored; its values in the
  verdict line read "n/a" with the reason.

### Code

- **The frozen code** is every tracked file under `app/` plus `docs/dev/run_backtest_model1.py`. Before Test A runs, a
  freeze commit (after this header's commits) adds the Phase 4 code: the random baseline with its acceptance-8 test,
  `run` and `report`, STRAT-003's per-timeframe activity indicator (for E1, below), and `fetch` and `train` set to
  this window and these 20 trainings (today the script has `fetch`
  and `train` only, with defaults 2023-01-01 to 2026-01-01 and one window per symbol).
- Every result JSON records the commit it was produced from and whether any frozen file differed from it. Every
  manifest records the trainer's commit and state (`trainer_git_commit`, `trainer_git_dirty`) and its code hashes
  (`code_sha256`).
- **A change after a result has been seen** is made only to fix a defect, which the report names. Every step from the
  first one the change affects is then re-run with the final code: all 20 trainings and everything after them if the
  trainer, `pattern_model.py` or `model_store.py` changed. The verdict is computed only from the final code's results;
  the earlier results and the verdict they gave are reported beside them, with what changed and why.

### Test A: single split (comparable with batch 1)

- **One model per symbol, trained on 2023-01-01 00:00 to 2025-08-16 04:00 UTC.** Batch 1's split is 70% of the bars of
  each timeframe: its out-of-sample windows start at 2025-08-16 07:00 (1h) and 2025-08-16 04:00 (4h). Ending the
  training at the earlier of the two keeps every out-of-sample bar of both timeframes at or after `train_end`, which
  `LOOKAHEAD_MODEL` accepts, so one model per symbol serves both. The 1h bars of 04:00 to 06:00 are neither trained on
  nor scored.
- **Scored:** batch 1's out-of-sample windows, to the end of the data, with the full KPI set (total return, CAGR, max
  drawdown, Sharpe, Sortino, trade count, win rate, average trade, exposure, fees, vs buy-and-hold) and buy-and-hold.
- **In-sample:** FDS-MDL asks for in-sample results too, but its lookahead guard, which "applies to every run",
  refuses to score bars a model was trained on (`LOOKAHEAD_MODEL`). The in-sample windows are therefore reported as
  refused, with buy-and-hold for reference. No other model is trained to fill them in.

### Test B: walk-forward

- **Expanding windows, per symbol:** nine models, each trained from 2023-01-01 to the first day of a quarter's first
  month (2024-07-01, 2024-10-01, 2025-01-01, 2025-04-01, 2025-07-01, 2025-10-01, 2026-01-01, 2026-04-01, 2026-07-01:
  "everything up to the end of month *m*", the first *m* being 2024-06). Each model scores the bars that open in
  [`train_end`, `train_end` + 3 calendar months). The last window, July to September 2026, ends with the data.
- **Scored** per run; each window has a fresh runner (overlay state reset) and starts flat, and the bars before it are
  decision history only, never traded. Buy-and-hold over the same bars.
- **Reported:** every window; per run the median and the worst window of *vs buy-and-hold*; and, for criterion 3, the
  median and the worst window over all 36 windows without overlays, pooled. Beside the pooled median, for information
  only: each combination's median over its 9 windows without overlays (the per-run medians above).
- **The last window's 1h and 4h bars are covered.** Batch 1's 1h and 4h files reach the end of July to September 2026:
  batch 1's records (`docs/dev/backtest-batch-1/*.json`, `data`) give their last bars as 2026-09-30 23:00 (1h) and
  20:00 (4h), and their only gap as the 1h bar of 2023-03-24 13:00. Checked on 2026-10-07 against the files batch 1
  read (`app/hub_data/candles/` in the main checkout, read only): in July to September 2026 each symbol has 2,208 1h
  bars and 552 4h bars, the full count. Three of those files still hash to batch 1's values. The BTCUSDT 1h file has
  since been extended by 37 bars past the data window; its header and rows before 2026-10-01 00:00, bytes as stored,
  still hash to batch 1's value. The fetched 1h and 4h files must match these hashes, so they hold the same bars.
  No Test B window is dropped or shortened for coverage: all 9 windows of every combination are scored. The 2h to 1w
  bars are not in batch 1; a decision held because one is missing, in any window, follows "No silent gaps" above,
  verdict-line note included.

### Control: random-entry baseline

- For each run: 100 random-entry strategies on Test A's out-of-sample bars, with the same costs, sizing and overlays.
  Each seed has a fresh runner (overlay state reset) and starts flat.
- **Seeds, fixed:** the integers 0, 1, 2, …, 99 (FDS-MDL section 7's "seeds 0 to 99"), the same 100 for every run
  (each combination with each overlay set). In each run, seed *s* gets a fresh `random.Random(s)`, which nothing else
  draws from. A placement depends only on the seed, *L*, *N* and *H*, so runs with the same *L*, *N* and *H* draw the
  same 100 placements: BTC and ETH have the same *L* at each timeframe (9,857 1h bars and 2,465 4h bars, batch 1's
  out-of-sample windows), and so do a combination's two overlay sets. Each run is still scored on its own prices.
- **Reproducible:** the results record the CPython version and, for every seed, its drawn entry bars (with overlays,
  also which of them were skipped), trade count and total return, in `docs/dev/backtest-model-1/`. Python guarantees
  `random()`'s sequence for a seed across versions, not `sample()`'s, which has two code paths. So the acceptance-8
  test pins seed 0's placement on each path, (*L*, *N*, *H*) = (2,465, 500, 3) for the pool path and (9,857, 100, 20)
  for the set path, and `report` re-derives every run's recorded entry bars from its seeds and asserts they match. If a
  later Python draws differently, those checks fail, and the recorded entry bars, not new draws, are the control.
- **Matching:** *N* is STRAT-003's trade count in that run (the KPI `trade_count`, which includes a position closed on
  the last bar) and *H* the mean of its trades' `bars_held` (all of them, that one included), rounded to the nearest
  bar, halves up, at least 1. With *L* the window's bars, numbered from 0: if *N*(*H* + 1) > *L* − 1, *H* is reduced one
  bar at a time until it is not, and the report says so; if it is still greater at *H* = 1, the run has no baseline
  (flagged), and without overlays that combination fails criterion 2.
- **Placement:** with *S* = *L* − 1 − *N*(*H* + 1), `rng = random.Random(seed)` and
  *c* = `sorted(rng.sample(range(S + N), N))`, the *k*-th trade (*k* from 1) enters at the open of bar
  1 + *c*<sub>*k*</sub> + (*k* − 1)·*H* and exits at the open of the bar *H* bars later (the strategy signals ENTER and
  EXIT at the closes before; the engine fills at the next open). Every placement of *N* non-overlapping trades of *H*
  bars that fit in the window is equally likely.
- **With overlays,** an entry an overlay blocks (`OVL-COOLDOWN`) is skipped, not deferred, and after an overlay exit
  (`OVL-ATR`) the next entry is the next drawn one.
- **Trade counts:** without overlays every seed makes exactly *N* trades by construction; with overlays a seed can make
  fewer. Every seed's count is reported; a seed outside *N* ± 10% (acceptance 8) is flagged and kept, not redrawn.
- **Percentile:** STRAT-003's out-of-sample total return ranked among the 100 seeds' returns: 100 × (seeds below it +
  half the seeds equal to it) / 100. "At or above the 95th percentile" means a rank of at least 95.
- A run in which STRAT-003 made no trade (*N* = 0) has no baseline; without overlays, that combination fails
  criterion 2.

### Verdict rule (FDS-MDL section 7, declared in advance)

Report **"evidence of an edge"** only if all three hold:

1. **Test A, out of sample, no overlays:** STRAT-003 beats buy-and-hold (its total return is strictly higher:
   *vs buy-and-hold* > 0, as batch 1 counted it) in at least 3 of the 4 combinations.
2. **In those same combinations** (every combination that meets 1): STRAT-003's rank in its random-entry baseline (no
   overlays) is at least 95.
3. **Test B, no overlays:** the median *vs buy-and-hold* over all 36 windows (2 symbols × 2 timeframes × 9 windows; the
   mean of the 18th and 19th values) is above 0. Each combination's own median over its 9 windows is shown beside it,
   for information only: those four medians do not enter the verdict.

Otherwise report **"no evidence of an edge."** The runs with overlays are reported but do not enter the verdict. The
generator asserts the verdict against the numbers before printing it, as batch 1 did.

### The verdict line and TRAINER-AUDIT 11.8

The three criteria are FDS-MDL's, with the interpretations listed below. `TRAINER-AUDIT.md` 11.8 found that the
trainer's held-out direction calls show **no skill above the up-rate base rate** (1-hour hit rate against the share of
closes that rose, BTC 50.3% vs 50.4%, ETH 51.3% vs 51.0%, n = 5,257 pairs each). That finding goes into the verdict line
itself, next to the verdict, whichever verdict it is, with the base rate and the held-out score side by side with the
sample size. The line is, with *V* the verdict and the bracketed values filled in by the generator:

> ***V*; in TRAINER-AUDIT 11.8 the trainer's held-out direction calls showed no skill above the up-rate base rate:**
> 1-hour hit rate vs share of closes that rose, BTC 50.3% vs 50.4% and ETH 51.3% vs 51.0% (n = 5,257 pairs each).
> Held-out metrics in Test A's manifests (a separate fit on the first 80% of each training window, scored on the last
> 20%, 2025-02-05 12:00 to 2025-08-16 04:00): BTC [hit]% vs [up]% (n = [n]), ETH [hit]% vs [up]% (n = [n]).

- The values come from `validation_metrics["1hour"]` (`direction_hit_rate`, `up_share_of_considered`,
  `direction_considered`): fractions × 100 to one decimal, n as an integer. If a manifest's `validation.status` is not
  `ok`, or a value is missing, its place reads "n/a (*reason*)", the reason being `validation.reason`, else
  `validation_metrics["1hour"]["error"]`.
- The generator asserts that each Test A manifest's `validation.holdout_start` and `holdout_end` are the dates in the
  line (the trainer splits the span its 1-hour bars cover, so different bars would move them).
- The second sentence gives those numbers as they are; it makes no claim of its own, and the generator does not choose
  its wording from them.
- The report also shows the same three values for every model used (Test A and Test B), side by side.
- Whatever the verdict, the line then ends with the "not assessable" note of "No silent gaps" when that applies, and
  then with the E2 note below when the gap-pass limit triggered at all.
- 11.8's held-out bars (2025-05-26 19:00 to 2026-01-01) overlap Test A's out-of-sample window. Nothing in this header
  was chosen from them: the criteria are FDS-MDL's, the windows and costs batch 1's, and the parameters the trainer's
  defaults.

### Interpretations of FDS-MDL's wording (confirmed by the owner as written, 2026-10-07)

1. **In-sample results are reported as refused** (FDS-MDL's Test A asks for them; its lookahead guard refuses them).
2. **Test A uses one model per symbol, trained to 04:00,** the earlier of batch 1's two split times (FDS-MDL: "the same
   split timestamp as batch 1"; batch 1 has one per timeframe). The alternative is two models per symbol.
3. **Criterion 3 is the median of the 36 windows without overlays, pooled.** FDS-MDL says "the median walk-forward
   window beats buy-and-hold". Alternatives: each combination's median above 0, or all 72 windows including overlays.
4. **"Beats" means strictly greater**, and criterion 2 is read literally: every combination that meets criterion 1
   must also rank at least 95.
5. **Holds:** missing bars fail the criterion their window feeds; `BOUNDS_NOT_CONVERGED` holds are reported only.
6. **The random baseline:** the matching and placement above; "at or above the 95th percentile" as a mid-rank of at
   least 95 (ties count half); and acceptance 8's ±10% (FDS-MDL: "matches trade count to within ±10%") met exactly
   without overlays and flagged, not enforced, with overlays, where blocked entries are skipped.
7. **TRAINER-AUDIT 11.8 enters the verdict line** with its numbers and Test A's, not as a fourth criterion.

They were confirmed in the owner's review of `51e499e`. Any later change to this header is made before Test A runs, in
a commit of its own; none is made once Test A has started. The report cites every header commit (`51e499e` and each
one after it).

### Two legacy-runner quirks, counted (E1, E2)

STRAT-003 reproduces the legacy runner on purpose, including two quirks found in Phase 3 (`docs/dev/RUN-LOG-model-1.md`,
Phase 3 section) and drafted as issues E1 and E2 in `docs/dev/ISSUE-DRAFTS-model-1.md`, in the same commit as this
amendment. Neither changes the rule. Both are counted per combination, for Test A's
out-of-sample window and for Test B (its 9 windows together, and each window in the window table), from the runs
without overlays (STRAT-003's own signals do not depend on the overlay set):

- **E1, the remap shift:** the decisions in which two or more of the timeframes before 1week (1hour, 2hour, 4hour,
  8hour, 12hour, 1day) were inactive at once, that is, their predictions were not active and they carried the
  placeholder bounds. In those decisions the runner's remap gives later timeframes a neighbour's bounds and 1week a
  placeholder. Reported as a count and as a share of the window's decisions: one at each bar's close except the
  window's last bar, where the engine decides nothing (*L* − 1 per window; for Test B, summed over its 9 windows). A
  decision held for a missing bar is held before all seven predictions are made: it counts among the decisions, never
  as E1. A `BOUNDS_NOT_CONVERGED` hold has all seven predictions and counts as E1 when the condition holds.
- **E2, the gap-pass limit:** the decisions in which the 100,000-step limit triggered (held `BOUNDS_NOT_CONVERGED`).
  Expected zero. If it is above zero anywhere, the verdict line ends, whatever the verdict and after any "not
  assessable" note, with "(gap-pass limit reached on *k* decisions: *combination*, *test*, *count*; …)".

For E1, STRAT-003 reports each timeframe's activity with every decision that made all seven predictions
(`BOUNDS_NOT_CONVERGED` holds included). That indicator is added in the freeze commit and changes no decision.

### Also reported

A short side-by-side table with STRAT-001 and STRAT-002 from batch 1, taken from the existing batch-1 JSON (not re-run).

### Outputs and reproduction

- This file.
- `docs/dev/backtest-model-1/`: JSON KPIs per run, trades CSVs, the random-baseline distributions and the manifests of
  every model used.
- `docs/dev/run_backtest_model1.py fetch|train|run|report`, every run with `POWERTRADER_HOME` set to the session's
  scratch folder outside the repo (recorded in `docs/dev/RUN-LOG-model-1.md`); `fetch` is the only step that uses the
  network (public klines).

---

*Results go below this line.*
