# FDS-SIG-001 — Signal-Candidate Audit (per coin, per timeframe)

**Issue:** none yet. Raise "Pre-registered audit of signal candidates" and link it here.
**Target repo:** `sjackson0109/powertraderai`
**Branch:** this spec is on `docs/fds-sig-001-signal-audit`, cut from `main` at `00d9c99`. The implementation and round one's registration go on `feat/signal-audit-1`, cut from `main` after this spec is merged.
**Recommended model:** Claude Opus 5.5, effort high, for the statistics module and the report generator. Sonnet 5.5, effort high, for fetching and plumbing.
**Run log:** `docs/dev/RUN-LOG-sig-<N>.md` for round N, in the same format as batch 1.
**Status:** draft for owner review. This version adopts the owner's decisions of 2026-10-12 (§15.1) and of 2026-11-06 (§15.4), and lists the defaults it sets that still need confirming (§15.3). Implemented on `feat/signal-audit-1` (2026-11-06); round one is not registered. This document changes no trainer or strategy.
**Related:** FDS-SIG-002, `docs/dev/specs/FDS-SIG-002-round-one-candidates.md`, names round one's candidates and depends on this spec.

---

## 1. Objective

Before any new signal, feature or method is trusted enough to feed a strategy, show with evidence that it predicts
something. This spec defines a repeatable audit that any signal candidate must pass, per coin and per timeframe, before
anyone considers wiring it into a strategy or letting it act on paper trades:

> On bars no one had seen when the test was registered, does the candidate call the next bar's direction better than
> the best constant guess, by more than chance, once every test in the round is accounted for, and does that hold again
> on the next fresh window?

The audit produces a report. It never wires anything to a strategy (§14).

## 2. Background

### 2.1 What PR #154 measured

`docs/dev/TRAINER-AUDIT.md` §11.8 is the re-run after FDS-MDL Phase 2. It sits in the trainer-audit document whose
Phase 0 gating verdict was STUB, and it is part of PR #154. On held-out 1-hour bars it compared the trained model's
direction calls with the share of closes that rose, on the same pairs:

| Symbol | Hits / n | Hit rate | Up-closes / n | Up share | Predicted up |
|---|---|---|---|---|---|
| BTC | 2,644 / 5,257 | 50.3% | 2,651 / 5,257 | 50.4% | 77.2% |
| ETH | 2,697 / 5,257 | 51.3% | 2,681 / 5,257 | 51.0% | 62.1% |

The counts are derived from the rates and n in `docs/dev/trainer-port-evidence-phase2.json` (rate × n; every one is an
exact integer).

- **The held-out pairs** are the last 20% of three years (2025-05-26 19:00 to 2026-01-01 UTC), scored by a separate fit
  on the first 80%.
- **n** counts the pairs where both the predicted and the actual close move are non-zero.
- **11.8's verdict** was "REAL by FDS-MDL 3.4 ... with no skill above the up-rate base rate".
- **11.8 already reported per coin and per timeframe:** 14 rows (BTC and ETH × 1h, 2h, 4h, 8h, 12h, 1d, 1w), with
  nothing pooled.
- **Its method used more than one comparison:**
  - Wilson 95% intervals;
  - a paired 95% bound on the hit rate minus the up share (at most 1.2 points for BTC, 2.0 for ETH);
  - two benchmarks: the best constant ("always up", or "always down" where fewer closes rose) and chance at the
    model's own up/down mix;
  - a Bonferroni correction over its 14 rows. The one row that looked significant was BTC 12h, worse than chance at
    the mix with z = −2.6. After the correction it was not read as a finding.
- **What 11.8 scored:** the sign of each timeframe's predicted next-bar close move (`app/pattern_model.py`,
  `score_timeframe`). It did **not** score STRAT-003's decision rule, which compares price with the model's predicted
  bounds across timeframes (`thinker_sides`). STRAT-003's own signal has never been scored for direction.

**PR #154's backtest verdict** (Phase 4, `docs/dev/BACKTEST-REPORT-model-1.md`) was "No evidence of an edge", against
FDS-MDL's three declared criteria:

1. **Test A beats buy-and-hold** out of sample, without overlays, in at least 3 of 4 combinations.
   - Not met. Only BTC 1h did (+13.95 points).
   - BTC 4h −5.90, ETH 1h −20.34, ETH 4h −19.26.
2. **Those combinations rank at or above the 95th percentile** of the random-entry baseline.
   - Met, by BTC 1h at a rank of exactly 95.0, the threshold.
   - With 4 combinations, the chance that at least one reaches rank 95 by luck alone is roughly 1 in 5.
3. **The median walk-forward window beats buy-and-hold** in Test B.
   - Not met. PR #154 read this as the pooled median of all 36 windows, which was −11.94 points.
   - BTC 1h's own median was −11.67, the same as ETH 1h's.

Criterion 1 counts combinations, criterion 2 is judged per combination, and criterion 3 pools all windows into one
median.

### 2.2 Batch 1

STRAT-001 (at its defaults, a TEMA 12/48 crossover with an ADX ≥ 20 trend filter; DEMA is selectable) and STRAT-002
(Supertrend, ATR 10 × 3.0) gave these results (`docs/dev/BACKTEST-REPORT-batch-1.md`):

- **Against buy-and-hold:** each was ahead out of sample on 2 of 4 combinations (both 4h) and behind on both 1h
  combinations, with and without overlays.
- **Absolute returns:** all 16 out-of-sample runs lost money. The 4h runs led only by losing less, mostly in cash, in a
  market that fell by roughly 30–40%.
- **Batch 1's own conclusion:** no edge.

Every catalogue strategy (STRAT-000 to STRAT-003) is built from OHLC price history alone, and none of them uses volume.

### 2.3 What this spec adds

It makes 11.8's comparisons a standing, pre-registered pass rule:
- the right comparator, a one-sided test and a correction for the number of tests (§7, §8);
- more coins (§10);
- windows no one had seen when the round was registered (§11);
- a confirmation round (§8.3);
- the edge each test could have detected (§9).

It narrows the timeframes compared with 11.8: round one uses 1h and 4h only.

## 3. Scope and non-goals

- **Changes nothing in:**
  - STRAT-000 to STRAT-003;
  - the trainer;
  - `strategy.engine`;
  - the live coin list (BTC, ETH, XRP, BNB, DOGE).
- **No trained model is committed for any coin, BTC and ETH included.** A trained candidate is trained for every audited
  coin with the unchanged trainer. Fetching, training and scoring all happen only in the audit's sandboxed
  `POWERTRADER_HOME`.
- **Direction only.** Round one tests direction. Other targets, such as "a large move is imminent", need their own
  comparators and are out of scope until an amendment defines them (§12, step 6). For a rare event, the constant "never"
  already scores a high hit rate.
- **No action.** Acting on a pass is a separate, later decision (§14).

## 4. Data: what the repo has

The audit may use only data the repo can fetch and cache with integrity checks today:

- **The candle cache** (`app/market_data/candles.py`) stores `open_time, open, high, low, close, volume` for Binance spot
  klines, where `volume` is the base-asset volume. *(Per exchange since the owner's decision of 2026-11-06: §15.4.)*
  - The fetch keeps kline fields 0–5 only. Binance's quote-asset volume (field 7), trade count (field 8) and taker-buy
    volumes (fields 9–10) are **dropped**.
  - `app/market_data/runner_history.py` parses quote volume, but only in memory, for recent bars.
- **Not in the repo:**
  - **Historical order-book data.** `real_time_market_data.py` defines an `order_books` table that nothing writes to,
    and the order-book fetches in `pt_exchanges.py` are live only.
  - **Market-cap or BTC-dominance series.** The market cap in `llm_research_engine.py` is a random placeholder.
  - **Futures data of any kind:** funding rates, open interest or liquidations.

  `real_time_market_data.py` declares `FUNDING_RATE` and `OPEN_INTEREST` data types, a `taker_buy_volume` column and a
  futures client, but nothing implements, writes or calls them. They are not a data source.

**Eligibility rule.** A round-one candidate may use only the OHLCV and base-asset volume of coins whose candles the round
fetches and hashes. Those are the audited coins plus any **input coins** the registration lists (for example, BTC's last
closed return as an input for another coin). All inputs are read from closed bars only.

- A candidate may not claim to use a field the repo lacks. A quantity derived from OHLCV, such as close × volume, is an
  OHLCV feature and is named as what it is, never as quote volume.
- A candidate that needs any other field is **ineligible** until a separate change adds that history to the cache under
  the same integrity rules (SHA-256 per file, §12). That change is outside this spec.

## 5. Candidates are registered as rules

A candidate is registered as an exact rule, not a name. For each candidate the registration records:

1. **Inputs:** the data fields and coins it reads, all eligible under §4.
2. **Parameters:** fixed values, chosen without looking at the window (literature defaults, or values fitted only on bars
   before it). Nothing is tuned on the window, and candidates are chosen before the window starts (§11).
3. **The rule:** a function from the closed bars up to bar t to exactly one of **up**, **down** or **abstain** at
   bar t.
   - A continuous score such as RSI needs its thresholds stated.
   - An unsigned quantity (volume, volatility regime, correlation) needs a stated mapping to a direction, or it cannot
     enter round one.
4. **Its kind,** fixed by the calls the rule can emit:
   - **two-sided:** it can emit both up and down;
   - **one-sided:** only up, or only down, plus abstain.

   A long-only "enter when X" rule is one-sided. A constant caller ("always up") is registered as two-sided by
   convention, as the reference comparator. It has no discordant pairs (§7.1) when the up share is at least 50%, and
   m = n otherwise. None of its call indicators varies, so it falls below the 30-block floor (§7.4) and is NOT
   ASSESSABLE.
5. **Warm-up:** the number of bars the rule needs before its first call. Warm-up bars come from before the window and are
   never scored.
6. **A trained model** (STRAT-003 or a future one) is registered with:
   - its training span, ending at or before the window start. `LOOKAHEAD_MODEL` accepts a `train_end` equal to the open
     of the first scored bar, since that bar was not trained on.
   - its seed;
   - the exact output that becomes the call. The sign of the predicted next-bar move (what 11.8 scored) and STRAT-003's
     bounds-based LONG/SHORT are **different candidates**.

An inverted rule ("do the opposite of candidate X") is a new candidate. It may enter only a later round, registered
before that round's window.

## 6. Target, eligible pairs and calls

Round one's target is 11.8's rule, applied per timeframe.

**Pairs.**
- A pair is two consecutive bars (t, t+1) of the timeframe.
- A pair counts toward the window when bar t opens at or after the window start and bar t+1 closes at or before the
  window end.
- A pair across a data gap is skipped and counted.

**Direction.**
- Up if close[t+1] > close[t], down if close[t+1] < close[t].
- An equal close is a **tie**: it is excluded from n and counted.

**Call time.** The call for pair (t, t+1) is made at the close of bar t, from closed bars only. An input from a higher
timeframe or another coin is visible only after its bar has closed, as in FDS-MDL §6, item 3.

**Counts and symbols.**

| Symbol | Meaning |
|---|---|
| eligible pairs | pairs in the window, not skipped, not ties |
| n (calls) | eligible pairs on which the candidate said up or down |
| abstentions | eligible pairs on which it abstained |
| coverage | n / eligible pairs |
| q | the share of calls that were up |
| h | the share of the n calls whose direction matched |

**Comparators for two-sided candidates.** These are computed on the n called pairs, not on the whole window, so a
candidate that fires mostly during a strong drift gets no credit for the drift:
- p_c, the up share;
- the best constant b = max(p_c, 1 − p_c);
- chance at the candidate's mix, q·p_c + (1 − q)(1 − p_c).

**Comparators for one-sided candidates.** The comparison group is the abstained eligible pairs (§7.2). p_c, b and chance
at the mix are shown for information only.

The up share on all eligible pairs is always reported beside the comparators.

**Floors.** A row (candidate × coin × timeframe) with **n < 1,000 calls** is NOT ASSESSABLE. Each statistic also has its
own floors (§7.4).

Multi-bar horizons are out of round one. A later round may register one only with non-overlapping samples, or with
standard errors that allow for the overlap.

## 7. The tests

Each row gets two one-sided tests: a **hit-rate test** and a **magnitude test**. Below, m is the discordant count of
§7.1. The family size of §8 is written F.

### 7.1 Hit-rate test, two-sided candidates: exact paired test against the best constant

The candidate and the best constant are scored on the same n pairs, so compare them where they differ.

- **Discordant pairs:** let m be the number of called pairs where the candidate's call differs from the constant's. That
  is the down calls when p_c ≥ 0.5, or the up calls otherwise.
- **Correct calls:** let k be the number of those m on which the candidate was right.
- **The edge:** the candidate beats the constant exactly when k > m/2, and h − b = (2k − m)/n.
- **Exact p-value:** P(Binomial(m, 0.5) ≥ k). When m = 0 there is no evidence: p = 1, and the m floor (§7.4) makes the
  statistic NOT ASSESSABLE.
- **Readable summary:** z = (2k − m)/√m.

Illustration only. These are examined bars, so this is a worked example and a test fixture, with no verdict (§11):

| | Best constant | m | k | z | Exact p | Chance at mix |
|---|---|---|---|---|---|---|
| BTC 1h, 11.8 | always up, 50.4% | 1,199 | 596 | −0.20 | 0.59 | 50.2% |
| ETH 1h, 11.8 | always up, 51.0% | 1,990 | 1,003 | +0.36 | 0.37 | 50.2% |

Here k = (hits − up-closes + m)/2. Neither row would beat the constant.

### 7.2 Hit-rate test, one-sided candidates

A one-sided candidate that only says "up" makes the same calls as the constant "always up" whenever the up share is
above 50%, so it can never beat that constant. Instead it is tested on what it chooses.

- **The question:** does the up share (down share, for a down-only candidate) on its called pairs beat that share on the
  abstained eligible pairs?
- **Exact p-value:** one-sided Fisher's exact test on the full 2 × 2 table of called/abstained × up/down.
- **When there is nothing to compare:** at 100% coverage p = 1, and the abstention floor (§7.4) makes the statistic NOT
  ASSESSABLE.
- **The test is relative.** A pass also requires the called pairs' own hit rate to be above 50%. Otherwise "better
  than abstaining" could pass a rule whose calls are mostly wrong.

### 7.3 Magnitude test (both kinds)

The hit rate ignores how big the moves are, so it cannot see payoff asymmetry. In the repo's own data, win rate and
payoff are decoupled:
- **Batch 1:** the out-of-sample trend runs won 23–33% of their trades, with the average win 1.3–2.2 times the average
  loss (per-trade %).
- **STRAT-003:** it won 50–56% of its trades in Test A's four runs without overlays.

None of those runs made money out of sample. Some beat buy-and-hold only by losing less. They are per-trade figures,
not the per-bar hit rate above, but the point stands: a hit-rate test alone would miss a size edge. So each row also
tests size.

Let r = close[t+1] / close[t] − 1 on each eligible pair.

- **Two-sided candidates:** let c = +1 for an up call and −1 for a down call. The statistic is the mean over the called
  pairs of c × (r − r̄), where r̄ is the mean return on those pairs.
  - Removing r̄ means a constant caller scores exactly zero, and calls that carry no information score zero on average.
  - A pass also requires the raw mean of c × r to be above zero.
- **One-sided candidates:** the mean return on called pairs minus the mean return on abstained eligible pairs, with the
  sign flipped for a down-only candidate.
  - A pass also requires the called pairs' mean return to have the called sign.
- **For information:** each row also reports the raw mean of c × r and the round-trip cost of 30 bps (10 bps fee plus
  5 bps slippage per fill, as in batch 1).

### 7.4 Dependence between bars, and the p-value that enters Holm

A signal that persists for many bars, in a market whose drift comes in regimes, clusters hits and misses. The binomial
p-value then overstates the evidence.

How large is the effect? In a simulation of the mix-corrected z it was mild for short signal runs. It reached about
8 times the nominal false-pass rate at z ≈ 2.9 (the Bonferroni bar for 30 tests), assuming month-long ±4-point regimes
in the up share and signal runs of about 200 bars. Those regime sizes are assumptions, not measurements from the repo's
data. The simulation comes from the 2026-10-12 review of this spec and is not committed.

**Per-pair contributions.** Every statistic is the mean of per-pair contributions over the **eligible pairs in time
order**. Let E be the number of eligible pairs; I = 1 on a called pair and 0 on an abstained one, with Ī the coverage;
u = 1 on an up call; and y = 1 on an up outcome.
- The two-sided contributions are zero on abstained pairs, and their ū, ȳ and r̄ are means over the called pairs.
- The one-sided contributions use the covariance form, and their ȳ and r̄ are means over all eligible pairs.

| Test | Per-pair contribution, before centring | Its mean over the eligible pairs |
|---|---|---|
| §7.1 hit rate | (the candidate's hit − the constant's hit) × (E / n) | h − b |
| §7.2 one-sided hit rate | (I − Ī)(y − ȳ) / (Ī(1 − Ī)) | called minus abstained up share |
| §7.3 two-sided magnitude | c × (r − r̄) × (E / n) | the §7.3 statistic |
| §7.3 one-sided magnitude | (I − Ī)(r − r̄) / (Ī(1 − Ī)) | called minus abstained mean return |
| §7.5 two-sided WORSE (hit rate) | 2(u − ū)(y − ȳ) × (E / n) | h − chance at the mix |

For a down-only candidate the one-sided contributions are negated. A unit test shows that the contributions reproduce
each statistic exactly.

**Block length L.** L is set from the calls alone, never from the outcomes.
- **The call indicators:** I over the E eligible pairs, and u over the n called pairs.
- **Their autocorrelation time:** for each indicator that is not constant, over its own series of length S, compute a
  Bartlett-weighted autocorrelation time:
  - τ = max(1, 1 + 2 Σ_{k=1..M} (1 − k/(M + 1)) ρ̂_k);
  - M = min(one month of bars, ⌊S/4⌋), where one month is 720 bars at 1h and 180 at 4h.

  There is no noise cutoff, so a small but persistent autocorrelation still counts. Use the larger τ.
- **L is the larger of** one day of bars (24 at 1h, 6 at 4h) and ⌈2τ⌉.
- **A constant caller:** if no call indicator varies, L = E. Then K = 1, and every statistic is below the block floor.

A rule whose calls flicker from bar to bar while its underlying tendency drifts slowly therefore gets longer blocks. A
strongly drifting one falls below the 30-block floor and is NOT ASSESSABLE, rather than passing on a block length that
only measures how often its call flips. A very weak, slow drift can still be under-blocked. §16 item 2 tests the rule
at stated drift sizes, and if it fails there, M is raised.

**Floors per statistic.** Below any of these, that statistic is NOT ASSESSABLE for the row:
- at least **30 blocks** (K = ⌊E / L⌋ ≥ 30);
- **m ≥ 200** discordant pairs, for §7.1;
- **at least 200 abstained eligible pairs**, for §7.2 and the one-sided magnitude test.

**Two dependence-robust p-values.** Each is one-sided. Each is also computed for the opposite tail (§7.5), except for the
two-sided hit rate: its WORSE p-values come from the §7.5 contribution and Fisher's lower tail.
- **Circular block bootstrap** of the centred contributions.
  - The p-value is (1 + #{T* ≥ T}) / (B + 1).
  - B is at least 100 / α₁, where α₁ = 0.05 / F is Holm's first step: 80,000 resamples at F = 40, 320,000 at F = 160.
  - The seed is registered, and each p-value's Monte Carlo standard error is recorded.
- **Batch means** on the uncentred contributions.
  - Drop the oldest E − KL pairs, and report how many.
  - Split the rest into K non-overlapping blocks of L pairs.
  - Refer the mean of the block means, divided by its standard error, to t(K − 1).

**The p-value that enters Holm** (§8.1) is the largest of:
- hit rate: the exact p-value (§7.1 or §7.2), the bootstrap p-value and the batch-means p-value;
- magnitude: the bootstrap p-value and the batch-means p-value.

**NOT ASSESSABLE members.** A (row, statistic) that is NOT ASSESSABLE enters the forward Holm, the opposite-direction Holm
and any confirmation Holm with p = 1. That includes both statistics of a row with n < 1,000. A p-value computed below a
floor is never ranked.

### 7.5 Worse than chance

The opposite tail of §7.1 means "worse than the best constant". With any drift, an uninformative caller trails the
constant on average, so that tail mixes drift with anti-skill. WORSE is therefore judged as 11.8 judged it:

- **Hit rate, two-sided candidates:** against chance at the candidate's mix. The p-value is the largest of three:
  - the lower tail of Fisher's exact test on the 2 × 2 call × outcome table;
  - the lower tail of the bootstrap of the §7.5 contribution (§7.4);
  - the lower tail of batch means of the same contribution.
- **Hit rate, one-sided candidates:** the opposite tails of the §7.2 exact, bootstrap and batch-means p-values; the
  largest counts.
- **Magnitude:** the opposite tails of the §7.3 bootstrap and batch-means p-values, which are already drift-neutral; the
  larger counts.

The opposite-direction p-values get their own Holm procedure over F, separate from the forward one. WORSE is information
only: it is not a pass, and inverting the rule is a new candidate (§5).

### 7.6 The row's verdict

- **NOT ASSESSABLE:** n < 1,000, or both statistics are below their floors.
- Otherwise, **PASS (provisional):** either statistic survives the forward Holm (§8.1) and meets its own extra condition
  (§7.2, §7.3).
- Otherwise, **WORSE:** either statistic survives the opposite-direction Holm (§7.5).
- Otherwise, **FAIL.**
- After a confirmation round (§8.3), a provisional pass becomes **CONFIRMED** or **FAIL (not confirmed)**.

### 7.7 Why not the simpler test

The first draft compared the hit rate with the up share, with a two-sided |z| ≥ 2 and sd = √(p(1−p)/n). On this repo's
own data that rule gives wrong verdicts:

- **"Always down" passes.** It passes on ETH 1h (z = −2.90, 11.8's held-out pairs), on ETH 4h (z = −2.32) and on ETH's
  Test A manifest holdout (z = −4.37).
- **Worse than a constant passes.** BTC 12h (43.9% against 50.3%, z = −2.70) passes while doing worse than always
  guessing the same way.
- **The spread is understated.** The up share is estimated from the same pairs as the hit rate. A signal with no
  information that calls up half the time passes |z| ≥ 2 15.7% of the time (nominal 4.6%), and z ≥ 3 1.7% of the time
  (nominal 0.13%).

## 8. Multiple comparisons and confirmation

### 8.1 The family and the correction

- **The family** is every (candidate, coin, timeframe, statistic) in the round's registration. Its size is
  F = candidates × coins × timeframes × 2, or fewer if a candidate does not run on every coin. Rows later marked NOT
  ASSESSABLE stay in F.
- **The correction** is Holm's step-down at a **family error rate of 5%**, on the one-sided p-values from §7.4.
- **A provisional pass** is a row where either statistic survives (default, §15.3), as §7.6 defines.
- **Reporting:** every row shows its uncorrected and Holm-adjusted p-values.

Holm's first step is the Bonferroni bar, and its last step is p ≤ 0.05 (z ≥ 1.645):

| F (10 coins × 2 timeframes × 2 statistics × candidates) | 40 (1 candidate) | 80 (2) | 120 (3) | 160 (4) |
|---|---|---|---|---|
| First Holm step, one-sided | z ≥ 3.02 | z ≥ 3.23 | z ≥ 3.34 | z ≥ 3.42 |

A correction is required. Under no skill at all:
- **at an uncorrected one-sided z ≥ 2,** 30 tests produce at least one false pass about half the time;
- **even z ≥ 3** lets that chance exceed 5% above about 38 tests.

The first draft's rule shows this on PR #154's held-out measurements:
- **1h and 4h:** it passes 1 of the 40 (ETH 1h, model trained to 2024-10-01, z = +2.68);
- **all seven timeframes:** it passes 9 of the 138 that can be computed, all from models PR #154 found no evidence of an
  edge for.

**The tests are positively dependent.** Coins move together, and the 1h and 4h rows of one coin share one price path.
Holm stays valid under that dependence, and conservative. Clusters of chance passes are likelier than independence
suggests, so the report says so, and it never counts passes across rows into a verdict.

### 8.2 No pooling

Each row's verdict stands alone. A pass on BTC 1h says nothing about BTC 4h, about ETH, or about any other coin. Only
the bar is corrected for the family. The rows are never averaged or counted into an overall verdict.

### 8.3 Confirmation round

A provisional pass counts only after it **replicates on the next fresh window**:
- **The window** does not overlap any earlier one, and its registration is committed before it starts (§11).
- **What is re-tested:** the same candidate, parameters, direction and statistic, with the same frozen model for a
  trained candidate (no retraining).
- **The family:** one member per provisional (row, statistic), with Holm at a 5% family error rate, one-sided.
- **The rules:** §7.4's p-value rules and floors apply unchanged.
- **The outcome:** a member is CONFIRMED if it survives Holm and also meets its §7.2 or §7.3 extra condition on the
  confirmation window. Otherwise, including when it falls below a floor, it is FAIL (not confirmed).
- **No sharing:** a confirmation round and a new round never share a window (default, §15.3).

Only a CONFIRMED row may be considered for trading-result testing (§14).

## 9. Power: what a fail means

The audit can only detect large edges on windows of months, and the report must say so.

**Planning table.** At 80% power against Holm's first step, with the planning spread √(0.5/n) for a balanced two-sided
candidate, the smallest edge in hit rate over the best constant is **at least**:

| Calls n | F = 40 | F = 160 |
|---|---|---|
| 1,000 (the floor) | 8.6 points | 9.5 points |
| 2,190 (3 months of 1h, or 1 year of 4h) | 5.8 | 6.4 |
| 4,383 (6 months of 1h) | 4.1 | 4.6 |
| 8,766 (1 year of 1h) | 2.9 | 3.2 |

These are lower bounds. When the up share is near 50%, the real power at the tabled edges is lower than 80%:
- **at most about 63%,** from the constant being chosen from the same pairs (§7.1);
- **about 47–61%** once the largest-of-three rule (§7.4) also applies, lowest at the 1,000-call floor at 1h.

Detecting a 2-point edge at F = 40 needs **at least** 18,700 calls (2.1 years of 1h, 8.5 years of 4h). A 1-point edge
needs at least 75,000.

**Row figures.** A FAIL means **"no evidence of an edge at this power"**, not "no edge". So every statistic of every row
reports two figures, and every FAIL verdict line carries both (§13).

One rule applies to both figures: wherever a standard error is used, it is **the largest of the independent-sample,
block-bootstrap and batch-means standard errors**, matching §7.4.

**The minimum detectable effect** at 80% power against Holm's first step:
- **Two-sided hit rate:** by simulation for the row's own n, q, p_c and F, including the ex-post choice of constant and
  the largest-of-three rule (§7.4).
- **One-sided hit rate:** from two-proportion power at the row's called and abstained counts.
- **Magnitude:** (z for α₁ + 0.84) × the standard error.

**A 95% upper bound on the edge:**
- **Two-sided hit rate:** (h − b) + 1.96 × the standard error of h − b. The independent-sample standard error is
  √m/n, and the 1.96 allows for the constant being chosen from the same pairs. With that standard error alone, 11.8's
  rows give 1.16 points for BTC and 1.97 for ETH, matching 11.8's 1.2 and 2.0.
- **One-sided hit rate:** the difference in the called direction's share (up share for up-only, down share for
  down-only), called minus abstained, plus 1.645 standard errors. No constant is chosen here, so the one-sided
  multiplier applies.
- **Magnitude:** the statistic plus 1.645 standard errors.

## 10. Coins and timeframes

### 10.1 Coin selection

- **Universe:** Binance spot pairs quoted in USDT. This includes every symbol Binance's exchange information returns, of
  any status, at the ranking fetch (§12, step 0). *(Per exchange since the owner's decision of 2026-11-06: §15.4.)*
- **Ranking:** by 30-day quote volume, the sum of kline field 7 over the 30 UTC days of 1d klines ending on the
  **ranking date**. *(Per exchange since the owner's decision of 2026-11-06: §15.4.)*
- **Ranking date:** fixed in the registration, and before the window starts. That avoids ranking coins on volume or
  performance from inside the window, and the survivorship bias that would follow.
- **The ranking fetch** happens within 7 days after the ranking date. A pair removed from exchange information before
  that fetch cannot be ranked, and the registration says so.
- **Exclusions:**
  - stablecoins and fiat- or commodity-pegged tokens (for example USDC, FDUSD, TUSD, USDP, DAI, EURI, PAXG);
  - wrapped or staking-derivative tokens (for example WBTC, WBETH);
  - leveraged tokens: a base asset that is a listed asset's ticker plus UP, DOWN, BULL or BEAR (BTCUP, BTCDOWN), or a
    token Binance marks as leveraged. An ordinary ticker that merely ends in those letters, such as JUP, is not
    excluded.

  The registration lists each excluded symbol with its reason.
- **History:** an eligible coin has `<COIN>USDT` 1h candles with at most 0.1% of bars missing and no gap longer than
  24 hours over the span the round needs:
  - **with a trained candidate in the round:** 1,095 days before the window. That is the trainer's default span
    (`DEFAULT_WINDOW` in `app/pt_pattern_trainer.py`), as used by 11.8's three-year runs.
  - **otherwise:** from at least 30 days before the ranking date (the ranking span) up to the window start, and in any
    case covering the longest registered warm-up measured in time. For SIG-A in FDS-SIG-002, that is 19 bars × 4 hours
    = 76 hours.

  Where a coin fails, the next eligible coin by rank takes its place, and the replacement is recorded.
- **Count:** the top **10** eligible coins.
- **After registration:** coins are never replaced. A coin delisted or gapped during the window keeps its rows, which are
  NOT ASSESSABLE where they fall below a floor.
- **Evidence:** committed with the registration:
  - the full ranked list (rank, symbol, status, 30-day quote volume, included or excluded, reason);
  - the raw ranking responses and their SHA-256.

### 10.2 Timeframes

- **Round one: 1h and 4h.**
- **1d is dropped from round one,** because 1,000 daily calls need 2.7 years of window.
- **1w is excluded.** `app/market_data/timeframes.py` treats it as candle-only, so the strategy and backtest layer cannot
  use it. Its held-out counts are also tiny: 11.8 scored n = 17 for BTC and 9 for ETH, and three years hold 156 weekly
  bars.

## 11. Windows: fresh only

**Fresh** means no project evaluation has trained on, scored or reported any bar in the window, for any audited coin,
and the window starts after its registration was committed.

- **Registered before it starts.** The registration commit (§12, step 1) is dated before the window's first bar opens,
  and the audit script refuses to run otherwise.
- **One window for the round:** a single start and a single end for every coin and timeframe. The start is a 00:00 UTC
  boundary, and the end is the close time of the last outcome bar.
- **No interim looks:** the script refuses to score before the end has passed.
- **Earliest start:** the later of 2026-10-01 00:00 UTC and the first 00:00 UTC after the registration commit.
  - PR #154 and batch 1 trained on, scored or reported every BTC/ETH 1h and 4h bar from 2023-01-01 to 2026-09-30:
    11.8's held-out pairs, Test A's manifest holdouts and out-of-sample window, Test B's windows, and batch 1's
    in-sample and out-of-sample spans.
  - The bars since 2026-10-01 have been visible in the hub's charts, so a window may not start before its registration.
- **Before the window:** training, fitting and warm-up use only bars before the window starts.
- **BTC/ETH history:**
  - 11.8's numbers are cited as history (§2.1). They are neither reused as a test nor re-measured.
  - The trainer is deterministic (11.8's determinism check: 0 of 35 files differ), so re-running it on 11.8's window can
    only reproduce 11.8's numbers.
  - Any re-run on an examined window is a reproduction check and carries no verdict.
- **Disclosure:** the registration lists every earlier period whose results for the audited coins have been published.
- **Later windows:** each later round and each confirmation round uses its own new window, which starts after the
  previous window ends (§8.3).

**How long a window must run.** At full coverage, with no ties or gaps, from the window start to the close of the last
outcome bar:

| Calls | 1h | 4h |
|---|---|---|
| 1,000 | 41 days 17 hours | 166 days 20 hours |
| 2,190 | 91 days 7 hours | 365 days 4 hours |
| 4,383 | 182 days 16 hours | 730 days 16 hours |

The registered end allows a margin for ties, gaps and each candidate's expected coverage. A candidate that calls on 30%
of bars needs about 3.3 times the span. The end is a single date that trades time against power for both timeframes
(§9, §15.2).

## 12. Process

The process inherits FDS-MDL's registration discipline, including the integrity checks that made PR #154's verdict
checkable. The audit script is `docs/dev/run_signal_audit.py`.

0. **Ranking and history fetch, through public endpoints, before registration.** *(Per exchange since the owner's decision of 2026-11-06: §15.4.)*
   - Fetch 1d klines with quote volume, and exchange information. The raw responses and their SHA-256 are committed with
     the registration.
   - Fetch the 1h klines that the §10.1 history check needs, for each ranked coin down to the last one considered. The
     gap report and the files' SHA-256 are committed with the registration. The files themselves stay in the sandbox.
1. **Registration, in its own commit, dated before the window starts.**
   - The file is `docs/dev/sig-audit/round-<N>/registration.json`, plus a human-readable header at the top of the round's
     report.
   - It records:
     - the candidates as rules (§5);
     - the coin ranking evidence and the coin list (§10.1), and any input coins (§4);
     - the timeframes;
     - the window's start and end (§11);
     - the target and eligibility rules (§6);
     - F and the family error rate (§8);
     - the block-length rule, the floors, B and the seed (§7.4);
     - the previously examined periods;
     - the frozen paths (at least `app/` and the audit script);
     - the sandbox home.
2. **Code freeze, in its own commit:** the frozen paths. A commit that changes the registration may not touch a frozen
   path, as `docs/dev/run_backtest_model1.py` checks its header commits.
3. **Fetch, after the window ends,** through public Binance endpoints *(Per exchange since the owner's decision of 2026-11-06: §15.4.)*: candles for every audited and input coin, for the
   round's timeframes and for every timeframe a registered trained candidate's trainer reads. Each candle file's SHA-256 is recorded, and the run stops if a file differs from an earlier record of it.
4. **Run.** The script refuses to run, and logs an ERROR, if any of these holds:
   - the registration file is missing, uncommitted, or changed since its registration commit;
   - the registration commit is not dated before the window start;
   - a commit that changes the registration also touches a frozen path;
   - any frozen path is dirty (`git status --porcelain` over the frozen paths, as `run_backtest_model1.py` does);
   - the registration commit is not an ancestor of the freeze commit;
   - the window's end has not yet passed;
   - a trained model's `train_end` is after the window start.

   Otherwise it computes every row, applies both Holm procedures, and assigns the verdicts (§7.6).
5. **Report.**
   - The generator writes every row and verdict line.
   - It asserts each verdict against the numbers, and **re-derives it independently**, as `app/backtest/model_eval.py`
     does with `recheck_verdict`.
   - Each output records the commit, whether any frozen file changed, the registration file's SHA-256, the Python
     version, and `POWERTRADER_HOME`.
6. **Amendments.**
   - Before results: a change to the registration goes in its own owner-reviewed commit, before the window starts.
   - After results: only defect fixes, through `--supersede`, with the earlier verdict reported beside the new one.
   - A new target (§3) needs an amendment to this spec.
7. **No silent gaps.** Skipped pairs, ties and missing bars are counted and reported. A row or statistic below a floor is
   NOT ASSESSABLE, and its verdict line says so.

## 13. Report

The report for round N is `docs/dev/SIG-AUDIT-REPORT-round-<N>.md`. Its evidence is in `docs/dev/sig-audit/round-<N>/`,
including the per-pair call and return series for every row.

**One row per (candidate, coin, timeframe),** none dropped. Each row has:
- **Counts:** eligible pairs, skipped pairs, ties, calls n, coverage and q.
- **Comparators:** p_c, the best constant b, chance at the mix, and the up share on all eligible pairs.
- **The hit rate:**
  - h;
  - for two-sided candidates, m and k;
  - for one-sided candidates, the full 2 × 2 table (up and down within called, up and down within abstained).
- **Per statistic:**
  - its value;
  - for both tails: the exact p-value (hit rate only), the bootstrap p-value with its Monte Carlo standard error, and the
    batch-means p-value. For the two-sided hit rate, the opposite-tail figures are §7.5's, from Fisher's lower tail and
    the §7.5 contribution;
  - the forward and opposite-direction Holm-adjusted p-values;
  - the minimum detectable effect and the 95% upper bound (§9).
- **The magnitude conditions:** the raw mean of c × r (two-sided), the called pairs' mean return (one-sided), and the
  30 bps round-trip cost.
- **Dependence:** each call indicator's autocorrelation time τ, the block length L, the number of blocks K, the pairs
  dropped from batch means, the mean call-run length, and the lag-1 autocorrelation of the hit series.
- **The verdict** (§7.6).

**Recomputing a verdict.** The exact p-values, both Holm procedures and every verdict can be recomputed from the report
alone. The bootstrap and batch-means p-values can be recomputed from the evidence series with the registered seed.

**Verdict lines carry their caveat** in the same line, with the score, the comparator and n side by side. Every line
names the statistic and the family. PASS lines also give the Holm-adjusted p-value. FAIL lines also give the 95% upper
bound and the minimum detectable effect (§9).

For example (illustrative figures):

> **PASS (provisional, not yet confirmed; hit rate; family of 160 tests at 5%)**: hit rate 53.0% vs best constant
> 50.3% (n = 8,766; m = 4,383, k = 2,310; Holm p = 0.03).

> **FAIL, no evidence of an edge at this power (hit rate; family of 160 tests at 5%)**: hit rate 50.6% vs best constant
> 50.4% (n = 4,383); edge at most 2.3 points (95%); smallest detectable edge 5.1 points.

**The round header** states:
- F and the family error rate;
- how many rows passed provisionally, and that provisional passes are not yet replicated;
- that the tests are positively dependent: the 1h and 4h rows of one coin share one price path, and passes on several
  coins are not independent confirmations.

The header gives counts for information only. It gives no pooled, averaged or counted verdict.

## 14. Relationship to trading-result testing (out of scope)

PR #154's trading criteria are declared in FDS-MDL §7 and interpreted in `BACKTEST-REPORT-model-1.md`:
1. at least 3 of 4 symbol/timeframe combinations beat buy-and-hold out of sample without overlays;
2. those combinations rank at or above the 95th percentile of the random-entry baseline;
3. the median Test B window beats buy-and-hold. PR #154 read this as the median of all 36 windows, pooled across
   combinations.

**Why they can't be reused unchanged.** Criteria 1 and 3 aggregate across combinations, so they cannot be applied "per
coin per timeframe" as they stand. A per-combination trading test is a change, and it needs its own spec and
registration. Its scored windows must not overlap this audit's windows if the two stages are to count as independent.

**The order is fixed:**
1. directional skill, CONFIRMED under this spec (§8.3);
2. a trading-result test under a separate, future spec.

Nothing is wired to a strategy, the trainer or paper trading by this spec.

## 15. Owner decisions

### 15.1 Adopted on 2026-10-12

1. **Bar:** one-sided, with Holm over the registered test count at a 5% family error rate, plus a confirmation round on
   the next fresh window (§8).
2. **Coins:** Binance spot USDT pairs ranked by 30-day quote volume as of a date fixed before the window starts.
   Stablecoins, wrapped and leveraged tokens are excluded, and the ranked list is recorded (§10.1).
3. **1d** is dropped from round one (§10.2).
4. **Candidates:**
   - each is registered as an explicit up/down/abstain rule per bar;
   - n is the calls made, and coverage, ties and the target are stated (§5, §6);
   - any candidate whose data the repo does not have is excluded (§4).

   One departure from the literal wording: for one-sided candidates the comparison is against the abstained pairs
   (§7.2), because on their own called pairs the comparison is degenerate.
5. **BTC/ETH:** 11.8's numbers are neither reused nor re-measured. They are cited as history, and candidates are scored
   only on fresh windows (§11).
6. **Location:** this file, on its own branch from `main`.

### 15.2 To settle in the round-one registration

1. **The window end,** one date for both timeframes, trading time against power (§9, §11).
   - At 1h, 3 months detects edges of at least about 6 points, and 1 year about 3.
   - At 4h, 1 year detects about 6.
   - A short window leaves 4h rows NOT ASSESSABLE.
2. **Round-one candidates:** FDS-SIG-002 names two rules, both eligible under §4 and written as §5 requires:
   - **SIG-A:** the Chaikin Money Flow sign, 20 bars, on all 10 coins;
   - **SIG-B:** a BTC one-bar lead on the other 9 coins.

   With BTC in the top 10, F = 76 and Holm's first step is z ≥ 3.21.

   Out of round one, each for its own reason:
   - **funding rate:** it depends on the futures API, so it needs a separate data change;
   - **open interest:** the REST API keeps only 30 days, below the 1,000-call floor;
   - **liquidations:** the market-wide endpoint is dead and the other is signed, own-account only, so there is no
     reliable public source;
   - **spot taker-buy share:** it waits for a cache change.

### 15.3 Defaults this spec sets, to confirm or change before the round-one registration

1. **Either statistic qualifies** a row, with both inside the Holm family (§8.1). Choosing hit rate only, or magnitude
   only, halves F and lowers the bar.
2. **Dependence (§7.4, §9):**
   - The p-value that enters Holm is the largest of the exact, bootstrap and batch-means p-values.
   - The block length is max(one day, 2 × the call indicators' Bartlett-weighted autocorrelation time), with a maximum
     lag of min(one month, a quarter of the series).
   - The floors are 30 blocks, m ≥ 200 and 200 abstained pairs.
   - NOT ASSESSABLE members enter every Holm procedure with p = 1.
   - B ≥ 100 / α₁.
   - Every minimum detectable effect and upper bound uses the largest of the independent-sample, bootstrap and
     batch-means standard errors.
3. **The n floor** is 1,000 calls (§6).
4. **Coins (§10.1):**
   - the top 10;
   - the history span: 1,095 days when a trained candidate is registered, otherwise at least 30 days before the ranking
     date plus the longest warm-up in time;
   - the continuity tolerance: at most 0.1% of 1h bars missing, and no gap over 24 hours;
   - the ranking fetch within 7 days of the ranking date;
   - the extra exclusion classes, commodity-pegged and staking-derivative tokens;
   - the measure: the 30-day sum of quote volume.
5. **Input coins:** cross-coin inputs come from coins listed and fetched in the registration (§4).
6. **Confirmation:**
   - one family member per provisional (row, statistic), with Holm at 5%;
   - a NOT ASSESSABLE member counts as FAIL;
   - no sharing a window with a new round (§8.3). The alternative is to share it, with the 5% split 2.5/2.5.
7. **WORSE label:** judged against chance at the mix, with its own Holm. Inverted rules may enter only a later round
   (§5, §7.5).
8. **Test designs:**
   - the de-meaned magnitude statistic and Fisher's one-sided test;
   - the sign conditions on one-sided and magnitude passes (§7.2, §7.3).
9. **Registration before the window starts** (§11). This is stricter than "after the last examined bar": the bars since
   2026-10-01 have already been visible in the hub.

### 15.4 Owner decisions of 2026-11-06

1. **No single-exchange logic** ("Each exchange needs to do this - no single exchange logic allowed!"). This spec predates
   the multi-exchange design (FDS-MX-001, 2026-10-26), and its §4, §10.1, §12 and §17 name Binance. They now apply to
   every exchange alike:
   - **The round's exchange** is the first in Settings order (the primary first) whose connector lists its spot markets,
     states daily quote volume and serves the round's candle history. Every exchange passed over is recorded in the
     registration with its reason. One round's coins are ranked, history-checked and fetched on that one exchange.
   - **The universe** is every spot market that exchange lists against the quote currency the app's dollar markets use on
     it (USDT, USD), in any status, at the ranking fetch.
   - **The ranking measure** is the daily quote volume as that exchange states it: Binance's 1d kline field 7, KuCoin's
     1day candle turnover, Kraken's daily OHLC vwap × volume. An exchange that states no quote volume (Coinbase's candles
     carry base volume only) cannot rank a round: base volume times a price is not quote volume (§4).
   - **Leveraged tokens:** a token the exchange itself marks as leveraged is excluded, as Binance's marks are.
   - **Network (§17):** only the public market data of the exchanges in Settings.
2. **Every simulation runs locally, ten times over** ("Do all the 'simulations' locally, run 10x of them"): each
   simulation (the two-sided minimum detectable effect of §9, and §16 item 2's false-pass study) runs as 10 independent
   runs with registered seeds, and reports the pooled figure with each run's own beside it.

## 16. Acceptance criteria (for the implementation)

1. **Statistics module (unit tests).** Hand-worked values, independent scalar reference implementations, and a 1e-6
   tolerance, as `app/tests/test_indicators.py` does for FDS-121. It covers:
   - the exact paired test, Fisher's one-sided and lower-tail tests, and both magnitude statistics;
   - that the per-pair contributions reproduce each statistic exactly;
   - the block bootstrap with a fixed seed, and batch means;
   - the floors, and the m = 0 and full-coverage cases;
   - the block-length rule, including long blocks for calls whose tendency drifts slowly;
   - that the p-value entering Holm is the largest of the registered components, with a fixture in which each component
     is the largest in turn;
   - both Holm procedures, the minimum detectable effects, and the 95% upper bounds, with their coverage checked on
     independent data at an up share of 0.5 and on the persistent data of item 2;
   - reproducing the §7.1 illustration from the counts derived from `docs/dev/trainer-port-evidence-phase2.json` (a
     fixture for the statistics, not a measurement).
2. **No-skill rules never pass (tests).**
   - "Always up" and "always down" are never PASS. They are NOT ASSESSABLE under the block floor.
   - Near-constant callers that clear the floors also never pass, on fixtures with an up share above and below 50%. An
     example is "always up" with seeded 10% flips. This exercises the best-constant comparator itself.
   - Seeded random calls never pass.
   - Simulated no-skill data includes:
     - persistent signals (runs of 100–200 bars) over regime-drifting returns;
     - calls drawn with a probability that drifts slowly (over weeks to a month), by ±0.15 and by ±0.30 around 0.5, for
       both the one-sided hit test and the two-sided magnitude test.
   - On that data, the false-pass rate is at or below 5% per family and at or below α/F per test, within Monte Carlo
     error.
3. **No look-ahead (tests).** With post-t bars poisoned in a fixture, every registered rule's call at t is unchanged. A
   cross-timeframe or cross-coin input is read only from bars closed by t. Fitting and warm-up use only bars before the
   window.
4. **Refusals (tests).** Every refusal in §12, step 4.
5. **Rows and floors (tests).**
   - Every registered row appears in the report with all its §13 fields.
   - F includes NOT ASSESSABLE rows, and every NOT ASSESSABLE (row, statistic) enters each Holm procedure with p = 1.
   - A row with at least 1,000 eligible pairs but fewer than 1,000 calls is NOT ASSESSABLE.
   - The §7.6 verdict rule, including WORSE, is applied as written.
6. **Verdicts checked twice (test).** Holm is applied over the registered F. The generator asserts each verdict against
   the numbers and re-derives it independently.
7. **No pooling (test on a fixture report).** The report has no pooled, averaged or counted verdict, and the generator
   refuses to emit one.
8. **Verdict lines (test on a fixture report).** Each one carries its caveat in the form of §13.
9. **Confirmation (tests).**
   - A round's Holm survivor is reported only as PASS (provisional).
   - A confirmation run takes exactly the provisional (row, statistic) members as its family and applies Holm at 5%.
   - It refuses if the candidate, parameters, direction, statistic or model differ, or if its window overlaps any
     registered earlier window.
   - It labels a result CONFIRMED only if the member survives Holm and meets its extra condition (§7.2, §7.3). Otherwise
     it is FAIL (not confirmed).
10. **Evidence (tests).**
    - The ranking evidence, exclusions with reasons, replacements and raw responses are present with matching SHA-256.
    - Coins failing the history rule are excluded and replaced in rank order, tested on a fixture with a gapped coin.
    - Each candle file's SHA-256 is recorded, and the run stops on a mismatch.
    - The §12, step 5 output record is complete.
    - The registered seed, B, floors and block-length rule are the ones used.
11. **Suite and network.** No test touches the network. The full suite is no worse than `main`.
12. **Nothing else changes:** `strategy.engine`, STRAT-000 to STRAT-003, the trainer and the live coin list are untouched.

## 17. Run protocol

Same as `00-RUN-ORDER.md` and FDS-MDL §10:
- **Paper only.** No API keys are read, created or requested.
- **Network:** only public Binance market-data endpoints, and only in the ranking and history fetch (§12, step 0) and the
  candle fetch (§12, step 3). *(Per exchange since the owner's decision of 2026-11-06: §15.4.)*
- **Sandbox:** runs use a sandboxed `POWERTRADER_HOME`.
- **Commits:** one commit per step (registration, freeze, results), with the full suite no worse than before.
- **Blocked steps:** log BLOCKED with the reason. Never weaken a test or a criterion to make it pass.
