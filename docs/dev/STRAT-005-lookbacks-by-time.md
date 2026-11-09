# STRAT-005: lookbacks found by time

2026-11-08. This is follow-up 3 of the owner's review of E1. STRAT-005 stays research-only. E1's frozen results are unchanged.

## The defect

E1 found that STRAT-005 found each lookback's earlier close by counting bars back, and then required that bar to have opened exactly L days earlier. One missing bar anywhere in the 365-day window shifted the count. Every decision for up to a year then read `BARS_MISSING`: no entries and no exits.

On E1's 4h candles that held 832 of the 1,960 weekly decisions (42%). The module's docstring described the narrower, intended rule, and the spec (§5.4.3) defines the returns in calendar days.

## The fix (`app/strategies/momentum.py`)

1. **The reference bars are found by time.** Each of the 30-, 90- and 365-day reference closes is the bar whose open time is exactly the decision bar's open time minus L days.
2. **The only reason to hold is a missing reference.** A decision holds (`BARS_MISSING`) only when a reference bar is missing. A bar an hour off is not used, and no earlier or later bar stands in.
3. **The warm-up is by time.** It holds (`WARMUP`) until the candles reach back `lookback_3` days, where before it waited for `warmup_bars` of them. Without this, a gap in a coin's first year would still hold a decision whose reference bars are all there.
4. **Unchanged:**
   - the decision schedule (weekly from Monday 2020-01-06, on the bar that closes at midnight UTC);
   - the defaults (30, 90, 365, two of three, weekly);
   - the parameter rules;
   - the runner's window size;
   - the catalogue entry, including `authorisation: research`.
5. **No future bars.** The strategy sees only the candles up to the decision bar, and a later bar is never used, as before.

On a series with no gaps, both rules give the same decisions on every bar, and the warm-up ends on the same bar. A test checks this on daily, 12h and 4h series.

## Tests (`app/tests/test_strategy_momentum.py`)

| Requirement | Tests |
|---|---|
| Isolated gaps change nothing | A single missing day 1, 29, 31, 50, 89, 91, 200 or 364 days back leaves the action, the reason and all three returns unchanged |
| A missing reference bar holds | A missing day 30, 90 or 365 days back gives `BARS_MISSING` |
| Consecutive gaps | 59 missing days between two references: unchanged. The days either side of every reference missing: unchanged. A run of 11 missing days over the 90-day reference: holds |
| Timestamp boundaries | A reference bar moved an hour later or earlier is not used. Candles that start exactly 365 days back decide; one day shorter holds for warm-up. Candles from exactly 365 days back with five days missing are fewer than `warmup_bars`, but decide |
| No future observations | With the 90-day reference missing, the decision holds even though 29 later bars exist |
| Valid data | On complete daily, 12h and 4h random walks every decision matches the old bar-counting rule, and the warm-up ends on the same bar |
| 12h and 4h | On 12h and 4h bars, a lone missing bar, a missing half-day and the bar beside a reference change nothing; the bar exactly 30 days back holds |
| Parity | The live signal engine and a replayed runner agree on every closed daily bar of a series with four missing bars, two of them adjacent. Every `BARS_MISSING` is at a missing reference |

The existing test that dropped a bar 50 days back and expected a hold now drops the 90-day reference bar instead. The old test encoded the defect.

## Checked on E1's development candles (`docs/dev/strat005_gap_check.py`)

The script ran STRAT-005 at its defaults on the daily, 12h and 4h series E1 froze, with E1's costs, the £10,000 account and E1's robustness seeds for REF-RANDOM (B = 1,000).

**Safeguards:**
- **The candles:** before scoring, it checks that the candles match the SHA-256s in E1's sealed record (`experiment.json`, 9a095a59…). The candle cache is E1's, cut at 2025-05-06, and E1's loader refuses the reserved months.
- **The sandbox:** it ran in a scratch sandbox with E1's experiment folder and trial log absent, so it logged no trial.
- **No changes:** it registers and changes nothing, and tunes nothing.

It ran twice, on main (cf858a7, `strategies/momentum.py` 680764d6…) and on this branch (cc33db8f…). The outputs are in `docs/dev/strat005-gap-check/`: `old.json` (574229e5…) and `new.json` (dc6e7076…).

**The run on main reproduces E1 exactly:**
- the 12h and 4h robustness figures and their REF-RANDOM p-values match the sealed `results.json`;
- the daily figures match the sealed £10,000 cell;
- the 4h decisions held are 832 of 1,960, as E1's report gives.

### The differences

| £10,000, 0.50% + 0.05% a fill | Daily (deciding) | 12h | 4h, before | 4h, after |
|---|---|---|---|---|
| Candidate trades | 927, unchanged | 927, unchanged | 462 | 915 |
| Trades taken | 151, unchanged | 151, unchanged | 103 | 151 |
| Net | $+1,528.33, unchanged | $+1,528.33, unchanged | $-175.76 | $+1,530.73 |
| Return per capital-day | +0.1683%, unchanged | +0.1683%, unchanged | -0.0286% | +0.1694% |
| Return on the account over the period | +11.34%, unchanged | +11.34%, unchanged | -1.30% | +11.36% |
| Mean share of the account committed | 3.97%, unchanged | 3.97%, unchanged | 3.64% | 3.95% |
| Maximum drawdown | 10.14%, unchanged | 10.15%, unchanged | 7.40% | 10.45% |
| REF-RANDOM p (shown, B = 1,000) | — | 0.178, unchanged | 1.000 | 0.160 |
| Weekly decisions held for a missing bar | 0 of 1,960 | 0 of 1,960 | 832 of 1,960 | 15 of 1,960 |

- **Daily and 12h:** unchanged. The candidate trades are byte-identical, so E1's deciding results (S2, S4, G3 and M2) would be the same under the fix.
- **4h:** the row now tracks the daily one. On 4h bars STRAT-005 decides on the bar that closes at midnight, as on daily bars, so with the gaps no longer holding it the two rows nearly agree.
- **The 15 decisions still held:** each has a missing reference bar, one or two a coin.
- **Not deciding:** the 4h row is a robustness row, shown and never deciding. It still does not beat random entries (p = 0.160), and its drawdown, like the daily one, is above the 8% halt.

### 4h decisions held for a missing bar, by coin

| Coin | Before | After |
|---|---|---|
| ADA | 52 | 1 |
| AVAX | 52 | 1 |
| BTC | 94 | 2 |
| DASH | 148 | 2 |
| DOGE | 52 | 1 |
| ETH | 94 | 2 |
| LINK | 94 | 2 |
| LTC | 94 | 2 |
| SOL | 52 | 1 |
| XRP | 0 | 0 |
| ZEC | 100 | 1 |

The warm-up holds are 309 before and after.

## What this does not change

- **E1:**
  - It stays as frozen, and its report's 4h row (−$176) stays as recorded.
  - This check is not a trial and not a re-run of E1.
  - Its figures were read after E1's, from the same development candles. A later specification should list this check as an earlier exposure of those candles.
- **Authorisation:**
  - STRAT-005 stays research-only and is refused for paper and live trading.
  - Nothing here is evidence for raising its authorisation.
- **E1's freeze check:** `strategies/` is one of the packages E1's freeze hashes, so `experiment.verify("SR1-E1")` on a tree after this change reports that the code changed. E1 reproduces at its frozen code, ca38500.
