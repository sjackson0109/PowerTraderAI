# RUN-LOG-sr-1: strategy research and catalogue expansion (FDS-SR-001)

## 2026-11-07: the owner's implementation authorisation

The owner accepted FDS-SR-001, with its research report, architecture assessment and decision record (PR #236, merged `0e765e5`), as the implementation baseline.

**Decisions approved, as recommended:** E-D1, E-D2, E-D3, E-D4, E-D7 and E-D9. The rest wait for their milestones.

**Authorised:**
1. Merge #236.
2. M2a, M2b.
3. M3a, M3b, M3c.
4. Then M4, M5 and M6, in separate, tested PRs.

**Not authorised:**
- registering any experiment, so M5c waits for a separate approval;
- activating any strategy, gate or sizing policy for paper or live;
- any live-trading change.

**An instruction that amends FDS-SR-001 §5.4.1** (REF-RANDOM):
- Random-entry baselines must keep the strategy's own execution and exit constraints.
- Resampled holding periods are not to be treated as equivalent to replaying the actual exit rules, unless that equivalence is validated.
- As built (M4a): REF-RANDOM replays the strategy's actual exit rules from each random entry.

**Pull requests** (the owner merges; each branch is cut from the one before, so they merge in order):

| Milestone | What | PR |
|---|---|---|
| M2a | Catalogue lifecycle, authorisation, fail-closed checks | #237 |
| M2b | The strategy list in Settings > Strategy | #238, on M2a |
| M3a | STRAT-004, the daily Donchian breakout | (see M3a), on M2b |
| M3b | STRAT-005, time-series momentum decided weekly | (see M3b), on M3a |
| M3c | OVL-REGIME and the entry gate's market context | (see M3c), on M3b |
| M4a | The portfolio simulation, baselines, accounts and lot sizes | (see M4a), on M3c |
| M4b | Experiment records, the trial log, strategy looks, the reserved months | (see M4b), on M4a |
| M4c | The model cells | (see M4c), on M4b |
| M5a | "Run a backtest..." and "Compare results..." | (see M5a), on M4c |
| M5b | "Model evidence..." | this branch, on M5a |

## M2a: the catalogue lifecycle

**Branch** `feat/sr-m2a-catalogue-lifecycle`, from `main` at `0e765e5`.

**Built:**
- **`strategies/catalogue.json`:** every entry states its `authorisation` (E-D3):
  - STRAT-000, -001 and -002 and the four overlays: `live`;
  - STRAT-003: `research`, and `deterministic: false`.
- **`strategies/catalogue.py`:**
  - `authorisation` is required;
  - the new families;
  - the optional fields with their defaults: `timeframes_permitted`, `deterministic`, `data_requirements` and `research_refs`;
  - `allowed_in_mode`.
- **`strategies/settings.py`:**
  - `read_strategy_settings(settings, mode=None)`: with a mode, an entry not authorised for it is a problem;
  - a timeframe outside `timeframes_permitted` is a problem;
  - `read_research_enabled`.
- **`pt_trader.py`:** both strategy-settings checks (before each order, and each pass) pass the trader's pinned mode.
- **`pt_hub.py`:** the SIGNALS note passes the configured mode, so a refused strategy shows as blocked.
- **`pt_settings_manager.py`:** a rule for `strategy.research_enabled`.

### Where the spec was not explicit

| Point | As built | Why |
|---|---|---|
| Overlays and gates in `strategy.research_enabled` | The list holds strategies and overlays. The default is the seven entries that existed before FDS-SR-001 | The owner: "all new strategies and gates must remain research-only and disabled by default" |
| A malformed `strategy.research_enabled` | Reads as the default. The settings check reports it | It never affects trading, so a typo should not empty the research windows |
| Without a mode | `read_strategy_settings` checks no authorisation | Research callers (backtests) may use any entry. Only callers that trade pass a mode |
| The optional fields in the file | Left out of `catalogue.json` where they equal their defaults; filled in when the catalogue loads | The file stays as it was for every existing entry, apart from `authorisation` |

### Tests

`tests/test_strategy_lifecycle.py`:
- the approved authorisations;
- the defaults;
- every refusal of a malformed field;
- the mode matrix;
- **existing behaviour:** STRAT-000, -001 and -002 with each of the 16 combinations of the four overlays read the same with and without a mode, in both modes;
- **a replayed paper session:**
  - its orders are byte-identical with and without the check;
  - a research strategy places none;
  - a paper strategy trades in paper as before.

`tests/test_catalogue.py` and `tests/test_model_strategy.py` changed only where they pin the schema (the new required field, the longer families list).

## M2b: the strategy list in Settings > Strategy

**Branch** `feat/sr-m2b-strategy-catalogue-view`, from M2a's branch.

**Built:**
- **`strategy_settings_ui.py`:** a "Strategies and stops" list at the top of the window.
  - **Rows:** every strategy, then every stop. Each shows its name, kind, family and candles, what it may be used for ("Research only", "Paper", "Paper and live"), whether it is enabled for research, and whether it is in use.
  - **Highlighting a row shows:**
    - its description;
    - what it can be used for;
    - an "Enabled for research" tick;
    - "Use for trading". This is offered only where the entry's authorisation covers the trading mode in Settings: for a strategy it chooses it, for a stop it ticks it.
- **Trading choices:**
  - The strategy and stop choices below the list offer only what the trading mode may use.
  - A saved strategy or stop the mode may not use is reported, as an unknown one is today.
  - The candles offered are the strategy's `timeframes_permitted`.
- **Save** writes `strategy.research_enabled` only when a research tick changed.
- **`strategies/descriptions.py`:**
  - the words for families, kinds and uses;
  - a description of STRAT-003, which the list now shows (it still cannot be chosen).

### Where the spec was not explicit

| Point | As built | Why |
|---|---|---|
| Evidence references in the details (§5.8) | Not shown | The owner's rule: on-screen text states facts only, with no spec or document names. The references stay in `catalogue.json` |
| Parameters of a strategy that is not in use | Not edited in this window | The trader uses only the selected strategy's parameters. A research-only strategy's parameters are chosen per run in "Run a backtest…" (M5a) |
| The trading mode the window checks | `trading.mode` in the settings file: "live" only when it is exactly that, as the trader reads it | One rule for both |

### Tests

`tests/test_strategy_catalogue_view.py`, 15 tests:
- the rows and their words;
- "In use" following the choices;
- "Use for trading" for a strategy and a stop;
- research-only, paper-only (in live) and research-only stop entries;
- research ticks saved only when changed, with either signal source;
- the permitted candles;
- facts-only words.

The existing `tests/test_strategy_settings_ui.py` passes unchanged, except that its "offered strategies" test now states the authorisation rule.

## M3a: STRAT-004, the daily Donchian breakout

**Branch** `feat/sr-m3a-strat-004-donchian`, from M2b's branch.

**Built:**
- **`strategies/breakout.py`:**
  - **Entry:** on the closed bar, a close above every close of the previous `entry_days` days.
  - **Exit:** a close below every close of the previous `exit_days` days.
  - **Defaults:** 55/20 (the Turtle System 2 rule, not tuned; E-D9). Bounds are 20–250 and 5–120, with `exit_days < entry_days`.
- **Catalogue entry:** family `breakout`; `authorisation: research`; `timeframes_permitted: ["1d"]`; not enabled for research by default.
- **Its description** for the strategy list.

### Where the spec was not explicit

| Point | As built | Why |
|---|---|---|
| The channel's prices | Closes, for both the entry and the exit | Zarattini et al. build the channel from closes. Decisions are on closed bars, so an intrabar high is never used |
| Ties | Equal to the previous high is not a breakout; equal to the previous low is not a new low | "Above every close" / "below every close", as §5.4.3 states |
| Days on other candles | Calendar days, turned into whole bars by the run's bar length (rounded up) | §5.4.3: so 4-hour and 12-hour robustness runs span the same time |
| The window | Exactly the rule's span plus the decision bar | Rolling maxima and minima have no warm-up; a larger window would make the live engine fetch more bars for nothing |
| Missing bars | The channel counts bars, as every catalogue strategy does | Gaps are rare in daily bars. FDS-SR-001 §6.3 reports per coin |

### Tests

`tests/test_strategy_breakout.py`:
- hand-worked entries, exits and ties;
- the warm-up;
- calendar days on 4-hour and 1-hour bars;
- bounds and the rule;
- no look-ahead: appending bars changes no earlier decision, and the rule reads only its window;
- parity: the live signal engine and a replayed runner agree on every closed daily bar;
- the backtester's next-open fills;
- research-only, not enabled, refused for trading, described.

## M3b: STRAT-005, time-series momentum decided weekly

**Branch** `feat/sr-m3b-strat-005-tsmom`, from M3a's branch.

**Built:**
- **`strategies/momentum.py`.** On a decision day it counts how many of the 30-, 90- and 365-day returns are positive.
  - **Entry:** at least `min_agree` (2) are positive.
  - **Exit:** fewer are.
  - **Between decision days:** HOLD, so only an overlay can exit.
  - **Decision days:** every `rebalance_days` (7) days from Monday 2020-01-06. The decision is made on the bar that closes at midnight UTC at the end of the day.
  - **Each lookback's earlier close** is the bar that opened exactly L calendar days earlier. A gap there holds.
  - **Defaults:** 30/90/365, two of three, weekly (E-D9), not tuned.
- **Catalogue entry:** family `momentum`; `authorisation: research`; `timeframes_permitted: ["1d"]`; not enabled for research by default.
- **Its description** for the strategy list.

### Where the spec was not explicit

| Point | As built | Why |
|---|---|---|
| The decision bar on intraday candles | The bar that closes at 00:00 UTC ending a decision day | One decision per decision day on any candles, as on daily bars |
| A gap at a lookback's date | HOLD, "BARS_MISSING"; no other bar stands in | A return over a different span would be a different rule |
| Entering mid-trend | On any decision day with enough positive returns, not only when the vote first turns | It is the published rule: long while the signal is positive. After a stop's exit it re-enters on the next decision day if the vote still holds |
| A zero return | Not positive | "Positive" (§5.4.3) |
| The lookback's earlier bar on intraday candles | Exactly L days of bars before the decision bar | Every supported timeframe divides a day, so L days is a whole number of bars |

### Tests

`tests/test_strategy_momentum.py`:
- the schedule (weekly Mondays, `rebalance_days`, 4-hour bars);
- hand-worked votes, `min_agree`, a zero return, a gap;
- the warm-up;
- no look-ahead;
- engine/runner parity on every closed daily bar;
- next-open fills;
- bounds and the rule;
- research-only, not enabled, refused for trading, described.

## M3c: OVL-REGIME and the entry gate's market context

**Branch** `feat/sr-m3c-ovl-regime`, from M3b's branch.

**Built:**
- **`strategies/runner.py`, the context interface (§5.6):**
  - An overlay may declare `context_needs()`: (reference, timeframe, bars), where the reference is "self" or a coin. It then decides in `allow_entry_in(symbol, bar_time, context)`.
  - The default `allow_entry_in` calls the plain `allow_entry`, so the four existing overlays are unchanged.
  - `StrategyRunner.evaluate` takes an optional `context`.
  - `slice_context` keeps only the bars closed at or before the decision bar's close, and only as many as declared.
- **`strategies/overlays.py`, OVL-REGIME:**
  - It allows an entry only while the reference's last closed daily close is above its `sma_days`-day simple average (that close included). The defaults are BTC and 200 days.
  - It never exits.
  - It fails closed: with no bars, too few, bars whose last one closed more than 2 days before the decision, or a missing close, it blocks.
- **`backtest/engine.py`:** `run_backtest` and `evaluate_split` take `context_frames`. Each decision sees only bars closed by its own close. Without them the gate blocks.
- **`signal_engine.py`:** fetches the declared bars through the same closed-only provider, cached per series, with the same retry rule. An unfetchable series is left out, and the gate blocks.
- **`backtest/cli.py`:** loads the reference bars from the run's own exchange and cache, and records them in the results' provenance.
- **Catalogue entry:**
  - family `regime`, `authorisation: research`;
  - `data_requirements: own+reference`;
  - not enabled for research;
  - its description, with Bitcoin and the coin itself as the reference choices.

### Where the spec was not explicit

| Point | As built | Why |
|---|---|---|
| Calling an existing runner | `evaluate` is given a context only when an overlay declared needs | A subclass overriding `evaluate` (`backtest/model_eval.py`'s `RecordingRunner`) keeps working unchanged |
| "Stale" | The reference's last daily bar closed more than 2 days before the decision bar's close | A daily series should have closed a bar within the last day. Two days allows one late bar |
| The average | The last `sma_days` daily closes, the latest included; the latest must be strictly above it | §5.4.3: "above its average" |
| "self" | The coin being decided on, at the gate's own timeframe (daily), fetched as its own series | A 1-hour strategy's coin has no daily bars of its own in the run |

### Tests

`tests/test_regime_gate.py`:
- closed-bar slicing (an intraday decision never sees that day's forming daily bar);
- allow and block, the average's span, and every fail-closed case;
- existing overlays declare nothing and are called as before;
- the runner's block reason;
- the backtester with and without context;
- **parity:** the live engine and a replay agree on every hourly bar, with the gate both blocking and allowing;
- the CLI loads and records the reference;
- research-only and refused for trading.

`tests/test_overlays.py` and `tests/test_strategy_settings_ui.py` changed only where they pin the list of overlays.

## M4a: the portfolio simulation, baselines, accounts and lot sizes

**Branch** `feat/sr-m4a-portfolio-simulation`, from M3c's branch.

**Built:**
- **`app/strategy_lab/`**, a new package:
  - **`candidates.py`:** `RunnerSpec` (a strategy, its parameters and overlays, on a timeframe) and `TradeTable` (one coin's trades).
    - `trade_from(i)` is the trade `run_backtest` makes at zero cost from an entry decided on bar i. It replays the strategy's and the overlays' own exits.
    - `candidates()` are the trades from every bar the runner, flat, enters on. That includes the regime gate's context.
    - Each bar's strategy signal is computed once.
  - **`simulate.py`:**
    - `load_universe`: one read per coin and per declared context series, through `exchange_candles`.
    - `Simulation`: the replay at each account size from the same trades, marked at the strategy's closes, with the cooldown.
    - `usd_accounts` (pounds to dollars at a stated rate); `ACCOUNTS_GBP` = (50, 500, 10,000).
  - **`baselines.py`:**
    - REF-HOLD;
    - REF-RANDOM: random entries replayed through the strategy's own exits, the same entries and waits in a random order, `random()` only;
    - `replay_draws`: many draws in one replay, each vetoing the trades that are not its own.
  - **`venue.py`:** today's minimum order and sell step per coin, through the exchange layer.
- **`signal_fusion/evaluation/replay.py`.** Every extension is off unless asked for, and FDS-SIG-004's tests pass unchanged:
  - `mark_s`;
  - `cooldown` (OVL-COOLDOWN's rule per path);
  - `Costs.base_increment` (sells rounded down, the remainder kept and reported);
  - the halt's exposure and its further fall over 30 days.

  **One correction for strategies in general:** an entry that fills at the same open as its own coin's exit is not taken. The backtester ignores ENTER while long. STRAT-001 could never meet this, since it cannot signal ENTER and EXIT at once.
- **The exchange layer:**
  - `lot_increment` on the connector base (unknown);
  - Coinbase, from the public product endpoint `min_order_usd` already reads;
  - the managers, primary first.
- **FDS-SR-001 amended:** REF-RANDOM (§5.4.1) and the lot-size model (§5.10).

### Where the spec was not explicit, or the code said otherwise

| Point | As built | Why |
|---|---|---|
| REF-RANDOM | Random entries replayed through the strategy's own exits; per coin, its number of entries and waits in a random order (FDS-MH-001's R1 idea) | The owner's instruction of 2026-11-07, which replaces §5.4.1's resampled holding periods |
| Lot sizes | Buys in dollars, raised to the minimum entry. Sells in coins, rounded down to the base increment, with the unsellable remainder kept and reported | `pt_exchanges.py`: Coinbase sizes a market buy in `quote_size` and a sell in `base_size`, rounded down. §5.10 had both rounded |
| A forced exit's time | The last bar's close | Its fill is that close. A trade entering on the last bar would otherwise open and close at the same instant. The backtester labels it with the bar's open; the tests allow for that |
| Path-dependent gates | OVL-COOLDOWN is applied by the replay, per path. Gates that read only the market (OVL-REGIME) shape the candidates | A cooldown counts from the path's own last exit |
| Prices for candidates | Raw opens and closes; costs once, in the replay | As FDS-SIG-004's opportunities: (1 + r_g) m(f, e) − 1 |
| `vetoed` in a batch of random draws | Counts the other draws' trades a path does not take | It is the batching's mechanism, not a measure. The draws' results are their net, capital-days and drawdown |

### Tests

`tests/test_strategy_lab.py`, 21 tests:
- **Exactness:** with one coin at 100% and no costs, the replay makes exactly `run_backtest`'s trades for STRAT-001 at 1h, STRAT-002 at 4h with an ATR stop, STRAT-004 with a ratchet, STRAT-005, and STRAT-001 with the cooldown;
- the regime gate's context;
- an entry at its coin's own exit, a case shown to occur in the test's data;
- one load for three accounts (counting the loader's calls);
- the stated rate;
- small accounts: the minimum entry, and the rounded sells with their reported remainder;
- the halt's exposure;
- REF-HOLD;
- **REF-RANDOM:** own exits, counts and waits, seeds, and batch against alone;
- the replay's defaults unchanged;
- the sell step from Coinbase, and primary first.

## M4b: experiment records, the trial log, strategy looks and the reserved months

**Branch** `feat/sr-m4b-experiment-records`, from M4a's branch.

**Built** (`app/strategy_lab/`):
- **`windows.py`:**
  - development 2021-01-01 to 2025-05-06;
  - FDS-MH-001's lockbox 2025-05-06 to 2026-11-06;
  - `development_only`, which refuses any period reaching into the reserved months (E-D7).
- **`looks.py`:**
  - **Strategy looks:**
    - STRAT-001 and STRAT-002 in strategy batch 1's backtest (BTC and ETH, 2023-01-01 to 2026-10-01, which covers the lockbox);
    - STRAT-001 in FDS-SIG-004's development run.
  - **Related looks:** the lab's `rule.high20` (beside STRAT-004) and `rule.mom14` (beside STRAT-005), from FDS-MH-001's phase B timing run, walk-forward only.
  - It reuses `model_lab.catalogue.Look` and `seen_in`.
- **`experiment.py`:**
  - `strategy_record`: every parameter with its defaults, their SHA-256, and the overlays' versions;
  - `freeze`: sealed with its SHA-256, with the code's hashes over `strategies/`, `strategy_lab/`, `backtest/`, `signal_fusion/` and `model_lab/` plus the libraries; never overwritten;
  - `verify`: refuses a changed record, code, libraries or candles;
  - the trial log `<data dir>/strategy_lab/trials.jsonl`, with its kinds and `trial_counts`.

**Nothing is registered.** The mechanism is built and tested on records only. Freezing E1 is M5c, which needs the owner's separate approval.

### Where the spec was not explicit

| Point | As built | Why |
|---|---|---|
| Which trial log | The strategy lab's own (`strategy_lab/trials.jsonl`), not the model lab's | The model lab's counts and kinds (FDS-MH-001 amendment 1) stay as they are; each lab counts its own trials |
| The lockbox's opening ledger | Not built here | FDS-MH-001's final check, which opens the lockbox and would keep that ledger, is not built yet either. The two must share one ledger when either is built (backlog) |
| The trial kinds | strategy, gate, model, forecast, calibration, sizing, exploration | One per kind of finding in §6.2, plus exploratory runs from Settings |

### Tests

`tests/test_strategy_experiments.py`, 10 tests:
- the windows and the reserved months;
- the looks (the existing strategies have seen the lockbox; the new ones have only related signals);
- the strategy record;
- the code hash's coverage;
- freezing once;
- refusing an incomplete declaration;
- `verify` refusing an edited record, changed code, libraries or candles;
- the trial counts, and an unknown kind refused.

## M4c: the model cells

**Branch** `feat/sr-m4c-model-cells`, from M4b's branch.

**Built:** `app/strategy_lab/models.py`. **The strategy and its exits are held constant:** every cell starts from the same candidate trades, and can only veto or shrink them.
- **`forecast_filter`:** a lab model's out-of-fold probability at each trade's decision hour (FDS-MH-001's `probabilities/<key>.npz`).
  - It vetoes below a causal threshold: the q-quantile of every probability before the decision's calendar month, all coins pooled.
  - With no probability at that hour, or fewer than 1,000 before it, it cannot assess, and never vetoes.
- **`meta_filter`:** FDS-SIG-004's F_P or F_PV on this strategy's own trades (`signal_fusion.meta.walk_forward` and `signal_fusion.labels`).
  - Forced trades are never labels, and calibration is out of fold.
  - The payoff tables come from each fold's training trades. The veto acts where the expected value is at most 0.
  - With fewer than 200 events or 200 non-events it is not assessable (D16).
- **`shrink_scales`:** FDS-SIG-004's shrink per trade.
- **`cell`:** one cell's path.
- **`eligible_assessable`, `random_vetoes` (R3), `random_scales` (R3s):** thin wrappers over `signal_fusion.evaluation.baselines`.
- **`development_folds`:** FDS-MH-001's 14 development folds.
- **`label_trades`:** a strategy's trades as FDS-SIG-004's labelled opportunities. `signal_fusion/labels.py` is not changed.

### Where the spec was not explicit

| Point | As built | Why |
|---|---|---|
| A generic filter's threshold | The q-quantile of the model's probabilities before the decision's month | The lab saves probabilities, not its per-fold thresholds. A month-start quantile is causal, and the same for every strategy |
| The shrink where σ̂ is missing | Scale 1 (no shrink) | As the shrink is evaluated in Log only: it fails open |

### Tests

`tests/test_strategy_models.py`, 10 tests:
- the folds;
- the filter's causal threshold, its unassessable cases, and its share of vetoes;
- the meta-model: forced trades, out of fold, the expected-value veto, the event floor;
- **a cell keeps the candidates' own trades:** each kept trade's net is (1 + r_g) m − 1 of its candidate;
- R3 per coin among the eligible candidates, repeatable for a seed;
- the shrink and R3s.

## M5a: "Run a backtest..." and "Compare results..."

**Branch** `feat/sr-m5a-backtest-windows`, from M4c's branch.

**Built:**
- **`strategy_lab/runs.py`, `run(config)`:**
  - refuses a period reaching the reserved months;
  - reads candles once, from far enough back for the warm-up;
  - takes the trades decided in the period, with today's venue minimums and sell steps;
  - replays them in one account against buy-and-hold, cash and random entries (through the strategy's own exits);
  - logs an exploratory trial with its months, and saves `runs/<id>/run.json`.

  A stop between stages saves nothing. `list_runs()` lists the saved runs.
- **`strategy_lab/baselines.py`:** buy-and-hold and the random draws can start at a run's own start.
- **`strategy_lab_ui.py`, `BacktestWindow`:**
  - a strategy enabled for research, with its bounded parameters;
  - stops enabled for research, the candles and the coins in Settings;
  - the period (development only) and the account in pounds with the stated rate;
  - the fee, slippage and random draws.

  It runs off the Tk thread (`ui_jobs`) and can be stopped. It shows the results table, per coin, the facts and the equity line.
- **`strategy_lab_ui.py`, `CompareWindow`:** every saved run, with a search.
- **`strategy_settings_ui.py`:** the buttons "Run a backtest..." and "Compare results..." beside the list. The backtest window uses the research ticks as they are now, saved or not. The coins come from Settings.

### Where the spec was not explicit

| Point | As built | Why |
|---|---|---|
| A stop or filter's parameters in a backtest | Their catalogue defaults | Keeps the window to one strategy's parameters. Tuning stops is out of E-D9's scope |
| The fee's default | 0.50% a side, editable | The account's rate (E-D10's recommendation); the window cannot read the account's tier |
| Random draws | 200 by default, up to 10,000 | Exploratory only. A declared test uses 10 runs × 1,000 |
| The share of random draws at or above | Shown as a fact, not a p-value | An exploratory run is never evidence |

### Tests

`tests/test_strategy_backtest_window.py`, 12 tests:
- **a run:** compares, saves and logs itself; counts only trades in its period; refuses the reserved months; a stopped run saves nothing; the rate and the coins are required;
- only research-enabled entries are offered;
- the window explains wrong inputs and runs nothing;
- a run shows its results; Stop ends a run without saving;
- facts-only words;
- "Compare results..." lists and searches;
- the Strategy window opens both, with its current ticks.

The window was rendered after a run and checked by eye.

## M5b: "Model evidence..."

**Branch** `feat/sr-m5b-model-evidence`, from M5a's branch.

**Built:**
- **`strategy_lab/evidence.py`:**
  - `RECORDED`: STRAT-001's five findings from FDS-SIG-004's development run, copied verbatim from `docs/dev/SIG4-REPORT-dev.md`. A test checks each against the report.
  - `write_results`: a frozen experiment's result lines, sealed and never overwritten.
  - `lines_for(strategy_id)`: both sources, kept apart by kind (prediction, trading, economic).
  - A results file, or its experiment, that changed since it was sealed is not shown.
- **`strategy_lab_ui.py`, `EvidenceWindow`:** one row per finding. With none: "No model has been evaluated with this strategy."
- **`strategy_settings_ui.py`:** "Model evidence..." for the highlighted strategy (disabled for a stop).

**M5c,** the declared first evaluation (E1) and its report, waits for the owner's separate approval to register it, as authorised. Nothing in M5 freezes or runs it.

### Where the spec was not explicit

| Point | As built | Why |
|---|---|---|
| Evidence from before the strategy lab | Recorded in code, verbatim, in a reviewed change (like the looks) | STRAT-001 already has development findings. Showing none would hide them |
| F3's line | The verdict verbatim, with its trades and net added: "(385 trades, net -$131 on $10,000)" | The verdict names only the requirement that failed; the figures are the report's |

### Tests

`tests/test_strategy_evidence.py`, 7 tests:
- STRAT-001's lines match the report verbatim, in kind order;
- the empty case;
- facts-only words;
- a declared experiment's sealed results (shown only with their strategy; never overwritten; hidden once changed);
- an unknown kind refused;
- the button (enabled for a strategy, disabled for a stop).

## Backlog (non-critical)

FDS-SR-001 §13, and:

- **One lockbox opening ledger** shared by FDS-MH-001's final check and FDS-SR-001's, when either is built.
