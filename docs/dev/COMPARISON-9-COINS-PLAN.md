# The nine-coin comparison: plan, written before any result

**Status:** written and committed on 2026-11-10, before any strategy run of this comparison. The model half is batch 1, declared in FDS-MH-001 §7 on 2026-11-06 and frozen on 2026-11-10 at 23:26Z (`docs/dev/run_mh_batch1.py`). This plan does not change it.

**Authority:**
- **Scope (owner, 2026-11-08):**
  - nine coins: ZEC, XRP, BNB, SOL, ETH, HYPE, DOGE, DASH and BTC;
  - both the model lab and the legacy trainer, "distinguishing their purposes and capabilities";
  - "all existing strategies and relevant published alternatives";
  - the development dataset only, with the lockbox closed;
  - "a tightly scoped investigation, not another large architecture programme".
- **The details below:** the owner left them to me on 2026-11-10 ("you decide").

## 1. The question

On the development months (2021-01-01 to 2025-05-06), and for these nine coins, how do the entry models and the strategies compare in plain figures? Each is set against random entries, buy-and-hold and cash.

## 2. What this is not

- **Not a registered experiment.** It has no pass rule, no p-values on the strategy half and no families.
  - E1 (FDS-SR-001) is the registered evidence for STRAT-004 and STRAT-005.
  - Batch 1's own report carries the model half's declared verdicts.
- **No tuning.** Every strategy runs at its catalogue defaults, and every model as batch 1 declares it. Nothing is re-run with other values after a result is seen.
- **Nothing is enabled, promoted or registered.** No setting, strategy, model or gate changes.
- **No reserved months are read.** That means nothing from 2025-05-06 on: not the lockbox (2025-05-06 to 2026-11-06), and not the months after it.
- **Its figures cannot by themselves support a trading decision.**

## 3. The two halves, and what each can say

| | Model half: the model lab, batch 1 | Strategy half: the strategy lab, "Run a backtest…" |
|---|---|---|
| What varies | The entry: which hours to buy | The whole strategy: its entries and its own exits |
| What is fixed | The trader's own exits: DCA and the trailing profit margin, with neural DCA off | One account of £10,000 over the coins, with today's minimum orders and sell steps |
| Models and strategies | 14 entry models and the reference. Among them is **the legacy trainer's pattern model**, fitted walk-forward: each fold is fitted only on bars before it | STRAT-000, 001, 002, 004 and 005, each alone and with the 200-day market filter (§4) |
| Compared with | Random entries with the same waits, and the same waits moved to other dates (10,000 draws each) | Buy-and-hold, cash, and random entries replayed through the strategy's own exits |
| What it can say | Whether a model picks better hours than chance, under these exits only | What each strategy would have done here, against holding and against chance |
| What it cannot say | Anything about other exits | Whether a result would hold out of sample: these runs are exploration, and not evidence |
| Coins | Batch 1's 13. The nine are read from its per-coin lines | The nine, in one account |

## 4. Strategies

Every strategy runs at its catalogue defaults, on its own primary timeframe.

| Strategy | Defaults | Published form |
|---|---|---|
| STRAT-000, EMA cross | 20/50, 1h | The moving-average crossover |
| STRAT-001, trend crossover | TEMA 12/48, persistence 2, ADX(14) ≥ 20, 1h | — |
| STRAT-002, Supertrend | ATR 10 × 3, 1 confirm bar, 4h | — |
| STRAT-004, Donchian breakout | Enter on a 55-day closing high, exit on a 20-day closing low, 1d | The channel breakout (the "Turtle" rules) |
| STRAT-005, time-series momentum | 30, 90 and 365-day returns, 2 of 3 positive, weekly decisions, 1d | Moskowitz, Ooi and Pedersen (2012); in crypto, Liu and Tsyvinski (2021) |

**Each strategy has two runs:**
- **alone;**
- **with OVL-REGIME at its defaults:** entries only while BTC's daily close is above its 200-day average. This is the published trend filter (Faber, 2007).

That is 10 runs.

**Not run here:**
- **STRAT-003, the legacy pattern model as a strategy.** It runs one published model file. A file fitted today and replayed over 2021 to 2025 would make one fit stand in for years of retraining, and it could include bars from these months.
  - The legacy trainer is compared fairly in the model half. There, batch 1's `pattern` contestant is the trainer's own fit, refitted every 3 months on earlier bars only.
- **Published alternatives the catalogue does not have:**
  - **Short-horizon mean reversion (Connors' RSI(2)).** This would be a small addition, and only if the owner asks for it.
  - **Cross-sectional momentum (Liu, Tsyvinski and Wu, 2022).** It ranks coins against each other and rebalances a portfolio, which the lab does not do. Building that would be the larger programme the owner ruled out.

## 5. Data

- **Candles** come through the exchange layer, in Settings order. The sandbox uses the shipped template: Coinbase first, then the others.
  - **One rule for late listings:** an exchange whose series for a coin starts after 2025-05-06 is passed over for that coin, so the next exchange in Settings order serves it. This is for BNB and HYPE: on Coinbase they start on 2025-10-22 and 2026-02-05, after the period ends.
  - Each run records which exchange served each coin.
- **Warm-up** is read from before 2021 where a strategy needs it, but never before 2020-01-01.
- **Late coins** join when their bars start:
  - SOL and DOGE in 2021-06, and ZEC in 2020-12, on Coinbase;
  - HYPE late in 2024 at the earliest, so at most about five months. STRAT-005's 365-day lookback leaves it no decisions.
- **XRP:** Coinbase halted XRP from 2021-01-19 to 2023-07-13.
  - The model half's XRP starts on 2023-07-13 (batch 1's rule).
  - The strategy half uses whatever bars the layer serves, and the report says which months XRP covers.

## 6. Costs and account

- **Fees:** 0.50% a side (the owner's account rate) plus 0.05% slippage.
- **Account:** £10,000 at a fixed GBP/USD rate of 1.3476 (BoE XUDLUSS for 2026-11-05, as E1 used).
- **Both halves use the same fee.**

## 7. Random entries: 10 seeded runs

- **The strategy half:** each strategy's random entries are drawn as 10 seeded runs of 200 draws, with seeds 700000 + 1000 k for k = 0 to 9.
  - Run k = 0 is saved, as the app's "Run a backtest…" saves one.
  - Runs 1 to 9 differ only in their random draws, because a strategy's own trades do not depend on a seed. They are reported, not saved.
  - The report gives each run's figures and the pooled 2,000 draws.
- **The model half:** batch 1's 10,000 draws are already reported as 10 runs of 1,000 (FDS-MH-001 amendment 1).

## 8. What the report shows

The report is `docs/dev/COMPARISON-9-COINS-REPORT-dev.md`, with the runs in `docs/dev/compare-9/`. It shows:

- **For each strategy run:**
  - trades;
  - net profit;
  - return per capital-day;
  - worst drawdown;
  - time in the market;
  - buy-and-hold over the same coins and months;
  - the random entries' median;
  - the share of random draws the strategy beat, per run and pooled;
  - its per-coin trades and profit.
- **For each model:** batch 1's figures and verdicts, with its per-coin lines for the nine coins.
- **One plain paragraph** on what was found, with its limits in the same sentences:
  - the number of trades;
  - the base rates;
  - that this is exploration on development months only.

**No figure is called a pass or a fail,** and there are no p-values on the strategy half.

## 9. Results in the app

- Both halves run in a scratch sandbox, because nothing may write into the real user folders.
- **Results are committed in `docs/dev/`.**
- **The runs are deterministic.** To see them in the app's "Compare models…" and "Compare results…", run them from those windows with the same choices. The same candles give the same figures.
