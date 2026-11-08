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
| M2a | Catalogue lifecycle, authorisation, fail-closed checks | (see M2a) |
| M2b | The strategy list in Settings > Strategy | (see M2b), on M2a |
| M3a | STRAT-004, the daily Donchian breakout | this branch, on M2b |

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

## Backlog (non-critical)

FDS-SR-001 §13. Nothing new yet.
