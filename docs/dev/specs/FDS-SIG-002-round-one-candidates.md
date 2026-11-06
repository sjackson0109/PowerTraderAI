# FDS-SIG-002 — Round-One Signal Candidates

**Issue:** none yet. Link it to FDS-SIG-001's issue when that is raised.
**Target repo:** `sjackson0109/powertraderai`
**Branch:** `docs/fds-sig-001-signal-audit`, together with FDS-SIG-001. The audit code and round one's registration go on `feat/signal-audit-1` (FDS-SIG-001's header).
**Recommended model:** Claude Sonnet 5.5, effort high: two small rules and their tests, built inside FDS-SIG-001's implementation.
**Run log:** none of its own. Round one is logged in FDS-SIG-001's run log, `docs/dev/RUN-LOG-sig-1.md`.
**Status:** draft for owner review. This version adopts the owner's decisions of 2026-10-12 (§6). Implemented on `feat/signal-audit-1` (2026-11-06, `app/signal_audit/round_one.py`); round one is not registered. This document changes no trainer or strategy.
**Depends on:** FDS-SIG-001, `docs/dev/specs/FDS-SIG-001-signal-candidate-audit.md`. This spec defines no audit process. It defines the round-one candidates that FDS-SIG-001 §15.2 item 2 refers to, written as the rules FDS-SIG-001 §5 requires, for copying into round one's registration (FDS-SIG-001 §12, step 1).

---

## 1. Objective

Name round one's candidates as exact, eligible rules, and record why other candidates are not in round one.

Every candidate here must meet FDS-SIG-001's requirements:
- **§4:** only the OHLCV and base-asset volume of coins the round fetches and hashes;
- **§5:** an up/down/abstain rule with fixed parameters;
- **§6:** round one's target, the direction of the next bar.

## 2. What the evidence supports, and what it does not

### 2.1 This repo

- **Only one OHLC-derived signal has ever been scored for direction:** the pattern model's sign of the predicted
  next-bar move, in TRAINER-AUDIT §11.8. It showed no skill above the best constant (FDS-SIG-001 §2.1).
- **Trading results, not direction:** batch 1 and PR #154's Test A/B measured the trading results of price-only
  strategies (STRAT-001 to STRAT-003), and found no edge (FDS-SIG-001 §2.1, §2.2). They did not score per-bar
  direction.
- **Never scored for direction:** no RSI, SMA, ADX, ATR, DEMA/TEMA or Supertrend signal, and no volume-based signal. No
  catalogue strategy uses volume.

Round one therefore starts from no prior directional result for any candidate class, except the pattern model's.

### 2.2 Herremans and Low, arXiv 2211.08281 (2022)

**What it is.**
- A model forecasting next-day **volatility spikes** for **Bitcoin** on daily data.
- The label counts a day as a spike when volatility is at least 1.0 **and** the log return is positive, so it is an
  upside-spike target.
- Inputs:
  - market data: daily OHLCV, market cap, open interest, funding rates, and **perpetual-swap** taker buy and sell volumes
    and ratios;
  - CryptoQuant on-chain and exchange-flow data;
  - long and short liquidations;
  - @whale_alert tweet data;
  - simple technical indicators.
- The out-of-time test window runs from 2020-11-12 to 2021-09-21.

**What it supports.** In its feature ablation, the paper names taker buy volume, high-low spread and volume as
recurring important features (p. 19, Table 5). Its taker buy volume is perpetual-swap volume, not spot.

**Limits.**
- The target is a next-day upside volatility spike, a rare event, not next-bar direction.
- The bars are daily, not 1h or 4h.
- It covers one asset and one test window.
- Ablation importance is not out-of-sample skill.

**How this spec uses it.** Only as a reason to pick a range-and-volume rule for candidate A (§3.1). It is not evidence
that candidate A has directional skill on 1h or 4h bars, and nothing in this spec relies on its headline scores.

### 2.3 Sources considered and not relied on

- **arXiv 2504.18982 ("On Bitcoin Price Prediction", posted 2025, written in early 2022).** None of its figures is used
  here:
  - its average accuracy is reported with no comparator or significance test, and in the four confusion matrices it
    shows, accuracy is below the share of the most common class;
  - its backtest sums signed daily returns with a same-bar look-ahead;
  - its unit-root counts concern price levels, not return predictability.
- **The claim that less liquid coins are less efficient.** It is not used. Coin selection stays FDS-SIG-001 §10.1's
  volume-ranked rule (owner decision 2 of 2026-10-12).

## 3. Round-one candidates

Both candidates are registered as written below, with no parameter left open. Both are two-sided, run on 1h and 4h
(FDS-SIG-001 §10.2), and call at the close of bar t from closed bars only (FDS-SIG-001 §6).

### 3.1 SIG-A: Chaikin Money Flow sign, 20 bars

- **Inputs:** the coin's own high H, low L, close C and base-asset volume V, on the same timeframe.
- **Parameter:** length **20**. Published sources give 20 or 21 as Chaikin's default, and this spec fixes 20.
- **Definition at bar t:**
  - money-flow multiplier MFM_i = ((C_i − L_i) − (H_i − C_i)) / (H_i − L_i), with MFM_i = 0 when H_i = L_i;
  - CMF_t = Σ (MFM_i × V_i) / Σ V_i, both sums over the 20 bars i = t − 19 … t.
- **Rule:**
  - **up** if CMF_t > 0;
  - **down** if CMF_t < 0;
  - **abstain** if CMF_t = 0, if Σ V_i = 0, or if any of the 20 bars is missing.
- **Kind:** two-sided.
- **Warm-up:** 19 bars before the first call, taken from before the window.
- **Coins:** all 10 audited coins.
- **Expected coverage:** close to 100%.
- **Block length:** CMF's calls persist, because consecutive 20-bar sums overlap. Under FDS-SIG-001 §7.4 its block length
  comes out at about 30 bars, and about 38–40 after a run of abstentions caused by a data gap. To clear the 30-block
  floor, SIG-A rows therefore need roughly **1,200–1,500 eligible pairs** per timeframe, not 1,000. At 4h, 1,500 pairs
  is about 250 days.
- **What it is:** a range-and-volume indicator built from OHLCV. It is not a measure of taker flow, which the cache does
  not hold (FDS-SIG-001 §4).

### 3.2 SIG-B: BTC one-bar lead

- **Inputs:** BTCUSDT's close on the same timeframe. BTC is listed as an input coin in the registration (FDS-SIG-001 §4)
  and is fetched and hashed whether or not it is among the audited coins. *(Since FDS-SIG-001 §15.4, 2026-11-06: BTC's
  close on the round's exchange, in that exchange's dollar market.)*
- **Parameters:** none beyond the one-bar lag.
- **Rule at bar t,** for an audited coin other than BTC:
  - **up** if BTC close[t] > BTC close[t − 1];
  - **down** if BTC close[t] < BTC close[t − 1];
  - **abstain** if they are equal, or if BTC's bar t or t − 1 is missing.

  BTC's bar t closes at the same moment as the coin's bar t, so it is closed when the call is made.
- **Kind:** two-sided.
- **Warm-up:** 1 bar.
- **Coins:** every audited coin except BTC: 9 coins when BTC is in the top 10, 10 otherwise. On BTC itself the rule would
  be BTC's own one-bar momentum, which is a different candidate.
- **Expected coverage:** close to 100%, less BTC's tied bars.

### 3.3 Family size and power

**Family size.** With BTC in the top 10, F = (10 + 9 coins) × 2 timeframes × 2 statistics = **76**. The first Holm step
is z ≥ 3.21 (α₁ = 6.6 × 10⁻⁴), and the bootstrap needs B ≥ 152,000 (FDS-SIG-001 §7.4, §8.1). If the owner chooses one
statistic (FDS-SIG-001 §15.3 item 1), F = 38 and the first step is z ≥ 3.01.

**Power.** Both rules call on nearly every bar, so n is close to the number of eligible pairs. The method of FDS-SIG-001
§9's planning table (80% power against Holm's first step, spread √(0.5/n)) gives these smallest detectable edges in hit
rate over the best constant at F = 76. They are lower bounds, for the reasons FDS-SIG-001 §9 gives.

| Calls n | Smallest detectable edge (F = 76) |
|---|---|
| 1,000 (the floor; SIG-A rows may be NOT ASSESSABLE here, §3.1) | at least 9.1 points |
| 2,190 (3 months of 1h, or 1 year of 4h) | at least 6.1 |
| 4,383 (6 months of 1h) | at least 4.3 |
| 8,766 (1 year of 1h) | at least 3.1 |

The window end is a registration decision (FDS-SIG-001 §11, §15.2 item 1). It should allow for SIG-A's block floor
(§3.1).

## 4. Not in round one

| Candidate | Why not in round one | What it would take |
|---|---|---|
| Spot taker-buy share (taker-buy base volume / volume) | Binance spot candles carry taker-buy volume (fields 9–10) for their full history, but the cache drops it (FDS-SIG-001 §4) | The side-file cache change in §5. **Kept as a later-round candidate.** It has no support from 2211.08281: that paper's taker ratio was not among its important features. |
| Funding rate | Futures API data, not in the repo | A separate data change: a fetcher for the futures host, a spot-to-perpetual symbol map, and alignment to bar closes. Funding settles every 8 hours (4 for some symbols), so 1,000 1h calls see only about 125 distinct values (about 250 for a 4-hour symbol). Dropped from round one. |
| Open interest | Futures API data. The REST API keeps only the latest 30 days, so a fetch after the window gives at most 720 1h or 180 4h pairs, below the 1,000-call floor. | Backfill from Binance's bulk archive (data.binance.vision), if its coverage of each audited coin's perpetual is verified, or forward collection. Dropped from round one. |
| Liquidation volume | No public history covering any fresh window. The bulk archive's USDT-M liquidation snapshots stop after 2024-03-31, and they are sampled. The market-wide endpoint has refused requests since 2021-04-27. The remaining endpoint is signed and returns only the caller's own orders, which FDS-SIG-001 §17 rules out. The public stream sends at most one liquidation per symbol per second, so it undercounts. | Nothing reliable. **Dropped.** |
| STRAT-003's bounds-based LONG/SHORT | Eligible, but it needs ten models trained in the audit sandbox (FDS-SIG-001 §3). It also brings in the 1,095-day history rule for every coin (FDS-SIG-001 §10.1), which could change the coin list. | Ten models trained with the unchanged trainer in the audit sandbox. A later round. |
| Order-book imbalance | No historical order-book data in the repo. Binance's public REST gives live depth only. | Forward collection. |
| Price-shape indicators (RSI, MACD, Bollinger Bands, Stochastic) | Not ruled out by evidence, since none has been scored for direction here (§2.1). Left out to keep round one small: each candidate adds about 40 tests to F. | A later round, as rules under FDS-SIG-001 §5. |
| Sentiment / NLP signals | No data source in the repo | A new data source. |
| A volatility target ("a large move is imminent") | Outside round one (FDS-SIG-001 §3). At event shares of 2–10%, the constant "never" already scores 90–98%. | An amendment to FDS-SIG-001 (§12, step 6) defining the event, its comparator (for example a Brier score against the base-rate forecast), n and its own Holm family. |

## 5. The side-file cache change (a later round, outside this spec)

What it would take to make spot taker-buy share eligible. This is a separate change, specified and reviewed on its own:

1. **Fetch:** keep kline fields 7–10 (quote volume, trade count, taker-buy base volume, taker-buy quote volume) from the
   same `/api/v3/klines` call `app/market_data/candles.py` already makes.
2. **Store** them in a separate side file per symbol and timeframe, hashed with SHA-256 like the candle files.
   `CANDLE_COLUMNS` and the strategy interface stay unchanged.
3. **Re-fetch the full history.** The incremental cache fetches only missing time ranges, so it would never backfill new
   columns into existing files.
4. **Eligibility:** once committed under FDS-SIG-001 §4's integrity rules, the fields become eligible.
5. **Quote volume:** the side file would also make quote volume available to candidates. The coin ranking does not
   need it: FDS-SIG-001 §10.1 already reads quote volume from the raw responses fetched in its §12, step 0.

## 6. Owner decisions (2026-10-12)

1. **Round one** is SIG-A (CMF sign, length 20, all 10 coins) and SIG-B (BTC one-bar lead, the other 9 coins) (§3).
2. **Dropped from round one:**
   - funding rate, because it depends on the futures API;
   - open interest, because of the 30-day retention;
   - liquidations, because the endpoints are dead.
3. **Spot taker-buy share** stays a later-round candidate, once the side-file cache change is built (§4, §5).
4. **STRAT-003's bounds signal** stays out of round one until 10 models are trained (§4).
5. **Disputed claims removed:** every claim from arXiv 2211.08281 and 2504.18982 that the 2026-10-12 review disputes is
   gone. Only what the review confirmed remains (§2.2, §2.3).

## 7. Acceptance

**Procedural.** This spec is accepted when round one's registration (FDS-SIG-001 §12, step 1) copies §3's two rules
verbatim, with their inputs, parameters, thresholds, kind, warm-up, coins and BTC as an input coin. F is computed from
the registered coin list as in §3.3.

**Implementation.** FDS-SIG-001 §16 governs the implementation, plus:

1. **CMF unit tests.** CMF matches hand-worked values and an independent scalar reference at a 1e-6 tolerance, as
   `app/tests/test_indicators.py` does. The tests cover H = L, Σ V = 0 and a missing bar.
2. **BTC-lead tests.** It abstains on a tie and on a missing BTC bar, and it is never computed for BTC itself.
3. **No look-ahead,** as FDS-SIG-001 §16 item 3 requires. Neither rule's call at t changes when bars after t are
   poisoned, and SIG-B reads BTC only from bars closed by t.
