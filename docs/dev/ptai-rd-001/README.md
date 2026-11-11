# PTAI-RD-001: strategy discovery, model research and trading validation

The owner's programme brief of 2026-11-11.

**Authorised:**
- research;
- architecture;
- implementation;
- experiments that do not trade live.

**Still the owner's to decide:** live trading, raising a strategy's authorisation, opening the lockbox, and paid data (D §3).

## Deliverables

| | File | What it holds |
|---|---|---|
| A | `A1-capability-matrix.md` | What the code does today, stage by stage, with file:line evidence. Also the dependency map, the data layer, the Python environment, duplicated implementations, the ten biggest gaps, and the earlier architecture assessment checked against today's code |
| A | `A2-defect-register.md` | 51 defects (D1-D7, N1-N37, A1-A7), each with evidence, severity, whether its fix changes trading, and a reproducing test. 4 are high: D1, N1, N5, N19 |
| A | `A3-hardware-inventory.md` | The workstation as measured, and what it means for research |
| B | `B-strategy-catalogue.md` + `B-candidates.json` | 130 sourced candidates: strategies, signals, models, data sources, risk and portfolio rules. Each has evidence quality, crypto evidence, data needs, licences, turnover and fee sensitivity, and a priority set without looking at returns |
| C | `C-architecture.md` | The integrated architecture: one implementation per job, its interfaces, the qualification path, the statistical method, and the programme trial ledger |
| D | `D-backlog.md` | Work packages by milestone (M0-M8), the order of work, and the owner decisions O1-O8 |
| E | Pull requests | Below |

## First implementation (Deliverable E)

| PR | Milestone | What |
|---|---|---|
| #260 | M1 | The signal engine decides a bar the exchange publishes late, instead of a bar later or never (D1) |
| #262 | M5 | A local job queue and scheduler: resource modes, worker processes, pause, resume, cancel, checkpoints, deduplication, seeds, time and memory per job |
| #263 | M5 | Strategy backtests as engine jobs; unique run folders; candle-cache writes safe across processes |
| #264 | M5 | Settings > Training > "Research engine...": the computer, the mode, energy figures, and the queue |
| #265 | M1 | Strategy-lab series end at a gap longer than a day, so no trade spans an exchange halt (N17) |
| #266 | M1 | A stationary bootstrap on marked daily results, measured for size and power (N19; adoption is O3) |

## The headline findings

- **Nothing from research can reach trading today**, by design: research-only entries are refused in paper and live (A1 §1.4, gap 3). Promotion is a hand edit of `catalogue.json`.
- **Four high-severity defects** (A2 §0):
  - **D1: a late bar is skipped.** Fixed in PR #260.
  - **N1: the emergency halt leaves positions unmanaged,** while logging that it closed them.
  - **N5: an order retried after a network error gets a new ID,** so it can be placed twice.
  - **N19: the long-holding bootstrap's p-values are artefacts.**
  - N1 and N5 change live behaviour, so they wait for the owner (O1, O2).
- **The evidence fits slow strategies only** (B §1): slow, daily, long-or-cash trend and breakout rules with a few round trips a year. STRAT-004 and STRAT-005 are already that. No published study tests crypto rules at this account's 0.55% a side.
- **The honest search budget is small** (B §20): 4.3 years of development data support a few dozen independent configurations in total. The programme declares candidates with published parameters, and counts every trial.
