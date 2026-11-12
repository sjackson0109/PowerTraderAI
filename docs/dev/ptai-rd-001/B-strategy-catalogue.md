# B: Strategy, signal, model and data-source catalogue (PTAI-RD-001, Deliverable B)

**Date:** 2026-11-11.
**Machine-readable companion:** `B-candidates.json`: 130 candidates, one object per candidate, with parameter variants grouped.
**Extends:** `docs/dev/strategy-research/A-research-report.md` (the A report) and `docs/dev/model-research/C-evidence.md`.
- Their citations are reused where they are correct, and are marked "via A" or "via C" in the JSON.
- This catalogue does not repeat their prose. It adds the families they did not cover:
  - volume, liquidity and microstructure;
  - volatility models;
  - statistical, ML and LLM models;
  - additional data sources;
  - risk and portfolio rules;
  - licensing;
  - a high-return audit.

**Scope:**
- long-only spot crypto on Coinbase (primary), Kraken, KuCoin and Binance;
- the coins BTC, ETH, XRP, BNB, SOL, DOGE, ZEC, DASH and HYPE;
- accounts of £50, £200, £500 and £10,000.

**Costs used throughout:**
- the 0.50% taker fee plus 0.05% slippage: 0.55% a side, 1.10% a round trip;
- yearly drag ≈ round trips per coin-year × 1.10%. For example, 4 round trips ≈ 4.4% a year and 52 ≈ 57%.

**How to read it:**
- Each source's finding in the JSON starts with what was read:
  - **[FT]** full text (or the relevant section);
  - **[A]** abstract or record page only;
  - **[S]** a secondary summary or search extract only.
- [R] marks this catalogue's own reasoning.
- Figures are quoted only from what was read. "Gross" means before costs, and "long-short" means the result needs shorting.
- Sources that were known but could not be confirmed are listed in §14. They are not cited in the JSON, and no numbers are taken from them.
- **Priority:**
  - **1:** test next.
  - **2:** test soon, or infrastructure that every test needs.
  - **3:** research later.
  - **4:** low; keep only as a falsification control.
  - **5:** not feasible here (shorting, leverage, derivatives positions, paid data, or terms that forbid the use).
- Headline returns never set the priority.

> **Read this first.**
> - No published study tests a crypto rule at 0.55% a side. The closest published cost levels are:
>   - 0.50% a trade in Zarattini, Pagani and Barbon (2025, working paper);
>   - a 0.5% round trip in Sebastião and Godinho (2021).
> - Every published result above about 30% a year in this catalogue has at least one of these features:
>   - it is long-short;
>   - it is intraday;
>   - it uses fees of 10 bp or less;
>   - it is before costs;
>   - it is the best of many configurations;
>   - it comes from a few months of data.
> - The only well-evidenced fit to this account is still a slow, daily, long-or-cash trend or breakout rule with a few round trips a year. That is what STRAT-004 and STRAT-005 already are.
> - The repository's own development result: STRAT-004 netted +23.6% over 4.3 years and beat random entries, but stayed below buy-and-hold (+27%). That sets the bar every candidate below must clear.

---

## 1. Summary

### 1.1 Candidates by family and priority

| family | candidates | P1 | P2 | P3 | P4 | P5 |
|---|---|---|---|---|---|---|
| trend | 8 | 1 | 1 | 1 | 5 | 0 |
| breakout | 4 | 2 | 0 | 1 | 1 | 0 |
| momentum | 4 | 1 | 1 | 0 | 1 | 1 |
| relative_strength | 3 | 0 | 0 | 3 | 0 | 0 |
| mean_reversion | 7 | 0 | 0 | 0 | 7 | 0 |
| stat_arb | 3 | 0 | 0 | 0 | 1 | 2 |
| regime | 17 | 1 | 1 | 5 | 8 | 2 |
| volume | 8 | 0 | 0 | 2 | 6 | 0 |
| liquidity | 4 | 0 | 1 | 1 | 2 | 0 |
| microstructure | 9 | 0 | 0 | 0 | 8 | 1 |
| volatility | 8 | 0 | 3 | 2 | 3 | 0 |
| ml_model | 15 | 0 | 2 | 4 | 9 | 0 |
| llm | 5 | 0 | 0 | 3 | 2 | 0 |
| risk | 9 | 0 | 4 | 3 | 2 | 0 |
| portfolio | 5 | 0 | 2 | 3 | 0 | 0 |
| data_source | 21 | 1 | 2 | 5 | 9 | 4 |
| **total** | **130** | **6** | **17** | **33** | **64** | **10** |

The `regime` family also holds the slow alternative-data signals: Fear & Greed, attention, sentiment, on-chain and the leverage/carry veto. These are gates or regime inputs, and the schema has no separate sentiment family.

**Merges at assembly:**
- `volatility.regime-filter` went into `regime.volatility-filter`.
- `volatility.atr-stops-and-sizing` went into `risk.atr-trailing-stop`.
- `momentum.cross-coin-lead-lag` went into `relative_strength.btc-lead-lag`.

### 1.2 Main findings

1. **Slow trend and breakout rules are the only family with crypto evidence that is out of sample or corrected for data snooping, and that is long-only compatible and survives the fee arithmetic.**
   - Detzel et al. 2021; Wei et al. 2024; Gerritsen et al. 2020; Zarattini et al. 2025 (working paper).
   - Everything else is one of three things:
     - long-short (cross-sectional momentum, pairs, lead-lag, CTREND, most ML);
     - too fast for 1.10% a round trip (intraday momentum, microstructure, short-term reversal, calendar effects);
     - unsupported (MACD, Supertrend, ADX, oscillators, candlestick and chart patterns, OBV/MFI/VWAP, squeezes).
2. **For large coins at daily and weekly horizons, the evidence shows continuation, not reversal.** Every mean-reversion candidate is priority 4.
3. **Machine learning adds little over simple rules on large coins, and nothing proven after these costs.** Its best use here is as a filter that can only remove trades:
   - meta-labelling of STRAT-004/005 entries;
   - a calibrated expected-value gate.
   - The binding constraint is the label count: about 120-310 trades over 4.3 years across 9 coins [R].
4. **LLM trading results are dominated by look-ahead and memorisation.**
   - Published LLM agents lost 51-62% of their Sharpe ratio once tested after the model's cut-off (Profit Mirage, 2025).
   - No crypto study was confirmed that tests LLM sentiment against out-of-sample returns.
   - The only clean design is forward-only, as a veto on a slow rule, against a random-slot baseline. The app's `llm_gate` already does this.
5. **Data.**
   - Coinbase public endpoints cover everything the priority-1 and priority-2 candidates need.
   - Binance Vision is the only free bulk archive of trades, funding and open interest. Its terms (CC BY-NC-SA 4.0) allow "algorithmic historical backtesting for purely personal non-production research" and forbid "live proprietary trading execution".
   - Free sentiment, social and on-chain sources are thin, restricted, or have no demonstrated out-of-sample value.
6. **Licensing.**
   - Permissive libraries cover every priority-1 and priority-2 need: TA-Lib, ta, statsmodels, arch, scikit-learn, LightGBM, XGBoost, hmmlearn and skfolio.
   - Several common choices cannot be reused as code:
     - GPL/AGPL: freqtrade, backtrader, backtesting.py;
     - Commons Clause: vectorbt;
     - proprietary: mlfinlab;
     - non-commercial weights: FinBERT on Hugging Face, Moirai, TimesFM 3.0.
   - pandas-ta's current licence could not be confirmed.

### 1.3 Summary table (all candidates)

- **Data** lists the data the candidate needs. Anything other than `ohlcv` needs a feed beyond candles.
- **Trades / coin / yr** is the estimated round trips per coin per year, abbreviated from the JSON. "Gate" or "veto" means the candidate adds no trades.

| id | family | data | evidence | crypto evidence | trades / coin / yr | priority | repo |
|---|---|---|---|---|---|---|---|
| `trend.price-above-ma` | trend | ohlcv | moderate | mixed | 3-10 (50-200d MA) | 1 | related:STRAT-005 |
| `trend.ma-crossover` | trend | ohlcv | moderate | mixed | 1-3 daily; 100+ at 1h | 2 | implemented:STRAT-000 |
| `trend.multi-timeframe` | trend | ohlcv | anecdotal | mixed | filter | 3 | related:OVL-REGIME |
| `trend.adx-filter` | trend | ohlcv | weak | none | filter (adds 0) | 4 | implemented:STRAT-001 |
| `trend.dema-tema-adx` | trend | ohlcv | weak | negative | ~60 at 1h | 4 | implemented:STRAT-001 |
| `trend.macd` | trend | ohlcv | weak | negative | ~320 at 1h; 10-20 daily | 4 | absent |
| `trend.psar-ichimoku` | trend | ohlcv | weak | mixed | 15-40 PSAR; 4-10 Ichimoku | 4 | absent |
| `trend.supertrend` | trend | ohlcv | anecdotal | negative | 20-40 at 4h; 5-12 daily | 4 | implemented:STRAT-002 |
| `breakout.donchian-turtle` | breakout | ohlcv | moderate | positive | 3-4 (S2); 7-8 (S1) | 1 | implemented:STRAT-004 |
| `breakout.zarattini-ensemble` | breakout | ohlcv | moderate | positive | 3-8 at 20-60d (0.5-29 by lookback) | 1 | related:STRAT-004 |
| `breakout.52wk-high-proximity` | breakout | ohlcv | moderate | none | 0.5-1 | 3 | related:STRAT-004 |
| `breakout.intraday-orb` | breakout | ohlcv | weak | mixed | 100-365+ | 4 | absent |
| `momentum.tsmom` | momentum | ohlcv | strong | mixed | 2-6 | 1 | implemented:STRAT-005 |
| `momentum.dual-momentum` | momentum | ohlcv | anecdotal | positive | 4-12 | 2 | related:STRAT-005 |
| `momentum.intraday-tsmom` | momentum | ohlcv | moderate | positive | up to 365 | 4 | absent |
| `momentum.cross-sectional-long-short` | momentum | ohlcv | moderate | mixed | ~17 per slot (weekly) | 5 | absent |
| `relative_strength.btc-lead-lag` | relative_strength | ohlcv | moderate | mixed | gate (adds 0); tens standalone | 3 | related:signal_fusion |
| `relative_strength.coin-vs-btc-ratio` | relative_strength | ohlcv | weak | none | 4-12 | 3 | absent |
| `relative_strength.top-k-rotation` | relative_strength | ohlcv | moderate | mixed | 10-25 swaps per book | 3 | related:portfolio_optimizer |
| `mean_reversion.bollinger` | mean_reversion | ohlcv | weak | mixed | ~15 daily | 4 | absent |
| `mean_reversion.candlestick-patterns` | mean_reversion | ohlcv | weak | negative | 10-50 | 4 | related:candlestick_patterns |
| `mean_reversion.chart-patterns` | mean_reversion | ohlcv | weak | none | a few to 10 | 4 | related:candlestick_patterns |
| `mean_reversion.rsi14-30-70` | mean_reversion | ohlcv | weak | negative | 2-4 daily | 4 | absent |
| `mean_reversion.rsi2-connors` | mean_reversion | ohlcv | weak | none | 5-15 | 4 | absent |
| `mean_reversion.short-term-reversal-dip` | mean_reversion | ohlcv | moderate | negative | 5-20 daily | 4 | related:pt_trader DCA ladder |
| `mean_reversion.stochastic-williams-r` | mean_reversion | ohlcv | anecdotal | none | 10-25 | 4 | absent |
| `stat_arb.long-only-leg-rotation` | stat_arb | ohlcv | weak | negative | 4-12 daily | 4 | absent |
| `stat_arb.funding-cash-and-carry` | stat_arb | funding, ohlcv, cross_exchange | moderate | positive | continuous (perps) | 5 | absent |
| `stat_arb.pairs-cointegration` | stat_arb | ohlcv | moderate | mixed | hundreds (intraday) | 5 | absent |
| `regime.ma-trend-gate` | regime | ohlcv | moderate | mixed | veto (adds 0) | 1 | implemented:OVL-REGIME |
| `regime.leverage-carry-veto` | regime | funding, ohlcv | weak | mixed | veto (adds 0) | 2 | absent |
| `regime.drawdown-from-high` | regime | ohlcv | weak | none | gate | 3 | absent |
| `regime.fear-greed-index` | regime | social, ohlcv | weak | mixed | gate; 2-6 contrarian | 3 | absent |
| `regime.hmm-markov-switching` | regime | ohlcv | weak | none | 2-6 (persistent regimes) | 3 | related:OVL-REGIME |
| `regime.onchain-activity-hashrate` | regime | on_chain | moderate | positive | 1-4 | 3 | absent |
| `regime.volatility-filter` | regime | ohlcv | weak | none | veto (adds 0) | 3 | related:signal_fusion |
| `regime.bubble-state` | regime | ohlcv | moderate | mixed | gate | 4 | absent |
| `regime.calendar-weekly-monthly` | regime | ohlcv | weak | mixed | 12-52 | 4 | absent |
| `regime.halving-cycle` | regime | ohlcv | anecdotal | mixed | 0.25-0.5 | 4 | absent |
| `regime.intraday-seasonality` | regime | ohlcv | anecdotal | mixed | 365 | 4 | absent |
| `regime.news-coverage` | regime | news | weak | mixed | daily; few as gate | 4 | related:llm_gate |
| `regime.onchain-valuation` | regime | on_chain | weak | negative | 1-3 | 4 | absent |
| `regime.search-attention` | regime | social | weak | negative | a few to 12 | 4 | absent |
| `regime.stablecoin-issuance` | regime | on_chain | moderate | mixed | gate | 4 | absent |
| `regime.exchange-flows-whales` | regime | on_chain, social | weak | mixed | veto | 5 | absent |
| `regime.social-media-sentiment` | regime | social | weak | mixed | dozens | 5 | related:llm_gate |
| `volume.ctrend-trend-factor` | volume | ohlcv | moderate | positive | 10-30 (weekly) | 3 | absent |
| `volume.relative-volume` | volume | ohlcv | moderate | mixed | filter (2-6 of host's 3-8) | 3 | related:signal_fusion |
| `volume.cmf` | volume | ohlcv | weak | negative | veto on host | 4 | related:signal_fusion |
| `volume.mfi` | volume | ohlcv | anecdotal | none | 5-15 | 4 | absent |
| `volume.obv` | volume | ohlcv | weak | none | 6-20 standalone | 4 | absent |
| `volume.volume-price-divergence` | volume | ohlcv | weak | none | filter | 4 | absent |
| `volume.volume-profile` | volume | trades, ohlcv | anecdotal | none | >20 (est.) | 4 | absent |
| `volume.vwap-signals` | volume | ohlcv, trades | anecdotal | none | >250 intraday; 3-10 daily | 4 | absent |
| `liquidity.spread-depth-filter` | liquidity | order_book | moderate | positive | gate (adds 0) | 2 | related:signal_fusion |
| `liquidity.intraday-execution-timing` | liquidity | ohlcv, order_book | moderate | positive | adds 0 | 3 | absent |
| `liquidity.amihud-illiquidity` | liquidity | ohlcv | moderate | mixed | 52 rebalances (cross-section) | 4 | related:signal_fusion |
| `liquidity.volume-conditioned-reversal` | liquidity | ohlcv | moderate | mixed | hundreds | 4 | absent |
| `microstructure.cross-exchange-premium` | microstructure | cross_exchange, ohlcv | weak | mixed | gate | 4 | absent |
| `microstructure.funding-rate-contrarian` | microstructure | funding, ohlcv | anecdotal | mixed | 2-6 | 4 | absent |
| `microstructure.large-trade-whale-prints` | microstructure | trades, on_chain | weak | mixed | dozens (est.) | 4 | absent |
| `microstructure.liquidation-cascade-rebound` | microstructure | liquidations, ohlcv | anecdotal | none | 2-8 events | 4 | absent |
| `microstructure.open-interest-change` | microstructure | open_interest, ohlcv | anecdotal | none | unknown | 4 | absent |
| `microstructure.taker-flow-reversal-15m` | microstructure | trades, order_book, ohlcv | strong | negative | tens of thousands | 4 | absent |
| `microstructure.trade-flow-imbalance` | microstructure | trades | moderate | mixed | hundreds+ intraday | 4 | absent |
| `microstructure.vpin-toxicity` | microstructure | trades, ohlcv | moderate | mixed | veto | 4 | absent |
| `microstructure.order-book-imbalance` | microstructure | order_book | strong | positive | thousands | 5 | absent |
| `volatility.ewma-riskmetrics` | volatility | ohlcv | moderate | none | input | 2 | related:signal_fusion |
| `volatility.realised-vol-estimators` | volatility | ohlcv | strong | positive | input | 2 | related:signal_fusion |
| `volatility.vol-targeting-sizing` | volatility | ohlcv | moderate | mixed | 0 if sized at entry | 2 | related:signal_fusion |
| `volatility.garch-family` | volatility | ohlcv | moderate | mixed | input | 3 | absent |
| `volatility.har-rv` | volatility | ohlcv | strong | positive | input | 3 | absent |
| `volatility.implied-vol-dvol` | volatility | cross_exchange | weak | none | gate | 4 | absent |
| `volatility.range-breakout` | volatility | ohlcv | anecdotal | none | 100-250 | 4 | absent |
| `volatility.squeeze` | volatility | ohlcv | moderate | none | ~5 daily | 4 | absent |
| `ml_model.calibration-ev-gate` | ml_model | ohlcv | moderate | mixed | removes only | 2 | related:model_lab |
| `ml_model.meta-labelling` | ml_model | ohlcv | weak | none | <= base 3-8 (removes only) | 2 | related:model_lab |
| `ml_model.gradient-boosted-trees` | ml_model | ohlcv | weak | mixed | gate <= base 3-12; hundreds hourly | 3 | related:model_lab |
| `ml_model.logistic-linear-lagged-returns` | ml_model | ohlcv | weak | mixed | 20-60; 4-12 with cost threshold | 3 | related:model_lab |
| `ml_model.random-forest` | ml_model | ohlcv | weak | mixed | gate <= base; 20-60 standalone | 3 | absent |
| `ml_model.stacking-ensembles` | ml_model | ohlcv, on_chain | weak | mixed | gate <= base 3-12 | 3 | absent |
| `ml_model.bayesian-models` | ml_model | ohlcv, on_chain | weak | none | gate <= base 3-12 | 4 | absent |
| `ml_model.genetic-programming` | ml_model | ohlcv | weak | none | rule-dependent | 4 | absent |
| `ml_model.knn-analog-patterns` | ml_model | ohlcv | anecdotal | negative | tens-hundreds (1h) | 4 | implemented:STRAT-003 |
| `ml_model.lstm-gru` | ml_model | ohlcv | weak | negative | hundreds intraday; gate <= base | 4 | related:model_lab |
| `ml_model.reinforcement-learning` | ml_model | ohlcv | weak | mixed | hundreds+ | 4 | absent |
| `ml_model.svm` | ml_model | ohlcv | weak | mixed | 20-60 standalone | 4 | absent |
| `ml_model.tcn` | ml_model | ohlcv | weak | negative | hundreds hourly; gate <= base | 4 | absent |
| `ml_model.transformers` | ml_model | ohlcv | weak | negative | hundreds hourly; gate <= base | 4 | absent |
| `ml_model.ts-foundation-models` | ml_model | ohlcv | weak | negative | hundreds hourly; gate <= base | 4 | absent |
| `llm.context-veto-gate` | llm | ohlcv, news | anecdotal | none | <= base 3-8 (removes only) | 3 | related:llm_gate |
| `llm.news-headline-sentiment` | llm | news | moderate | none | 6-20 smoothed; 20-100 raw | 3 | related:llm_gate |
| `llm.sentiment-classifiers` | llm | news, social | weak | none | 6-20 smoothed | 3 | absent |
| `llm.autonomous-trading-agent` | llm | ohlcv, news, on_chain | moderate | negative | 20-100+ | 4 | related:llm_gate |
| `llm.hypothesis-generation` | llm | ohlcv | weak | none | n/a | 4 | absent |
| `risk.atr-trailing-stop` | risk | ohlcv | weak | positive | 2-8 exits (as sole exit) | 2 | implemented:OVL-ATR |
| `risk.position-sizing-small-account` | risk | ohlcv | anecdotal | none | 0 | 2 | related:position_sizing |
| `risk.ratchet-stop` | risk | ohlcv | moderate | positive | = base (3-8) | 2 | implemented:OVL-RATCHET |
| `risk.stop-loss` | risk | ohlcv | moderate | positive | +0-3 | 2 | related:OVL-ATR |
| `risk.cooldown-time-stop` | risk | ohlcv | anecdotal | none | 0 (cooldown); +1-3 (time stop) | 3 | implemented:OVL-COOLDOWN |
| `risk.kelly-sizing` | risk | ohlcv | moderate | none | 0 if sized at entry | 3 | related:position_sizing |
| `risk.profit-lock-targets` | risk | ohlcv | weak | none | +1-4 | 3 | implemented:OVL-PLOCK |
| `risk.dca-averaging-down` | risk | ohlcv | weak | none | many adds | 4 | related:pt_trader DCA ladder |
| `risk.drawdown-control-cppi` | risk | ohlcv | weak | none | 4-20 adjustments | 4 | absent |
| `portfolio.dca-periodic` | portfolio | ohlcv | strong | none | 12-52 buys, no sells | 2 | absent |
| `portfolio.equal-weight-1n` | portfolio | ohlcv | moderate | positive | 12 partial (monthly); fewer banded | 2 | related:portfolio_optimizer |
| `portfolio.mean-variance-optimisation` | portfolio | ohlcv | moderate | mixed | 12-52 partial | 3 | related:portfolio_optimizer |
| `portfolio.rebalancing-premium` | portfolio | ohlcv | weak | mixed | a few (banded) to hundreds | 3 | absent |
| `portfolio.risk-parity-inverse-vol` | portfolio | ohlcv | weak | mixed | 12 partial (monthly) | 3 | related:portfolio_optimizer |
| `data_source.coinbase-public-market-data` | data_source | ohlcv, trades, order_book | strong | none | n/a | 1 | related:market_data |
| `data_source.binance-vision-bulk` | data_source | ohlcv, trades, order_book, funding, open_interest, liquidations | strong | none | n/a | 2 | related:market_data |
| `data_source.kraken-ohlcvt` | data_source | ohlcv | strong | none | n/a | 2 | related:market_data |
| `data_source.alternative-me-fear-greed` | data_source | social | strong | mixed | n/a | 3 | absent |
| `data_source.coin-metrics-community` | data_source | on_chain, ohlcv | moderate | positive | n/a | 3 | absent |
| `data_source.deribit-dvol` | data_source | funding | moderate | none | n/a | 3 | absent |
| `data_source.hyperliquid-info-api` | data_source | funding, open_interest, ohlcv | moderate | none | n/a | 3 | absent |
| `data_source.kucoin-public-api` | data_source | ohlcv, trades, order_book | moderate | none | n/a | 3 | related:market_data |
| `data_source.btc-chain-explorers` | data_source | on_chain | weak | positive | n/a | 4 | absent |
| `data_source.bybit-okx-archives` | data_source | ohlcv, trades, funding | weak | none | n/a | 4 | absent |
| `data_source.coingecko-demo` | data_source | ohlcv | strong | none | n/a | 4 | absent |
| `data_source.coinmarketcap-basic` | data_source | ohlcv | strong | none | n/a | 4 | absent |
| `data_source.dune-etherscan` | data_source | on_chain | moderate | mixed | n/a | 4 | absent |
| `data_source.gdelt` | data_source | news | strong | mixed | n/a | 4 | absent |
| `data_source.google-trends` | data_source | social | moderate | negative | n/a | 4 | absent |
| `data_source.news-apis` | data_source | news | weak | mixed | n/a | 4 | related:llm_gate |
| `data_source.wikipedia-pageviews` | data_source | social | moderate | negative | n/a | 4 | absent |
| `data_source.cryptocompare-coindesk` | data_source | ohlcv, social, news | moderate | none | n/a | 5 | absent |
| `data_source.onchain-analytics-vendors` | data_source | on_chain, social | moderate | negative | n/a | 5 | absent |
| `data_source.paid-tick-vendors` | data_source | trades, order_book, liquidations, open_interest, funding | moderate | none | n/a | 5 | absent |
| `data_source.social-platform-apis` | data_source | social | moderate | mixed | n/a | 5 | absent |

---

## 2. Trend (MA crossovers, DEMA/TEMA, MACD, Supertrend, PSAR/Ichimoku, ADX, multi-timeframe)

- **Moving-average rules are one family.** Levine and Pedersen (2016, via A) show that crossovers and time-series momentum are equivalent representations. So STRAT-000, STRAT-001 and STRAT-005 are one family, and testing many smoothers is mostly multiple testing.
- **The crypto support is for slow daily price-to-average signals:**
  - Detzel et al. (2021): predictability in and out of sample.
  - Wei et al. (2024): the short-term log MA ratio is one of only two survivors of SPA and "lucky factor" correction.
  - Hudson and Urquhart (2021) found no out-of-sample Bitcoin predictability.
  - **Hence `trend.price-above-ma` at priority 1:** daily, 50-200-day averages, about 3-10 round trips a year.
- **Headline crossover returns are gross and from short samples:**
  - Rozario et al. 2020 (arXiv): 255% walk-forward with costs assumed negligible.
  - Rohrbach et al. 2017: Sharpe 1.62, gross, over two years.
- **MACD, Supertrend (STRAT-002), PSAR/Ichimoku and the ADX filter have almost no crypto evidence.**
  - A 42-market futures test found that ADX "does not add value" to a Donchian model (Oxford Capital Strategies).
  - The repository's hourly STRAT-000 and STRAT-001 and 4h STRAT-002 lost money.
  - All are priority 4. Do not retest hourly crossovers.
- **Multi-timeframe filtering** helped a gross hourly BTC MACD in one practitioner test (Quantpedia 2025). It cannot rescue an hourly base rule at 0.55% a side (priority 3, as a filter only).

## 3. Breakout (Donchian/Turtle, Zarattini ensemble, 52-week high, opening range)

- **Daily Donchian breakouts carry the best crypto evidence:**
  - Gerritsen et al. 2020 (Bitcoin trading-range breakout);
  - Zarattini, Pagani and Barbon 2025: a long-only, multi-lookback ensemble with a midline trailing stop that never moves down. Net of 10 bp, the 10-coin book had a Sharpe ratio of 1.50 and a maximum drawdown of 12% (via A).
  - STRAT-004 is the repository's best result.
- **What the ensemble adds to STRAT-004:**
  - the ratchet exit (OVL-RATCHET exists);
  - several lookbacks.
  - Members below 20 days should be dropped at these fees: Zarattini's 5- and 10-day members make about 15-29 trades a year on Bitcoin.
- **The 52-week-high effect is an equity result** (George and Hwang 2004). In crypto it appears only indirectly (MAX momentum; the 250-360-day Donchian members). Test it as the long member of the ensemble (priority 3).
- **Opening-range and intraday breakouts** need 100-365 round trips a year, so the fees destroy them (priority 4).

## 4. Momentum (time-series, cross-sectional, intraday, dual)

- **Time-series momentum (STRAT-005) has the strongest general evidence:**
  - Moskowitz et al. 2012;
  - Hurst et al. 2017, net of estimated costs.
  - Its crypto support is real but short-sample and mostly in-sample (Liu and Tsyvinski 2021).
  - The asset-by-asset critiques still apply (Huang et al. 2020; Kim, Tse and Wald 2016).
  - Priority 1, for evaluation rather than building.
- **Cross-sectional momentum needs shorting.** Among large coins it earns mostly from shorts, and fades over time (Fieberg, Liedtke and Zaremba 2024, via A). Priority 5 as a factor; the long-only remnant is `relative_strength.top-k-rotation`.
- **Intraday time-series momentum** (Shen, Urquhart and Wang 2022) trades daily, so the fees destroy it.
- **Dual momentum:**
  - Weekly: hold the stronger of two assets while its return is positive, otherwise cash.
  - It is long-only by design, and a natural BTC/ETH/cash extension of STRAT-005 (priority 2).
  - Its only crypto test is a gross, in-sample Quantpedia BTC/gold backtest: 79.91% a year, −43.94% drawdown.

## 5. Relative strength (rotation, coin/BTC ratio, BTC/ETH leadership)

- **Long-only top-k rotation among the 9 coins:**
  - The evidence is long-short and dominated by small coins.
  - One swap a week at k = 3 costs about 19% a year (A §8).
  - It needs a portfolio-level strategy interface the app lacks.
  - Priority 3.
- **Coin-versus-BTC ratio trends:** no direct study was found (priority 3).
- **BTC/ETH leadership** (`relative_strength.btc-lead-lag`, merged with the cross-coin lead-lag candidate):
  - BTC-ETH causality is mostly bi-directional and "can barely" be exploited (Sifat et al. 2019).
  - The large cross-coin profits are long-short (Guo et al. 2024: 2.16% a day in the working-paper version, which C calls implausible).
  - It already exists as a `signal_fusion` input. Keep it as a slow gate, not a strategy.

## 6. Mean reversion (RSI, RSI(2)/Connors, stochastic/Williams %R, Bollinger, reversal, candlestick and chart patterns)

- **For large coins at daily and weekly horizons, the evidence shows continuation:**
  - Zaremba et al. 2021 and Fičura 2023, via A.
  - A gross community tally across 8 coins found RSI above 70 and closes above the upper band the most bullish states (Coinpaprika 2026, vendor blog, community evidence only).
- **RSI(2)/Connors:**
  - As published: above the 200-day SMA, RSI(2) ≤ 5, exit above the 5-day SMA, no stop.
  - It is tested on equities from 1995 to 2007, with no out-of-sample test and no frictions (CXO).
  - Its per-trade edge is below 1.10%.
- **Bollinger reversion:**
  - It fails after costs in equities (Lento et al. 2007, via A).
  - The positive Bitcoin study is on margined futures (Day et al. 2023, abstract only).
- **Stochastic and Williams %R:** no test was found.
- **Short-term reversal:**
  - At 15 minutes it is real but about 1.3 bp gross (Kitron and Wengrowicz 2026).
  - Daily counter-overreaction trading was not profitable (Caporale and Plastun 2018).
- **Candlestick patterns** are "of little use" across 68 patterns and 23 coins (Ho et al. 2022). The repository's `candlestick_patterns` (FDS-SIG-003) should stay a falsification test.
- **Chart patterns:** the evidence is distributional only, in equities (Lo, Mamaysky and Wang 2000).
- **All seven are priority 4.**

## 7. Statistical arbitrage (pairs/cointegration; long-only feasibility; cash-and-carry)

- **Pairs trading in crypto works only intraday and long-short:**
  - Fil and Kristoufek 2020: −0.07% a month with the daily distance method, against 11.61% a month at 5 minutes (abstract extract).
  - Fischer et al. 2019: three months out of sample, long-short.
- **Long-only spot feasibility [R].** The only spot form rotates an existing holding into the cheaper leg, or buys it from cash.
  - That keeps at most half the spread return and adds full directional exposure.
  - It pays 1.10% per switch, on daily spreads that do not reliably revert.
  - **Verdict:** pairs are priority 5. The leg-rotation remnant is assessed and not to be built (priority 4).
- **Funding cash-and-carry** (long spot, short perpetual):
  - It is the best-documented crypto "high return": Sharpe 6.45 over Aug 2020 to May 2025 (Borri et al. 2025).
  - It has decayed sharply: 4.06 from 2024, negative in 2025.
  - It needs a short derivatives leg, which UK retail clients cannot hold (FCA PS20/10).
  - Priority 5.

## 8. Regime (trend gate, volatility state, bubbles, calendar, halving, HMM, alternative-data regimes)

- **The BTC 200-day gate (OVL-REGIME) is the natural long-only control** (priority 1).
  - Its documented benefit is smaller drawdowns, not higher returns:
    - Faber via CXO;
    - Detzel et al., where Bitcoin's drawdowns were −66% to −70% against −89.5% for buy-and-hold, via A.
  - Evaluate it as a veto, and report time in each state.
- **A volatility-state veto:**
  - It has no crypto trading evidence.
  - Option-implied data show two Bitcoin volatility regimes (Almeida et al. 2024), but the paper is descriptive.
  - The veto risks cutting the strongest up-trends. Priority 3.
- **Bubble dependence of technical returns** (Svogun and Bazán-Palomino 2022) is a caution for reading every trend result, not a usable real-time gate.
- **Calendar and hour-of-day effects** do not persist (Baur et al. 2019) and need 12-365 round trips a year.
- **The halving cycle** has n = 4 events.
- **HMM / Markov-switching:**
  - In crypto, regimes exist and improve forecasts or VaR (Koki et al. 2022; Ardia et al. 2019).
  - The only cost-inclusive trading test is on equity indices: a jump model beat an HMM (Shu, Yu and Mulvey 2024).
  - Any regime model must beat OVL-REGIME. Priority 3.
- **Alternative-data regimes:** see §16 for the data.
  - **Leverage/carry veto** (no new entries while funding or basis is extreme; priority 2). High carry predicts crashes (Schmeling, Schrimpf and Todorov 2023, BIS working paper), but no tested veto exists.
  - **Fear & Greed** (priority 3): Granger-predicts BTC and ETH on one year of weekly data (Cavalheiro et al. 2024); a poor out-of-sample predictor (Shelton 2024).
  - **Hashrate and adoption** (priority 3): Wei et al. 2024's hashrate index survives correction, but hashrate exists only for BTC, DOGE, ZEC and DASH.
  - **Search attention, news coverage, on-chain valuation and stablecoin issuance** are priority 4. Social sentiment and exchange-flow/whale data are priority 5.

## 9. Volume (OBV, CMF, MFI, relative volume, divergence, VWAP, volume profile, CTREND)

- **Volume carries information, but no stand-alone volume rule is supported for large coins at retail fees.**
  - Volume Granger-causes Bitcoin returns away from the tails (Balcilar et al. 2017), in-sample.
  - The cross-sectional sign is disputed:
    - Bianchi, Babiak and Dickerson 2022;
    - Garfinkel, Hsiao and Hu 2025: high abnormal volume predicts lower returns only where shorting is impossible.
- **Indicator by indicator:**
  - OBV, MFI, VWAP, volume profile and volume-price divergence have no crypto-specific evidence.
  - The only VWAP backtest is a promotional intraday long-short on QQQ.
- **CTREND** (Fieberg et al. 2025, JFQA) combines price and volume indicators with ML, survives costs and persists in large coins. But it is cross-sectional and long-short (priority 3).
- **Repository evidence:**
  - Volume added no forecast value over price (SIG-004 development run: Δ log loss +0.00033, p = 0.17).
  - A 1h relative-volume filter raised the hit rate but trades still lost after fees.
- **Recommendation:** at most one pre-registered relative-volume veto on STRAT-004 entries (priority 3).
- **Data-quality caveat:** wash trading averaged over 70% of reported volume on unregulated exchanges (Cong et al. 2023). Use regulated-venue volume (Coinbase, Kraken) and never mix venues.
- **Data needed:**
  - True VWAP and volume profiles need trades.
  - OBV, CMF, MFI and relative volume work from OHLCV.

## 10. Liquidity (Amihud, spread/depth, volume-conditioned reversal, execution timing)

- **Liquidity is a cost and risk measure here, not a return source.**
  - Illiquidity premia and liquidity-provision reversal sit in small coins, long-short, at 12-hour to weekly rebalancing.
  - The time-series relation for leading coins is insignificant or unstable.
- **Coinbase BTC and ETH spreads were 1-2 bp** (Brauneis et al. 2021, via A). Bitcoin is "investible at retail trade sizes" (Dyhrberg, Foley and Svec 2018).
- **ZEC, DASH and HYPE were never measured.** So `liquidity.spread-depth-filter` is priority 2 infrastructure:
  - record Coinbase book snapshots from now on, since the endpoint gives no history;
  - check the 0.05% slippage assumption;
  - skip trades when the spread is wide.
- **Execution timing** by intraday liquidity periodicity (Hansen, Kim and Kimbrough 2021) can save part of the slippage, not the fee (priority 3).

## 11. Microstructure (trade-flow imbalance, order-book imbalance, VPIN, large prints, taker-flow reversal, funding, open interest, liquidations, cross-exchange premia)

- **Strong evidence, wrong horizon.**
  - Order-flow imbalance explains short-interval price changes (Cont, Kukanov and Stoikov 2014).
  - In crypto, trade-flow imbalance explains contemporaneous moves better than book imbalance (Silantyev 2019).
  - Signed volume explains about 80% of Bitcoin returns, contemporaneously (Makarov and Schoar 2020).
  - **The taker-flow 15-minute reversal** (Kitron and Wengrowicz 2026) shows the problem: it appears in about 90% of Binance pairs, but its gross edge of about 1.3 bp is roughly 85 times smaller than 110 bp.
- **Data needed:**
  - **Trades:** trade-flow imbalance, VPIN, large prints.
  - **Order book (L2 updates):** order-book imbalance, which has no free history.
  - Coinbase's trades endpoint reports the **maker** side, and backfilling is slow.
  - Binance klines carry taker-buy volume, but the bulk files are non-production only.
- **Funding, open interest, liquidations and cross-exchange premia:**
  - **Funding** as a direct return predictor is unproven: one four-month practitioner regression found R² ≈ 0.001.
  - **Open interest and liquidation** studies are about risk and market quality, not prediction.
  - **Cross-exchange premia** widen in rallies, moving with returns rather than leading them (Makarov and Schoar 2020).
  - All priority 4, as information only, since UK retail clients cannot hold crypto derivatives.
- **Verdict:** nothing here is built for return. The order book is used only to measure costs.

## 12. Volatility (realised, clustering, ATR, EWMA, GARCH/HAR, breakouts, squeeze, targeting, DVOL)

- **Volatility is forecastable; direction from volatility is not shown.**
  - Crypto volatility clusters, has long memory and needs robust filters (Catania and Grassi 2022).
  - HAR on realised variance beats GARCH for Bitcoin (Bergsli et al. 2022, via C).
  - GARCH model rankings are unstable (Katsiampa 2017, against Darné and Charles 2019).
  - Range-based estimators (Yang and Zhang 2000) use daily OHLC efficiently.
- **As entry signals, squeezes and range breakouts are negative or anecdotal.**
  - Bollinger-squeeze profits vanished in equities after 2001, and were negative net of a 1% friction (Fang, Jacobsen and Qin 2014, via CXO).
  - Larry Williams-style range breakouts trade daily (priority 4).
- **As sizing:**
  - Volatility management reduced crypto momentum crashes (Grobys et al. 2025, abstract).
  - It is part of Zarattini et al.'s design, but contested in equities (Cederburg et al. 2020, via A).
  - The repository's own development test found the volatility shrink no better than random sizing at reducing drawdown (Q3, p = 0.69). So `volatility.vol-targeting-sizing` is priority 2 to re-test on the slow strategies, sized once at entry with a wide band, not assumed.
- **EWMA** (RiskMetrics λ = 0.94) and range-based estimators are the priority-2 inputs. GARCH and HAR are priority 3, used only if the simple estimator shows value.
- **DVOL** (Deribit, BTC and ETH only) has a free public endpoint but no verified evidence of return predictability.

## 13. Statistical and machine-learning models

- **Forecast skill on large coins is small:**
  - direction accuracy is about 51-56% (via C), or 55-65% in Akyildirim et al. (2021);
  - one team's live correlation in the G-Research competition was about a quarter of its cross-validation score.
- **Profits appear only where this account cannot go:**
  - long-short (Fischer et al. 2019; Jaquart et al. 2022; Guo et al. 2024);
  - at 10-25 bp fees (Bysik and Ślepaczuk 2026);
  - or over one short window (Sebastião and Godinho 2021).
- **Daily beats hourly:** a random forest beats the random walk on daily BTC; no model does hourly (Gradojevic et al. 2023).
- **Complexity does not help:**
  - naive forecasts beat ML and deep models (Puoti et al.);
  - linear models are competitive in the cross-section (Cakici et al. 2024);
  - iTransformer did no better than XGBoost (Bysik and Ślepaczuk);
  - zero-shot foundation models show near-zero crypto IC (Kronos paper; Fu et al. 2024).
- **The repository agrees.** STRAT-003 and the model-lab contestants showed no edge over random entries.
- **What fits:**
  - **Priority 2:**
    - `ml_model.meta-labelling`: triple-barrier labels on STRAT-004/005 entries, as a take-or-skip gate (López de Prado 2018; Joubert 2022, unverified full text);
    - `ml_model.calibration-ev-gate`: Platt or isotonic calibration, then trade only when p × gain − (1 − p) × loss > 1.10%.
    - Both only remove trades.
  - **Priority 3:** regularised logistic regression with cross-coin lags, gradient boosting, random forests and stacking. They are already in `model_lab`, and remain worth running as pooled daily gates.
  - **Priority 4:** SVM, kNN/analog patterns (STRAT-003), Bayesian models, LSTM/GRU, TCN, transformers, time-series foundation models, reinforcement learning and genetic programming.
    - The crypto deep-RL literature's profits are largely backtest overfitting (Gort et al. 2022).
    - GP rules lose their excess returns after realistic costs (Neely and Weller 2001).
- **Overfitting rules that bind every ML candidate:**
  - Bailey et al. 2014/2017 and the Deflated Sharpe Ratio (A §11);
  - Arnott, Harvey and Markowitz 2019;
  - purged cross-validation (López de Prado 2018);
  - the C-evidence §4 harness rules.
- **The binding limit is the sample:** about 120-310 labelled trades over 4.3 years across 9 coins [R]. Every gate must beat a random skip at the same rate (`entry_gate`).

## 14. LLM-assisted signals (news and sentiment, context, veto/confirmation, hypothesis generation)

**Does it predict returns?**
- **Equities: narrowly, yes.**
  - Lopez-Lira and Tang (v6) [A]: on headlines dated after the model's cut-off, GPT-4 scores predict next-day drift, "especially for small stocks and negative news". The returns fall as LLM adoption rises.
  - Kirtac and Germano (2024) [S]: an OPT long-short strategy had a Sharpe ratio of 3.05 after 10 bp costs (search summary; full text not read).
  - These are next-day, long-short and short-side-heavy results. They do not transfer to a long-only book of large coins paying 1.10% a round trip.
- **Crypto: no study was confirmed that tests LLM news or social sentiment against out-of-sample returns.** The crypto evidence is about agents:
  - **CryptoTrade (EMNLP 2024) [FT].** It trailed buy-and-hold in the 2023 bull windows for BTC (28.47% vs 39.66%) and SOL (115.18% vs 176.72%), and lost less in the bear window.
    - Its windows postdate GPT-3.5's cut-off but plausibly fall inside GPT-4o's training data.
    - The paper states no fee rate.
  - **Alpha Arena season 1** (live, real money, 18 Oct to 3 Nov 2025; ForkLog).
    - Results: Qwen3 Max +22.3%, DeepSeek +4.9%, and four models lost 42-59%.
    - It was traded on leveraged perpetuals, with n = 6 over 17 days. That is no evidence of skill either way.
    - End balances differ between reports, and the official leaderboard was not read.
  - **Sentiment classifiers** (FinBERT, CryptoBERT) measure sentiment. Whether crypto sentiment predicts returns is the data question in §8 and §16, where the evidence is weak.

**Look-ahead and memorisation critiques:**
- **Glasserman and Lin (2023) [A]:** in-sample, a model's knowledge of the named company distorts its reading of news. Anonymised headlines did better.
- **Sarkar and Vafa (2024):** direct tests find look-ahead bias in pretrained models. They recommend models whose pretraining predates the test period.
- **Lopez-Lira, Tang and Zhu (2025) [S]:**
  - before its cut-off, GPT-4o recalls exact index levels and macro figures;
  - instructions to ignore the future do not stop it;
  - recall vanishes after the cut-off.
- **Profit Mirage (Li et al. 2025) [FT §2]:** five published LLM agents on GPT-4o lost 51-62% of their Sharpe ratio and 50-72% of their return from a pre-cut-off window (Q2-Q3 2021) to a post-cut-off window (Q3-Q4 2024). Market returns were similar in both windows.
- **FINSABER (2025):** LLM strategies are over-conservative in bull markets and over-aggressive in bear markets.
- **Mitigations:**
  - chronologically consistent models (ChronoBERT/ChronoGPT; He et al. 2025);
  - anonymised inputs.

**What a clean test needs [R]:**
1. **Forward-only windows** that start after the pinned model's published cut-off. A model upgrade starts a new record.
2. **Point-in-time inputs:** only text timestamped before the decision bar closes. Anonymise coin names where possible.
3. **A random-slot baseline** at the same veto or entry rate, on the same bars. `llm_gate` already does this.
4. **Every prompt and answer logged.**
5. **The LLM as a veto on a slow rule** (`llm.context-veto-gate`, priority 3), never as the trader. That caps fees at the base rule's 3-8 round trips per coin a year.
6. **Patience:** about 30-70 decisions a year across nine coins. Report "no skill above base rate" until the sample supports more.

**Candidates:**
- **Priority 3:** news-headline sentiment, sentiment classifiers and the context veto gate.
- **Priority 4:** autonomous trading agents and hypothesis/alpha generation.
  - Hypothesis generation is useful only for proposing rules, which then enter the trial log and count against the multiple-testing budget (A §11).

## 15. Risk (stops, trailing and ratchet exits, profit locks, cooldowns, sizing, CPPI, averaging down)

- **Stops help only when prices trend or switch regime.** Under a random walk they can only lower expected return (Kaminski and Lo 2014).
  - **Equities:** the evidence is large but gross and long-short. Han, Zhou and Zhu's 15% stop on momentum moved the worst month from −49.8% to −17.4% (via CXO).
  - **Crypto:** one supporting abstract (Sadaqat and Butt 2023), with no cost level stated.
  - Wide stops on the daily strategies are priority 2.
- **The ratchet exit (OVL-RATCHET)** is the exit of the best-evidenced long-only design (Zarattini et al.), although its own contribution is not isolated there (priority 2).
- **The ATR trail (OVL-ATR):**
  - Its only crypto ablation is a long-short perpetuals preprint at 4 bp (Bui and Nguyen 2026), whose Sharpe arithmetic does not reconcile.
  - Evaluate it at k = 2-3.5 on daily bars, against no stop and random stops (priority 2).
- **Profit-lock targets (OVL-PLOCK)** reduced trend-following returns in a 42-market practitioner test (Oxford Strat; priority 3).
- **Cooldowns** have no evidence. They can only remove re-entries (priority 3).
- **Kelly sizing** needs a measured edge, and the app has none yet (MacLean, Thorp and Ziemba 2011; priority 3).
- **Small accounts** (`risk.position-sizing-small-account`, priority 2):
  - Coinbase sets a per-product minimum (`min_market_funds` / `quote_min_size`); no single "$1" figure was confirmed.
  - At £50, a 1% entry is below the minimum, so entries become about 2% or more of equity. A 10% per-coin cap then allows about 5 minimum orders, and DCA ladders cannot work.
  - At £10,000, minimums do not bind.
- **CPPI** has no crypto study (priority 4).
- **The legacy averaging-down ladder** has no empirical support (Hayley 2014; priority 4).

## 16. Portfolio (1/N, mean-variance, risk parity, rebalancing premium, DCA)

- **1/N is as good as optimised weights out of sample in crypto:**
  - Platanakis, Sutcliffe and Urquhart 2018;
  - Liu 2019: no model "can consistently beat the naive 1/N portfolio in Sharpe ratio".
  - So equal-weight buy-and-hold of the same coins is the benchmark for any multi-coin strategy (priority 2).
- **Black-Litterman with constraints** beat naive weights out of sample after costs (Platanakis and Urquhart 2019), on a short, pre-2019 sample (priority 3).
- **Risk parity and inverse volatility** tilt towards BTC (priority 3).
- **The rebalancing premium** has only gross vendor evidence (Quantpedia, 27 coins, 2018-2021), and it is contrarian against large-coin momentum (priority 3).
- **Periodic DCA** is a baseline, never a source of return (priority 2 as a baseline). Lump sum beats it about two-thirds of the time in equities (via A).
- **Only banded, monthly-or-slower rebalancing** is compatible with 0.55% a side [R].

## 17. Additional data sources

### 17.1 Findings

- **Coinbase public market data is sufficient for every priority-1 and priority-2 candidate:**
  - candles at 1m, 5m, 15m, 1h, 6h and 1d, up to 300 per request (350 on Advanced Trade, which adds 2h and 4h);
  - trades, with `side` the maker side;
  - the current book snapshot only, with no history.
  - Its Market Data Terms of Use returned HTTP 403 and were not read.
- **Binance Vision** is the only free bulk archive of trades, funding (from 2020-01) and open interest (from 2020-09-01). Its Terms (version 1.0, last updated 26 Aug 2026; read on GitHub 2026-11-11) license the datasets under CC BY-NC-SA 4.0:
  - Permitted: "algorithmic historical backtesting for purely personal non-production research".
  - Forbidden: "live proprietary trading execution, automated commercial order generation, or signal distribution to third parties", hosting and resale.
  - **Usable for the owner's research backtests only.** Never as a live feed, and never bundled in the repo.
  - Binance paused new UK onboarding in October 2023.
- **Kraken OHLCVT downloads** give full per-pair history, including 4h and trade counts. They are a licence-clean second source.
- **Derivatives data** (funding, open interest, liquidations, DVOL) is information only for a UK retail spot account (FCA PS20/10). Hyperliquid's public API is the only free funding source for HYPE; its terms were not read.
- **Sentiment and news:**
  - **Fear & Greed:** from 2018-02-01, with attribution required.
  - **GDELT:** free for any use with citation, and the cleanest news licence.
  - **X and Reddit:** paid or non-commercial only.
  - **NewsAPI:** forbids production use on its free plan.
  - **CryptoCompare/CoinDesk:** retired its free tier on 2026-05-21, per a third-party page.
- **On-chain data:**
  - Coin Metrics Community is CC BY-NC 4.0, so non-commercial only.
  - Exchange-flow and whale data need paid vendors.
  - Hashrate exists only for the proof-of-work coins: BTC, DOGE, ZEC and DASH.

### 17.2 Data-source assessment table

| Source | Data | Free? | Terms (key points, URL) | History | Rate limits | Legal / UK note | Use in PTAI |
|---|---|---|---|---|---|---|---|
| Coinbase Exchange / Advanced Trade public | OHLCV (1m, 5m, 15m, 1h, 6h, 1d; Advanced Trade adds 2h, 4h), trades, order book, WebSocket | Yes, no key | Market Data Terms of Use (updated 2023-02-06): rights not granted are reserved; redistribution via a partner programme. Full text returned 403, so not read ([terms](https://www.coinbase.com/legal/market_data), [candles doc](https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles)) | From each product's listing; 300 candles per request | 10 req/s per IP, bursts to 15 ([doc](https://docs.cdp.coinbase.com/exchange/rest-api/rate-limits)) | Primary venue; own-trading use is the intended use | **Primary:** all backtests and live signals |
| Binance Vision (data.binance.vision) | Spot klines (1s to 1mo), aggTrades, trades; USD-M futures klines, trades, bookTicker, bookDepth, metrics (open interest, long/short), fundingRate, mark/index/premium; COIN-M liquidationSnapshot | Yes, no key | **CC BY-NC-SA 4.0**. Permitted: "algorithmic historical backtesting for purely personal non-production research". Forbidden: "live proprietary trading execution, automated commercial order generation", hosting and resale ([T&C v1.0, 26 Aug 2026](https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md)) | Spot BTCUSDT 1d from 2017-08; fundingRate from 2020-01; metrics from 2020-09-01 | Bulk files | Binance paused new UK onboarding from 16 Oct 2023 ([The Block](https://www.theblock.co/news/markets/2023-10-16-binance-to-temporarily-stop-accepting-new-uk-users-after-fca-restriction-257721)); downloads are not account-bound | Owner's personal research backtests only (trades, funding, open interest). Never live, never in the repo |
| Kraken OHLCVT downloads + REST | OHLCVT at 1m, 5m, 15m, 1h, 4h, 12h and 1d, with trade counts | Yes | No specific licence; general Kraken Terms of Service ([page](https://support.kraken.com/hc/en-us/articles/360047124832-Downloadable-historical-OHLCVT-Open-High-Low-Close-Volume-Trades-data)) | From each pair's first trade; refreshed quarterly | REST: only the 720 most recent candles | Kraken serves UK clients; connector exists | Licence-clean cross-check of Coinbase; long USD/GBP history |
| KuCoin public API | Klines (1,500 per call), trades, order book | Yes | Not read ([doc](https://www.kucoin.com/docs-new/rest/spot-trading/market-data/get-klines)) | Paginated by time | Public pool per IP; quota not confirmed | Connector exists | Fallback venue data |
| Bybit / OKX archives | Trade archives, klines, premium index | Partly | Not read | Not confirmed | Not confirmed | Not app venues | Redundant with Binance Vision |
| Deribit public API | DVOL, historical volatility, funding | Yes, no key | Not read ([doc](https://docs.deribit.com/api-reference/market-data/public-get_volatility_index_data)) | DVOL from about 2021-04 ([S]) | Not read | Data only; derivatives banned for UK retail (FCA PS20/10) | BTC/ETH implied-volatility regime input |
| Hyperliquid info API | Funding history, predicted funding, current open interest and premium | Yes, no key | Not read ([doc](https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals)) | Venue since 2023; HYPE since late 2024 | Not read | Data only | Only free funding source for HYPE |
| CoinGecko Demo | Aggregated prices, market caps, volumes | Partly | Attribution required; commercial licence only on paid plans ([pricing](https://www.coingecko.com/en/api/pricing)) | 1 year daily/hourly on Demo | 10k credits a month; 100/min | — | Market cap and dominance only |
| CoinMarketCap Basic | Quotes, listings, global metrics | Yes (shallow) | No redistribution ([pricing](https://coinmarketcap.com/api/pricing/)) | 1 month intraday, 1 year daily | 15k credits a month; 50/min | — | Little value |
| CryptoCompare / CoinDesk Data | Aggregated OHLCV, social, news | **No** (free tier retired 2026-05-21, per a [third-party page](https://currencyinfo.docs.adamant.im/reference/sources/cryptocompare)) | Paid, by sales contact | — | 401 without a subscription | — | Do not use |
| alternative.me Fear & Greed | Daily 0-100 index | Yes, no key | Attribution beside the data; commercial use allowed ([page](https://alternative.me/crypto/fear-and-greed-index/)) | From 2018-02-01 | Not stated | Fine with attribution in the UI | Optional regime gate |
| GDELT | Global news events, tone, themes (GKG), DOC API | Yes | Unlimited use including commercial; cite and link ([about](https://www.gdeltproject.org/about.html)) | 1.0 daily from 2013-04; 2.0 every 15 min | Bulk files | Cleanest free news licence | News-coverage research only |
| Google Trends | Relative search interest | Partly (UI; the API is a closed alpha) | Google terms not read; pytrends (Apache-2.0) archived 2025-04-17 ([repo](https://github.com/GeneralMills/pytrends)) | Not verified | Unofficial scraping hits HTTP 429 | Scraping may breach terms | Avoid |
| Wikipedia Pageviews | Daily article views | Yes | CC0 data; User-Agent required ([policy](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html)) | Start date not confirmed | Under revision in 2026 | Clean | Low-value attention proxy |
| X API | Posts | **No** | Pay-per-use, $0.005 per post read ([pricing](https://docs.x.com/x-api/getting-started/pricing)) | Paid | — | Authenticated and paid | Not usable |
| Reddit Data API | Posts, comments | Free for non-commercial use only | 100 QPM per OAuth client from 2023-07-01; commercial use paid ([S], via a mirrored announcement) | No archive | 100 QPM | Terms page unreadable | Not usable |
| NewsAPI | News search | Developer plan only | 100 req/day, 24h delay, 1 month back, not for production ([pricing](https://newsapi.org/pricing)) | 1 month | 100/day | Production use forbidden on the free plan | Not usable |
| CryptoPanic | Coin-tagged headlines | Partly (key needed) | Free tier about 5 req/s; one tier needs "Powered by CryptoPanic" ([S], [about](https://cryptopanic.com/developers/api/about)) | Not confirmed | About 5 req/s | Key needed | Live LLM context at most |
| blockchain.com / Blockchair / mempool.space | BTC chain statistics, blocks, mempool | Partly | Blockchair 30 req/min free per a docs copy ([S]); mempool is AGPL-3.0 and self-hostable ([S]) | BTC from genesis | Varies | Terms not read | Redundant with Coin Metrics |
| Coin Metrics Community | Daily network metrics, reference rates | Yes, no key | CC BY-NC 4.0, attribution ([docs](https://docs.coinmetrics.io/access-our-data/api), [S]) | Limited depth versus paid | 10 req per 6 s per IP | Non-commercial only | Hashrate and address research |
| Glassnode / CryptoQuant / Santiment | MVRV, SOPR, exchange flows, social volume | Partly | CryptoQuant API from the Professional plan; Glassnode data credits; Santiment free tier excludes the last 30 days ([CQ](https://cryptoquant.com/pricing), [San](https://academy.santiment.net/sanapi/historical-and-realtime-data-restrictions/)) | CQ Basic 3 years daily; Santiment about 2 years minus 30 days | By plan | Accounts and keys needed | Outside these research rules |
| Dune / Etherscan | EVM transfers, mints, SQL | Partly | Etherscan free tier 3/s and 100k/day; Dune paid for execution and API ([Etherscan](https://docs.etherscan.io/resources/rate-limits), [Dune](https://dune.com/pricing)) | Chain genesis | As stated | Keys needed | Stablecoin-mint events, if pursued |
| Tardis.dev / Kaiko / Coinglass | Tick trades, books, liquidations, open interest, funding | Tardis: first day of each month free; others paid | Tardis by plan; Coinglass from $273/yr; Kaiko by quote ([Tardis](https://docs.tardis.dev/faq/data), [Coinglass](https://www.coinglass.com/pricing)) | Tardis Coinbase from 2019-03-30 | By plan | Paid | Sanity checks only |

**UK regulatory note.** FCA PS20/10 bans the sale to retail clients of derivatives and ETNs that reference cryptoassets, from 6 January 2021 ([FCA](https://www.fca.org.uk/publications/policy-statements/ps20-10-prohibiting-sale-retail-clients-investment-products-reference-cryptoassets), [S]). It covers holding positions, not reading public derivatives data. Not legal advice.

---

## 18. Licensing of reference implementations

**PowerTraderAI is Apache-2.0.**
- MIT, BSD and NCSA code may be included with its notices kept.
- GPL-3.0 and AGPL-3.0 code cannot be copied in without the combined work becoming (A)GPL, so use those projects for ideas only.
- LGPL-3.0 is acceptable only as an unmodified, separately installed dependency.
- The Commons Clause removes the right to sell, and is not an OSI open-source licence.
- CC BY-NC(-SA) forbids commercial use.

**How licences were read (2026-11-11):**
- GitHub's public repository pages and unauthenticated repository API;
- PyPI JSON;
- Hugging Face model cards and API.

This is not legal advice.

| Library / asset | Purpose | Licence (as read) | URL | Reuse | Note for Apache-2.0 |
|---|---|---|---|---|---|
| TA-Lib (C library) | Indicators | BSD-3-Clause | https://github.com/TA-Lib/ta-lib | code | Keep notice; needs a compiled binary |
| ta-lib-python | TA-Lib wrapper | BSD-2-Clause | https://github.com/TA-Lib/ta-lib-python | code | Permissive |
| ta (bukosabino) | Pure-pandas indicators | MIT | https://github.com/bukosabino/ta | code | Permissive |
| pandas-ta (upstream) | Indicators | **Unconfirmed.** The GitHub repo returns 404. PyPI 0.4.71b0 (2025-09-14) has no licence field, and its licence page did not load. Mirrors say MIT [S] | https://pypi.org/project/pandas-ta/ | ideas_only | Do not vendor until confirmed |
| pandas-ta-openbb (fork) | Indicators | MIT (PyPI) | https://pypi.org/project/pandas-ta-openbb/ | code | Upstream chain not checked |
| finta | Indicators | LGPL-3.0; archived 2022 | https://github.com/peerchemist/finta | ideas_only | Dependency only; unmaintained |
| tulipy / tulipindicators | Indicators (C) | LGPL-3.0 | https://github.com/cirla/tulipy | ideas_only | Dependency only |
| statsmodels | Regression, ARIMA, Markov switching, cointegration | BSD-3-Clause | https://github.com/statsmodels/statsmodels | code | Permissive |
| arch | GARCH family, HAR, bootstrap, SPA/StepM | NCSA (permissive) | https://github.com/bashtage/arch | code | Keep notice |
| hmmlearn | Gaussian HMM | BSD-3-Clause (limited maintenance) | https://github.com/hmmlearn/hmmlearn | code | Permissive |
| pomegranate | HMMs, mixtures | MIT | https://github.com/jmschrei/pomegranate | code | Permissive |
| scikit-learn | Logistic regression, RF, SVM, HistGB, calibration, stacking | BSD-3-Clause | https://github.com/scikit-learn/scikit-learn | code | Already used by model_lab |
| LightGBM | Gradient boosting | MIT (repo moved to lightgbm-org) | https://github.com/lightgbm-org/LightGBM | code | Permissive |
| XGBoost | Gradient boosting | Apache-2.0 | https://github.com/dmlc/xgboost | code | Same licence |
| CatBoost | Gradient boosting | Apache-2.0 | https://github.com/catboost/catboost | code | Same licence |
| PyTorch | Deep learning | BSD-3-style (bundled parts vary) | https://github.com/pytorch/pytorch | code | Permissive as a dependency |
| darts / NeuralForecast | Forecasting models (TCN, iTransformer, PatchTST) | Apache-2.0 | https://github.com/unit8co/darts | code | Same licence |
| sktime / tsfresh | Time-series ML, features | BSD-3-Clause / MIT | https://github.com/sktime/sktime ; https://github.com/blue-yonder/tsfresh | code | Permissive |
| skfolio | Purged CV, walk-forward, portfolio optimisation | BSD-3-Clause | https://github.com/skfolio/skfolio | code | Permissive |
| qlib | Quant ML platform | MIT | https://github.com/microsoft/qlib | code | Permissive |
| FinRL | Reinforcement-learning trading | MIT | https://github.com/AI4Finance-Foundation/FinRL | code | Permissive |
| mlfinlab (Hudson & Thames) | López de Prado methods | All rights reserved; paid tiers | https://github.com/hudson-and-thames/mlfinlab | no | Reimplement meta-labelling and triple barrier from the book |
| hudson-and-thames/meta-labeling | Paper code | Not shown on the repo page | https://github.com/hudson-and-thames/meta-labeling | ideas_only | Treat as unlicensed |
| ccxt | Exchange connectors, market limits | MIT | https://github.com/ccxt/ccxt | code | Permissive |
| binance-public-data | Download scripts | MIT (scripts); datasets CC BY-NC-SA 4.0 | https://github.com/binance/binance-public-data | code (scripts only) | The data is non-production only |
| freqtrade | Bot / backtester | GPL-3.0 | https://github.com/freqtrade/freqtrade | ideas_only | No code copying |
| backtrader | Backtester | GPL-3.0 | https://github.com/mementum/backtrader | ideas_only | No code copying |
| backtesting.py | Backtester | AGPL-3.0 | https://github.com/kernc/backtesting.py | ideas_only | Includes the network clause |
| vectorbt | Vectorised backtester | Apache-2.0 + Commons Clause v1.0 (no right to "Sell the Software") | https://github.com/polakowo/vectorbt/blob/master/LICENSE.md | ideas_only | Not OSI open source; avoid as a shipped dependency |
| VectorBT PRO | Paid successor | Proprietary membership | https://vectorbt.pro/ | no | Proprietary |
| zipline-reloaded | Backtester | Apache-2.0 | https://github.com/stefan-jansen/zipline-reloaded | code | Same licence |
| bt / ffn | Portfolio backtests, metrics | MIT | https://github.com/pmorissette/bt | code | Permissive |
| jesse | Crypto bot framework | MIT | https://github.com/jesse-ai/jesse | code | Paid plugins not checked |
| nautilus_trader | Trading engine | LGPL-3.0 | https://github.com/nautechsystems/nautilus_trader | ideas_only | Dependency only |
| hummingbot | Market-making bot | Apache-2.0 | https://github.com/hummingbot/hummingbot | code | Same licence |
| Lean (QuantConnect) | Engine (C#) | Apache-2.0 | https://github.com/QuantConnect/Lean | code | C#; ideas in practice |
| PyPortfolioOpt / Riskfolio-Lib / cvxpy | Optimisation, HRP, risk parity | MIT / BSD-3-Clause / Apache-2.0 | https://github.com/PyPortfolio/PyPortfolioOpt ; https://github.com/dcajasn/Riskfolio-Lib ; https://github.com/cvxpy/cvxpy | code | Permissive |
| empyrical-reloaded / quantstats | Performance metrics | Apache-2.0 | https://github.com/stefan-jansen/empyrical-reloaded ; https://github.com/ranaroussi/quantstats | code | Same licence |
| FinBERT: code | Financial sentiment training code | Apache-2.0 | https://github.com/ProsusAI/finBERT | code | Code only |
| FinBERT: weights | Pretrained sentiment model | **CC-BY-NC-SA-4.0** (HF card, checked twice) | https://huggingface.co/ProsusAI/finbert | no | Non-commercial and share-alike. Do not ship; fine-tune an MIT/Apache model instead |
| CryptoBERT (ElKulako) | Crypto social sentiment | MIT (model card) | https://huggingface.co/ElKulako/cryptobert | code | The kk08/CryptoBERT card has no licence |
| Chronos / Chronos-2 | Pretrained forecasters | Apache-2.0 (code and weights) | https://github.com/amazon-science/chronos-forecasting | code | Same licence |
| Kronos | K-line foundation model | MIT (code and weights) | https://github.com/shiyu-coder/Kronos | code | Permissive |
| TimesFM 2.0 / 2.5 | Pretrained forecaster | Apache-2.0 (code and these weights) | https://github.com/google-research/timesfm | code | Same licence |
| TimesFM 3.0 weights | Pretrained forecaster | timesfm-non-commercial-license-v1.0 (per PyPI) | https://pypi.org/project/timesfm/ | no | Non-commercial |
| Moirai 2.0 weights | Pretrained forecaster | CC-BY-NC-4.0 | https://huggingface.co/Salesforce/moirai-2.0-R-small | no | Non-commercial |
| TradingAgents | LLM multi-agent trader | Apache-2.0 | https://github.com/TauricResearch/TradingAgents | code | Same licence |
| CryptoTrade | LLM crypto agent | CC BY-NC-SA (stated for the dataset; LICENSE not read) | https://github.com/Xtra-Computing/CryptoTrade | ideas_only | Non-commercial |
| pytrends | Unofficial Google Trends client | Apache-2.0; archived 2025-04 | https://github.com/GeneralMills/pytrends | code | The data terms are the issue, not the code |
| TradingView public Pine scripts (e.g. Supertrend) | Indicator scripts | MPL-2.0 by default; the House Rules require crediting the author | https://www.tradingview.com/blog/en/changes-to-script-publishing-on-tradingview-13462 | ideas_only | Reimplement from the indicator's definition |

---

## 19. High-return research

**What counts.** Strategies with published returns of 10% or more over a defined period, from the sources read. The table reports each claim's own cost treatment. "Out of sample / after publication" records whether the result survived.

| candidate | claim (costs as stated) | period | drawdown | leverage / shorting | out of sample / after publication |
|---|---|---|---|---|---|
| `trend.ma-crossover` | 255% walk-forward annualised (Rozario et al.); 299% gross average annual, Sharpe 1.62 (Rohrbach et al. TS portfolio); both assume no or negligible costs | BTC ~2010-2020 (Rozario); Mar 2015 - Mar 2017 (Rohrbach) | about -40% (Rohrbach TS); not verified for Rozario | Rohrbach weights scaled by volatility, long and short; Rozario unverified | Rozario reports walk-forward; neither shown to survive realistic costs or post-publication |
| `breakout.donchian-turtle` | Turtle System 1 backtest 72% a year (Garner 2010, practitioner, futures) | Original Turtle era, futures (exact span in Garner) | 66% | Futures with unit pyramiding (leveraged) | Essentially unprofitable since the early 1990s per Garner: did not survive |
| `breakout.zarattini-ensemble` | 10-coin long-only portfolio Sharpe 1.50, about 18% net CAGR, about 11% a year net alpha vs BTC, at 10 bp costs | Jan 2015 - Mar 2025 | 12% max (portfolio) | Position size up to 200% of allocation (min(25%/sigma, 200%)) | No formal holdout reported; working paper of April 2025, no post-publication evidence yet |
| `momentum.dual-momentum` | 79.91% a year, Sharpe 1.64 (8-week BTC/gold variant), no costs | Dec 2018 - Apr 2026 | -43.94% | None (vol-capped variant holds cash) | No; lookbacks chosen on the full sample |
| `momentum.cross-sectional-long-short` | Weekly long-short excess returns 2.7%-4.1% before costs (Liu, Tsyvinski, Wu); 359% gross annual (Rohrbach et al.) | 2014-2018 (LTW); Mar 2015 - Mar 2017 (Rohrbach) | about -70% (Rohrbach CS) | Long-short, dollar-neutral | Fieberg et al. (2024): effect fades over time and is mostly from shorts after costs |
| `relative_strength.btc-lead-lag` | Long-short 2.16% a day out of sample after costs (Guo et al. working paper) | Not verified | Not verified | Long-short | Reported OOS; size flagged implausible in C-evidence.md |
| `mean_reversion.bollinger` | Average holding-period return >20% (20-day MA) and >50% (60-day MA) on Bitcoin futures (Day et al. 2023) | Not seen in abstract | Not reported in abstract | Futures margin; authors note returns on margin would be higher | Not verified |
| `stat_arb.funding-cash-and-carry` | Crypto carry up to 60% p.a., average above 10% a year (BIS); carry strategy Sharpe 6.45 (Borri et al.). Costs not stated in what was read; delta-neutral. | Borri et al.: 2020-08-01 to 2025-05-31; BIS sample period not read | Not given in the parts read | Delta-neutral, margin on the short leg | Decayed after publication/crowding: Sharpe 4.06 from 2024, negative in 2025 (Borri et al.) |
| `stat_arb.pairs-cointegration` | 11.61% a month at 5-minute frequency (Fil & Kristoufek); about 29% a year after costs (Fischer et al.) | Fischer: 18 Jun - 17 Sep 2018; Fil & Kristoufek: not verified | Not verified | Long-short (short leg requires margin/derivatives) | Fischer OOS only 3 months; Fil & Kristoufek not verified |
| `regime.intraday-seasonality` | 33% a year (21:00-23:00 UTC BTC rule), no costs | Oct 2015 - Feb 2022 | -22.45% | None | No; in-sample, and non-persistent per Baur et al. |
| `volume.vwap-signals` | 671% total return on QQQ, Sharpe 2.1, intraday long-short, net of unspecified commissions; about 8,242% on 3x TQQQ (Concretum summary) | 2018-01-02 to 2023-09-28 | 9.4% (QQQ version); TQQQ drawdown not given | 1x on QQQ (intraday long-short); 3x via TQQQ | No out-of-sample period reported. A replication reportedly found Sharpe of about 0.7 (unverified secondary claim). |
| `liquidity.amihud-illiquidity` | About 3% weekly excess return for long low-volume / short high-volume coins (3.2% for dollar volume), gross of costs (Liu, Tsyvinski and Wu, as summarised) | Working-paper sample, 2014-2018 (exact dates not verified) | Not reported in the summary read | Zero-investment long-short | No. In-sample factor sorts, explained by the three-factor model. |
| `ml_model.gradient-boosted-trees` | Long-only XGBoost over 65% a year with Sharpe above 1, net of 10 bp per transaction | Hourly BTC-USDT 2018-2026, 27-fold walk-forward | not read | not stated in what was read (perpetual-futures data) | Walk-forward, but the best of selected configurations; single coin in a strongly rising period |
| `ml_model.logistic-linear-lagged-returns` | Logistic regression about 18.8% a year, random forest about 29% a year, long-short after costs (level unverified) | Out of sample 18 Jun to 17 Sep 2018 (three months), 120-minute horizon, 40 coins | not reported in what was read | long-short; the short leg needs borrowing | Yes, but three months only; no later replication found |
| `ml_model.random-forest` | About 29% a year (7.1 bp a day) long-short after costs | 18 Jun to 17 Sep 2018, 40 coins, 120-minute horizon | not read | long-short | Yes, three months; no replication found |
| `ml_model.lstm-gru` | Up to 39% a month before costs (long-short), negative after costs | BTC, 1-60 minute horizons (dates not read) | not read | long-short | Yes; the gain does not survive costs |
| `ml_model.reinforcement-learning` | At least 4-fold returns in 50 days after 0.25% commission | Poloniex backtests, 50-day test windows (dates not read) | not read | none (portfolio weights) | Backtest only; the authors' repository says the reported test span is shorter than the experiment and warns live results may differ badly |
| `llm.news-headline-sentiment` | [S] OPT sentiment long-short gained 355% (Sharpe 3.05) after 10 bp costs | August 2021 to July 2023, US equities | not read | long-short | Test window; its relation to OPT's pretraining data was not verified; no independent replication found |
| `llm.autonomous-trading-agent` | Qwen3 Max +22.3% (from $10,000 to $12,231) in a live contest; four of six models lost 42-59% | 18 Oct to 3 Nov 2025 (17 days) | DeepSeek peaked above $13,000 before ending at $10,489; others not read | crypto perpetuals with leverage allowed [S]; level not read | Live and after every model's cut-off, but one short run with n = 6 |
| `risk.atr-trailing-stop` | Full system: 40.5% a year, Sharpe 2.41, net of 4 bp taker, slippage and funding | Jan 2022-Dec 2024 (out of sample) | -12.7% | Not stated; 70/30 long-short perpetuals | Walk-forward with monthly grid re-optimisation; preprint, no post-publication record |
| `risk.ratchet-stop` | Long-only Donchian ensemble with ratchet exit: 18% net CAGR, 11% a year net alpha against BTC; Sharpe 1.50 (10-coin book) | Jan 2015 to Mar 2025 | 12% (10-coin long-only, net 10 bp) | Volatility sizing min(25%/sigma, 200%), so up to 2x | Backtest on a survivorship-free universe; no post-publication record yet; the portfolio result at 0.50% was not verified |
| `risk.stop-loss` | US stock momentum with a 15% stop: 1.93% a month against 0.99% without (gross of costs, long-short) | 1926-2013 | Worst month -17.4% against -49.8% | Long-short; no leverage stated | Not crypto; gross; CXO warns of data snooping; no post-publication test found |

**Additional rows** (sources read, but the candidate sits elsewhere or the claim is context):

| Strategy | Source | Period | Return | Drawdown | Leverage / shorting | Costs | OOS / after publication |
|---|---|---|---|---|---|---|---|
| Daily LSTM/GRU long-short, top-100 coins | Jaquart, Köpke and Weinhardt 2022 (via C) | Not recorded in C | Sharpe 3.23 (LSTM) vs 1.33 for buy-and-hold | n/a | Long-short | After costs (level unverified) | OOS; authors cite limits to arbitrage |
| Contrarian portfolios, 100 coins | Kość, Sakowski and Ślepaczuk 2019 [A] (https://ideas.repec.org/a/eee/phsmap/v523y2019icp691-701.html) | 2014-2017 | Information ratio "often exceeds two-digit values" | n/a | Not stated | Percentage costs varied | Implausibly high; no replication found; contradicted by daily momentum in large coins |
| LSTM on BTC | Islas Anguiano and García-Medina 2025 (via C) | Under 1 year | +65% | n/a | n/a | Not stated | Buy-and-hold baseline only |
| ML ensemble (5 models must agree) | Sebastião and Godinho 2021 (via C) | Apr 2018 to Mar 2019 | 9.62% a year ETH, 5.73% LTC | n/a | n/a | 0.5% round trip | One bear-market year; best of many variants. Below the 10% bar, but the closest published cost level |
| Equity anomalies (decay context) | McLean and Pontiff 2016 (via C) | 97 predictors | 26% lower out of sample; 58% lower after publication | n/a | n/a | n/a | The decay estimate itself |

**Conclusions [R]:**
- **Only one claim is long-only, daily and low-turnover:** Zarattini et al. 2025, at 18% net CAGR, 12% drawdown and Sharpe 1.50, net of 10 bp. Its sizing goes up to 200%, which spot cannot match, and it is untested at 55 bp.
- **Decay is documented wherever it was measured:**
  - funding carry: Sharpe 6.45, then 4.06 from 2024, then negative in 2025 (Borri et al.);
  - Turtle System 1: unprofitable since the early 1990s (Garner 2010);
  - cross-sectional momentum fades (Fieberg et al. 2024);
  - Hudson and Urquhart found no Bitcoin predictability out of sample.
- **No crypto study measures post-publication decay** the way McLean and Pontiff do.
- **[R]** Haircut any published crypto return by at least McLean and Pontiff's 58%, then subtract the yearly fee drag at 1.10% a round trip.

---

## 20. Top 15 priorities

Ranked on the evidence for long-only spot at 0.55% a side, free and legal data, feasibility in the app, and turnover. Headline return was not used.

| Rank | id | Priority | Why |
|---|---|---|---|
| 1 | `breakout.donchian-turtle` (STRAT-004) | 1 | **The repository's best result:** +23.6% net over 4.3 years, beating random entries but below buy-and-hold. Positive crypto evidence (Gerritsen et al. 2020; Zarattini et al. 2025). 3-4 round trips a year (≈ 3-5% drag). Next: paper observation and slower-exit variants. |
| 2 | `breakout.zarattini-ensemble` | 1 | **The closest published design to this account:** long-only, daily, survivorship-free, tested up to 50 bp. Add lookbacks of 20 days or more and the midline ratchet to STRAT-004. Spot caps sizing at 100%. |
| 3 | `momentum.tsmom` (STRAT-005) | 1 | **The strongest general evidence** (Moskowitz et al.; Hurst et al. net of costs). Weekly decisions, 2-6 round trips a year. Already built, so evaluate rather than tune; the repo's lookback study exists. |
| 4 | `trend.price-above-ma` | 1 | **Daily price above its 50-200-day average, else cash.** Detzel et al. found it predictive out of sample, and Wei et al.'s log MA ratio survived SPA. 3-10 round trips a year; OHLCV only. Declare it as a member of the TSMOM family, which uses up trials. |
| 5 | `regime.ma-trend-gate` (OVL-REGIME) | 1 | **A veto that only removes trades;** cuts drawdowns in the cited studies. Evaluate on STRAT-004/005 with time in each state reported. |
| 6 | `data_source.coinbase-public-market-data` | 1 | **The primary venue's own free, keyless candles, trades and book.** Covers every candidate above. Start recording book snapshots now, since there is no history. |
| 7 | `portfolio.equal-weight-1n` | 2 | **The benchmark every multi-coin result must beat.** 1/N matches optimised weights out of sample in crypto (Liu 2019; Platanakis et al. 2018). Pair it with the existing random-entry baseline. |
| 8 | `risk.ratchet-stop` (OVL-RATCHET) | 2 | **Already built,** and the exit of the best-evidenced long-only design. Test it as STRAT-004's exit, not alone. |
| 9 | `ml_model.calibration-ev-gate` | 2 | **Infrastructure for any model or LLM:** trade only when calibrated EV exceeds 1.10%. Only removes trades; scikit-learn (BSD-3). |
| 10 | `ml_model.meta-labelling` | 2 | **The one ML use that fits a fixed strategy:** take or skip STRAT-004/005 entries. Must beat a random skip at the same rate on about 120-310 labels. |
| 11 | `volatility.vol-targeting-sizing` (with `volatility.ewma-riskmetrics`) | 2 | **Size once at entry from EWMA or range volatility, capped at 100%,** so no trades are added. Moderate evidence (Zarattini; Grobys et al. 2025), but the repo's Q3 test found no drawdown gain, so re-test rather than assume. |
| 12 | `risk.atr-trailing-stop` (OVL-ATR) | 2 | **Built but never evaluated.** Pre-register k = 2-3.5 on daily bars, against no stop and random stops. The only crypto evidence is a weak preprint. |
| 13 | `momentum.dual-momentum` | 2 | **A BTC/ETH/cash weekly switch;** long-only by design, 4-12 switches a year. Only gross, in-sample evidence, so it is a cheap extension of STRAT-005 rather than a new bet. |
| 14 | `risk.position-sizing-small-account` | 2 | **Every test must model the £50/£200/£500/£10,000 accounts:** minimum order, 1% entry raised to the minimum, 10% cap per coin. At £50 the minimum binds and DCA cannot work. |
| 15 | `data_source.kraken-ohlcvt` | 2 | **A licence-clean, long, free second history** (including 4h and trade counts) to cross-check Coinbase candles. Binance Vision cannot serve live use. |

**Next in line (priority 2, outside the top 15):**
- `regime.leverage-carry-veto`. Its free funding history is Binance Vision (non-production only) or Hyperliquid, whose terms were not read.
- `liquidity.spread-depth-filter`: validates the 0.05% slippage assumption for ZEC, DASH and HYPE.
- `volatility.realised-vol-estimators`;
- `trend.ma-crossover`, daily and slow only;
- `risk.stop-loss`, wide;
- `portfolio.dca-periodic`, as a baseline;
- `data_source.binance-vision-bulk`, for research only.

**Budget [R].** The A report (§11) limits an honest search over 4.3 years of data to a few dozen independent configurations across the whole initiative (Bailey et al. 2014). Declaring the 15 items above, with literature parameters and no tuning, already uses a large share of that budget.

---

## 21. What could not be verified

No numbers from these sources are used in the JSON. Where one is mentioned above, it is flagged.

**Classical technical:**
- Marshall, Young and Rose (2006), on candlesticks: only the bibliographic record was seen.
- Szakmary, Shen and Sharma (2010) and Fičura (2023): not re-located in this session; used only via A.
- Han, Kang and Ryu, on crypto momentum: the PDF returned 403.
- Gbadebo (2025), EMA momentum: redirect loop.
- A Mahidol RSI/PSAR thesis: snippet only.
- Grayscale (2023), "The trend is your friend": HTTP 429.
- Day et al. (2022), candles on Bitcoin futures: snippet only.
- Kurihara and Matsumoto: snippet only.
- JRFM 18(5) 242 (2025), on the halving: snippet only.
- CoinGecko halving figures: not read.
- Liberated Stock Trader's Supertrend test: HTTP 403.
- Supertrend's authorship.
- Resta, Pagnottoni and De Giuli (2020): MDPI returned 403.
- Huang, Huang and Ni (2019): snippet only.
- The exact rule classes in Hudson and Urquhart.

**Volume, liquidity and volatility:**
- Easley, O'Hara, Yang and Zhang (2024, VPIN/ML crypto): SSRN returned 403.
- Grobys et al. (2025): full text blocked.
- Bergsli et al. (2022): PDF 403; used via C.
- Lee and Wang (2024).
- Leirvik (2022): abstract only.
- Darné and Charles (2019): search summary only.
- The journal version of Hansen, Kim and Kimbrough.
- The CTREND full-text figures.
- The Zarattini and Aziz (2023) VWAP paper itself; its "replication Sharpe ≈ 0.7" is secondary only.
- Original sources not fetched: RiskMetrics (1996), Wilder (1978), Granville (1963), Chaikin, Quong and Soudack, Steidlmayer, Faith's Turtle PDF.
- Alexander and Imeraj, on the Bitcoin VIX.
- Practitioner claims that DVOL predicts returns.
- Bieganowski and Ślepaczuk (2026): figures not in the abstract.
- Gerritsen et al.'s OBV-specific results.
- Exchange trade-history backfill depth.
- The terms of Binance REST and of Deribit.

**ML and LLM:**
- López de Prado, "10 reasons most ML funds fail": not searched.
- The full texts of Joubert (2022), Meyer et al. (2022, 2023) and Thumm et al. (2022): companion-repo summaries only.
- The licence of the meta-labeling repo.
- Kirtac and Germano (2024) full text: their 74.4%, Sharpe 3.05 and 355% come from a summary.
- Lopez-Lira and Tang's earlier "over 500%" figure: summary only.
- FinMem, FinAgent and Alpha-GPT papers: not opened.
- The TradingAgents test window.
- CryptoTrade's fee rate and GPT-4/4o cut-offs.
- The official Alpha Arena leaderboard.
- LiveTradeBench and AlphaAgent results: summaries only.
- Agakishiev et al. (2025), on HMM with RL.
- The Springer DRL paper (login wall).
- Millea (2021).
- The genetic-programming papers on Bitcoin.
- Neely, Weller and Dittmar on FX genetic programming.
- Three crypto LLM-sentiment papers (MDPI BDCC 8(6):63; arXiv 2502.19349; an NCCU thesis): found but not opened.
- Kulakowski and Frasincar's accuracy figures.
- The CLEF 2026 working note.
- The PGPortfolio code licence.

**Data sources:**
- Coinbase Market Data Terms full text: HTTP 403.
- CoinDesk's own announcement of the free-tier retirement.
- Reddit Data API terms: a mirror was used.
- Google's Trends terms and the Trends API alpha page.
- The start date of Wikipedia pageviews.
- Glassnode's free tier.
- Kaiko pricing.
- Bybit and OKX archive contents and terms.
- Deribit and Hyperliquid terms and rate limits.
- Blockchair's official docs; mempool.space's licence on the repo page.
- Inan, "Predictability of funding rates".
- A Czech Journal of Economics and Finance Fear & Greed study: 404.
- Huang et al. (2024), a Bitcoin sentiment index.
- Steinert and Herff (2018): captcha.
- Alessi et al., on news in 26 languages.
- K33's long-squeeze statistic.
- Lim (2026), on the Hyperliquid liquidation cascade.
- A UDP thesis on Bitcoin predictors.

**Risk, portfolio and licensing:**
- The Han, Zhou and Zhu paper itself: CXO summary only.
- Alpha Architect's replication of it: 403.
- Kaminski and Lo, and MacLean, Thorp and Ziemba: full texts not read.
- Black and Perold (1992), on CPPI: not searched.
- **Coinbase's minimum order in USD/GBP:** no official single figure; third parties say $1 or $2.
- Coinbase's flat fees for small simple trades.
- Petukhina et al. (2020) full text.
- The opencryptopricing replication of Liu, Tsyvinski and Wu.
- **pandas-ta's current licence.**
- A Leiria thesis on DCA.
- QuantConnect's inverse-volatility and HRP figures.
- Perrenod's Kelly figures.
- The Sadaqat and Butt (2023) full text.
- Kaufman (1995), on profit-taking.
- Coinbase's current fee pages: the 0.50% taker figure is the app's, as in the A report.

---

## 22. Method

**How the catalogue was built.** Five research passes on 2026-11-11, each with its own web searches and fetches:
1. classical technical families;
2. volume, liquidity, microstructure and volatility;
3. ML and LLM;
4. data sources and alternative-data signals;
5. risk, portfolio, licensing and high returns.

**Assembly:**
- The parts were merged and checked for schema completeness, enum values and unique ids.
- Three overlapping pairs were merged.
- Every finding was confirmed to carry a [FT]/[A]/[S] tag.

**Independent re-checks at assembly:**
- the Binance Vision terms (licence and the clauses quoted above);
- the FinBERT weights' licence on Hugging Face;
- the Bui and Nguyen arXiv record;
- the Alpha Arena coverage;
- pandas-ta's PyPI record;
- a public copy of Garner (2010).

**Repository facts** come from the task brief, the A report, C-evidence and the code tree (`app/strategies/catalogue.json`, `model_lab`, `signal_fusion`, `llm_gate`, `candlestick_patterns`, `portfolio_optimizer`, `position_sizing`). The repository was not edited.

**Working files.** Each research pass's JSON and notes, and the script that merged them into `B-candidates.json`, were kept outside the repository (572 KB). They hold longer prose and per-pass licence and data tables, and can be added on request.
