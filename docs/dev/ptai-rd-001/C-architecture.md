# C: Proposed integrated architecture (PTAI-RD-001)

This document builds on what A1 found working. Each layer names the module to keep as the one implementation, what to change, and its interface. Three things are new rather than extended:
- the research engine (M5, built in this programme);
- a programme trial ledger;
- isolated paper portfolios.

## 1. Principles

1. **One implementation per job.** A1 §5 counts:
   - about 10 candle loaders;
   - 3 trade simulators;
   - 4 to 5 cost models;
   - 2 trial ledgers;
   - 6 random-baseline variants.

   New work goes into the module chosen below, and the others are retired as their users move.
2. **Research and trading share decision code, and nothing else.**
   - Backtests and the trader decide through the same `strategies` runner. This is the parity property, tested by `test_the_engine_replays_exactly_what_the_backtester_would_decide`.
   - Research never writes trading state.
   - A candidate reaches paper or live only by raising its catalogue `authorisation`, on the owner's recorded decision.
3. **Every result carries its provenance:**
   - the dataset snapshot;
   - the code hash, covering every file on the path (A1 §5 shows four hash sets with gaps);
   - the configuration hash;
   - the seeds;
   - the months read, including earlier exposures;
   - the trial ledger entry.
4. **Deterministic where possible.** Seeds are explicit. A job's key is its kind, version, parameters and seed, so the same experiment is not run twice by accident, and is never counted twice.
5. **Gates are the owner's.** These choices escalate to the owner:
   - authorisation;
   - opening the lockbox;
   - paid data;
   - live capital;
   - changes to the research rules, such as adopting a new bootstrap.

   Engineering inside research does not.

## 2. Layers and interfaces

| # | Layer | Keep as the one implementation | Change / add | Interface |
|---|---|---|---|---|
| L1 | Market data | `market_data.candles.exchange_candles` (exchange layer, per-exchange cache, closed bars only) | Dataset snapshots; one bar hash; refetch the last cached bars to catch revisions (A2 N16); refill interior gaps; research series end at gaps over a day (N17); a point-in-time universe from listing evidence (N20); new sources behind one protocol | `DataSource.fetch(symbol, kind, start, end) -> frame` with `attrs` provenance; `DatasetSnapshot{id=sha256(manifest), coins, timeframe, exchange, range, bar hashes, gaps, listing}` |
| L2 | Features | `strategies.indicators` (live) and `model_lab.features` (research) | One feature library with as-of semantics. A value at bar t reads only bars that closed by t. Cached by (snapshot, feature, version, parameters) | `Feature{id, version, params, inputs, warmup_bars}.compute(frames) -> Series` |
| L3 | Signals | `signal_audit` (registration, rounds, statistics) | A signal is a feature turned into an event or score with a declared horizon. It is evaluated as a signal (information, decay, against random), separately from any strategy | `Signal{id, version, horizon}.values(snapshot) -> Series` |
| L4 | Strategy decisions | `strategies` (Strategy, StrategyRunner, overlays, catalogue) | New candidates join the catalogue at `authorisation: research`. Model-backed strategies load published artifacts through `model_store`, as STRAT-003 does | unchanged: `evaluate(window, position, coin, context) -> Decision` |
| L5 | Signal combination | `signal_fusion` (gate settings, log-only path), overlay `allow_entry_in` | Combination policies as entry gates, so backtest and trader see them identically: fixed conjunction, weighted score, calibrated logistic meta-model, expected-value threshold, veto. An ablation harness runs each policy with each part removed, on the same seeds | `CombinationPolicy.allow(context) -> (allow, size_factor, reasons)` |
| L6 | Portfolio and sizing | `position_sizing` + `replay.Account` | Sizing policies: fixed fraction with venue minimum (today), volatility target, equal risk. Exposure and correlation caps. Positions keyed by (portfolio, coin), not coin alone (A1 gap 4) | `SizingPolicy.size(signal, account, venue) -> usd` |
| L7 | Risk | `pt_risk` thresholds + trader halt | A deterministic risk state, independent of strategies: `normal`, `entries_refused`, `exits_only`, and `liquidate` (only when the owner authorises it). Persisted order intents (N5). Polling of pending orders (N6). Stub logs removed (N1) | `RiskState`; `OrderIntent{coin, side, bar, client_id, state}` |
| L8 | Execution and costs | `replay.Costs` (fee, allowance, minimum, sell step), fed by the exchange layer's `trading_fees` | One cost model everywhere (N27). Paper fills apply sell steps and minimums (N28). An entry is acted on only within a window after its bar (N12) | `Costs.from_exchange(exchange, coins)` |
| L9 | Evaluation | `signal_fusion.evaluation.replay` (the only portfolio replay) + `strategy_lab.baselines` | One baseline library: random entries with the strategy's exits, matched holding, hold, cash, the unfiltered strategy. One statistics module (§4). Daily, weekly, monthly and annual returns. Accounts of £50, £200, £500 and £10,000, separately. Intrabar drawdown for the halt (N18) | `evaluate(trades, snapshot, costs, accounts, baselines, seeds) -> Report` |
| L10 | Registration | `strategy_lab.experiment` (freeze, seal, verify) + `model_lab.batch` sealing | **One programme trial ledger**, appended to through adapters; the existing ledgers and frozen records stay byte-exact. One register of exposures to data (looks). A lockbox-opening register that enforces FDS-MH-001's limit | `ledger.append(Trial{...})`, schema below |
| L11 | Research engine | `research_engine` (this programme: queue, scheduler, window) | Job kinds per lab; dataset and feature caches; compute budgets per hypothesis; run history of resources | `@job_kind(name, version)`; `Scheduler.submit(kind, params, seed)` |
| L12 | Research backlog | `B-candidates.json` | A candidate registry with each entry's status: proposed, implemented, tested, rejected, qualified or observing. Hypothesis cards. Priority from evidence, data, feasibility and cost, never from past returns | `Candidate{id, family, sources, data_required, status, evidence, priority}` |
| L13 | Paper lab | `trading_mode` paper book + `strategy_lab.observation` | Isolated paper portfolios, each with a frozen configuration, its own virtual book and ledger, and a reconciliation against the replay of the same bars. Started only for entries at `paper` (the owner's decision) | `PaperPortfolio{id, config_hash, book, ledger, window}` |
| L14 | Authorisation and promotion | `catalogue.json` `authorisation`, the trader's fail-closed checks | A promotion package: development results, the unseen-data check, paper evidence, reconciliation, risk tests, and fee and minimum feasibility. It goes to an owner decision record, then a PR that raises the authorisation. No UI path raises `live` | `PromotionPackage` (a document plus the evidence files) |
| L15 | UI | Settings windows and `ui_table.DataTable` | Research engine (built). A research leaderboard: never sorted by highest return; development, unseen and forward results kept apart. An evidence browser. A paper-lab window | facts-only wording (owner rule) |

### Data flow

```
DataSource ─► DatasetSnapshot ─► Feature library ─► Signals ──┐
                                                              ▼
                       catalogue Strategy + overlays + CombinationPolicy  (same code in backtest and trader)
                                                              ▼
            SizingPolicy ─► RiskState ─► Costs/venue ─► replay (research) | trader (paper/live)
                                                              ▼
            evaluate(): baselines + statistics + accounts ─► Report ─► ledger.append(Trial)
                                                              ▼
              research engine job result ─► candidate status ─► leaderboard (development / unseen / forward)
```

## 3. The qualification path

| Stage | Data | Who starts it | What it can conclude |
|---|---|---|---|
| Exploration | Development months (to 2025-05-06) | The engine, autonomously | Nothing. It is logged as a trial and ranks priorities only |
| Declared evaluation | Development months, with the plan frozen before running | The engine, after the method in §4 is approved | Profitable, unprofitable or inconclusive *on development data*, after multiple-testing control |
| Unseen check | The lockbox (2025-05-06 to 2026-11-06): one opening per finalist, within FDS-MH-001's limits | **Owner**: a separately registered evaluation | Whether the effect survives months not used to choose it |
| Forward paper observation | New months, as they arrive | **Owner**: authorisation raised to `paper` | Operational evidence: fills, reconciliation, costs. Too little time for a profit verdict |
| Live candidate | All of the above | **Owner** | A decision package, not an activation |

At every stage a candidate whose power is too low is reported as **INCONCLUSIVE**, never as profitable or unprofitable.

## 4. Statistical method (to settle before M6)

These follow from A2 N19 and N21 to N25, and from the lessons of the FDS-SIG-004 reviews:
- equivalence bounds, not "the interval contains zero";
- costs counted once;
- protective limits fail closed;
- a declared batch is never amended.

The method:
- **Resampling.**
  - Day-level marked returns with a stationary bootstrap (Politis-Romano), whose mean block length is chosen from the data's autocorrelation.
  - Each trade's net is booked across the days it was held, not on its entry day.
  - It is checked on synthetic null series (size about 5%) and on known-skill fixtures (power reported).
  - Adopting it in place of the merged draft amendment is owner decision O3.
- **Multiple testing.**
  - A programme-wide error budget in the ledger.
  - Holm within each declared family, and Romano-Wolf across a family's configurations where resamples are shared.
  - The deflated Sharpe ratio reported beside every best-of-many.
  - PBO is shown, marked as indicative, when it rests on few contestants.
- **Power.**
  - Every verdict states the smallest effect it could have detected.
  - "Inconclusive" when that is larger than the effect worth trading after costs.
- **Returns.**
  - Net of fees and slippage, on starting equity.
  - Daily, weekly, monthly and annual, separately.
  - Per capital-day.
  - With drawdown and recovery time.
  - At each account size, without assuming linear scaling.
  - A 10% figure is reported with its period, drawdown and the chance of it recurring, never as a threshold.

## 5. The programme trial ledger (schema v1)

One JSON line per trial, appended under `<data dir>/research_engine/ledger.jsonl`. Adapters write the existing strategy-lab and model-lab trials into it, so nothing old is rewritten.

| Field | Meaning |
|---|---|
| `trial_id` | Unique id; the job key when it ran in the engine |
| `experiment_id`, `member` | The declared experiment and its member, or `exploration` |
| `kind` | exploration, declared, unseen_check, paper_observation |
| `family`, `hypothesis_id` | From the candidate registry |
| `candidates` | Strategy, model and policy ids, with versions and parameter hashes |
| `snapshot_id`, `months`, `coins`, `exchange` | What data was read |
| `seeds`, `code_hash` | For reproduction |
| `earlier_exposures` | Looks at the same months by related candidates |
| `outcome` | A pointer to the report; headline figures; verdict and its power |
| `counted_in` | The error budget this trial counts against |

## 6. Decisions made within research scope (documented, not escalated)

| ID | Decision | Why |
|---|---|---|
| RD-1 | The engine runs jobs in spawned processes from a SQLite queue, below normal priority, keeping max(4 GiB, a share) of memory free | Windows-safe isolation from the hub and the trader; jobs persist across restarts; no service to install |
| RD-2 | CPU first: no GPU dependency | There is no CUDA (A3). Tree models and replays are CPU-bound. torch stays optional |
| RD-3 | One new ledger fed by adapters; frozen records untouched | Preserves E1 and batch evidence byte-exact |
| RD-4 | Research series end at gaps over one day | Removes the impossible XRP trades (N17) without touching live code |
| RD-5 | The leaderboard ranks by verdict class, then by the lower confidence bound of net return per capital-day after costs, never by highest return | The brief's rule against ranking by headline return |
| RD-6 | Strategy code is reimplemented from published rules. Code is reused only under MIT, BSD or Apache licences, with attribution; GPL frameworks are used for ideas only | PowerTraderAI is Apache-2.0 |

## 7. Owner decisions (escalated)

See D §3 (O1 to O8).
