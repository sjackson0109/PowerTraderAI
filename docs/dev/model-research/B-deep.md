# B: Deep sequence models and pretrained time-series models

Research agent B of three. Written 2026-11-05. This is research only: nothing was installed or run.

**Verdict, with its caveat:** I found no credible published evidence that any deep sequence model or pretrained time-series foundation model (TSFM) can time entries on hourly crypto better than a naive or random baseline. The best measured skill is at chance level, or a little above it with large caveats. The models below are worth testing only as cheap experiments through the existing entry gate, and the expected result is "no skill above random entries".

Each claim gives its source in brackets. Text marked **Inference** is my own reasoning, not taken from a source.

---

## 0. Short answers to the four questions

1. **Is CPU use feasible at our scale (per coin, hourly, about 26,000 bars)?**
   - **Zero-shot inference: yes, for the small models.** NXAI ran a test on a 2-core 2016 laptop CPU (i7-6600U), with 2048 bars of context and a 32-step horizon. Time per forecast was 0.09 s for TiRex, 0.31 s for Chronos-2, 2.35 s for TimesFM-2.5 and 13.8 s for PatchTST-FM ([NXAI, HF blog, 2026-03-05](https://huggingface.co/blog/BobWue/edge)). NXAI makes TiRex, so this is a vendor-run test.
   - **Our own small networks: yes.** On a Xeon CPU, an LSTM with 168 bars of lookback took 118 ms per prediction and PatchTST took 9 ms ([Soni et al. 2026, arXiv 2605.24381](https://arxiv.org/abs/2605.24381)).
   - **Training our own small network: "minutes per coin" is plausible, but I found no published timing.** **Inference:** a model of under 1M parameters trained on about 26k windows should take minutes on CPU. Measure it before relying on it.
   - **Fine-tuning:** fine-tuning a tiny TSFM (IBM TTM, about 1M parameters) takes "a few minutes" and "can be executed even on CPU-only machines", by IBM's own claim ([TTM r2 card](https://huggingface.co/ibm-granite/granite-timeseries-ttm-r2)). Fine-tuning a model of 100M+ parameters (Chronos-2, TimesFM) on CPU has no published timing. For scale: Fu et al. needed 8 V100 GPUs for about an hour to fine-tune TimesFM on 90M points ([arXiv 2412.09880](https://arxiv.org/abs/2412.09880)).
   - **Pretraining a finance TSFM from scratch:** this is the only route that produced gains in Rahimikia et al., and it took about 50,000 GPU hours ([arXiv 2511.18578](https://arxiv.org/abs/2511.18578)). It is not feasible on CPU.

2. **What evidence exists on returns, not benchmarks?** Very little, and it is mostly negative. Benchmark wins do not carry over:
   - FinVerse (116,897 financial series, 43 models) finds model rankings agree only moderately with GIFT-Eval rankings (r = 0.43). Its authors write that "generic forecasting benchmarks do not fully capture the aspects of forecast quality that matter for financial decision-making" ([arXiv 2608.03259](https://arxiv.org/abs/2608.03259)).
   - A hold-out test built only from data published after each model's release found that pretrained models matched seasonal-naive forecasts on daily exchange rates, as did every other method tested. Their wins elsewhere tracked how familiar each domain was from the pretraining corpus ([Moghadasi & Ghaderi 2026, arXiv 2609.10357](https://arxiv.org/abs/2609.10357)).
   - Across 9 deep architectures trained on hourly OHLCV for 12 assets (4 of them crypto), mean directional accuracy was 50.08% ([Saidd 2026, arXiv 2603.16886](https://arxiv.org/abs/2603.16886)).

3. **Do zero-shot forecasts carry a trading signal after costs?** I found no credible evidence that they do.
   - On daily stock returns, zero-shot Chronos and TimesFM "perform poorly" ([Rahimikia et al. 2025](https://arxiv.org/abs/2511.18578)).
   - On daily crypto, zero-shot TimesFM had a Sharpe ratio of -0.03 before costs ([Fu et al. 2024](https://arxiv.org/abs/2412.09880)).
   - On 997 Binance pairs, zero-shot Moirai, TimesFM, MOMENT and Chronos showed near-zero or negative crypto IC (information coefficient, the correlation between forecast and outcome) ([Kronos paper, Tables 15/17](https://arxiv.org/abs/2508.02739)).
   - The one positive hint is a seminar abstract on hourly BTC from 2018 to 2021. It says these models "can occasionally" make profitable signals after costs, but gives no numbers I could verify, and its test period predates, and so may overlap, the models' pretraining data ([WNE UW seminar](https://www.wne.uw.edu.pl/badania-i-nauka/konferencje-i-seminaria/nadchodzace-wydarzenia/seminarium-z-udzialem-jana-wolyniaka-studenta-wne-uw)).

4. **Can they predict a classification target like ours?**
   - **Deep networks we train:** yes, directly, with a binary cross-entropy loss. NeuralForecast also offers a Bernoulli loss "for temporal classifiers" ([NeuralForecast losses](https://nixtlaverse.nixtla.io/neuralforecast/losses.pytorch.html)).
   - **TSFMs:** no. They output forecasts only:
     - quantiles: Chronos-2, Chronos-Bolt, TimesFM-2.5/3, TiRex/TiRex-2, Toto 2.0, Moirai 2.0;
     - sample paths: original Chronos, Sundial, Kronos, Lag-Llama;
     - point forecasts: TTM.

     (Sources in section 2.)
   - **Turning quantile forecasts into "chance of +5% before -2.5%":** this cannot be done exactly. **Inference** (standard probability, no source needed): per-step marginal quantiles do not fix the joint law of the path, so they give neither the running maximum or minimum nor which barrier is hit first. The most they give is a lower bound on "touches +5% at some step".
   - **Two workable routes (Inference):**
     - (a) Use a model that samples whole paths and count barrier hits by Monte Carlo. Kronos is the best fit, because it samples full OHLCV candles, so highs and lows are included.
     - (b) Feed the TSFM's quantiles in as features to a small classifier trained on our label and calibrated on validation bars.

**How our judge changes the reading (Inference):** the entry gate compares the model with random entries on the same coin, with the same number of trades and the same exits, so fees fall on both sides. Many published studies fail after costs because of turnover: they trade every hour (Bysik & Ślepaczuk, below). Our exits hold positions until a +5% trailing exit, so turnover is low. The question that matters for us is therefore whether a model has any entry-timing skill at all over hours to days. That evidence (direction about 50%, cross-sectional IC about 0.02-0.04, hourly random walk not beaten) is weak even before costs.

---

## 1. Shortlist, ranked (4 candidates; I did not pad it to 6)

Evidence scale used in the table:
- **strong:** after-cost results on hourly crypto against a naive or random baseline, replicated;
- **some:** peer-reviewed, clean temporal split, crypto included, but no after-cost trading result;
- **weak:** related settings only, or mixed results;
- **none:** nothing found.

| # | Name | Family | What it predicts for us (target) | Why it is on the list | Evidence | Fit to constraints 1 / 2 / 3 / 4 |
|---|---|---|---|---|---|---|
| 1 | Small deep classifier on the barrier label (GRU or TCN; one model pooled across coins, or one per coin) | Deep sequence model we train | P(high reaches entry +5% plus fees before low reaches the first DCA level, -2.5%, within N hours). Optional second head: P(reaching DCA 2, -5%). | Only option that optimises our target directly. We control the training window, so there is no pretraining overlap. Cheapest to build and run. Tells us whether depth adds anything over agent A's tabular models. | **Weak** (direction-classification studies: mixed, mostly negative after costs; nothing on barrier labels with our exits) | 1: yes (inference about 0.1 s, sourced; training minutes, unsourced). 2: PyTorch, BSD-3; torch 2.15.0, 2026-10-28. 3: OHLCV only. 4: local. |
| 2 | Kronos-mini (4.1M) / Kronos-small (24.7M) | Pretrained TSFM, finance-native (OHLCV candles) | Zero-shot: sample about 20-50 future candle paths and count the share whose highs touch +5% before their lows touch -2.5% (Monte Carlo barrier probability). Optionally fine-tune. | Only open model pretrained on OHLCV candles that include crypto, at 1m to 1w. It samples whole candles, so the barrier probability can be computed directly. Pretraining ends June 2024, so a 2026 hold-out is clean. | **Some** (AAAI 2026, clean temporal split, crypto included), but its crypto IC is no better than DLinear's and there is no crypto trading test | 1: unknown. No CPU timings published; autoregressive sampling of many paths may exceed 1 s per bar, so measure it. 2: MIT (code and weights); GitHub-only install, no PyPI; last commit 2026-04-13. 3: OHLCV plus amount, our exact data. 4: local. |
| 3 | Chronos-2 (120M), zero-shot; TiRex-2 as alternative | Pretrained TSFM, general-purpose | Quantiles of close, high and low over the next N hours (multivariate; BTC as a covariate for altcoins), used as features in a calibrated classifier on our label, or as a rule such as "skip entry when the 10% quantile of the 24h low is below -X%". | Easiest TSFM to run on CPU with a maintained pip package. Needs no per-coin training, which matters for HYPE (about 1 year of history). | **Weak**, and mostly negative for returns | 1: yes (0.31 s per forecast on a 2016 2-core laptop CPU, vendor test). 2: Apache-2.0 code and weights; chronos-forecasting 2.3.2, 2026-09-08. 3: OHLCV. 4: local after one weight download. |
| 4 | IBM TTM r2 (Granite TinyTimeMixer, about 1M), fine-tuned per coin | Pretrained TSFM, tiny, fine-tunable | Point forecasts of the next-N-hour path (close, high, low), or of a volatility proxy, used as classifier features | Only TSFM whose maker says it fine-tunes on CPU in minutes. Its pretraining includes a bitcoin dataset. It was the only TSFM to beat Log-HAR at every horizon on realised volatility (Log-HAR is the standard econometric volatility benchmark). | **Weak** (volatility only, narrow margin; nothing on returns) | 1: yes (vendor claim). 2: Apache-2.0; granite-tsfm 0.3.12, 2026-10-29. Pins torch <2.12, which conflicts with tsai (torch >=2.12). 3: OHLCV. 4: local. |

TimesFM-2.5, Toto 2.0, Sundial, Mantis and the deep forecasters (PatchTST, N-HiTS, iTransformer, TFT and others) are covered in section 4. I left them off the list because they duplicate a slot above or fail a constraint.

---

## 2. Candidates in detail

### 2.1 Small deep classifier on the barrier label (rank 1)

**What it is:** a GRU or TCN reads the last W hourly bars (for example W = 168) and outputs P(y = 1) through a sigmoid. Several horizon labels can be predicted at once. Training is pooled across coins with a coin embedding, or done per coin.

**Target (Inference):** for entry at close t, with entry price including fees:
- y = 1 if, within N hours, the high reaches the trailing-start level (+5%) before the low reaches the first DCA level (-2.5%);
- ties within one bar are resolved pessimistically (low first).

This is the "triple-barrier" labelling of López de Prado (Advances in Financial Machine Learning, Wiley 2018, ch. 3). The same book (ch. 7) explains why overlapping labels need purging and an embargo at the train/test boundary. Here that means dropping the last N hours of training before the validation and hold-out bars.

Score it against the label's base rate, and then through the entry gate. Hit rate means nothing under these exits.

**Evidence (all on direction labels, not on our barrier label):**

- **Jaquart, Dann & Weinhardt 2021**, *J. Finance & Data Science*. BTC at 1-60 minute horizons; GRU, LSTM and boosting. The models beat a random classifier, and monthly returns reached up to 39% before costs, but "negative returns after taking transaction costs into account" ([EconBiz record](https://www.econbiz.de/Record/short-term-bitcoin-market-prediction-via-machine-learning-jaquart-patrick/10013162705)).
  - Flaws: very short holding periods. The record does not say which cost level was assumed.
- **Jaquart, Köpke & Weinhardt 2022**, *J. Finance & Data Science* 8:331-352. Daily binary relative moves of the 100 largest coins. Accuracy 52.9-54.1%. A long-short LSTM/GRU portfolio had an after-cost Sharpe of 3.23 / 3.12, against 1.33 for buy-and-hold ([doi 10.1016/j.jfds.2022.12.001](https://doi.org/10.1016/j.jfds.2022.12.001); abstract via DOAJ/EconBiz).
  - Flaws: I could not verify the cost assumption (full text not readable). The design is cross-sectional long-short, which needs shorting of small coins; the authors themselves say limits to arbitrage "cannot be entirely ruled out". The sample is a crypto bull era. It does not transfer to single-coin, long-only timing.
- **Bysik & Ślepaczuk 2026**, hourly BTC/USDT perpetuals, 2018 to 2025-26, 27-fold walk-forward, XGBoost, LSTM and iTransformer ([arXiv 2606.00060](https://arxiv.org/abs/2606.00060)).
  - Long-only with the naive sign rule at 10 bps: LSTM annualised return went from +72.4% to -50.7%, and iTransformer from +129% to -83.9%.
  - With a cost-aware filter: LSTM +49.4% (Sharpe 0.84) and iTransformer +34.9% (Sharpe 0.64), against buy-and-hold +56.3% (Sharpe 0.82). The filtered strategies do not significantly beat buy-and-hold after Holm correction.
  - Flaws: many configurations, with the best one highlighted; no random baseline; costs of 10 bps against our roughly 55 bps per side.
- **Saidd 2026:** 918 runs, 9 architectures (ModernTCN best by RMSE, PatchTST second), hourly OHLCV for 12 assets including 4 crypto. "Mean directional accuracy is 50.08%" ([arXiv 2603.16886](https://arxiv.org/abs/2603.16886)).
  - Flaws: no trading test; the asset list is not given in the abstract.
- **Fischer & Krauss 2018**, *EJOR* 270(2). LSTM on S&P 500 stocks: 0.46% a day before costs, but since 2010 "profitability hovering around zero after transaction costs" ([RePEc](https://econpapers.repec.org/RePEc:eee:ejores:v:270:y:2018:i:2:p:654-669)). Equities, not crypto.
- **Baquero 2026 review of Bitcoin forecasting:**
  - Puoti et al. (2024) found naive models "consistently outperform all complex alternatives", LSTM included.
  - Gradojevic et al. (2023), at hourly frequency: "no model significantly outperforms the random walk".
  - Only 7 of the 23 studies tabulated use a naive or random-walk benchmark.

  Source: [arXiv 2606.00071](https://arxiv.org/abs/2606.00071) (secondary; I did not open the cited studies).

**Fit:**
- C1: LSTM inference 118 ms on a Xeon ([Soni et al. 2026](https://arxiv.org/abs/2605.24381)). Training time is unsourced (Inference: minutes for under 1M parameters on 26k windows).
- C2: PyTorch (BSD-3); the latest torch is 2.15.0, released 2026-10-28; the Windows x86-64 wheel on PyPI is 126.7 MB ([PyPI torch](https://pypi.org/project/torch/#files)).
- C3: OHLCV only. Multi-timeframe inputs come from bars we already have.
- C4: fully local.

**Pitfalls (Inference):**
- 26k hourly bars is small for a deep network; pooling across coins is the standard fix.
- Compute normalisation statistics only from the context window. Kronos shipped exactly this leak in its fine-tuning code (see 2.2).

### 2.2 Kronos (rank 2)

**What it is:** a decoder-only model over tokenised candles (OHLCV plus amount). It was pretrained on "over 12 billion K-line records from 45 global exchanges", covering equities, crypto, futures and FX at 7 frequencies from 1 minute to weekly. "The pre-training data for Kronos extends up to June 2024", and "our test period for all tasks begins in July 2024" ([arXiv 2508.02739](https://arxiv.org/abs/2508.02739); published at AAAI 2026, [AAAI proceedings](https://ojs.aaai.org/index.php/AAAI/article/view/39730)).

**Models:**
- open: mini (4.1M parameters, context 2048), small (24.7M, context 512), base (102.3M, context 512);
- large (499M) is not released.

Code and weights are MIT ([GitHub](https://github.com/shiyu-coder/Kronos), [HF card](https://huggingface.co/NeoQuasar/Kronos-small)).

**Target for us (Inference):** Kronos samples whole future candles, so each sampled path has highs and lows. P(+5% before -2.5% within N hours) is then the share of sampled paths where the high crosses first. Of all the models here, this matches our label most directly.

**Evidence:**

- **Crypto results** (Binance perpetuals, 997 assets, from 2021-01-31, averaged over frequencies; per-pair results not given):
  - Return-forecast IC/RankIC was 0.037/0.033 (Kronos-small), against 0.0446/0.0283 for DLinear. Kronos leads on RankIC but **not on IC**.
  - On price-series RankIC for crypto, Kronos (0.0138) trails PatchTST (0.0192).
  - Zero-shot Moirai, TimesFM, MOMENT and Chronos show near-zero or negative crypto IC.

  Source: paper, Tables 14-17.
- **Trading simulation:** Chinese A-shares only (CSI300/800), top-k long-only, "a conservative transaction cost of 0.15%". Kronos-small had an annualised excess return of 0.179 and an information ratio of 1.42, against 0.168 / 1.37 for the best baseline (paper, Table 10). There was no crypto trading test.
- **Critique ([Pith review](https://pith.science/paper/2508.02739)):** Kronos averages 10 sampled rollouts while every baseline makes one forecast. No single-rollout result is reported, so part of the headline "93% RankIC" gain may come from ensembling. Sampling settings appear to have been tuned on the test period. There are no error bars. The reviewer judges the temporal split sound.
- **Leakage bug:** a bug in the repo's fine-tuning dataset leaked future bars into the normalisation statistics. It was reported 2026-03-17 and fixed in PR #234, merged 2026-04-13 ([issue thread](https://github.com/shiyu-coder/Kronos/pull/227)). The thread does not say whether the published numbers were affected.
- **Kinlay commentary:** "a promising research direction, not a production alpha engine". He ran no Kronos tests of his own ([blog, 2026-02](https://jonathankinlay.com/2026/02/time-series-foundation-models-for-financial-markets-kronos-and-the-rise-of-pre-trained-market-models/)).

**Bias checklist:**
- Look-ahead: clean for a 2026 hold-out. A 3-year training window would overlap pretraining from Nov 2023 to Jun 2024, which matters only if we fine-tune.
- Costs: present only in the equities simulation.
- Random baseline: none.
- Replication: none independent.

**Fit:**
- C1: no CPU timing published. The paper's runs used GPU pods ([paper appendix](https://arxiv.org/html/2508.02739)). **Inference:** about 25 autoregressive steps times 20-50 paths with a 4-25M parameter model is likely a few seconds per bar on CPU, so it could miss the under-1-second target unless we batch or cut the path count.
- C2: MIT. There is no PyPI package; install is from GitHub. Last commits were in April 2026, with about 76 commits and no tagged releases. There is a maintenance risk.
- C3: our exact data.
- C4: local.

**Fallback if Kronos is too slow or unmaintained:** Sundial-base (128M, Apache-2.0) also samples paths (close only). Its maker reports CPU times of 249-949 ms on an M1 Pro for 1-20 samples. It pins `transformers==4.40.1` and Python 3.10 and needs `trust_remote_code` ([HF card](https://huggingface.co/thuml/sundial-base-128m)). Evidence on finance: none.

### 2.3 Chronos-2, zero-shot, with TiRex-2 as alternative (rank 3)

**What it is:**
- 120M parameters, encoder-only; zero-shot univariate, multivariate and covariate-informed forecasting ([arXiv 2510.15821](https://arxiv.org/abs/2510.15821), 2025-10-17).
- Context up to 8,192 steps; horizon up to 1,024 steps; output is quantiles; supports CPU ([HF card](https://huggingface.co/amazon/chronos-2)).
- Trained on a subset of the Chronos datasets, GIFT-Eval Pretrain and synthetic data.
- Apache-2.0. `chronos-forecasting` 2.3.2 was released 2026-09-08 and needs Python >=3.10, torch <3 and >=2.2, and transformers <6 and >=4.41 ([PyPI](https://pypi.org/project/chronos-forecasting/)).
- Fine-tuning is available through PEFT/LoRA ([AutoGluon Chronos-2 source](https://auto.gluon.ai/stable/_modules/autogluon/timeseries/models/chronos/chronos2.html)).

**Target for us (Inference):** quantiles cannot give "first to +5% or -2.5%" exactly (section 0). Two uses remain:
- (a) Feed the q10/q50/q90 of high, low and close at 6/24/72 hours into the rank-1 classifier as extra features, then let the entry gate judge whether they add anything.
- (b) A downside veto: skip an entry when the predicted lower tail is deep. This targets the trades that drive mean return under our exits (deep DCA, long hold).

**Evidence (all weak or negative on returns):**

- **Rahimikia, Ni & Wang 2025:** daily excess returns, 94 countries, out-of-sample 2001-2023.
  - Zero-shot Chronos-large (window 512) had R² of -1.37% and directional accuracy "just above 51%". TimesFM-500M had R² of -2.80% and directional accuracy "just below 50%".
  - Fine-tuning "does not translate into economic gains".
  - Only pretraining from scratch on finance data helped, at about 50,000 GPU hours.
  - Flaws: headline Sharpe ratios are "without accounting for transaction costs"; the authors flag look-ahead from pretraining overlap for the off-the-shelf models.

  Source: [arXiv 2511.18578](https://arxiv.org/abs/2511.18578).
- **Noguer i Alonso & Franklin 2026:** TimeGPT, TimesFM-2.5, Moirai-2.0, Chronos and Chronos-2 on 5 large US stocks, 20-day horizon.
  - The pretrained models won 8 of 10 task-level rankings, but skill scores against the random walk are about 10⁻³: "gains over the random-walk benchmark are small and sparse". Diebold-Mariano tests reject equal accuracy only in 2 cases.
  - The authors say this does not support TSFMs as engines of "alpha generation or trading performance".
  - Flaws: 5 hand-picked surviving stocks; no trading test; the test period (Aug 2024 to Feb 2026) may overlap 2025 pretraining.

  Source: [arXiv 2606.27100](https://arxiv.org/abs/2606.27100).
- **Fu, Hirano & Imajo 2024:** zero-shot TimesFM on daily crypto, market-neutral long-short, zero cost: Sharpe -0.03; random baseline 0.01.
  - After fine-tuning on about 90M financial points (including about 50M hourly crypto points): Sharpe 0.26, against 0.17 for an AR(1) model. "Neutral cost" was 0.44% (their "cost basis to zero out returns").
  - Inference: if that is a per-trade break-even cost, it is below our roughly 0.55% per side.

  Source: [arXiv 2412.09880](https://arxiv.org/abs/2412.09880).
- **Etienne 2026 (personal blog, anecdotal):** zero-shot Chronos-2 on BTC 4h bars, Oct-Dec 2024, had directional accuracy of 0.43-0.48, against 0.51 for ARIMA. One regime, no cost model ([post 06](https://jeromeetienne.github.io/blog/2026-06-15-post-06-pretrained.html)).
  - A fine-tuned Chronos-2-small, averaged over 5 seeds, still trailed ARIMA ([post 07](https://jeromeetienne.github.io/blog/2026-06-17-post-07-finetuned.html)).
- **Wołyniak & Ślepaczuk** (Univ. Warsaw seminar, year not stated): Chronos, Chronos-2, TimesFM, Toto, Moirai, Lag-Llama, MOMENT and TTM zero-shot on hourly BTC from 2018 to Jan 2021.
  - Frictionless returns were "extremely high … due to very frequent trading". With costs, only sparse, selective signals did better.
  - Cost level not stated. Test period pre-dates (and may overlap) pretraining corpora; TTM's pretraining includes a bitcoin dataset.

  Source: [seminar page](https://www.wne.uw.edu.pl/badania-i-nauka/konferencje-i-seminaria/nadchodzace-wydarzenia/seminarium-z-udzialem-jana-wolyniaka-studenta-wne-uw). Full paper not found.

**Fit:**
- C1: 0.31 s per forecast on an i7-6600U at context 2048 ([NXAI blog](https://huggingface.co/blog/BobWue/edge)). No training is needed. **Inference:** a full gate replay of 720 hold-out bars × 9 coins is about 6,500 forecasts, roughly 30 minutes unbatched on that old CPU, and less when batched.
- C2: Apache-2.0 code and weights.
- C3: OHLCV.
- C4: local after one weight download.

**TiRex-2 (alternative in the same slot):**
- xLSTM, 38.4M parameters (plus 44.1M in multivariate mode), quantiles, past and future covariates, Apache-2.0 ([GitHub](https://github.com/NX-AI/tirex-2)).
- `tirex-2` 0.4.0 was released 2026-10-20 and needs Python >=3.11 and torch >=2.8, plus the `flashrnn` and `mlstm_kernels` packages ([PyPI](https://pypi.org/project/tirex-2/)).
- TiRex v1 was the fastest model in the NXAI CPU test (0.09 s).
- Windows risk: the package "applies `torch.compile` unconditionally, which requires a working C++ toolchain" ([sktime wrapper docs](https://www.sktime.net/docs/api-reference/sktimeforecastingtirex2tirex2forecaster/)). Windows is not documented. TiRex v1 was "only tested on Linux and MacOS" ([PyPI tirex-ts](https://pypi.org/project/tirex-ts/)) and is under the NXAI Community License, not Apache.
- Fine-tuning is only in the paid "TiRex-2 PRO".
- Evidence on finance: none.

### 2.4 IBM TTM r2, fine-tuned (rank 4)

**What it is:**
- Tiny MLP-mixer models of about 1M parameters (the card lists 805k).
- Contexts of 512/1024/1536; minutely to hourly resolution (r2), daily and weekly from r2.1; point forecasts.
- "Can be executed even on CPU-only machines"; fine-tuning takes "a few minutes".
- Pretraining includes "bitcoin" among public datasets.
- Apache-2.0.

Source: [HF card](https://huggingface.co/ibm-granite/granite-timeseries-ttm-r2). `granite-tsfm` 0.3.12 was released 2026-10-29 and needs Python 3.11-3.13, torch <2.12 and >=2.10, and transformers <6 and >=4.57.6 ([PyPI](https://pypi.org/project/granite-tsfm/)).

**Target for us (Inference):** a fine-tuned point forecast of the next-N-hour high, low and close, or of realised volatility, fed into the rank-1 classifier as a feature. Because it fine-tunes in minutes on CPU, it is the only pretrained model we could retrain on our schedule.

**Evidence:**
- **Brini 2026:** realised volatility on 50 assets (equities, FX, futures; no crypto). TTM was the only one of 9 zero-shot TSFMs to beat Log-HAR at every horizon, "only by a narrow margin". Most of the short-horizon gain was better scaling, not better dynamics ([arXiv 2607.05291](https://arxiv.org/abs/2607.05291)).
- **Goel et al. 2025:** fine-tuned TimesFM beat econometric benchmarks on realised volatility; zero-shot was only "a reasonable baseline" ([arXiv 2505.11163](https://arxiv.org/abs/2505.11163)).
- Volatility is a different target. **Inference:** a volatility forecast does not give direction. Higher volatility means both a faster +5% and deeper DCA, so its value to our entries is unknown.
- Returns evidence: none. TTM appears in the Wołyniak & Ślepaczuk BTC study, but with no reported numbers.

**Fit:**
- C1: yes (vendor claim).
- C2: Apache-2.0, maintained. Dependency conflict: torch <2.12 conflicts with tsai 1.0.1 (torch >=2.12), and the current torch is 2.15.
- C3: OHLCV.
- C4: local.

---

## 3. Libraries: one interface for swapping models

**Recommendation (Inference):** don't make a third-party library the app's model interface. Define a thin interface in the app: `fit(bars, until)` and `entry_score(context) -> float`, plus a flag saying whether the model needs training. Write one small adapter per model behind it.

Reasons:
- Our target is a classification label scored by our own gate.
- None of these libraries treats "deep model plus classification" and "TSFM" the same way.
- Their pins conflict.

If one backend library is wanted for the deep and foundation models, **Darts** is the best fit.

| Library | Latest (date) | Licence | What it covers for us | Windows / install cost |
|---|---|---|---|---|
| **Darts** | 0.48.1 (2026-10-16) | Apache-2.0 | Torch models: RNN/LSTM/GRU, TCN, N-BEATS, N-HiTS, TFT, TiDE, TSMixer, DLinear/NLinear, with probabilistic output. Foundation wrappers: Chronos-2, TimesFM 2.5 and 3, TiRex/TiRex-2, PatchTST-FM, T0 ("no training required"). **Classification only through sklearn-style models** (CatBoost, LightGBM, XGBoost, sklearn), not torch models. | Python >=3.11. `darts[torch]` adds torch >=2.6 and pytorch-lightning >=2.6.6 (loose pins). TiRex/TiRex-2/T0/NeuralForecast are separate installs. Windows listed. ([PyPI](https://pypi.org/project/darts/), [INSTALL.md](https://github.com/unit8co/darts/blob/master/INSTALL.md), [README](https://github.com/unit8co/darts)) |
| **NeuralForecast** | 3.3.0 (2026-10-07) | Apache-2.0 | About 30 deep forecasters (N-HiTS, PatchTST, iTransformer, TFT, LSTM and others). **Bernoulli loss "for temporal classifiers"**, the only library here where its deep models can train on a binary target. No TSFMs. | Hard dependencies: torch >=2.9.1, pytorch-lightning >=2.6.6 and **ray[train,tune]** (heavy). ([PyPI JSON](https://pypi.org/pypi/neuralforecast/json), [losses](https://nixtlaverse.nixtla.io/neuralforecast/losses.pytorch.html)) |
| **sktime** | 1.2.0 (22 Sep; year not shown, presumably 2026) | BSD-3 | Widest set of wrappers (TSFMs including TiRex-2, deep forecasters) **plus time-series classification**. | Core is light. The `dl` extra pulls tensorflow, transformers <4.41 and gluonts, many limited to Python <3.12 or <3.13. That clashes with chronos-forecasting (transformers >=4.41). ([PyPI JSON](https://pypi.org/pypi/sktime/json)) |
| **AutoGluon-TimeSeries** | 1.6.3 (2026-09-18) | Apache-2.0 | AutoML forecasting ensembles including Chronos-2 (with LoRA fine-tuning) and deep models. Forecasting only. | Heaviest. Pins torch <2.14 (current is 2.15), transformers 5.3 to <5.15, gluonts 0.17, statsforecast, mlforecast and autogluon.tabular (CatBoost, LightGBM, XGBoost). Python 3.10-3.13. ([PyPI JSON](https://pypi.org/pypi/autogluon.timeseries/json)) |
| tsai (for reference) | 1.0.1 (2026-05-27) | Apache-2.0 | Deep time-series classification (fastai). | torch >=2.12 and <3; fastai. ([PyPI JSON](https://pypi.org/pypi/tsai/json)) |

**Cost on Windows:**
- The torch CPU wheel is 126.7 MB to download ([PyPI](https://pypi.org/project/torch/#files)). I found no figure for installed size; Inference: several hundred MB on disk with Lightning and transformers.
- Each TSFM's weights are a one-time download: TTM about 1M parameters, Chronos-2 120M, Kronos-small 24.7M, TimesFM-2.5 200M. File sizes beyond these counts were not checked.
- **Version pins do not fit in one environment:**
  - granite-tsfm needs torch <2.12, while tsai needs >=2.12;
  - AutoGluon needs torch <2.14;
  - uni2ts (Moirai) needs torch <2.5 and numpy ~1.26;
  - Sundial needs transformers ==4.40.1, while chronos needs >=4.41 and AutoGluon >=5.3.

  **Inference:** choose 2-3 backends and pin them together, or give conflicting models their own environment.

---

## 4. Rejected

**Hosted, closed or non-commercial:**
- **TimeGPT (Nixtla):** hosted API. "TimeGPT itself is closed source" and "an API key is required" ([PyPI nixtla](https://pypi.org/project/nixtla/)). Set aside.
- **TimesFM 3.0** (Aug 2026): weights under `timesfm-non-commercial-license-v1.0`, "non-commercial, non-production use" ([PyPI timesfm](https://pypi.org/project/timesfm/)).
- **Moirai 2.0 / uni2ts:** weights CC-BY-NC-4.0, "for research purposes only" ([HF](https://huggingface.co/Salesforce/moirai-2.0-R-small)). uni2ts 2.0.0 pins torch <2.5 and numpy ~1.26.

**Duplicates a shortlist slot, or too slow:**
- **TimesFM 2.5:** Apache-2.0, 200M parameters. 2.35 s per forecast on the NXAI CPU test (context 2048). The covariate extra (`xreg`) pulls `jax[cuda]`. Finance evidence is negative zero-shot (Rahimikia et al.). Duplicates the Chronos-2 slot.
- **Toto 2.0** (Datadog, May 2026): Apache-2.0, 4M to 2.5B parameters, quantiles. Claims the top GIFT-Eval ranking among foundation models ([Datadog](https://www.datadoghq.com/blog/ai/toto-2/)). Built for observability data, no finance evidence, Python >=3.12. Duplicates the Chronos-2 slot.
- **TiRex v1:** NXAI Community License; "only tested on Linux and MacOS". TiRex-2 supersedes it.

**Stale or poorly maintained:**
- **Lag-Llama:** last dated README update 2024-06-27 ([GitHub](https://github.com/time-series-foundation-models/lag-llama)). Flagged for test leakage in a 2026 comparison (secondary: [presenc.ai](https://presenc.ai/research/best-open-weight-time-series-models-2026)). Unmaintained.
- **MOMENT:** `momentfm` 0.1.4 (2025-03-19) pins transformers ==4.33.3 and numpy ==1.25.2 ([PyPI](https://pypi.org/pypi/momentfm/json)). Near-zero or negative zero-shot crypto IC in the Kronos tables.

**No usable evidence or out of reach:**
- **FinCast** (CIKM 2025): 1B parameters, Apache-2.0 per its HF README. No trading evaluation, and the pretraining cutoff was not found ([arXiv 2508.19609](https://arxiv.org/abs/2508.19609)). Per-bar CPU speed at 1B parameters is doubtful (unsourced).
- **Time-MoE:** best zero-shot crypto return IC (0.029) in the Kronos tables. I did not assess its licence or maintenance.
- **Original Chronos (T5):** gives sample paths, but Chronos-Bolt and Chronos-2 supersede it. The Base model took 1.76 s per forecast even on a T4 GPU ([Soni et al. 2026](https://arxiv.org/abs/2605.24381)).

**Deep forecasters as standalone models** (PatchTST, N-HiTS, N-BEATS, iTransformer, TFT, TiDE, TSMixer, ModernTCN):
- Their wins are on benchmarks: LTSF-Linear beats the Transformer models on 9 datasets ([Zeng et al. 2023, arXiv 2205.13504](https://arxiv.org/abs/2205.13504)).
- On hourly OHLCV their direction is about 50% (Saidd 2026).
- iTransformer was the best before costs and the worst after costs on hourly BTC (Bysik & Ślepaczuk 2026).
- Use one as the encoder inside candidate 1 if wanted, not as a separate candidate.

**Platform or data blockers:**
- **Mamba-based models:** `mamba-ssm` needs "Linux", an "NVIDIA GPU" and "CUDA 11.6+" ([GitHub](https://github.com/state-spaces/mamba)). Not usable on Windows CPU.
- **Order-book models (DeepLOB and similar):** need L2 order-book history, an extra data need. We would have to record the exchange's feed from now on, or buy history from a vendor (price not checked).
- **Pretraining our own finance TSFM from scratch:** the route that worked for Rahimikia et al. cost about 50,000 GPU hours. Not feasible.

**Not tested, or out of scope:**
- **Mantis** (ICML'26): 8M-parameter time-series classification foundation model, Apache-2.0 ([HF](https://huggingface.co/paris-noah/Mantis-8M)). It fits a classification target as a frozen encoder plus a linear head, but no finance evidence exists. A possible later add-on to candidate 1.
- **TabPFN-TS / tabular foundation models:** out of my scope (tabular), left to the other agents.

---

## 5. What I couldn't establish

- **CPU timings on the owner's PC:**
  - for Kronos sampling (none published);
  - for Chronos-2, TiRex-2 and TTM beyond the vendor tests above;
  - for training a small GRU/TCN on 26k bars. My "minutes" figure is unsourced.
- **TiRex-2 and Kronos on Windows:** whether TiRex-2's `torch.compile`, `flashrnn` and `mlstm_kernels` work on Windows without MSVC, and whether Kronos installs cleanly on Windows. Neither is documented.
- **Jaquart et al. 2022 cost assumption:** the full text was not readable, so the 3.23 after-cost Sharpe rests on the abstract alone.
- **The Wołyniak & Ślepaczuk paper:** full text, cost levels and numbers not found.
- **Effect of the Kronos leakage bug:** whether its published numbers were affected by the normalisation leak fixed in April 2026.
- **Recent pretraining cutoffs:** for TimesFM 3.0, Toto 2.0 and TiRex-2. If any includes 2025-26 crypto bars, a fine-tuning or training window that overlaps them is contaminated. The hold-out must stay after each model's release date.
- **A random-entry baseline in the literature:** no study found compares a model with random entries under fixed exits, as our gate does. The nearest is Fu et al.'s chance-rate random guesser.
- **Statistical power (not a model question, but it limits every test above; Inference):** the earlier gate run had only 6-14 entries per coin per hold-out. With so few, a small real edge (IC about 0.02-0.04 is the best reported) would rarely clear the 95th percentile of random entries. Pooling coins, or a longer hold-out, will matter more than which model is chosen.
