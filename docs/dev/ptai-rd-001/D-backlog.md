# D: Implementation backlog and execution plan (PTAI-RD-001)

Work packages (WP) by milestone, with what they depend on, the tests they need and the gate they pass. Defect IDs refer to A2, layers to C.

**Every PR's gate:**
- focused tests, plus the full app suite (locally and in CI), with the results stated in the PR;
- no change to a frozen record;
- the owner reviews and merges.

**Extra gate for a PR that changes paper or live behaviour:** it says so in its own section, with old against new behaviour.

## 1. Milestones and work packages

### M0: baseline and gaps (this PR)

| WP | Deliverable | Status |
|---|---|---|
| 0.1 | A1 capability matrix, dependency map, duplication list | Done |
| 0.2 | A2 defect register (51 rows; 4 high) | Done |
| 0.3 | A3 hardware inventory | Done |
| 0.4 | B strategy research catalogue + `B-candidates.json` | Done |
| 0.5 | C architecture, D this plan | Done |

### M1: research and execution correctness

| WP | What | Fixes | Changes trading? | Test required | Gate | Status |
|---|---|---|---|---|---|---|
| 1.1 | Decide a late bar after a retry, not a bar later | D1 | Yes (fix) | 4 late-bar tests that fail on the old code | Review | **PR #260** |
| 1.2 | Engine-safe candle cache writes; unique run folders | (found building M5) | No (cache only) | cache-replace failure; same-second runs | Review | **PR #263** |
| 1.3 | Research series end at gaps over a day (strategy lab; the single-coin backtester `backtest/` still to do) | N17 | No | a 30-day hole: no trade spans it; XRP compare row recomputed as a diagnostic | Review | **PR #265** |
| 1.4 | `MarketNotFound` is a HOLD, and each coin is handled in its own `try` | N8 | Yes (fix) | first coin raises; second still decided; status written | Review | **PR #272** |
| 1.5 | The decision log names the exchange whose bars were used | N15 | No | primary fails; log names the fallback | Review | **PR #273** |
| 1.6 | Refetch the last cached bars; refill interior gaps | N16 | Yes (data) | provisional close revised; the cache holds the revision | Review | Planned |
| 1.7 | Cooldown counted from the fill bar | N13 | Yes (parity fix, live overlay) | replay and engine agree on the first allowed bar | Review | Planned |
| 1.8 | Entry actionable only within a window after its bar | N12 | Yes | ENTER at close + 6 h is recorded as missed | **Owner (O4)** | Proposed |
| 1.9 | Risk states: entries refused / exits only / liquidate-if-authorised; remove false stub logs | N1 to N4 | Yes | a halt with held positions: exits still sell (after O1) | **Owner (O1): approved 2026-11-12** | **PR #270** |
| 1.10 | Persisted order intents, resent with the same client id | N5, N6 | Yes (live) | a network error after acceptance: one order, not two | **Owner (O2): approved 2026-11-12** | **PR #271** |
| 1.11 | Stationary bootstrap on marked days; calibration on null and known-skill fixtures | N19, N22 | No | size near 5% on null series; power reported on skill fixtures | **Owner (O3)**: measure a stricter variant first | **PR #266** (library) and **PR #277** (calibration; the default is the studentised test with 1.5x blocks) |
| 1.12 | Observation fixes: freeze LLM mode and exchange order; code hash; Reconcile completeness | D2 to D7 | No | the readiness tests listed in A2 | Review | Planned |
| 1.13 | Fee defaults from the exchange layer, or a refusal; paper applies sell steps and minimums | N27, N28 | Yes (paper) | fee feed fails: paper refuses; DOGE sell rounds to 0.1 | Review | Planned |
| 1.14 | Intrabar drawdown for the halt check in replays | N18 | No | 9% intraday dip, 7% on closes: halt reported | Review | Planned |

### M2: unified research framework

| WP | What | Depends | Test required |
|---|---|---|---|
| 2.1 | Programme trial ledger (C §5) + adapters from strategy-lab and model-lab trials. **PR #274** | — | old ledgers unchanged byte for byte; every engine job appends one line |
| 2.2 | Dataset snapshots + one bar hash (replaces three) | 2.1 | the same bars give the same id; a revised bar gives a new id |
| 2.3 | One statistics module (bootstrap, Holm, Romano-Wolf, deflated Sharpe, PBO, power) | 1.11 | each method on null and skill fixtures |
| 2.4 | One baseline library (random with the strategy's exits, matched holding, hold, cash, unfiltered) | — | each baseline's trade count and holding match their definition |
| 2.5 | One cost model from `trading_fees` (retire 3 others) | 1.13 | every caller reads the same rate for the same exchange |
| 2.6 | Report: daily/weekly/monthly/annual returns; £50/£200/£500/£10,000 accounts; capital use; return per capital-day; recovery time. **PR #276**: the period returns (accounts still to do) | 2.3 | hand-computed fixtures |
| 2.7 | Code hashes cover every file on the path (strategies, exchange layer) | — | changing a strategy file breaks the seal |

### M3: strategy catalogue expansion

Each candidate becomes a catalogue entry at `authorisation: research`, with:
- its published defaults;
- source and licence in `research_refs`;
- tests of its rule on hand-made fixtures;
- a backtest–engine parity test.

The order follows B §20. OHLCV-only candidates come first, because no other data is held (A1 §3).

**B's budget warning applies:** 4.3 years of development data support only a few dozen honest, independent configurations across the whole programme. So each candidate is declared with its published parameters and is not tuned, and each one counts against the ledger's budget (M2 2.1).

| WP | Candidate (B id) | Kind of work | Notes |
|---|---|---|---|
| 3.1 | `breakout.zarattini-ensemble` | New catalogue entry | An ensemble of Donchian lookbacks of 20 days or more, with the midline ratchet; daily, long-only, sized at most 100% |
| 3.2 | `trend.price-above-ma` | New catalogue entry | Daily close above its 50-200-day average, else cash. Declared as a member of the TSMOM family |
| 3.3 | `portfolio.equal-weight-1n`, `portfolio.dca-periodic` | Baselines (M2 2.4) | Every multi-coin result is compared with 1/N and periodic buying, as well as with random entries |
| 3.4 | `risk.ratchet-stop`, `risk.atr-trailing-stop`, `regime.ma-trend-gate` | Evaluation only (M6) | Already built: evaluated as STRAT-004's exits and gate, against no stop and random stops. No new code |
| 3.5 | `volatility.vol-targeting-sizing` + `volatility.ewma-riskmetrics` | SizingPolicy (M4 4.2) | Sized once at entry, at most 100%; re-tested, since the repo's earlier test found no drawdown gain |
| 3.6 | `momentum.dual-momentum` | Needs the portfolio interface (C L6) | A weekly BTC/ETH/cash switch: one decision across coins |
| 3.7 | `ml_model.calibration-ev-gate`, `ml_model.meta-labelling` | Gates (M4 4.4) | Take or skip STRAT-004/005 entries; must beat a random skip at the same rate |
| 3.8 | `data_source.coinbase-public-market-data` | Recorder job | Records order-book snapshots and trades from now on, since no history exists. Needs WP 5.7 to run while the hub is closed |
| 3.9 | `data_source.kraken-ohlcvt` | Second history | A licence-clean cross-check of Coinbase candles |
| 3.10 | `data_source.binance-vision-bulk` | Research-only data | Its CC BY-NC-SA terms allow personal backtesting but not live trading, and its data must not be committed |

Mean-reversion and microstructure candidates are priority 4 in B: the evidence is against them at these costs. They stay in the catalogue as falsification controls and are not built first.

### M4: models and signals

| WP | What | Depends |
|---|---|---|
| 4.1 | Feature library (C L2), with as-of tests; consolidates RSI, SMA and Parkinson | 2.2 |
| 4.2 | Volatility features and sizing: EWMA, GARCH(1,1) (`arch`, NCSA licence), realised volatility; volatility targeting as a SizingPolicy | 4.1 |
| 4.3 | Regime models: HMM (`hmmlearn`, BSD) and threshold rules, as overlays | 4.1 |
| 4.4 | Meta-labelling and calibrated expected value on catalogue trades (the strategy lab's M family generalised) | 2.3 |
| 4.5 | Combination policies plus the ablation harness (C L5) | 4.4 |
| 4.6 | LLM evaluation harness. It evaluates only on events after the model's training cutoff, to avoid memorised outcomes; local inference first (the owner runs `llama-server`). An LLM never overrides risk controls | 2.1 |
| 4.7 | Funding, open interest and liquidations from free public endpoints, where history allows (B data table) | 2.2 |

### M5: local research engine

| WP | What | Status |
|---|---|---|
| 5.1 | Queue, scheduler, resources, modes, self-test | **PR #262** |
| 5.2 | Strategy backtests as jobs | **PR #263** |
| 5.3 | Settings > Training > Research engine window | **PR #264** |
| 5.4 | Model-lab batches as jobs | **PR #275** |
| 5.5 | Dataset and feature caches shared by jobs | after 2.2, 4.1 |
| 5.6 | Budgets per hypothesis; backlog-driven queueing; the next-experiment rule (C L12) | after 2.1 |
| 5.7 | Option to keep the engine running while the hub is closed | after 5.3 |

### M6: the experimental programme

It starts only after O3 (the method) is decided and M2 is in place. Then:
- one declared evaluation per family, with search spaces frozen before running;
- all four account sizes;
- profitable, unprofitable and inconclusive results reported alike, on development data.

The lockbox is used only through O5.

### M7: forward paper laboratory

| WP | What |
|---|---|
| 7.1 | Isolated paper portfolios (C L13): own book, own ledger, frozen configuration |
| 7.2 | Several portfolios at once in one trader process, or one process each |
| 7.3 | Reconciliation against the replay of the same bars, and missed or late signals reported |
| 7.4 | The owner's route to start a paper observation (O7 for each candidate) |

### M8: live readiness

| WP | What |
|---|---|
| 8.1 | Failure-scenario suite: exchange outage, late candles, missing quotes, rejected orders, stale balances, partial fills, restarts, gaps |
| 8.2 | Promotion package generator (C L14) |
| 8.3 | Credential guidance: trade-only API keys, withdrawals disabled |
| 8.4 | Owner decision record template; no activation |

## 2. Order of work

1. M1: WP 1.1, 1.2, 1.3, 1.4, 1.5 and 1.11 (library); M5: 5.1 to 5.4.
2. M2: 2.1, 2.2, 2.3, 2.6 and 2.7.
3. M3: the first OHLCV families from B, run as exploration jobs in the engine.
4. M4: 4.1 and 4.2; then M6, once O3 is decided.
5. M7, once a candidate's paper authorisation is decided (O7).

## 3. Owner decisions needed

| ID | Decision | Why it is the owner's | Recommendation |
|---|---|---|---|
| O1 | Change the emergency halt: entries refused, exits still run, and liquidation only if explicitly allowed | It changes live and paper behaviour. FDS-SR-001 left the halt out of scope | **Approved 2026-11-12** ("yes, sounds like a big flaw"): PR #270, exits only, no liquidation |
| O2 | Persisted order intents with resend under the same client id | Live order behaviour | **Approved 2026-11-12**: PR #271 |
| O3 | Adopt the stationary, marked-day bootstrap for long holdings (it replaces the draft amendment) | A change to research rules | **2026-11-12: measure a stricter variant first.** Done in PR #277: none of four variants met the declared 6.0% limit; the lowest worst case (studentised, 1.5x blocks, 6.2%) is the library default. A declared evaluation names its method in its registration |
| O4 | Entry actionable only within a window after its bar (for example 15 minutes) | Changes when trades happen | Yes, for parity with backtests |
| O5 | Any lockbox opening | Spends the only unseen months | Not before a declared M6 finalist exists |
| O6 | Install scikit-learn in the app's `.venv` | Changes the owner's environment | **Done 2026-11-12** ("go ahead, add it to requirements.txt too"): installed, pinned to what was there; PR #267 |
| O7 | Raise any candidate to `paper` (STRAT-004 first, once D1 is merged) | Authorisation | **Approved 2026-11-12** for STRAT-004: PR #268, after #260 merged |
| O8 | Paid data sources | Cost | None proposed; B lists free sources |
| O9 | A trading switch for any strategy in Settings > Strategy (the owner's request of 2026-11-12, e.g. STRAT-001 off now and on later) | Authorisation from the UI | Built: PR #269; switching on an entry its authorisation does not clear asks first |
