# E: Decision record for strategy research and catalogue expansion

**Date:** 2026-11-07.
**For:** the owner's approval of FDS-SR-001's shortlist and sequence.
**Status:** proposed. Nothing here is built, registered, enabled or activated.
**Sources:**
- `docs/dev/specs/FDS-SR-001-strategy-research-and-catalogue.md`, the specification;
- `A-research-report.md`, the evidence;
- `B-architecture-assessment.md`, the code as it is.

---

## 1. Proposed first implementations

| Build | ID | What it is | Why first | Status when built |
|---|---|---|---|---|
| 1 | STRAT-004 | Donchian breakout, daily: enter on a new 55-day closing high, exit on a new 20-day closing low | The best crypto-specific evidence for a long-only rule. Low turnover, and an entry no catalogue strategy has (A §4) | Research only, not enabled |
| 2 | OVL-REGIME | Regime gate: no new entries while BTC (or the coin) is below its 200-day average | Composes with every strategy, the one in use included. It can only reduce trading (A §6) | Research only, not enabled |
| 3 | STRAT-005 | Time-series momentum, long or cash: 30-, 90- and 365-day returns, 2 of 3 positive, decided weekly | The best-evidenced family overall, at horizons where 1.10% round trips can be covered (A §3) | Research only, not enabled |

**Deferred, with reasons:**
- **STRAT-006, mean reversion:** the evidence for these coins points against it (A §7).
- **STRAT-007, relative strength:** weak long-only evidence on 12 coins, and it needs a new portfolio interface (A §8; B §9).
- **Overlays:** OVL-MIDLINE and OVL-TIMESTOP.

**Not new strategies:**
- **The volatility shrink** is evaluated as a sizing policy across strategies, from FDS-SIG-004's code.
- **DCA** stays an execution policy of the legacy engine. Periodic accumulation is a baseline, REF-ACCUM.

## 2. Evidence requirements

**What the first evaluation (E1) must show, and how each result is worded** (FDS-SR-001 §6.2, §6.6):

| Finding | Test | Words a pass may use |
|---|---|---|
| Trading: the strategy times entries better than chance | Against matched random entries (REF-RANDOM), with Holm over the family | "Beats random entries" |
| Economic: the strategy is profitable after costs | FDS-SIG-004 F3's requirements at £10,000 and 0.50%: at least 100 trades; a profit overall, in each half and without the best coin; a drawdown below 8% | "Profitable after fees …, development only" |
| Trading: the regime gate adds value | Against random vetoes at the same per-coin counts (R3) | "The gate adds value over random vetoes" |
| Trading: a model improves a strategy's entries, exits unchanged | Against random vetoes at the same counts (R3) | "Beats random vetoes" |
| Prediction: a model forecasts better | Paired log loss (exploratory here) | "Forecasts improved" |

**Before any result:**
- each family states its smallest detectable effect;
- a member that could not have seen a realistic effect reads "Too few trades to tell".

**Expect that to be common.**

**To change a strategy's authorisation** (FDS-SR-001 §6.7; proposed in D8):
- **research → paper:**
  - its tests pass, including the backtest–paper parity test;
  - a declared development evaluation has reported, whatever its result;
  - the owner decides.

  Paper observation is operational evidence.
- **paper → live:** no route in this spec. It needs a passed check on unseen months, and the owner's decision, under a later spec.

## 3. Material risks

| Risk | Effect | What the design does |
|---|---|---|
| Costs | 1.10% a round trip is above every cost level in the literature | Daily decisions, holds of weeks. Fees at 0.50% decide, with 1.20% shown |
| Few trades | 150–300 trades in development for daily rules; long holds lengthen the bootstrap blocks | The smallest detectable effect is reported first; "Too few trades to tell" is an honest verdict |
| Multiple testing | Strategies × models × gates × accounts × timeframes is a large grid | Only 9 declared members decide; everything else is a trial with BH or PBO |
| Survivorship | Today's coins, no point-in-time universe | Robustness on coins with history from 2021, and on BTC and ETH only |
| Lockbox reuse | FDS-MH-001's lockbox is shared; STRAT-001 and STRAT-002 have seen it | Opening limits are shared; their checks are marked as seen |
| The halt does not exit | A halted trader leaves positions unmanaged | The exposure at the halt, and its further loss, are reported |
| Paper is not live | Paper fills at the top of the book | "Reconcile…" measures the gap per trade |
| Small accounts | At £50, every entry is the minimum, and lot rounding can be 1.5% of an order | Minimum raises, rounding and skips are modelled and counted per account |

## 4. Decisions

### 4.1 Decisions that cannot reasonably be deferred (M2 and M3 depend on them)

| # | Decision | Recommended | Alternative |
|---|---|---|---|
| E-D1 | The shortlist and the first builds | STRAT-004, OVL-REGIME and STRAT-005, in that order | STRAT-006 (mean reversion) instead of STRAT-005: more diverse, weaker evidence |
| E-D2 | Identifiers | Spec FDS-SR-001. New IDs: STRAT-004 and STRAT-005, then OVL-REGIME. STRAT-006, STRAT-007, OVL-MIDLINE and OVL-TIMESTOP are reserved. Baselines are REF-HOLD, REF-CASH, REF-RANDOM and REF-ACCUM, outside the catalogue | Other names. STRAT-000 to STRAT-003 keep theirs in any case |
| E-D3 | The authorisation of the existing entries | STRAT-000, -001, -002 and the four overlays are `live`, so nothing changes. STRAT-003 is `research`; it cannot trade today either. New entries are `research` | Mark STRAT-000 and STRAT-002 `paper` or `research`. That would change today's behaviour, so it is not recommended without a reason |
| E-D4 | Execution | One selected strategy for every coin, as today. Multi-strategy execution is defined (FDS-SR-001 §5.7), not built. A strategy switch still hands open positions to the new strategy, as today | Build multi-strategy execution: a later spec. Or change switching to "drain": a behaviour change, also later |
| E-D7 | Research windows | Settings backtests read the development period only (to 2025-05-06). The lockbox and later months are read only by declared final checks, within FDS-MH-001's opening limits. Every exploratory run is logged | Allow any period in the window, with each look recorded. This spends the unseen months |
| E-D9 | Parameters | Defaults from the literature or a stated convention, never tuned. Declared variants are trials, with PBO | A tuning search: it needs its own family and a walk-forward selection |

### 4.2 Decisions that can wait (M4 or M5 needs them)

| # | Decision | Recommended | Needed by |
|---|---|---|---|
| E-D5 | The deciding account | £10,000 decides; £500 and £50 are shown | M4a |
| E-D6 | Currency | One GBP-to-USD rate per experiment, entered by the owner and recorded. The pairs stay USD-quoted | M4a |
| E-D8 | Paper eligibility | As in §2: tests plus a reported development evaluation, plus the owner's decision. A pass is not required | Before any authorisation change |
| E-D10 | Fees | 0.50% taker + 0.05% decides. 1.20% taker and a 0.60% maker scenario are shown; orders are not changed | M4b |
| E-D11 | E1's families | S (K = 4), G (K = 3), M (K = 2), as in FDS-SR-001 §6.2. Frozen only when the owner approves registering E1 | M5c |
| E-D12 | The backlog | Keep FDS-SR-001 §13 out of scope: the legacy backtest tab, the missing FDS-121 files, the DCA display mismatch and the others | Any time |

## 5. On approval

1. The next task is to build M2a (the catalogue lifecycle), then M3a, M3b and M3c (STRAT-004, STRAT-005, OVL-REGIME). Each is a separate, tested PR, research-only and not enabled.
2. No experiment is registered, and no strategy is activated, by any of them.
3. M5c, the first declared evaluation, waits for a separate approval to register it.
