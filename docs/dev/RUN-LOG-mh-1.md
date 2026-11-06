# RUN-LOG-mh-1: the multi-model harness (FDS-MH-001)

## 2026-11-06: the owner's go-ahead

The owner said "go" on D1–D10 as recommended:
- the spec is PR #225;
- phase A, the gate fix, is PR #226.

## 2026-11-06: phase B, the harness core

**Branch** `feat/mh-b-harness-core`, stacked on `feat/mh-a-gate-per-day` (#226). The package is `app/model_lab/`; the tests are `app/tests/test_model_lab.py`. There is no new dependency.

### Where the spec was not explicit

Each of these is also written into the spec (#225).

| Point | As built | Why |
|---|---|---|
| A series' SHA-256 (§5.2) | The SHA-256 of the bars used, in the candle cache's CSV format (`pt_pattern_trainer.candle_sha256`'s) | The cache file is shared and grows, so its own hash would not identify the bars |
| Reading a frozen series again | From the exchange it was frozen with, from its recorded first bar | So a later change of primary exchange cannot swap the data; and a pair listed late is not asked for again before its first bar |
| R2's offset (§5.6) | A draw takes one number u in [0, 1); each coin's δ is that share of its range [D, length − D] | "One δ for every coin" and "at least D from 0 and from the stream's length" cannot both hold when streams differ in length. Coins with the same stream length, as most are, still move together |
| R2's comparison | Against the contestant's trades on the coins that take part in R2 | R2's draws cover only those coins |
| No coin long enough for R2 | p₂ = 1 | It must beat both; a baseline that cannot be drawn is not beaten |
| K (§5.6) | Every tested contestant, one with no entries at p = 1 | So the correction does not shrink when a contestant makes no entries |
| Daily rules | The last *built* UTC day; undecided when the day that just ended was not built (an hour missing); N days = the last N built days | A day with a missing hour is a gap (`build_candles`), not a guess |
| Joining late (§5.4) | Rules: once the coin has 100 complete UTC days. Pattern model: from the first fold that starts 365 days after the coin's first bar | As §5.4, made exact |
| Refusals | A batch whose file, code (SHA-256 of `model_lab/*.py` and what it replays and fits with) or candles changed since it was frozen is refused | "The same batch on the same cached candles gives the same results" holds only for the same code |
| Trial log | A trial is logged as soon as it is scored | A stopped batch's scored trials stay counted |

### D11: the lockbox is 18 months (owner, 2026-11-06)

§5.7 draws R1 and R2 on the lockbox's hours, but a 6-month lockbox is shorter than 2D (320 days), so R2 could not be drawn there. Asked, the owner chose to lengthen the lockbox to 18 months ("let's expand the spec to 18mths") over the alternative, R1 only.

`walkforward.LOCKBOX_MONTHS` is now 18. For batch 1, frozen on 2026-11-06:
- the walk-forward runs from 2021-01-01 to 2025-05-06, in 18 folds (22 before);
- the lockbox runs from 2025-05-06 to the end.

Two consequences:
- **Fewer walk-forward trades.** The walk-forward stream is about 4.3 years rather than 5.3, so about a fifth fewer trades, and "too few trades to tell" is a little more likely.
- **Late coins.** BNB and HYPE start on Coinbase after 2025-05-06, so they are in the final check only.

Nothing in phase B opens the lockbox: that comes with phase D's "Final check…".

### Tests (no network, fixture candles)

- **No look-ahead.** Every rule's decision at an hour, made from bars cut at that hour, equals its decision from all bars. This was checked at 70 hours per coin, including the hours around a missing hour, a 6-hour gap and a 20-hour gap.
- **Lockbox.** A batch run never passes a contestant a bar from the lockbox.
- **R2's offsets.** R2 never moves a signal less than D, in 2,000 random streams; a coin whose stream is shorter than 2D takes no part.
- **False-pass rate.** On random-walk prices, R1 and R2 each pass a no-skill contestant at about the nominal rate: 200 trials, within the binomial range of 2 to 22 passes.
- **Determinism.** A batch run twice gives byte-identical `results.json`.
- **Refusals.** A batch whose file, candles or code changed is refused.
- **Pattern fold 1.** The pattern contestant's fold-1 entries and long counts equal those of the trainer's sibling fit (`validation_fit`) on the same window, and so do the model files' SHA-256.
- **Trade table.** It is `model_gate.replay` from every hour.
- **Late listings.** A coin listed after the lockbox starts (as BNB and HYPE are on Coinbase) has an empty walk-forward stream: it never joins, is reported as such, and takes no part in R2. The first timing run found this.
- **Statistics.** Holm, Benjamini-Hochberg, the p-values and PBO, on hand-checked cases.
- **Full suite:** 2659 passed, 13 skipped, 0 failed.

### Measured: batch 1 without the trained contestants

**The run.** A sandbox (no keys, no real user folders), with Settings from the shipped template (Coinbase primary) and public candles. Batch `20261106-143033`:
- 13 coins from 2020-01-01;
- the seven rules, `ref.always` and `pattern`;
- 0.50% a side (the owner's account rate) plus 0.05% slippage;
- the trader's default rules;
- B = 10,000.

**Candles.** Every series came from Coinbase. Coins that start later there:
- ADA 2021-03, ZEC 2020-12, DOGE and SOL 2021-06, AVAX 2021-09;
- BNB 2025-10-22 and HYPE 2026-02-05;
- XRP's series starts 2023-07-13: Coinbase halted XRP from 2021-01-19, and a gap longer than 24 hours ends the earlier part.

The walk-forward stream is 380,539 coin-hours, in 18 folds from 2021-01-01 to 2025-05-06.

| Stage | Time |
|---|---|
| Freeze, downloading 2020-01 to 2023-11 for 13 coins and BTC | 114 s (2 s from the cache) |
| Read the series again and check their SHA-256 | 2 s |
| Trade cache: every stream hour's trade, 380,539 replays | 231 s (0.6 ms each) |
| The seven rules' decisions | 1 s |
| Pattern model: 155 fits (18 folds, the coins with 12 months of bars), with their counts | 3,565 s (23 s a fit) |
| Draws: R1 and R2 × 10,000 for 8 contestants, the fee lines, and the pattern model's neural DCA line (1,000 draws) | 1,333 s |
| Holm, Benjamini-Hochberg, PBO, the best-rule comparison | 1 s |
| **Run, in all** | **5,133 s (86 min)** |

The run ended "done". The coins joined where §5.4 says they should:
- BNB and HYPE never joined;
- the pattern model joined ADA on 2022-04-01 and XRP on 2024-10-01;
- XRP's pattern stream is shorter than 2D, so it takes no part in R2 there.

Phase C adds pooled fits: 6 contestants × 18 folds.

**These are trials.** The run logged 8 trials in the sandbox's trial log. Phase E's report counts them.

## 2026-11-06: the owner's review of #225 and #226

### 1. The LLM gate's per-trade minimum

**The finding.** #226, as first pushed, retired `gate_min_return_after_fees` and fixed the LLM signal gate's rule b at 0%. Anyone who had saved another value would see different LLM gate decisions, and the tests compared decisions at the default settings only.

**Checked.** I ran `main`'s gate code (500a355) and #226 as pushed (`a652b5b`) on the same LLM fixtures, at seven saved settings: minimums of 0%, +0.5%, +3%, −5% and −10%, plus two with other non-default fields.
- At +3%, the "edge" model (mean return after fees +2.39%) **passed under `a652b5b` and is rejected by `main`**.
- At every setting, `a652b5b`'s records lacked the minimum's key.

**Fixed** (`09f9fa6` on #226). The owner offered two routes, a separate LLM threshold or an explicit approval of the change; this keeps the threshold.
- `gate_min_return_after_fees` stays as saved and is the LLM signals' rule b (`GateSettings.min_mean_return`). Its field is back in Settings > Training as "Minimum mean return per LLM signal after fees %".
- A trained model keeps its own per-day minimum. The per-trade value is never turned into it.
- `llm_settings_ui.py` is `main`'s again.
- With the fix, every decision figure equals `main`'s at all seven settings. The tests pin `main`'s texts at +3%, at −5%, and at +1% with the 90th percentile.

### 2. Provenance: earlier looks at results

**The finding.** The pattern model has already been evaluated on part of the proposed holdout. Those observations are not unseen evidence for it.

**Built** in #227: `model_lab/catalogue.py`'s `LOOKS` records every earlier look at a contestant's results, with the months covered and where each is written up. A batch records, when frozen, which looks cover its lockbox. A contestant with any is never given "Beats random entries": a finalist reads "Passed; its lockbox was seen before, so a final check would not be unseen evidence".

The pattern model's looks:

| Look | Coins | Months | On |
|---|---|---|---|
| FDS-MDL Tests A and B (as STRAT-003, that strategy's exits) | BTC, ETH | 2024-07-01 to 2026-10-01 | 2026-10-07 |
| Volume research, held-out replay and model experiment | 10 | 2026-03-31 to 2026-11-05 | 2026-11-05 |
| The entry gate's held-out slices of the models in use | the coins with a model | from about 2026-04 | 2026-11-05 |
| Gate diagnostic | 13 | 2026-04-05 to 2026-11-05 | 2026-11-05 |

With batch 1's lockbox (from 2025-05-06), the pattern model's final check cannot be unseen evidence for it. The seven rules have no earlier look at their lockbox.

The phase B timing run (2021-01-01 to 2025-05-06, walk-forward only) is recorded for all 8 of its contestants, and its 8 trials count in phase E's report.

No substantive Copilot review was received on #225 or #226: GitHub reported insufficient review quota.
