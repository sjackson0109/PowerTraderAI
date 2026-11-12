# The nine-coin comparison at $500 and $50: report (development months only)

**In one paragraph:**
- **Scope:** the same ten strategy runs as the £10,000 comparison (`COMPARISON-9-COINS-REPORT-dev.md`), at a $500 and a $50 account. They cover BTC, ETH, XRP, BNB, SOL, DOGE, ZEC, DASH and HYPE, on 2021-01-01 to 2025-05-06 only, at 0.50% a side plus 0.05% slippage.
- **$500 is £10,000 in miniature.** Counting the coins a sale leaves unsold, every run ends within 0.3 points of its £10,000 share. The ranking is the same: STRAT-004 (Donchian breakout) is the best strategy, and it is still below buy-and-hold.
- **$50 is below the size the 1% rule works at.**
  - 1% of $50 is under Coinbase's $1 minimum order, so every entry is raised to $1.031, about 2% of the start, and stays that size.
  - Gains and losses roughly double as shares, and buy-and-hold's do too, so the ranking does not change.
  - **Every run reaches the 8% emergency-halt level,** six of the ten in 2021, the first year. The trader would have halted each of them.
  - The hourly STRAT-001 loses 83% of the account.
- **What this cannot support:** these are exploration runs on months that E1 and the model lab have already used, so none of them is evidence for trading anything. The account size changes how large the swings are, not which strategy does best.

**Sources:**
- **Plan:** `COMPARISON-9-COINS-PLAN-accounts.md`, committed and pushed before any run at these sizes (cde4915). Its expectations are checked in §5.
- **Driver:** `docs/dev/run_compare9_accounts.py`.
- **Evidence:** `docs/dev/compare-9/accounts/`, byte-exact:
  - every figure, per size (`500/compare9.json`, `50/compare9.json`);
  - the twenty saved runs;
  - the trial log;
  - the launcher.

## 1. Why the account size matters at all

The fee is a percentage, so on its own it scales with the account. Three rules do not scale, and they decide everything in this report. They are the replay's rules (`signal_fusion/evaluation/replay.py`, `position_sizing.py`), the same as the trader's defaults:

- **Entry size:** an entry is 1% of the account's value at that moment. No coin may hold more than 10%.
- **Minimum entry:** an entry below the minimum entry is raised to it. The minimum entry is Coinbase's $1 minimum order with room for the fees, the slippage and a 2% margin: **$1.031**.
- **Coin steps:** a sale is rounded down to the coin's step (DOGE 0.1, HYPE 0.001, BNB 0.00001). The part below one step stays in the account as unsold coins.

What that means at each size:

| Account | 1% entry | What happens |
|---|---|---|
| £10,000 ($13,476) | $134.76 | Entries grow and shrink with the account |
| $500 (£371.03) | $5.00 | The same, unless the account fell below $103.10, which no run did |
| $50 (£37.10) | $0.50 | Below the minimum, so every entry is $1.031. That is about 2.1% of the start, and it does not shrink when the account does |

## 2. At $500

| Run | Trades | Net | Value at the end | Worst drawdown | Reached the 8% halt | Buy-and-hold net | Random entries' median net | Beat (2,000 draws) |
|---|---|---|---|---|---|---|---|---|
| STRAT-000 | 2,608 | −$36 | $468.45 | 13.8% | 2022-06-20 | +$147 | −$97 | 100.0% |
| STRAT-000 + OVL-REGIME | 1,497 | −$5 | $497.65 | 8.3% | 2025-04-28 | +$147 | −$46 | 100.0% |
| STRAT-001 | 4,909 | −$194 | $314.00 | 39.0% | 2021-11-28 | +$147 | −$206 | 100.0% |
| STRAT-001 + OVL-REGIME | 2,793 | −$115 | $390.00 | 23.9% | 2023-04-28 | +$147 | −$128 | 100.0% |
| STRAT-002 | 760 | +$69 | $570.29 | 5.8% | never | +$149 | +$7 | 96.4% |
| STRAT-002 + OVL-REGIME | 427 | +$42 | $542.69 | 4.8% | never | +$149 | +$12 | 58.5% |
| STRAT-004 | 100 | +$118 | $618.14 | 5.7% | never | +$136 | +$27 | 92.6% |
| STRAT-004 + OVL-REGIME | 82 | +$129 | $628.94 | 5.7% | never | +$136 | +$42 | 90.8% |
| STRAT-005 | 109 | +$86 | $586.48 | 12.7% | 2021-05-20 | +$146 | +$53 | 48.2% |
| STRAT-005 + OVL-REGIME | 81 | +$86 | $586.60 | 12.4% | 2021-05-20 | +$146 | +$46 | 56.1% |

How to read the columns:
- **Net** is the profit realised in trades.
- **Value at the end** adds the unsold coins at their last price.
- **Buy-and-hold** buys every coin once, by the same sizing rules, and sells at the end.
- **Beat** is the share of 2,000 random-entry draws (10 seeds of 200) with a lower return per capital-day, each draw replayed through the strategy's own exits.

Buy-and-hold also reaches the 8% level, in May 2021, at this size and at £10,000.

## 3. At $50

| Run | Trades | Net | Value at the end | Worst drawdown | Reached the 8% halt | Skipped for want of cash | Buy-and-hold net | Random entries' median net | Beat (2,000 draws) |
|---|---|---|---|---|---|---|---|---|---|
| STRAT-000 | 2,608 | −$10.23 | $44.34 | 25.6% | 2022-01-31 | 0 | +$30.02 | −$24.45 | 100.0% |
| STRAT-000 + OVL-REGIME | 1,497 | −$2.71 | $50.03 | 14.9% | 2023-03-28 | 0 | +$30.02 | −$11.41 | 100.0% |
| STRAT-001 | 4,495 | −$48.98 | $8.48 | 86.7% | 2021-06-21 | 414 | +$29.99 | −$48.98 | 100.0% |
| STRAT-001 + OVL-REGIME | 2,793 | −$29.69 | $24.99 | 53.7% | 2021-10-07 | 0 | +$29.99 | −$33.14 | 100.0% |
| STRAT-002 | 760 | +$13.41 | $64.53 | 10.3% | 2022-10-14 | 0 | +$30.37 | +$1.13 | 97.2% |
| STRAT-002 + OVL-REGIME | 427 | +$8.46 | $59.05 | 8.6% | 2023-06-07 | 0 | +$30.37 | +$2.19 | 62.5% |
| STRAT-004 | 100 | +$22.76 | $72.88 | 9.8% | 2021-03-01 | 0 | +$27.71 | +$5.46 | 91.9% |
| STRAT-004 + OVL-REGIME | 82 | +$24.54 | $74.64 | 9.7% | 2021-03-01 | 0 | +$27.71 | +$8.84 | 89.3% |
| STRAT-005 | 109 | +$16.90 | $67.10 | 21.8% | 2021-03-01 | 0 | +$30.10 | +$10.67 | 48.6% |
| STRAT-005 + OVL-REGIME | 81 | +$16.93 | $67.08 | 21.2% | 2021-03-01 | 0 | +$30.10 | +$9.31 | 55.4% |

- **STRAT-001 runs out of money.** Its account fell below what nine $1.031 entries need, and 414 entries were skipped for want of cash. Its random entries run out the same way: their median loss is within a cent of its own.
- **Buy-and-hold at $50** reaches the 8% level in February 2021, with a 31% to 39% worst drawdown. Its nine entries are $1.031 each, so it holds about 19% of the start rather than about 9%.

## 4. The three sizes side by side, as shares of the start

| Run | Size | Trades | Net | Value at the end | Worst drawdown | Reached the 8% halt | Skipped for want of cash | Buy-and-hold net | Beat (2,000 draws) |
|---|---|---|---|---|---|---|---|---|---|
| STRAT-000 | £10,000 | 2,608 | −6.5% | −6.5% | 13.9% | 2022-09-27 | 0 | +29.5% | 100.0% |
| STRAT-000 | $500 | 2,608 | −7.2% | −6.3% | 13.8% | 2022-06-20 | 0 | +29.5% | 100.0% |
| STRAT-000 | $50 | 2,608 | −20.5% | −11.3% | 25.6% | 2022-01-31 | 0 | +60.0% | 100.0% |
| STRAT-000 + OVL-REGIME | £10,000 | 1,497 | −0.5% | −0.5% | 8.4% | 2025-04-28 | 0 | +29.5% | 100.0% |
| STRAT-000 + OVL-REGIME | $500 | 1,497 | −1.0% | −0.5% | 8.3% | 2025-04-28 | 0 | +29.5% | 100.0% |
| STRAT-000 + OVL-REGIME | $50 | 1,497 | −5.4% | +0.1% | 14.9% | 2023-03-28 | 0 | +60.0% | 100.0% |
| STRAT-001 | £10,000 | 4,909 | −37.6% | −37.5% | 39.1% | 2021-11-28 | 0 | +29.4% | 100.0% |
| STRAT-001 | $500 | 4,909 | −38.8% | −37.2% | 39.0% | 2021-11-28 | 0 | +29.4% | 100.0% |
| STRAT-001 | $50 | 4,495 | −98.0% | −83.0% | 86.7% | 2021-06-21 | 414 | +60.0% | 100.0% |
| STRAT-001 + OVL-REGIME | £10,000 | 2,793 | −22.1% | −22.1% | 24.0% | 2023-05-02 | 0 | +29.4% | 100.0% |
| STRAT-001 + OVL-REGIME | $500 | 2,793 | −22.9% | −22.0% | 23.9% | 2023-04-28 | 0 | +29.4% | 100.0% |
| STRAT-001 + OVL-REGIME | $50 | 2,793 | −59.4% | −50.0% | 53.7% | 2021-10-07 | 0 | +60.0% | 100.0% |
| STRAT-002 | £10,000 | 760 | +14.0% | +14.0% | 5.7% | never | 0 | +29.8% | 96.0% |
| STRAT-002 | $500 | 760 | +13.8% | +14.1% | 5.8% | never | 0 | +29.8% | 96.4% |
| STRAT-002 | $50 | 760 | +26.8% | +29.1% | 10.3% | 2022-10-14 | 0 | +60.7% | 97.2% |
| STRAT-002 + OVL-REGIME | £10,000 | 427 | +8.5% | +8.5% | 4.7% | never | 0 | +29.8% | 57.5% |
| STRAT-002 + OVL-REGIME | $500 | 427 | +8.4% | +8.5% | 4.8% | never | 0 | +29.8% | 58.5% |
| STRAT-002 + OVL-REGIME | $50 | 427 | +16.9% | +18.1% | 8.6% | 2023-06-07 | 0 | +60.7% | 62.5% |
| STRAT-004 | £10,000 | 100 | +23.6% | +23.6% | 5.7% | never | 0 | +27.1% | 92.7% |
| STRAT-004 | $500 | 100 | +23.6% | +23.6% | 5.7% | never | 0 | +27.1% | 92.6% |
| STRAT-004 | $50 | 100 | +45.5% | +45.8% | 9.8% | 2021-03-01 | 0 | +55.4% | 91.9% |
| STRAT-004 + OVL-REGIME | £10,000 | 82 | +25.8% | +25.8% | 5.7% | never | 0 | +27.1% | 90.7% |
| STRAT-004 + OVL-REGIME | $500 | 82 | +25.8% | +25.8% | 5.7% | never | 0 | +27.1% | 90.8% |
| STRAT-004 + OVL-REGIME | $50 | 82 | +49.1% | +49.3% | 9.7% | 2021-03-01 | 0 | +55.4% | 89.3% |
| STRAT-005 | £10,000 | 109 | +17.3% | +17.3% | 12.7% | 2021-05-20 | 0 | +29.2% | 48.2% |
| STRAT-005 | $500 | 109 | +17.3% | +17.3% | 12.7% | 2021-05-20 | 0 | +29.2% | 48.2% |
| STRAT-005 | $50 | 109 | +33.8% | +34.2% | 21.8% | 2021-03-01 | 0 | +60.2% | 48.6% |
| STRAT-005 + OVL-REGIME | £10,000 | 81 | +17.3% | +17.3% | 12.4% | 2021-05-20 | 0 | +29.2% | 56.1% |
| STRAT-005 + OVL-REGIME | $500 | 81 | +17.3% | +17.3% | 12.4% | 2021-05-20 | 0 | +29.2% | 56.1% |
| STRAT-005 + OVL-REGIME | $50 | 81 | +33.9% | +34.2% | 21.2% | 2021-03-01 | 0 | +60.2% | 55.4% |

## 5. Against the plan's expectations

The plan (§2) predicted the results from the sizing rules before anything ran.

**$500: "every dollar figure should be the £10,000 run's × 0.0371".**
- **Held, once unsold coins are counted.** Every run's value at the end is within 0.3 points of its £10,000 share. Trades, drawdowns and the share of random draws beaten are the same, or within 1.5 points for beaten draws.
- **The departure is in net profit, and only for the busy strategies.**

  | Run | Net at $500 ÷ (net at £10,000 × 0.0371) |
  |---|---|
  | STRAT-000 | 1.109 (11% more loss) |
  | STRAT-000 + OVL-REGIME | 1.907 (−$5.13 against −$2.69; $2.78 left unsold) |
  | STRAT-001 | 1.033 |
  | STRAT-001 + OVL-REGIME | 1.036 |
  | STRAT-002, alone and with the filter | 0.988 |
  | STRAT-004 and STRAT-005, alone and with the filter | 0.999 to 1.000 |

  - **Cause:** the plan named it. A sale is rounded down to the coin's step, and the part below one step is left unsold. That part is bounded by the step, not by the position, so it weighs more on a $5 position than on a $135 one.
  - **STRAT-000 at $500:** its 2,608 trades left $4.54 of coins unsold, mostly DOGE (step 0.1), then BNB and HYPE. The same trades at £10,000 left $4.52, which is 0.03% of that account.
  - **Counting those coins,** STRAT-000's value at the end is −6.3% at $500 against −6.5% at £10,000.
  - **In practice,** the leftover coins are not lost. The replay never sells them, but a later sale of the whole balance would.

**$50: "entries about twice the usual share".**

| Plan's expectation | What happened |
|---|---|
| Drawdowns and capital in use at about twice the share | Drawdowns 1.7 to 2.2 times the £10,000 run's. Capital in use 1.6 to 2.7 times, and 4.0 times for STRAT-001, whose account shrank under fixed-size entries |
| Profitable strategies about twice the share | STRAT-002 ×1.9, STRAT-004 ×1.9, STRAT-005 ×2.0. Buy-and-hold ×2.0 too (+55% to +61% against +27% to +30%) |
| Losing strategies about twice the share | More than twice in net: STRAT-000 −20.5% against −6.5%, STRAT-001 + OVL-REGIME −59.4% against −22.1%. In value at the end, about twice: −11.3% against −6.5%, and −50.0% against −22.1%. STRAT-000 + OVL-REGIME nets −5.4% against −0.5%, but its value at the end is +0.1%: $2.74 of its $50 sits in unsold coins. The entries stay $1.031 as the account falls, so each loss is a growing share of what is left. STRAT-001 is capped by running out of cash: −83.0% in value |
| The 8% halt reached sooner | Yes. All ten runs reach it at $50. At £10,000, four of the ten never did: STRAT-002 and STRAT-004, each alone and with the filter. Six of the ten $50 runs reach it in 2021 |
| The DOGE and HYPE rounding weighs more | Yes. STRAT-000 leaves $4.57 unsold at $50, which is 9% of the start; STRAT-001 leaves $7.46 |

## 6. The 8% halt

The replay reports the halt but does not model it: a halted account in the app waits for its owner, which a replay cannot know.

At £10,000 and $500, the halt level is reached by:
- the four hourly runs;
- STRAT-005, alone and with the filter, in May 2021;
- buy-and-hold, in May 2021.

STRAT-002 and STRAT-004 never reach it.

At $50 every run reaches it, buy-and-hold in February 2021 and STRAT-004 on 2021-03-01. So **at $50, the trader's emergency halt (8% by default, `risk.emergency_drawdown_pct`) would have stopped every strategy here, six of them in 2021.** The figures after that date are what the account would have done had the owner resumed it each time.

## 7. How the runs were made

- **Sandbox:** the first comparison's, with no real user folders, no keys and Coinbase first in Settings order. BNB and HYPE come from KuCoin under the plan's late-listing rule.
- **One shared simulation per strategy run.** A strategy's trades, and its random entries' trades, do not depend on the account, so each run's simulation was built once and used by all three sizes.
- **The check came first:** on that shared simulation, the £10,000 figures had to equal the first comparison's saved figures, including every one of the ten seeds and the pooled draws. All ten runs passed, so sharing changed no figure.
- **Each size's seed-700000 run is `strategy_lab.runs.run`'s own,** saved as the app saves a run. The other nine seeds were drawn as in the first comparison.
- **Trial log:** 20 new exploration lines, 76 in all. That is E1's 46, the first comparison's 10 and these 20.
- **Restarts:** none. STRAT-004 ran first, alone, as a check; then three workers ran the other strategies.

## 8. Agreement with E1's account sizes

E1 (`docs/dev/sr1-e1/SR1-E1-REPORT-dev.md`, §4) also replayed each strategy at £500 ($673.80) and £50 ($67.38), on its own 13 coins. It found the same pattern:
- £500 is close to £10,000 in share for the slow strategies. The busy ones lose more there, as here: STRAT-000 −18.6% against −14.4%;
- at £50, every entry was raised to the minimum: 3,535 of STRAT-000's 3,535;
- at £50, STRAT-001 lost 98.5% of the account, with 3,852 entries skipped for want of cash.

## 9. What can and cannot be read from this

**Can be read:**
- **At $500, the strategies compare as at £10,000.** The only effect of the size is the leftover coins on the busiest strategies.
- **At $50, the minimum order sets the trade size, not the 1% rule.** Each trade then risks about 2% of the start, and every run here, buy-and-hold included, falls 8% at some point, six of the ten in 2021.
- **The ranking does not change with the size.** STRAT-004 is the best strategy at all three sizes, and below buy-and-hold at all three.

**Cannot be read:**
- **That any strategy works.** These are explorations on development months that E1 and the model lab have already used. No figure here is a test, and none is evidence for trading anything.
- **What a halted $50 account would do.** The replay keeps trading after the 8% level. The trader would stop.

## 10. Seeing these in the app

The runs are deterministic. In Settings > Strategy, "Run a backtest…":
1. choose the strategy (the list now shows each ID);
2. tick the nine coins;
3. set the period 2021-01-01 to 2025-05-06;
4. set **Account (£)** to 371.03 or 37.10 and the rate to 1.3476;
5. set the fee to 0.50% and the slippage to 0.05%;
6. tick "Market regime filter" for the filtered runs. It must first be enabled for research in the strategy list; #256, now merged, lets those runs start.

The runs then appear in "Compare results…".

**One difference:** the app reads BNB and HYPE from Coinbase, the primary exchange, which has no bars for them in these months. So those two coins differ unless another exchange is put first in Settings > Exchanges. On the same candles, the figures are the same.

## Appendix: per coin (net / trades)

The coins' shares are as at £10,000. STRAT-004's profit is 77% from BNB and SOL at $500, and 79% at $50.

**At $500:**

| Run | BTC | ETH | XRP | BNB | SOL | DOGE | ZEC | DASH | HYPE |
|---|---|---|---|---|---|---|---|---|---|
| STRAT-000 | −$13.56 / 360 | −$7.47 / 342 | +$9.01 / 153 | +$3.86 / 369 | +$10.84 / 295 | −$10.63 / 341 | −$8.98 / 349 | −$13.69 / 364 | −$5.47 / 35 |
| STRAT-000 + OVL-REGIME | −$7.96 / 203 | −$3.18 / 202 | +$11.35 / 106 | +$7.81 / 227 | +$8.61 / 155 | −$8.14 / 184 | −$4.04 / 197 | −$2.53 / 194 | −$7.06 / 29 |
| STRAT-001 | −$27.17 / 678 | −$20.39 / 673 | −$10.09 / 289 | −$18.85 / 651 | −$25.25 / 600 | −$28.71 / 639 | −$32.97 / 696 | −$28.89 / 628 | −$1.70 / 55 |
| STRAT-001 + OVL-REGIME | −$14.56 / 375 | −$12.65 / 383 | −$9.73 / 214 | −$9.98 / 369 | −$9.80 / 317 | −$19.33 / 345 | −$19.16 / 398 | −$17.30 / 351 | −$2.08 / 41 |
| STRAT-002 | +$4.00 / 105 | −$1.44 / 112 | +$15.58 / 42 | +$20.26 / 110 | +$21.02 / 91 | +$8.92 / 77 | −$0.31 / 109 | +$2.06 / 105 | −$0.86 / 9 |
| STRAT-002 + OVL-REGIME | +$1.66 / 55 | −$1.06 / 64 | +$15.84 / 30 | +$20.52 / 64 | +$3.51 / 46 | +$2.60 / 40 | −$0.87 / 63 | +$3.20 / 59 | −$3.33 / 6 |
| STRAT-004 | +$6.66 / 16 | +$7.95 / 15 | +$8.76 / 7 | +$58.78 / 14 | +$32.23 / 11 | +$12.83 / 9 | −$4.43 / 13 | −$4.80 / 14 | −$0.01 / 1 |
| STRAT-004 + OVL-REGIME | +$7.32 / 14 | +$7.62 / 13 | +$8.91 / 7 | +$60.46 / 11 | +$34.01 / 9 | +$14.94 / 6 | −$3.01 / 11 | −$1.38 / 10 | +$0.01 / 1 |
| STRAT-005 | +$10.63 / 13 | +$6.19 / 17 | +$17.62 / 5 | +$29.07 / 23 | +$16.57 / 11 | +$3.40 / 14 | −$1.78 / 14 | +$4.58 / 12 | — |
| STRAT-005 + OVL-REGIME | +$8.32 / 10 | +$4.01 / 13 | +$17.86 / 4 | +$31.02 / 17 | +$16.85 / 7 | +$4.73 / 11 | −$2.12 / 9 | +$5.77 / 10 | — |

**At $50:**

| Run | BTC | ETH | XRP | BNB | SOL | DOGE | ZEC | DASH | HYPE |
|---|---|---|---|---|---|---|---|---|---|
| STRAT-000 | −$2.80 / 360 | −$1.54 / 342 | +$1.84 / 153 | +$0.15 / 369 | +$2.20 / 295 | −$3.90 / 341 | −$1.89 / 349 | −$2.83 / 364 | −$1.46 / 35 |
| STRAT-000 + OVL-REGIME | −$1.60 / 203 | −$0.61 / 202 | +$2.33 / 106 | +$1.22 / 227 | +$1.70 / 155 | −$2.76 / 184 | −$0.81 / 197 | −$0.49 / 194 | −$1.69 / 29 |
| STRAT-001 | −$6.40 / 626 | −$4.78 / 625 | −$2.63 / 234 | −$5.64 / 614 | −$5.71 / 556 | −$9.22 / 583 | −$7.56 / 639 | −$6.50 / 585 | −$0.54 / 33 |
| STRAT-001 + OVL-REGIME | −$3.40 / 375 | −$2.92 / 383 | −$2.36 / 214 | −$3.01 / 369 | −$2.32 / 317 | −$6.55 / 345 | −$4.31 / 398 | −$3.96 / 351 | −$0.85 / 41 |
| STRAT-002 | +$0.83 / 105 | −$0.22 / 112 | +$3.06 / 42 | +$4.03 / 110 | +$4.04 / 91 | +$1.29 / 77 | +$0.06 / 109 | +$0.55 / 105 | −$0.22 / 9 |
| STRAT-002 + OVL-REGIME | +$0.38 / 55 | −$0.19 / 64 | +$3.20 / 30 | +$4.14 / 64 | +$0.68 / 46 | +$0.28 / 40 | −$0.08 / 63 | +$0.73 / 59 | −$0.67 / 6 |
| STRAT-004 | +$1.23 / 16 | +$1.58 / 15 | +$1.48 / 7 | +$11.99 / 14 | +$5.91 / 11 | +$2.18 / 9 | −$0.80 / 13 | −$0.82 / 14 | −$0.00 / 1 |
| STRAT-004 + OVL-REGIME | +$1.33 / 14 | +$1.51 / 13 | +$1.48 / 7 | +$12.28 / 11 | +$6.19 / 9 | +$2.51 / 6 | −$0.55 / 11 | −$0.21 / 10 | −$0.00 / 1 |
| STRAT-005 | +$2.05 / 13 | +$1.30 / 17 | +$3.21 / 5 | +$5.99 / 23 | +$3.19 / 11 | +$0.54 / 14 | −$0.33 / 14 | +$0.95 / 12 | — |
| STRAT-005 + OVL-REGIME | +$1.61 / 10 | +$0.89 / 13 | +$3.26 / 4 | +$6.37 / 17 | +$3.23 / 7 | +$0.80 / 11 | −$0.40 / 9 | +$1.17 / 10 | — |
