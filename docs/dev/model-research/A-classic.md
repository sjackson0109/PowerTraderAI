# Research A: classic machine learning and untrained floors

Agent A of three. Date 2026-11-05. Research only: no code was run, no packages were installed, and the repository was not read.

Conventions used below:
- **Source says** marks what a cited source states. **My inference** marks my own reasoning. Anything else without a source is marked *unsourced*.
- Evidence flaws are tagged as follows. **LA**: look-ahead risk. **FEE**: no costs, or costs far below ours. **IS**: in-sample only. **HP**: one short or hand-picked period. **SURV**: survivorship. **BH**: compared only with buy-and-hold, often in a one-way market. **NOBASE**: no random or naive baseline. **MT**: many trials with no multiple-testing correction. **XS**: cross-sectional or long-short result that a long-only, one-coin-at-a-time spot trader cannot capture.
- Our cost is 0.50% a side plus about 0.05% slippage, so about 1.1% a round trip. Most papers assume 0.1% a side or less, so nearly every paper below is tagged FEE relative to us.

---

## 1. Shortlist (ranked)

**Headline: nothing on this list has credible published evidence of beating random entries after costs like ours.** No study found tests entries under DCA and trailing-profit exits against random entries at all. The ranking is therefore by (evidence) x (fit to our exits) x (cost to test).

| Rank | Name | Family | What it predicts / decides for us | Why it's on the list | Evidence | Fit to C1-C4 |
|---|---|---|---|---|---|---|
| 1 | **Trend / time-series-momentum floor** (e.g. close above its N-day moving average, or past 7-14-day return above 0) | Untrained rule | Enter only when the rule is on (alone, or as a gate on the current signal) | The most-replicated crypto return pattern. If trends persist for days, it should cut the entries that fall into the DCA ladder. | **Some** for daily and weekly predictability. **None** for our exit structure. Mostly IS/BH, concentrated in bull markets, and Bitcoin shows no out-of-sample predictability in one large test. | C1 trivial. C2 no package. C3 OHLCV only. C4 local. |
| 2 | **LightGBM classifier** (gradient-boosted trees) | Trained, tabular | P(clean win): price reaches +5% before the first DCA level (-2.5%) within H hours. Also used as a meta-labeller on top of rank 1 or the current pattern model. | The best-supported tabular learner. It was among the best models in the studies that compare models, it supports sample weights for overlapping labels, and it is cheap on CPU. | **Weak** for after-cost edge. **Some** for small predictive skill (accuracy 52-56%, AUC about 0.6). Fails after 10 bps costs at hourly horizons unless trades are filtered, and is not significantly better than buy-and-hold even then. | C1 yes (estimate, unmeasured). C2 lightgbm 4.7.0 (2026-07-18), MIT; scikit-learn's HistGradientBoosting is a no-new-dependency alternative. C3 OHLCV only. C4 local. |
| 3 | **Regularised logistic regression** (L2) | Trained, linear | Same target and features as rank 2 | The trained floor. Two studies find simple models match trees, so rank 2 is only worth keeping if it beats this. Hard to overfit. | **Weak**. Matched trees (holdout AUC 0.6087) in a 2026 Bitcoin stop-loss/take-profit label study, which still found no economic value after fees. | C1 seconds. C2 scikit-learn 1.9.1 (2026-09-10), BSD-3. C3/C4 yes. |
| 4 | **Short-term reversal ("dip") floor**: enter when the 24-72 h return is in the coin's own bottom decile | Untrained rule | Enter only after a sharp fall | The opposite sign to rank 1, and what a DCA ladder implicitly bets on. Testing both tells you which side each coin sits on. | **Weak, and it points the wrong way for majors.** Daily reversal shows up in small, illiquid coins. The largest coins show daily *momentum* instead. | Trivial; OHLCV; local. |
| 5 | **Random forest / extremely randomised trees** | Trained, tree ensemble | Same target as rank 2 | A lower-variance nonlinear check on LightGBM, with little tuning. | **Weak**. Best accuracy in a 2018-19 bear-market test, best cross-validated AUC (0.6086) in the 2026 Bitcoin study. No after-cost edge shown. | C1 yes; model files can be large. C2 scikit-learn, BSD-3. C3/C4 yes. |

**Not shortlisted but kept as a feature:** volatility filters (section 4) and BTC's recent move (section 2.2).

---

## 2. Candidates in detail

### 2.1 Rank 1: trend / time-series-momentum floor

**Rule family to test (untrained).** Use daily closes from completed daily candles only. Signals: close / SMA(N days) > 1 for N in {20, 50, 100}; or log return over the past 7 or 14 days > 0; or a Donchian breakout (close above the max close of the past N days). Use it two ways: as an "enter whenever on" floor, and as a gate on the current pattern model's signal. Fix the parameter grid up front and count every variant as a trial (section 3.4).

**Evidence**
- **Liu & Tsyvinski, "Risks and Returns of Cryptocurrency", *Review of Financial Studies* 34(6), 2021** ([NBER WP](https://www.nber.org/system/files/working_papers/w24877/w24877.pdf), [EconPapers](https://econpapers.repec.org/RePEc:nbr:nberwo:24877)).
  - Source says: the published abstract reports a "strong time-series momentum effect". The working paper finds significant time-series momentum at daily and weekly frequencies for BTC, XRP and ETH. In one-week sorts, the top quintile returned 11.20% a week against 1.07% for the bottom quintile.
  - Flaws: IS (predictive regressions), FEE (costs are not part of the test), HP (sample ends in the 2017-18 boom), NOBASE.
- **Han, Kang & Ryu, "Time-Series and Cross-Sectional Momentum in the Cryptocurrency Market: A Comprehensive Analysis under Realistic Assumptions"**, working paper, publication status not confirmed ([AUT-hosted PDF](https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf); I read the abstract via search only).
  - Source says: once costs and liquidation risk are included, evidence of time-series momentum is strong and evidence of cross-sectional momentum is weak. Time-series momentum when the market falls "yields negative profits in most cases", so it is concentrated in bullish markets.
  - This is the most realistic momentum test I found. Flaws: BH-type regime dependence; not peer-reviewed as far as I could find.
- **Detzel, Liu, Strauss, Zhou & Zhu, "Learning and predictability via technical analysis…", *Financial Management* 50(1), 2021** ([IDEAS](https://ideas.repec.org/a/bla/finmgt/v50y2021i1p107-137.html)).
  - Source says: price-to-moving-average ratios predict daily Bitcoin returns in and out of sample. Strategies built on them give economically significant alpha and Sharpe gains over buy-and-hold.
  - Flaws: BH; Bitcoin only; I could not confirm the cost assumption.
- **Hudson & Urquhart, "Technical trading and cryptocurrencies", *Annals of Operations Research* 297, 2021** ([Reading repository](https://centaur.reading.ac.uk/85715)).
  - Source says: almost 15,000 rules in five classes, daily, on BTC, LTC, ETH and XRP. Many rules stay significant after multiple-testing corrections, but there is **no predictability for Bitcoin in the out-of-sample period**.
  - This counts against the floor for BTC specifically.
- **Grobys, Ahmed & Sapkota, "Technical trading rules in the cryptocurrency market", *Finance Research Letters* 32, 2020** ([Osuva record](https://osuva.uwasa.fi/handle/11111/619)).
  - Source says: a 20-day variable moving average on the 11 most-traded coins, daily, 2016-2018. Excluding Bitcoin, the excess return was about 8.76% a year.
  - Follow-up (Ahmed, Grobys & Sapkota 2020, privacy coins, same repository): the rule beat buy-and-hold **only for Dash** of ten privacy coins. That matters for our DASH and ZEC.
  - Flaws: HP (3 years), BH, costs unconfirmed.
- **Corbet, Eraslan, Lucey & Sensoy, "The effectiveness of technical trading rules in cryptocurrency markets", *Finance Research Letters* 31, 2019** ([IDEAS](https://ideas.repec.org/a/eee/finlet/v31y2019icp32-37.html)).
  - Source says: on high-frequency Bitcoin data, moving-average rules get "significant support". The variable-length moving average performs best, and buy signals earn more than sell signals.
  - Flaws: Bitcoin only; costs and period unconfirmed (abstract only).
- **Gerritsen, Bouri, Ramezanifar & Roubaud, *Finance Research Letters* 34, 2020** ([Utrecht portal](https://research-portal.uu.nl/en/publications/the-profitability-of-technical-trading-rules-in-the-bitcoin-marke/)).
  - Source says: trading-range-breakout rules have significant forecasting power for Bitcoin, daily, 2010-2019, mainly in strongly trending markets.
  - Flaws: FEE (secondary summaries say there are no transaction costs; not confirmed from the paper), BH.
- **Deprez & Frömmel, "Are simple technical trading rules profitable in bitcoin markets?", *Int. Review of Economics & Finance* 93, 2024** ([IDEAS](https://ideas.repec.org/a/eee/reveco/v93y2024ipbp858-874.html)).
  - Source says: 75,360 rules, daily and intraday, with transaction costs and a multiple-hypothesis selection. Combined into portfolios, the selected rules can beat buy-and-hold out of sample, "especially risk–return wise".
  - The best-controlled rule study found. Flaws: BH; cost level not seen.
- **Zarattini, Pagani & Barbon, "Catching Crypto Trends", Swiss Finance Institute RP 25-80, 2025** ([IDEAS](https://ideas.repec.org/p/chf/rpseri/rp2580.html), [CXO summary](https://www.cxoadvisory.com/technical-trading/crypto-asset-trend-following-strategies/)).
  - Source says: a long-only Donchian ensemble on up to 20 liquid coins, daily, survivorship-bias-free data, 2015 to March 2025. At 0.10% costs: 18% net CAGR and 11% net alpha against Bitcoin buy-and-hold. They also test 0.25% and 0.50%.
  - Flaws: BH only; it is a full strategy with stops and volatility sizing up to 200% leverage, not an entry filter; authors include a commercial firm (Concretum).
- **Counter-evidence at hourly horizons:**
  - **Bysik & Ślepaczuk 2026** ([arXiv 2606.00060](https://arxiv.org/abs/2606.00060), [summary](https://www.emergentmind.com/papers/2606.00060)). Source says: their 24-hour momentum benchmark on hourly BTC also fails after 10 bps costs.
  - **Mroziewicz & Ślepaczuk 2026** ([arXiv 2602.10785](https://arxiv.org/abs/2602.10785)). Source says: an intraday EMA rule roughly matched buy-and-hold out of sample, with a break-even cost of about 0.4% per transaction. **My inference:** our 0.55% a side is above that break-even.

**My inference.**
- The only horizon with decent evidence is days to weeks. That matches our holding periods, because a +5% trail on a major usually takes days, not hours.
- The barrier arithmetic in section 3.1 shows a floor helps only if it selects bars with positive drift over the trade horizon. Momentum is the one published effect that claims exactly that, but mostly in bull markets.
- Because we are long-only, the bear-market failure Han et al. report becomes "few entries" rather than short-side losses. That is good for drawdown but leaves fewer trades to judge.

**Fit.** C1 trivial; C2 none needed; C3 OHLCV (daily candles); C4 local.

### 2.2 Rank 2: LightGBM classifier (gradient-boosted decision trees)

**Target.** Label L1 from section 3.2, an asymmetric triple barrier: +5% upper, -2.5% lower (the first DCA level), H-hour vertical barrier. Variant: L2, the full strategy-replay return. Also run as a **meta-labeller**: the primary signal is rank 1 or the current pattern model (long score ≥ 3 and short score 0), and LightGBM decides whether to take each signal.

**Features (OHLCV only, scale-free so coins can be pooled).**
- Log returns over 1, 4, 12, 24, 72, 168 and 336 hours.
- Realised volatility: standard deviation of 1 h returns over 24 h and 168 h, Parkinson range volatility, and the 24h/168h volatility ratio.
- Close / SMA ratios at 24 h, 7 d and 30 d, plus the daily 50 and 200 (Detzel-type).
- Drawdown from the 30-day high and distance from the 30-day low.
- log(24 h volume / 30-day mean volume).
- Candle-shape fractions (body and wicks as a share of range).
- For altcoins: BTC's returns and volatility at the same lags, and alt-minus-BTC returns.
- The current pattern model's long and short scores, for stacking.
- Higher-timeframe values must come from the last **completed** 4h/1d/1w candle (section 3.5).
- Evidence for BTC-lead features is weak. The search found Granger-causality studies ([JMU](https://commons.lib.jmu.edu/jmurj/vol9/iss1/5), [NJIT intraday](https://researchwith.njit.edu/en/publications/does-bitcoin-still-own-the-dominant-power-an-intraday-analysis/)) but no after-cost hourly trading test.

**Evidence**
- **Jaquart, Dann & Weinhardt, "Short-term bitcoin market prediction via machine learning", *J. Finance and Data Science* 7, 2021** ([KITopen](https://publikationen.bibliothek.kit.edu/1000150665)).
  - Source says: BTC at 1-60 minute horizons. All models beat a random classifier. Recurrent nets and gradient boosting classifiers (xgboost) were best, ahead of random forest and logistic regression. A long-short quantile strategy made up to 39% a month **before** costs, which **turned negative after costs** because holding periods were short.
  - Credible negative result. Flaw: XS (long-short).
- **Jaquart, Köpke & Weinhardt, "Machine learning for cryptocurrency market prediction and trading", *JFDS* 8, 2022** ([DOAJ](https://doaj.org/article/cfc09801314441198e3e1c92a3914e54)).
  - Source says: daily direction for the 100 largest coins, average accuracy 52.9-54.1% (57.5-59.5% on the 10% most confident predictions). An LSTM/GRU long-short portfolio had a post-cost Sharpe of 3.23 and 3.12, against 1.33 for buy-and-hold.
  - The winners were recurrent nets, not trees. I could not read the cost assumption or the long-leg-only numbers (the PDF would not extract). Flaws: XS, cost level unknown.
- **Bysik & Ślepaczuk, "Machine Learning-Based Bitcoin Trading Under Transaction Costs: Evidence From Walk-Forward Forecasting", arXiv 2606.00060, May 2026** ([abs](https://arxiv.org/abs/2606.00060), [HTML](https://arxiv.org/html/2606.00060v1)). The most relevant study found.
  - Setup: hourly BTC-USDT perpetual, 2018-2026, about 70,900 bars. XGBoost, LSTM and iTransformer in a 27-fold walk-forward (12-month train, 3-month validation, 3-month test), 10 bps per position change.
  - Naive sign-following loses: XGBoost long-only went from +73.5% annualised return gross to **-64.0%** after costs.
  - A cost-aware filter (trade only when the forecast exceeds a cost-based threshold) cut trades from 10,619 to 251 and gave XGBoost long-only 65.4% annualised, Sharpe 1.09, against buy-and-hold at 56.3% and 0.82. The authors say Sharpe comparisons against buy-and-hold "do not reject after bootstrap adjustment".
  - Only 16 of 27 folds were profitable. XGBoost beat the neural models descriptively, but not after multiple-testing correction.
  - Flaws: MT (about 21,000 tuning trials across models by my count from their table; the threshold λ=2.0 choice is not explained), BH, FEE (10 bps is a fifth of ours).
  - **My inference:** at 5x their cost, the naive version is hopeless. The filtered version survives only because it trades rarely and waits for big forecast moves, which is close in spirit to our +5% target.
- **Sobreiro, Martinho, Martins & Vardasca, "Multi-Timeframe Feature Engineering for Bitcoin Market Prediction", *Forecasting* (MDPI) 8(3), 2026** ([summary page](https://synapsesocial.com/papers/6a0cfff4d24d91c50ccc91ae); the preprint and MDPI pages blocked fetching; the dates differ between versions).
  - Source says: BTC, 2020-Nov 2025. LR, decision tree, RF, XGBoost and LightGBM on stop-loss/take-profit labels. Cross-validated AUC 0.57-0.61 for all models (RF best at 0.6086); LR reached 0.6087 on a 2025 holdout.
  - A multi-timeframe alignment look-ahead bug had inflated AUC by **about 0.20**.
  - After "realistic round-trip fees, net returns are likely negligible": models with AUC around 0.60 "cannot reliably generate economically significant returns".
  - This is the closest analogue to our L1 label (SL 1% / TP 2% is the same 2:1 ratio as our 5% / 2.5%).
- **Islas Anguiano & García-Medina, "Technical Analysis Meets Machine Learning: Bitcoin Evidence", arXiv 2511.00665, 2025** ([HTML](https://arxiv.org/html/2511.00665v1)).
  - Source says: daily BTC, one test year (2024). After a 0.1% fee, LightGBM returned 39.78% against 42.31% for buy-and-hold (accuracy 0.584).
  - Flaws: HP, BH, no significance tests.
- **Cakici, Shahzad, Będowska-Sójka & Zaremba, "Machine learning and the cross-section of cryptocurrency returns", *IRFA* 94, 2024** ([repository](https://open.icm.edu.pl/handle/123456789/25543)).
  - Source says: the benefit of model complexity is limited, and predictability comes mainly from a handful of simple characteristics (price, past alpha, illiquidity, momentum). Strategies stay profitable after costs, but alpha is concentrated in small, illiquid, volatile coins.
  - Flaw: XS. This is support for rank 3 (simple models) rather than for trees.
- **General (non-crypto) support for LightGBM as a pooled learner**:
  - Makridakis, Spiliotis & Assimakopoulos, "M5 accuracy competition: Results, findings, and conclusions", *IJF* 38(4), 2022 ([IDEAS](https://ideas.repec.org/a/eee/intfor/v38y2022i4p1346-1364.html)). Retail sales; LightGBM-based global models won.
  - Ke et al., "LightGBM: A Highly Efficient Gradient Boosting Decision Tree", NeurIPS 2017 (training speed).
  - Neither is evidence of market edge.

**Fit.**
- C1: *unsourced estimate*: a pooled set of about 9 coins x 26k hourly rows x ~40 features should train in seconds to a few minutes per walk-forward fold, and one-row prediction should take milliseconds. Not measured.
- C2: lightgbm 4.7.0, released 2026-07-18 ([PyPI](https://pypi.org/project/lightgbm/)). MIT licence ([LICENSE](https://github.com/microsoft/LightGBM/blob/master/LICENSE)). Python ≥ 3.10, 1.4 MB win_amd64 wheel.
- No-new-dependency alternative: scikit-learn's `HistGradientBoostingClassifier`, which is "inspired by LightGBM", is "much faster than GradientBoostingClassifier for … n_samples >= 10 000", and supports `sample_weight`, monotonic constraints and NaNs ([docs](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingClassifier.html)).
- C3: OHLCV only. C4: local.

### 2.3 Rank 3: regularised logistic regression

**Target and features.** Same as 2.2. Standardise features on each training window only.

**Evidence.**
- Sobreiro et al. 2026 (above): LR matched or beat trees on the holdout (AUC 0.6087), but there was no economic value after fees.
- Cakici et al. 2024: complexity adds little.
- Jaquart et al. 2021: at 1-60 minute horizons LR was behind GBDT and recurrent nets. That is mixed evidence.
- Sebastião & Godinho 2021 (section 2.5): the linear model had the lowest BTC hit rate (46.15%).

**Why it's here (my inference).** With effective samples in the hundreds per coin (section 3.3), a linear model is the honest first test of "is there any signal in these features?". If LightGBM can't beat it on the gate, the extra flexibility is fitting noise.

**Fit.** C1: seconds. C2: scikit-learn 1.9.1, released 2026-09-10, BSD-3-Clause, Python ≥ 3.11 ([PyPI](https://pypi.org/project/scikit-learn/)). C3/C4: yes.

### 2.4 Rank 4: short-term reversal ("dip") floor

**Rule.** Enter when the 24 h (or 72 h) log return is below the coin's own trailing-90-day 10th percentile. Optional: only if the rank-1 trend rule is also on ("dip in an uptrend"); count that as a separate trial.

**Evidence**
- **Zaremba, Bilgin, Long, Mercik & Szczygielski, "Up or down? Short-term reversal, momentum, and liquidity effects in cryptocurrency markets", *IRFA* 78, 2021** ([AMiner abstract](https://aminer.org/pub/628d19b35aee126c0f369100/up-or-down-short-term-reversal-momentum-and-liquidity-effects-in-cryptocurrency)).
  - Source says: the last day's return is a strong predictor. Small, illiquid coins reverse, while "the handful of largest and most tradeable coins exhibit daily momentum rather than a reversal".
  - Flaw: XS.
  - **My inference:** for BTC, ETH, XRP, BNB, SOL and DOGE this predicts the dip floor does *worse* than random; DASH and ZEC are the coins where it might not.
- **Wen, Bouri, Xu & Zhao, "Intraday return predictability in the cryptocurrency markets: Momentum, reversal, or both", *NAJEF* 62, 2022** ([IDEAS](https://ideas.repec.org/a/eee/ecofin/v62y2022ics1062940822000833.html)).
  - Source says: Bitcoin intraday momentum *and* reversal, 2013-2020. Which one appears depends on jumps, FOMC days, liquidity and COVID. A timing strategy beats always-long.
  - Flaws: costs not stated on the abstract page; BH.
- **Dobrynskaya, "Cryptocurrency momentum and reversal", *J. Alternative Investments* 26, 2023** ([HSE summary](https://www.hse.ru/en/news/research/559533243.html)).
  - Source says: cross-sectional momentum up to about 2 weeks, reversal from about 4 weeks.
  - Flaw: XS, weekly. Nothing here supports a 24-72 h dip-buy on majors.

**Why keep it (my inference).** It is free, it is the sign test that complements rank 1, and DCA is itself a dip-buying bet. If the reversal floor beats random on a coin while momentum doesn't, that tells you something about the coin, provided it survives the correction in section 3.4.

**Fit.** Trivial, OHLCV, local.

### 2.5 Rank 5: random forest / extremely randomised trees

**Target.** Same as 2.2. Use `min_samples_leaf` large (hundreds) and pass sample weights.

**Evidence**
- **Sebastião & Godinho, "Forecasting and trading cryptocurrencies with machine learning under changing market conditions", *Financial Innovation* 7, 2021** ([PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC7785332/)).
  - Setup: daily BTC/ETH/LTC with linear, RF and SVM models; long-only; 0.5% round-trip cost.
  - Test period 13 Apr 2018 to 3 Mar 2019, described as "characterized by bearish markets".
  - Source says: hit rates ranged from 46.15% (linear, BTC) to 60.00% (RF, ETH). After costs, "Ensemble 5" made +9.62% (ETH) and +5.73% (LTC) a year, but -23.66% on BTC. The other ensembles mostly lost on BTC (-52.79%, +1.25%).
  - Buy-and-hold lost 55-77% over the same period. The authors note that the validation sample overlaps training.
  - Flaws: HP, BH in a crash (beating a -55% buy-and-hold is easy for a part-time long-only rule), MT (ensemble thresholds compared on the test set), FEE (half ours).
- Sobreiro et al. 2026: RF had the best cross-validated AUC (0.6086), with no economic value after fees.
- **My inference:** there is no evidence that RF beats GBDT here. Its value is as a robustness check: if LightGBM passes and RF and LR fail on the same label and features, suspect overfitting.

**Fit.** C1: yes; parallel training on CPU; prediction is fast, but deep forests can be tens of MB on disk (*unsourced*). C2: scikit-learn, BSD-3. C3/C4: yes.

---

## 3. Recommended labels and validation for the fixed strategy

### 3.1 What the gate actually rewards (my inference, check against the app)

- **The per-trade outcome comes down to one event.** Under these exits, a trade either:
  - reaches +5% before falling 2.5% (a "clean win": exits near peak -0.5%, so about +4.5% gross and about +3.4% net of 1.1% costs), or
  - takes a DCA buy and later exits near +2.5% - 0.5% on a larger position (about +0.9% net).
  
  So, assuming the gate measures return on total capital committed (I could not confirm how the app defines it), mean return per trade is roughly 0.9% + 2.5% x P(clean win). The mark-to-market losses on trades still open at the end of the holdout are the remainder.
- **Barrier probability under no drift.** For a driftless random walk in log price, the chance of hitting an upper barrier U before a lower barrier L is L/(U+L) (gambler's ruin). With drift μ and volatility σ it becomes (1 - e^{2μL/σ²}) / (e^{-2μU/σ²} - e^{2μL/σ²}) ([first-passage statement](https://quantvault.org/problem-416-first-passage-probabilities-and-optimal-barriers-for-brownia.html); the formula checks against the scale function).
  - With U = ln 1.05 and L = -ln 0.975, the no-drift value is **P ≈ 0.34**.
  - At zero drift **this does not depend on volatility**. A volatility filter changes how fast and how deep a trade goes, not the clean-win rate.
- **The drift needed to move it.** Raising P from 0.34 to about 0.40 needs 2μ/σ² ≈ 7. At 60% annual volatility that is a conditional log-drift of about **0.36% a day** (about 0.6% a day at 80% volatility), held over the trade.
  - That is a large edge. By the formula above it would add only about 0.15 percentage points to mean return per trade.
  - The useful target is therefore "which bars have positive drift over the next days relative to their variance". It is not "where will the next candle's high/low be".
- **Why the current model may fail.** It predicts next-candle high/low levels. Range forecasts are mostly volatility forecasts: the high-low range is a volatility estimator and is forecastable like GARCH (Chou, "Forecasting financial volatilities with extreme values: the CARR model", *JMCB* 37(3), 2005, [EconPapers](https://econpapers.repec.org/RePEc:mcb:jmoncb:v:37:y:2005:i:3:p:561-82)). By the result above, volatility on its own carries no information about which barrier is hit first. That is a plausible reason the current model sits near or below random (mean percentile 38). It is not tested.

### 3.2 Labels

**L1: asymmetric triple barrier aligned to the exits.**
- Source: López de Prado, *Advances in Financial Machine Learning* (Wiley, 2018), ch. 3.4. Each observation gets profit-take, stop-loss and expiry barriers ([TOC](https://toc.uni.li/FLMF049641.pdf), [notes](https://reasonabledeviations.com/notes/adv_fin_ml)).
- For us:
  - Entry is the bar-t close plus fees.
  - y = 1 if the high reaches entry x 1.05 before the low reaches entry x 0.975 within H hours, else 0.
  - **Do not volatility-scale the barriers** (AFML's default). Our exits are fixed percentages, so the barriers must be too (my inference).
  - If one 1 h bar touches both barriers, count it as 0, or resolve it from 1 m candles.
  - Choose H once, from the time-to-resolution distribution of random entries in *training* data (for example its 75th percentile). Never tune it on the holdout.
- Expect a base rate near 0.34 (section 3.1). Positive sample drift will push the training base rate above that, so compare against each fold's own base rate, not 0.5.

**L2: full strategy replay label (the gate's own outcome).**
- From each candidate bar, replay the fixed rules: the DCA ladder, 2x sizing, the 2-per-24h cap, the budget cap, the trailing exits, fees and slippage.
- Record net trade return, number of DCA buys, maximum adverse excursion, and duration.
- Use it:
  - as the evaluation metric everywhere;
  - as an optional regression or ranking target (for example LightGBM on net return, or "number of DCA buys = 0");
  - for weighting L1 samples by outcome size (AFML ch. 4 suggests weights based on uniqueness and return size, per the [notes](https://reasonabledeviations.com/notes/adv_fin_ml)).
- Its label windows are long (DCA trades can run for weeks), so purging must use each trade's real end time.

**L3: meta-label.**
- Source: AFML ch. 3.6. The primary model sets the side with high recall, and a secondary classifier decides whether to act on each signal ([notes](https://reasonabledeviations.com/notes/adv_fin_ml)). Joubert, "Meta-Labeling: Theory and Framework", *J. Financial Data Science* 4(3), 2022 sets out the framework.
- For us: primary = the rank-1 trend floor, or the current pattern signal (long ≥ 3, short = 0). Secondary = LightGBM or LR predicting L1 on the primary's bars only. Enter if p > threshold, with the threshold set in inner validation folds.
- Evidence for meta-labelling comes mainly from the method's proponents (Hudson & Thames authors) and is not crypto-specific. I found no independent crypto test with costs.
- The nearest crypto triple-barrier evidence is Grądzki, Wójcik & Lessmann, "Algorithmic crypto trading using information-driven bars, triple barrier labeling and deep learning", *Financial Innovation* 11, 2025 ([Springer](https://link.springer.com/article/10.1186/s40854-025-00866-w)).
  - Source says: BTC and ETH tick data 2018-2023, CUSUM-filtered bars plus triple-barrier labels. It beat time bars and next-bar labels, "consistently positive" after costs.
  - Abstract only. Deep-learning models. Cost level unknown.

**Labels to avoid.** Next-bar direction and next-bar return.
- Jaquart et al. 2021: short holds made after-cost returns negative.
- Bysik & Ślepaczuk 2026: naive hourly sign trading at 10 bps lost 64% a year with XGBoost.
- Symmetric barriers do not match our exits.

**Overlap.** Labelling every hourly bar with H up to 72 h means each label overlaps with dozens of others.
- Use AFML ch. 4 average-uniqueness weights, which LightGBM and scikit-learn accept as `sample_weight`, or sequential bootstrap for forests ([notes](https://reasonabledeviations.com/notes/adv_fin_ml)).
- Simplest alternative: one candidate bar per coin per N hours.

### 3.3 How many samples, and pooling

**Effective samples (my inference, not sourced).**
- About 3 years of hourly bars is about 26,000 rows per major. With L1 labels resolving after tens of hours, average uniqueness of a few percent gives **hundreds of effective labels per coin**. HYPE (about 1 year) gets roughly a third of that.
- Pooling 7-9 coins gives low thousands, fewer in practice because coin returns are correlated.
- I found no sourced rule for the minimum samples a GBDT needs on financial labels.

**Pooling.** Pool by default.
- Sirignano & Cont, "Universal features of price formation in financial markets", *Quantitative Finance* 19(9), 2019 ([arXiv](https://arxiv.org/abs/1803.06917v1)). Source says: one model trained on all stocks beat asset-specific models out of sample, and also worked on stocks outside training. US equity order-book data, deep learning.
- Montero-Manso & Hyndman, "Principles and algorithms for forecasting groups of time series: Locality and globality", *IJF* 37(4), 2021 ([arXiv](https://arxiv.org/abs/2008.00444v3)). Source says: global models outperform local ones for groups of similar series. Their complexity stays constant as the group grows, while local complexity grows with it.
- Crypto studies that pool across coins: Jaquart et al. 2022 (100 coins), Cakici et al. 2024. Equities: Gu, Kelly & Xiu, "Empirical Asset Pricing via Machine Learning", *RFS* 33(5), 2020, which pools trees and nets across stocks.
- How to do it (my inference):
  - Use one pooled model with scale-free features (ratios, z-scores), plus coin volatility as a feature and optionally a coin-ID category.
  - Fit per-coin models only as a comparison arm.
  - Pooling is the only way HYPE gets a usable model.

### 3.4 Validation

1. **Purged, embargoed walk-forward for training and tuning.** Use an expanding window and refit monthly.
   - Purge from training every sample whose label window [t, t_end] overlaps the test window.
   - Embargo at least H hours after each test window, or the trade-duration cap for L2.
   - Tune hyperparameters in inner purged folds only. Source: AFML ch. 7. Ordinary k-fold "vastly over-inflates results" ([notes](https://reasonabledeviations.com/notes/adv_fin_ml)).
   - CPCV (AFML ch. 12) is optional for comparing settings. Arian, Norouzi Mobarekeh & Seco, "Backtest overfitting in the machine learning era", *Knowledge-Based Systems*, 2024 (DOI 10.1016/j.knosys.2024.112477) found CPCV had lower probability of backtest overfitting and higher deflated-Sharpe statistics than walk-forward, on synthetic data.
   - `skfolio` 1.12.5 (2026-10-29, BSD-3) ships `CombinatorialPurgedCV` and `WalkForward` ([PyPI](https://pypi.org/project/skfolio/)). The purging logic is also simple to write in-house.
   - Do not use `mlfinlab`: a fork states its code is under an "all rights reserved" licence ([famlafl on PyPI](https://pypi.org/project/famlafl/)).
2. **Keep the entry gate as the verdict, and give it power.**
   - The project notes record 6-14 holdout entries per coin.
   - **My calculation** (normal approximation, one-sided 95th percentile): the chance a model with a true per-trade improvement of δ standard deviations passes is Φ(δ√n - 1.645).

   | true edge δ | n = 10 | n = 50 | n = 100 | n = 300 |
   |---|---|---|---|---|
   | 0.1 SD | 9% | 17% | 26% | 54% |
   | 0.2 SD | 16% | 41% | 64% | 97% |
   | 0.5 SD | 48% | 97% | ~100% | ~100% |

   - **At 10 entries, a real but modest edge is missed most of the time.** Pool the gate across coins and across successive forward folds, so a model is judged on hundreds of entries. Random sets should still be drawn per coin and per fold, with the same counts.
3. **Correct for the number of models and coins.**
   - Sources:
     - Bailey & López de Prado, "The Deflated Sharpe Ratio", *JPM* 40(5), 2014 ([SSRN](https://papers.ssrn.com/abstract=2460551)). Source says: a holdout "does not eliminate data snooping bias when multiple strategies are tested against the same hold-out data".
     - White, "A Reality Check for Data Snooping", *Econometrica* 68(5), 2000.
     - Hansen, "A Test for Superior Predictive Ability", *JBES* 23, 2005 ([summary](https://economics.brown.edu/sites/g/files/dprerj726/files/papers/2003-9_paper.pdf)).
     - Masters, *Permutation and Randomization Tests for Trading System Development*, 2020. The random-entry gate is a form of this.
   - **My calculation:** 5 shortlisted models x 9 coins = 45 tests at the 95th percentile. With no skill anywhere, that gives about 2.3 expected false passes and about a 90% chance of at least one, if the tests were independent. The extra gate rules reduce this, and correlated tests change it.
   - Recommendations:
     - Count every model x feature-set x hyperparameter x coin as a trial, and report them all.
     - Apply Holm (or Bonferroni) across models on the pooled test.
     - Raise random sets from 1,000 to at least 10,000. With 1,000 sets the smallest p-value the gate can show is 0.001, which is already the Bonferroni level for 45 tests.
4. **Keep one final holdout untouched.** Use it once for the shortlist's survivors.

### 3.5 Data hygiene specific to this app

- **Multi-timeframe look-ahead.** Features from 4h/1d/1w candles must use the last *completed* candle at decision time. Sobreiro et al. 2026 found an alignment bug that inflated AUC by about 0.20. Our current model already works across 1h-1w timeframes, so this is a live risk.
- **Fees inside labels and gate.** Use 0.55% a side plus slippage, not 0.1%, in L2 and in any threshold choice.
- **Survivorship.**
  - The coin list was chosen in 2026. Training on coins that are known to have survived inflates trend-following results.
  - Zarattini et al. used survivorship-free data for this reason.
  - Delisted coins are already blocked in the app (market_status.json, per project notes). For research, keep their history in training where available.
- **Regime.** Every positive study above leans on bull periods (Han et al.: momentum negative in falling markets) or on beating a crashing buy-and-hold (Sebastião & Godinho). Report gate results per fold and per regime.

---

## 4. Rejected

- **XGBoost** (3.4.1, 2026-08-15, Apache-2.0, needs Python ≥ 3.12; a CPU-only `xgboost-cpu` wheel exists; [PyPI](https://pypi.org/project/xgboost/), [xgboost-cpu](https://pypi.org/project/xgboost-cpu/)). It duplicates LightGBM; no evidence it would differ here. Keep it as a fallback if LightGBM is unavailable.
- **CatBoost** (1.2.10, 2026-02-18, Apache-2.0, CPython 3.8-3.14; [PyPI](https://pypi.org/project/catboost/)). Same reason; larger and slower to train (*unsourced*).
- **k-nearest neighbours** (candle shapes or engineered features). The current kNN-like model already fails the gate (percentiles 0-94, mean about 38). The search found no crypto study of kNN with after-cost trading results, only error metrics.
- **SVM.**
  - Akyildirim, Goncu & Sensoy, *Annals of OR* 297, 2021 ([Bilkent](https://repository.bilkent.edu.tr/items/8f518a9d-24b8-4b2a-a6ea-f17847399ccd/full)): SVM was the most accurate of four classifiers (55-65% average accuracy). The study reports accuracy only, with no after-cost test confirmed.
  - scikit-learn's SVC fit time "scales at least quadratically with the number of samples and may be impractical beyond tens of thousands of samples", and its probability option is deprecated in favour of calibration ([docs](https://scikit-learn.org/stable/modules/generated/sklearn.svm.SVC.html)). Pooled hourly data is beyond that.
- **Any next-bar direction or next-hour return model** (linear regression, classifiers). It fails after costs at short holds (Jaquart et al. 2021; Bysik & Ślepaczuk 2026).
- **Cross-sectional long-short ML portfolios** (Jaquart et al. 2022; Cakici et al. 2024). These need shorting and a broad universe, and the alpha sits in small, illiquid coins. We are long-only spot on 9 coins.
- **Intraday time-of-day momentum** (Shen, Urquhart & Wang, "Bitcoin intraday time series momentum", *Financial Review* 57(2), 2022, [Birmingham](https://research.birmingham.ac.uk/en/publications/bitcoin-intraday-time-series-momentum/)). Half-hour returns on a volume clock; holds far too short for a 1.1% round trip.
- **Volatility filter as a standalone floor.**
  - I found no peer-reviewed crypto test of volatility filters as entry rules; only practitioner volatility-targeting backtests (for example [Advisor Perspectives commentary](https://www.advisorperspectives.com/commentaries/2025/11/02/client-portfolios-cant-stomach-ride-considered-crypto)), which disclose they are simulations.
  - Theory (section 3.1) says it cannot change the clean-win rate at zero drift.
  - Keep volatility as a *feature* and as a reporting split (depth of DCA and drawdown scale with it).
- **Order-book, funding-rate, on-chain and sentiment feature models.**
  - Jaquart et al. 2021 used blockchain and sentiment features, and Liu & Tsyvinski used Google searches.
  - These are extra data with their own sources and access terms, not costed here. Set aside until an OHLCV-only model passes; none of the shortlist needs them.
- **mlfinlab.** Licence problem (section 3.4).
- **Neural sequence models (LSTM/GRU/transformers).** Outside my scope (classic ML). Noted only because they were the winners in Jaquart et al. 2022 and were not better than XGBoost in Bysik & Ślepaczuk 2026.

---

## 5. What I couldn't establish

- **Jaquart et al. 2022 details.** The transaction-cost assumption, tree-model results and long-leg-only returns. The PDFs would not extract and ScienceDirect blocked fetching.
- **Cost assumptions in several rule studies.** Exact costs in Detzel et al. 2021, Corbet et al. 2019, Grobys et al. 2020, Wen et al. 2022 and Deprez & Frömmel 2024 (abstracts only).
- **Any study of our strategy type.** I found none, academic or otherwise, that tests ML or rule entries under DCA ladders and trailing exits against random entries. The search returned only bot vendors and repositories.
- **Sample-size rules.** No sourced rule for minimum labelled samples per coin for GBDT or LR on financial labels. My effective-sample figures are estimates.
- **Volatility filters.** No peer-reviewed evidence on crypto volatility filters at hourly-to-daily horizons.
- **Runtime on the owner's PC.** Training and prediction times for constraint 1 were not measured (no code run), and the app's Python version was not checked. That version matters: scikit-learn 1.9 needs ≥ 3.11 and XGBoost 3.4 needs ≥ 3.12.
- **How the app computes "return per trade".** Whether it is on total capital committed or on the first buy. This changes the clean-win arithmetic in 3.1. If it is on first-buy capital, DCA'd trades would look *better*, and L1 should be replaced by L2.
- **Publication status and dates.** Han, Kang & Ryu's publication status; the exact publication date of Sobreiro et al. (the preprint and MDPI pages disagree); the Grądzki et al. 2025 cost level.
- **Package dates.** The release dates and versions quoted are from PyPI pages fetched on 2026-11-05 and may move.
