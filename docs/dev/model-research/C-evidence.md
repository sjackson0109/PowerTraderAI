# C: Evidence audit on predicting crypto returns, and rules for the comparison harness

Research agent C, 2026-11-05. This is research only: no code was run and nothing was installed.

How to read this:
- Each claim has a source next to it: a URL, or a paper title and year.
- **[inference]** marks my own reasoning. It is not something a source says.
- **unverified** marks a detail I could not check in an accessible copy. Usually this is because only the abstract was readable: ScienceDirect, Springer and Wiley full texts were blocked.
- "From knowledge" marks a classic reference that I did not fetch in this session.

---

## 1. Verdict

1. **I found no credible published result where any model on OHLCV data beats simple baselines for spot, long-only crypto at hourly-to-daily horizons, after costs near ours (0.55% a fill, about 1.1% a round trip).** The positive results that survive scrutiny share three traits:
   - They are small and mostly at daily frequency.
   - They usually need shorting, small illiquid coins, or fees of 0.10-0.25% a side.
   - Several fade after the period studied.
2. **The best-supported signals are simple, untrained trend/momentum rules on large coins at daily frequency, plus a weaker "other coins' lagged returns" effect.** Where ML was compared with simple or linear methods, it added little. Hourly BTC looks close to efficient.
3. **At 6-33 held-out trades per coin, our gate can only detect edges of several percent per trade.** A realistic edge (my estimate: 0.2-1% per trade, [inference]) needs hundreds to thousands of pooled trades. So expect "no skill above random (base rate)" for most models. Also expect lucky passes, about 5% of all model x series x coin tests at the 95th percentile, unless the harness pools coins and corrects for multiple tests.

---

## 2. Evidence table

**Flaw codes:**

| Code | Meaning |
|---|---|
| C0 | No costs |
| C- | Costs well below ours (≤0.25% a side) |
| S | Needs shorting or long-short portfolios |
| U | Small or survivor-only universe |
| P | One short or particular period |
| M | Many configurations tried; the best is reported (corrected, or correction unverified) |
| B | Buy-and-hold is the only baseline |
| D | Needs data we lack (sentiment, on-chain, equities, order flow) |
| R | The result depends on the authors' own sizing or portfolio rules |
| IS | In-sample or largely in-sample |

### A. Broad tests that control for data snooping (closest to our multiple-model problem)

| Study | Year | Predicted | Horizon | Costs? | Baseline / correction | OOS? | Flaws | Result |
|---|---|---|---|---|---|---|---|---|
| Hudson & Urquhart, "Technical trading and cryptocurrencies", *Ann. Oper. Res.* 297 ([abstract](https://reading-clone.eprints-hosting.org/85715), [DOI](https://link.springer.com/article/10.1007/s10479-019-03357-1)) | 2021 | ~15,000 technical rules on BTC, ETH, LTC, XRP | Daily | Breakeven costs only | Multiple-hypothesis procedures, 1000 stationary-bootstrap p-values | Yes (sub-period) | U, M (corrected), C (breakeven, not actual) | Significant in sample after correction. **Out of sample: no predictability for Bitcoin**; some remains in the other three |
| Anghel, "A reality check on trading rule performance in the cryptocurrency market: ML vs technical analysis", *FRL* 39 ([abstract](https://ideas.repec.org/a/eee/finlet/v39y2021ics1544612320304414.html)) | 2021 | ML and technical rules | Several frequencies | "Market frictions" controlled (level unverified) | White's Reality Check / SPA framework | Yes | Details unverified (abstract only) | "Statistically significant positive excess returns are rarely achieved", whatever the frequency, position type or significance level. The cross-section of rule performance tracks beta and idiosyncratic volatility, so the rules mostly earn risk premia |
| Wei, Kyriakou, Sermpinis, Stasinakis, "Cryptocurrencies and Lucky Factors", *Int. J. Fin. Econ.* 29(4) ([record](https://eprints.gla.ac.uk/302711/)) | 2024 (online 2023) | 7,846 technical rules, 5 log moving-average ratios, 59 fundamental factors. 12 coins including BNB, DOGE, SOL, XRP, DASH, and Terra, which later failed | Unverified (likely daily) | Not in abstract | SPA test + Harvey-Liu "Lucky Factors" | Yes | C unverified | Only the **short-term log moving-average ratio** and the Hashrate Index show genuine in- and out-of-sample profitability. The authors "question the value of both technical and fundamental analysis" |
| Deprez & Frömmel, "Are simple technical trading rules profitable in bitcoin markets?", *IREF* 93 ([abstract](https://ideas.repec.org/a/eee/reveco/v93y2024ipbp858-874.html)) | 2024 | 75,360 simple rules on BTC | Daily + intraday | Yes, in selection (level unverified) | Multiple-hypothesis procedure; buy-and-hold | Yes (portfolios of selected rules) | B, cost level and sample unverified | Simple rules "can outperform buy-and-hold out-of-sample", mainly on a risk-adjusted basis |
| Li, "Profitability and data-snooping tests of four technical trade strategies for BTC/USDT and ETH/USDT ... 2022–2023", *J. Accounting & Finance* ([page](https://articlegateway.com/index.php/JAF/article/view/6453)) | c. 2023-24 (unverified) | 4 classes of technical strategy | Unverified | Unverified | Data-snooping-adjusted | Yes | P (2 years), minor journal | No profitable strategies in either the analysis sample or the prediction sample |
| Svogun & Bazán-Palomino, "Technical analysis in cryptocurrency markets: do transaction costs and bubbles matter?", *JIFMIM* 79 ([abstract](https://ideas.repec.org/a/eee/intfin/v79y2022ics1042443122000816.html)) | 2022 | 69 moving-average and breakout rules, 2016-2021 | Daily + 1-min | With and without | Buy-and-hold | n/a | B | Technical-analysis returns beyond buy-and-hold are statistically tied to formally dated **bubbles**, so they depend on the regime |

### B. Machine-learning studies

| Study | Year | Predicted | Horizon | Costs? | Baseline | OOS? | Flaws | Result |
|---|---|---|---|---|---|---|---|---|
| Gradojevic, Kukolj, Adcock, Djakovic, "Forecasting Bitcoin with technical analysis: a not-so-random forest?", *IJF* 39(1) ([record](https://econpapers.repec.org/RePEc:eee:intfor:v:39:y:2023:i:1:p:1-17)) | 2023 | BTC returns from technical features (random forest and others) | Hourly and daily | C0 (forecast test) | **Random walk** | Yes | Single coin; sample 2015-2019 per a secondary source (unverified) | **Hourly: no model beats the random walk** (weakly efficient). **Daily: random forest + technical features beats it significantly** |
| Puoti, Pittorino, Roveri, "Quantifying cryptocurrency unpredictability" (AIMLSystems 2024; [arXiv 2502.09079](https://arxiv.org/abs/2502.09079)) | 2024/25 | Prices of BTC, ETH, XRP, BNB, LTC. Naive, ARIMA, ETS, RF, XGBoost, RNN, LSTM, N-BEATS | 1, 7, 30 days | C0 | **Naive** | Yes (walk-forward per [Baquero 2026](https://arxiv.org/abs/2606.00071)) | Price-level accuracy, not trading | **Naive models beat ML and deep learning** across horizons and windows |
| Yae & Tian, "Out-of-sample forecasting of cryptocurrency returns", *Physica A* 598 ([abstract](https://ideas.repec.org/a/eee/phsmap/v598y2022ics0378437122002928.html)) | 2022 | Returns from many predictors and algorithms | Unverified | Unverified | Historical mean (OOS R²) | Yes | D (equity data) | Popular in-sample predictors (attention, volume) **fail out of sample**. Only the change in stochastic correlation with stocks works: OOS R² 2.69% BTC, 1.71% ETH, 2.12% XRP. Generic ML, shrinkage and combinations do worse than economically motivated methods |
| Jaquart, Dann, Weinhardt, "Short-term bitcoin market prediction via machine learning", *JFDS* 7 ([KIT](https://publikationen.bibliothek.kit.edu/1000150665)) | 2021 | BTC direction | 1-60 min | Yes | Random classifier | Yes | S, D (some blockchain and sentiment features) | All models beat a random classifier; RNN and gradient boosting are best. A long-short strategy makes **up to 39% a month before costs and is negative after costs** |
| Jaquart, Köpke, Weinhardt, "Machine learning for cryptocurrency market prediction and trading", *JFDS* 8 ([DOAJ](https://doaj.org/article/cfc09801314441198e3e1c92a3914e54)) | 2022 | Whether each of the top-100 coins beats the cross-section that day | Daily | Yes (level unverified) | Buy-and-hold | Yes | **S** (long-short relative bets), U (top-100 selection, survivorship handling unverified), B | Accuracy 52.9-54.1%, or 57.5-59.5% on the 10% most confident predictions. Long-short Sharpe 3.23 (LSTM) and 3.12 (GRU) after costs, against 1.33 for buy-and-hold. The authors cite possible limits to arbitrage |
| Akyildirim, Goncu, Sensoy, "Prediction of cryptocurrency returns using machine learning", *Ann. Oper. Res.* 297 ([record](https://repository.bilkent.edu.tr/items/8f518a9d-24b8-4b2a-a6ea-f17847399ccd/full)) | 2021 | Direction, 12 liquid coins | Daily + minute | C0 in abstract | 50% | Yes | No trading-after-cost result verified | SVM best; **55-65% average accuracy** |
| Fischer, Krauss, Deinert, "Statistical arbitrage in cryptocurrency markets", *JRFM* 12 ([MDPI](https://mdpi.com/1911-8074/12/1/31)) | 2019 | Whether each of 40 coins beats the cross-sectional median, using a random forest on lagged returns | 120 min | Yes (level unverified) | Logistic regression; buy-and-hold | Yes, **18 Jun to 17 Sep 2018 only** | S, P | 7.1 bp a day after costs, about 29% a year (logistic regression 18.8%). The authors flag volume limits |
| Sebastião & Godinho, "Forecasting and trading cryptocurrencies with ML under changing market conditions", *Financial Innovation* 7 ([record](https://estudogeral.sib.uc.pt/handle/10316/93816)) | 2021 | BTC, ETH, LTC, using trading and network (on-chain) features | Daily | **0.5% round trip** (about half ours) | Buy-and-hold | Yes: 13 Apr 2018 to 3 Mar 2019 (bear market) | P (one year), M (best of many variants), D, C- | The best ensemble trades only when 5 models agree. It earns 9.62% a year (ETH) and 5.73% a year (LTC) after costs. No BTC figure in the abstract |

### C. Cross-sectional anomaly and factor studies (mostly long-short)

| Study | Year | Predicted | Horizon | Costs? | Baseline | OOS? | Flaws | Result |
|---|---|---|---|---|---|---|---|---|
| Cakici, Shahzad, Będowska-Sójka, Zaremba, "Machine learning and the cross-section of cryptocurrency returns", *IRFA* 94 ([repository](https://open.icm.edu.pl/handle/123456789/25543)) | 2024 | Cross-section of many coins; ML vs linear | Portfolio rebalancing (likely weekly; unverified) | Yes | Factor alphas | Yes | S (portfolio construction), not our universe | Most ML strategies are profitable after costs, but **alphas "critically depend on harvesting extreme returns on small, illiquid, and volatile coins"**. Model complexity adds little. Returns come from the long leg |
| Fieberg, Liedtke, Zaremba, "Cryptocurrency anomalies and economic constraints", *IRFA* ([repository](https://open.icm.edu.pl/handle/123456789/25544)) | 2024 | Tradability of the known anomalies | Portfolio | Yes | Factor alphas | Yes | Same caveats | Size and volume anomalies come from **micro-caps**. Momentum holds in larger coins but has high trading costs and earns mostly **from short positions**. Abnormal returns occur mainly in **bull markets and fade over time**. Recommended protocol: long positions, costs, hard-to-trade coins, weight on recent years |
| Zaremba, Bilgin, Long, Mercik, Szczygielski, "Up or down? Short-term reversal, momentum, and liquidity effects in cryptocurrency markets", *IRFA* 78 ([abstract](https://aminer.org/pub/628d19b35aee126c0f369100/up-or-down-short-term-reversal-momentum-and-liquidity-effects-in-cryptocurrency)) | 2021 | Next-day cross-sectional returns from the last day's return | Daily | Unverified | Cross-section | Unverified | S | Reversal shows up in less liquid coins. **The largest, most tradeable coins show daily momentum**, not reversal |
| Guo, Sang, Tu, Wang, "Cross-cryptocurrency return predictability", *JEDC* 163 ([abstract](https://ideas.repec.org/a/eee/dyncon/v163y2024ics0165188924000551.html)) | 2024 | A coin's return from other coins' lagged returns (adaptive LASSO), Binance data | Daily | Yes (working paper) | Historical mean | Yes | S; the size is implausible | The working-paper version reports a long-short **2.16% a day** out of sample after costs. The authors' mechanism is slow information diffusion. Treat the size with caution |
| Liu & Tsyvinski, "Risks and returns of cryptocurrency", *RFS* 34(6) ([NBER](https://www.nber.org/papers/w24877)) | 2021 | BTC, ETH, XRP returns | Daily/weekly (details unverified) | C0 | n/a | Mostly IS predictive regressions | IS, D (attention proxies) | "Strong time-series momentum effect"; investor-attention proxies forecast returns |
| Shen, Urquhart, Wang, "Bitcoin intraday time series momentum", *Financial Review* 57(2) ([record](https://centaur.reading.ac.uk/100181)) | 2022 | BTC late-day return from early-day return | Intraday | Unverified | Unverified | Unverified | Single coin | Economic gains in market timing, **strongest in downturns**; linked to liquidity provision and to high-volume, high-volatility periods |

### D. Recent (2025-26) and practitioner evidence

| Study | Year | Predicted | Horizon | Costs? | Baseline | OOS? | Flaws | Result |
|---|---|---|---|---|---|---|---|---|
| Kitron & Wengrowicz, "Short-horizon mean reversion in cryptocurrency markets" ([arXiv 2608.21888](https://arxiv.org/abs/2608.21888), preprint) | 2026 | Next 15-min direction; 183 Binance pairs vs 187 US stocks/ETFs | 15 min | Yes (5 bp round trip) | Matched equities; **exact permutation null**; frozen 6-month holdout | Strict | Preprint | About 90% of pairs show significant reversal, against 2.7% of equities. But the **gross edge is about 1.3 bp a trade**, "too small to clear" costs. The design is rigorous and the effect is real, but it is ~85x smaller than our round-trip cost [inference: 110 bp / 1.3 bp] |
| Bysik & Ślepaczuk, "ML-based Bitcoin trading under transaction costs: evidence from walk-forward forecasting" ([arXiv 2606.00060](https://arxiv.org/abs/2606.00060), preprint) | 2026 | BTC-USDT, about 70k hourly bars 2018-2026; XGBoost, LSTM, iTransformer | Hourly | **10 bp per transaction** (~1/5 of ours) | Naive sign strategies | 27-fold walk-forward | M ("selected configurations"), C-, B-like (BTC rose strongly), single coin | Naive sign-based trading fails after costs. Trading only when the forecast exceeds a cost threshold restores profit "in selected configurations". The best is long-only XGBoost at >65% a year with Sharpe >1. **Bootstrap tests do not support XGBoost beating the neural models** |
| Zarattini, Pagani, Barbon, "Catching crypto trends: a tactical approach for Bitcoin and altcoins", SFI RP 25-80 ([Concretum](https://concretumgroup.com/catching-crypto-trends-a-tactical-approach-for-bitcoin-and-altcoins/), [CXO summary](https://www.cxoadvisory.com/technical-trading/crypto-asset-trend-following-strategies/)) | 2025 | Long-only Donchian-channel trend ensemble with volatility sizing; top-20 liquid coins rotated | Daily signals | 0.10 / 0.25 / 0.50% tested; headline at 0.10% | BTC buy-and-hold | Backtest 2015 to Mar 2025; **survivorship-free** (21,616 assets) | C- (headline), R, B, parameter selection unverified, practitioner authors | Sharpe >1.5 and about 11% a year net alpha against BTC (18% net CAGR per CXO). **The result at 0.50% was not verified.** This is the closest published design to our setting |
| G-Research Crypto Forecasting (Kaggle) ([wrap-up](https://www.gresearch.com/news/wrapping-up-the-g-research-crypto-forecasting-competition/), [one team's slides](https://docs.google.com/presentation/d/110XGGTDAQlnfa5psJPEi4r1EyB15_fEH/htmlpresent)) | Nov 2021 to May 2022 | Short-term returns of 14 coins. From memory the target was 15-min market-residualised returns (unverified) | Minutes | C0 | Weighted correlation; 3 months of **live** scoring | Live | Correlation metric, not P&L | The top 3 all used LightGBM, and the winners credited features over model choice. G-Research calls it a "low signal, high noise" setting. One silver-medal team scored 0.073-0.078 in CV against **~0.016-0.020 live**, about a 4x shrinkage |
| Islas Anguiano & García-Medina, "Technical analysis meets machine learning: Bitcoin evidence" ([arXiv 2511.00665](https://arxiv.org/abs/2511.00665)) | 2025 | BTC; LSTM, LightGBM, EMA, MACD | Unverified | Not stated | Buy-and-hold | Unverified | P (<1 year), B, C? | LSTM made +65% "in under a year". This is a typical example of the bulk literature: one short window, buy-and-hold baseline, no random or naive baseline |
| Baquero, "Bitcoin price prediction: peer-reviewed evidence and social media discourse" ([arXiv 2606.00071](https://arxiv.org/abs/2606.00071), preprint review) | 2026 | Review of 23 studies | Various | n/a | n/a | n/a | Preprint by one author | About **30% of studies use a naive or random-walk baseline**. Daily predictability depends on frequency and "may not survive transaction costs". The field needs better evaluation (walk-forward, multi-regime holdouts, naive baselines, Diebold-Mariano / Model Confidence Set tests), not more models |

### E. Decay, efficiency over time, and random baselines

| Study | Year | Finding | Relevance |
|---|---|---|---|
| McLean & Pontiff, "Does academic research destroy stock return predictability?", *JF* 71(1) ([issue](https://afajof.org/issue/volume-71-issue-1/)) | 2016 | 97 equity predictors: portfolio returns **26% lower out-of-sample and 58% lower post-publication** | The best quantitative estimate of decay, but for equities, not crypto |
| Sullivan, Timmermann, White, "Data-snooping, technical trading rule performance, and the bootstrap", *JF* 54(5) (from knowledge) | 1999 | The best DJIA rule was significant after the Reality Check in 1897-1986 but not in 1987-1996 | Rules that survive correction can still decay |
| Tran & Leirvik, "Efficiency in the markets of crypto-currencies", *FRL* 35 ([abstract](https://ideas.repec.org/a/eee/finlet/v35y2020ics1544612319310438.html)) | 2020 | The top-5 coins were mostly inefficient before 2017 and grew more efficient over 2017-2019 | Pre-2018 crypto studies may overstate today's predictability |
| Fieberg, Liedtke, Zaremba (above) | 2024 | Anomaly returns "fade over time" | Crypto-specific decay |
| Biondo, Pluchino, Rapisarda, Helbing, "Are random trading strategies more successful than technical ones?", *PLoS ONE* 8(7) ([PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC3708927/)) | 2013 | On stock indices over 15-20 years, standard technical strategies do no better than random ones on average | The only random-strategy baseline study I found; not crypto |
| Bergsli, Lind, Molnár, Polasik, "Forecasting volatility of Bitcoin", *RIBF* 59 ([PDF](https://core.ac.uk/download/491266028.pdf)) | 2022 | HAR on realised variance beats GARCH, most at short horizons | **Volatility** is forecastable; returns much less so |

### What survives, effect sizes, and decay

**Claims that survive scrutiny (with caveats):**
1. Daily trend and moving-average signals on BTC and large coins (Detzel et al. 2021; Wei et al. 2024; Zaremba et al. 2021; Deprez & Frömmel 2024; Zarattini et al. 2025).
   - Detzel, Liu, Strauss, Zhou, Zhu (2021), *Financial Management* 50(1), [abstract](https://ideas.repec.org/a/bla/finmgt/v50y2021i1p107-137.html): the ratio of price to its moving average forecasts daily BTC returns both in and out of sample.
   - Even here, Hudson & Urquhart found no BTC predictability out of sample, and Anghel and Li found little after data-snooping control. Svogun & Bazán-Palomino and Fieberg et al. tie the profits to bubbles and bull markets.
2. Short-horizon reversal exists, but at 15 minutes it is about 1.3 bp gross (Kitron & Wengrowicz 2026).
3. Cross-coin lead-lag (Guo et al. 2024) is reported, but only long-short.

**Claims that do not survive:**
- Intraday ML direction prediction after costs (Jaquart et al. 2021: 39% a month gross, negative net).
- Hourly forecasting against a random walk (Gradojevic et al. 2023).
- Complex deep learning against naive forecasts (Puoti et al.).
- Popular in-sample predictors out of sample (Yae & Tian 2022).
- Cross-sectional ML, unless you trade micro-caps (Cakici et al. 2024).

**Typical effect sizes when something survives:**
- Direction accuracy is 51-56%, or 57-59% on the most confident decile (Jaquart 2021/2022; Akyildirim 2021, 55-65%).
- Single-predictor OOS R² reaches about 2-3% at best (Yae & Tian).
- Live correlation at 15 min is about 0.02 (one Kaggle team).
- Gross 15-min reversal is about 1.3 bp.

**Decay:**
- Crypto: Hudson & Urquhart (no BTC predictability out of sample), Fieberg et al. ("fade over time"), Tran & Leirvik (efficiency rising).
- Equities: post-publication returns about 58% lower (McLean & Pontiff).
- CV to live in one Kaggle team: about 4x shrinkage.

**Our cost level is high for this literature.** Most studies assume 0.05-0.25% a side; only Zarattini (0.50%, result unverified) and Sebastião & Godinho (0.5% round trip) come close. [inference] High-turnover approaches are ruled out for us. Only multi-day holds can pay off the 1.1% round trip, and the extra 0.55% each DCA buy costs.

**Results that need what we cannot do or do not have:**
- Shorting: Jaquart 2021/2022, Fischer 2019, Cakici 2024, Fieberg 2024 (momentum), Guo 2024, Zaremba 2021.
- Sentiment, on-chain, equity or order-flow data: Liu & Tsyvinski, Sebastião & Godinho, Yae & Tian, Kitron & Wengrowicz (taker flow).
- The authors' own sizing and rotation: Zarattini.

**No study I found uses a random-entry baseline on crypto, or DCA/trailing-profit exits.** No published number transfers directly to our gate.

---

## 3. Model families with the best evidence for our setting (ranked, at most 6)

Our setting: spot, long-only, hourly-to-daily, 0.55% a fill, OHLCV only.

1. **Simple untrained trend/momentum rules on daily bars**: price above its moving average, Donchian breakout, N-day return above zero, and a BTC trend filter for altcoins.
   - **Evidence:** Detzel 2021; Wei 2024 (the short-term log MA ratio is one of only two survivors after SPA and Lucky Factors); Zaremba 2021 (daily momentum in the largest coins); Deprez & Frömmel 2024; Zarattini 2025 (long-only, survivorship-free).
   - **Against:** Anghel 2021, Li (2022-23), and Hudson & Urquhart (BTC out of sample).
   - **ML vs these rules:** the evidence says ML is rarely better. Cakici found complexity adds little, Puoti found naive models win, Yae & Tian found simple, economically motivated methods win, and Bysik & Ślepaczuk found no formal dominance.
   - **Fit:** they are long or flat by nature, trade rarely, and need no training.
   - **Use:** build these first, both as models and as the bar ML must clear.
   - **Caveat:** the profits sit in bull runs. Random entries in the same period benefit too, so the extra skill over random may be small [inference].
2. **Gradient-boosted trees (LightGBM/XGBoost) or random forests** on lagged-return and technical features at daily or 4h bars.
   - **Evidence:** Gradojevic 2023 (daily random forest beats the random walk); Bysik & Ślepaczuk 2026 (hourly long-only XGBoost with a cost threshold, at 10 bp); G-Research (top 3 used LightGBM); Fischer 2019 (random forest); Jaquart 2021 (gradient boosting among the best).
   - **How:** pool across coins, and trade only when the predicted edge exceeds costs. They are cheap on CPU.
   - **Caveat:** gains are fragile and reported "in selected configurations".
3. **Regularised linear or logistic models** (ridge, LASSO, elastic net) on a coin's own and other coins' lagged returns, especially BTC's lag for altcoins.
   - **Evidence:** Guo 2024 (cross-coin lags, adaptive LASSO); Cakici 2024 (linear is competitive); Yae & Tian 2022; Magner & Hardy 2022 (autoregressive models beat the random walk for some of 13 coins, as cited in [Baquero 2026](https://arxiv.org/abs/2606.00071); I did not fetch the paper).
   - **Why:** low variance, fast, and a second, stronger baseline.
4. **Short-horizon reversal / "buy the dip"** rules: oversold after a sharp drop, ideally after a high-volume move.
   - **Evidence:** reversal is everywhere at 15 minutes but about 1.3 bp gross (Kitron & Wengrowicz). Daily reversal sits in illiquid coins, while large coins show momentum (Zaremba 2021).
   - **Expectation:** low at our costs. It is worth one or two untrained rules only because our DCA exits already pay off dips, and it may duplicate what DCA does [inference].
5. **Small recurrent nets (GRU/LSTM)** on daily sequences, pooled across coins.
   - **Evidence is mixed:** positive but long-short in Jaquart 2022; negative after costs in Jaquart 2021; naive wins in Puoti; neural models no better than XGBoost in Bysik & Ślepaczuk; LSTM no better than a simple RNN in Berger & Koubová 2024 (as cited in Baquero 2026; not fetched).
   - **Use:** try only after families 1-3 have run on the same harness.
6. **Volatility and regime models** (HAR-RV, EGARCH, HMM) as entry filters.
   - **For:** volatility is forecastable (Bergsli 2022).
   - **Against:** I found no study showing that volatility forecasts improve long-only entry timing. An HMM with reinforcement learning showed no out-of-sample gain (Agakishiev et al. 2025, as cited in Baquero 2026; not fetched).
   - **Status:** experimental.

**Not shortlisted:**
- **k-NN / analog pattern matching** (the current model family). I found no credible crypto evidence with costs, and our own tests show no edge.
- **Transformers and foundation models.** I found no evidence of gains over gradient boosting: the G-Research winners used LightGBM, and Bysik & Ślepaczuk's iTransformer was not better.
- **Deep RL portfolio agents.** I found no credible after-cost out-of-sample evidence; not reviewed in depth.
- **Sentiment, attention, on-chain and order-flow models.** These need data we lack.

**Across all families [inference, using López de Prado 2018, *Advances in Financial Machine Learning*, ch. 3: triple-barrier labels and meta-labelling]:**
- Train on what the fixed strategy actually pays for. That is whether a trade entered at this bar reaches +5% (+2.5% after a DCA buy) before deep DCA or the end of the window, and its net return.
- Predicting the next candle's high and low is only loosely tied to that outcome.
- With meta-labelling, a model decides whether to take a simple base signal. This fits "the strategy is fixed; only the entry model changes".

---

## 4. Rules for our harness

### 4.0 What our gate is, statistically

**What it tests.** The gate is a Monte Carlo permutation (randomisation) test of entry timing. It is conditional on the realised price path and the fixed exits. The general method for trading systems is in Masters, *Permutation and Randomization Tests for Trading System Development* (2020) ([book page](https://www.goodreads.com/book/show/51518758-permutation-and-randomization-tests-for-trading-system-development)).

**Its p-value.** The one-sided p-value is p = (1 + number of random sets with mean ≥ the model's mean) / (B + 1). Phipson & Smyth, "Permutation p-values should never be zero", *Stat. Appl. Genet. Mol. Biol.* 9(1), 2010 (from knowledge).

**What a pass means.** Passing at the 95th percentile means p ≤ about 0.05, so each test passes 5% of no-skill models by chance [inference, from the definition].

**How false passes add up over M tests:**
- Expected false passes = 0.05 x M.
- P(at least one false pass) = 1 - 0.95^M. That is 92% for M = 50.
- Example: 6 families x 4 series x 3 hyperparameter settings x 9 coins = 648 coin-level tests, so about **32 lucky passes** are expected even if nothing works [inference, arithmetic].

### 4.1 White's Reality Check

**What it is.** White, "A reality check for data snooping", *Econometrica* 68(5), 2000 (from knowledge). It tests whether the *best* of K models beats a benchmark. The p-value comes from bootstrapping the maximum performance across all models jointly (stationary bootstrap: Politis & Romano, *JASA* 89, 1994). This corrects for having searched.

**Fits our test?** Yes, as a max-statistic permutation test [inference]:
1. Give each model m a score z_m = (model mean - mean of its random-set means) / SD of its random-set means.
2. For each random draw b, compute the same score for random set b of every model, and take the maximum over models.
3. The family-wise p-value is the share of draws where that maximum is at least the observed maximum.

If random sets are drawn independently per model, the null ignores the dependence between similar models. That makes the test conservative: still valid, but with less power.

**Recommend:** yes, as the family-wise check before promoting any model. Use the studentised form from 4.2.

### 4.2 Hansen's SPA test (and stepwise versions)

**What it is.** Hansen, "A test for superior predictive ability", *JBES* 23(4), 2005 (from knowledge). It improves the Reality Check by studentising each model's statistic and recentring the null. Clearly worse models then no longer inflate the null, so the test has more power when many weak models are included.

The stepwise versions return the *set* of models that beat the benchmark, with family-wise error control:
- Romano & Wolf StepM: "Stepwise multiple testing as formalized data snooping", *Econometrica* 73(4), 2005.
- Hsu, Hsu & Kuan Step-SPA: *J. Empirical Finance* 17(3), 2010.

Both are from knowledge. The Python package `arch` implements `SPA`, `StepM`, `MCS` and `RealityCheck` ([docs](https://arch.readthedocs.io/en/latest/multiple-comparison/multiple-comparison-reference.html)). Note it needs time series of losses per model and a block bootstrap.

**Fits our test?** Yes:
- The z-score above is already studentised, and our percentile is its rank form.
- To port Hansen's recentring, leave out of the null maximum any model whose observed z is significantly below 0, meaning worse than random [inference].
- To use `arch` directly, express each model as a monthly series of (trade return - random-set mean) [inference].

**Recommend:** SPA-style studentised max test, or **StepM** to get the passing set of (model, series) pairs. We want a set, not just "the best one is real".

### 4.3 Deflated Sharpe Ratio (Bailey & López de Prado)

**What it is.** Bailey & López de Prado, "The deflated Sharpe ratio: correcting for selection bias, backtest overfitting and non-normality", *JPM* 40(5), 2014 ([SSRN 2460551](https://papers.ssrn.com/abstract=2460551)). It gives the probability that the true Sharpe is above 0. It takes into account the expected maximum Sharpe of N trials (from the variance of Sharpes across trials), the sample length, and the skewness and kurtosis of returns.

A companion paper puts the selection problem in numbers: with 5 years of data, as few as ~45 independent configurations can produce a winner that looks good and has no out-of-sample value. It also says that if the number of configurations tried is not reported, the risk of overfitting cannot be judged. Bailey, Borwein, López de Prado, Zhu, "Pseudo-mathematics and financial charlatanism", *Notices AMS*, 2014 ([abstract](https://scholarworks.wmich.edu/math_pubs/40/)).

**Fits our test?** Only partly:
- It tests against Sharpe = 0, not against random entries.
- It could be applied to per-trade "trade return - random mean" values [inference].
- Our permutation test already copes with non-normality. The lasting value is the **honest trial count N**.

**Recommend:** log every trial (model x series x hyperparameters x coin scored on held-out data). Report the DSR with that N as a secondary number. Do not gate on it alone.

### 4.4 Probability of backtest overfitting (PBO) via CSCV

**What it is.** Bailey, Borwein, López de Prado, Zhu, "The probability of backtest overfitting", *J. Computational Finance* 20(4), 2017 ([SSRN 2326253](https://papers.ssrn.com/abstract=2326253)). The method, combinatorially symmetric cross-validation (CSCV), is model-free:
1. Split a time-ordered matrix (periods x configurations) into S blocks.
2. For every way of using half the blocks as in-sample, pick the in-sample best configuration and record its out-of-sample rank.
3. PBO is the share of splits where that in-sample best lands below the out-of-sample median.

**Fits our test?** Yes, as a diagnostic of the *selection process* across all trials in a batch. It needs per-block performance for each configuration, for example monthly pooled (trade return - random mean). With so few trades per coin per month, it only works pooled across coins [inference].

**Recommend:** compute PBO for each batch. My thresholds are my own judgement, not from the source: PBO > 0.5 means selection is no better than chance, so do not promote the batch winner. PBO < 0.2 is acceptable.

### 4.5 False discovery rate control

**What it is.** FDR control limits the expected *share* of false passes among all passes, instead of the chance of any false pass. That gives far more power when tests are many. Sources (all from knowledge):
- Benjamini & Hochberg, *JRSS-B* 57(1), 1995: valid under independence and positive dependence.
- Benjamini & Yekutieli, *Ann. Stat.* 29(4), 2001: valid under any dependence, more conservative.
- Barras, Scaillet & Wermers, *JF* 65(1), 2010: applied to fund alphas.
- Bajgrowicz & Scaillet, "Technical trading revisited: false discoveries, persistence tests, and transaction costs", *JFE* 106(3), 2012: applied to thousands of technical rules. After FDR control and costs, outperformance on the DJIA vanished in recent periods and did not persist.

**Fits our test?** Yes: the permutation p-values feed Benjamini-Hochberg directly. The catch is the p-value floor of 1/(B+1). With B = 1000 the smallest possible p is about 0.001. Benjamini-Hochberg at q = 0.10 over 450 tests needs a smallest p of 0.10/450 ≈ 0.0002, which cannot be reached. **B must be ≥ 10,000**, or the tail must come from a normal fit to the random-set means [inference].

**Recommend:** use Benjamini-Hochberg (or Benjamini-Yekutieli) at q = 0.10 as the stage-1 screen for "worth a lockbox look". Do not use it as the promotion rule.

### 4.6 Locked final holdout ("lockbox")

**What it is.** A final slice of data that is never used for training, tuning or selection. It is opened once per finalist. If the model fails, it is retired, with no re-tuning and retrying.
- Skocik et al., "I tried a bunch of things: the dangers of unexpected overfitting in classification", bioRxiv 078816, 2016 ([preprint](https://storage.prod.researchhub.com/uploads/papers/2025/11/22/078816v1.full.pdf)), recommends lock boxes, blind analysis and pre-registration. It was later published with Hosseini & Powell as first authors (journal details from knowledge).
- Dwork et al., "The reusable holdout", *Science* 349, 2015 (from knowledge), show that reusing a holdout adaptively overfits it, and propose Thresholdout as a controlled way to reuse it.

**Fits our test?** Yes: the same gate runs once on the lockbox. Use Bonferroni if there are a few finalists.

**Recommend:**
- Make the lockbox the **most recent ~6 months across all coins**: effects fade, so recent data is the relevant test (Fieberg 2024; McLean & Pontiff 2016).
- Log every opening.
- When new data arrives, fold the old lockbox into development and form a fresh one.
- Power caveat: 6 months pooled is about 50-150 trades. The lockbox catches leakage and overfitting; it cannot prove a small edge [inference].

### 4.7 Walk-forward and combinatorial purged cross-validation

**What they are** (López de Prado 2018, *Advances in Financial Machine Learning*, ch. 7 and 12, from knowledge):
- **Walk-forward** trains on the past, tests on the next block, then rolls forward.
- **Combinatorial purged cross-validation (CPCV)** splits the data into N groups and tests on every combination of k groups, which gives many backtest paths. It **purges** training samples whose label window overlaps the test, and **embargoes** samples right after the test.
- Arian, Norouzi Mobarekeh, Seco, "Backtest overfitting in the machine learning era", *Knowledge-Based Systems*, 2024 (DOI 10.1016/j.knosys.2024.112477), found CPCV had lower PBO and higher DSR than walk-forward. Their test used synthetic data plus the S&P 500.

**Fits our test?**
- **Walk-forward fits our path-dependent replay directly.** Stitch the walk-forward test blocks into one continuous out-of-sample stream, where each bar is scored by a model trained only on earlier data. Then replay trades one at a time over that stream. This gives *years* of held-out trades instead of one 7-month split [inference].
- CPCV can help with model selection, but non-contiguous test groups break the one-trade-at-a-time DCA replay. Trades that cross group boundaries need closing or marking [inference].

**Recommend:** an expanding-window walk-forward, retrained at the app's cadence. Purge at least the label horizon plus the longest feature lookback, and embargo at least the label horizon. Treat CPCV as an optional second opinion on selection.

### 4.8 Pooling coins

**What it is.** Two forms:
- Pool trades from all coins into one test: either the pooled mean of (trade return - random mean), or Stouffer's combination of per-coin z-scores (sum of z / √K).
- Pool training: one model for all coins with scale-free features. Jaquart 2022, Cakici 2024, Fischer 2019 and the G-Research winners all did this.

**Fits our test?** Yes. Random sets are still drawn per coin with the same entry counts. But coins move together: correlations are positive and change over time (Gómez-Martínez & Medrano-Garcia, *Sustainable Technology and Entrepreneurship*, 2025, DOI 10.1016/j.stae.2024.100087; the market factor in Liu, Tsyvinski, Wu, "Common risk factors in cryptocurrency", *JF* 2022). So pooled trades are not independent. To keep that in the null, use the same random calendar offsets for every coin within draw b, or block-bootstrap by calendar month [inference].

**Recommend:** decide pass/fail at the pooled level. Report per-coin numbers, and decide per-coin on/off by shrinking each coin's estimate toward the pooled one (empirical Bayes: Efron & Morris, *JASA* 70, 1975, from knowledge), not by per-coin percentiles.

### 4.9 Other rules the evidence supports

- **Naive baselines as competitors.** Include "always enter when flat", 2-3 untrained trend and dip rules, and persistence. Baquero 2026 recommends naive baselines, and Puoti found naive models win. ML must beat random entries *and* the best simple rule on the same held-out data.
- **Costs inside the test, plus a sensitivity check** at 0.25 / 0.55 / 0.75% a fill. Anghel 2022 makes this point in its title ("No pain, no gain: you should always incorporate trading costs for a bias-free evaluation of trading rule overperformance", *Econ. Letters* 216, [record](https://ideas.repec.org:443/a/eee/ecolet/v216y2022ics0165176522001720.html)). Jaquart 2021 shows a 39%-a-month edge turning negative.
- **Report rising and falling markets separately**, because profits cluster in bubbles and bull markets (Svogun & Bazán-Palomino 2022; Fieberg 2024).
- **Measure return per capital-day as well as per trade** [inference]. Mean return per trade ignores how long capital is tied up. Entries made just before long drawdowns can look good per trade because the DCA doublings enlarge the position.
- **Add a second null that keeps the model's clustering** [inference]. Uniform random entries do not reproduce how the model's entries cluster in time. Adding a "circular shift" null (the model's own entry series rotated by a random offset) controls for that.

### 4.10 How many trades are needed

**Reasoning.** Under no skill, a model's mean per-trade return behaves like one random set's mean. Its SD is about σ/√n, where σ is the SD of one trade's net return under the fixed rules. A one-sided test at level α with power 1-β needs:

n ≈ ((z_α + z_β) · σ / Δ)²

where Δ is the true edge per trade over random entries. This is the standard two-sided-normal power calculation. It matches the "minimum track record length" for a Sharpe ratio (Bailey & López de Prado, "The Sharpe ratio efficient frontier", *J. of Risk* 15(2), 2012, from knowledge). That version adds a factor [1 - γ₃·SR + (γ₄-1)/4·SR²], which *raises* n for negatively skewed, fat-tailed returns like ours: many small wins and rare large marked-down losses (see also Lo, "The statistics of Sharpe ratios", *FAJ* 2002).

**Trades needed** (α = 0.05, the 95th percentile, power 80%, so z_α + z_β = 2.49; normal approximation; trades assumed independent):

| σ per trade \ edge Δ | 0.25% | 0.5% | 1% | 2% | 4% |
|---|---|---|---|---|---|
| 4% | 1,583 | 396 | 99 | 25 | 6 |
| 8% | 6,333 | 1,583 | 396 | 99 | 25 |
| 12% | 14,250 | 3,562 | 891 | 223 | 56 |

- With a Bonferroni correction for 100 tests (α = 0.0005), multiply by about 2.8.
- Correlated trades (same regime, coins moving together) raise n further.

**Smallest detectable edge at our current sample sizes** (σ = 8%, an assumption):

| Trades | Smallest detectable edge per trade |
|---|---|
| 6 | 8.1% |
| 20 | 4.4% |
| 33 | 3.5% |
| 150 (pooled) | 1.6% |
| 600 | 0.8% |

**What a realistic edge is [inference].** The published sizes are 51-56% accuracy, OOS R² ≤ ~3%, and live correlation of ~0.02 at 15 minutes. Grinold's "fundamental law of active management" (*JPM* 15(3), 1989, from knowledge) gives the expected excess per bet as roughly correlation x σ over the horizon x selectivity. With correlation 0.03-0.05, multi-day σ of 5-10%, and selectivity of about 1-1.4, that is roughly **0.15-0.7% per trade**. Plan for Δ ≈ 0.5%, which means **about 400 to 3,500 pooled trades** depending on σ. That is years of walk-forward history across 7-9 coins, not 7 months.

**Practical rule [inference]:**
- The harness can measure its own power. The minimum detectable edge ≈ 2.49 x (SD of the random-set means).
- If that is above ~1% per trade, label the result **"underpowered: no verdict"**, not "fail" and certainly not "pass".
- A cheap screen with far more observations: for every held-out bar t, compute R(t), the net return of a trade entered at t under the fixed rules (ignoring one-at-a-time). These values *are* the random-entry population.
- Score each model by the rank correlation between its signal and R(t) over all bars, with a block bootstrap because R(t) values overlap heavily.
- Use this screen to discard weak models early. The trade-replay gate stays the final judge.

### 4.11 Recommended set

1. **Pre-register each batch** before running it: models, series, hyperparameter grid, coins (including any later delisted, to avoid survivorship), metrics and thresholds. **Log every trial** to give the trial count N (DSR, PBO, the Bailey et al. reporting rule).
2. **Develop with an expanding walk-forward**, with purge and embargo. Replay trades over the stitched out-of-sample stream, aiming for at least 2 years of it.
3. **Keep a lockbox**: the most recent ~6 months, all coins, opened once per finalist and logged. A failure retires the model.
4. **Put baselines in every batch**: random entries (the existing gate), always-enter, and 2-3 untrained trend and dip rules. Promote a model only if it beats random entries *and* the best simple rule.
5. **Make the pooled test across coins the primary test.** Draw random sets with a shared calendar for each draw. Make per-coin decisions by shrinking toward the pooled estimate.
6. **Use B ≥ 10,000 random sets**, with p = (1+k)/(B+1).
7. **Three stages:**
   - Stage 1: Benjamini-Hochberg FDR at q = 0.10 over all (model x series) pooled tests gives candidates.
   - Stage 2: a studentised max test (Reality Check/SPA style), or StepM, at 5% family-wise error over *all* trials in the batch gives finalists.
   - Stage 3: the lockbox.
8. **Report the minimum detectable edge on every result**, and call a result "underpowered" when it is above 1% per trade.
9. **Report PBO** (CSCV on pooled monthly excess returns) **and DSR** (with the logged N) as diagnostics. Do not promote if PBO > 0.5.
10. **Report fee sensitivity** (0.25 / 0.55 / 0.75% a fill), a rising/falling-market split, and return per capital-day alongside return per trade.

---

## 5. What I couldn't establish

- **Exact cost assumptions** in Jaquart 2022, Fischer 2019, Detzel 2021, Deprez & Frömmel 2024 and Anghel 2021. Only abstracts were accessible.
- **Zarattini et al. at 0.50% costs.** Results were only seen at the 0.10% headline, and I could not check how parameters were chosen.
- **G-Research details**: the exact target definition and the winning live score. Only one team's slides were readable.
- **Horizon details** for Liu & Tsyvinski 2021, Yae & Tian 2022 and Wei et al. 2024; the year of the Li (JAF) paper; the sample periods of several abstract-only papers.
- **Any peer-reviewed crypto study with a random-entry baseline**, or one that evaluates ML entries under DCA/trailing-profit exits. None found. The nearest is Biondo et al. 2013, on stocks.
- **A formal post-publication decay test for crypto anomalies.** None found, only "fade over time" statements and efficiency trends.
- **Evidence specific to ZEC, DASH and HYPE.** Almost none: HYPE's history is short, and DASH appears only in Wei et al. 2024.
- **σ of per-trade returns under our exact rules.** The sample-size table uses assumed values. The harness should measure σ from its random sets.
- **Several studies cited only through Baquero's 2026 review** (Magner & Hardy 2022, Berger & Koubová 2024, Agakishiev et al. 2025, Arain & Snudden 2025) were not fetched.
- **Out-of-date and unreviewed sources.** Studies before 2020 describe a less efficient market (Tran & Leirvik). The 2025-26 arXiv items are unreviewed preprints. G-Research ran in 2021-22.
