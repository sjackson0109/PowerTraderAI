# STRAT-004 paper observation: readiness assessment

> **Preparation only. Nothing is enabled.** STRAT-004 is `research` in `app/strategies/catalogue.json:107` at this commit, so the trader refuses it in paper and in live. The authorisation change in section 13 is proposed and has not been applied. No setting, authorisation or trading behaviour was changed to prepare this document.

**Prepared:** 2026-11-08, on `docs/strat-004-paper-readiness`, cut from `main` at `cf858a7` (E1 merged, PR #249).
**For:** the owner's approval before activation.
**Specification:** FDS-SR-001 sections 5.3, 5.7, 5.8, 5.10, 5.11, 6.7, 9 and 12; `docs/dev/RUN-LOG-sr-1.md` (M3a, M6a, M6b, M5c).

**The owner's instruction (2026-11-08).** STRAT-004 is the preferred candidate for operational observation, notwithstanding its failed economic acceptance test. The configuration is:

| Setting | Value |
|---|---|
| Strategy | STRAT-004 (Donchian breakout, version 1.0.0) |
| Entry lookback | 55 days |
| Exit lookback | 20 days |
| Timeframe | Daily (`1d`) |
| Regime gate | Disabled (no OVL-REGIME) |
| Predictive models | Disabled (no model filter, no LLM signal, entry assessment Off) |
| Strategy parameters | Original defaults (55/20, the Turtle System 2 rule, not tuned) |
| Trading mode | Paper only |
| Live trading | Prohibited |

**What every record of this observation must say.** E1 (`docs/dev/sr1-e1/SR1-E1-REPORT-dev.md`), development period only:
- **S1 passed:** STRAT-004 beat random entries with its own exits. Its return per capital-day was +0.2882% against a random median of +0.0104% (p = 0.0065, Holm over 4, B = 10,000, 135 trades); on the account, that was +12.56% over the period.
- **S3 failed:** STRAT-004 was not shown to be profitable after fees at £10,000 and 0.50% + 0.05%. It lost $116.89 in the first half. Its net over the period was +$1,692.94: +12.56% of the account (2.76% a year) at a return per capital-day of +0.2882%, with 2.6% of the account committed on average. The profit came from the five coins listed after 2021 (+$1,749 against −$56 on the six older coins).
- **Paper evidence is operational:** does paper do what the backtest says? It is not a forward confirmation, and it cannot show profitability.

---

## 0. Summary

**Verdict: ready with caveats.** The authorisation controls fail closed, and backtest–signal parity holds on closed daily bars. One defect (D1) can delay or skip a daily decision when the exchange publishes a bar late. It should be fixed before the segment starts. Reconcile needs manual checks for exits, fees and duplicates. The evidence will be operational only: STRAT-004 passed S1 and failed S3.

| # | Item | Status | Evidence, in one line |
|---|---|---|---|
| 1 | Authorisation controls and fail-closed behaviour | Ready | `research` is refused in both modes at the settings check and at the order gate (`pt_trader.py:1788-1807`). A replayed paper session places no orders (new test). Unknown values are refused. |
| 2 | Paper eligibility under §6.7 | Ready (proposal) | Both evidence conditions of §6.7 are met: the M3a tests pass, parity test included (14 passed), and E1 has reported. The owner's decision is the third condition. |
| 3 | Backtest-to-signal parity | Ready with caveats | The engine and a replayed runner agree on every closed daily bar. A replayed paper trader fills on the backtester's bars, and Reconcile matches every trade (new test). D1: a late bar can skip a decision. |
| 4 | Sizing, minimum order, lot size, residual | Ready with caveats | Each entry is 1% of the account, raised to the minimum only when below it. Each sell is the whole quantity bought (new test). Paper rounds no sells and leaves no residual; live would leave one. |
| 5 | Stops, position limits, risk controls | Ready with caveats | There is no stop by design. There is one position per coin, the 10% coin budget, and the 8% halt, which persists until Resume. DCA and trailing are off. A halt leaves positions open. |
| 6 | Segment with a frozen configuration hash | Ready with caveats | The hash for the proposed settings is `b0e54cdf…e1cc70`, computed in a sandbox with `observation.snapshot` and pinned by a test. Not frozen: the LLM signal mode, the exchange order and the code version (D2, D7). |
| 7 | Reconciliation procedure | Ready with caveats | Reconcile matches entries, entry fills and entry fees. It does not show exits, exit fees, duplicates or refused orders, so section 7 adds manual steps and proposes a tool (D4). |
| 8 | Criteria for missed, delayed, duplicated, unexpected trades | Ready | Definitions, thresholds and the source of each check are in section 8. Reconcile hides duplicated entries, and a delay within a candle shows as matched (D4). |
| 9 | Start, end and termination | Ready | Section 9 gives the sequence: start flat, start the segment before 00:00 UTC and the trader after it, plus the triggers to end the segment. |
| 10 | Duration and trade-frequency limits | Ready (proposal) | About 31 entries a year (15.5 expected in 6 months, 90% range 9 to 22). Proposed: at least 6 months and 15 round trips, capped at 12 months. |

**Defects found** (none fixed; section 11 gives the evidence and the smallest fixes):

| ID | Defect | Severity | Proposed before the start? |
|---|---|---|---|
| D1 | The signal engine treats a frame without the just-closed bar as current, and does not fetch again until the next bar. A late daily bar delays every decision by a day, or skips one. | High | Yes |
| D2 | The segment does not freeze `llm.signal_mode` (it can confirm or veto entries) or the exchange order (`trading_config.json`: quotes, fees, minimums, candles). | Medium | Yes, or check by hand |
| D3 | A change is noticed only when the Observation window opens or reconciles. A change that is reverted in between is never noticed, and Reconcile does not check each row's strategy fields. | Medium | Check by hand |
| D4 | Reconcile hides duplicated entries, shows a same-candle delay as matched and open trades as "Different candle", and omits exits, exit fees, assumed fees, residuals and refused orders. | Medium | Manual steps; tool later |
| D5 | `trader_status.json` reports `blocked: null` ("SIGNALS: STRAT-004 1d") while every order is refused for authorisation. The hub's strip is correct. | Low | No |
| D6 | The Observation window shows neither the segment's SHA-256 nor its frozen settings, so the owner cannot check them in Settings. | Low to medium | Preferred |
| D7 | The segment records no code version. An update of the owner's checkout during the segment is invisible. | Medium | A code freeze, or end the segment at each update |

---

## 1. Strategy-authorisation controls and fail-closed behaviour

**Status: Ready.**

**Evidence (code).**

| Control | Where | What it does |
|---|---|---|
| STRAT-004's authorisation | `app/strategies/catalogue.json:107` | `"authorisation": "research"` |
| Allowed values | `app/strategies/catalogue.py:56-61` | `research`, `paper`, `live`. Paper mode allows `paper` and `live`; live mode allows `live` only. |
| A missing or unknown value | `catalogue.py:243-245`, `202-203` | The catalogue refuses to load (`CatalogueError`), so nothing that imports `strategies` starts. |
| Unknown id or mode | `catalogue.py:312-320` | `allowed_in_mode` is False for an unknown id, an unknown mode or `None`. |
| Settings with a mode | `app/strategies/settings.py:115-126`, `201-206` | Every strategy and overlay is checked. A refusal is a `problem`, never replaced by a default. |
| Permitted timeframe | `settings.py:171-177` | STRAT-004 may trade on `1d` only (`catalogue.json:97`). |
| Order gate | `app/pt_trader.py:1788-1807` | Before every buy and sell, the settings are read with the trader's pinned mode. On a problem: "ORDER REFUSED", and no price lookup. |
| Each pass | `pt_trader.py:2300-2310` | With a problem, catalogue mode is off and a warning says no orders will be placed. Any order is still refused at the gate. |
| Trading mode | `app/trading_mode.py:1-19`, `249-284` | Anything other than exactly "live" is paper. Live without a broker is refused at start-up. A mode change while running stops all orders (`pt_trader.py:2284-2291`). |
| Settings > Strategy | `app/strategy_settings_ui.py:52-61`, `256-273` | "Use for trading" is offered only where the authorisation covers the trading mode. |

**Evidence (tests, run on this branch).**

| Test | Result |
|---|---|
| `tests/test_strategy_lifecycle.py` (the mode matrix, a refused research strategy, byte-identical orders with and without the check, a research strategy places no orders) | 18 passed, 201 subtests |
| `tests/test_strategy_breakout.py::CatalogueTests` (STRAT-004 research-only, refused in both modes) | passed (in 14) |
| `tests/test_strategy_catalogue_view.py` (Use for trading only where allowed) | 15 passed |
| New `tests/test_strat004_paper_readiness.py::TodayTests` (refused in paper and live, with both forms of the mode; an unknown authorisation or mode refused; with `paper` it is still refused in live) | 5 passed, 7 subtests |
| New `PaperSessionTests::test_today_a_paper_session_places_no_orders` (a replayed daily paper session: no orders, no rows) | passed |
| New `PaperSessionTests::test_with_paper_authorisation_a_research_overlay_is_still_refused` (STRAT-004 at `paper` with OVL-REGIME: no orders) | passed |

**A scratch check (not committed).** It ran one trader pass with the proposed settings on today's catalogue. Each order attempt printed `ORDER REFUSED: invalid strategy configuration: STRAT-004 can be used for research only, not paper trading`, and `_gate_or_refuse()` and `place_buy_order()` both returned `None`.

**Gaps.**
- **D5.** In that same check, `trader_status.json` showed `{"blocked": null, "note": "SIGNALS: STRAT-004 1d"}`.
  - The cause: `_signals_status` (`pt_trader.py:2048-2053`) and `SignalEngine.settings` (`signal_engine.py:102-104`) read the settings without a mode.
  - The hub's strip is correct, because it passes the mode (`pt_hub.py:6226`).
  - No order is affected.
- **A refusal freezes positions.** With a refused configuration, every sell is refused too, so a held position is not exited. That is fail-closed, but if a refusal appeared during the segment (for example if the authorisation were reverted), open positions would stay unmanaged. Section 9 makes this a termination trigger.

## 2. Proposal for paper eligibility under FDS-SR-001 §6.7

**Status: Ready (proposal for the owner's decision).**

§6.7 requires three things to raise a strategy to `paper`. The record must state the result the strategy had (§6.7: "a strategy need not have passed its tests to be observed in paper").

| §6.7 condition | Met? | Evidence |
|---|---|---|
| Its milestone's tests pass, including the backtest–paper parity test | Yes | `tests/test_strategy_breakout.py`: 14 passed. That covers hand-worked signals, ties, warm-up, calendar days, no look-ahead, bounds, and `ParityTests.test_the_signal_engine_and_a_replayed_runner_agree_on_every_bar` (the live signal engine against a replayed runner on every closed daily bar). Also `tests/test_strategy_lab.py` (21 passed): with one coin at 100%, the replay makes exactly `run_backtest`'s trades for STRAT-004. |
| A declared development evaluation has reported, whatever its result | Yes | E1 (`SR1-E1`, frozen 2026-11-08T12:38:00Z, SHA-256 `ba060bb6006ec8620dcc96a4357c673ea58318248bdce216ae0b0eff092acecb`), merged in PR #249 (`cf858a7`). |
| The owner decides | Pending | This document asks for that decision (section 14). |

**Proposed record text** (for the authorisation PR and the run log):

> STRAT-004 version 1.0.0 (Donchian breakout, daily, entry 55 days, exit 20 days, parameter SHA-256 `89579608ee854d67afce197674141a23848b1adb3bcca6b5096d72dcfd726265`) is raised from `research` to `paper` on the owner's decision of [date], for operational observation in paper only.
>
> **Evidence.** Its M3a tests pass, including the backtest–paper parity test, and the declared development evaluation E1 has reported.
> - **S1 passed:** it beats random entries with its own exits (return per capital-day +0.2882% against a random median of +0.0104%, p = 0.0065, Holm over 4, 135 trades; +12.56% of the account over the period).
> - **S3 failed:** it was not shown to be profitable after fees at £10,000 and 0.50% + 0.05%. It lost $116.89 in the first half. Over the period it made +12.56% of the account (2.76% a year) at +0.2882% a capital-day, with 2.6% of the account committed on average, and the profit came from coins listed after 2021.
>
> **Limits.** Paper evidence is operational only. It is not a forward confirmation and cannot show profitability. Live trading stays prohibited: §6.7 gives no route to `live` without a passed final check on unseen months under a later spec.

**What does not change:** the version (1.0.0), the defaults, the bounds, `timeframes_permitted`, the research tick (`strategy.research_enabled`), STRAT-005, OVL-REGIME and every other entry. FDS-SR-001 §5.2 raises the version only for a change to a rule or a default, and the authorisation is neither. E1's frozen code hashes cover the `.py` files only (`docs/dev/sr1-e1/experiment.json`), so E1's sealed evidence is unaffected.

## 3. Backtest-to-signal parity

**Status: Ready with caveats.**

**Evidence.**

| Check | Where | Result |
|---|---|---|
| The rule reads closes only, a tie is not a breakout, and the window is exactly 56 bars | `app/strategies/breakout.py:63-77`; `RuleTests` | passed |
| No look-ahead: appending bars never changes an earlier decision | `LookAheadTests` (2) | passed |
| The live signal engine agrees with a replayed runner on every closed daily bar (action, reason, bar time) | `ParityTests.test_the_signal_engine_and_a_replayed_runner_agree_on_every_bar` | passed |
| The backtester enters at the next open after a breakout | `ParityTests.test_the_backtester_enters_at_the_next_open_after_a_breakout` | passed |
| A forming bar is never evaluated, even if the provider returns it | `tests/test_signal_engine.py::EngineTests::test_forming_bar_is_never_evaluated_even_if_a_provider_returns_it` (in 38 passed) | passed |
| The replay (the engine behind E1 and Reconcile) reproduces `run_backtest`'s trades | `tests/test_strategy_lab.py` exactness tests | passed (21) |
| **End to end, new:** with `paper` in memory, the real paper trader runs bar by bar, seeing each daily bar 10 s after it closes. Every ENTRY and EXIT fills on the backtester's own bars (the next open, +10 s), and every row names STRAT-004 at its defaults. | `PaperSessionTests.test_with_paper_authorisation_paper_trades_where_the_backtest_does` | passed |
| **End to end, new:** Reconcile on that session's own rows: every trade matched, none missed or extra. The fill against the open is +0.05% (the quote), and the fee 0.50% a side. | `PaperSessionTests.test_reconcile_matches_every_trade_with_its_fill_and_fee` | passed |

**Gaps and caveats.**
- **D1: a late daily bar.** This is the main caveat.
  - **The cause.** `SignalEngine._get_candles` (`app/signal_engine.py:349-351`, `365-367`) stores whatever the provider returns as the frame for the expected bar. If the first fetch after 00:00 UTC lacks the bar that just closed, the engine does not fetch again until the next day. No test covers a late bar: the parity tests' providers serve each closed bar at once, and the stuck-feed tests check only the staleness limit.
  - **Reproduction** (`docs/dev/strat-004-readiness/late_daily_bar.py`, output beside it). When the exchange is 5 s late at every boundary, each decision is made a day late. When it is late once, the breakout bar is never decided: the replay enters on 2024-03-11, and the engine decides 2024-03-10, 2024-03-12 and 2024-03-13, with no ENTER_LONG.
  - **Not observed live.** Whether Coinbase is ever that late at 00:00 UTC is not known.
  - **Effect.** Reconcile would show such trades as "Different candle" or "Not placed".
- **Stale or missing candles hold, exits included.** A last bar more than 2 days old (`signal_engine.py:305-318`) or no candles at all gives HOLD, so an exit can be delayed.
- **Fallback exchanges.** Candles come from the first exchange in Settings that can serve the range (`market_data/candles.py:436-508`). The exchange used is not logged with the decision, so a decision made on another exchange's bars cannot be told apart. Reconcile replays from the same per-exchange cache.
- **Missing daily bars.** STRAT-004 counts bars (run log M3a). A gap widens its channel by a day but does not freeze it, unlike STRAT-005 (E1 §13.4). E1's daily series had no gaps.

## 4. Order sizing, minimum order, lot size and residual balance

**Status: Ready with caveats.**

**How an entry is sized** (paper mode, the proposed settings):
1. The amount is `start_allocation_pct` (1%) of the account value: cash plus holdings at the bid (`app/position_sizing.py:91-106`; `pt_trader.py:2103-2123`).
2. Below the exchange's minimum order, it is raised to minimum × (1 + spread + 2 × taker fee + 2% margin) (`position_sizing.py:74-88`). The minimum comes from the exchanges in Settings, primary first (`pt_trader.py:2080-2091`).
3. The risk gate allows a buy up to 10% of the account (`max_coin_allocation_pct`), and always allows the raised minimum (`pt_trader.py:1764-1771`, `402-423`).
4. The quantity is dollars ÷ the current ask, rounded to 8 decimals (`pt_trader.py:2187`). Paper fills a market buy at the ask (`trading_mode.py:760-806`).

**How an exit is sized:** the smaller of the holding and the quantity the ledger says the trader bought (`pt_trader.py:2007-2015`). Paper fills a market sell at the bid.

**The figures at E1's deciding account and venue** (`docs/dev/sr1-e1/experiment.json`, venue read 2026-11-08):

| | £10,000 ($13,476) | $10,000 (paper default) |
|---|---|---|
| Entry at 1% | about $134.76 | about $100.00 |
| Coinbase minimum order (all 11 coins) | $1.00 | $1.00 |
| Raised to the minimum? | No (E1: 0 of 135 entries raised) | No |
| Coinbase sell step | DOGE 0.1, LINK 0.01, XRP 0.000001, others 0.00000001 | the same |
| Unsold remainder, in E1's replay | $1.09 over 135 trades | — |

**Evidence (tests, run on this branch).**

| Test | Result |
|---|---|
| `tests/test_position_budget.py` (1% entry, raised to the minimum, a small account trades at the minimum, the 10% budget, primary-first minimums) | 41 passed |
| `tests/test_entries_above_minimum.py` (the floor with spread, fees and margin; one entry per signal at the minimum; remainders are dust) | 25 passed |
| `tests/test_paper_fees.py` (taker rate of the exchange that priced the fill; fees in cost basis) | 20 passed |
| New `PaperSessionTests.test_with_paper_authorisation_paper_trades_where_the_backtest_does` | The first entry is $100.00 (1% of $10,000). Every sell is the whole quantity bought, with `closes_position` true, and the strategy holds nothing at the end. |

**Gaps.**
- **No residual in paper.** Paper rounds no sell to the exchange's step and enforces no minimum (`app/pt_paper_trading.py:290-363`: `_validate_order_risk` accepts every size), so a paper exit leaves no remainder. Coinbase would round a live sell down to its step and leave one (FDS-SR-001 §5.10). At about $135 an entry the difference is cents, and E1 modelled it.
- **Below the minimum.** A paper account below about $100 would raise every entry to the minimum (E1's £50 account: 135 of 135 raised). That is not proposed here.

## 5. Stop behaviour, position limits and risk controls

**Status: Ready with caveats.**

| Control | Behaviour with the proposed settings | Evidence |
|---|---|---|
| Stop | None. No overlay is selected, so the only exit is STRAT-004's: a close below every close of the previous 20 days, decided once a day on the closed bar and sold at market at the next open. Nothing limits a loss between two closes. E1's largest single loss was $73.63. | `breakout.py:73-74`; `strategies/runner.py:301-344` |
| One position per coin | A held coin is skipped for entries. An ENTER while long is ignored. | `pt_trader.py:2956-2959`; `runner.py:281-299` |
| DCA and the trailing profit margin | Off in catalogue mode: the strategy block ends with `continue`. | `pt_trader.py:2629-2682`; `test_signal_engine.py::test_legacy_dca_and_trailing_pm_are_off_in_catalogue_mode` (passed) |
| Positions the trader did not open | Never sold by the strategy. | `test_a_position_the_trader_did_not_open_is_never_sold_by_the_strategy` (passed) |
| Max per coin | 10% of the account at cost for a buy; the minimum is always allowed. | `pt_trader.py:1764-1771`; `test_position_budget.py::test_a_buy_past_the_coins_budget_is_refused_by_the_risk_gate` (passed) |
| Account drawdown | Warning at 3%, critical at 5% and the emergency stop at 8% of the peak the trader has seen. The stop halts trading: no orders, no exits. It persists across restarts until "Resume trading" in Settings > Risk. | `pt_trader.py:425-450`, `3117-3153`; `tests/test_risk_state.py` (24 passed, including `test_a_restart_after_an_emergency_stop_does_not_trade_until_resume`); `tests/test_risk_settings_ui.py` (34 passed) |
| The peak at the start | Saving Settings > Paper Account clears the paper peak (a halt stays). | `pt_hub.py:7600-7610` |
| Stale prices | Under the `pause` policy, a quote older than 30 s rejects the order (`PRICE_UNAVAILABLE`), and the next pass tries again. | `trading_mode.py:638-692`; `pt_trader.py:1860-1870` |
| Repeated order ids | A fill already in the books is not recorded twice. | `pt_trader.py:1873-1883` |
| A research overlay | Refused even with STRAT-004 at `paper`. | New test, passed |

**E1's figures for these controls** (development only, £10,000): maximum drawdown 7.32% (the 8% halt was not reached); peak capital committed 10.95%; mean 2.64%.

**Gaps.**
- **The halt manages nothing.** At 7.32% in development, the halt is close enough to matter. If it is reached, positions stay open and unmanaged until the owner resumes (FDS-SR-001 §9 item 7). Section 9 makes the halt a termination trigger.
- **No protective stop.** That is by design (original defaults, no overlays), and it is stated in the record.

## 6. The observation segment and its frozen configuration hash

**Status: Ready with caveats.**

### 6.1 The proposed settings

| Setting | Value | Where it is set | In the snapshot? |
|---|---|---|---|
| Trading mode | Paper | Settings > Trading | Yes (`trading.mode`) |
| Strategy | STRAT-004, "Use for trading" | Settings > Strategy | Yes |
| Parameters | Defaults (55, 20): saved as no entry under `strategy.params` | Settings > Strategy, "Reset to defaults" | Yes |
| Timeframe | 1 day | Settings > Strategy | Yes |
| Stops and gates | None ticked (no OVL-REGIME) | Settings > Strategy | Yes (`overlays: []`) |
| Entry assessment, volatility size reduction, entry limits | Off | Settings > Strategy, Settings > Risk | Yes (`signal_fusion`) |
| LLM signals | Off | Settings > LLM | **No (D2)** |
| Coins | BTC, ETH, XRP, DOGE, SOL, ZEC, DASH, ADA, AVAX, LINK, LTC: E1's 11, in E1's order (an owner decision, section 14) | Settings > Trading | Yes |
| Paper trading coins | Inherit | Settings > Paper trading | Yes |
| Start allocation, max per coin, minimum order margin | 1%, 10%, 2% | Settings > Risk | Yes |
| Drawdown levels | 3%, 5%, 8% | Settings > Risk | Yes |
| Paper fills | `pause`, quotes at most 30 s old | Settings > Paper trading | Yes |
| Exchange order | Coinbase first, as E1 (Coinbase, Kraken, KuCoin, Binance) | Settings > Exchanges > Configure Exchange APIs... | **No (D2)** |
| Paper account | Reset, no positions, $13,476 (£10,000 at E1's rate) or $10,000 (an owner decision) | Settings > Paper trading > Paper Account... | No (the book, not a setting) |
| Code | The commit the owner's app runs from | — | **No (D7)** |

### 6.2 The hash and its inputs

The hash was computed with `strategy_lab.observation.snapshot()` and `digest()` (`app/strategy_lab/observation.py:73-89`), in a sandbox with its own `POWERTRADER_HOME`, `APPDATA` and `LOCALAPPDATA`. No real settings file was read. The inputs are a fresh install's defaults (`pt_settings_manager.DEFAULT_SETTINGS` for `risk` and `paper`, `pt_hub.DEFAULT_SETTINGS` for the sizing and legacy keys) with the changes above. Script and output: `docs/dev/strat-004-readiness/snapshot_hash.py` and `snapshot_hash.txt`. The test `SnapshotTests` pins the hash, and pins the defaults it assumes.

**The frozen snapshot (canonical JSON, the text `digest()` hashes):**

```
{"config":{"paper":{"max_quote_age_s":30,"price_fallback_policy":"pause"},"risk":{"drawdown_critical_pct":5.0,"drawdown_warning_pct":3.0,"emergency_drawdown_pct":8.0},"signal_fusion":null,"strategy":{"active_id":"STRAT-004","engine":"catalogue","overlays":[],"params":{},"timeframe":"1d"},"trading.mode":"paper"},"gui":{"coins":["BTC","ETH","XRP","DOGE","SOL","ZEC","DASH","ADA","AVAX","LINK","LTC"],"dca_levels":[-2.5,-5.0,-10.0,-20.0,-30.0,-40.0,-50.0],"dca_multiplier":2.0,"max_coin_allocation_pct":10.0,"max_dca_buys_per_24h":2,"min_order_margin_pct":2.0,"paper_coins":[],"paper_coins_mode":"inherit","pm_start_pct_no_dca":5.0,"pm_start_pct_with_dca":2.5,"start_allocation_pct":1.0,"trade_start_level":3,"trailing_gap_pct":0.5}}
```

| Hash | Value |
|---|---|
| **Snapshot SHA-256** (the entry assessment never saved: `signal_fusion` absent) | `b0e54cdfdd2a1615b0cf779d6f819101dd035a0b11ff2814830736a1efe1cc70` |
| Snapshot SHA-256, if Settings > Strategy has saved the entry assessment, all Off (`{"entry_assessment":"off","participation_cap":"off","participation_pi":0.01,"spread_cap":"off","spread_max":0.005,"volatility_shrink":"off"}`) | `a446295996744388dc4379c5c481559452b62881cb94191636f237db404f344f` |
| STRAT-004's parameter SHA-256 (`{"entry_days":55,"exit_days":20}`, in every trade row as `strategy_params_sha256`) | `89579608ee854d67afce197674141a23848b1adb3bcca6b5096d72dcfd726265` |

Both values were checked with `sha256sum` on the canonical text. Reconcile reads the frozen strategy back from this snapshot as `RunnerSpec("STRAT-004", {}, (), "1d")`, that is STRAT-004 at its defaults.

### 6.3 How to check that a started segment matches

The segment's hash equals the one above only if the frozen parts of the owner's two settings files hold exactly these values. That includes number formats (30 against 30.0) and any keys an earlier save left in the `strategy` section, such as another strategy's saved parameters or `research_enabled`. So the check works on two levels:
1. **At the start.** Read the new segment file, `<hub>/paper/observations/<id>.json`, which holds `snapshot` and `sha256`. If `sha256` equals `b0e54cdf…` (or `a4462959…`), the settings are exactly as proposed. If it does not, compare the file's `snapshot` with 6.2 key by key. The deciding values must match: `trading.mode`, `strategy.active_id`, `engine`, `timeframe`, STRAT-004's absence from `params`, `overlays`, `signal_fusion` (absent or all Off), `risk`, `paper` (values, not formats), `coins`, `paper_coins_mode`, `start_allocation_pct`, `max_coin_allocation_pct` and `min_order_margin_pct`. Any other differences must be recorded. The legacy keys (`dca_*`, `pm_*`, `trailing_gap_pct`, `trade_start_level`) do not decide a catalogue trade.
2. **During the segment.** The segment's own `sha256` is then the frozen reference. Opening the Observation window compares the settings files with it, and ends the segment on any difference (`observation.py:174-190`).

Until D6 is fixed, the window does not show the hash or the frozen settings. The lead reads the segment file and records the hash in the observation log.

### 6.4 Gaps

- **D2.** `llm.signal_mode` is not in the snapshot (`observation.py:46`). A change to Confirm or Veto would change entries without ending the segment. The existing test `test_an_unrelated_setting_changes_nothing` treats `llm` as unrelated. The exchange order is in `trading_config.json` (`pt_multi_exchange.py:737-747`), which `read_current()` does not read (`observation_ui.py:56-74`). That order decides the paper quote, the fee (FDS-SR-001 §5.11's "fee source"), the minimum and the candles.
- **D3.** `check` runs only when the window opens or reconciles (run log M6b). A change made and reverted between two openings is never seen.
- **D7.** The snapshot records no code version. The owner's app runs from the checkout, so every merged PR changes the trader's code without ending the segment.
- **Conservative by design.** Any change in the `strategy` section ends the segment, even a research tick or another strategy's saved parameters.

## 7. Reconciliation procedure

**Status: Ready with caveats.**

### 7.1 What Reconcile does today

Settings > Paper trading > Observation... > "Reconcile..." (`observation_ui.py:110-115`, `observation.py:325-376`):
1. It loads the segment's closed daily candles, with warm-up, through the exchange layer and its cache.
2. It replays them through the frozen strategy, one trade after another, flat after each exit.
3. It pairs each replayed trade with the paper trades: ENTRY buys and EXIT sells from `<hub>/paper/trade_history.jsonl`.

| Result | Meaning |
|---|---|
| Matched | The paper entry and exit filled in the replay's candles |
| Different candle | Within 3 candles of the replay's entry, not in the same candles |
| Not placed | A replayed trade with no paper trade within 3 candles (no reason recorded) |
| Extra | A paper trade with no replayed trade within 3 candles |

For each matched or different-candle trade it also reports two figures:
- **Paper fill vs replay open:** paper's entry price ÷ the replay's entry open − 1.
- **Paper fee a side:** the entry's `fees_usd` ÷ (quantity × price).

**Verified on this branch.**
- `tests/test_observation.py` passed (7). On a real replayed paper trader's rows, the new `test_reconcile_matches_every_trade_with_its_fill_and_fee` passed: every trade matched, the fill at +0.05%, the fee at 0.50%.
- A probe on synthetic rows (`docs/dev/strat-004-readiness/reconcile_probe.py`, output beside it) showed what Reconcile does not report:

| Case | What Reconcile shows |
|---|---|
| Two ENTRY buys for one entry, one sell | 1 matched, 0 extra: the duplicate is hidden (`observation.py:247-248` overwrites the first buy) |
| An entry filled 20 hours late, in the same candle | Matched; only "Paper fill vs replay open" (+3.0%) hints at the delay |
| An exit fee of 1.20% against an entry fee of 0.50% | Only the entry fee is shown (`Row` has no exit fee, `observation.py:207-216`) |
| A trade still open | "Different candle" (the replay closes it at the last close) |
| Rows placed by another strategy on the replay's candles | Matched (rows' `strategy_id` is not checked) |

### 7.2 The procedure

**Weekly, and at the end.** Steps 1 to 5 use Settings and the hub's tabs. Steps 6 to 9 need the files or the trader's log until the proposed tool exists (7.3).

1. **Settings.** Open Settings > Paper trading > Observation.... The status must read "Observing since … UTC". If it reads "ended: settings changed: …", the segment has ended: record when and why, and follow 9.3. Confirm by eye that Settings > LLM signal mode is Off and that Coinbase is still first in Settings > Exchanges (D2).
2. **Reconcile.** Press "Reconcile..." and record the four counts.
3. **Classify each row** by section 8's criteria:
   - **Not placed:** find the reason in the trader's log for that coin and day (step 7).
   - **Extra:** if its entry is in the newest candle, it is pending until that candle closes. Otherwise it is unexpected.
   - **Different candle:** if the trade is still open in Current Trades, it is open. Otherwise it is delayed.
   - **Matched:** the delay is "Paper entry" minus "Replay entry", in minutes.
4. **Exits** (not in Reconcile). In Trade History, filter Source = Strategy. For each sell, record its time against Reconcile's "Replay exit". Record its price against that candle's open, from the chart's daily candles.
5. **Fees and quantities** (Trade History). For every Strategy row, the fee rate is Fees ÷ Value. Compare it with the fee the segment assumed. That is the account's taker rate when Coinbase keys are set (0.50% at 2026-11-05, read by an authenticated call that already exists, `pt_exchanges.py:2079-2098`), else Coinbase's standard 1.20% (`trading_mode.py:717-741`). E1 assumed 0.50% + 0.05% slippage. For each coin, the quantity sold must equal the quantity bought.
6. **Strategy fields.** Every row in the segment must carry `strategy_id` STRAT-004, `strategy_version` 1.0.0, `strategy_params_sha256` `89579608…6265`, `strategy_timeframe` 1d and `strategy_overlays` []. Read them from `<hub>/paper/trade_history.jsonl`, the lead's step until the tool exists. Any other value is an unexpected trade (D3).
7. **Orders against fills.** Every ENTRY and EXIT row is a fill. Refused and rejected orders exist only in the trader's log (`pt_trader.py:1797-1806`, `1860-1870`). The paper book keeps cash and positions but no orders (`trading_mode.py:972-995`). Search the log for the coin and day: "ORDER REFUSED", "ORDER REJECTED", "RISK BLOCK", "No price available", "STALE", "CANDLES_UNAVAILABLE", "TRADING HALTED". The log rotates at 10 MB × 5 files (`pt_logging.py:180-212`), so copy the relevant lines at each weekly reconcile.
8. **Decisions.** The trader logs one line per coin per daily bar: `Decision <coin>: strategy=STRAT-004 action=… bar=…` (`signal_engine.py:412-434`). Spot-check that each coin has one line for the last closed bar. If a coin has none, or one for an older bar after about 00:05 UTC, that is D1 or stale candles.
9. **Record.** Add the week to the observation log: the counts, every non-matched row with its class and reason, the delays (median and maximum), fees by side, residuals, and the segment's `sha256`.

**P&L.** If it is shown at all, give return per capital-day and the account's return together, labelled "operational only, not evidence of profitability".

### 7.3 Gaps, and the proposed tool (not built)

**D4.** Reconcile compares entries only. A "Reconcile (full)" view would add:
- the exit fill against the replay's exit open, and the exit's delay;
- the fee on each side against the fee assumed;
- the delay within the candle, in minutes after the replay's fill time;
- duplicated entries (a second ENTRY buy before an exit) and repeated exits;
- rows whose strategy fields differ from the frozen strategy (D3);
- an open trade labelled "Open", and the newest candle's entries labelled "Pending";
- quantity bought against quantity sold (residual);
- the paper trading coins, not the Settings coins, as the replay's universe (`observation_ui.py:112`);
- the reason for each missed entry, from a structured record of refused entries and rejected orders (the run log's backlog item "Refused entries recorded");
- the segment's SHA-256 and frozen settings in the window (D6).

Each of these is read from records that exist, or would exist after the backlog item. None changes an order.

## 8. Criteria for reporting missed, delayed, duplicated and unexpected trades

**Status: Ready.**

| Class | Definition | Where it is detected | Reported |
|---|---|---|---|
| On time | The paper fill is in the replay's candle, no later than 15 minutes after the replay's fill time (00:00 UTC, the next open), and the exit likewise | Reconcile "Matched" plus the delay (7.2 steps 3 and 4) | Counted |
| Delayed | In the replay's candle but more than 15 minutes late; or "Different candle" for a closed trade (1 to 3 candles late) | Reconcile, Trade History | Each one, with its delay and cause (D1, stale candles, price unavailable, cash, trader not running) |
| Missed | Reconcile "Not placed": a replayed entry, or a replayed exit, with no paper fill within 3 candles | Reconcile; exits by 7.2 step 4 | Each one, with its reason from the log: cash, minimum, price unavailable, halt, candles stale or unavailable, late bar (D1), settings refused, trader not running, other |
| Duplicated | More than one ENTRY buy for a coin between two exits; more than one EXIT sell for one entry, other than the rest of a partial fill; or one order id twice | Trade History by coin (Reconcile hides it, D4) | Each one, at once |
| Unexpected | Reconcile "Extra" that is not pending; any segment row whose strategy fields differ from the frozen ones; any DCA, trailing-margin or neural entry; any live order | Reconcile, the rows' fields, Trade History "Source" | Each one, at once |
| Pending or open | An entry in the newest candle (the replay needs the next candle), or a trade still open | Reconcile ("Extra" / "Different candle") | Not a finding; re-checked next week |

**Thresholds.**
- **End the segment and investigate:** any duplicated trade; any unexplained unexpected trade; any live order.
- **Review with the owner:** two or more unexplained missed trades in a month, or any delay of a day or more. A known cause still counts: D1, if not fixed, is recorded as the cause, not excused.
- **Rates in the final report:** each class's count over the replayed trades, with an exact 95% upper bound (for zero events in n: 1 − 0.05^(1/n)).

## 9. Start, end and termination

**Status: Ready.**

### 9.1 Before the start

1. The owner approves this assessment and the authorisation change (section 13). The change is merged as a reviewed PR that cites the record in section 2.
2. The owner decides on D1, D2, D3, D6 and D7 (section 14). If fixes are chosen, they are merged first.
3. Record the commit the owner's app will run from. Then hold merges that touch the trading path for the segment's life (D7): `app/pt_trader.py`, `app/signal_engine.py`, `app/strategies/`, `app/trading_mode.py`, `app/pt_paper_trading.py`, `app/position_sizing.py`, `app/market_data/`, `app/pt_exchanges.py` and `app/pt_multi_exchange.py`. If that is not acceptable, every such merge ends the segment (9.3).

### 9.2 The start, in this order

1. **Stop the trader.**
2. **Settings > Trading:** mode Paper; the hub shows "MODE: PAPER". Set the coins (6.1).
3. **Settings > Exchanges > Configure Exchange APIs...:** Coinbase first, as in E1. Record the order.
4. **Settings > Strategy:**
   - highlight STRAT-004 and press "Use for trading";
   - choose 1 day and press "Reset to defaults";
   - leave every stop and gate unticked, and the entry assessment Off;
   - press Save.

   **Settings > Risk:** start allocation 1%, max per coin 10%, minimum order margin 2%; the volatility size reduction and entry limits Off; drawdown levels 3, 5 and 8. **Settings > LLM:** signal mode Off.
5. **Settings > Paper trading:** paper coins Inherit; then "Paper Account...". Reset to the chosen balance with no positions. This backs up the paper history and clears the paper peak. If Settings > Risk shows a halt, press "Resume trading".
6. **Check:**
   - Current Trades shows no open positions;
   - the hub strip reads "SIGNALS: STRAT-004 1d";
   - Settings > Strategy shows STRAT-004 as "Paper" and "In use".
7. **Start the segment.** In the last hour before 00:00 UTC, press Settings > Paper trading > Observation... > "Start an observation". Record the start time and the segment's `sha256`, and compare its snapshot with 6.2 (6.3).
8. **Start the trader after 00:05 UTC.** The first bar it decides then closed after the segment started, so paper and the replay start flat on the same bar. Starting it earlier would let it act on a bar decided before the segment, which Reconcile would show as "Extra".
9. **Day 1:** check the log for one `Decision … strategy=STRAT-004 … bar=<yesterday>` line per coin (7.2 step 8).

### 9.3 Ending the segment

- **Normal end** (section 10): press "End the observation", then "Reconcile...", and write the report (section 10).
- **Automatic end:** any change to a frozen setting ends it at the time the file was written. Reconcile the ended segment, and start a new one only on the owner's decision. Starting a new one means going through 9.2 again.
- **End at once and investigate,** on any of these:
  1. a duplicated trade, an unexplained unexpected trade, or any live order (section 8);
  2. the 8% emergency stop (positions are then unmanaged; resuming is the owner's decision, and a new segment starts afterwards);
  3. a strategy settings refusal during the segment, which also freezes positions (section 1);
  4. a merge to the trading path (9.1 step 3);
  5. a change to the LLM signal mode or the exchange order (D2), which the segment does not notice.
- **After any end:** the trader may keep running in paper. Its trades after the end are not part of the segment. Returning STRAT-004 to `research` is a separate reviewed change, and is needed only if the owner ends the observation for good.

## 10. Proposed duration and the limits of the trade rate

**Status: Ready (proposal).**

**Expected trade rate.** E1 had 135 trades in 1,586 days across 11 coins: 0.085 a day, 31 a year, 2.8 a coin a year. The median holding was 26 days (90th percentile 61). These are development-period rates in a mostly rising market (E1: 24 to 41 trades a calendar year, and 6 in 2025 to 6 May). The rate assumes independent trades. Breakouts cluster across coins in trending markets, so the real spread is wider than this:

| Duration | Expected entries | 90% range | Chance of 15 or more | Coin-day decisions |
|---|---|---|---|---|
| 1 month | 2.6 | 0 to 5 | 0.00 | 330 |
| 3 months | 7.7 | 3 to 13 | 0.01 | 1,001 |
| 6 months | 15.5 | 9 to 22 | 0.59 | 2,009 |
| 9 months | 23.3 | 16 to 32 | 0.97 | 3,013 |
| 12 months | 31.1 | 22 to 41 | 1.00 | 4,018 |

**What a count can show.** With no defects in n orders, the exact 95% upper bound on the defect rate is:

| Orders (n) | Upper bound | Roughly |
|---|---|---|
| 15 | 18% | 7 or 8 round trips |
| 30 | 9.5% | 15 round trips, about 6 months |
| 60 | 4.9% | 30 round trips, about 12 months |

For "unexpected" trades, every coin-day is a decision that should not trade. Checked against the decision log, 2,009 coin-days give a bound of 0.15%.

**Proposal.**
- **Minimum:** 6 months and at least 15 completed STRAT-004 round trips (30 orders), whichever is later.
- **Cap:** 12 months. If the cap arrives with fewer than 15 round trips, the rate-based criteria read "too few trades to tell", with the bound reached.
- **Reviews:** a weekly reconcile (section 7), a monthly summary to the owner, and an interim review at 3 months.
- **Final report:** the counts and rates by class with their bounds, fill-against-open and fees by side, delays, residuals, and the halt record. P&L is shown only with return per capital-day and the account's return together, labelled operational.

**Limits that come from the trade rate.**
- **The sample is small.** Six months gives about 15 round trips. A one-in-20 failure mode can easily go unseen.
- **The regime may give few trades.** Few new highs means few entries. A falling market could give a few trades in 6 months, as in 2025's first months.
- **Exits lag entries** by weeks, so the trades entered in the last two months may still be open at the end.
- **P&L is noise.** At about 31 trades a year and 2.6% committed, a year's P&L cannot be told from chance. E1's whole development period could not do so either (S3).

## 11. Defects found (not fixed)

**D1. A late daily bar delays or skips a decision.**
- **Evidence.** `app/signal_engine.py:349-351` returns the cached frame whenever its key equals the expected last bar. Line 367 stores the provider's frame under that key even when the frame's last bar is older. `docs/dev/strat-004-readiness/late_daily_bar.txt`:
  - an exchange 5 s late at every boundary makes every decision a day late;
  - an exchange late once leaves the breakout bar undecided, with no ENTER_LONG at all, where the replay enters.
- **Smallest fix.** Mark the frame as current only when it holds the expected bar. Otherwise keep it as a fallback, and fetch again after `FETCH_RETRY_SECONDS` (30 s):
  ```python
  last = df["open_time"].iloc[-1]
  key = expected_last_open if last >= expected_last_open else last
  self._candles[pair] = (key, df)
  ```
  Apply the same at `signal_engine.py:409` for an entry gate's context.
- **Test.** A provider 5 s late at the first fetch: the new bar is decided within 30 s, and an exchange that never publishes is asked at most every 30 s.
- **Scope.** This affects every catalogue strategy, but a daily one loses a whole day.

**D2. Two deciding settings are not frozen.**
- **Evidence.** `observation.py:46-61` freezes `strategy`, `risk`, `paper`, `signal_fusion`, `trading.mode` and the GUI keys. `llm.signal_mode` (`llm_gate.py:29-55`) can confirm or veto an entry. `trading_config.json` decides the quote, fee, minimum and candles.
- **Smallest fix.** Add `llm.signal_mode` and `llm.signal_use` to the snapshot. Add the enabled exchanges in order, primary first, read from `trading_config.json`. Then `check` ends the segment when either changes. The test `test_an_unrelated_setting_changes_nothing` would change accordingly.

**D3. A reverted change, and rows from other settings, go unseen.**
- **Evidence.** `check` runs only when the window opens or reconciles (`observation_ui.py:173-180`). `paper_trades` ignores the rows' strategy fields (`observation.py:235-274`; probe case 5).
- **Smallest fix.** Reconcile flags every segment row whose strategy fields differ from the frozen strategy's.

**D4. Reconcile's comparison is incomplete.**
- **Evidence.** The probe cases in 7.1.
- **Smallest fix.** The additions in 7.3. The first two are small changes in `observation.py`: keep every ENTRY buy, flagging a second one before an exit, and add the exit fee and exit fill to `Row`.

**D5. The trader's status file does not show an authorisation refusal.**
- **Evidence.** The scratch check in section 1.
- **Smallest fix.** In `_signals_status` (`pt_trader.py:2049`), read the settings with `mode=self._target.mode`.

**D6. The segment's hash and frozen settings are not shown in Settings.**
- **Evidence.** `observation_ui.py:182-196` shows only the status line.
- **Smallest fix.** Show the SHA-256 and a list of the frozen values, facts only, in the Observation window.

**D7. The code version is not frozen.**
- **Evidence.** The snapshot holds settings only (`observation.py:73-84`).
- **Smallest fix.** Record the SHA-256s of the trading-path files at the start, as E1's record does for its code. `check` ends the segment when they change.

## 12. What this observation cannot show

- **Profitability.** S3 failed in development. A paper segment of 15 to 31 round trips, with 2.6% of the account committed, cannot show a profit after fees, whatever its P&L.
- **A forward confirmation.** None is registered. Months after 2026-11-06 are reserved for a registered forward confirmation, which is not authorised (FDS-SR-001 §6.1). A later registered confirmation should either start after this observation ends or count its months as seen (section 14).
- **Strategy effectiveness.** S1 (beating random entries) was a development result. Paper repeats it neither for nor against.
- **Live execution.** Paper fills at the top of the book: no size slippage, no queue, no partial fills, no sell rounding (FDS-SR-001 §9 item 8). The fee depends on the keys (7.2 step 5).
- **Robustness.** One coin set: survivorship was not addressed, and E1's profit came from coins listed after 2021. One market period, defaults only. PBO across STRAT-004's parameter sets was 0.52 (E1 §14), so nothing here may be tuned.
- **The reserved months.** Before its first decision, the trader reads 61 daily bars (`signal_engine.py:359`: the 56-bar window plus 5), and Reconcile reads 58 before the start (`strategy_lab/runs.py:81-87`). For a start before 2027-01-06, some of those bars fall in the lockbox (2025-05-06 to 2026-11-06). They are used as warm-up only, and no trade in them is scored (section 14).

## 13. The proposed authorisation change (not applied)

To be made after the owner's approval, as one reviewed PR on its own branch. **Not applied here.** `app/strategies/catalogue.json` still reads `research` at this commit.

```diff
diff --git a/app/strategies/catalogue.json b/app/strategies/catalogue.json
--- a/app/strategies/catalogue.json
+++ b/app/strategies/catalogue.json
@@ -104,7 +104,7 @@
       "exit_days": {"min": 5, "max": 120}
     },
     "version": "1.0.0",
-    "authorisation": "research",
+    "authorisation": "paper",
     "research_refs": ["FDS-SR-001 5.4.3", "strategy-research/A-research-report.md 4"]
   },
   {
```

**The same PR also:**
- **Updates the tests that pin today's state.** A run with the change simulated in memory (`docs/dev/strat-004-readiness/sim_paper_plugin.py`, over 9 related test files) found exactly these:
  - `tests/test_strategy_breakout.py::CatalogueTests::test_it_is_research_only_and_daily` (`research` → `paper`);
  - `tests/test_strategy_breakout.py::CatalogueTests::test_it_is_refused_for_trading_in_both_modes` (allowed in paper, refused in live: "paper trading, not live trading");
  - `tests/test_strategy_catalogue_view.py::test_a_research_strategy_is_not_offered_and_a_saved_one_is_reported` (the paper list gains STRAT-004);
  - `tests/test_strat004_paper_readiness.py`: `TodayTests::test_it_is_research_only_in_the_catalogue_file`, `TodayTests::test_the_proposed_settings_are_refused_in_every_mode` and `PaperSessionTests::test_today_a_paper_session_places_no_orders` become their post-change forms, and `paper_authorised()` is no longer needed.
- **Records the owner's decision** in `docs/dev/RUN-LOG-sr-1.md`, with the record text of section 2.
- **Changes nothing else:** no version, default, bound or timeframe; STRAT-005 and OVL-REGIME stay `research`; no entry becomes `live`; no setting is changed. Selecting STRAT-004 stays the owner's own step in Settings > Strategy (section 9.2).

**Effect once merged.** In paper mode, Settings > Strategy offers STRAT-004 ("Paper"). In live mode it is still refused, at the settings check and at the order gate, as `test_with_paper_authorisation_it_is_still_refused_in_live` shows.

## 14. Decisions for the owner

1. **Authorisation:** approve the change in section 13 (STRAT-004 `research` → `paper`), with the record text in section 2.
2. **D1:** fix the late-bar defect before the start (recommended), or start with it known and record its rows as such.
3. **D2, D3, D6, D7:** fix them before the start, or accept the manual checks in sections 7 and 9 (the lead reads the segment file and the rows' fields; the LLM mode, exchange order and code are checked by hand).
4. **Coins:** E1's 11 coins (recommended, so paper observes E1's universe) or the current Settings list. Reconcile replays the Settings coins, so an override would show other coins as "Not placed".
5. **Paper balance:** $13,476 (£10,000 at E1's rate, the same entry size as E1's deciding account) or $10,000.
6. **Fee source:** with Coinbase keys, paper charges the account's own taker rate (0.50% at 2026-11-05) through an existing authenticated read. Without keys it charges the standard 1.20%. E1 assumed 0.50% + 0.05%.
7. **Code freeze:** hold merges to the trading path during the segment, or end and restart a segment at each one.
8. **Duration:** at least 6 months and 15 round trips, capped at 12 months (section 10).
9. **Reserved months:** accept warm-up bars from the lockbox for a start before 2027-01-06, or start on or after that date.
10. **Forward months:** whether months observed in paper count as seen for any later registered forward confirmation.
11. **Thresholds:** the termination and review thresholds in section 8.

## 15. Tests run (this branch, guarded, one file at a time)

| File | Result |
|---|---|
| `tests/test_strat004_paper_readiness.py` (new, 12 tests) | 12 passed, 7 subtests |
| `tests/test_strategy_breakout.py` | 14 passed |
| `tests/test_strategy_lifecycle.py` | 18 passed, 201 subtests |
| `tests/test_observation.py` | 7 passed |
| `tests/test_trade_strategy_fields.py` | 3 passed |
| `tests/test_signal_engine.py` | 38 passed |
| `tests/test_strategy_lab.py` | 21 passed |
| `tests/test_strategy_catalogue_view.py` | 15 passed |
| `tests/test_position_budget.py` | 41 passed |
| `tests/test_entries_above_minimum.py` | 25 passed |
| `tests/test_paper_fees.py` | 20 passed |
| `tests/test_risk_state.py` | 24 passed |
| `tests/test_risk_settings_ui.py` | 34 passed |

The full suite was not run here; the lead runs it. CI runs none of FDS-SR-001's tests (run log backlog).

## Appendix A: evidence scripts

All four are in `docs/dev/strat-004-readiness/`, with their outputs as `.txt` beside them:

| Script | What it shows |
|---|---|
| `snapshot_hash.py` | The proposed snapshot, its hashes and the parameter hash (section 6.2) |
| `late_daily_bar.py` | D1, on synthetic daily bars |
| `reconcile_probe.py` | D4's cases, on synthetic rows |
| `sim_paper_plugin.py` | A pytest plugin that simulates section 13's change in memory, to list the tests the PR must update |

**Safety.** The scripts read no real settings and make no network calls. Each refuses to run unless `POWERTRADER_HOME`, `APPDATA` and `LOCALAPPDATA` point into a `p4-sbx` folder.

**How they were run.** From `app/`, with:
- `PYTHONPATH` set to `app/`;
- `PYTHONNOUSERSITE=1`, `PYTHON_KEYRING_BACKEND=keyring.backends.fail.Keyring`, `PYTHONIOENCODING=utf-8` and `POWERTRADER_USER_REGION=GLOBAL`;
- those three folders pointing at a new sandbox folder.

The plugin was run with the isolation guard on:

```
PYTHONPATH=<this folder>;<app> python -m pytest -p sim_paper_plugin tests/<file>.py
```
