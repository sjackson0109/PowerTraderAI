# SR1-E2: a registered evaluation of the Donchian ensemble (draft)

**Status: draft for the owner's review (decision O17, 2026-11-13).** Nothing in this file has run. Nothing is frozen, no trial is logged and the lockbox stays closed. Approving this draft would authorise only the work in §8 and, after its rehearsal, the freeze and the development run. Opening the lockbox stays a separate decision (O5).

It is written under FDS-SR-001 §6 (a declared development evaluation, like E1), with the owner's decisions O3 (the stationary bootstrap) and O12 (drawdown at the lows, peak at earlier highs).

## 1. What is evaluated

| | |
|---|---|
| **Strategy** | STRAT-007 (`breakout`, daily, PR #290) with OVL-MIDLINE: enter on a new closing high of the channel; exit when the close falls below the midline of the channel; the midline stop only ratchets up |
| **Ensemble** | One member for each channel of 20, 30, 60, 90, 150, 250 and 360 days, as merged in #290. The paper's 5- and 10-day members are left out, as the backlog (3.1) set |
| **Book** | Each coin gets 1/N of the account; each member 1/7 of that, sized once at entry and never re-sized. An entry the cash cannot fund is skipped and counted (`skipped_cash`) |
| **Code** | `strategy_lab.ensemble` and `strategy_lab.runs` at the commit frozen in the record (§7) |

## 2. What this can and cannot show

**It cannot be unseen evidence.** The development months (2021-01-01 to 2025-05-06) have already been looked at for this exact strategy:
- the exploration of 2026-11-13 (PR #291): the ensemble, every member alone, and volatility sizing at 25% a year, on nine coins;
- O18's runs at 50% and 75% a year (reported separately);
- the nine-coin comparison (PR #257) ran STRAT-004 and others, not STRAT-007, on the same months and coins.

These are earlier exposures (FDS-SR-001 §6.1). They are recorded in the record before the run, with the sandbox trial log's count.

**What it adds** is a declared test with a correction for the members tested, random-entry baselines of the book's own, and F3's requirements. A pass would make the ensemble a **finalist** for one final check on the lockbox (§6), which needs the owner's separate approval. A pass here is not evidence for paper or live use: every line ends "Development only: not evidence for enabling anything" (§6.6).

**What the exploration already showed** (descriptive, one path, #291):
- **Return:** the ensemble made +279% against +216% for an equal-weight hold of the same coins. The bootstrap's 95% interval for the yearly lead ran from −33 to +44 points, and 42% of resamples showed no lead.
- **Fall:** 42% at the closes against the hold's 72%.

## 3. The family: B, the book (proposed K = 2, Holm at 5%)

| Member | Test | Passes when |
|---|---|---|
| **B1** | The ensemble's book against **REF-RANDOM-E**, random entries in each (coin, member) slice with that member's own exits (§8 item 1) | Its return per capital-day is above the draws: p = (1 + #{draws ≥ book}) ÷ (B + 1), B = 200 draws a run, 10 seeded runs pooled, 2,000 in all (the owner's rule for simulations, as the exploration) |
| **B2** | The ensemble's economics: F3's requirements (FDS-SIG-004 §6.1) at £10,000 and 0.50% + 0.05% a fill | 1. At least 100 trades and 30 in each half (otherwise "Not assessable").<br>2. Return per capital-day above 0 by `research_stats.resampling.rpcd_test` at its default (studentised, blocks ×1.5: O3). This is the family member.<br>3. Net profit above 0 in each half.<br>4. Above 0 without the most profitable coin.<br>5. **Drawdown: see decision D1.** |

**Shown, deciding nothing** (BH at q = 0.10 where a p-value exists):
- **Against an equal-weight hold:** the yearly mean daily log-return difference, with its studentised stationary-bootstrap interval (§8 item 2). See D3 for why this is not a family member.
- **Matched holding** (O19): random entries held as long as the book's trades.
- **Each member alone**, with its trades a coin a year.
- **Sizing:** the book under volatility targeting, at the target or targets D4 names.
- **PBO** across the seven members and the book.
- **Robustness** (FDS-SR-001 §6.4):
  - fees at 1.20%;
  - BTC and ETH only;
  - only the coins with bars from 2021-01-01 (survivorship);
  - the second exchange in Settings order;
  - £500 and £50. Most slices there fall below the exchange minimums and are skipped, so these mostly show that the book cannot be built at those sizes.

**Drawdown everywhere follows O12:** the trough at each bar's low; the peak at the highest high of the earlier bars. Close-based figures are shown beside it.

**Power** (§6.5): the family reports its smallest detectable effect, from `research_stats.power`, before its result.

## 4. Data, accounts and costs

| | |
|---|---|
| **Months** | Development, 2021-01-01 to 2025-05-06, with warm-up from 2020-01-01. The longest member needs 362 days of bars, so on a coin listed late its longer members start up to a year after its first bar |
| **Coins** | Decision D2 |
| **Candles** | Public, from the candle cache, cut at 2025-05-06 00:00 UTC (as E1's `cache_cut.json`), with every series' SHA-256 in the record |
| **Exchange** | The first in Settings order whose cache holds the series, recorded per series (the multi-exchange rule) |
| **Account** | £10,000 decides. The GBP/USD rate is retrieved at registration, checked against a second source and frozen (as E1's E-D6) |
| **Costs** | 0.50% taker, read through the exchange layer with its source recorded, + 0.05% slippage a fill. The venue's minimums and sell steps apply |
| **Halt** | Reported, not modelled (as E1), so a book that would have halted the trader is reported as such |

## 5. Trial count

- **Before the freeze:** the sandbox trial log of the explorations is listed as earlier exposure, with its line count.
- **The run:** about 20 trials, logged in the programme ledger (`research_engine.ledger`, #274):
  - the book;
  - the 7 members;
  - the sizing variants (D4);
  - the robustness runs;
  - the random draws, counted as E1 counted its random baselines.
- **The budget:** the strategy catalogue (B §20) allows a few dozen independent configurations for the whole programme, and E1 used 46 trials. The ensemble's members are not tuned: they are the published lookbacks of 20 days and over.

## 6. The final check on the lockbox (declared now, not authorised)

If B1 and B2 both pass after Holm, the ensemble at its frozen configuration is declared a finalist (FDS-SR-001 §6.1: at most 3 finalists a family). The check is declared now so that it cannot be shaped by the result:
- **Months:** 2025-05-06 to 2026-11-06, read once.
- **Tests:** the same two members and the same costs. The final check needs its own registration under a later spec, which FDS-SR-001 §6.7 requires for any route to `live`.
- **Opening:** only on the owner's decision (O5), recorded in one opening ledger.

**Power warning.** These are rough figures from the exploration's resamples; §8 item 4 computes them properly.
- **18 months is short.** The exploration's interval for the yearly lead over the hold had a half-width of about 0.39 over 4.3 years.
  - On 18 months, a one-sided test at 5% with 80% power could detect only a yearly log-return lead of about 0.8.
  - On the development months, it could detect only one of about 0.5.
  - The observed lead was 0.04.
- **Random entries:** the test against random entries has more trades to work with: about 220 in 18 months at the exploration's rate.

## 7. The record (frozen before any result)

As E1's `experiment.json`:
- the members and the family;
- the seeds;
- the coins, costs, account and rate;
- every code file's SHA-256, with LF line endings, including `strategies/donchian_midline.py`, `strategy_lab/ensemble.py`, `strategy_lab/sizing.py` and `market_data/gaps.py`;
- every candle series' SHA-256;
- the venue rules;
- the earlier exposures.

The evidence writer refuses once the code changes.

## 8. Work before the freeze (authorised only by approving this draft)

1. **REF-RANDOM-E.** For each (coin, member) slice: as many random entries as the slice's own, on that coin's decision bars, each exited by that member's own rule and ratchet, and replayed through the same book: same cash, same 1/N/7 slices, same skips. Seeded. Tests on hand-made series.
2. **The hold comparison.** A studentised stationary bootstrap of the mean daily log-return difference (book less hold), on `research_stats.resampling.stationary_indices` with O3's block rule ×1.5. It is calibrated on null fixtures, as O3's variants were, before the freeze.
3. **F3 for a book:** halves by entry day, and the total without the most profitable coin, summed across the coin's seven members.
4. **The power figures** of §3 and §6 from `research_stats.power`.
5. **The record and the driver:** `strategy_lab.experiment` support for a book, and a driver like `run_sr1_e1.py`.
6. **A rehearsal on synthetic candles** in its own sandbox, then the full guarded suite.

## 9. Decisions for the owner

| ID | Decision | Options | Recommendation |
|---|---|---|---|
| **D1** | **F3's fifth requirement.** A drawdown below the trader's 8% halt. Fully invested, the book fell 42%, and its replay reached the 8% level on 2021-01-22, its first month. As configured, it fails this requirement before anything else is read | (a) Keep it, and accept a certain "not viable as configured".<br>(b) Keep it, and evaluate the book at a smaller fixed share of the account. Any share chosen now is chosen after seeing the 42% fall.<br>(c) For this evaluation, replace it with: the book's drawdown (O12) below the equal-weight hold's. Report the halt, and say plainly that trading it would need the halt changed | **(c)**: B1's and B2's return-per-capital-day tests barely depend on the share invested (only through minimums); the halt question comes back only if the lockbox check passes, as a live-risk decision |
| **D2** | **Coins** | (a) The nine of the exploration: BTC, ETH, XRP, BNB, DOGE, SOL, ZEC, DASH, HYPE. BNB and HYPE come from KuCoin.<br>(b) E1's 11 coins, from Coinbase. | **(a)**: the same coins the exploration looked at, so nothing is picked from its results. Survivorship is shown (§3) |
| **D3** | **The hold comparison: a member or shown?** | (a) Shown only (K = 2).<br>(b) A third member (K = 3) | **(a)**: at the exploration's spread, it could detect only a lead of about 0.5 a year on these months. As a member it would cost the other two tests power and almost certainly read "Too few to tell" |
| **D4** | **Sizing in the record** | (a) The book's own sizing decides; volatility-sized books are shown.<br>(b) A volatility target decides | **(a)**: decide after O18's report. Choosing a target from these months would be fitting them |
| **D5** | **Approve the work in §8 and the development run** | yes / no / change | Approve after D1 to D4 |
