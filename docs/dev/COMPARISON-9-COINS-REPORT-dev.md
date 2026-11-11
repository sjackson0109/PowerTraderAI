# The nine-coin comparison: report (development months only)

**In one paragraph:**
- **Scope:** BTC, ETH, XRP, BNB, SOL, DOGE, ZEC, DASH and HYPE, on 2021-01-01 to 2025-05-06 only, at 0.50% a side plus 0.05% slippage.
- **Entry models:** none picks better entry hours than random entries by enough for the test to see. That holds for the legacy pattern model and for every model-lab model (batch 1: 14 of 14 "too few trades to tell", over about 500 trades each).
- **Whole strategies:** only the slow ones made money.
  - The daily Donchian breakout (STRAT-004) netted +$3,183 on £10,000 in 100 trades. That is better than 93% of random entries through its own exits.
  - It was still below buy-and-hold's +$3,655, with 77% of its profit from BNB and SOL.
- **Hourly strategies:** both lost money to fees.
- **What this cannot support:** these are exploration runs on months that E1 and the model lab have already used, so none of them is evidence for trading anything.

**Sources:**
- **Plan:** `COMPARISON-9-COINS-PLAN.md`, committed before any strategy result (7b62b3d).
- **Model half:** `MODEL-LAB-REPORT-batch-1.md` (88095a5).
- **Strategy half's evidence:** `docs/dev/compare-9/`, byte-exact:
  - every figure (`compare9.json`);
  - the ten saved runs;
  - the trial log;
  - the launcher.
- **Driver:** `docs/dev/run_compare9.py`.

## 1. Three tools, three questions

| | Legacy trainer (the pattern model) | Model lab (FDS-MH-001) | Strategy lab (FDS-SR-001) |
|---|---|---|---|
| What it is | The model the trader uses. It trains per coin on that coin's own history, and the trader enters when its long signal reaches 3 | A test bench. It compares entry models on the same coins and hours. It trades nothing | A test bench. It replays whole strategies in one account, with minimum orders and sell steps |
| What it varies | — | Only the entry. The exits are held at the trader's own: DCA and the trailing profit margin | The entries and the strategy's own exits |
| How it is tested | Since #224, the entry gate checks its held-out slices against random entries | Walk-forward fits, two random-entry baselines, Holm over the batch, the probability of backtest overfitting, and a lockbox | Explorations, as here, against buy-and-hold, cash and random entries. Registered experiments (E1) add families and p-values |
| In this comparison | The `pattern` contestant in batch 1, refitted every 3 months on earlier bars only | Batch 1: 14 models and the reference, on 13 coins including the nine | Ten runs: five strategies, each alone and with the 200-day filter |

**The two halves cannot be added up.**
- The model half scores entries under DCA exits, in units of a 100-unit account per coin.
- The strategy half scores whole strategies in dollars, in one £10,000 account.
- They answer different questions.

## 2. Model half: batch 1, read for the nine coins

In full in `MODEL-LAB-REPORT-batch-1.md`. In brief:

- **Every model reads "Too few trades to tell".** Nothing passes Holm over 14; the smallest p is 0.051. The probability of backtest overfitting is 0.78.
- **The legacy pattern model** made 515 trades, at +0.007% a day.
  - That puts it at the 79th percentile of random entries with the same waits, and the 62nd with those waits moved to other dates.
  - It could only have shown an edge above +0.026% a day.
- **BNB and HYPE have no walk-forward bars,** because batch 1 is declared on Coinbase, where both start inside the lockbox.
- **On the nine coins:**
  - BTC, SOL and XRP made money under almost every model.
  - DASH lost money under every model but one.
  - ZEC lost under most models.
- **The best-looking line** is BTC's close above its 50-day average. It is one line in 14, at the 95th percentile against the second baseline, so it is a lead for a declared test, not a result.

## 3. Strategy half: ten exploration runs

**The common setup:**
- each strategy at its catalogue defaults, on its own primary timeframe;
- the nine coins in one account of £10,000 ($13,476 at 1.3476);
- 0.50% a side plus 0.05% slippage;
- trades decided from 2021-01-01, with nothing read from 2025-05-06 on.

**Columns:**
- **Per capital-day:** net profit over the dollar-days of capital committed.
- **Capital in use:** the mean share of the account committed.
- **Worst drawdown:** of the account.
- **Reached the 8% halt:** when the account's drawdown first reached the trader's emergency level. The replay reports it, and carries on.

### 3.1 The strategies

| Run | Trades | Net | Per capital-day | Capital in use | Worst drawdown | Reached the 8% halt | Median days held |
|---|---|---|---|---|---|---|---|
| STRAT-000 | 2,608 | −$877 | −0.097% | 4.2% | 13.9% | 2022-09-27 | 1.5 |
| STRAT-000 + filter | 1,497 | −$72 | −0.012% | 2.6% | 8.4% | 2025-04-28 | 1.5 |
| STRAT-001 | 4,909 | −$5,064 | −1.252% | 2.3% | 39.1% | 2021-11-28 | 0.6 |
| STRAT-001 + filter | 2,793 | −$2,982 | −1.182% | 1.3% | 24.0% | 2023-05-02 | 0.6 |
| STRAT-002 | 760 | +$1,888 | +0.199% | 4.1% | 5.7% | never | 5.5 |
| STRAT-002 + filter | 427 | +$1,147 | +0.208% | 2.4% | 4.7% | never | 5.2 |
| STRAT-004 | 100 | +$3,183 | +0.608% | 2.1% | 5.7% | never | 27.0 |
| STRAT-004 + filter | 82 | +$3,475 | +0.731% | 1.9% | 5.7% | never | 29.0 |
| STRAT-005 | 109 | +$2,328 | +0.260% | 3.8% | 12.7% | 2021-05-20 | 14.0 |
| STRAT-005 + filter | 81 | +$2,332 | +0.289% | 3.4% | 12.4% | 2021-05-20 | 21.0 |

**The strategies:**
- **STRAT-000:** EMA cross 20/50, 1h.
- **STRAT-001:** TEMA 12/48 with ADX, 1h.
- **STRAT-002:** Supertrend 10 × 3, 4h.
- **STRAT-004:** Donchian breakout 55/20, daily.
- **STRAT-005:** time-series momentum 30/90/365, 2 of 3, weekly decisions, daily.

The "filter" is OVL-REGIME at its defaults: entries only while BTC's daily close is above its 200-day average.

### 3.2 Against holding and against chance

**Columns:**
- **Buy-and-hold:** one trade per coin from the run's first decidable bar, through the same account rules.
- **Random entries:** the strategy's own exits, with its waits between trades in a random order: 2,000 draws as 10 seeded runs of 200.
- **Beat:** the share of draws whose return per capital-day the strategy exceeded.

| Run | Net | Buy-and-hold net | Its per capital-day | Its capital in use | Its worst drawdown | Random entries' median net | Beat (2,000) | Beat, each run of 200 |
|---|---|---|---|---|---|---|---|---|
| STRAT-000 | −$877 | +$3,970 | +0.229% | 7.1% | 24.0% | −$2,533 | 100.0% | 100.0% to 100.0% |
| STRAT-000 + filter | −$72 | +$3,970 | +0.229% | 7.1% | 24.0% | −$1,185 | 100.0% | 100.0% to 100.0% |
| STRAT-001 | −$5,064 | +$3,961 | +0.228% | 7.1% | 24.0% | −$5,416 | 100.0% | 100.0% to 100.0% |
| STRAT-001 + filter | −$2,982 | +$3,961 | +0.228% | 7.1% | 24.0% | −$3,354 | 100.0% | 100.0% to 100.0% |
| STRAT-002 | +$1,888 | +$4,021 | +0.232% | 7.0% | 24.4% | +$214 | 96.0% | 94.0% to 98.0% |
| STRAT-002 + filter | +$1,147 | +$4,021 | +0.232% | 7.0% | 24.4% | +$331 | 57.5% | 52.5% to 66.5% |
| STRAT-004 | +$3,183 | +$3,655 | +0.213% | 7.0% | 22.2% | +$724 | 92.7% | 87.5% to 96.0% |
| STRAT-004 + filter | +$3,475 | +$3,655 | +0.213% | 7.0% | 22.2% | +$1,146 | 90.7% | 87.0% to 93.5% |
| STRAT-005 | +$2,328 | +$3,939 | +0.251% | 6.4% | 18.7% | +$1,435 | 48.2% | 43.5% to 54.5% |
| STRAT-005 + filter | +$2,332 | +$3,939 | +0.251% | 6.4% | 18.7% | +$1,244 | 56.1% | 52.0% to 60.0% |

**Beating random entries is a low bar here.** Random entries go through the strategy's own exits.
- For the hourly strategies those exits lose money for anyone: the random entries' median is −$2,533 for STRAT-000.
- So beating 100% of the draws only means the entries lose less than chance does.
- What decides is the net figure, and how it compares with holding.

### 3.3 Per coin

Net and trades per coin. BNB and HYPE come from KuCoin (§4). HYPE has bars from 2024-12-07 only.

| Run | BTC | ETH | XRP | BNB | SOL | DOGE | ZEC | DASH | HYPE |
|---|---|---|---|---|---|---|---|---|---|
| STRAT-000 | −$363 / 360 | −$201 / 342 | +$242 / 153 | +$124 / 369 | +$293 / 295 | −$224 / 341 | −$242 / 349 | −$370 / 364 | −$137 / 35 |
| STRAT-000 + filter | −$213 / 203 | −$85 / 202 | +$306 / 106 | +$224 / 227 | +$232 / 155 | −$181 / 184 | −$109 / 197 | −$68 / 194 | −$179 / 29 |
| STRAT-001 | −$728 / 678 | −$548 / 673 | −$271 / 289 | −$473 / 651 | −$680 / 600 | −$665 / 639 | −$888 / 696 | −$778 / 628 | −$33 / 55 |
| STRAT-001 + filter | −$389 / 375 | −$340 / 383 | −$262 / 214 | −$247 / 369 | −$264 / 317 | −$453 / 345 | −$516 / 398 | −$466 / 351 | −$45 / 41 |
| STRAT-002 | +$108 / 105 | −$39 / 112 | +$420 / 42 | +$551 / 110 | +$567 / 91 | +$255 / 77 | −$8 / 109 | +$55 / 105 | −$21 / 9 |
| STRAT-002 + filter | +$45 / 55 | −$29 / 64 | +$427 / 30 | +$557 / 64 | +$95 / 46 | +$78 / 40 | −$23 / 63 | +$86 / 59 | −$88 / 6 |
| STRAT-004 | +$180 / 16 | +$214 / 15 | +$236 / 7 | +$1,585 / 14 | +$869 / 11 | +$348 / 9 | −$119 / 13 | −$129 / 14 | +$0 / 1 |
| STRAT-004 + filter | +$197 / 14 | +$205 / 13 | +$240 / 7 | +$1,630 / 11 | +$917 / 9 | +$404 / 6 | −$81 / 11 | −$37 / 10 | +$0 / 1 |
| STRAT-005 | +$287 / 13 | +$167 / 17 | +$475 / 5 | +$785 / 23 | +$447 / 11 | +$93 / 14 | −$48 / 14 | +$123 / 12 | — |
| STRAT-005 + filter | +$224 / 10 | +$108 / 13 | +$481 / 4 | +$837 / 17 | +$454 / 7 | +$129 / 11 | −$57 / 9 | +$155 / 10 | — |

**Where the profit comes from:**
- **STRAT-004:** BNB and SOL give +$2,453 of its +$3,183, and the five coins listed before 2021 give +$381. E1 found the same of STRAT-004: its profit came from the coins listed after 2021.
- **ZEC and DASH lose money under almost every strategy,** as they do under most models in batch 1.

### 3.4 XRP: impossible trades across Coinbase's halt (post-hoc)

**The problem:**
- Coinbase halted XRP from 2021-01-19 to 2023-07-13, and its candles have no bars in between.
- The strategy lab joins the bars on either side of the gap, so a position open when the halt began is replayed as one trade that ends after trading resumed.
- Such a trade could not have been sold on Coinbase during the halt.
- Found after the runs, by listing each strategy's XRP trades (alone, without the filter):
  - **STRAT-000:** one such trade, 2021-01-18 to 2023-07-21.
  - **STRAT-002:** one, 2021-01-19 to 2023-07-23.
  - **STRAT-005:** two, entered 2021-01-12 and 2021-01-19, both ending 2024-08-06.
  - **STRAT-001 and STRAT-004:** none.
- The model lab ends a series at any gap longer than 24 hours, so batch 1's XRP starts on 2023-07-13 and is unaffected.

**The plan (§5) said to use the bars the layer serves.** So the figures above stand as run, with XRP's lines read with this in mind. Without XRP, each run's net changes as below. This is a reading added after the results: the account replays were not re-run.

| Run | Net | XRP | Without XRP |
|---|---|---|---|
| STRAT-000 | −$877 | +$242 | −$1,120 |
| STRAT-000 + filter | −$72 | +$306 | −$378 |
| STRAT-001 | −$5,064 | −$271 | −$4,793 |
| STRAT-001 + filter | −$2,982 | −$262 | −$2,720 |
| STRAT-002 | +$1,888 | +$420 | +$1,468 |
| STRAT-002 + filter | +$1,147 | +$427 | +$721 |
| STRAT-004 | +$3,183 | +$236 | +$2,947 |
| STRAT-004 + filter | +$3,475 | +$240 | +$3,235 |
| STRAT-005 | +$2,328 | +$475 | +$1,853 |
| STRAT-005 + filter | +$2,332 | +$481 | +$1,851 |

**The order of the strategies does not change.** The random entries may also hold such trades, which this does not correct.

## 4. Data

- **Exchanges:** in the shipped template's order (Coinbase, Kraken, KuCoin, Binance), with the plan's one rule: an exchange whose series starts after 2025-05-06 is passed over.
  - **BNB and HYPE:** Coinbase's series start on 2025-10-22 and 2026-02-05. Kraken serves only its latest 720 bars at each size used here. So both came from KuCoin, as BNB-USDT and HYPE-USDT: priced in USDT, not USD, for every timeframe.
  - **The other seven:** from Coinbase.
  - Each run's `sources` records this.
- **HYPE:** KuCoin's bars start on 2024-12-07, which gives about five months. STRAT-005's 365-day lookback leaves it no trades. STRAT-004's 55-day breakout gives it one trade.
- **Minimum orders and sell steps** are today's, read from the exchange layer at run time ($1 minimum for each coin).

## 5. How the runs were made, and where they differ from the plan

| Point | What happened | Effect on the figures |
|---|---|---|
| A bug in the app | `strategy_lab.simulate.load_universe` stops every run with OVL-REGIME (a tz-aware start), in the app's "Run a backtest…" too. The driver passes the same instant without a zone (`naive_start`). The app's fix is a separate PR, #256 | None: the candle layer reads a naive time as UTC |
| The ten seeds | Seed 700000's run is the app's own `runs.run`, saved. The ten seeds are drawn on one simulation of the same config, which must reproduce that saved run's figures exactly. Drawing each seed as a full run took about 47 minutes a seed with an overlay | None. For STRAT-000, all ten seeds matched ten full runs exactly |
| The pooled draws | Reported exactly, from all 2,000 draws. The plan had expected only the 10 runs' figures | More exact than planned |
| Two processes | The last seven runs were shared between two processes, with disjoint strategies | None |
| Restarts | The first launch stopped on a driver bug, before anything was saved. The second saved STRAT-000's run, then stopped on the app bug. The third stopped when Windows' temporary-file cleanup removed the scratch Python environment's files, and the environment was rebuilt with the same package versions. The fourth saved the filtered STRAT-000 run and was stopped to move to one simulation per run. The fifth was stopped to share the rest between two processes. A run saved by an earlier launch was reused only after it was reproduced exactly, and none was saved twice | None |
| XRP without its halt | §3.4, a reading added after the results | Shown beside the figures, not instead of them |

**Trials:** the strategy lab's trial log (`compare-9/trials.jsonl`) holds E1's 46 lines and this comparison's 10 explorations, one per saved run.

## 6. What can and cannot be read from this

**Can be read:**
- **At 0.50% a side, frequent trading loses.**
  - STRAT-000 and STRAT-001 trade 1,500 to 4,900 times.
  - STRAT-001 loses on every coin, and STRAT-000 on six of nine, with or without the filter.
  - STRAT-001 alone reached the 8% halt level in November 2021, and fell 39%.
- **The slow strategies make money in these months,** but none beats holding the nine coins in net.
  - STRAT-004, STRAT-002 and STRAT-005 net +$1,147 to +$3,475, against buy-and-hold's +$3,655 to +$4,021.
  - They do it with 27% to 59% of holding's capital in use, and with drawdowns of 4.7% to 12.7% against holding's 18.7% to 24.4%.
- **STRAT-004 has the best return per capital-day of any run** (+0.61%, or +0.73% with the filter, against holding's +0.21%). It beats 91% to 93% of its random entries.
  - Its profit rests on BNB and SOL, and on 82 to 100 trades.
  - This agrees with E1's registered S1 (STRAT-004 beats random entries, p = 0.0065), and with E1's finding that the gain comes from the coins listed later.
- **The 200-day filter:**
  - It cuts trades by 18% to 44%.
  - It narrows the hourly strategies' losses.
  - It adds about 9% to STRAT-004's net.
  - It removes most of STRAT-002's lead over random entries (from 96% to 58%).
  - It barely changes STRAT-005's net, which already reads the market's direction itself.
- **Time-series momentum (STRAT-005) makes money but is no better than its random entries** (48% and 56%). E1's S2 read "too few trades to tell".

**Cannot be read:**
- **Whether any of this would hold in other months.**
  - The development months include one bear market (2022) and its recovery.
  - These months were used by E1 and by the model lab already.
  - The runs are explorations, with no correction for the 10 runs.
- **Anything about BNB beyond KuCoin's USDT prices,** or about HYPE beyond five months.
- **Anything at other fees.** Every run is at 0.50% a side, the owner's account rate. At a maker or lower-tier rate the hourly strategies would lose less.

## 7. Seeing these in the app

- **Where the runs live:** in a scratch sandbox, because nothing may write into the real user folders.
- **To see them in the app:**
  - **Strategy runs:** run each from Settings > Strategy > "Run a backtest…" with the same choices. They then appear in "Compare results…".
    - The 200-day filter must first be enabled for research, and needs #256 before that run works.
    - There, BNB and HYPE are read from Coinbase, the primary, which has no bars for them in these months, unless another exchange is put first in Settings > Exchanges.
  - **Batch 1:** run it from Settings > Training > "Compare models…" with "Tick batch 1" once #255 is merged. It reads its candles through the exchange layer, Coinbase first, and each coin's fee as the exchange states it. On the same candles and fee it gives the same figures.

## 8. Follow-ups, for the owner to decide

1. **#256:** the fix for the OVL-REGIME crash, which also affects the paper observation. It changes `strategy_lab`'s code hash, so E1's `verify` will report it, as it did for #252.
2. **The strategy lab and long gaps.** A series could end at any gap longer than a day, as the model lab's does, so that a halt cannot make an impossible trade. Not built.
3. **BTC's 50-day trend** (batch 1) and **STRAT-004 with the filter** (here) are the two lines worth a declared test.
   - FDS-SR-001's Section 8 restriction still stands: no new experiment is registered before the revised method is reviewed.
   - No tuning was done on these figures.
4. **Mean reversion (RSI(2))** is the published family the catalogue lacks. It is a small addition, if wanted.
