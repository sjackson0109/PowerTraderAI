# Backtest report — trained pattern model (STRAT-003), model 1

**Status: pre-declared header only.** Everything below was written and committed before any backtest of STRAT-003 was
run (FDS-MDL section 10: the declared settings and the verdict rule in their own commit before Test A; here `51e499e`
and the owner's amendments after it, all before Test A and none changing code). No result has been seen.
`docs/dev/run_backtest_model1.py report` will append the results under this header, and must not change it.

**Amended 2026-10-07 in its own commit on top of `51e499e`, still before any backtest,** after the owner's review of
that commit: the owner confirmed the interpretations below as written; each combination's Test B median is shown
beside the pooled one, for information only; the last Test B window's 1h and 4h coverage is confirmed; the random
baseline's seeds are fixed and recorded; and two counts for the legacy-runner quirks E1 and E2 are added to the
output, with E2 flagged in the verdict line if it is not zero.

**Amended again 2026-10-07, in its own commit, still before any backtest,** after the owner approved `d36cdf1` with
one change: each combination draws its random baseline from its own range of seeds (a departure from FDS-MDL section
7's literal "seeds 0 to 99"; see the Control section). Also: every fetched candle file's SHA-256 is recorded in the
results, so the run can be repeated on the same data; E1 and E2 are filed as #152 and #153.

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
- **The model's other timeframes** (2h, 8h, 12h, 1d, 1w) are not in batch 1, so there is no hash to check them
  against. `fetch` records every fetched file's SHA-256 (all seven timeframes, both symbols) and `run` checks that each
  file still has it; if any differs, nothing is scored: the run stops and the report records the mismatch, as for
  batch 1's hashes. The results JSON and the report record them all, so the run can be repeated on the same data.
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
  `run` and `report`, STRAT-003's per-timeframe activity indicator (for E1, below), `fetch` recording every fetched
  file's SHA-256, and `fetch` and `train` set to this window and these 20 trainings (today the script has `fetch`
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
- **Seeds, fixed per combination:** BTCUSDT 1h 0 to 99, BTCUSDT 4h 100 to 199, ETHUSDT 1h 200 to 299, ETHUSDT 4h 300
  to 399; a combination's two overlay sets share its range. In each run, seed *s* gets a fresh `random.Random(s)`,
  which nothing else draws from.
- **This departs from FDS-MDL section 7's literal "seeds 0 to 99"** (owner decision, 2026-10-07). A placement depends
  only on the seed, *L*, *N* and *H*, and BTC and ETH have the same *L* at each timeframe (9,857 1h bars and 2,465 4h
  bars, batch 1's out-of-sample windows). With the same seeds, two combinations whose *N* and *H* also matched would
  draw identical placements, and near-identical ones when they were merely close. BTC and ETH prices are correlated,
  so their controls would be near-copies, and the 3-of-4 count (criterion 1, whose combinations must each also pass
  criterion 2, where the control enters) would partly count one control result twice. Separate ranges make the four
  controls independent draws. A combination's two overlay sets score the same bars, so they keep sharing its range.
- **Reproducible:** the results record the CPython version and, for every seed, its drawn entry bars (with overlays,
  also which of them were skipped), trade count and total return, in `docs/dev/backtest-model-1/`. Python guarantees
  `random()`'s sequence for a seed across versions, not `sample()`'s, which has two code paths. So the acceptance-8
  test pins one placement on each path: seed 0 (BTCUSDT 1h's first) with (*L*, *N*, *H*) = (9,857, 100, 20) for the
  set path, and seed 100 (BTCUSDT 4h's first) with (2,465, 500, 3) for the pool path. `report` re-derives every run's
  recorded entry bars from its seeds and asserts they match. If a later Python draws differently, those checks fail,
  and the recorded entry bars, not new draws, are the control.
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
Phase 3 section) and filed as #152 (E1) and #153 (E2), drafted in `docs/dev/ISSUE-DRAFTS-model-1.md`. Neither changes
the rule. Both are counted per combination, for Test A's out-of-sample window and for Test B (its 9 windows together,
and each window in the window table), from the runs without overlays (STRAT-003's own signals do not depend on the
overlay set):

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

## Results

### Known presentation defects

*Added by hand on 2026-10-08, after `report` ran, at the owner's request. The run script did not write this note, and
nothing else below the marker was changed. Neither defect is fixed: either fix would need a change to frozen code and a
superseded re-run (owner decision: leave both).*

- The header's status line ("pre-declared header only … No result has been seen") describes the header as committed
  before Test A; it cannot change. The results follow below.
- **Test B table, "Missing bars" column:** for each window without overlays it shows the BARS_MISSING and
  TIMEFRAME_UNKNOWN holds added together, under a heading that names only missing bars. `results.json` keeps the two
  counts apart for every window, Test A reports them separately, and every count is 0. It affects no number and not the
  verdict. Draft: [ISSUE-DRAFTS-model-1.md, F1](ISSUE-DRAFTS-model-1.md#f1).
- **Manifest copies in `docs/dev/backtest-model-1/manifests/`:** each holds the same JSON as its model's
  `manifest.json` in the model store, but the bytes differ. The copy has CRLF line endings and a trailing newline,
  while the store file has LF line endings and no trailing newline. So a copy's SHA-256 does not equal the store
  file's. `run` compares the parsed content, which is equal for all 20 models, and each model id is derived from
  the identity the manifest records, not from its file bytes. It affects no number and not the verdict. Draft: [ISSUE-DRAFTS-model-1.md, F2](ISSUE-DRAFTS-model-1.md#f2).

- **Code:** commit `68d4ed7426b0b42d06fe5d50256f1ec6db0cbcab`; frozen files changed from it: none. Python 3.13.15. `POWERTRADER_HOME`: `C:\Users\Simon\AppData\Local\Temp\claude\c--Users-Simon-Documents-sjackson0109-PowerTraderAI\57710dd7-ccf3-4fdb-8966-6da8cc28ea84\scratchpad\p4home`. Reported from commit `68d4ed7426b0b42d06fe5d50256f1ec6db0cbcab`.
- **Frozen-code commits after the header** (the freeze commit, and any fix after it): `68d4ed7 2026-10-07 FDS-MDL Phase 4: the freeze commit (random baseline, evaluation, run script)`.
- **Header commits:** `42b0622 2026-10-07 FDS-MDL Phase 4: a seed range per combination; record every candle file's hash`; `d36cdf1 2026-10-07 FDS-MDL Phase 4: amend the rule after the owner's review; draft E1 and E2`; `51e499e 2026-10-07 FDS-MDL Phase 4: pre-declared header and verdict rule`.

### Verdict

***No evidence of an edge*; in TRAINER-AUDIT 11.8 the trainer's held-out direction calls showed no skill above the up-rate base rate:** 1-hour hit rate vs share of closes that rose, BTC 50.3% vs 50.4% and ETH 51.3% vs 51.0% (n = 5,257 pairs each). Held-out metrics in Test A's manifests (a separate fit on the first 80% of each training window, scored on the last 20%, 2025-02-05 12:00 to 2025-08-16 04:00): BTC 50.7% vs 50.5% (n = 4,599), ETH 51.4% vs 51.6% (n = 4,588).

- Criterion 1 (Test A, out of sample, no overlays, at least 3 of 4 beat buy-and-hold): not met; combinations: BTCUSDT 1h.
- Criterion 2 (each of those ranks at least 95 in its random baseline): met.
- Criterion 3 (Test B, no overlays, median of all 36 windows above 0): not met; pooled median -11.94 pp, worst window -67.70 pp.
- For information only (not in the verdict), each combination's Test B median: BTCUSDT 1h -11.67 pp; BTCUSDT 4h -12.20 pp; ETHUSDT 1h -11.67 pp; ETHUSDT 4h -16.95 pp.

### Data

| File | Bars | First | Last | Missing bars | SHA-256 | Batch 1 |
|---|---|---|---|---|---|---|
| BTCUSDT 1h | 32,855 | 2023-01-01T00:00:00+00:00 | 2026-09-30T23:00:00+00:00 | 1 | `7171bc667f3db6032a721770c6128545b2bc3f089432e8861181034493171893` | same |
| BTCUSDT 2h | 16,428 | 2023-01-01T00:00:00+00:00 | 2026-09-30T22:00:00+00:00 | 0 | `98d9ea257b4585b1390be71d797ddcb36017fee336ec8c742f7c66fed2a258d4` | — |
| BTCUSDT 4h | 8,214 | 2023-01-01T00:00:00+00:00 | 2026-09-30T20:00:00+00:00 | 0 | `f58fee86fa7e7c6aa69096b75ddeb3156a592c9f55059383da7d95506266836f` | same |
| BTCUSDT 8h | 4,107 | 2023-01-01T00:00:00+00:00 | 2026-09-30T16:00:00+00:00 | 0 | `7541ae03416a68487c780d860dfaefc50d3fd1e46ecf029bc58a6c1fb19aa901` | — |
| BTCUSDT 12h | 2,738 | 2023-01-01T00:00:00+00:00 | 2026-09-30T12:00:00+00:00 | 0 | `2a81f99752d3dbe6b666e75113989eba5abc7b2a07b20052e15a949f287b595d` | — |
| BTCUSDT 1d | 1,369 | 2023-01-01T00:00:00+00:00 | 2026-09-30T00:00:00+00:00 | 0 | `5059b561afcab3f423ac20690d787bc156a2742554e34894352912084f00c01f` | — |
| BTCUSDT 1w | 195 | 2023-01-02T00:00:00+00:00 | 2026-09-21T00:00:00+00:00 | 0 | `4bc1b4ba5223b9025a5a33946fe8c3f4d9e4ee79f7766d51f1602a25668aebe8` | — |
| ETHUSDT 1h | 32,855 | 2023-01-01T00:00:00+00:00 | 2026-09-30T23:00:00+00:00 | 1 | `2bd3369c64bc6ce400ba5d91519c68524ae0cc4a41d8f139ad46eb256e3d4eb8` | same |
| ETHUSDT 2h | 16,428 | 2023-01-01T00:00:00+00:00 | 2026-09-30T22:00:00+00:00 | 0 | `fd83f0d04d41b47ba0511bf8391f591efeb422917772fbacfbd4274031cdb811` | — |
| ETHUSDT 4h | 8,214 | 2023-01-01T00:00:00+00:00 | 2026-09-30T20:00:00+00:00 | 0 | `11c6946a168f25bb96d2f6b6415db9990c3a53b70c1585864cd3ab8f5dce8722` | same |
| ETHUSDT 8h | 4,107 | 2023-01-01T00:00:00+00:00 | 2026-09-30T16:00:00+00:00 | 0 | `4fd49328d0353fcde511088205f843238948934cd5be9d90a0f9943670b695d7` | — |
| ETHUSDT 12h | 2,738 | 2023-01-01T00:00:00+00:00 | 2026-09-30T12:00:00+00:00 | 0 | `806103bb90b84e29260871f29c9147ee985fb1d0903b56588e260a72b0e7dc61` | — |
| ETHUSDT 1d | 1,369 | 2023-01-01T00:00:00+00:00 | 2026-09-30T00:00:00+00:00 | 0 | `2a84ae4e9bb50dd7543f28b78310781767e59ff60372b50efd323ed6fa5eb885` | — |
| ETHUSDT 1w | 195 | 2023-01-02T00:00:00+00:00 | 2026-09-21T00:00:00+00:00 | 0 | `241b92e287143f7f65207b18b14b935bc647a94633757814a82061bf1d6393bc` | — |

### Models

| Test | Model | Window | Held-out 1h hit rate | Up share | n | Validation |
|---|---|---|---|---|---|---|
| A | `BTC-20250816T0400Z-5d85edd38e43` | 2023-01-01T00:00:00Z .. 2025-08-16T04:00:00Z | 50.7% | 50.5% | 4,599 | ok |
| B | `BTC-20240701T0000Z-9766305cd89c` | 2023-01-01T00:00:00Z .. 2024-07-01T00:00:00Z | 49.7% | 50.6% | 2,619 | ok |
| B | `BTC-20241001T0000Z-abf9b82c91dc` | 2023-01-01T00:00:00Z .. 2024-10-01T00:00:00Z | 50.9% | 50.0% | 3,062 | ok |
| B | `BTC-20250101T0000Z-0f00a5b7e4cd` | 2023-01-01T00:00:00Z .. 2025-01-01T00:00:00Z | 50.7% | 51.4% | 3,503 | ok |
| B | `BTC-20250401T0000Z-60ba79990e0c` | 2023-01-01T00:00:00Z .. 2025-04-01T00:00:00Z | 51.3% | 51.5% | 3,937 | ok |
| B | `BTC-20250701T0000Z-d1d15c03212f` | 2023-01-01T00:00:00Z .. 2025-07-01T00:00:00Z | 51.3% | 50.3% | 4,376 | ok |
| B | `BTC-20251001T0000Z-5a4c3794f1f0` | 2023-01-01T00:00:00Z .. 2025-10-01T00:00:00Z | 50.1% | 50.3% | 4,817 | ok |
| B | `BTC-20260101T0000Z-bbaa39a08dfa` | 2023-01-01T00:00:00Z .. 2026-01-01T00:00:00Z | 50.3% | 50.4% | 5,257 | ok |
| B | `BTC-20260401T0000Z-f4a4594d192b` | 2023-01-01T00:00:00Z .. 2026-04-01T00:00:00Z | 49.5% | 49.8% | 5,689 | ok |
| B | `BTC-20260701T0000Z-f57e4910b34a` | 2023-01-01T00:00:00Z .. 2026-07-01T00:00:00Z | 50.7% | 49.6% | 6,127 | ok |
| A | `ETH-20250816T0400Z-6ce59ce7a360` | 2023-01-01T00:00:00Z .. 2025-08-16T04:00:00Z | 51.4% | 51.6% | 4,588 | ok |
| B | `ETH-20240701T0000Z-1d37993cacce` | 2023-01-01T00:00:00Z .. 2024-07-01T00:00:00Z | 51.8% | 50.2% | 2,621 | ok |
| B | `ETH-20241001T0000Z-91d236f2f788` | 2023-01-01T00:00:00Z .. 2024-10-01T00:00:00Z | 52.0% | 49.6% | 3,059 | ok |
| B | `ETH-20250101T0000Z-8210ec3df6be` | 2023-01-01T00:00:00Z .. 2025-01-01T00:00:00Z | 51.6% | 50.5% | 3,500 | ok |
| B | `ETH-20250401T0000Z-e88dc9d7b9f3` | 2023-01-01T00:00:00Z .. 2025-04-01T00:00:00Z | 50.5% | 50.6% | 3,931 | ok |
| B | `ETH-20250701T0000Z-5ec3069687c7` | 2023-01-01T00:00:00Z .. 2025-07-01T00:00:00Z | 50.9% | 51.1% | 4,362 | ok |
| B | `ETH-20251001T0000Z-9b4e1e5eb974` | 2023-01-01T00:00:00Z .. 2025-10-01T00:00:00Z | 51.3% | 51.3% | 4,810 | ok |
| B | `ETH-20260101T0000Z-20796d245c44` | 2023-01-01T00:00:00Z .. 2026-01-01T00:00:00Z | 51.3% | 51.0% | 5,257 | ok |
| B | `ETH-20260401T0000Z-c535fb7f5059` | 2023-01-01T00:00:00Z .. 2026-04-01T00:00:00Z | 50.8% | 49.9% | 5,689 | ok |
| B | `ETH-20260701T0000Z-9858650537ee` | 2023-01-01T00:00:00Z .. 2026-07-01T00:00:00Z | 50.4% | 49.6% | 6,125 | ok |

### Test A: out of sample

#### BTCUSDT 1h: 2025-08-16T07:00 to 2026-09-30T23:00 (9,857 bars)

| Run | total ret | CAGR | max DD | Sharpe | Sortino | trades | win rate | avg trade | exposure | fees | vs B&H (pp) | Baseline rank |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| STRAT-003, no overlays | -15.03% | -13.49% | -47.06% | -0.36 | -0.51 | 101 | 54.46% | -0.12% | 45.4% | $1,526 | 13.95 | 95.0 |
| STRAT-003, OVL-ATR + OVL-COOLDOWN | -22.49% | -20.27% | -37.51% | -1.08 | -1.50 | 115 | 41.74% | -0.20% | 21.9% | $1,752 | 6.49 | 78.0 |
| **Buy-and-hold** | -28.98% | -26.24% | -53.74% | -0.50 | -0.70 | 1 | 0.00% | -28.98% | 100.0% | $17 | — | — |

- Random baseline, none: N = 101, H = 44; seeds 0-99, trade counts 101-101, flagged (outside N ± 10%): none.
- Random baseline, OVL-ATR+OVL-COOLDOWN: N = 115, H = 19; seeds 0-99, trade counts 103-114, flagged (outside N ± 10%): [74].
- Without overlays: holds for missing bars 0, unknown timeframe 0, gap-pass limit 0; E1 12 of 9856 decisions (0.1%), E2 0.
- In-sample 2023-01-01 to 2025-08-16 (22,998 bars): refused (LOOKAHEAD_MODEL: model BTC-20250816T0400Z-5d85edd38e43 was trained on bars up to 2025-08-16 04:00:00+00:00, after the first scored bar (2023-01-01 00:00:00+00:00); score only bars that open at or after the end of the model's training window); buy-and-hold 607.56%.

#### BTCUSDT 4h: 2025-08-16T04:00 to 2026-09-30T20:00 (2,465 bars)

| Run | total ret | CAGR | max DD | Sharpe | Sortino | trades | win rate | avg trade | exposure | fees | vs B&H (pp) | Baseline rank |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| STRAT-003, no overlays | -34.91% | -31.73% | -39.75% | -1.42 | -1.86 | 77 | 55.84% | -0.50% | 30.8% | $1,260 | -5.90 | 26.0 |
| STRAT-003, OVL-ATR + OVL-COOLDOWN | -18.02% | -16.19% | -23.19% | -0.83 | -1.14 | 65 | 53.85% | -0.28% | 21.2% | $1,153 | 10.99 | 55.0 |
| **Buy-and-hold** | -29.00% | -26.25% | -53.45% | -0.53 | -0.73 | 1 | 0.00% | -29.00% | 100.0% | $17 | — | — |

- Random baseline, none: N = 77, H = 10; seeds 100-199, trade counts 77-77, flagged (outside N ± 10%): none.
- Random baseline, OVL-ATR+OVL-COOLDOWN: N = 65, H = 8; seeds 100-199, trade counts 48-61, flagged (outside N ± 10%): [100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 117, 119, 120, 121, 122, 123, 124, 125, 126, 127, 128, 129, 130, 131, 132, 133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146, 147, 148, 149, 150, 151, 152, 153, 154, 155, 157, 158, 159, 160, 161, 162, 163, 164, 165, 166, 167, 168, 169, 170, 171, 172, 173, 174, 175, 176, 177, 178, 179, 180, 181, 182, 183, 184, 185, 186, 187, 188, 189, 190, 191, 192, 193, 194, 195, 196, 197, 198, 199].
- Without overlays: holds for missing bars 0, unknown timeframe 0, gap-pass limit 0; E1 3 of 2464 decisions (0.1%), E2 0.
- In-sample 2023-01-01 to 2025-08-16 (5,749 bars): refused (LOOKAHEAD_MODEL: model BTC-20250816T0400Z-5d85edd38e43 was trained on bars up to 2025-08-16 04:00:00+00:00, after the first scored bar (2023-01-01 00:00:00+00:00); score only bars that open at or after the end of the model's training window); buy-and-hold 607.77%.

#### ETHUSDT 1h: 2025-08-16T07:00 to 2026-09-30T23:00 (9,857 bars)

| Run | total ret | CAGR | max DD | Sharpe | Sortino | trades | win rate | avg trade | exposure | fees | vs B&H (pp) | Baseline rank |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| STRAT-003, no overlays | -59.74% | -55.47% | -71.57% | -2.03 | -2.68 | 175 | 51.43% | -0.49% | 33.5% | $1,916 | -20.34 | 24.0 |
| STRAT-003, OVL-ATR + OVL-COOLDOWN | -59.32% | -55.06% | -64.23% | -2.80 | -3.63 | 168 | 44.05% | -0.51% | 19.6% | $2,016 | -19.92 | 4.0 |
| **Buy-and-hold** | -39.40% | -35.95% | -69.15% | -0.44 | -0.62 | 1 | 0.00% | -39.40% | 100.0% | $16 | — | — |

- Random baseline, none: N = 175, H = 19; seeds 200-299, trade counts 175-175, flagged (outside N ± 10%): none.
- Random baseline, OVL-ATR+OVL-COOLDOWN: N = 168, H = 12; seeds 200-299, trade counts 141-156, flagged (outside N ± 10%): [200, 201, 202, 203, 204, 205, 206, 207, 209, 211, 212, 213, 214, 215, 216, 217, 218, 219, 220, 222, 223, 224, 225, 226, 228, 229, 230, 231, 234, 237, 238, 239, 240, 241, 243, 244, 245, 246, 247, 248, 250, 251, 252, 254, 255, 256, 257, 259, 260, 261, 262, 263, 264, 265, 266, 267, 268, 269, 270, 271, 272, 274, 275, 276, 277, 278, 280, 281, 282, 283, 284, 287, 288, 289, 290, 291, 293, 294, 295, 296, 298, 299].
- Without overlays: holds for missing bars 0, unknown timeframe 0, gap-pass limit 0; E1 28 of 9856 decisions (0.3%), E2 0.
- In-sample 2023-01-01 to 2025-08-16 (22,998 bars): refused (LOOKAHEAD_MODEL: model ETH-20250816T0400Z-6ce59ce7a360 was trained on bars up to 2025-08-16 04:00:00+00:00, after the first scored bar (2023-01-01 00:00:00+00:00); score only bars that open at or after the end of the model's training window); buy-and-hold 268.35%.

#### ETHUSDT 4h: 2025-08-16T04:00 to 2026-09-30T20:00 (2,465 bars)

| Run | total ret | CAGR | max DD | Sharpe | Sortino | trades | win rate | avg trade | exposure | fees | vs B&H (pp) | Baseline rank |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| STRAT-003, no overlays | -58.84% | -54.58% | -70.75% | -1.96 | -2.49 | 112 | 50.00% | -0.72% | 33.9% | $1,411 | -19.26 | 10.0 |
| STRAT-003, OVL-ATR + OVL-COOLDOWN | -54.87% | -50.71% | -59.49% | -2.37 | -2.95 | 88 | 47.73% | -0.85% | 23.3% | $1,247 | -15.29 | 8.0 |
| **Buy-and-hold** | -39.58% | -36.11% | -68.03% | -0.45 | -0.63 | 1 | 0.00% | -39.58% | 100.0% | $16 | — | — |

- Random baseline, none: N = 112, H = 7; seeds 300-399, trade counts 112-112, flagged (outside N ± 10%): none.
- Random baseline, OVL-ATR+OVL-COOLDOWN: N = 88, H = 7; seeds 300-399, trade counts 61-76, flagged (outside N ± 10%): [300, 301, 302, 303, 304, 305, 306, 307, 308, 309, 310, 311, 312, 313, 314, 315, 316, 317, 318, 319, 320, 321, 322, 323, 324, 325, 326, 327, 328, 329, 330, 331, 332, 333, 334, 335, 336, 337, 338, 339, 340, 341, 342, 343, 344, 345, 346, 347, 348, 349, 350, 351, 352, 353, 354, 355, 356, 357, 358, 359, 360, 361, 362, 363, 364, 365, 366, 367, 368, 369, 370, 371, 372, 373, 374, 375, 376, 377, 378, 379, 380, 381, 382, 383, 384, 385, 386, 387, 388, 389, 390, 391, 392, 393, 394, 395, 396, 397, 398, 399].
- Without overlays: holds for missing bars 0, unknown timeframe 0, gap-pass limit 0; E1 7 of 2464 decisions (0.3%), E2 0.
- In-sample 2023-01-01 to 2025-08-16 (5,749 bars): refused (LOOKAHEAD_MODEL: model ETH-20250816T0400Z-6ce59ce7a360 was trained on bars up to 2025-08-16 04:00:00+00:00, after the first scored bar (2023-01-01 00:00:00+00:00); score only bars that open at or after the end of the model's training window); buy-and-hold 269.44%.

### Test B: walk-forward

E1, E2 and missing bars are counted in the runs without overlays (STRAT-003's own signals do not depend on the overlay set).

| Combination | Overlays | Model trained to | Window | vs B&H (pp) | STRAT-003 | Buy-and-hold | Trades | E1 | E2 | Missing bars |
|---|---|---|---|---|---|---|---|---|---|---|
| BTCUSDT 1h | none | 2024-07-01 | 2024-07-01..2024-09-30 | -14.24 | -13.66% | 0.58% | 38 | 24 of 2207 (1.1%) | 0 | 0 |
| BTCUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2024-07-01 | 2024-07-01..2024-09-30 | -12.12 | -11.54% | 0.58% | 35 | — | — | — |
| BTCUSDT 4h | none | 2024-07-01 | 2024-07-01..2024-09-30 | -22.62 | -22.03% | 0.58% | 22 | 6 of 551 (1.1%) | 0 | 0 |
| BTCUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2024-07-01 | 2024-07-01..2024-09-30 | -15.32 | -14.74% | 0.58% | 17 | — | — | — |
| BTCUSDT 1h | none | 2024-10-01 | 2024-10-01..2024-12-31 | -45.68 | 1.64% | 47.32% | 26 | 1 of 2207 (0.0%) | 0 | 0 |
| BTCUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2024-10-01 | 2024-10-01..2024-12-31 | -44.84 | 2.49% | 47.32% | 31 | — | — | — |
| BTCUSDT 4h | none | 2024-10-01 | 2024-10-01..2024-12-31 | -57.05 | -9.73% | 47.32% | 18 | 1 of 551 (0.2%) | 0 | 0 |
| BTCUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2024-10-01 | 2024-10-01..2024-12-31 | -61.24 | -13.92% | 47.32% | 13 | — | — | — |
| BTCUSDT 1h | none | 2025-01-01 | 2025-01-01..2025-03-31 | -4.91 | -16.95% | -12.05% | 35 | 0 of 2159 (0.0%) | 0 | 0 |
| BTCUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2025-01-01 | 2025-01-01..2025-03-31 | -2.67 | -14.71% | -12.05% | 39 | — | — | — |
| BTCUSDT 4h | none | 2025-01-01 | 2025-01-01..2025-03-31 | -3.03 | -15.08% | -12.05% | 21 | 0 of 539 (0.0%) | 0 | 0 |
| BTCUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2025-01-01 | 2025-01-01..2025-03-31 | 3.08 | -8.97% | -12.05% | 19 | — | — | — |
| BTCUSDT 1h | none | 2025-04-01 | 2025-04-01..2025-06-30 | -21.24 | 8.17% | 29.41% | 18 | 0 of 2183 (0.0%) | 0 | 0 |
| BTCUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2025-04-01 | 2025-04-01..2025-06-30 | -33.83 | -4.42% | 29.41% | 23 | — | — | — |
| BTCUSDT 4h | none | 2025-04-01 | 2025-04-01..2025-06-30 | -19.06 | 10.35% | 29.41% | 15 | 0 of 545 (0.0%) | 0 | 0 |
| BTCUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2025-04-01 | 2025-04-01..2025-06-30 | -22.13 | 7.27% | 29.41% | 13 | — | — | — |
| BTCUSDT 1h | none | 2025-07-01 | 2025-07-01..2025-09-30 | -11.67 | -5.54% | 6.12% | 7 | 0 of 2207 (0.0%) | 0 | 0 |
| BTCUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2025-07-01 | 2025-07-01..2025-09-30 | -16.71 | -10.59% | 6.12% | 13 | — | — | — |
| BTCUSDT 4h | none | 2025-07-01 | 2025-07-01..2025-09-30 | -12.20 | -6.08% | 6.12% | 10 | 0 of 551 (0.0%) | 0 | 0 |
| BTCUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2025-07-01 | 2025-07-01..2025-09-30 | -17.10 | -10.97% | 6.12% | 7 | — | — | — |
| BTCUSDT 1h | none | 2025-10-01 | 2025-10-01..2025-12-31 | 0.38 | -23.00% | -23.38% | 31 | 0 of 2207 (0.0%) | 0 | 0 |
| BTCUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2025-10-01 | 2025-10-01..2025-12-31 | 7.49 | -15.89% | -23.38% | 33 | — | — | — |
| BTCUSDT 4h | none | 2025-10-01 | 2025-10-01..2025-12-31 | 11.23 | -12.14% | -23.38% | 23 | 0 of 551 (0.0%) | 0 | 0 |
| BTCUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2025-10-01 | 2025-10-01..2025-12-31 | 9.74 | -13.64% | -23.38% | 18 | — | — | — |
| BTCUSDT 1h | none | 2026-01-01 | 2026-01-01..2026-03-31 | 12.60 | -9.73% | -22.33% | 30 | 12 of 2159 (0.6%) | 0 | 0 |
| BTCUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2026-01-01 | 2026-01-01..2026-03-31 | 15.83 | -6.50% | -22.33% | 32 | — | — | — |
| BTCUSDT 4h | none | 2026-01-01 | 2026-01-01..2026-03-31 | -0.78 | -23.10% | -22.33% | 19 | 3 of 539 (0.6%) | 0 | 0 |
| BTCUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2026-01-01 | 2026-01-01..2026-03-31 | 11.88 | -10.45% | -22.33% | 16 | — | — | — |
| BTCUSDT 1h | none | 2026-04-01 | 2026-04-01..2026-06-30 | 27.44 | 13.04% | -14.40% | 26 | 0 of 2183 (0.0%) | 0 | 0 |
| BTCUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2026-04-01 | 2026-04-01..2026-06-30 | 18.97 | 4.57% | -14.40% | 28 | — | — | — |
| BTCUSDT 4h | none | 2026-04-01 | 2026-04-01..2026-06-30 | 1.07 | -13.34% | -14.40% | 15 | 0 of 545 (0.0%) | 0 | 0 |
| BTCUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2026-04-01 | 2026-04-01..2026-06-30 | 12.44 | -1.97% | -14.40% | 14 | — | — | — |
| BTCUSDT 1h | none | 2026-07-01 | 2026-07-01..2026-09-30 | -23.57 | 18.64% | 42.21% | 10 | 0 of 2207 (0.0%) | 0 | 0 |
| BTCUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2026-07-01 | 2026-07-01..2026-09-30 | -29.90 | 12.31% | 42.21% | 15 | — | — | — |
| BTCUSDT 4h | none | 2026-07-01 | 2026-07-01..2026-09-30 | -26.27 | 15.95% | 42.21% | 11 | 0 of 551 (0.0%) | 0 | 0 |
| BTCUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2026-07-01 | 2026-07-01..2026-09-30 | -34.71 | 7.50% | 42.21% | 11 | — | — | — |
| ETHUSDT 1h | none | 2024-07-01 | 2024-07-01..2024-09-30 | -11.67 | -36.21% | -24.54% | 45 | 50 of 2207 (2.3%) | 0 | 0 |
| ETHUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2024-07-01 | 2024-07-01..2024-09-30 | 6.46 | -18.08% | -24.54% | 47 | — | — | — |
| ETHUSDT 4h | none | 2024-07-01 | 2024-07-01..2024-09-30 | -9.27 | -33.81% | -24.54% | 27 | 13 of 551 (2.4%) | 0 | 0 |
| ETHUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2024-07-01 | 2024-07-01..2024-09-30 | -1.03 | -25.57% | -24.54% | 20 | — | — | — |
| ETHUSDT 1h | none | 2024-10-01 | 2024-10-01..2024-12-31 | -23.92 | 3.97% | 27.88% | 47 | 28 of 2207 (1.3%) | 0 | 0 |
| ETHUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2024-10-01 | 2024-10-01..2024-12-31 | -32.75 | -4.87% | 27.88% | 48 | — | — | — |
| ETHUSDT 4h | none | 2024-10-01 | 2024-10-01..2024-12-31 | -16.95 | 10.93% | 27.88% | 29 | 7 of 551 (1.3%) | 0 | 0 |
| ETHUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2024-10-01 | 2024-10-01..2024-12-31 | -17.53 | 10.35% | 27.88% | 22 | — | — | — |
| ETHUSDT 1h | none | 2025-01-01 | 2025-01-01..2025-03-31 | 0.43 | -45.13% | -45.56% | 66 | 52 of 2159 (2.4%) | 0 | 0 |
| ETHUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2025-01-01 | 2025-01-01..2025-03-31 | 12.53 | -33.04% | -45.56% | 57 | — | — | — |
| ETHUSDT 4h | none | 2025-01-01 | 2025-01-01..2025-03-31 | -1.74 | -47.30% | -45.56% | 38 | 14 of 539 (2.6%) | 0 | 0 |
| ETHUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2025-01-01 | 2025-01-01..2025-03-31 | 0.30 | -45.26% | -45.56% | 24 | — | — | — |
| ETHUSDT 1h | none | 2025-04-01 | 2025-04-01..2025-06-30 | -37.70 | -1.73% | 35.97% | 54 | 46 of 2183 (2.1%) | 0 | 0 |
| ETHUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2025-04-01 | 2025-04-01..2025-06-30 | -55.24 | -19.26% | 35.97% | 44 | — | — | — |
| ETHUSDT 4h | none | 2025-04-01 | 2025-04-01..2025-06-30 | -44.11 | -8.14% | 35.97% | 26 | 11 of 545 (2.0%) | 0 | 0 |
| ETHUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2025-04-01 | 2025-04-01..2025-06-30 | -35.68 | 0.29% | 35.97% | 19 | — | — | — |
| ETHUSDT 1h | none | 2025-07-01 | 2025-07-01..2025-09-30 | -60.51 | 5.77% | 66.28% | 40 | 0 of 2207 (0.0%) | 0 | 0 |
| ETHUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2025-07-01 | 2025-07-01..2025-09-30 | -59.19 | 7.09% | 66.28% | 37 | — | — | — |
| ETHUSDT 4h | none | 2025-07-01 | 2025-07-01..2025-09-30 | -67.70 | -1.42% | 66.28% | 29 | 0 of 551 (0.0%) | 0 | 0 |
| ETHUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2025-07-01 | 2025-07-01..2025-09-30 | -71.07 | -4.80% | 66.28% | 22 | — | — | — |
| ETHUSDT 1h | none | 2025-10-01 | 2025-10-01..2025-12-31 | -3.59 | -32.12% | -28.53% | 58 | 0 of 2207 (0.0%) | 0 | 0 |
| ETHUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2025-10-01 | 2025-10-01..2025-12-31 | 6.54 | -21.98% | -28.53% | 49 | — | — | — |
| ETHUSDT 4h | none | 2025-10-01 | 2025-10-01..2025-12-31 | 14.43 | -14.10% | -28.53% | 34 | 0 of 551 (0.0%) | 0 | 0 |
| ETHUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2025-10-01 | 2025-10-01..2025-12-31 | 30.49 | 1.96% | -28.53% | 27 | — | — | — |
| ETHUSDT 1h | none | 2026-01-01 | 2026-01-01..2026-03-31 | -11.52 | -40.88% | -29.36% | 46 | 0 of 2159 (0.0%) | 0 | 0 |
| ETHUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2026-01-01 | 2026-01-01..2026-03-31 | -1.49 | -30.85% | -29.36% | 44 | — | — | — |
| ETHUSDT 4h | none | 2026-01-01 | 2026-01-01..2026-03-31 | -23.03 | -52.39% | -29.36% | 22 | 0 of 539 (0.0%) | 0 | 0 |
| ETHUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2026-01-01 | 2026-01-01..2026-03-31 | -13.11 | -42.47% | -29.36% | 17 | — | — | — |
| ETHUSDT 1h | none | 2026-04-01 | 2026-04-01..2026-06-30 | 17.48 | -8.08% | -25.56% | 36 | 0 of 2183 (0.0%) | 0 | 0 |
| ETHUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2026-04-01 | 2026-04-01..2026-06-30 | 8.35 | -17.21% | -25.56% | 37 | — | — | — |
| ETHUSDT 4h | none | 2026-04-01 | 2026-04-01..2026-06-30 | 11.76 | -13.80% | -25.56% | 21 | 0 of 545 (0.0%) | 0 | 0 |
| ETHUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2026-04-01 | 2026-04-01..2026-06-30 | 4.21 | -21.35% | -25.56% | 17 | — | — | — |
| ETHUSDT 1h | none | 2026-07-01 | 2026-07-01..2026-09-30 | -35.88 | 34.47% | 70.35% | 19 | 0 of 2207 (0.0%) | 0 | 0 |
| ETHUSDT 1h | OVL-ATR+OVL-COOLDOWN | 2026-07-01 | 2026-07-01..2026-09-30 | -65.56 | 4.79% | 70.35% | 20 | — | — | — |
| ETHUSDT 4h | none | 2026-07-01 | 2026-07-01..2026-09-30 | -40.62 | 29.74% | 70.35% | 14 | 0 of 551 (0.0%) | 0 | 0 |
| ETHUSDT 4h | OVL-ATR+OVL-COOLDOWN | 2026-07-01 | 2026-07-01..2026-09-30 | -54.58 | 15.78% | 70.35% | 14 | — | — | — |

| Combination | Overlays | Median vs B&H (pp) | Worst window (pp) | E1 (Test B) | E2 (Test B) |
|---|---|---|---|---|---|
| BTCUSDT 1h | none | -11.67 | -45.68 | 37 of 19719 (0.2%) | 0 |
| BTCUSDT 1h | OVL-ATR+OVL-COOLDOWN | -12.12 | -44.84 | — | — |
| BTCUSDT 4h | none | -12.20 | -57.05 | 10 of 4923 (0.2%) | 0 |
| BTCUSDT 4h | OVL-ATR+OVL-COOLDOWN | -15.32 | -61.24 | — | — |
| ETHUSDT 1h | none | -11.67 | -60.51 | 176 of 19719 (0.9%) | 0 |
| ETHUSDT 1h | OVL-ATR+OVL-COOLDOWN | -1.49 | -65.56 | — | — |
| ETHUSDT 4h | none | -16.95 | -67.70 | 45 of 4923 (0.9%) | 0 |
| ETHUSDT 4h | OVL-ATR+OVL-COOLDOWN | -13.11 | -71.07 | — | — |

### Batch 1 side by side (out of sample, no overlays; batch 1 not re-run)

| Combination | STRAT-001 vs B&H (pp) | STRAT-002 vs B&H (pp) | STRAT-003 vs B&H (pp) |
|---|---|---|---|
| BTCUSDT 1h | -24.80 | -19.48 | 13.95 |
| BTCUSDT 4h | 5.30 | 2.91 | -5.90 |
| ETHUSDT 1h | -25.63 | -8.57 | -20.34 |
| ETHUSDT 4h | 3.98 | 7.00 | -19.26 |

