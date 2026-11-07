# A: Trading-strategy research for PowerTraderAI

**Date:** 2026-11-07.
**For:** FDS-SR-001, the specification this report supports.
**Scope:**
- long-only spot crypto;
- 11 to 13 large coins, on the exchanges in Settings (Coinbase is the primary exchange);
- closed candles from 1 hour to 1 day.

**Costs used throughout:**
- the account's taker fee of 0.50% plus 0.05% slippage, which is 0.55% a side and 1.10% a round trip;
- Coinbase's lowest published tier, 1.20% taker (`DEFAULT_TRADING_FEES`, `pt_exchange_abstraction.py:268-273`), which is 1.25% a side and 2.50% a round trip.

These are the app's own figures. Coinbase's fee pages could not be opened to re-check them on 2026-11-07.

**How to read it:**
- Each claim is labelled:
  - **[P]** a published finding (peer-reviewed, unless marked "WP" for a working paper);
  - **[PR]** a practitioner or institutional claim;
  - **[R]** this report's own reasoning or arithmetic.
- The reference list (§12) says for each source whether its full text (FT), only its abstract (A), or only a secondary summary (S) was read.
- Short quotations from the full texts were checked against the saved texts.

> **Read this first.**
> - No published study tests a crypto trading rule at costs as high as this account's 0.55% a side. The highest level found is 0.50% a trade (Zarattini, Pagani and Barbon 2025, a working paper).
> - Historical performance in this report is never evidence of future profit. The evidence decides only which strategies are worth the cost of testing, and how.

---

## 1. Summary

| Family | Evidence, in general | Evidence, in crypto | Cost tolerance at 1.10% a round trip | Long-only spot | Verdict for PowerTraderAI |
|---|---|---|---|---|---|
| Time-series momentum, moving-average trend | Strong in diversified futures over a century (Moskowitz, Ooi and Pedersen 2012; Hurst, Ooi and Pedersen 2017). Contested: Huang et al. 2020; Kim, Tse and Wald 2016 | Positive but short samples, mostly before costs (Liu and Tsyvinski 2021; Detzel et al. 2021). Out of sample, mixed (Hudson and Urquhart 2021; Wei et al. 2024) | Only slow rules (weeks to months, a few trades a year) | Good: most futures returns come from long signals (NBIM 2014) | **Test**, at daily bars and long horizons |
| Breakout (price channel, Donchian) | Positive net of costs in commodity futures (Szakmary, Shen and Sharma 2010) | Positive on Bitcoin (Gerritsen et al. 2020); long-only portfolios positive net of 0.10% (Zarattini et al. 2025, WP) | Slow lookbacks only: at 0.50% the 5-day rule's return roughly halves, while 30–60-day rules are less affected | Good: the long-only book beat long-short in the one direct comparison | **Test first** |
| Volatility-adjusted trend | Volatility scaling raises Sharpe ratios for assets with a leverage effect (Harvey et al. 2018). Contested in direct comparisons (Cederburg et al. 2020) | Bitcoin's return–volatility asymmetry ran the other way before 2014 (Bouri, Azzi and Dyhrberg 2017) | Re-sizing adds turnover. It needs a wide no-trade band | Natural: it only holds less | **Test as a sizing policy**, not as a strategy |
| Market-regime awareness | Tradable regime timing is hard to show (Hurst et al. 2017, Panel B). A slow trend filter cuts drawdowns (Faber, via CXO, S) | A price-above-SMA filter on Bitcoin (Detzel et al., WP summary, S) | Good: a veto on entries reduces trading | Natural: long or cash | **Test as an entry gate** on any strategy |
| Mean reversion (bands, oscillators, reversal) | Strong short-term reversal in old equity data, mostly gone after costs (Jegadeesh 1990; Lehmann 1990; Bajgrowicz and Scaillet 2012) | Reversal exists in small, illiquid coins. The largest coins show daily and weekly **continuation** instead (Zaremba et al. 2021; Fičura 2023, WP) | Poor: short holds and many trades | Possible, but against the evidence for these coins | **Defer**; a falsification test at most |
| Relative strength (cross-sectional momentum) | Strong long-short in equities (Jegadeesh and Titman 1993); crashes in rebounds (Daniel and Moskowitz 2016) | Broad universes, long-short and gross (Liu, Tsyvinski and Wu 2022). Among larger coins the alpha is "largely from short positions" and "incurs substantial trading costs" (Fieberg, Liedtke and Zaremba 2024) | About 19% a year of drag at k = 3 with one swap a week [R] | Weak: long-only forgoes most of the published alpha | **Defer**; needs a portfolio interface |
| DCA and accumulation | Lump sum beats averaging about two-thirds of the time (Williams and Bacon 1993; Vanguard 2023) | No peer-reviewed crypto study found | Neutral if each tranche clears the minimum | Yes | **An execution policy and a baseline**, never a source of return |
| Baselines (hold, cash, random) | Random entries matched technical rules on four equity indices (Biondo et al. 2013) | Buy-and-hold is the standard benchmark | — | — | **Required** for every test |

**The recommendation this supports** (FDS-SR-001 §5.4):
- first, a daily Donchian breakout and a daily time-series momentum rule;
- an entry gate for market regime, usable with any strategy;
- the existing volatility shrink, evaluated as a sizing policy across strategies;
- mean reversion and relative strength deferred.

## 2. What the costs alone imply

- **The hurdle per trade [R].** A round trip costs 1.10%. So a strategy must earn more than 1.10% gross per trade on average to break even, or more than 2.50% at the 1.20% tier.
- **The yearly drag [R]:** turnover per year × 1.10% of the capital turned over.
  - One full round trip a month costs about 13% a year.
  - One a week costs about 57%; one a day, about 400%.
- **Spreads are small beside the fees.** Coinbase BTC-USD and ETH-USD spreads were about 1–2 basis points in 2017–2019 [P, Brauneis et al. 2021, FT]. That is 25 to 50 times smaller than one taker fee. The 0.05% slippage assumption is therefore conservative for the majors; smaller coins were not measured.
- **The repository agrees:**
  - Unfiltered STRAT-001 at 1h, at 0.50%, made 6,825 trades on 11 coins from 2021-01-01 to 2025-05-06, and lost $5,191 of $10,000 (`docs/dev/SIG4-REPORT-dev.md`).
  - STRAT-001 and STRAT-002 lost out of sample even at 0.10% + 0.05% (`docs/dev/BACKTEST-REPORT-batch-1.md`).
- **Consequence [R]:**
  - Hourly decisions with short holds cannot be expected to cover these costs.
  - Every candidate below decides on daily bars and holds for weeks.
  - Shorter timeframes appear only as robustness checks.

## 3. Time-series momentum and moving-average trend

**1. Basis.**
- [P] Moskowitz, Ooi and Pedersen (2012, FT): "We document significant 'time series momentum' in equity index, currency, commodity, and bond futures for each of the 58 liquid instruments we consider". Returns persist "for one to 12 months that partially reverses over longer horizons, consistent with sentiment theories of initial under-reaction and delayed over-reaction."
- [P] Hurst, Ooi and Pedersen (2017, FT): 67 markets from 1880 to 2016, profitable in every decade.
- [P] Levine and Pedersen (2016, FT): time-series momentum and moving-average crossovers "are equivalent representations in their most general forms". So **STRAT-000 and STRAT-001 already belong to this family**.
- [P] In crypto:
  - Liu and Tsyvinski (2021; working paper FT, journal A) find "a strong time-series momentum effect": weekly returns predict the next one to four weeks.
  - Detzel et al. (2021, A) find that "ratios of prices to their moving averages forecast daily Bitcoin returns in and out of sample".

**2. Rules as published.**
- [P] Moskowitz et al.: long if the last 12 months' excess return is positive, short if negative, rebalanced monthly. Each position is sized to 40% annual volatility, from an exponentially weighted variance with a 60-day centre of mass.
- [P] Hurst et al.: an equal mix of 1-, 3- and 12-month signals, volatility-scaled, with a portfolio target of 10%.
- [P] In crypto:
  - Grobys, Ahmed and Sapkota (2020, A): price against its 20-day average, daily.
  - The Detzel et al. working paper (S): Bitcoin above its 5- to 100-day average, otherwise cash.

**3. Data.** Daily closes and a daily volatility estimate. No other coin is needed.

**4. Timeframes.**
- [P] The core evidence is monthly rebalancing on daily data.
- [P] Crypto evidence is daily or weekly. Intraday Bitcoin momentum exists (Shen, Urquhart and Wang 2022, A), but not net of retail fees.
- [R] No study was found of 1h or 4h time-series momentum net of fees at these levels.

**5. Trade frequency.** [P] Monthly rebalancing. [R] As long-or-cash, a coin switches a few times a year at 3- to 12-month horizons.

**6. Costs.**
- [P] Hurst et al. deduct estimated costs (higher for earlier periods) and fees, and returns stay positive.
- [P] Moskowitz et al. report returns before costs.
- [P] Hudson and Urquhart (2021, A) test almost 15,000 rules on crypto. They find break-even costs "substantially higher than those typically found in cryptocurrency markets", but "no predictability for Bitcoin in the out-of-sample period".
- [S] The Detzel et al. working paper's break-even "switching frictions" rise from 1.1% (5-day average) to 4.5% (100-day).
- [R] At 1.10% a round trip, only the slow averages leave a margin.

**7. Where it works and fails.**
- [P] It does best in extreme markets.
- [P] It loses at sharp reversals: "The ending of a crisis constitutes a sharp trend reversal that generates losses" (Moskowitz et al.).
- [P] It "may not perform well in bear markets that occur very rapidly" (Hurst et al.).

**8. Protective controls.**
- [R] The cash state is the main control for long-only.
- [R] A decision schedule (weekly or monthly) or a minimum hold limits whipsaw.
- [P] Volatility scaling.

**9. Evidence quality and contradictions.**
- [P] Huang, Li, Wang and Zhou (2020, A): asset-by-asset tests "reveal little evidence of TSM, both in- and out-of-sample". The strategy "is virtually the same as that of a similar strategy that is based on historical sample mean".
- [P] Kim, Tse and Wald (2016, A): the results are "largely driven by volatility-scaling". "Without scaling by volatility, time series momentum and a buy-and-hold strategy offer similar cumulative returns."
- [P] Sullivan, Timmermann and White (1999, FT): Brock, Lakonishok and LeBaron's rules survive data-snooping correction in-sample. Out of sample, from 1987 to 1996, there is "scant evidence that technical trading rules were of any economic value".
- [P] Wei, Kyriakou, Sermpinis and Stasinakis (2024, FT): 12 coins from 2015 to 2022, 7,846 rules. Only a short-term price-to-average ratio and a hashrate index show genuine profitability. "Our findings question the value of both technical and fundamental analysis on cryptocurrencies."
- [R] Crypto samples span two or three boom-and-bust cycles, dominated by a long bull market.

**10. Long-only.**
- [PR] Norges Bank Investment Management (2014, FT): "most of the positive portfolio performance is due to the long signals, while the value-added from the short signals is only apparent in currencies and commodities."
- [R] Long-only gives up the short side's crisis returns (Hurst et al.), so in a crash it can only go to cash.

## 4. Breakout: price channels and Donchian

**1. Basis.**
- [P] Szakmary, Shen and Sharma (2010, A), 28 commodity futures over 48 years: "all parameterizations of the dual moving average crossover and channel strategies … yield positive mean excess returns net of transactions costs in at least 22 of the 28 markets."
- [P] Gerritsen, Bouri, Ramezanifar and Roubaud (2020, A), daily Bitcoin from 2010 to 2019: the "trading range breakout" rule has significant forecasting power, and outperforms "in strongly trending markets".
- [R] A breakout is a non-linear trend rule, outside Levine and Pedersen's linear equivalence. Its entry (a new high) and its exit (a trailing channel) differ from every strategy in the catalogue.

**2. Rules as published.** Zarattini, Pagani and Barbon (2025, WP, FT):
- **Entry:** long when today's close is the highest close of the last n days.
- **Exit:** the first close below a trailing stop. The stop starts at the channel's midline. "we never allow the trailing stop to be updated downward": stop(t+1) = max(stop(t), midline(t)).
- **Lookbacks:** n from 5 to 360 days, averaged into an ensemble.
- **Sizing:** min(25% ÷ σ, 200%), with σ the 90-day volatility.

[PR] The Turtle rules (Garner 2010, quoting Faith):
- System 1 enters on a 20-day high and exits on a 10-day low.
- System 2 enters on a 55-day high and exits on a 20-day low.
- Stops are 2 ATR(20), with pyramiding and unit caps.

**3. Data.** Daily highs, lows and closes; ATR for stops and sizing.

**4. Timeframes.**
- [P] The positive evidence is daily.
- [P] On 1-minute Bitcoin, trading-range breakouts were weak: one significant result out of 20 (Corbet, Eraslan, Lucey and Sensoy 2019, FT preprint).

**5. Trade frequency.** [P] Zarattini et al.'s Bitcoin trade counts from January 2015 to March 2025:

| Lookback (days) | 5 | 10 | 20 | 30 | 60 | 90 | 150 | 250 | 360 |
|---|---|---|---|---|---|---|---|---|---|
| Trades | 292 | 156 | 78 | 49 | 28 | 20 | 15 | 9 | 5 |

[R] At 20 to 60 days that is about 3 to 8 trades per coin a year.

**6. Costs.**
- [P] Zarattini et al. test 10, 25 and 50 basis points: "at 50 bps, the CAGR of the 5-day model is significantly reduced (from 34% to 18%) while longer-term models are less affected".
- [P] Their headline 10-coin long-only portfolio, net of 10 basis points, has a Sharpe ratio of 1.50 and a maximum drawdown of 12%.
- [R] The account's 55 basis points a side is above their highest level tested, so this is untested.
  - [R] At 7.6 trades a year (20 days), a full position costs about 8% a year.
  - [R] At 2.7 trades a year (60 days), it costs about 3%.

**7. Where it works and fails.**
- [P] It works in strongly trending markets.
- [PR] The Turtle System 1 backtest returned 72% a year with a 66% drawdown, and has "essentially been unprofitable" since the early 1990s. Its slower variants held up better (Garner 2010).

**8. Protective controls.** [P] The ratcheting stop (it only rises). [PR] ATR stops and caps on the number of units.

**9. Evidence quality.**
- [P] Zarattini et al. is a working paper. Two of its three authors are practitioners. Its per-coin tables use the "top 40 … by cumulative trading volume", which the authors concede "is affected by selection bias". Its settings were reported after exploration, and no multiple-testing correction is shown.
- [P] Wei et al. (2024) find short channel-breakout rules strong in-sample but not consistently out of sample.

**10. Long-only.** [P] In Zarattini et al.'s direct comparison, the 10-coin long-only book had a Sharpe ratio of 1.50, against 1.18 for long-short (both net of 10 basis points). Long-only is the better-evidenced form here.

## 5. Volatility-adjusted trend: scaling, targets and ATR exits

**1. Basis.**
- [P] Moreira and Muir (2017, FT working paper): "Managed portfolios that take less risk when volatility is high produce large alphas".
- [P] Harvey et al. (2018, FT), on more than 60 assets: volatility scaling raises Sharpe ratios for risk assets through the leverage effect. "For other assets, such as bonds, currencies, and commodities, volatility scaling has a negligible effect". It "consistently reduces the likelihood of extreme returns".

**2. Rules.**
- [P] Targets: 40% per position (Moskowitz et al.); 25% with a 200% cap (Zarattini et al.); 10% for the portfolio (Hurst et al.).
- [P] Volatility from a 60-day exponentially weighted variance, a 90-day window, or the previous month's realised variance.
- [PR] ATR stops: 2 × ATR(20) (Turtle).

**3. Data.** Daily returns; highs, lows and closes for ATR.

**4–5. Timeframes and turnover.** [P] Volatility targeting adds trades even when the signal does not change. Zarattini et al. needed a 20% rebalance band, and recovered "approximately 100 basis points per year" with it at 50 basis points.

**6. Costs.** [P] Moreira and Muir survive 1 to 10 basis points; Harvey et al. assume 0.5 to 3.5. [R] At 55 basis points, small re-sizing trades are uneconomic. Size once at entry, or re-size only on large deviations.

**7. Where it works and fails.**
- [P] Bitcoin's volatility rose more after positive shocks than negative ones before its 2013 crash, the opposite of equities. There was no significant relation after (Bouri, Azzi and Dyhrberg 2017, A).
- [P] Zarattini et al. note it "may also hinder full participation in large trending moves".

**8. Controls.** [R] Never above 100% of the allocated amount, since spot has no leverage. A floor at zero. Re-sizing only beyond a band.

**9. Evidence quality.**
- [P] Cederburg, O'Doherty, Wang and Yan (2020, A), 103 equity strategies: volatility-managed portfolios "do not systematically outperform", and real-time versions earn less.
- [P] Kim, Tse and Wald (2016): much of time-series momentum's alpha *is* the scaling.

**10. Long-only and this app.**
- [R] The trader sizes each entry at 1% of the account (`position_sizing.py`), so a volatility target applies to that entry, not to the account.
- [R] FDS-SIG-004's shrink, min(1, σ_ref ÷ σ̂) (`signal_fusion/volatility.py`), is already this policy in its shrink-only form. It is evaluated across strategies in FDS-SR-001 rather than rebuilt.

## 6. Market-regime awareness

**1. Basis.**
- [S] Faber's 10-month-average rule (via CXO Advisory's summary of the 2013 update). S&P 500 from 1901 to 2012:

  | | Buy-and-hold | 10-month rule |
  |---|---|---|
  | Return a year | 9.3% | 10.2% |
  | Standard deviation | 17.9% | 12.0% |
  | Worst drawdown | −83.5% | −50.3% |

  CXO cautions: "Data snooping bias via selection of a 10-month SMA may be material."
- [P] Hurst et al.: correlation affected trend performance most. Their Panel B, using lagged (tradable) indicators, "shows the apparent difficulty of improving the strategy via timing decisions".

**2. Rules.**
- [S] Price above its 10-month average, checked at month-end; Bitcoin above its 5- to 100-day average.
- [R] No verified crypto study specifies a 200-day filter with costs.

**3. Data.** Daily closes, of the coin itself or of BTC as the market.

**4. Timeframes.** [R] Daily or slower. Regime flips on hourly bars multiply fees.

**5–6. Turnover and costs.** [R] A gate that only vetoes entries can only reduce trading. Used as a forced exit, it would add round trips.

**7. When to stand aside.** [P] Losses cluster at sharp rebounds after crises (Moskowitz et al.; Daniel and Moskowitz 2016). [R] For long-only, "stand aside" means cash.

**8. Controls.** [R] Make it a veto on new entries, not a forced exit. Report the time spent in each state.

**9. Evidence quality.**
- [S] Even with a moving-average filter, Bitcoin's drawdowns stayed between −66% and −70%, against −89.5% for buy-and-hold (2010–2017, before costs).
- [P] Timing by volatility regime fails out of sample in equities (Cederburg et al. 2020).
- [R] No peer-reviewed crypto regime-switching trading study with costs was found.

**10. Long-only.** [R] It is the most natural family: it is already long or cash. Its risk is the choice of filter length.

## 7. Mean reversion

**1. Basis.**
- [P] Jegadeesh (1990, A): monthly returns show "highly significant" negative serial correlation.
- [P] Lehmann (1990, A): weekly winners and losers "experience sizeable return reversals the next week".
- [P] Lo and MacKinlay (1990, A) find evidence "against overreaction as the only source of contrarian profits".
- [P] **In crypto, the evidence points the other way for these coins.**
  - Zaremba, Bilgin, Long, Mercik and Szczygielski (2021, A), more than 3,600 coins: daily reversal comes from "the illiquidity of the vast majority of traded cryptocurrencies", and "the handful of largest and most tradeable coins exhibit daily momentum rather than a reversal".
  - Fičura (2023, WP, A): weekly reversal "occurs for small and illiquid coins only", while large coins "exhibit weekly momentum effect instead".

**2. Rules.**
- [P] Lento, Gradojevic and Wright (2007, A): Bollinger Bands "after adjusting for transaction costs … are consistently unable to earn profits in excess of the buy-and-hold trading strategy".
- [PR] Common conventions: a 20-period band at ±2 standard deviations, exiting at the middle; RSI(14) at 30/70. No original source was verified for either.

**3–5. Data, timeframes and frequency.** OHLCV for each coin. [P] The documented effects are daily and weekly, in small coins. [R] Holds are short, so there are many trades.

**6. Costs.** [P] Bajgrowicz and Scaillet (2012, A): "even in-sample, the performance is completely offset by the introduction of low transaction costs." [R] Each trade must clear 1.10%.

**7. Where it works and fails.** [P] It works in illiquid micro-caps, which this app does not trade. It fails in trends, and the large coins trend at these horizons.

**8. Controls.** [R] A trend or regime filter; a time stop; a hard exposure cap; never averaging down without limit (§9).

**9. Evidence quality.**
- [P] Park and Irwin (2007, A) survey 95 modern studies: 56 positive, with profits "at least until the early 1990s". They flag data snooping and ex-post rule selection.
- [P] Marshall, Cahan and Cahan (2008, A): "none of the 7846 popular technical trading rules we test are profitable after data snooping bias is taken into account."

**10. Suitability.** [R] Poor. The published evidence predicts continuation, not reversal, for these coins and horizons, and the fee hurdle is above any per-trade edge reported.

## 8. Relative strength and cross-sectional momentum

**1. Basis.**
- [P] Jegadeesh and Titman (1993, A): buying past winners and selling past losers earns significant returns over 3 to 12 months.
- [P] Daniel and Moskowitz (2016, A): momentum crashes occur "in panic states, following market declines and when market volatility is high".
- [P] In crypto:
  - Liu, Tsyvinski and Wu (2022; working paper FT, pp. 1–4): weekly quintile sorts on coins above $1m of market capitalisation, 2014 to 2018, long-short. Weekly excess returns of 2.7% to 4.1% are shown before costs.
  - Fieberg, Liedtke and Zaremba (2024, A), nearly 4,000 coins: momentum "prevails in larger cryptocurrencies" but "incurs substantial trading costs" and "extracts alphas largely from short positions".
  - Grobys and Sapkota (2019, A), 143 coins: "our findings do not indicate any evidence of significant momentum payoffs".
  - Tzouvanas, Kizys and Tsend-Ayush (2020, A), twelve coins: short-term momentum, fading at longer horizons.

**2. Rules.** [P] Sort on the past one to four weeks' return and hold for a week. [R] Long-only: hold the top k of the 12 coins, equal-weighted, rebalanced weekly, with cash when the leaders' own trend is negative.

**3. Data.** [R] Every coin's daily closes at the same instant, and a liquidity screen.

**4–5. Timeframes and frequency.** [P] Weekly. [R] 52 rebalances a year.

**6. Costs.** [R] With k = 3 and one coin swapped a week, the drag is 52 × ⅓ × 1.10% ≈ 19% a year, or about 43% at 1.20%.

**7. Where it works and fails.** [P] It does well in bull markets, weakens over time (Fieberg et al.), and crashes in rebounds after panics.

**8. Controls.** [R] A rank band (no swap unless the new coin leads by a margin), a minimum hold, an absolute-trend filter and caps per coin.

**9. Evidence quality.** [P] The findings contradict each other. The headline effects are long-short, before costs, and dominated by small coins.

**10. Suitability.** [R] Marginal with 11–13 coins:
- the quintiles hold two or three coins each;
- large coins share one strong common factor;
- long-only forgoes most of the published alpha;
- the right benchmark is equal-weighted buy-and-hold of the same coins.

It also needs a strategy interface that sees every coin at once, which does not exist (B §9 item 5).

## 9. DCA and systematic accumulation (execution policies)

**1. Basis.**
- [P] Williams and Bacon (1993, FT): lump sum "outperformed dollar cost averaging nearly two-thirds of the time" (S&P 500, 1926–1991).
- [P] Vanguard (Finlay and Zorn 2023, FT): lump sum beat a 3-month split "68% of the time". The split beat holding cash 69% of the time.
- [P] Cho and Kuvvet (2015, FT): it is a trade-off of risk against return.
- [P] Hayley (2014, City University working paper, abstract read): strategies that "double down" following losses bias the IRR, and value averaging "is inefficient under any plausible investor risk preferences".

**2. Rules.**
- A fixed amount at fixed intervals.
- Value averaging: buy to a target path.
- [PR] "DCA on drawdown": add a larger amount after each fall. This is the legacy engine's ladder: −2.5% to −50%, at 2 × the position's value (`pt_trader.py:2758-2858`).

**6. Costs.** [R] Proportional fees make splitting roughly cost-neutral, provided every tranche clears the exchange minimum.

**7. Where it works and fails.**
- [P] Averaging wins only when prices fall during the averaging window.
- [R] Averaging down with no edge leaves the expected value unchanged. It produces many small wins and rare large losses, as exposure grows into a falling asset.
- No peer-reviewed empirical study of averaging down was found.

**8. Controls.** [R] A maximum number of adds, a total cap per coin, a portfolio stop, and tests that include the 2018 and 2022 bear markets.

**10. For PowerTraderAI.**
- [R] DCA is an execution or risk policy: it decides *how much* to hold, not *whether*. It must never be scored as a source of return.
- [R] The legacy engine's DCA stays with that engine, unchanged.
- [R] A periodic-accumulation schedule is useful as a **baseline** (§10), not as a strategy.

## 10. Baselines

- **Buy-and-hold** is the standard crypto benchmark [P: Hudson and Urquhart; Gerritsen et al.; Borgards 2021]. The backtester already has it (`backtest.engine.buy_and_hold`).
- **Cash** [P]: Brock, Lakonishok and LeBaron's rules "significantly outperform a benchmark of holding cash", as Sullivan et al. describe them.
- **Random entry** [P]: Biondo, Pluchino, Rapisarda and Helbing (2013, FT) find that RSI, MACD and momentum rules "perform on average not better than the purely random strategy" on four equity indices, before costs.
  - The repository has three versions:
    - per coin, `backtest.random_baseline`;
    - the lab's R1 and R2;
    - signal fusion's R3, a random veto at the same rate.
- **[R] Design:**
  - The random baseline must match the strategy's exposure: the same coins, number of entries, holding times and costs. Then it tests timing, not market exposure.
  - Across a family of strategies, the comparison must allow for having chosen the best (White's Reality Check), not test each one alone.

## 11. Methods: overfitting and multiple testing

`docs/dev/model-research/C-evidence.md` §4 already sets the repository's rules (White, SPA, the Deflated Sharpe Ratio, PBO, FDR, the lockbox, how many trades). This section adds only what strategy research changes.

- **Minimum backtest length** (Bailey, Borwein, López de Prado and Zhu 2014, FT): "if only 5 years of data are available, no more than 45 independent model configurations should be tried".
  - [R] The development period here is 4.3 years. An honest search is therefore limited to a few dozen independent configurations across the whole initiative, not per strategy.
- **The probability of backtest overfitting** (Bailey et al. 2017, FT; the CSCV method) needs a T × N matrix of every configuration tried. The lab already computes it over 16 blocks (`model_lab/stats.py`).
- **The Deflated Sharpe Ratio** (Bailey and López de Prado 2014, FT) needs the number of trials and the variance of their Sharpe ratios. It needs a complete trial log, which the lab keeps (`model_lab/batch.py`).
- **White's Reality Check** (2000, FT) and **Hansen's SPA test** (2005, A) test the best of a family against a benchmark.
  - Sullivan et al.'s best rule had an out-of-sample p-value of "nearly 12 percent".
  - Romano and Wolf's StepM (2005, A) identifies which members beat the benchmark.
- **Harvey, Liu and Zhu (2016, A):** a new factor needs "a t-statistic greater than 3.0".
- **[R] For this initiative:**
  - declare each family's members before any result;
  - fix every parameter from the literature, with no tuning;
  - report any parameter variation as trials, with PBO;
  - keep the lockbox and the forward window unread until finalists are chosen.

## 12. References

Verification: **FT** full text read (quotations checked against the saved text where quoted); **A** abstract only; **S** secondary summary only.

1. Bailey, D.H., Borwein, J.M., López de Prado, M., Zhu, Q.J. (2017). The probability of backtest overfitting. *Journal of Computational Finance* 20(4). https://doi.org/10.21314/JCF.2016.322. FT (2015 revision, https://escholarship.org/content/qt4w1110bb/qt4w1110bb.pdf).
2. Bailey, D.H., Borwein, J.M., López de Prado, M., Zhu, Q.J. (2014). Pseudo-mathematics and financial charlatanism. *Notices of the AMS* 61(5), 458–471. https://doi.org/10.1090/noti1105. FT.
3. Bailey, D.H., López de Prado, M. (2014). The Deflated Sharpe Ratio. *Journal of Portfolio Management* 40(5), 94–107. https://doi.org/10.3905/jpm.2014.40.5.094. FT.
4. Bajgrowicz, P., Scaillet, O. (2012). Technical trading revisited: false discoveries, persistence tests, and transaction costs. *Journal of Financial Economics* 106(3), 473–491. https://doi.org/10.1016/j.jfineco.2012.06.001. A.
5. Biondo, A.E., Pluchino, A., Rapisarda, A., Helbing, D. (2013). Are random trading strategies more successful than technical ones? *PLOS ONE* 8(7), e68344. https://doi.org/10.1371/journal.pone.0068344. FT.
6. Borgards, O. (2021). Dynamic time series momentum of cryptocurrencies. *North American Journal of Economics and Finance* 57, 101428. https://doi.org/10.1016/j.najef.2021.101428. A.
7. Bouri, E., Azzi, G., Dyhrberg, A.H. (2017). On the return-volatility relationship in the Bitcoin market around the price crash of 2013. *Economics E-Journal* 11, 2017-2. https://doi.org/10.5018/economics-ejournal.ja.2017-2. A.
8. Brauneis, A., Mestel, R., Riordan, R., Theissen, E. (2021). How to measure the liquidity of cryptocurrency markets? *Journal of Banking & Finance* 124, 106041. https://doi.org/10.1016/j.jbankfin.2020.106041. FT (pp. 1, 5–6).
9. Brock, W., Lakonishok, J., LeBaron, B. (1992). Simple technical trading rules and the stochastic properties of stock returns. *Journal of Finance* 47(5), 1731–1764. A.
10. Cederburg, S., O'Doherty, M.S., Wang, F., Yan, X. (2020). On the performance of volatility-managed portfolios. *Journal of Financial Economics* 138(1), 95–117. https://doi.org/10.1016/j.jfineco.2020.04.015. A.
11. Cho, D.D., Kuvvet, E. (2015). Dollar-cost averaging: the trade-off between risk and return. *Journal of Financial Planning* 28(10), 52–58. FT.
12. Corbet, S., Eraslan, V., Lucey, B., Sensoy, A. (2019). The effectiveness of technical trading rules in cryptocurrency markets. *Finance Research Letters* 31, 32–37. https://doi.org/10.1016/j.frl.2019.04.027. FT (preprint).
13. Daniel, K., Moskowitz, T.J. (2016). Momentum crashes. *Journal of Financial Economics* 122(2), 221–247. https://doi.org/10.1016/j.jfineco.2015.12.002. FT (NBER working paper 20439).
14. Deprez, N., Frömmel, M. (2024). Are simple technical trading rules profitable in bitcoin markets? *International Review of Economics & Finance* 93(B), 858–874. https://doi.org/10.1016/j.iref.2024.05.003. A: 75,360 rules in 6 classes, at daily and intraday frequencies. The best are selected after transaction costs with a multiple-hypothesis procedure. Out of sample, portfolios of them "can outperform a buy-and-hold strategy", "especially risk–return wise". The cost level and sample period are not in the abstract.
15. Detzel, A., Liu, H., Strauss, J., Zhou, G., Zhu, Y. (2021). Learning and predictability via technical analysis: evidence from bitcoin and stocks with hard-to-value fundamentals. *Financial Management* 50(1), 107–137. https://doi.org/10.1111/fima.12310. A; working-paper figures via CXO Advisory, S.
16. Faber, M.T. (2007, updated 2013). A quantitative approach to tactical asset allocation. *Journal of Wealth Management* 9(4). S (CXO Advisory's summary).
17. Fičura, M. (2023). Impact of size and volume on cryptocurrency momentum and reversal. FFA Working Papers 5, 003, Prague University of Economics and Business. A.
18. Fieberg, C., Liedtke, G., Zaremba, A. (2024). Cryptocurrency anomalies and economic constraints. *International Review of Financial Analysis* 94, 103218. https://doi.org/10.1016/j.irfa.2024.103218. A.
19. Finlay, M., Zorn, J. (2023). Cost averaging: invest now or temporarily hold your cash? Vanguard. FT (pp. 1–3).
20. Garner, A. (2010). Tuning up the turtle. *Active Trader*, February 2010 (citing C. Faith, *The Original Turtle Trading Rules*). FT (practitioner).
21. Gerritsen, D.F., Bouri, E., Ramezanifar, E., Roubaud, D. (2020). The profitability of technical trading rules in the Bitcoin market. *Finance Research Letters* 34, 101263. https://doi.org/10.1016/j.frl.2019.08.011. A.
22. Grobys, K., Ahmed, S., Sapkota, N. (2020). Technical trading rules in the cryptocurrency market. *Finance Research Letters* 32, 101396. https://doi.org/10.1016/j.frl.2019.101396. A.
23. Grobys, K., Sapkota, N. (2019). Cryptocurrencies and momentum. *Economics Letters* 180, 6–10. https://doi.org/10.1016/j.econlet.2019.03.028. A.
24. Hansen, P.R. (2005). A test for superior predictive ability. *Journal of Business & Economic Statistics* 23(4), 365–380. https://doi.org/10.1198/073500105000000063. A.
25. Harvey, C.R., Hoyle, E., Korgaonkar, R., Rattray, S., Sargaison, M., Van Hemert, O. (2018). The impact of volatility targeting. *Journal of Portfolio Management* 45(1), 14–33. https://doi.org/10.3905/jpm.2018.45.1.014. FT.
26. Harvey, C.R., Liu, Y., Zhu, H. (2016). … and the cross-section of expected returns. *Review of Financial Studies* 29(1), 5–68. https://doi.org/10.1093/rfs/hhv059. A.
27. Hayley, S. (2014). Dynamic strategy bias of IRR and modified IRR: the case of value averaging. City Research Online. https://openaccess.city.ac.uk/id/eprint/6298/. Abstract page read.
28. Huang, D., Li, J., Wang, L., Zhou, G. (2020). Time series momentum: is it there? *Journal of Financial Economics* 135(3), 774–794. https://doi.org/10.1016/j.jfineco.2019.08.004. A.
29. Hudson, R., Urquhart, A. (2021). Technical trading and cryptocurrencies. *Annals of Operations Research* 297(1), 191–220. https://doi.org/10.1007/s10479-019-03357-1. A.
30. Hurst, B., Ooi, Y.H., Pedersen, L.H. (2017). A century of evidence on trend-following investing. *Journal of Portfolio Management* 44(1). https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing. FT (exhibit tables are images).
31. Jegadeesh, N. (1990). Evidence of predictable behavior of security returns. *Journal of Finance* 45(3), 881–898. A.
32. Jegadeesh, N., Titman, S. (1993). Returns to buying winners and selling losers. *Journal of Finance* 48(1), 65–91. A.
33. Kim, A.Y., Tse, Y., Wald, J.K. (2016). Time series momentum and volatility scaling. *Journal of Financial Markets* 30, 103–124. https://doi.org/10.1016/j.finmar.2016.05.003. A.
34. Lehmann, B.N. (1990). Fads, martingales, and market efficiency. *Quarterly Journal of Economics* 105(1), 1–28. https://doi.org/10.2307/2937816. A.
35. Lento, C., Gradojevic, N., Wright, C.S. (2007). Investment information content in Bollinger Bands? *Applied Financial Economics Letters* 3(4), 263–267. https://doi.org/10.1080/17446540701206576. A.
36. Levine, A., Pedersen, L.H. (2016). Which trend is your friend? *Financial Analysts Journal* 72(3), 51–66. https://doi.org/10.2469/faj.v72.n3.3. FT.
37. Liu, Y., Tsyvinski, A. (2021). Risks and returns of cryptocurrency. *Review of Financial Studies* 34(6), 2689–2727. https://doi.org/10.1093/rfs/hhaa113. A; NBER working paper 24877, FT.
38. Liu, Y., Tsyvinski, A., Wu, X. (2022). Common risk factors in cryptocurrency. *Journal of Finance* 77(2), 1133–1177. https://doi.org/10.1111/jofi.13119. A; NBER working paper 25882, FT pp. 1–4.
39. Lo, A.W., MacKinlay, A.C. (1990). When are contrarian profits due to stock market overreaction? *Review of Financial Studies* 3(2), 175–205. A.
40. Marshall, B.R., Cahan, R.H., Cahan, J.M. (2008). Does intraday technical analysis in the U.S. equity market have value? *Journal of Empirical Finance* 15(2), 199–210. A.
41. Moreira, A., Muir, T. (2017). Volatility-managed portfolios. *Journal of Finance* 72(4), 1611–1644. https://doi.org/10.1111/jofi.12513. FT (NBER working paper 22208).
42. Moskowitz, T.J., Ooi, Y.H., Pedersen, L.H. (2012). Time series momentum. *Journal of Financial Economics* 104(2), 228–250. https://doi.org/10.1016/j.jfineco.2011.11.003. FT.
43. Norges Bank Investment Management (2014). Momentum in futures markets. Discussion Note 1-2014. FT (institutional, not peer-reviewed).
44. Park, C.-H., Irwin, S.H. (2007). What do we know about the profitability of technical analysis? *Journal of Economic Surveys* 21(4), 786–826. https://doi.org/10.1111/j.1467-6419.2007.00519.x. A.
45. Romano, J.P., Wolf, M. (2005). Stepwise multiple testing as formalized data snooping. *Econometrica* 73(4), 1237–1282. https://doi.org/10.1111/j.1468-0262.2005.00615.x. A.
46. Shen, D., Urquhart, A., Wang, P. (2022). Bitcoin intraday time series momentum. *Financial Review* 57(2), 319–344. https://doi.org/10.1111/fire.12290. A.
47. Sullivan, R., Timmermann, A., White, H. (1999). Data-snooping, technical trading rule performance, and the bootstrap. *Journal of Finance* 54(5), 1647–1691. https://doi.org/10.1111/0022-1082.00163. FT.
48. Szakmary, A.C., Shen, Q., Sharma, S.C. (2010). Trend-following trading strategies in commodity futures: a re-examination. *Journal of Banking & Finance* 34(2), 409–426. A.
49. Tzouvanas, P., Kizys, R., Tsend-Ayush, B. (2020). Momentum trading in cryptocurrencies: short-term returns and diversification benefits. *Economics Letters* 191, 108728. https://doi.org/10.1016/j.econlet.2019.108728. A.
50. Wei, M., Kyriakou, I., Sermpinis, G., Stasinakis, C. (2024). Cryptocurrencies and lucky factors: the value of technical and fundamental analysis. *International Journal of Finance & Economics* 29, 4073–4104. https://doi.org/10.1002/ijfe.2863. FT.
51. White, H. (2000). A reality check for data snooping. *Econometrica* 68(5), 1097–1126. https://doi.org/10.1111/1468-0262.00152. FT (pp. 1–2).
52. Williams, R.E., Bacon, P.W. (1993). Lump-sum beats dollar-cost averaging. *Journal of Financial Planning* 6(2), 64–67. FT (AAII reprint).
53. Zaremba, A., Bilgin, M.H., Long, H., Mercik, A., Szczygielski, J.J. (2021). Up or down? Short-term reversal, momentum, and liquidity effects in cryptocurrency markets. *International Review of Financial Analysis* 78, 101908. https://doi.org/10.1016/j.irfa.2021.101908. A.
54. Zarattini, C., Pagani, A., Barbon, A. (2025). Catching crypto trends: a tactical approach for Bitcoin and altcoins. Swiss Finance Institute Research Paper 25-80; SSRN 5209907. FT (version of 9 April 2025).

**Searched for, not found or not verified:**
- a peer-reviewed study of overnight reversal in crypto;
- a peer-reviewed crypto study of DCA against lump sum;
- an empirical study of averaging down;
- a crypto regime-switching trading study with costs;
- a numeric split of long and short returns in diversified-futures trend following;
- the original sources of the RSI(14, 30/70) and Bollinger(20, 2) conventions;
- Han, Kang and Ryu (crypto momentum under realistic costs; the PDF was refused);
- Coinbase's current fee pages.
