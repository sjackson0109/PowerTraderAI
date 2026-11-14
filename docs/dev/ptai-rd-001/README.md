# PTAI-RD-001: strategy discovery, model research and trading validation

The owner's programme brief of 2026-11-11.

**Authorised:**
- research;
- architecture;
- implementation;
- experiments that do not trade live.

**Still the owner's to decide:** live trading, raising a strategy's authorisation, opening the lockbox, and paid data (D §3).

**The owner's decisions of 2026-11-12** are in D §3: O1, O2, O6 and O7 approved; O3 answered with "measure a stricter variant first"; and a new request, a trading switch for every strategy in Settings > Strategy. The owner's answers that evening (O3 accepted, O10 to O16) are in the same table. The owner's answers of 2026-11-13 (O17 to O25) follow from the ensemble and sizing exploration, and cover the merges of #288 to #303, the design for N11 and the fixes that came from it.

## Deliverables

| | File | What it holds |
|---|---|---|
| A | `A1-capability-matrix.md` | What the code does today, stage by stage, with file:line evidence. Also the dependency map, the data layer, the Python environment, duplicated implementations, the ten biggest gaps, and the earlier architecture assessment checked against today's code |
| A | `A2-defect-register.md` | 59 defects (D1-D7, N1-N45, A1-A7), each with evidence, severity, whether its fix changes trading, and a reproducing test. 5 are high: D1, N1, N5, N19, N38 |
| A | `A3-hardware-inventory.md` | The workstation as measured, and what it means for research |
| B | `B-strategy-catalogue.md` + `B-candidates.json` | 130 sourced candidates: strategies, signals, models, data sources, risk and portfolio rules. Each has evidence quality, crypto evidence, data needs, licences, turnover and fee sensitivity, and a priority set without looking at returns |
| C | `C-architecture.md` | The integrated architecture: one implementation per job, its interfaces, the qualification path, the statistical method, and the programme trial ledger |
| D | `D-backlog.md` | Work packages by milestone (M0-M8), the order of work, and the owner decisions O1-O25 |
| E | Pull requests | Below |

**A design awaiting a decision:** `N11-halt-equity-design.md`, which covers what the drawdown halt measures, how money moved in or out of the account moves it, and a proposed fix in three parts (N11, O21). It is docs only, and trading is unchanged.

## First implementation (Deliverable E)

| PR | Milestone | What |
|---|---|---|
| #260 | M1 | The signal engine decides a bar the exchange publishes late, instead of a bar later or never (D1) |
| #262 | M5 | A local job queue and scheduler: resource modes, worker processes, pause, resume, cancel, checkpoints, deduplication, seeds, time and memory per job |
| #263 | M5 | Strategy backtests as engine jobs; unique run folders; candle-cache writes safe across processes |
| #264 | M5 | Settings > Training > "Research engine...": the computer, the mode, energy figures, and the queue |
| #265 | M1 | Strategy-lab series end at a gap longer than a day, so no trade spans an exchange halt (N17) |
| #266 | M1 | A stationary bootstrap on marked daily results, measured for size and power (N19; adoption is O3) |

**After the owner's decisions of 2026-11-12:**

| PR | Milestone | What |
|---|---|---|
| #267 | O6 | `requirements.txt` requires scikit-learn (installed in the owner's `.venv` the same day) |
| #268 | O7 | STRAT-004 raised from `research` to `paper`, with the record in `RUN-LOG-sr-1.md` |
| #269 | Owner request | Settings > Strategy: a trading switch for every strategy and stop (`strategy.trading_allowed`) |
| #270 | M1 (O1) | The emergency halt refuses buys and keeps managing what is held (N1) |
| #271 | M1 (O2) | Order intents: each order is recorded before it is sent and never resent under a new id (N5) |
| #272 | M1 | One coin's error never ends the trader's pass (N8) |
| #273 | M1 | Each decision names the exchange whose bars decided it (N15) |
| #274 | M2 | The programme trial ledger, schema v1, with adapters (WP 2.1) |
| #275 | M5 | Model-lab batches as engine jobs (WP 5.4) |
| #276 | M2 | Daily, weekly, monthly and annual returns (WP 2.6, first part) |
| #277 | M1 (O3) | The bootstrap's calibration: four variants; the default is the studentised test with 1.5x blocks (worst null size 6.2%) |
| #278 | Docs | These decisions and PR tables |
| #279 | M1 | The trader's status shows a strategy not cleared for its trading mode as blocked (D5) |
| #280 | M1 | The live cooldown counts from the bar the sale filled in, as the backtester does (N13; changes live behaviour) |
| #281 | M2 | Each account size, £50 to £10,000, reported separately; drawdown recovery; the run window's tabs (WP 2.6, second part; stacked on #276) |
| #282 | M2 | One statistics module: Romano-Wolf, deflated Sharpe, PBO, power and the three verdicts (WP 2.3) |
| #283 | M2 | Dataset snapshots and one canonical bar hash (WP 2.2) |
| #284 | M1 | Replays measure drawdown and the halt within the bar as well (N18) |
| #285 | M3 | STRAT-006, price above its average, research only (backlog 3.2) |
| #286 | M1 | Observation: LLM signals, exchange order and program files frozen; fuller Reconcile; the frozen hash shown (D2, D3, D4, D6, D7) |
| #287 | M4 | The feature library: 13 price, volatility and volume features, checked as of each bar (WP 4.1) |

#267 to #287 were merged on 2026-11-13 (O10), the last as `76534a1`.

**Opened on 2026-11-13** (stacks merge bottom first; the owner approved their merge the same day, O20):

| PR | Milestone | What |
|---|---|---|
| #288 | M1 (O12) | The intrabar drawdown's peak is the highest high of the earlier bars (N18) |
| #289 | M4 | Sizing policies for replays: a volatility target, with random orders of its sizes as the baseline (WP 4.2; on #288) |
| #290 | M3 | STRAT-007, OVL-MIDLINE and the Donchian ensemble, research only (backlog 3.1; on #289) |
| #291 | Docs | The ensemble and volatility sizing, explored on the development months (on #290) |
| #292 | M1 (O15) | Entries are acted on only within 15 minutes of their bar's close (N12; changes live and paper behaviour) |
| #293 | M1 (O15) | Live and paper hold an entry while the bars it reads span a gap over a day (N17, the live part; on #292) |
| #294 | M1 (O15) | Bars are used 30 s after their close; the last cached bars are fetched again; gaps are refilled (N16; on #293) |
| #295 | M1 (O15) | Binance order results: partial fills, average price and fee (N7; changes live behaviour) |
| #296 | M1 (O15) | An unreadable settings file blocks trading instead of reading as the defaults (N10) |
| #297 | M1 (O14) | Paper fills follow the exchange's sell step and minimum order (N28) |

#288 to #298 were merged on 2026-11-13 and 2026-11-14 (O20).

**Opened on 2026-11-13 and 2026-11-14:**

| PR | Milestone | What |
|---|---|---|
| #299 | M6 (O17) | SR1-E2, a registered evaluation of the Donchian ensemble: a draft for review; nothing runs until it is approved |
| #300 | Docs (O18) | Volatility sizing at 50% and 75% a year; a correction to #291's intrabar column |
| #301 | M1 (O21) | The N11 design: the drawdown halt across deposits and withdrawals |
| #302 | M2 (O19) | A matched-holding baseline beside the random entries, reported only |
| #303 | M1 | Settings > Risk: a halt stops buying, not trading (N41; text only) |
| #304 | Tests | The LLM gate's no-second-wait check bounds at the 1 s wait, not 0.3 s |
| #305 | M1 (O24) | The legacy engine manages only the trader's own quantity of a coin (N40; changes live behaviour) |
| #306 | M1 (O23) | A holding with no USD price no longer switches the halt off; the drawdown is checked before the first entry (N38, N39; changes live behaviour) |
| #307 | M1 (O22) | The halt measures every balance, funds on hold included (N11 part 1; on #306) |
| #308 | M1 (O22) | A deposit never reduces the drawdown (N11 part 2; on #307) |

#299 to #303 were approved for merging by me on 2026-11-13 (O25). #304, #305 and #306 to #308 are the owner's to merge.

## The headline findings

- **Nothing from research can reach trading today**, by design: research-only entries are refused in paper and live (A1 §1.4, gap 3). Promotion is a hand edit of `catalogue.json`.
- **Four high-severity defects** (A2 §0):
  - **D1: a late bar is skipped.** Fixed in PR #260.
  - **N1: the emergency halt leaves positions unmanaged,** while logging that it closed them.
  - **N5: an order retried after a network error gets a new ID,** so it can be placed twice.
  - **N19: the long-holding bootstrap's p-values are artefacts.**
  - N1 and N5 change live behaviour: the owner approved their fixes on 2026-11-12 (O1, O2), in PRs #270 and #271.
- **The evidence fits slow strategies only** (B §1): slow, daily, long-or-cash trend and breakout rules with a few round trips a year. STRAT-004 and STRAT-005 are already that. No published study tests crypto rules at this account's 0.55% a side.
- **The honest search budget is small** (B §20): 4.3 years of development data support a few dozen independent configurations in total. The programme declares candidates with published parameters, and counts every trial.
