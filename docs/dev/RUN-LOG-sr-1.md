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
| M2a | Catalogue lifecycle, authorisation, fail-closed checks | this branch |

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

## Backlog (non-critical)

FDS-SR-001 §13. Nothing new yet.
