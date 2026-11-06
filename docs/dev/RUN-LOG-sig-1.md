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
5. **The ranking date.** It falls within the 7 days before the ranking fetch (§10.1), so it is set when you approve. The `rank` step refuses a fetch more than about 7 days after it.
6. **The registered seed and the MDE simulation.**
   - Seed 20261106.
   - The two-sided MDE: 10 runs × 1,000 simulated rows, with the bootstrap taken at its B → ∞ limit inside that simulation only. The audit's own p-values always use the full bootstrap.
7. **Settled by the evidence, recorded:** the block length's maximum lag stays at one month (§7.4). The false-pass study does not fail at the stated drift sizes, even for an exact one-month cycle.
