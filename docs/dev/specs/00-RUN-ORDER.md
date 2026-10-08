# RUN-ORDER — Unattended build session (post FDS-096)

**Target repo:** `sjackson0109/powertraderai`
**Read this file first.** It tells you which specs to build, in what order, and the
rules for working unattended for several hours.

---

## 1. Specs in this batch (build in this order)

| # | File | Issue | Depends on | Size |
|---|---|---|---|---|
| 1 | `FDS-096b-price-source-integrity.md` | follow-up to #96 | FDS-096 (done) | S |
| 2 | `FDS-087-paper-trading-demo.md` | #87 | FDS-096, 096b | S |
| 3 | `FDS-121-strategy-runtime-and-catalogue-lite.md` | #121 (lite) | — | L |
| 4 | `FDS-122-dema-tema-crossover.md` | #122 | 121 | M |
| 5 | `FDS-123-supertrend-atr.md` | #123 | 121 | M |
| 6 | `FDS-129-risk-overlays.md` | #129 (+#113–#116) | 121 | M |
| 7 | §5 below: backtest report | — | 122, 123, 129 | S |

## 2. Ground rules (apply to every spec)

1. **Branch.** Work on `feat/strategy-batch-1`, branched from the commit containing
   FDS-096. Never commit to `main`. Never push unless the repo already has a remote
   configured for this branch; if unsure, don't push.
2. **One commit per spec**, message `FDS-<id>: <summary>`, made only when that spec's
   acceptance criteria pass and the **full** test suite is no worse than before
   (the known failure `test_expired_proposal_cannot_execute` is allowed).
3. **Paper only.** Do not read, create or request API keys. Do not call any
   authenticated endpoint. Do not change `trading.mode` default. Public market-data
   endpoints (Binance klines/ticker) are allowed.
4. **Tests never touch the network.** Use recorded fixtures under
   `app/tests/fixtures/` (or the repo's existing test-data location). Network is only
   used by the candle downloader and the demo script when run manually.
5. **Don't touch out-of-scope areas:** the legacy trainer files, GUI theming, exchange
   implementations, issues outside this batch. If you find a bug outside scope, log it
   (rule 7) and move on, unless it blocks the current spec.
6. **If a spec is blocked** (acceptance can't be met after a genuine attempt), stop
   work on it, revert its uncommitted changes, record why in the run log, and continue
   with the next spec **that doesn't depend on it**. Never weaken an acceptance
   criterion or a test to get it passing.
7. **Run log.** Maintain `docs/dev/RUN-LOG-strategy-batch-1.md`: for each spec, start
   time, end time, status (done / blocked / partial), commit hash, test counts, and any
   bugs found out of scope. Update it after every spec so the session can be resumed if
   it is cut short.
8. **No silent fallbacks** anywhere you write code: if data is missing, stale or
   simulated, say so in logs and in the data itself.

## 3. Model / effort

Recommended for the whole unattended run: **Claude Sonnet 5.5, effort high.**
If FDS-121 (the architecture spec) stalls or produces a design that the later specs
fight against, escalate that spec only to **Opus 5.5**. Usage limits may end the
session early; the run log (rule 7) exists so it can be resumed from the next spec.

## 4. Definition of done for the batch

- All six specs committed, or blocked with a written reason.
- Full suite green apart from the known pre-existing failure.
- `python app/demo_paper_trading.py` runs (manual network check).
- Backtest report (§5) written.

## 5. Final step: backtest report

After 122, 123 and 129 are committed, run the backtest CLI from FDS-121 on real cached
Binance candles and write `docs/dev/BACKTEST-REPORT-batch-1.md` containing:

- Data: symbols (BTCUSDT, ETHUSDT), timeframe (1h and 4h), date range, candle count,
  source, and the SHA-256 of each cached candle file.
- For each strategy, with and without overlays: the KPI set from FDS-121 §6,
  **in-sample and out-of-sample reported separately.**
- Buy-and-hold over the identical out-of-sample window, with the same fees.
- One plain-English paragraph: did anything beat buy-and-hold out of sample after
  costs? If not, say so plainly. Do not tune parameters on the out-of-sample window.
