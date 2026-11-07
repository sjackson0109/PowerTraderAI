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

Decisions 8 to 12 come from the PR #228 review (below). The owner decided them on 2026-11-07 (FDS-SIG-001 §15.5), and the follow-up review's questions A1 to A7 are at the end.

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

*Decided by the owner on 2026-11-07 (FDS-SIG-001 §15.5): D8 approved, D9 revised, D10 and D11 approved, D12 no change. See the follow-up section below.*


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

## 2026-11-07: the follow-up review and the owner's decisions D8 to D12

The owner accepted the remediation in principle. An independent follow-up review raised two matters to resolve before merge, and the owner decided D8 to D12 (FDS-SIG-001 §15.5). Round one is still not registered, ranked, fetched or run. PR #228 stays open. No statistical procedure, threshold or signal candidate changes.

| # | Matter | Requirement | Code path at `c3297be` | Classification | Correction | Commit |
|---|---|---|---|---|---|---|
| 1 | Listing and cessation inferred, not established | §10.1; D10 "strict … subject to verified listing and cessation evidence" | `ranking.volume_evidence`: "listed within the span" from the answer's first bar; "stopped within the span" and "not trading in the span" from missing later bars and the current status | **CONFIRMED DEFECT**, established from the code: an incomplete answer gives the same bars | Only the exchange's own stated trading start or end can account for a missing day; otherwise the ranking is refused | `56a8275` |
| 2 | Defects discovered before results | D9 (revised); §12 step 6 | `check_can_run` refused changed code before results, but the remediation's proposed route ran the frozen code, then superseded it | **SPECIFICATION CHANGE** by the owner (D9) | Cancellation record, a refused cancelled round, a replacement registration; `--supersede` keeps the earlier results and their provenance | `549c9fa`, `d6edbd3`, `2ebaeb8` |
| 3 | D8, D10, D11, D12 | §15.5 | — | owner decisions | D8 in step 4; D10 as matter 1; D11 compressed, hashed, committed snapshots with `verify`; D12 recorded | `09f7114`, `d6edbd3`, `2ebaeb8` |
| 4 | A 12-month round without blocking `main` | the owner's item 4 | — | documentation, plus a guarantee test | FDS-SIG-001 §12.1: a research branch and its own worktree; the run state records package versions | `549c9fa`, `2ebaeb8` |

### Matter 1: what each exchange states about listing and cessation

**Investigated** with `docs/dev/sig_listing_evidence_probe.py`, using public data and the standard library only, on 2026-11-07, over the 30 days ending 2026-11-06. The evidence is in `docs/dev/sig-audit/verification/listing-evidence-probe.json`, which records each answer's SHA-256.

| Exchange | Market list (dollar quote) | Fields naming or holding a time | Trading start stated | Cessation stated | Not trading now |
|---|---|---|---|---|---|
| Binance | `exchangeInfo`, 775 USDT | none | no | no. The delisting schedule (`/sapi/v1/spot/delist-schedule`) refuses without an API key (`-2014`), and the audit reads no key | 257 BREAK |
| KuCoin | `/api/v2/symbols`, 800 USDT | `tradingStartTime` (708), three `callauction…StartTime` (357) | **yes:** `tradingStartTime`, on 708 of 800 | no. A delisted symbol leaves the list | none (all 800 enabled) |
| Kraken | `AssetPairs`, 681 USD | none (two position-limit numbers look like times; they are not) | no | no | 55 cancel_only, 2 post_only |
| Coinbase | `/products`, 496 USD | none | no | no | 91 delisted |

**KuCoin's `tradingStartTime` checked against its own daily candles:**
- **Recent listings:** for every symbol stated to start within 40 days of the span (18), the first daily candle fell on the stated day.
- **Older symbols:** in a sample of 25, 20 matched. In the other 5, the candles begin later than the stated day, because KuCoin's candle history starts on 2022-09-29.
- **Contradictions:** no symbol had a candle before its stated day.
- **Symbols without the field:** all 92 had 30 days of candles in the span.

**Binance:**
- **Listings:** 15 TRADING markets began within the span, by their first-ever daily kline. Most are tokenized equities and ETFs (BBBUSDT, MDBBUSDT, UVXYBUSDT, BRKBBUSDT, …).
- **Not trading:** of the 257 BREAK markets, 254 have no bar in the span and 3 have part of it (QUICKUSDT, VELODROMEUSDT, EPICUSDT).

**Classification: CONFIRMED DEFECT.**
- At `c3297be`, a market whose answer began on day 21 ranked as "listed within the span". An answer that had lost its first 20 days ranks the same way.
- Missing later bars plus a status of BREAK ranked as "stopped".
- No bars at all plus BREAK ranked as zero volume.
- None of these observations dates a listing or a cessation. The new test `test_the_same_bars_without_a_stated_start_are_an_incomplete_answer` ranked as listed at `c3297be`.

**Corrected** (`56a8275`), within the exchange-neutral design:
- **The data model:** `ListedMarket` gains `trading_start_ms`, `trading_end_ms` and `history_stated_by`. They are set only where the exchange's listing states them; nothing infers them.
- **The connectors:** KuCoin's connector keeps `tradingStartTime`, while null or 0 states nothing. No other connector states a time.
- **The rule** (`volume_evidence`). A day without a bar is accounted for only by those statements. The market was listed within or after the span, stopped within or before it, or both, and every day of the stated period inside the span has a bar. Otherwise the ranking is refused:
  - **incomplete:** missing days with no stated time, or a gap inside the stated period;
  - **conflicting:** a bar outside the stated period, a stated end while the market is listed as trading, or an end before the start.
- **The evidence:** the stated times and their field are kept in the volume evidence, the ranked list and `ranking/refused.json`.

**Tests:**
- **Ranking** (7 new): a genuine recent listing with its stated start, and a listing after the span; the same bars without a stated start (refused); days missing after a stated start; a ceased market with a stated end, and the same bars without one (refused); conflicting evidence; complete bars.
- **The connector:** null and 0 state nothing, and no other connector states a time.

**What this means in practice** (ambiguity A1 below):
- **KuCoin:** on the probe's day, every incomplete span was accounted for by a stated start.
- **Binance:** a strict ranking would be refused. It states no time for its 15 new listings or its 257 BREAK markets.

### Matter 2: a defect found before results (D9)

**Owner direction:** "Do not knowingly execute defective frozen code to manufacture an original result for subsequent supersession."

**Corrected:**
- **Cancellation** (`registration.cancellation_record`; `run_signal_audit.py cancel --round N --defect "…"`): `cancellation.json` is committed on its own. It records:
  - the defect;
  - the registration's commit and SHA-256;
  - the freeze commit;
  - the code at cancellation (the frozen files changed or uncommitted);
  - whether the window had started or ended.

  It is refused without a committed registration, twice, or when results exist.
- **The cancelled round is never run** (a new refusal), with or without `--supersede`.
- **The replacement** (`draft --replaces N`) is a new registration in a later round, through steps 0 to 2 in full.
  - It records the cancelled round: its cancellation's commit and SHA-256, the cancelled window, and whether that window had started.
  - The run refuses a replacement whose cancellation is uncommitted, changed since, or not committed before it.
  - Its window starts after its own registration commit, as every registration's does.
  - The spec covers both cases: a cancelled window that had not started (the same dates may be kept), and one that had (a new window).
- **`--supersede`** (`registration.supersede_results`) is kept for defects found after results. The earlier results, evidence series and report move to `superseded/<k>-<commit>/`, with the note, the time, the results' commit and each file's SHA-256.

**Tests:**
- `test_signal_audit_run.py`, 7 new tests:
  - a cancellation before and after the window started;
  - its refusals;
  - a replacement and its refusals;
  - supersession;
  - the package versions;
  - the worktree run.
- `test_signal_audit_script.py`, 3 new tests: the script end to end on a throwaway repository.

### The decisions recorded (FDS-SIG-001 §15.5)

- **D8:** the two freeze refusals are in §12 step 4.
- **D9:** §12 step 6, with both window cases, and §11's later windows (a cancelled window is never examined).
- **D10:** §10.1 "Every day accounted for", with what the exchanges state.
- **D11:** §12 step 3.
  - **The snapshots:** gzip (no file name, time 0, level 9: the same bars give the same bytes) in `candles/<coin>_<tf>.csv.gz`, written once. The bars' SHA-256 and the file's are recorded, and they are committed with the results.
  - **`verify`:** checks every snapshot without the exchange, and re-derives the results from the snapshots, only with the code that produced them. With `--refetch`, it compares each snapshot with the exchange's bars now.
- **D12:** no statistical change. The round-scale study stands.

### Item 4: a 12-month round without blocking development

FDS-SIG-001 §12.1 gives the PowerShell steps.
- **The research branch.** The round's registration and freeze are committed on `research/sig-round-N`, cut from `main` after this PR. The branch is pushed, and the freeze commit is tagged.
- **The worktree.** The run executes from its own worktree, outside the repo and outside `%TEMP%` (which Windows cleans), with its own virtual environment and sandbox, untouched for the round.
- **During the window.** Development continues on `main`. Merging `main` into the research branch makes the run refuse, so it fails safe.
- **After the window.** The fetch, the run, the results commit (with the snapshots) and `verify` all happen in the worktree. The round's folder and report reach `main` by checking out those paths, not by merging, so no frozen or fixed code enters `main`.
- **What it preserves:** the registration, the freeze, the candle evidence and every refusal, because they all read the worktree's own HEAD and history.
- **Tested:** `test_a_round_runs_from_its_research_worktree_while_main_moves_on`. The run is refused in a moved-on main checkout, allowed in the research worktree with the fetch committed, and refused there once `main` is merged in.
- **The environment:** the outputs now record the numpy, scipy and pandas versions.

### Tests, before and after

| Run | Before (`c3297be`) | After |
|---|---|---|
| The signal-audit tests (`tests/test_signal_audit_*.py`, from `app/`) | 123 passed | **142 passed**: 6 more ranking, 1 connector, 7 registration, 2 snapshot and 3 end-to-end script tests |
| The full suite (`python -m pytest -q`, from `app/`, isolation guard on) | 2,786 passed, 13 skipped, 0 failed | **2,805 passed, 13 skipped, 0 failed**, in 18.9 min: the 2,786 before plus exactly the 19 new tests |
| The listing evidence probe | none | run 2026-11-07, as above |
| Black, flake8 | clean | `black --check app/` clean; CI's `flake8 --select=E9,F63,F7,F82` clean; a full flake8 of the audit's files clean. At first my change missed an import (`Any` in `pt_exchanges.py`), and CI's F821 would have failed; it was fixed before the commit |

### Ambiguities for the owner

- **A1. Binance under the strict rule.**
  - **The problem.** A Binance ranking is refused for as long as Binance lists markets whose 30 days it cannot account for. Binance states no trading start or end. On the probe's day that meant 254 BREAK markets with no bar in the span, 3 with part of it, and 15 new listings.
  - **Unaffected:** the round ranks on KuCoin with the shipped Settings order (decision 1).
  - **Options:**
    - **(a)** accept: Binance cannot rank a round;
    - **(b)** add a registered exclusion for markets the exchange lists as not trading at the ranking fetch. Such a market cannot pass the history check, which needs bars to the window start with no gap over 24 hours, so its volume cannot change which coins are selected. For the new listings this leaves decision 4: they are mostly tokenized equities;
    - **(c)** accept the exchange's first-ever and last-ever kline as listing evidence. D10 rules this out.
  - **Recommendation:** (b), with decision 4's tokenized-stock exclusion. Both are §10.1 changes.
- **A2. KuCoin's `tradingStartTime` as a stated listing time.** It is exchange-stated, matched the first candle in every recent case and was never contradicted. It is treated as verified listing evidence. Confirm.
- **A3. A replacement's window.**
  - §11 now reads "after the previous *examined* window". A cancelled window is never examined, so a replacement's window may overlap the unelapsed part of a cancelled one.
  - Where the cancelled window had not started, it may keep the same dates, if its registration commit precedes their start.
  - Confirm, or require the replacement to start after the cancelled window ends.
- **A4. The replacement's ranking.** It ranks afresh (steps 0 to 2 in full) in both cases, rather than carrying the cancelled round's ranking evidence forward. Confirm.
- **A5. Round numbers.** A replacement takes the next free round number. For example, round 2 would register FDS-SIG-002's round-one candidates. This is naming only.
- **A6. Confirmation windows.** A confirmation round is refused when it overlaps "any registered earlier window" (§8.3, §16 item 9), and that includes cancelled windows as written. This is conservative. Confirm, or exclude cancelled windows.
- **A7. Results to `main`.** They are carried by checking out the round's paths from the research branch, not by a merge (§12.1, step 5). Confirm.

### Residual limitations

- **KuCoin's delisted symbols** leave its list, so they cannot be ranked. §10.1 already says so for removed pairs, but the registration can name only what the listing still shows.
- **`tradingStartTime`** is validated only for recent listings. For 5 of 25 older symbols, the candle history begins after the stated day. That does not matter within a 30-day span.
- **Re-deriving results** needs the code that produced them (the freeze tag or the fix commit). Package versions are recorded but not enforced: `verify` on another numpy or scipy could differ in the last digits, and would say so.
- **A historical correction** found at the fetch, or later by `verify --refetch`, is reported and never resolved by the code. Accepting a corrected series is the owner's call.
