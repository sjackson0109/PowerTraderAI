# The nine-coin comparison at $500 and $50: plan, written before any result

**Status:** written and committed on 2026-11-11, before any run at these account sizes.

**Authority:** the owner, 2026-11-11: "repeat that strategy evaluation based off a $500 initial investment - and again another based on $50 investment."

## 1. What changes

Only the account. The app's "Run a backtest…" takes the account in pounds and rounds the dollars to the cent, so the two sizes are:

| Account | In pounds, at 1.3476 | In dollars |
|---|---|---|
| The first comparison | £10,000.00 | $13,476.00 |
| This plan | £371.03 | $500.00 |
| This plan | £37.10 | $50.00 |

Everything else is `COMPARISON-9-COINS-PLAN.md` unchanged:
- the same ten runs (§4);
- the data rule (§5);
- 0.50% + 0.05% (§6);
- 10 seeds of 200 random draws (§7);
- the report's contents (§8).

The same limits apply: development months only, no tuning, nothing enabled or registered, and no figure called a pass or a fail.

**The model half is not repeated.** Batch 1 measures entries in units of one entry per trade (`model_gate.ACCOUNT` is 100 units a coin) and has no account size, so its figures would not change.

## 2. What I expect, before running

These follow from the replay's sizing rules (`signal_fusion/evaluation/replay.py`, `position_sizing.py`).

**The rules:**
- An entry is 1% of the account's value at that moment.
- An entry below the minimum entry is raised to it. The minimum entry is Coinbase's $1 minimum order × (1 + 0.1% slippage over both fills + 1.0% round-trip fee + 2% margin) = **$1.031**.
- No coin holds more than 10% of the account.

**At $500:**
- 1% is $5.00. That is above $1.031 while the account stays above $103.10, which needs a fall of nearly 80%.
- So every dollar figure should be the £10,000 run's × 500 / 13,476 (0.0371). Shares should stay about the same: the share of random draws beaten, the drawdown and the capital in use.
- **The one expected difference:** sells are rounded down to each coin's step (DOGE 0.1, HYPE 0.001). A smaller position leaves a larger share unsold.

**At $50:**
- 1% is $0.50, below the minimum. So every entry is raised to $1.031, which is about 2.1% of the start, until the account passes $103.10.
- Entries are therefore about twice the usual share. They are also fixed in dollars rather than growing with the account.
- **I expect:**
  - drawdowns and capital in use at about twice the share;
  - losing strategies to lose about twice the share;
  - the 8% halt to be reached sooner;
  - the DOGE and HYPE rounding to weigh more. A $1.031 DOGE buy at $0.70 can leave up to 0.1 DOGE ($0.07) unsold.
- Buy-and-hold and the random entries are sized by the same rules. So they are raised to the minimum too, and the comparison stays like for like.

If a figure departs from these expectations, the report says so and why.

## 3. How it is run

- **The driver is `docs/dev/run_compare9_accounts.py`,** in the first comparison's sandbox.
- **One simulation per strategy run,** shared by the three account sizes. A strategy's trades, and its random entries' trades, do not depend on the account.
- **The check comes first.** On the shared simulation, the £10,000 figures must reproduce the saved ones exactly, every seed included; otherwise it stops.
- **Each new size's seed-700000 run is `strategy_lab.runs.run`'s own, saved.** So it appears in "Compare results…" and is logged as a trial. The ten seeds are drawn as before.
- **The trial log continues:** 56 lines become 76.

## 4. The report

- **The report:** `docs/dev/COMPARISON-9-COINS-REPORT-accounts.md`.
- **The evidence:** `docs/dev/compare-9/accounts/`.
- **It shows each size's tables beside the £10,000 figures,** in dollars and as shares of the account.
