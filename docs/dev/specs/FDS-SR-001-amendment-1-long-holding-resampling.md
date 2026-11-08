# FDS-SR-001 amendment 1 — Resampling for long-holding strategies

**Status:** draft for the owner's review. Not approved. Until the owner approves it, nothing changes: FDS-SR-001 §6.0 stands as written.
**Amends:** FDS-SR-001 §6.0, "Block length for long trades", and the procedures that use the day-block bootstrap on a path's trades: §6.2's economic members, §6.3's paired differences and smallest detectable effect, and §6.5.
**Applies to:** experiments registered after the owner approves this amendment. Nothing registered before it changes.
**E1 (SR1-E1):** stays frozen under §6.0 as written. Its declaration, freeze, results, evidence and report are not changed, re-run or re-scored under this amendment.
**Evidence:** the simulation study in `docs/dev/sr1-bootstrap-study/`:
- `PRE-STATEMENT.md`, committed before the study script existed;
- `STUDY.md`, `tables.md`, `results.json.gz` and `diagnostics.json`;
- the script `docs/dev/sr1_bootstrap_study.py`, the table reader `docs/dev/sr1_bootstrap_report_tables.py` and the diagnostics `docs/dev/sr1_bootstrap_diagnostics.py`.

**Branch:** `spec/sr-001-long-holding-bootstrap`, from `main` at `cf858a7`.
**Authority** (owner, 2026-11-08): review alternative resampling methods, and deliver this amendment for review before any new economic evaluation is implemented or registered.
- **Not authorised:** implementing it; registering, freezing or re-running anything; changing E1.

> **Read this first.**
> - **§6.0's long-trade rule does not give dependable p-values.** On synthetic data with daily trend-like trades it rejected a true null 7% to 42% of the time at a nominal 5% (STUDY §4.2).
>   - The block length follows the longest 1% of trades, so it reaches the length of the period. With one block, every bootstrap draw equals the estimate and p = 1 ÷ (B + 1) whenever the estimate is positive.
> - **Longer or shorter blocks do not fix it** while a trade's whole profit sits on its entry day. Every length from 14 to 896 days was anti-conservative somewhere.
> - **The replacement** puts each day's change in the open positions' marked value on that day, and resamples those days in circular blocks of 14 days.
>   - The statistic, θ̂ = Σ net ÷ Σ capital-days, is unchanged.
>   - In every deciding cell it held the error rate: size at most 4.2% at a nominal 5%, and family-wise error under Holm at most 1.0%.
> - **It is conservative where profits are strongly right-skewed** (as low as 1.3%), so it can miss a real edge more often than a perfect test would. No method met the pre-stated size band in every cell. This one was selected by the pre-stated fallback, and blocks of 7 to 56 days did as well.
> - **Power stays low.** An edge of 0.10% per capital-day over 4.3 years was found 5% to 23% of the time. "Too few trades to tell" remains the usual answer.

---

## 1. What changes, and what does not

| | Before (§6.0, used by E1) | After (this amendment) |
|---|---|---|
| A path's day sums | A trade's whole net and capital-days on its entry day | Each trade's net and capital-days spread over the days it is held, by marking it to market (§2.1) |
| Block length | L = 28 × 2^k from the trades' holding times | L = 14 days, fixed (§2.2) |
| Interval reported | The percentile interval | The basic interval, which the p-value inverts (§2.3) |
| Too little data | F3's trade floor | F3's trade floor, and at least 14 blocks: a window of 183 days or more (§2.4) |
| Unchanged | | The centred p-value; circular blocks; all coins together; pairs on the same days; 10 runs of 1,000 draws seeded `seed + r`, `random()` only; the pooled p; Holm within each family; F3's other requirements |

**Not changed:**
- FDS-SIG-004 and FDS-MH-001 and their tests. They keep their own §6.0 procedures, including the 28/56-day rule.
- Tests on forecast rows, which FDS-SR-001 shows using those specs' tools, also keep them. Within FDS-SR-001 the day-block bootstrap decides only path statistics, so after this amendment one scheme covers every FDS-SR-001 test that decides.

## 2. The procedure

### 2.1 Marked day sums

For each path, the day sums are built from its trades and the closes the replay marks equity with (`signal_fusion.evaluation.replay`, at its `mark_s` grid, from the same `prices`).

**One trade.** Let:
- *a* be the amount, *p_e* the raw entry fill price and *m* = (1 − f)²(1 − e) ÷ (1 + e) the replay's cost multiplier;
- *net* the trade's net as the replay booked it (lot rounding included).

1. Its marked value at each mark *t* strictly between the entry fill and the exit fill is V(t) = a × m × close(t) ÷ p_e: what the position would realise at that close, after both fills' costs.
2. Set V(entry fill) = a and V(exit fill) = a + net.
3. Take the marks in order, with the entry and exit fills as the first and last. Each interval (t_{j−1}, t_j] carries:
   - **its change:** V(t_j) − V(t_{j−1});
   - **its capital:** a × (t_j − t_{j−1}) ÷ 86,400, in capital-days.
4. Each interval belongs to the UTC day containing its end, t_j. An end at exactly 00:00 UTC belongs to the day before, which is the day of the bar that closes then.

**The path:**
- N_d is the sum of the changes of every trade's intervals that belong to day d, and C_d the sum of their capital.
- The days run from the period's first day to its last, with zeros where nothing is held.
- **The totals are exact:**
  - the changes telescope, so Σ_d N_d equals the sum of the trades' nets;
  - Σ_d C_d equals the sum of their capital-days;
  - θ̂ = Σ N_d ÷ Σ C_d is the path's return per capital-day, unchanged.
- **Costs are counted once.** They enter through m on the first interval and through *net* on the last, and nowhere else.
- **The unsellable remainder** (FDS-SR-001 §5.10) is outside the trade's net, so it is outside these sums too.

**Paired statistics.** A paired difference (for example a path with a filter against the same path without it) puts both paths' (N_d, C_d) side by side on the same days: one `DaySums` with four columns, so both are always resampled on the same days.

### 2.2 The bootstrap

- `signal_fusion.evaluation.bootstrap.test_statistic` on the marked `DaySums`, with `block = 14`.
- Everything else is FDS-SIG-004 §6.0 unchanged:
  - circular blocks;
  - ⌈N ÷ 14⌉ blocks a draw, each starting on a uniform day and wrapping round the period's end;
  - all coins together;
  - the ratio of summed columns;
  - 10 runs of 1,000 draws, run r seeded `seed + r`, `random()` only;
  - the deciding p pools the 10,000 draws.
- **L is a constant.** It does not depend on the trades' holding times or on any other property of the data.
- **The smallest detectable effect** (FDS-SR-001 §6.3) is taken from the same draws, by FDS-SIG-004's formula.

### 2.3 The p-value and the interval

- **The p-value** is the centred p-value, as today: p = (1 + #{b : θ*_b − θ̂ ≥ θ̂}) ÷ (B + 1).
- **The reported interval** is the basic interval, from the same draws. Let c_b = θ*_b − θ̂ and k = ⌊α(B + 1)⌋ with α = 0.05:
  - the lower 95% bound is θ̂ − c₍k₎, where c₍k₎ is the k-th largest c_b;
  - the upper 95% bound is θ̂ − c₍k₎′, where c₍k₎′ is the k-th smallest;
  - together they form the two-sided 90% interval.
- Then "p ≤ 5%" holds exactly when the lower bound is above 0. The percentile interval, used today, inverts a different statistic and disagreed with p in up to 2.8% of replications (STUDY §4.1).
- The interval is shown, never deciding, and is not adjusted for Holm.

### 2.4 Not assessable

A bootstrap member reads "Not assessable", with the counts, and computes no p-value when any of these holds (fail closed):
1. **F3's trade floor** is not met: fewer than 100 closed trades, or fewer than 30 in either half (FDS-SIG-004 §6.1, unchanged).
2. **The window is shorter than 183 days,** that is fewer than 14 blocks of 14 days.
   - The study found the test within its error band at every window it tried, down to 183 days, which was its shortest (STUDY §4.7). Nothing shorter was tested.
3. **The marked series cannot be built:** a held mark has no close, or the day sums fail to add up to the trades' nets or capital-days within 1e-9 of their scale. There is no fall-back to entry-day attribution.

A not-assessable member enters its family's Holm procedure with p = 1, and the family's K does not change. It therefore cannot pass, and cannot make another member easier to pass.

### 2.5 Families and multiple comparisons

- **Families and K are declared at registration and frozen, as today** (FDS-SR-001 §6.2). Holm at 5% applies within each family.
- **Every bootstrap member uses §2.1 to §2.4.** A family's non-bootstrap members (REF-RANDOM, R3) are unchanged.
- **Holm is valid whatever the dependence between members,** provided each member's p-value is valid.
  - In the study, four correlated members (a strategy, the same strategy with a random filter, a second strategy on the same days, and that one filtered) gave a family-wise error of 0.8% to 1.0% under this procedure.
  - Under §6.0's rule it was 11.8% to 45.3% (STUDY §4.4).
- **A conservative member makes Holm more conservative, not less.**

### 2.6 What the experiment record declares

Every experiment registered under this amendment records:
- the scheme ("FDS-SR-001 amendment 1: marked days, circular blocks of 14 days");
- the floor of §2.4;
- the interval of §2.3.

The registration code refuses a new registration that names §6.0's long-trade rule. E1's record is not touched.

## 3. Why: the evidence in brief

All figures are from `docs/dev/sr1-bootstrap-study/STUDY.md`, on synthetic data only:
- 11 coins over 1,586 days;
- a GARCH-t common factor, with and without a 365-day bear market;
- heavy-tailed holds with medians of 10 to 120 days;
- 50 to 300 trades;
- and STRAT-004's and STRAT-005's own rules on simulated closes.

There were 10 runs of 300 replications a cell. The method was chosen by a rule written and committed before the study ran, and blind to E1's results.

| Method (22 deciding null cells) | Size at nominal 5%: lowest – highest | Holm FWER, 4 members: highest | 90% interval coverage: worst cell | Power at 2.5 × SD₀: lowest cell |
|---|---|---|---|---|
| §6.0's rule (entry day) | 7.1 – 42.0 | 45.3 | 0.0 | 87 |
| The rule capped at 112 days | 5.4 – 9.7 | 5.3 | 60.8 | 87 |
| Entry day, fixed 28 days | 5.3 – 14.9 | 7.3 | 53.4 | 88 |
| Entry day, Politis–White | 6.5 – 18.7 | 9.6 | 49.0 | 90 |
| Trades resampled independently | 7.2 – 20.8 | 14.6 | 43.5 | 91 |
| Episodes of overlapping trades resampled | 5.2 – 47.1 | 52.5 | 0.0 | 84 |
| **Marked days, 14-day blocks (this amendment)** | **1.3 – 4.2** | **1.0** | **87.6** | **82** |
| Marked days, 28-day blocks | 1.6 – 4.2 | 0.9 | 86.8 | 83 |
| Marked days, 448-day blocks | 3.1 – 8.5 | 5.6 | 76.4 | 87 |

Coverage is for the basic interval. Power is comparable only at matched size: the methods with higher power reject too often under the null.

**Why the replacement works:**
- Entries are decided on closed bars. With no edge, a day's change in the positions' marked value is unpredictable from earlier days, however long the trades last.
- A day's common shock stays inside one day, with every coin together.
- The bootstrap's spread then matches the estimate's true spread: a median ratio of 0.99 over the deciding cells, against 0.54 to 0.75 for entry-day methods (STUDY §4.6).

**Why it is conservative where profits are skewed:**
- A winning position's marked value grows, and so do its daily moves. A replication with a high θ̂ therefore also has a wide bootstrap spread, and a one-sided upper test rejects it less often.
- Size fell to 1.3% to 2.2% where positions are held most of the time (a 94% time in market) and in the TSMOM cells. This costs power, never error control.

**The choice of 14 days:**
- The pre-stated rule required size within [2.5%, 7.5%] in every deciding cell. No method qualified.
- The pre-stated fallback took the smallest worst-case size: 14 days at 4.20%, then 28 days and the stationary bootstrap at 4.23%, 7 days at 4.27% and 56 days at 4.30%.
- Those differences are one or two replications in 3,000. The study does not distinguish blocks of 7 to 56 days (decision AM1-D2).

## 4. Acceptance (for the later implementation)

### 4.1 Unit tests

1. **Hand-worked marks, daily bars.** One coin, one trade: entry fill at the open of bar 1, closes 100, 110 and 90, exit at the open of bar 4, f = 0.5%, e = 0.05%.
   - Every interval's change and capital matches hand values.
   - Σ N_d equals the replay's net, and Σ C_d its capital-days.
2. **Costs once.** A trade at constant prices gives a × (m − 1) on its first interval, 0 on every later interval, and its lot-rounding residue, if any, on its last.
3. **Days.**
   - An hourly trade that crosses midnight UTC splits its intervals between the two days.
   - A mark or fill at exactly 00:00 UTC belongs to the day before.
   - A trade entered and exited inside one day puts everything on that day.
4. **The remainder.** With `Costs.base_increment`, the day sums add up to the trade's own net, which excludes the unsellable remainder.
5. **θ̂ unchanged.** For every path in the M4 test fixtures, θ̂ from the marked sums equals the path's return per capital-day to 1e-12.
6. **The bootstrap call.**
   - `test_statistic` is called with `block = 14` whatever the holding times. A test with holds of 1,000 days still uses 14.
   - The result is reproducible from its seed, and the paired form shares days.
7. **The interval.** On random draws, "p ≤ 0.05" equals "basic lower bound > 0" in every case, including ties and B + 1 not a multiple of 20.
8. **The floor.** Each of these gives "Not assessable" with its counts, no p-value, and p = 1 in Holm:
   - 99 trades;
   - 29 trades in one half;
   - a window of 182 days;
   - a missing close under an open position;
   - a deliberately broken day sum.

   A window of 183 days with enough trades gives a p-value.
9. **Fail closed in the record.** A new registration naming §6.0's rule is refused. E1's frozen record still loads unchanged.

### 4.2 Synthetic tests, before the first registration under this amendment

These are run once and recorded in the run log, not in the unit suite.

10. **Equivalence with the study.** Convert synthetic replications from `docs/dev/sr1_bootstrap_study.make_data` into candles and trades:
    - cells exo(150, 30) base, exo(100, 120) bear and donchian bear;
    - seeds 20261108 to 20261110, 20 replications each.

    The implementation's marked day sums must equal the study's (`nm`, `cm`) to 1e-9.
11. **Size through the implementation's own code path.**
    - On exo(150, 30) base and bear, exo(100, 120) base, donchian bear and tsmom bear, 10 runs of 300 replications, the full 10 × 1,000 draws. Each run is seeded as in the study.
    - Size at nominal 5% must be at most 7.5% in every cell. Above that, the implementation fails and nothing is registered.
    - The lower side is reported. The study expects 1% to 4.5%.
12. **Family-wise error.** On the study's three family-wise cells, Holm over the four members must give at most 7.5%.
13. **The degenerate case.** With a block as long as the window, the call is refused, never answered with p = 1 ÷ (B + 1).

## 5. What this amendment does not fix

- **One market history.** Under persistent drift regimes, the variance of a 4.3-year estimate is dominated by a few regime spells, and no resampling of one history can estimate it. The study's regime stress test held at 3.4% to 5.0%, but stronger or longer regimes would not (FDS-SR-001 §9 item 4).
- **Conservative tests for skewed profits.** The test can miss real edges more often than a perfect test would. A studentised (bootstrap-t) version might recover some power; it was not tested and is not proposed.
- **Low power.** "Too few trades to tell" remains the usual verdict for daily strategies. Each family still reports its smallest detectable effect before its result (FDS-SR-001 §6.5).
- **F3's other requirements** are unchanged and are not bootstrap tests: the trade floor, profit in each half, profit without the best coin, and the drawdown against the halt level.
- **REF-RANDOM and R3** (families S1, S2, G and M) are unchanged.
- **FDS-SIG-004 and FDS-MH-001** are not amended, including FDS-SIG-004's 56-day rule and its percentile intervals. Applying the same change there would need their own amendments (decision AM1-D6).
- **E1** is unchanged and is not re-scored.
  - Re-asking E1's economic questions under this amendment would be a new experiment: declared and registered, with E1's reading of the development period recorded as an earlier exposure (decision AM1-D7).
  - No such experiment is authorised.
- **The rest of FDS-SR-001 §9:**
  - survivorship;
  - costs untested in the literature;
  - lockbox reuse;
  - paper is not live;
  - and the safety limits it records: the halt does not exit, an entry raised to the exchange minimum can exceed the coin's budget, and the strategies have no stop by default.

  No result under this amendment makes a small account safer.

## 6. Decisions for the owner

| # | Decision | Recommendation |
|---|---|---|
| AM1-D1 | Replace §6.0's long-trade rule with marked day sums and fixed circular blocks, for experiments registered after approval | Approve. Every entry-day method failed. E1 stays under the old rule |
| AM1-D2 | The block length | 14 days, as the pre-stated fallback selected. 28 days, FDS-SIG-004's length, did as well in the study (worst size 4.23% against 4.20%) and would be equally supported. The choice cannot be informed by any strategy's results |
| AM1-D3 | The not-assessable floor: F3's trade floor, plus at least 14 blocks (183 days) | Approve. It is the shortest window the study tested; shorter windows stay "Not assessable" until tested |
| AM1-D4 | Report the basic interval instead of the percentile interval | Approve. It agrees with the p-value by construction |
| AM1-D5 | A not-assessable member enters Holm with p = 1, K unchanged | Approve. It fails closed |
| AM1-D6 | Propose the same change to FDS-SIG-004 for its own tests | Not proposed here. Its 1h trades are short, so its rule rarely bites. A separate amendment, if wanted |
| AM1-D7 | Declare a new experiment re-asking E1's economic questions | Not authorised by this amendment. If wanted, it is a new registration with E1 recorded as an earlier exposure of the development period |

## 7. Exact text for FDS-SR-001 §6.0, on approval

Replace the paragraph that begins "**Block length for long trades**", with its two bullets and the "Proposed, not approved" pointer, by:

> **Path statistics: marked days** (amendment 1, approved on …; experiments registered from then on).
> - A path's day sums are its trades' changes in marked value and their capital, day by day, as amendment 1 §2.1 defines them. They add up to the trades' nets and capital-days exactly, so return per capital-day is unchanged.
> - The day-block bootstrap resamples them in circular blocks of L = 14 days, a constant. Everything else is FDS-SIG-004 §6.0 unchanged.
> - The interval reported is the basic interval (amendment 1 §2.3).
> - A member reads "Not assessable", and enters Holm with p = 1, below F3's trade floor, in a window under 183 days, or where the marked series cannot be built (amendment 1 §2.4).
> - **E1** was registered under the earlier rule: L = 28 × 2^k days, k the smallest integer ≥ 0 for which at most 1% of the family's scored trades last longer than L ÷ 2 days, with entry-day sums. It stays frozen under that rule.

**If AM1-D2 chooses 28 days,** replace 14 by 28 in this text and in §2.2, §2.6 and §4. The window floor stays at 183 days, which is 7 blocks of 28.
- The study ran M-28 in the floor cells too (`tables.md`). Its size was at most 5.3% in the base cells and 7.2% in the bear cells, so the pre-stated floor rule, applied to M-28, also gives 183 days.
- That application was made after the selection, and is recorded as such.

## References

The study's references (`docs/dev/sr1-bootstrap-study/STUDY.md`), in particular:
- Künsch 1989;
- Politis and Romano 1992 and 1994;
- Politis and White 2004, with Patton, Politis and White 2009;
- Hall and Wilson 1991;
- Bradley 1978;
- Holm 1979;
- Johnson 1978.
