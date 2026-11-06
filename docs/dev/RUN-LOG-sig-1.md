# RUN-LOG-sig-1: the signal-candidate audit, round one (FDS-SIG-001, FDS-SIG-002)

## 2026-11-06: implementation (branch `feat/signal-audit-1`)

### Pre-implementation gates

| Gate | Result |
|---|---|
| #225, #226, #227 merged into `main`, in that order, after CI and branch updates | Yes: #225 at 18:10, #226 at 18:15 (after its update-branch), #227 at 18:21 UTC (after a merge of `main`); every required check passed before each merge |
| Baseline | `main` at `0dfbc033c253628b01464bf92e6298e12bb4a22f`, equal to `origin/main` |
| Working tree | The branch was cut into a clean scratch worktree. The owner's checkout has the owner's own pre-existing changes (three deleted `app/*_training_results.json` files and an untracked `PowerTraderAI.code-workspace`), left untouched |
| Specs read in full | FDS-SIG-001 (814 lines) and FDS-SIG-002 (190 lines) |
| `docs/research/volume-module.md` | Read as context: CMF-type evidence rated weak (§4.4); the volume effect on STRAT-001 small; the pattern model's 1-hour direction 50.6% against a 50.3% base rate (n = 51,514). Nothing in it changes either spec |
| Already implemented? | No: no app code named either spec, CMF or the audit |

### Owner decisions during the implementation (FDS-SIG-001 §15.4)

1. **No single-exchange logic** ("Each exchange needs to do this - no single exchange logic allowed!"). Both specs predate the multi-exchange design and name Binance. Recorded in FDS-SIG-001 §15.4, with the affected sentences marked:
   - every connector gained `spot_markets` and `daily_quote_volume`;
   - the audit's logic is the same for every exchange, and no audit module names one (a test checks);
   - the round's exchange is the first in Settings order that can list, state quote volume and serve the history.
2. **Every simulation runs locally, ten times over** ("Do all the 'simulations' locally, run 10x of them"):
   - the two-sided minimum detectable effect is 10 runs of 1,000 simulated rows;
   - §16 item 2's false-pass study is 10 runs of 400 rows per scenario, with the full bootstrap.

### What each exchange can serve (public endpoints, checked live on 2026-11-06 in a sandbox, no keys)

| Exchange | Markets in its dollar quote | Daily quote volume | Leveraged mark | History |
|---|---|---|---|---|
| Binance | 775 (USDT), 518 trading | 1d kline field 7 | 40 marked (old BTCUP/BTCDOWN tokens, all BREAK) | years |
| KuCoin | 800 (USDT), all enabled | 1day candle turnover | none in its answer (no leveraged tokens listed) | years |
| Kraken | 681 (USD), 624 online | vwap x volume | none | only its latest 720 bars |
| Coinbase | 496 (USD), 405 trading | **not stated** (base volume only) | none | years |

The shipped Settings order is Coinbase, Kraken, KuCoin, Binance. With it, the round's exchange would be KuCoin:
- **Coinbase** states no quote volume;
- **Kraken** serves 720 bars, so it cannot serve a months-long window.

### Implementation notes (where the specs needed reading; none changes a method)

- **Holm** uses adjusted p-values. The recheck re-derives every verdict by the step-down thresholds instead.
- **Fisher's one-sided tests** are computed on the hypergeometric distribution.
- **The two-sided hit rate's minimum detectable effect** is simulated at the row's own E, n, q and p_c, with the constant chosen afresh in each simulated row and the largest-of-three rule.
  - The simulated pairs are independent, so their block length is one day.
  - Inside that simulation only, the bootstrap p-value is taken at its B -> infinity limit: the exact circular-block variance, with a normal tail. The full bootstrap per simulated row would need about 10^14 resamples. The audit's own tests always use the full bootstrap.
- **The bootstrap's random streams** are `SeedSequence(seed, spawn_key=(row, stream))`.
- **The ranking days** are the 30 daily bars opening on the 30 UTC days up to and including the ranking date.
- **The exclusion lists** (stablecoins and pegged tokens, wrapped and staking tokens, leveraged suffixes) are concrete lists in `signal_audit/ranking.py`, copied into the registration for review.
- **CMF's sums** are exactly rounded (`math.fsum`), so "CMF_t = 0" is decided the same way whatever order the bars are summed in.
- **The raw ranking answers** are stored gzip-compressed (Binance's exchange information alone is 17.8 MB), with each answer's SHA-256 and the file's.

### Tests

| Run | Command | Result |
|---|---|---|
| The signal-audit tests | `python -m pytest tests/test_signal_audit_*.py` (from `app/`) | 100 passed |
| The full suite | `python -m pytest -q` (from `app/`, isolation guard on) | **2,763 passed, 13 skipped, 0 failed**, in 19.5 min. `main`'s 2,663 plus exactly the 100 new tests |
| The full-scale false-pass study | `python docs/dev/sig_false_pass_study.py` | 15 scenarios × 4,000 simulated rows; all at or below nominal (below) |
| A live check of the new connector methods | four exchanges' public endpoints, a sandbox with no keys | every answer parsed |
| Black, flake8 | `black --check app/`; CI's `flake8 --select=E9,F63,F7,F82`; plus a full flake8 on the new files | clean |

**Environment:**
- Windows 11, Python 3.13.15, numpy 2.5.4, pandas 3.1.0, scipy from `app/requirements.txt`;
- tests under the isolation guard (`app/conftest.py`);
- no test touches the network or any real user folder.

**Defects found and fixed while building:**
- A gzip header held the file name, so the same answers hashed differently.
- KuCoin's leveraged-token mark was a guess with no basis; the live check showed KuCoin has none, and it is removed.

**No known open defect.**

### The false-pass study (§16 item 2, at full scale, simulated data only)

`docs/dev/sig_false_pass_study.py`; evidence in `docs/dev/sig-audit/verification/false-pass-study.json`.
- **Setup:** every scenario ran in 10 independent runs of 400 simulated rows (4,000 rows), seeds 7,000,000 + 1,000 × scenario + run.
- **Rows:** 4,380 eligible pairs each (six months of 1h).
- **Tests:** F = 4, so α/F = 1.25%. The bootstrap ran in full, at B = 8,000 = 100 / α₁.
- **Pass rules:** a test passes at Holm's first step; a family of 4 passes when any member survives Holm.

| No-skill scenario | Statistic | Per-test false passes (nominal 1.25%) | Per family (nominal 5%) | Assessable rows |
|---|---|---|---|---|
| Seeded random calls | hit rate | 0.03% | 0.1% | 4,000 |
| Seeded random calls | magnitude | 1.07% | 4.3% | 4,000 |
| "Always up" with 10% flips, up share 53% | hit rate | 0.00% | 0.0% | 4,000 |
| "Always up" with 10% flips, up share 47% | hit rate | 0.00% | 0.0% | 4,000 |
| "Always up" with 10% flips, up share 53% | magnitude | 0.00% | 0.0% | 4,000 |
| Calls in runs of 100–200 bars, regime-drifting returns | hit rate | 0.00% | 0.0% | 685 (the rest below the 30-block floor) |
| Calls in runs of 100–200 bars, regime-drifting returns | magnitude | 0.10% | 0.4% | 674 |
| Call probability drifting ±0.15 (2–4-week cycles), one-sided | hit rate | 0.88% | 3.5% | 4,000 |
| Call probability drifting ±0.30 (2–4-week cycles), one-sided | hit rate | 0.63% | 2.5% | 4,000 |
| Call probability drifting ±0.15 (2–4-week cycles), two-sided | magnitude | 1.05% | 4.2% | 4,000 |
| Call probability drifting ±0.30 (2–4-week cycles), two-sided | magnitude | 1.07% | 4.3% | 4,000 |
| Call probability drifting ±0.30, a cycle of exactly a month, one-sided | hit rate | 0.80% | 3.0% | 4,000 |
| Call probability drifting ±0.30, a cycle of exactly a month, two-sided | magnitude | 1.07% | 4.1% | 4,000 |
| Call probability drifting ±0.15, a cycle of exactly a month, one-sided | hit rate | 0.63% | 2.4% | 4,000 |
| Call probability drifting ±0.15, a cycle of exactly a month, two-sided | magnitude | 0.77% | 3.0% | 4,000 |

Monte Carlo standard errors are 0.18 points per test and 0.7 points per family. Every scenario is at or below α/F per test and 5% per family, within that error. Constant callers ("always up", "always down", above and below a 50% up share) are NOT ASSESSABLE (unit tests).

**The block length's maximum lag.** A call probability whose cycle is exactly a month is not seen by the Bartlett window when M is one month: its autocorrelations cancel, τ stays near 1, and L is one day. §7.4 says M is raised if §16 item 2 fails at the stated drift sizes. It does not fail, even for that exact cycle, so **M stays at one month as registered**.

### Round one: not registered

Nothing has been registered, ranked for evidence or fetched for a verdict. Until a registration is committed and its window has ended, there is no result.

**Decisions waiting for the owner:**

Nothing below is decided in this PR; each item waits for the owner.

1. **Which exchange ranks round one.**
   - **The problem.** Coinbase, the primary, states no quote volume, and FDS-SIG-001 §4 forbids calling base volume times a price "quote volume". With the shipped Settings order (Coinbase, Kraken, KuCoin, Binance), the round would rank and run on **KuCoin**: Kraken serves only 720 bars. The volume research found KuCoin's volume the least consistent with other exchanges (§4.5, §6.7).
   - **Options:**
     - (a) approve a stated approximation for Coinbase, for example the sum of each hour's close × base volume over the day, named "approximate quote volume", for the ranking only;
     - (b) put the exchange you want ranking round one first in Settings (an exchange that states quote volume: Binance, KuCoin);
     - (c) accept KuCoin.
   - **Recommendation:** (a). It keeps the round on your trading exchange, and the approximation is close to traded value at hourly granularity. It is a change to §4's wording, so it needs your approval.
2. **The window end** (FDS-SIG-001 §15.2 item 1). The start is the first 00:00 UTC after the registration commit.
   - **Floor:** SIG-A's 4h rows need about 1,200–1,500 eligible pairs, which is at least about 250 days, or they are NOT ASSESSABLE.
   - **Recommendation: 12 months.** The simulated smallest detectable edges for a balanced, full-coverage caller at F = 76 (10 runs, 2026-11-06):

     | Window | 1h | 4h |
     |---|---|---|
     | 12 months | 3.5 points | 7.0 points |
     | 9 months | 4.0 points | 8.1 points |

   - **Nine months** is the shortest that keeps the 4h rows assessable.
   - **The round-scale study** (finding 4, below) agrees: at 270 days, SIG-A's 4h rows were assessable in 93.8% of the simulated rounds (median K 52.5). The other 6.2% fell below the 30-block floor.
   - The planning table's lower bounds are 3.1 and 6.1 points at 12 months.
3. **FDS-SIG-001 §15.3's nine defaults**, which the spec itself says to confirm before registering:
   - either statistic qualifies a row;
   - the dependence rules;
   - the 1,000-call floor;
   - the coin rules;
   - input coins;
   - confirmation not sharing a window;
   - WORSE judged against chance at the mix;
   - the de-meaned magnitude test and its conditions;
   - registration before the window starts.

   The implementation uses all of them as written.
4. **The exclusion lists** in `signal_audit/ranking.py`, which the spec gives only by example:
   - **Concrete lists:** stablecoins and fiat- or commodity-pegged tokens, wrapped and staking tokens, and the leveraged suffixes UP, DOWN, BULL and BEAR.
   - **Not covered by the spec's classes:** KuCoin's "Stocks" market (10 USDT pairs of tokenized shares). Recommendation: exclude them as asset-pegged tokens.
5. **The ranking date.** It falls within the 7 days before the ranking fetch (§10.1), so it is set when you approve. The `rank` step refuses a fetch before the ranking date's UTC day has ended (its daily bar would still be forming), or more than 7 days after it.
6. **The registered seed and the MDE simulation.**
   - Seed 20261106.
   - The two-sided MDE: 10 runs × 1,000 simulated rows, with the bootstrap taken at its B → ∞ limit inside that simulation only. The audit's own p-values always use the full bootstrap.
7. **Settled by the evidence, recorded:** the block length's maximum lag stays at one month (§7.4). The false-pass study does not fail at the stated drift sizes, even for an exact one-month cycle.

Decisions 8 to 12 come from the PR #228 review (below).

## 2026-11-06: the PR #228 review (four findings)

The owner's review raised four findings. Each was reproduced or established from the code before anything changed. The reproductions ran against the PR as submitted (`6bd8ac5`), in a sandbox: no network, a throwaway git repository and a scratch candle cache. They ran again after the fixes.

The implementation section's "No known open defect" is superseded: three findings were defects in the code. Round one is still not registered, ranked, fetched or run, and nothing here changes a candidate, a statistical threshold, an approved test or a §15.3 default.

| # | Finding | Requirement | Code path | Classification | Correction | Commit |
|---|---|---|---|---|---|---|
| 1 | Missing quote volume | §10.1 ranking: "the sum of [the stated quote volume] over the 30 UTC days … ending on the ranking date" (silent on failed or partial answers); §12 step 0 | `ranking.rank_markets`; `run_signal_audit.rank` | **CONFIRMED DEFECT**, with a SPECIFICATION AMBIGUITY (listings and stops within the 30 days) | Every day accounted for, or the ranking is refused; errors kept; nothing estimated | `e305653` |
| 2 | Code-freeze integrity | §12 step 2 (code freeze); step 4 (refusals); step 6 ("After results: only defect fixes, through `--supersede`") | `registration.check_can_run`; `run_signal_audit.run` | **CONFIRMED DEFECT**, with a SPECIFICATION AMBIGUITY (step 4's list does not name it) | A frozen path changed after the freeze, or a changed freeze record, is refused, except a defect fix after results | `4514144` |
| 3 | Candle-cache reproducibility | §12 step 3 ("Each candle file's SHA-256 is recorded, and the run stops if a file differs from an earlier record of it"); step 4 | `run_signal_audit.fetch` and `run` | **CONFIRMED DEFECT** | Window-scoped snapshots, checked against a fresh fetch, read alone by the run | `e427706` |
| 4 | False-positive validation at F = 76 | §16 item 2; §8.1 (Holm over F = 76 for round one's draft) | `nullsim`, `sig_false_pass_study.py` | **NOT A DEFECT** in the statistics; the evidence was **insufficient**: the F = 4 study did not show the round's family error | A round-scale study: whole simulated rounds, F = 76, dependent rows, 10 runs | `5da9caf` |

### Finding 1: missing quote volume

**Reproduced (before).** A failed request ranked as zero volume and stayed included; a market with 10 of its 30 days ranked on those 10:

```
rank 1 AAAUSDT: volume 3000.0, days 30, included True
rank 2 CCCUSDT: volume 500.0, days 10, included True
rank 3 BBBUSDT: volume 0.0, days 0, included True
```

The script turned every exception from `daily_quote_volume` into `None` (`run_signal_audit.py`, `rank`), and `rank_markets` summed whatever days it found. **Also found:** the fetch-time check (`day <= fetched <= day + 8 days`) allowed a ranking fetch on the ranking date itself, while that day's bar was still forming.

**Corrected.** `ranking.volume_evidence` accounts for every one of the 30 days. A market's volume is established only when it is:

- **complete:** a bar on every day. Its stated volume is summed, and zero is a volume: a genuine zero ranks as zero;
- **listed within the span:** no bar before its first, and an unbroken run from then to the ranking date;
- **stopped within the span:** an unbroken run that ends early, and the exchange lists the market as not trading;
- **not trading in the span:** no bar at all, and the exchange lists it as not trading.

A failed request, no answer, a day missing while the market traded, or a volume that is not a finite number at least 0 is not evidence. **The ranking is refused** (`RankingRefused`) when any included market's volume is not established. `run_signal_audit.rank` then writes `ranking/refused.json`, with the exchange, the ranking date, the fetch time and each such market's error or missing days, and stops. An excluded market cannot be selected, so its evidence is recorded and does not refuse. The fetch must come after the ranking date's UTC day has ended, and within 7 days after it.

**After:**

```
refused: the 30-day quote volume of 2 included market(s) is not established, so the ranking cannot be:
  BBBUSDT: failed (ConnectionError: HTTP 503 from the exchange);
  CCCUSDT: incomplete (no bar after 2026-10-17, while the exchange lists it as TRADING)
the ranking date 2026-11-06 has not ended: its daily bar is still forming, so its volume is not final
```

**Tests:** `test_signal_audit_ranking.py`, 8 tests. They cover:
- a failed request, no answer, and a market missing from the answers;
- an incomplete period: the review's 10 of 30 days, a gap inside the period, and no bar at all while trading;
- a volume that is not a number;
- a listing or a stop within the period;
- an excluded market's failure;
- genuine zero volume;
- the fetch time.

### Finding 2: code-freeze integrity

**Reproduced (before).**
- A commit changing `app/code.py` after the freeze commit was not refused. It was only listed (`frozen_files_changed_since_freeze: ['app/code.py']`).
- Committing `freeze.json` again then moved the freeze point past the change, which was no longer even listed (`[]`).

**Consistency with FDS-SIG-001.**
- Step 2 freezes the code, and step 6 allows a change after results only as a defect fix through `--supersede`.
- Step 4's list of refusals names dirty frozen paths, but not committed changes after the freeze.
- Step 5 asks each output to record "whether any frozen file changed", which fits the superseding fix: a changed frozen file is allowed only there.
- So the audit could silently evaluate a registered experiment with other code than the code frozen for it. That is a defect against steps 2 and 6. Step 4's list is ambiguous by omission (decision 8 below).

**Corrected.**
- The freeze commit is the one that first added `freeze.json`. A later change to it, committed or not, is refused.
- A frozen path changed in any commit after the freeze is refused, unless results exist and the run carries a `--supersede` note. Then the changed files and the note are recorded in the outputs, and the earlier verdict stays beside the new one.
- Uncommitted frozen changes are refused as before, with a note or without.
- No existing refusal is weakened: the 24 earlier tests of `test_signal_audit_run.py` pass unchanged.

**After:**

```
refused: frozen paths changed since the freeze commit 44439b6: ['app/code.py']; no results exist, and section 12 allows changed code only as a defect fix after results, through --supersede
refused: the freeze record docs/dev/sig-audit/round-1/freeze.json changed after its freeze commit 44439b6 (in ['8950b75'])
```

**Tests:** 6 new tests in `test_signal_audit_run.py`. They cover:
- changes after the freeze, committed: a changed file and a new frozen file;
- changes before the freeze, committed: the freeze takes them;
- uncommitted changes, before and after the freeze;
- a reverted change, and a change outside the frozen paths;
- a changed freeze record;
- a superseding fix with and without results, and with a blank note.

Against the PR's original `registration.py`, five of the six fail:
- three on behaviour: a committed change, a new frozen file and a changed freeze record are not refused;
- two on the new `--supersede` arguments.

The sixth, a reverted change, must not be refused, so it passes on both.

### Finding 3: candle-cache reproducibility

**Reproduced (before).** The fetch recorded each shared cache file's SHA-256, and the run re-hashed the file. When later bars were appended to the cache, the window's bars were unchanged (`True`), but the file's SHA-256 changed (`True`), so the run would stop. The cache never asks again for a bar it holds, so an exchange's later correction of a past bar was invisible.

**Corrected** (`app/signal_audit/evidence.py`). This uses FDS-MH-001's form, the bars' SHA-256 in the cache's CSV form (`pt_pattern_trainer.candle_sha256`). The model harness itself is not changed.

- **Fetch.**
  - Each series is read through the exchange layer, from the registered exchange only.
  - It is fetched again from that exchange without the cache (`ExchangeManager.candles` with `only`), and that answer must name the same exchange and pair.
  - The two must agree bar for bar. A difference is a historical correction or a cache fault: the fetch stops and names the first bars that differ.
  - A series fetched before must match its earlier record.
  - The round's span, from the warm-up before the window start to the window end, is then written once as a **snapshot** in the sandbox, and never overwritten with other bars.
  - The snapshot is recorded with its exchange, pair, span, first and last bar, bar count and SHA-256. That SHA-256 is also the snapshot file's own.
- **Run.**
  - Only the snapshots are read, never the cache.
  - Each snapshot must match its record.
  - The record must hold exactly the registered exchange, coins, input coins, timeframes and span.
- **Step 0's history check** records the bars it read, not the cache file.

**After:** the cache file's SHA-256 changes as it grows, while the evidence and the evaluated series stay identical. A correction stops the fetch. A changed or missing snapshot, a record from another exchange, a series that is not registered, or a moved window stops the run. Two runs give byte-identical results.

**Tests:** `test_signal_audit_evidence.py`, 5 tests, on a fake exchange behind a real `ExchangeManager` that serves 1h bars only, so the 4h bars are built both through the cache and without it.

### Finding 4: false-positive validation at round scale

**Established from the code and evidence (before).**
- The full-scale study ran F = 4: families of four independent single-row tests, at α₁ = 1.25%.
- Round one's draft family is F = 76: SIG-A on ten coins and SIG-B on nine, on 1h and 4h, two statistics each. Its tests are at α₁ = 0.066%.
- Its rows are dependent:
  - the nine SIG-B rows of a timeframe share BTC's calls;
  - the coins share a market factor;
  - the 4h bars are the 1h bars;
  - a row's two statistics use the same pairs.
- Holm controls the family error under any dependence when each p-value is valid. The F = 4 study did not show that the p-values are valid that far into the tail (66 in 100,000), or the family error of a whole dependent round.
- No statistic, threshold or test was wrong. The evidence did not cover the family the round registers.

**Added** (`signal_audit.nullsim`, `docs/dev/sig_round_false_pass_study.py`).
- **Whole simulated rounds.** Ten coins (coin 0 is BTC) over the draft's 270-day window, plus warm-up.
- **The real code path from bars to verdicts:**
  - the 4h bars are built by the candle layer's `build_candles`;
  - the family by `registration.family_rows`;
  - the pairs by `pairs.row_pairs`;
  - SIG-A and SIG-B as registered;
  - each row by `engine.evaluate_row`, Holm by `engine.apply_holm`, the verdicts by `engine.verdict_of`;
  - B = 152,000 = 100 / α₁.
- **Dependence:**
  - one market factor in every coin (correlation 0.6 to 0.9);
  - GARCH(1,1) volatility clustering, month-long volatility regimes and a daily volatility cycle;
  - Student-t shocks (4 degrees of freedom);
  - volume that persists and rises with the absolute return;
  - outages that leave gaps in every coin at once.
- **No skill.** Each bar's return is a constant drift (an up share of 48 to 52%) plus a shock independent of every earlier bar.
- **The shortcut, and why it is safe.** A statistic's bootstrap is skipped only where it cannot change a decision.
  - The p-value entering Holm is the largest of three. When the exact and batch-means p-values of both directions already exceed 5%, neither direction can survive Holm at 5%, and no other member's adjusted p-value at or below 5% changes.
  - A unit test checks this on three seeds, including one with real skill. Every verdict, survivor and adjusted p-value at or below 5% equals `engine.evaluate_round`'s, and every statistic not skipped equals it exactly, seeds included.
  - The audit itself never skips.
- **A check with real skill.** One coin's return follows BTC's previous return. This shows a pass is still found.

**Results** (simulated data; verification, not a result about any market). The evidence is in `docs/dev/sig-audit/verification/round-false-pass-study.json`.
- **Runs:** 10 independent runs of 300 rounds (3,000 rounds), seeds 8,000,000 + run.
- **Bootstrap:** B = 152,000.
- **Time:** 77 minutes on 10 processes.

| Measure | Nominal | Pooled (3,000 rounds) | By run (300 rounds each) |
|---|---|---|---|
| Rounds with a false PASS (the family error, forward Holm) | at most 5% | **1.13%** (34); MC s.e. 0.40%; 99.9% upper bound 1.87% | 0.0% to 2.7% |
| Rounds with a WORSE (opposite-direction Holm) | at most 5% | 2.87% (86); 99.9% upper bound 3.93% | 2.0% to 4.0% |
| Per test: assessable, extra condition met, p at most α₁ | at most α₁ = 0.066% | **0.015%** (34 of 224,274); MC s.e. 0.005%; 99.9% upper bound 0.025% | 0.000% to 0.036% |
| Per test, the opposite direction | at most 0.066% | 0.044% (98) | |
| One component: the exact p-value at most α₁ | | 0.000% | |
| One component: the batch-means p-value at most α₁ | | 0.024% (53) | |

- **Where the 34 false passes fell:**
  - SIG-B: 11 on 1h, 10 on 4h;
  - SIG-A: 10 on 4h, 3 on 1h.
- **Assessable:**
  - SIG-A's 4h rows: in 93.8% of rounds (median L 30.5 bars, median K 52.5). The rest are below the 30-block floor.
  - Every other row type: 100%.
- **Bootstrap skipped:** 211,666 of the 228,000 statistics, 92.8%.
- **Real skill.** C03's return follows 0.15 of BTC's previous hourly shock. SIG-B C03 1h passed in **46 of 50 rounds** (95% lower bound 83%), with no other PASS and no WORSE.

**Conclusion: NOT A DEFECT.**
- At round scale, with the dependence a real round has, the procedure holds the family error well below 5% and the per-test rate below α₁.
- It is conservative: per test, about a quarter of nominal. The exact p-value never fell below α₁, and the batch-means p-value seldom did. The p-value entering Holm is the largest of the three.
- No deficiency was found, so no correction is proposed: no statistic, threshold, test, B or F changes.
- The F = 4 study stands as the single-row evidence. It covers the call processes this study leaves out: persistent and drifting calls over regime-drifting returns.

### Tests, before and after

| Run | Before (`6bd8ac5`) | After |
|---|---|---|
| The signal-audit tests (`tests/test_signal_audit_*.py`, from `app/`) | 100 passed | **123 passed** (the 100 before, plus 23 new: 8 ranking, 6 freeze, 5 snapshot, 4 round-scale) |
| The full suite (`python -m pytest -q`, from `app/`, isolation guard on) | 2,763 passed, 13 skipped, 0 failed | **2,786 passed, 13 skipped, 0 failed, in 19.3 min: the 2,763 before plus exactly the 23 new tests** |
| The F = 4 false-pass study (`sig_false_pass_study.py`) | 15 scenarios × 4,000 rows, all at or below nominal | reproduced exactly. Scenarios 10–14 match the committed records field for field. Scenarios 0–9 match in every printed figure: that part's process was stopped by mistake before it wrote its file, and the rest was re-run with `--only` |
| The round-scale study (`sig_round_false_pass_study.py`) | none | 3,000 rounds at F = 76: a false PASS in 1.13% of rounds (nominal 5%), 0.015% per test (nominal 0.066%); real skill found in 46 of 50 rounds |
| The review reproductions (sandbox) | four defects reproduced | each refused or stopped as above |
| Black, flake8 | reported clean | `black --check app/` clean; CI's `flake8 --select=E9,F63,F7,F82` clean. A full flake8 of the audit's files (line length 100, as `code-quality.yml`) is now clean. It found two style warnings in the PR's own tests, E741 and E731, which the implementation section's "clean" had missed; they are fixed in `6d16c35` |

### Decisions from the review, for the owner

8. **Step 4's list (finding 2).** Add two refusals to FDS-SIG-001 §12 step 4: a frozen path changed in any commit after the freeze commit, except a defect fix after results through `--supersede`; and a freeze record changed after its freeze commit. The code already refuses both.
9. **A defect found before results (finding 2).** The spec gives no route for one. This implementation reads steps 2 and 6 together:
   - run the frozen code first, from the freeze commit;
   - then supersede it with the fix;
   - both verdicts are reported.

   The alternative is to abandon the round and register a new window. **Recommendation:** the reading above, written into step 6.
10. **Ranking on incomplete volume (finding 1).**
    - **Confirm the classification in §10.1's wording:**
      - a market listed within the 30 days sums the days it traded;
      - one that stopped trading within them sums the days it traded, if the exchange lists it as not trading;
      - any other missing day, failed request or unusable volume refuses the ranking.
    - **Optional:** a market the exchange lists as not trading cannot pass the history check, so its failed request could be recorded instead of refusing.
    - **Recommendation:** keep the strict rule until a real ranking shows whether it bites. A refused ranking can be fetched again within the 7 days.
11. **Step 3's wording (finding 3).** "Each candle file's SHA-256" becomes the window-scoped snapshot's SHA-256, plus the fresh-fetch comparison that stops on a correction. Where the snapshots live:
    - **(a) the sandbox:** as built, and as step 0's candle files;
    - **(b) committed with the results:** gzip, about 2 MB, so anyone can verify the evaluated series without the exchange.

    **Recommendation:** (b), at the run.
12. **None needed for finding 4.** The round-scale study shows no deficiency, so no change to the tests, the thresholds, B or F is proposed. The conservatism (1.1% against 5%) comes from the approved largest-of-three rule. It costs power, which the simulated MDE already reflects (decision 2), and it is not changed.

### Residual limitations

- **Simulated, not real, data.**
  - The round-scale study shows the procedure's family error under one model of crypto dependence. It does not prove it for every market.
  - The model has no drift that changes within the window. A rule that follows recent bars would then have real skill over the best constant, and its passes would not be false.
  - The single-row F = 4 scenarios still cover calls that are independent of regime-drifting returns.
- **F = 76 only.** The draft has BTC in the top ten. Without BTC, F = 80: SIG-B then runs on all ten coins, with α₁ about 5% smaller. That family was not simulated. Its dependence is of the same kind.
- **Monte Carlo error.** At 3,000 rounds the family error's standard error is 0.4 points (99.9% upper bound 1.87%), and the per-test rate's is 0.005 points (upper bound 0.025%).
- **The shortcut.** It is used in the study only, and is proved and tested equal in its decisions. The audit always runs the full bootstrap.
- **The ranking refusal is all or nothing.** One persistently failing market blocks the ranking until the owner decides (decision 10). `ranking/refused.json` names it.
- **A historical correction stops the fetch.** The bars that differ are named. Accepting a corrected series is the owner's decision, by fetching again into an empty cache and recording why.
- **Snapshots in the sandbox** (decision 11). They are verifiable only on this machine, or by fetching again from the exchange.
