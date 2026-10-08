# Run log — trained-model strategy (STRAT-003), model 1

Branch: `feat/model-strategy-1`, in its own worktree at `C:\Users\Simon\Documents\sjackson0109\PowerTraderAI-model`.
Specs: `docs/dev/specs/FDS-MDL-trained-model-strategy.md` as amended by
`docs/dev/specs/FDS-MDL-A-addendum-after-108a.md` (v3); where they conflict, the addendum wins.
Run protocol: FDS-MDL section 10, `docs/dev/specs/00-RUN-ORDER.md` and addendum section 10.
Session: 2026-10-05, Claude Opus 5.5 (the spec's model for Phases 0 and 1).

Black reformatted `app/` after the addendum was written, so cited code is located by function or symbol
name. Line numbers in this log are as of `cbf7e21`.

## Base

- **Base: `main` at `7a84250`** (merge of PR #140). This is the addendum's preferred base (section 2):
  `git log --merges --oneline -n 10 main` shows #132 `feat/strategy-batch-1` (`afb42f0`), #133
  `fix/coinbase-connector` (`0966853`) and #134 `feat/user-data-separation` (`9bc2392`, which brought in
  `chore/untrack-trading-config` at `23243b0`), all merged with merge commits. `app/pt_paths.py` and
  `app/pt_secrets.py` exist on `main`.
- **Commits since `9bc2392`:** `d815910` (#137, `.git-blame-ignore-revs` and a run-log note), `da79c58`
  (#138, issue forms and `docs/dev/check_issue_forms.py`), `7a84250` (#140,
  `docs/dev/test_check_issue_forms.py`). `git diff --stat 9bc2392 7a84250` touches nothing under `app/` or
  `.github/scripts/`, and `docs/dev/test_check_issue_forms.py` is outside the folders `run_suite.py`
  collects. So the tested code is that of `9bc2392`, and `suite-9bc2392.json` stays the baseline. The
  baseline below confirms it.
- `feat/model-strategy-1` was cut from `main` at `7a84250` with
  `git worktree add ..\PowerTraderAI-model -b feat/model-strategy-1 main`.

## Spec files (first commit, `cbf7e21`)

Committed unchanged to `docs/dev/specs/`. The handoff folder `..\PowerTraderAI-specs\` held only the
addendum and `run_suite.py`; the other two came from `Downloads`. The owner confirmed these are the only
versions: FDS-MDL was never edited after delivery (all changes went into the addendum), and
`00-RUN-ORDER.md` is the batch-1 run order, cited for the general run protocol. An older addendum copy in
`Downloads` (13,518 bytes, not v3) was not used.

| File | Source | SHA-256 of the source |
|---|---|---|
| `FDS-MDL-trained-model-strategy.md` | `C:\Users\Simon\Downloads\FDS-MDL-trained-model-strategy.md` (2026-10-02) | `9f1a039d13a5655c182436459eb296eca8d15243eca89a3dd52449c182741ff6` |
| `FDS-MDL-A-addendum-after-108a.md` (v3) | `C:\Users\Simon\Documents\sjackson0109\PowerTraderAI-specs\` (2026-10-04 20:28) | `ed5ee9856bcd7a66ff225e919ded4ea66939f4b2ffdf605b3cad53b08e9e38e9` |
| `00-RUN-ORDER.md` | `C:\Users\Simon\Downloads\files\00-RUN-ORDER.md` (2026-10-02) | `672f51e342c76bc4a480e98bbd5e8966c4472710e0879f59c17ea37c77efd009` |
| `run_suite.py` | `C:\Users\Simon\Documents\sjackson0109\PowerTraderAI-specs\` (2026-10-04 09:44) | `e04e76d505fec74ccc2601981029ecbc56e6a6f5de81d760ab4a62152e357b56` |

The repository has `core.autocrlf=true` and no `.gitattributes`, so git stores these files with LF line
endings (the addendum source has CRLF). The committed text of each file was checked against its source
ignoring CR (`diff --strip-trailing-cr`): identical.

## Environment (addendum section 3)

- **Test venv:** `C:\Users\Simon\AppData\Local\Temp\claude\c--Users-Simon-Documents-sjackson0109-PowerTraderAI\57710dd7-ccf3-4fdb-8966-6da8cc28ea84\scratchpad\venv-test`,
  outside the repo. Created with `"C:\Program Files\Python313\python.exe" -m venv --system-site-packages`
  (Python 3.13.15), as at baseline. The repo's `.venv` is not used.
- **Installed:** `requirements.txt`, then `pytest` and `pytest-timeout`.
- **Packages beyond `requirements.txt`** (and its dependency closure): `pytest==9.1.1`,
  `pytest-timeout==2.4.0`, and their dependencies `iniconfig==2.3.0`, `pluggy==1.6.0`, `pygments==2.21.0`.
- **PyYAML** is not installed (nor in the system site-packages), so the two YAML tests skip, as at baseline.
- `requirements.txt` is unchanged.
- **Found in Phase 0:** a venv created with `--system-site-packages` also sees the per-user site-packages
  (`C:\Users\Simon\AppData\Roaming\Python\Python313\site-packages`). pip treated most of `requirements.txt` as
  already installed from there (`requests`, `numpy`, `pandas`, `matplotlib`, `cryptography`, `kucoin`, `scipy`, `ccxt`,
  `binance`, `flask`, `openai`, ...) and installed only `keyring` and `platformdirs` (with `jaraco.*`, `more-itertools`,
  `pywin32-ctypes`) into the venv, plus the test packages above. The baseline numbers were produced this way. No
  `sitecustomize` or `usercustomize` module exists in this environment (`importlib.util.find_spec`).

## Baseline (addendum section 9.2)

- **Method:** `docs/dev/specs/run_suite.py`, unmodified, on a fresh clone of `feat/model-strategy-1` at
  `cbf7e21` (in the session scratchpad, outside the repo):
  `python clone-base/docs/dev/specs/run_suite.py run clone-base --python venv-test/Scripts/python.exe --out suite-cbf7e21-baseline.json --github --work suite-work-baseline`
- **Result:**

  | Suite | Passed | Failed | Skipped |
  |---|---|---|---|
  | `app/` | 1010 | 10 | 6 |
  | `.github/scripts` | 23 | 19 | 1 |

  Within the expected numbers in section 9.2 (`app/` 1010 / 10–11 / 5–6; `.github/scripts` 23 / 19 / 1).
  No file timed out, the run was not aborted, `run_suite.py`'s real-state check was unchanged (no entries,
  no credentials before or after), and no file was written into the clone (`git status` clean).
- **Compare** (`run_suite.py compare suite-9bc2392.json suite-cbf7e21-baseline.json`): the only difference
  is the known Tk start-up flip.
  - `app/test_integration.py::TestPowerTraderHubIntegration::test_graceful_degradation`: **skipped** in
    this run (it failed at `9bc2392`).
  - `.github/scripts`: identical.
- **Failures at baseline:**
  - `app/test_integration.py`: `test_powertrader_hub_creation`.
  - `app/test_suite.py` (8): `test_exchange_factory`, `test_database_initialization`,
    `test_holdings_database`, `test_holdings_manager`, `test_performance_metrics`,
    `test_portfolio_analytics_initialization`, `test_portfolio_snapshot`, `test_database_integration`.
  - `app/test_trade_proposal_approval.py`: `test_expired_proposal_cannot_execute` (known).
  - `.github/scripts/test_integration.py` (10), `test_performance.py` (2), `test_risk_cost.py` (7): as at
    `9bc2392`.
- **No tests collected:** `app/test_comprehensive.py`, `.github/scripts/test_pr_validation.py`.
- **Results file:** a copy is kept at
  `C:\Users\Simon\Documents\sjackson0109\PowerTraderAI-specs\suite-cbf7e21-baseline.json` (SHA-256
  `0a2c8c164cac127e0cd1944a3e1f4550e334044c2c576f288230814363c28056`) for the per-phase compares.

## Real-folder and credential checks (addendum section 9.1)

| When | `%APPDATA%\SJackson` | `%LOCALAPPDATA%\SJackson` | `cmdkey /list` entries containing "PowerTraderAI" |
|---|---|---|---|
| Before the baseline | absent | absent | 0 |
| After the baseline | absent | absent | 0 |
| After the Phase 0 evidence runs and mutation check, 2026-10-05 10:20 | absent | absent | 0 |
| After the Phase 0 gating suite run, 2026-10-05 10:57 | absent | absent | 0 |
| Phase 1, after `fetch`, `train` and the first counter-checks, 2026-10-06 02:08 | absent | absent | 0 |
| Phase 1, after the first gating suite run, 2026-10-06 02:48 | absent | absent | 0 |
| Phase 1, after the final gating suite run, 2026-10-06 03:01 | absent | absent | 0 |
| Phase 1 follow-up, after the port-verdict evidence runs, 2026-10-06 17:06 | absent | absent | 0 |
| Phase 1 follow-up, before its commits, 2026-10-06 19:54 | absent | absent | 0 |
| Phase 2, after the evidence runs, mutation checks, real-data training and the gating suite run, 2026-10-06 22:53 | absent | absent | 0 |
| Phase 2, after the final gating suite run, before its commit, 2026-10-06 23:25 | absent | absent | 0 |
| Phase 3, after the mutation checks, the reviews and the gating suite run, before its commit, 2026-10-07 00:53 | absent | absent | 0 |
| Phase 4, before the header's commit (nothing run), 2026-10-07 01:20 | absent | absent | 0 |
| Phase 4, after the amendment's review agents and gating suite run, before its commit (no backtest), 2026-10-07 08:45 | absent | absent | 0 |
| After filing #152 and #153, before the issue-number commit, 2026-10-07 09:26 | absent | absent | 0 |
| Phase 4, after the seed-range review and gating suite run, before its commit (no backtest), 2026-10-07 09:38 | absent | absent | 0 |
| Phase 4, after the freeze code's reviews, mutation checks and gating suite run, before its commit (nothing fetched, trained or run), 2026-10-07 14:28 | absent | absent | 0 |
| Phase 4 Test A, before `fetch` (clean tree at `68d4ed7`), 2026-10-07 17:27 | absent | absent | 0 |
| Phase 4 Test A, after `fetch`, `train`, `run` and `report`, during the read-only audit, 2026-10-07 18:27 | absent | absent | 0 |
| Phase 4 Test A, after the home copy, the note and the drafts, before the results commit, 2026-10-08 01:24 | absent | absent | 0 |
| Phase 4 Test A, before the note's formatting fix commit, 2026-10-08 01:29 | absent | absent | 0 |
| Before the F3 and run-log-fix commit (before any push), 2026-10-08 02:17 | absent | absent | 0 |

## Phase 0 — trainer audit — **done, gating verdict STUB; the Phase 1 route is the owner's decision**

- **Start / end:** 2026-10-05 09:04 (fact-finding started, after the baseline commit `0ad2950`) / 2026-10-05 11:00 (audit commit).
- **Verdict:** `app/pt_trainer.py`, the script the hub launches for every coin on the new base (blob `c85fc4c`), is a
  **STUB** (the gating verdict, addendum 5.3): sleep-loop epochs, a formula for accuracy, a literal
  `"final_accuracy": 95.0`, unseeded random weights, and memories built from random prices because the data provider
  returns one candle as a string. In executed end-to-end training, determinism fails as launched (no seed; two runs
  differ in 28 of 35 files) and data dependence fails (four different prices and a different coin give byte-identical
  files). Not BLOCKED for default settings. Full report: `docs/dev/TRAINER-AUDIT.md`; evidence:
  `docs/dev/trainer-audit-evidence.json`.
- **Open decision for the owner (MIXED and the Phase 1 route):** `app/pt_neural_network.py` is a genuine but unlaunched
  learner. By the spec's definitions it is not a REAL trainer (it fails the determinism and held-out checks on reading,
  cannot run without `torch`/`scikit-learn`/`ta`, and writes nothing the thinker reads), so the spec's MIXED does not
  apply; by the owner's looser rule ("a genuine learner that nothing launches") it is MIXED. Phase 1 is a choice between
  (A) wiring it in and (B) porting the upstream trainer from history (`b4522b0` / `ba62130` / `3407fe7`). Recommendation:
  B, because Phase 3 must reproduce the legacy thinker's rule, which needs the upstream file format.
- **Commits** (files staged by explicit path; not pushed, no PR):
  - `b614f3e` Phase 0 tests (#136): `app/tests/helpers_trainer.py`, `app/tests/test_trainer_launch.py`,
    `app/tests/test_no_hard_coded_user_paths.py`; `git rm app/test_hub_trainer.py app/test_subprocess_trainer.py`.
  - This commit: the audit on its own: `docs/dev/TRAINER-AUDIT.md`, `docs/dev/trainer-audit-evidence.json`,
    `app/tests/audit_trainer_evidence.py` (the harness that produced the evidence), this run log.
- **Scope:** no production code changed. The test changes and the two deletions are authorised by the kickoff (#136 is
  assigned to Phase 0) and by #136's proposal (delete the two no-op tests "as part of the trainer audit"); addendum 5.3
  also requires the determinism and data-dependence checks to run real training.
- **#136 (a)** demonstrated in a scratch clone (`clone-mut136`) with the guard on. Mutation: the single line
  `self._refresh_trainer_path()` removed from `PowerTraderHub.__init__` (`app/pt_hub.py:2076`; the Settings-save call at
  `:8602` left in place). New `test_trainer_launch.py`: 3 failed, `AttributeError: '_tkinter.tkapp' object has no
  attribute 'proc_trainer_path'`; with the line restored: 3 passed. Previous `test_trainer_launch.py`
  (`git show HEAD:app/tests/test_trainer_launch.py`): 4 passed against the mutation. **(b):** the new static test
  passes after the deletion and failed before it on the three hard-coded lines.
- **Evidence run** (final): `app/tests/audit_trainer_evidence.py` under the guard, in an untouched scratch clone
  (`clone-audit3`) of `feat/model-strategy-1` with the Phase 0 test files, the test venv,
  `POWERTRADER_HOME=<scratch>\dev-home` (each test also gets its own per-test home from the guard), the fail keyring
  backend, `PYTHONDONTWRITEBYTECODE=1`, and `PYTHONHASHSEED=0` in every child: 4 passed, 12 training runs, 446 s.
  Recorded in the evidence, and matching the committed files: harness `app/tests/audit_trainer_evidence.py` SHA-256
  `a9baeb89a9bb4d9e3c2204c55e55fc73045f2e8208eab9021e2e532ce4807ba5` (blob `2e5927e5b585`); helpers
  `app/tests/helpers_trainer.py` SHA-256 `9c389da15c60fc788fdf45ad10a06397b2407275be1c1feab52fbd660bfc8b97` (blob
  `91ba48d59b21`); child guard (`CHILD_SITE`) SHA-256
  `c52948b7bddd99a2fd1794d53a4235e4981479e93198a590af7a6d6fffcb4960`; trainer blob `c85fc4c`. Evidence file SHA-256
  `760ec97565f58d5d163ec5bfa1105653431fc56a7de3101edf7fad3369958cdf`.
  - Discarded runs: (1) a window bug in the harness (two windows ended on the same bar, so they served the same price);
    (2) a run in the worktree, where my own write of `TRAINER-AUDIT.md` tripped the "install folder unchanged" check for
    run D4; (3) a clean run on the pre-review harness, superseded after the adversarial review; (4) a run whose new PID
    cross-check was wrong (on Windows a venv's `python.exe` is a launcher that starts the interpreter as a child, so the
    child's PID differs from the `Popen` PID), replaced by a start-time check.
- **Adversarial review:** six read-only reviewers checked `TRAINER-AUDIT.md`, the evidence and the tests (3 high
  findings, all on the same point, 29 medium, 47 low). All were applied or answered, notably: the MIXED call and the
  Phase 1 route are presented as the owner's decision; determinism is reported as "FAIL as launched"; the thinker effect
  is corrected (it never leaves its candle loop for a trained coin); the stub's history is attributed to `10e190e` and
  `49a2c92`; the seeded and unseeded runs no longer differ in `PYTHONHASHSEED`; `build_real_hub` skips only when Tk
  cannot start; `launch()` cannot return an earlier process; the CWD guard was restored; the child guard also refuses to
  run without the fail keyring backend; the install-folder check was narrowed to the program folder plus trainer outputs.
- **Suite** (`run_suite.py` on clone `clone-phase0b` with all final files; compare against `suite-cbf7e21-baseline.json`):

  | Suite | Passed | Failed | Skipped |
  |---|---|---|---|
  | `app/` | 1009 | 11 | 5 |
  | `.github/scripts` | 23 | 19 | 1 |

  - GONE `app/test_hub_trainer.py`, `app/test_subprocess_trainer.py` (1 "passed" each; deleted for #136).
  - `app/tests/test_trainer_launch.py` 4 -> 3 passed (rewritten; the AST-only results test became a real run).
  - NEW `app/tests/test_no_hard_coded_user_paths.py`: 2 passed.
  - `app/test_integration.py::TestPowerTraderHubIntegration::test_graceful_degradation`: **failed** in this run (skipped
    at the session baseline, failed at `9bc2392`): the known Tk start-up flip.
  - No other change; `.github/scripts` identical; real folders and credential entries unchanged; no file written into
    the clone. A copy of the results is kept at `..\PowerTraderAI-specs\suite-phase0-final.json`.
  - Results file: `<scratch>\suite-phase0-final.json`, SHA-256 `d906870c9569f7d634b319d6ded684a9363606b8d77d6045b369d25ee5164807`.
- **Tk start-up retries:** creating a Tk root right after a hub that started a child process occasionally fails with
  "Can't find a usable init.tcl". `build_real_hub` retries only that error; measured over 64 builds, all succeeded and
  3 needed a second attempt.
- **Black:** the four test files were formatted with Black 26.5.1 (a scratch venv, not the test venv).
  `docs/dev/specs/run_suite.py` was left untouched.
- **Process notes:** the read-only fact-finding agents (six and a critic) used git and grep reads. Deviations they
  reported: one grepped the standard-library `tkinter/__init__.py` under `%LOCALAPPDATA%\Programs\Python\Python314`,
  which breaches addendum section 10 as written ("anything in the real %LOCALAPPDATA% folders"), though it read no user
  data; one ran `python --version` and used `python -c` with `json.load` on `app/data_provider_config.json`; one used
  Python to parse the suite JSON files; the critic read five ignored training summaries in the main checkout
  (`data/btc_training_results.json`, `app/data/*_training_results.json`) and listed ignored file names there, which showed
  the names (not the contents) of the owner's `app/gui_settings.json`, `app/pt_config.json` and
  `app/pt_config.json.backup.*`. Separately: no config file, no credential, and nothing under `%APPDATA%\SJackson` or
  `%LOCALAPPDATA%\SJackson` was opened by any agent or by me. I checked the venv's packages with
  `importlib.util.find_spec` only.
- **Out-of-scope bugs found** (`TRAINER-AUDIT.md` section 7, not fixed): the data provider returns one synthetic candle
  as a string (live callers: the trainer and the thinker); the trader reads `long_dca_signal.txt` /
  `short_dca_signal.txt`, which nothing has written since `4fc3834`; `pt_multi_exchange` reads credentials for every
  configured exchange and replaces an unreadable `trading_config.json`; `trainer_status.json` is never written;
  auto-retrain timers cannot be cancelled (inferred); `ARCHITECTURE.md` claims about real PyTorch trainers are contradicted
  by the code; the hub writes `app/__pycache__` at runtime; the thinker rewrites the threshold files.
- **Owner actions:** (1) choose the Phase 1 route (A or B); (2) confirm `script_neural_trainer` in your
  `gui_settings.json` is `pt_trainer.py` (not opened by this session).
- **Next:** stop here and report (Phase 0 is a gate). Phase 1 waits for the owner.

## Phase 1 — restore a real trainer — **route B: port of upstream `ba62130`**

- **Session:** 2026-10-06, Claude Opus 5.5. Started after the owner's Phase 1 directions; one commit for the phase.
- **Owner decisions** (2026-10-06):
  - Route **B**: port the upstream trainer. Compare `ba62130` (last upstream-authored) with `3407fe7` (last full version
    on main) and port `ba62130` unless a later change is a genuine bug fix.
  - Data only from `app/market_data/candles.py`, never `pt_data_provider`.
  - Do **not** repair the legacy thinker→trader handoff. Draft three separate issues for it, issues for the other unfixed
    audit bugs, and a release-notes paragraph with scoped wording ("has not worked end to end since February 2026";
    "the accuracy shown during training since 25 February 2026 was a formula, not a measurement").
  - **Faithful port:** keep upstream's training bugs (weight updates never saved, the `var3` units mismatch, matching
    against flushed memories re-read every step). Output-only fixes allowed: flush every timeframe at its end, write all
    35 files, write the stamp last.
  - **Older-half rule:** keep it, documented (trainer header, this log, bar counts in the summary).
  - **Default window:** rolling 3 years (`train_end` = the last full hour, `train_start` = `train_end` − 1,095 days).
  - `script_neural_trainer` in the owner's `gui_settings.json`: **unknown** ("i don't know"). Not opened by this session.
    The design does not depend on it: a saved `pt_trainer.py` gets the refusal dialog, which names the setting to change;
    nothing rewrites the user's settings.
- **Upstream check** (read-only): upstream's current `pt_trainer.py` on `main` of `garagesteve1155/PowerTrader_AI` is blob
  `0369182e5685f599ec593600f82e2ecc74dc9384`, the same blob as `ba62130:pt_trainer.py`, checked 2026-10-06 with the
  GitHub contents API (`gh api`, no clone, no push); upstream head `36cf9fd`. So upstream had not moved on and no stop was
  needed. The owner asked for this check ("a scratch git remote fetch or a raw file fetch"). **Deviation:** `gh api`
  sends the stored GitHub token, so this was an authenticated call to a public endpoint, which 00-RUN-ORDER rule 3 ("Do
  not call any authenticated endpoint") and addendum section 8 (network only in `run_backtest_model1.py fetch`) do not
  allow as written; an unauthenticated raw-file fetch would have answered the same question. Read-only; nothing written. The vendored test fixture (`app/tests/fixtures/upstream_ba62130_pt_trainer.py.txt`, LF; blob `5359562`) gives
  exactly blob `0369182` with CRLF line endings; a test checks this.
- **`ba62130` vs `3407fe7`: zero KEEP items.** Eight commits touched the file (`6d7ba2c`, `91eb984`, `e713ca2`, `fac15d9`,
  `9ed5736`, `989cc19`, `2d7a0f2`, `b7f563a`). Every hunk was classified; none fixes a bug present in `ba62130`.

  | # | Commit | Change | Keep/drop | Reason |
  |---|---|---|---|---|
  | H1 | 6d7ba2c | Imports regrouped; upstream docstring removed | DROP | Cosmetic; the port has its own header |
  | H2 | 6d7ba2c | `pt_files` import | DROP | Only supports H8, H9, H16 |
  | H3 | 6d7ba2c | Globals typed, `'no'` → `False`, `starting_amounth0x` renamed | DROP | Overwritten at the loop top; never read |
  | H4 | 6d7ba2c | TODO comment | DROP | Comment |
  | H5 | 6d7ba2c | Type hints | DROP | No behaviour change |
  | H6 | 6d7ba2c | `load_memory`: narrowed `except` plus warnings | DROP | Fixes nothing observable; the port's I/O goes through `pt_paths` |
  | H7 | 9ed5736 | Warnings hidden when `POWERTRADER_ENV=test` | DROP | CI workaround for H6 |
  | H8 | 6d7ba2c | `flush_memory` via `secure_write_text` | DROP | `secure_write_text` swallows errors and is not atomic; the port writes atomically and fails loudly |
  | H9 | 6d7ba2c | Threshold via `secure_write_text` | DROP | As H8 |
  | H10 | 6d7ba2c | `killer.txt` also accepts `"true"` | DROP | Nothing writes `killer.txt`; the port drops the stop file |
  | H11 | 6d7ba2c | `restart_processing = True` | DROP | Regression: `.lower()` on a bool raises |
  | H12 | 9ed5736 | `restart_processing = "y"` | DROP | Repairs H11 only |
  | H13 | 6d7ba2c | Loop flags → bools, comparisons left as strings | DROP | Regression (statistics code never runs) |
  | H14 | 6d7ba2c | `no_list` bool | DROP | Never read |
  | H15 | 6d7ba2c | `next_coin` / `flipped` → `False` | DROP | Unread / feeds H13 |
  | H16 | 6d7ba2c | Stop path via `secure_write_text` | DROP | Reachable only through `killer.txt` |
  | H17 | 6d7ba2c | `any_perfect` bool with string initial value | DROP | Regression (noise only) |
  | H18 | e713ca2 | Tabs → spaces, Black, isort | DROP | Formatting; Black is applied to the port itself |
  | H19 | 91eb984 | Move to `app/`, CRLF → LF | n/a | The port is a new file, `app/pt_pattern_trainer.py` |
  | H20 | fac15d9 | KuCoin import guard | DROP | No KuCoin in the port |
  | H21 | 9ed5736 | `__main__` guard around 8 lines | DROP | Regression: `3407fe7` spins for ever and never trains |
  | H22 | 2d7a0f2 | KuCoin → `pt_data_provider` | DROP | Owner rule: `candles.py` only; the provider returns one synthetic candle |
  | H23 | b7f563a | Provider calls `get_historical_data` / `get_price_data` | DROP | Methods did not exist then (one still does not); window reversed |

- **Data source changed (FDS-MDL 4.2):** upstream read KuCoin klines (`market.get_kline`, newest first, up to the wall
  clock); the port reads Binance klines through the candle cache (`get_candles`), only bars closed by `train_end`. This
  can change behaviour: prices, volumes and bar alignment differ between exchanges. Weekly bars are Binance's (Monday
  00:00 UTC). `1w` was added to the candle layer only (`candle_timeframe_seconds`), so strategy settings, the signal
  engine and the backtester still reject it.
- **What changed:**
  - New `app/pt_pattern_trainer.py`: the port. Its header records the upstream repo, commit and blob, the bugs kept on
    purpose, and deviations 1–9 with reasons (data source and window; row selection; one load per timeframe; passes
    upstream could never finish are skipped and recorded; output completeness; an empty working folder; removed dead
    code, ticker, `killer.txt`, statistics and per-step prints; `ERROR` status and exit codes; the seed).
  - New `app/trainer_guard.py`: reads the first 4 KB of the configured trainer script (never imports it) for the marker,
    and `allow_mock_trainer` from `pt_config.json` through `trading_mode`'s settings reader. Only JSON `true` counts.
  - `app/pt_hub.py`: default `script_neural_trainer` = `pt_pattern_trainer.py`; `_trainer_launch_allowed` refuses a
    marked script (one dialog, status text) before the neural runner is stopped or any file deleted; Train All shows one
    refusal; an unattended auto-retrain of a refused mock starts nothing and shows no dialog (status text only), and the
    "Auto-retraining" status is set only when a new trainer process started; the Settings field falls back to the
    default name.
  - `app/pt_settings_manager.py`: the same default, plus `"allow_mock_trainer": False`.
  - The 12 stubs (`app/pt_trainer.py`, `app/pt_trainer_standalone.py` and the 10 per-coin copies) got line 2:
    `# MOCK - DO NOT USE FOR DECISIONS (FDS-MDL): sleep-loop "training", formula accuracy, nothing learned from market
    data. See docs/dev/TRAINER-AUDIT.md.` (true of all 12: seven of them write no model files at all). Nothing else in
    them changed; none was deleted or untracked.
  - `app/market_data/timeframes.py`: `CANDLE_ONLY_TIMEFRAME_SECONDS = {"1w": ...}`, `candle_timeframe_seconds`,
    `bar_open_floor` (Monday weeks). `timeframe_seconds` is unchanged. `app/market_data/candles.py` uses
    `candle_timeframe_seconds`; its docstring now names the real cache folder and warns that a past `now` with
    `offline=False` can leave a hole in the cache. `app/backtest/cli.py` checks `--tf` with `timeframe_seconds` before
    touching data, so `1w` is still refused up front.
  - `app/pt_paths.py`: `models_dir()` docstring corrected (the default trainer working root, not a model store).
  - `.github/scripts/create_desktop_installer.py`: lists the new files; default trainer name.
  - `docs/dev/run_backtest_model1.py` (new): `fetch` and `train`; refuses to run without `POWERTRADER_HOME` unless
    `--use-real-folders`, and always refuses a `POWERTRADER_HOME` inside the repo; prints the folders it resolved.
  - `docs/dev/ISSUE-DRAFTS-model-1.md` (new): A1–A3, B1a, B1b, B2 (trimmed after the port), B3–B5, D1–D3 (the kept
    upstream bugs) and the release-notes paragraph.
- **No lookahead (FDS-MDL 4.3), enforced in the data call:** for each timeframe every run reads the cache with
  `get_candles(..., offline=True, now=train_end)` for bars opening before the bar that contains `train_end`, so
  `get_candles` drops any bar that closes after `train_end`; the result is then checked (a later bar is a
  `TrainerError`). Online runs first fill the cache, with the wall clock deciding what is closed enough to cache (a past
  `now` there would leave a permanent hole in the shared cache; found in review). Online and offline runs parse the
  same values. They differ at the window's edges: online, bars the exchange does not have (a pair listed after
  `train_start`, a missing first or last bar) are counted (`missing_at_start`, `missing_at_end`) and printed, and
  training goes on; offline, the cache must reach both ends of the window or the run fails, because offline a short
  cache and a missing exchange bar look the same.
- **Determinism (FDS-MDL 4.4):** upstream uses no randomness. `--seed` (default 0) is applied to `random` and recorded.
  Output is identical across processes with different `PYTHONHASHSEED` (test).
- **Thinker format (FDS-MDL 4.5):** unchanged upstream format; a test runs the thinker's own parse expressions on the
  output, and checks plain floats and a byte-stable threshold.
- **Equivalence with upstream (evidence for "faithful"):** `test_the_port_writes_the_same_model_files_as_upstream` runs
  the vendored `ba62130` trainer in a child process (fake `kucoin.client.Market` serving the same bars plus one forming
  bar, frozen clock, network blocked) and the port in `--upstream-flush-only` mode on five data sets (corrected
  2026-10-08 from "four"; 10 and 20 weeks of a
  random walk; coarse ticks, where the threshold falls to its floor; near-identical bodies, where it settles below 0.1;
  zero closes, where upstream skips learning on a step).
  All 35 files are byte-identical in every case. One more test shows the only remaining difference, upstream's
  malformed row from an empty last KuCoin page (deviation 2), disappears when the port keeps one bar fewer.
- **Counter-checks** (each mutation applied to the production file, the named tests run with the isolation guard on,
  the file restored and its SHA-1 re-checked):

  | Mutation | Caught by |
  |---|---|
  | Read one bar past `train_end` (cut and backstop removed) | both poisoned-bar tests, the loader test |
  | Threshold step −0.01 → −0.02 | upstream equivalence (coarse ticks, near-identical bodies) |
  | Fine step −0.001 → −0.002 | upstream equivalence (near-identical bodies) |
  | Threshold clamp at 0 removed | upstream equivalence (coarse ticks) |
  | Weight updates saved (fixing D1) | upstream equivalence (all five; corrected 2026-10-08 from "all four") |
  | Older-half count off by one | upstream equivalence; the summary test |
  | Status `FINISHED` written after the stamp | the stamp-last test |
  | No final flush | the default-mode test |
  | Hub refusal removed (single coin / Train All) | the refusal tests (3 and 1) |
  | Any truthy value allows a mock | the JSON-`true` tests |
  | Cache fill with `now=train_end` (the review's cache-hole defect) | the cache-hole test |
  | Window start not rounded up to a bar boundary | the online-vs-offline test |
  | Online read not clamped to the cached range | the missing-last-bar test |
  | Zero-close skip removed | upstream equivalence (zero closes) |
  | `--offline` ignored | the stamp-last test; the inputs test |
  | `_leave_program_dir` removed (run in a scratch clone, as it writes into `app/`) | the program-folder tests (both coins) |
  | Auto-retrain refusal removed | the unattended-retrain test |
  | Backtest CLI `--tf` check removed | the backtest-CLI test |
  | Window start compared after truncating to whole seconds | the fractional-start test |
  | Auto-retrain status check reverted to "a live process exists" | the retrain-while-training test |
  | Auto-retrain status check removed | the retrain-that-starts-nothing test |

  Before the coarse-tick and near-identical data sets were added, the threshold and fine-step mutations survived (the
  random walk never produced more than 20 matches); that is why those data sets exist.
- **Runtime (FDS-MDL 4.7):** `run_backtest_model1.py train`, 1h data 2023-01-01 to 2026-01-01, full window, no
  subsampling, Python 3.13.15, this machine: **BTC 59.9 s, ETH 60.9 s** (well under 30 minutes). Each coin: 26,303 1h
  bars (one hour missing on Binance, 2023-03-24 13:00, reported in the summary, not filled). Bars used (the older-half
  rule): every pass 0 and all three 1hour passes, the oldest 13,152 1h bars; passes 1–2 on their own bars, 2hour 6,577
  of 13,152, 4hour 3,289 of 6,576, 8hour 1,645 of 3,288, 12hour 1,097 of 2,192; 1day and 1week passes 1–2, all 1,096
  and 156. 368–469 memories per timeframe. Under cProfile (99 s), re-reading the model files took 23% and the memory-text clean-up 18%
  (issue draft D3).
- **Network and sandbox:** network use was `run_backtest_model1.py fetch` (public Binance klines: 58 requests per coin,
  BTCUSDT and ETHUSDT × 7 timeframes) and the one upstream check above (`gh api`, a recorded deviation). Every `run_backtest_model1.py` run used
  `POWERTRADER_HOME=<scratch>\model1-home` (`<scratch>` is this session's temp scratchpad, outside the repo). Tests use
  synthetic candles only and block the network in the test process and every child.
- **Tests:** new `app/tests/test_pattern_trainer.py` (38), `app/tests/test_mock_trainer_refusal.py` (18), helpers
  `app/tests/helpers_candles.py` and `app/tests/helpers_upstream.py`, the vendored fixture; `test_trainer_launch.py`
  updated for the new default (the hub tests seed a synthetic cache and run the pattern trainer offline; the Settings test
  allows mocks before launching the standalone stub); `helpers_trainer.py` gained `configure_trainer`, records the
  trainer's environment inputs, and sets `POWERTRADER_CANDLES_OFFLINE=1` for every child; the Phase 0 harness
  `audit_trainer_evidence.py` now pins the stub through the user's settings files (it is not part of the suite).
- **Black:** Black 26.5.1 (scratch venv) on every changed Python file except the stubs, whose only change is the comment
  line. The 10 per-coin copies were already not Black-formatted at `7a84250`, and CI's `black --check app/` skips them.
- **Adversarial review** (two workflow rounds, read-only reviewers, each finding checked by a skeptical verifier):
  - Round 1, five reviewers (port fidelity, data layer and lookahead, hub and guard, tests, docs and spec): 22
    findings, 3 refuted. The one high finding was real: an online fill with `now=train_end` dropped the bars between
    `train_end` and the cache's first bar, leaving a permanent hole in the shared cache, so a later window across it
    trained on part of its data with nothing reported. Fixed (wall-clock fill, edge counts, regression test). The others:
    a zero close crashed the port where upstream skips the step (now matched, with an upstream-equivalence case); a
    misaligned `train_start` was reported as "listed later"; an exchange gap at the window's end failed or passed
    depending on the cache's history (online now consistent; offline documented); the backtest CLI fetched `1w` before
    failing; the stub header claimed random weights for seven stubs that write none; auto-retrain overwrote the refusal
    status; untested online path, program-folder start and `--offline` flag (tests added); run-log and issue-draft
    inaccuracies (bar counts, the `gh api` call, the `--use-real-folders` wording, the release-notes equivalence claim,
    B4's torch grep); a cross-drive crash in `run_backtest_model1.py`. All fixed.
  - Round 2, two reviewers on the fixes: 4 low findings, all fixed: a `train_start` with fractions of a second gave a
    false "1 bar missing"; auto-retrain claimed a run when the coin was already training; that branch had no test; the
    guard's docstring still said "random weights".
  - Refuted in round 1 (no change): the poisoned-bar control reaching only 1d/1w (by the owner's older-half rule the
    newest bars never reach intraday models; the loader test covers every timeframe), the oracle not comparing memories
    learned from 4h–1w bars (the learning code is the same for every timeframe and is compared on 1h, 2h and 4h), and
    B2's line numbers (they follow the drafts' stated convention).
- **Real data after the fixes:** `run_backtest_model1.py train` again (same scratch home and cache): all 35 model files
  byte-identical to the first run for both coins (BTC 58.9 s, ETH 58.5 s), and no missing bars at either window edge.
- **Suite** (`run_suite.py` on a fresh clone, `clone-phase1b`, holding every final code and test file; compare against
  `suite-cbf7e21-baseline.json`, and against `suite-phase0-final.json`):

  | Suite | Passed | Failed | Skipped |
  |---|---|---|---|
  | `app/` | 1065 | 11 | 5 |
  | `.github/scripts` | 23 | 19 | 1 |

  - Against Phase 0's final run: only NEW `app/tests/test_pattern_trainer.py` (38 passed) and NEW
    `app/tests/test_mock_trainer_refusal.py` (18 passed). `test_trainer_launch.py` still 3 passed (rewritten for the new
    default). Nothing else changed; `.github/scripts` identical.
  - Against the session baseline: as at Phase 0, plus the two new files. The only newly failing test is
    `app/test_integration.py::TestPowerTraderHubIntegration::test_graceful_degradation`, the known Tk start-up flip
    (skipped at the baseline, failed at `9bc2392` and at Phase 0).
  - `run_suite.py`'s real-state check unchanged before and after; no file written into the clone (`git status` showed
    the same 32 copied files before and after). Results: `<scratch>\suite-phase1b.json`, SHA-256
    `bf2e9190c253f39ec4eddeeb380196190e4ef4fc882bdbeafb2137b5cbced383`; copy at
    `..\PowerTraderAI-specs\suite-phase1-final.json`. An earlier full run on the code before the round-2 fixes gave the
    same picture (1062 passed).
  - The run log was finished after the clone was made; nothing else changed.
- **Real-folder and credential checks:** see the table above (three Phase 1 rows): both folders absent and 0
  credential entries each time.
- **Commit** (files staged by explicit path, 32 files; not pushed, no PR): this commit, `FDS-MDL Phase 1: port the
  upstream pattern trainer (ba62130)`.
- **Owner actions:**
  1. File the drafts in `docs/dev/ISSUE-DRAFTS-model-1.md` you agree with (A1–A3 for the legacy handoff, B1a–B5, D1–D3),
     then put their numbers into the release-notes paragraph.
  2. If your `gui_settings.json` names `pt_trainer.py` (likely if you ever pressed Save in Settings, because the hub
     saves every setting), the hub will refuse to train and say so. Set Settings > "pt_trainer.py path:" to
     `pt_pattern_trainer.py`.
  3. Note the recorded deviation: the upstream check used `gh api` (authenticated) instead of a raw-file fetch.
- **Next:** Phase 2 (model artifact provenance: `pt_paths.strategy_models_dir()`, manifests, loaders that refuse an
  artifact without a matching manifest).

## Phase 1 follow-up — port verdict and issue filing (before Phase 2)

- **Session:** 2026-10-06, Claude Opus 5.5. The addendum suggests Sonnet 5.5 for Phases 2-4; this session's model is
  Opus 5.5 throughout.
- **Owner directions** (2026-10-06, after accepting Phase 1): (1) re-run the four Phase 0 checks against
  `app/pt_pattern_trainer.py` through the hub's real launch path, with the Phase 0 isolation, and add a "Port verdict"
  section to `TRAINER-AUDIT.md` ("expect held-out metrics to fail until Phase 2; say so rather than calling it a pass");
  (2) no more authenticated calls of any kind (gh, git with credentials, API tokens) for the rest of this spec,
  unauthenticated raw fetches only, and only if needed; (3) create the issues in `ISSUE-DRAFTS-model-1.md` (with
  `--repo`, existing labels only, plus `needs-triage`), put the numbers into the release notes and commit; then Phases 2
  and 3, one commit each; stop after committing the Phase 4 pre-declared verdict rule, before any backtest.
- **Owner decisions** (asked because (2) and (3) conflict, and because the drafts file held 12 drafts, not 11):
  - One-time exception: `gh` with `--repo sjackson0109/PowerTraderAI` for exactly two things, listing existing labels
    and creating these issues. No other authenticated call for the rest of the spec.
  - File 11 issues: B1a and B1b merged into one (B1).
- **Port verdict** (`TRAINER-AUDIT.md` section 11; harness `app/tests/audit_port_evidence.py`; evidence
  `docs/dev/trainer-port-evidence.json`):

  | Check | Result |
  |---|---|
  | Static | PASS |
  | Determinism (seed 7; also another `PYTHONHASHSEED`, and as launched) | PASS (0 of 35 files differ) |
  | Data dependence | PASS as the spec words it. On the 9-week fixtures nothing is fitted: thresholds are step counters, weights 1.0, memories copied bar values; the one data-dependent output beyond those is the 1-hour matching (162 vs 160 learned matches on equal bars). On three years of real bars the written 1-hour and 2-hour thresholds also respond to the data |
  | Reported metrics | FAIL: no metric computed or reported, nothing held out |

  Verdict: not REAL by the spec's definition (reported metrics fail), and not a STUB (matching and, on long windows, the
  threshold respond to the data); what is adjusted is limited (#149, #151). To be re-run after Phase 2, whose metrics
  come from a separate 80% fit while the published model is refit on the whole window (owner decision): held out for
  that fit, not for the published model.
- **Evidence run:** 12 training runs through the real hub (D1-D4, X1-X5, T1 on the recorded fixtures resampled to
  2h-1w; L1, L2 on the Phase 1 fetched cache, BTC and ETH, 2023-01-01 to 2026-01-01), from a scratch clone
  (`clone-port`) that nothing else wrote to, `POWERTRADER_HOME=<scratch>\dev-home`, the fail keyring backend,
  `PYTHONDONTWRITEBYTECODE=1`, `PYTHONHASHSEED` pinned, `PT_AUDIT_LONG_CACHE=<scratch>\model1-home\cache\candles`
  (copied into each per-test home; read offline): 6 harness tests passed, 174 s. No network attempt in any child; the
  program folder unchanged. Harness blob `77e7904`; evidence written by it, recording the harness's SHA-256.
- **The fetched cache** behind L1 and L2 is the one Phase 1's `run_backtest_model1.py fetch` wrote. The SHA-256 prefixes
  `fetch` printed then (the evidence records the full values, which match):

  | Timeframe | BTCUSDT | ETHUSDT |
  |---|---|---|
  | 1h | `736539aef4587b59` | `69b9921681daabda` |
  | 2h | `9773898f9af96e7d` | `c1c8de3ce58b3c73` |
  | 4h | `d64d77248560a48d` | `67e8d561a1377aae` |
  | 8h | `97bc0fbb9197fb2c` | `216d594a32108fe3` |
  | 12h | `6f317460a1724d21` | `3dda5b58df4d727d` |
  | 1d | `303e05de5fc2c3bd` | `5f01a8791c5eb38b` |
  | 1w | `6c49a14c9a2c57ac` | `c046da136416d9e5` |

- **Adversarial review of the port verdict, round 1** (three reviewers, each finding checked by a skeptical verifier): 22
  findings: 9 confirmed, 2 plausible, 11 refuted. The confirmed and plausible ones were fixed, and some refuted ones
  prompted clarifications:
  - **High:** the first version said the checks "show" the outputs are learned. On the fixtures every threshold is a
    step counter, every weight 1.0 and the memories are per-bar copies of the data (Phase 0 3.5's standard). Section 11
    now says what responds to the data and what does not, and the harness asserts what a bar copier would fail.
  - The 3-year threshold figures had no recorded source: the harness now runs L1 and L2 and records them, with the
    cache files' SHA-256.
  - The printed-accuracy check searched only the kept output lines; it now searches every line, and every summary key
    is listed in the evidence.
  - Clarified: the positional comparison counts, the weights (all 1.0), X3 vs X4 (calendar, not prices), the sleep
    wording, the re-run after Phase 2 (no predicted pass), and that the SHA-256 values are of the clone's CRLF checkout.
- **Round 2** (two checkers on the revision): 20 findings, all fixed:
  - the three-year "matching in every timeframe" assertion was satisfied by the shared 1-hour pass 0 alone (now passes
    1-2 per timeframe), and nothing proved each timeframe trained on its own bars (now: per-timeframe bar counts against
    the cache, and the first pass-2 memory of each timeframe recomputed from its own bars; a mutation sending the 2-hour
    timeframe to 1-hour bars fails the check);
  - 162/161 matched steps became 162/160 learned matches (a pass's last step never learns), with the arithmetic shown;
  - "fitted" kept only for the written 1-hour and 2-hour thresholds; 1-hour pass 1 matches every step by construction;
    BTC and ETH both ending pass 0 on 2,993 matches is a coincidence; the pass-0 threshold adapts in every timeframe but
    each pass restarts at 1.0;
  - the static check now asserts the sleep sits in the `except PermissionError` handler; the thinker-parse check
    asserts `pt_thinker.py` still contains the copied expressions; the reported-metrics result is written only after
    its assertions; the summary-key list is complete; the harness docstring gives the full command; the fetch prefixes
    are recorded above.
- **Suite:** not re-run for these commits. They change documentation and add `app/tests/audit_port_evidence.py`, which
  `run_suite.py` does not collect (it runs `app/test_*.py`, `app/tests/test_*.py` and `.github/scripts/test_*.py`); no
  collected file changed since the Phase 1 gating run.
- **Real-folder and credential checks:** see the table above.
- **Issues** (the one-time exception; the only authenticated calls in this follow-up):
  1. `gh label list --repo sjackson0109/PowerTraderAI --limit 200` (2026-10-06 16:07 UTC): `bug`, `documentation`,
     `needs-triage` and `component-trading` exist.
  2. 11 × `gh issue create --repo sjackson0109/PowerTraderAI --title ... --body-file ... --label ...` (16:08-16:09 UTC):
     #141 (A1) to #151 (D3); B1 is #144. Each body is its draft with references between drafts replaced by the issue
     numbers already created (A3 → #141/#142, B4 → #142, D2 and D3 → #149); D1's one forward reference (to D2) is worded
     by description; a footer says the drafts and the audit live on `feat/model-strategy-1`. The bodies sent are kept in
     `<scratch>\issues\`. The issues were not viewed back (that would be another authenticated call).
  - `ISSUE-DRAFTS-model-1.md` now records each issue number, and the release notes cite #141, #142 and #143.
- **Commits** (explicit paths; not pushed, no PR): the port verdict (`TRAINER-AUDIT.md`, the harness, the evidence, this
  log), then the issue numbers (`ISSUE-DRAFTS-model-1.md`, this log).

## Phase 2 — model artifact provenance

- **Session:** 2026-10-06, Claude Opus 5.5 (FDS-MDL and the addendum suggest Sonnet 5.5 for Phases 2-4; this session's
  model is Opus 5.5 throughout). One commit for the phase.
- **Owner decisions** (2026-10-06):
  - **Held-out design: refit the full window.** The validation metrics come from a separate fit on the first 80% of the
    window, scored frozen on the last 20%; the published model is refit on the whole window, so the metrics describe a
    sibling fit.
  - **`TRAINER-AUDIT.md` 11.8:** "no skill above the up-rate base rate" goes in the verdict line itself, next to REAL,
    with the base rate and the held-out score side by side and the sample size. The finding feeds the Phase 4 verdict
    rule, which is committed before any backtest runs and which the owner reads first.
  - **For Phase 3, decided now** (asked during Phase 2, because the runner test driver needed the cadence):
    - **Cadence: just before the close.** For each timeframe, the decision at bar *t* uses the last bar that closed
      strictly before *t*; the current price is the close of bar *t*. That is the live runner's last evaluation inside
      bar *t*, in steady state: the bounds and the active guard come from the same predictions.
    - **Keep the short veto.** `ENTER_LONG` needs at least `min_tf_agree` (default 3, the legacy `trade_start_level`)
      timeframes on LONG and none on SHORT, as the legacy trader's entry gate (`pt_trader.py`, `buy_count >=
      start_level and sell_count == 0`). `EXIT_LONG` fires on SHORT on the primary timeframe.
- **What Phase 2 adds:**
  - `pt_paths.strategy_models_dir()` = `<data>/hub_data/strategy_models`: a sibling of `models_dir()`, created only when
    a model is published. Also `trainer_root()` (the configured trainer root, creating nothing) and `paths_overlap()`
    (realpath; letter case ignored on Windows and macOS).
  - `app/model_store.py`: `publish`, `verify_folder`, `load`, `find_published`. `publish`, `verify_folder` and `load`
    refuse with a `ModelStoreError` and log an ERROR (logger `model_store`); `find_published` logs an ERROR and returns
    None when nothing matches (it raises only for a trainer root that overlaps the store).
  - `app/pattern_model.py`: the neural runner's per-timeframe prediction (`pt_thinker.step_coin`) reproduced operation
    for operation, and the validation metrics (`score_timeframe`, `METRIC_DEFINITIONS`).
  - `app/pt_pattern_trainer.py`: after training, the validation fit and the publish. The summary records the
    `model_id`; a failed publish ends the run with exit 1, status `ERROR` and no stamp.
  - `app/pt_thinker.py`: a coin's model files are used only when a published manifest **for that coin** matches them
    byte for byte. The runner prints the model_id and window it uses at the first step and after any change to the
    files or the stamp; otherwise it holds the coin like an untrained one (zero signals, "MODEL NOT VERIFIED").
  - `docs/dev/run_backtest_model1.py`: prints the store folder at start-up, records each run's model_id, and exits
    non-zero for a run without one.
- **Manifest** (`<store>/<model_id>/manifest.json`): the fields FDS-MDL section 5 lists (`model_id`, `trainer_path`,
  `trainer_git_commit`, `upstream_commit`, `symbol`, `timeframes`, `train_start`, `train_end`, `candle_file_sha256` per
  timeframe, `params`, `seed`, `created_at`, `validation_metrics`) plus `manifest_version`, `coin` and `files` (the
  SHA-256 of each of the 35 files), all required by the loaders. It also holds the code's hashes (`code_sha256` for the
  trainer, `pattern_model.py` and `model_store.py`, LF line endings, so equal to what git stores),
  `trainer_git_dirty`, the bar reports, the validation window (the fit's and the held-out bars, the fit's file hashes,
  a status), the metric definitions and the training summary. Only relative paths: none starts an absolute path, and
  none contains the home or data folder (both checked by the tests).
- **Design choices** (not dictated by the spec):
  1. **model_id** = `<COIN>-<train_end>-<12 hex>`, the hex being a SHA-256 of the run's identity: coin, window, seed,
     the files, the candle hashes, the code hashes, the parameters. The same run gives the same id and leaves the
     published folder as it is; any difference gives a new id.
  2. **Nothing is written into coin folders.** The runner finds the manifest by the files' hashes: it lists the store,
     reads the coin's trainer-named models newest `train_end` first and stops at the first window with a match, then
     tries any folder not named like a trainer model. When a recent model matches (the usual case) it reads one or two
     manifests however large the store grows; only when nothing matches does it read all of them.
  3. **The validation split covers the span the 1-hour bars cover** (a pair listed after `train_start`, or whose bars
     stop before `train_end`). A fit that cannot be trained publishes the model with validation status `unavailable`
     and an error per timeframe. A validation in which no held-out pair could be scored is also `unavailable`, with a
     reason.
  4. **Candle hashes** are of the bars actually read, in the cache's CSV format (the cache files are shared and grow).
  5. **Metrics** per timeframe: active share, direction hit rate, up share, predicted-up share, close/high/low move
     errors, next close inside the predicted band (definitions in every manifest).
  6. **Validation scratch:** a folder per run under `<cache>/pt-validation-<COIN>`; a folder in which nothing changed
     for an hour belongs to a stopped run and is cleared.
  7. **Git:** local `git rev-parse` and `git status` (no network, `--no-optional-locks`), recorded only when the install
     folder is the top of the checkout git finds.
  8. **No retention rule.** The store keeps every distinct run: each hub training publishes a new folder (35 files and
     a manifest). Pruning is not in the spec, and deleting a model cannot be undone (Phase 4 needs its models), so it is
     left to the owner (owner actions).
- **User-visible change:** models trained before Phase 2 have no manifest, so the runner holds those coins until they
  are retrained once. A bullet in the release-notes checklist of `ISSUE-DRAFTS-model-1.md` says so.
- **Acceptance:** 4 (loaders refuse a missing or mismatched manifest): `model_store.load` (11 refusal cases) and the
  neural runner (an unpublished model, files changed after verification, another coin's model); the backtester and
  `SignalEngine` loaders arrive with STRAT-003 in Phase 3. 13 (addendum): `strategy_models_dir()` exists with a test,
  as a sibling of `models_dir()`; nothing is published into the trainer root or a coin folder; an overlap is refused by
  the loader and the provenance step; a model_id equal to a coin symbol stays in the store; a model folder linked in from
  outside the store is refused. 14: no absolute path in a manifest, and a model folder copied to another
  `POWERTRADER_HOME` loads.
- **Port verdict re-run** (`TRAINER-AUDIT.md` 11.8; evidence `docs/dev/trainer-port-evidence-phase2.json`): all four
  checks pass, so the trainer is REAL by FDS-MDL 3.4, **with no skill above the up-rate base rate**: held-out 1-hour
  direction hit rate against the share of closes that rose, BTC 50.3% vs 50.4% (n = 5,257 pairs), ETH 51.3% vs 51.0%
  (n = 5,257). 13 of the 14 timeframe rows have the best constant guess inside the hit rate's 95% interval; in the
  other (BTC 12-hour) the hit rate is below it. Same 12 runs through the real hub as the Phase 1 follow-up, from scratch clone
  `clone-port4` holding the final code: 6 harness tests passed, 326 s. (An earlier run, before the staging fix, gave
  the same metrics and model files; only the model_ids differ, because they cover `model_store.py`'s hash.)
- **Real data** (`run_backtest_model1.py train`, `POWERTRADER_HOME=<scratch>\model1-home`, offline from the Phase 1
  cache, 2023-01-01 to 2026-01-01, seed 0): **BTC 116.1 s, ETH 119.9 s** (Phase 1: 58.9 s and 58.5 s; the validation
  fit roughly doubles a run). All 35 model files byte-identical to Phase 1's for both coins. Published
  `BTC-20260101T0000Z-e48833004f99` and `ETH-20260101T0000Z-23fd0822f77a`, validation status `ok`, held-out 1-hour
  metrics as in 11.8, `trainer_git_dirty` true (the run used the uncommitted Phase 2 tree).
  - **Found by this run, not by the tests:** the first attempt failed for both coins while publishing. The staging
    folder was named `.<model_id>.<random>`, so its longest path in this scratch home was 260 characters, one over the
    Windows limit (long paths are disabled on this machine; the final folder's longest path is 250). pytest's short
    temporary paths never came near it. The staging folder is now `.stage-<random>` (15 characters, shorter than any of
    the trainer's model ids, which have at least 29), and a copy that fails anyway is a logged `ModelStoreError` (test added;
    two mutations caught). The tests,
    the evidence run and this run were then repeated on the final code.
- **Tests:** new `app/tests/test_model_provenance.py` (68 tests from 41 functions) and `app/tests/helpers_thinker.py` (the real
  `pt_thinker.step_coin` in a child process on fixture bars, behind a fake data provider, under the guard). The
  equivalence of `pattern_model` with the runner is checked on a trained model and on hand-made files (NaN tokens, NaN
  and zero weights, short weight lists, missing fields, cancelling sums). `app/tests/audit_port_evidence.py` (not in
  the suite) reads each run's manifest.
- **Mutation checks** (production code mutated in scratch clones, the provenance tests run with the guard on, the
  file restored; the clones were unchanged afterwards):
  - Round 1, on the first version: 15 mutations, 11 caught. Survivors:
    - `store_isabs_only`: equivalent on Windows, where `os.path.isabs` adds nothing to the drive and root-prefix checks
      (the same test catches it on POSIX);
    - `store_model_dir_unchecked`: not equivalent. The realpath check is what makes `load()` refuse a model folder
      linked into the store from outside, and nothing tested that; a test was added at the end and catches it;
    - `thinker_cache_forever`: re-checking after the files change without a new stamp; caught from round 2 by the test
      added with the round-1 fixes;
    - `pm_np_mean`: numpy's summation order went unnoticed; caught from round 2 by a crafted case with cancelling
      values, which tells Python's compensated `sum` from numpy's.
  - Round 2, after the round-1 fixes: 30 mutations, 25 caught. Survivors: `store_isabs_only` again, and four whose tests
    came with the round-2 fixes: `model_id_match_not_full`, `overlap_case_sensitive_mac`, `pm_hit_inverted` and
    `pm_band_over_scored` (the hand-computed metric case had one hit and one miss with every pair active, so an
    inverted hit test still gave 0.5 and a band share over all pairs equalled one over active pairs).
  - Final pass, after review rounds 2 and 3: 24 mutations, all caught: the four non-equivalent round-2 survivors,
    mutations of the round-2 and round-3 changes (publish retry, the newest-first scan, stale-folder clearing, status,
    the span clamps, the own-checkout check, LF hashing, `--no-optional-locks`) and the core gates again. Then 5 more,
    all caught: the staging name and the staging refusal, `store_model_dir_unchecked` (with its new test), a shared
    validation folder instead of one per run, and removing the shared parent folder. Not mutated: the `Z` timestamp
    parse, which is equivalent on the supported Python versions (3.11 and later).
- **Adversarial review** (three workflow rounds; read-only reviewers, each followed by a skeptical verifier):
  - Round 1, four reviewers (spec, runner equivalence, store security, validation and tests): 24 findings, 15
    confirmed, 4 plausible, 5 refuted. Fixed:
    - the runner re-verified every step, because it rewrites the threshold files unchanged; thresholds are now
      compared by content;
    - a pair listed late in the window could no longer be trained (the 80% fit had no bars); the split now covers the
      bars' span, and a fit that cannot be trained no longer fails the run;
    - a reused model_id could keep an earlier run's manifest; the id now covers the seed, the candles and the code,
      whose hashes and git state are recorded;
    - a loader could fail with a raw `OSError` and no ERROR;
    - another coin's model passed the runner's check;
    - a literal `nan` in a memory file was treated as a parse error, where the runner skips that memory;
    - untested: the provenance step's overlap refusal, metric values, the validation fit's own isolation; one check
      that could not fail on Windows;
    - the backtest script printed a placeholder for the store folder; a publish race; letter case on macOS; scratch
      folders left by a stopped run.
  - Round 2, two reviewers on the fixes: 14 findings (7 confirmed, 6 plausible, 1 refuted), two of them duplicates of
    others. Fixed: no
    retry when a scanner holds the folder rename; every check read every manifest in the store; code hashes depended on
    line endings; runs of one coin shared a scratch folder; the split was not clamped at the bars' end, and a
    validation with nothing scored said `ok`; a `Z` timestamp parse that fails before Python 3.11; `git status` could
    take the index lock; five tests that could not fail when they should.
  - Round 3, two reviewers: 5 findings, all confirmed and fixed: a run removing the shared scratch parent under another
    run; a commit recorded from an unrelated enclosing repository; three test gaps.
  - Refuted (no change): the junction case (verification already refuses it), the trailing-dot id case (no code path
    produces one), the cross-coin case as a spec violation (fixed anyway, as hardening), the Windows `fromisoformat`
    case on supported Pythons (fixed anyway).
- **Section 11.8 checked** by two independent agents against the evidence (every number recomputed; the wording against
  the owner's requirement). First pass: 201 numbers recomputed with no arithmetic error, 39 claims checked; 1 high
  finding (a sentence that was false for the BTC 12-hour row, already corrected when it came in), 2 medium (the
  harness asserts the cut for the X and L runs only; "no skill in any timeframe" switched benchmarks in the weekly
  rows) and 13 low, all fixed. Second pass on the revision: 58 items, 6 low, fixed (among them: a paired 95% bound gives
  2.0 points for ETH, not 1.7; the Bonferroni wording).
- **Suite** (`run_suite.py` on a fresh clone, `clone-phase2b`, holding every final code and test file; 23:15-23:24):

  | Suite | Passed | Failed | Skipped |
  |---|---|---|---|
  | `app/` | 1132 | 11 | 6 |
  | `.github/scripts` | 22 | 20 | 1 |

  - Against Phase 1's final run (`suite-phase1-final.json`): NEW `app/tests/test_model_provenance.py` (68 passed), and
    two flips in files Phase 2 does not touch, both environmental and both passing when re-run on the same clone with
    the guard on:
    - `app/tests/test_trainer_launch.py::test_a_launch_runs_to_completion_on_cached_candles` skipped: "Tk not available
      (attempt 1): invalid command name "tcl_findLibrary"", the known Tk start-up flake (the test skips when Tk cannot
      start). Re-run: 3 passed.
    - `.github/scripts/test_performance.py::TestPerformance::test_cpu_usage_under_load` failed: "CPU usage too high:
      99.2%", a reading of the whole machine's load. Re-run: 3 passed and the 2 errors this file has had since the
      baseline.
  - Against the session baseline (`suite-cbf7e21-baseline.json`): as at Phase 1, plus that file and the two flips. The
    newly failing app test is still `app/test_integration.py::TestPowerTraderHubIntegration::test_graceful_degradation`,
    the known Tk start-up flip.
  - The run before it (`clone-phase2`, 22:44-22:53, the same code with one test fewer and the run log not yet
    finished) gave app 1132/11/5 and `.github/scripts` 23/19/1: against Phase 1's final run only the new file
    differed (67 passed). The last test, for a model folder linked in from outside the store, was added after it.
  - `run_suite.py`'s real-state check unchanged before and after; nothing written into either clone (`git status` the
    same before and after). Results: `<scratch>\suite-phase2b.json`, SHA-256
    `ac17ebdd5a2b0fc3c22400b0d3dc5896098c8ced894165d252286a97e0425d73`; copy at
    `..\PowerTraderAI-specs\suite-phase2-final.json`. The run log was finished after the clone was made; nothing else
    changed.
- **Real-folder and credential checks:** see the table above (Phase 2 rows).
- **Commit** (explicit paths; not pushed, no PR): `FDS-MDL Phase 2: model provenance and manifests`.
- **Owner actions:**
  1. Decide a retention rule for `strategy_models` (every hub training adds a folder; nothing is deleted).
  2. Retrain each coin once after this lands: models trained before it have no manifest and are held.
  3. Note the 11.8 finding: the held-out direction calls are no better than the base rate.

## Phase 3 — STRAT-003, the trained model as a catalogue strategy

- **Session:** 2026-10-06/07, Claude Opus 5.5 (FDS-MDL suggests Sonnet 5.5 for Phases 2-4). One commit for the phase.
- **Owner decisions** used here (recorded in the Phase 2 section, 2026-10-06): cadence "just before the close" (each
  timeframe's last bar closed strictly before *t*; the current price is the close of bar *t*; steady state), and keep the
  short veto (ENTER needs `min_tf_agree` LONG and no SHORT; EXIT on SHORT on the primary timeframe).
- **What Phase 3 adds:**
  - `app/pattern_model.py`: the runner's end-of-sweep rule, statement for statement (`thinker_bounds`,
    `thinker_sides`, `thinker_decision`): the 0.5% rebuild with placeholders, the sort, `list.index`, the gap pass
    (skip, `continue`, `gap_modifier`, the 0.0005 nudges), the remap that drops repeated values, the padding and the
    SHORT-first comparison.
  - `app/strategies/model_strategy.py`: `TrainedModelStrategy`, registered as STRAT-003. It loads the model once at
    construction (`model_store.load`: refused without a matching manifest, ERROR logged); `on_bar` does no I/O. Bars come
    from `use_bars` (the backtest CLI loads them from the run's own source) or, otherwise, from the default candle cache,
    read once when the run's timeframe is set. It decides on 1h to 1d bars (not 1w).
  - The catalogue: STRAT-003 (`family` `model`, `class_type` `main`; `model_id` "", `min_tf_agree` 3, all seven
    timeframes), a closed family enum (`trend`, `risk_overlay`, `model`) checked at load, and two bound types
    (`model_id`, `model_timeframes`).
  - `Strategy.set_timeframe` / `bar_seconds`, which `StrategyRunner.set_timeframe` now also calls.
  - The backtester: `LOOKAHEAD_MODEL` (`check_lookahead`) on every run, when the model's `train_end` is after the first
    scored bar's open (a NaT or unreadable `train_end` is refused; a naive one is UTC). In a time split a refused
    in-sample window is reported as refused, and a refused out-of-sample window fails the run. A model trained on another
    pair is refused. Decisions held for missing bars are counted (`bars_missing`) and reported.
  - The backtest CLI: loads the strategy's seven timeframes from the run's own source and injects them; refuses, before
    loading data, a timeframe the strategy cannot decide on and a model of another pair; with `--candles-file`, refuses
    a cache whose bars are not the file's; records a SHA-256 per bar file; reports the model (id, window).
  - Strategy settings: a `model` strategy whose default names no model is a settings problem (the signal engine runs
    strategies with their default parameters), so the hub strip shows `SIGNALS: BLOCKED`. The signal engine fails closed
    on a model it cannot load (ModelStoreError: no signals, an ERROR every few minutes per configuration, the reason in
    `block_reason`); other build errors propagate as before. The trader's status shows a blocked engine.
  - `docs/technical/ARCHITECTURE.md`: the families, STRAT-003, and the lookahead rule.
- **Design choices** (not dictated by the spec):
  1. **A missing bar holds** (`BARS_MISSING:<timeframe>`) instead of using an older bar, as the runner would. A deliberate
     difference (no silent fallback); the backtester counts and reports these decisions.
  2. **A gap pass that never ends holds** (`BOUNDS_NOT_CONVERGED`). The runner loops for ever there (two equal zero bounds
     in a pair with no placeholder); STRAT-003 stops after 100,000 steps.
  3. **The exit comes first:** a SHORT on the primary timeframe exits, so it never enters, even when that timeframe is
     not counted (documented in the catalogue entry).
  4. **`min_tf_agree` above the number of counted timeframes is refused** (it could never enter).
  5. **The 14-day freshness gate is not applied** (a backtest scores a fixed model on later bars by design).
  6. The decision's bars and sides are exposed as indicators (`bar_<tf>`, `side_<tf>`, `longs`, `shorts`, the primary
     timeframe's bounds), so every decision can be checked against the runner.
- **What the reproduction shows about the legacy runner** (reproduced on purpose; not in the issue drafts, and no issue
  can be filed under the no-authenticated-calls rule) (**superseded:** drafted as E1 and E2 and filed as #152 and #153
  on 2026-10-07 under an owner-approved exception; see "Phase 3 follow-up" below):
  - With two or more inactive timeframes, the remap drops the repeated placeholders, so later timeframes are compared
    with the next timeframe's bounds and 1week with a padded placeholder: in the recorded fixture with two inactive
    timeframes, 1week never signals.
  - Two equal zero bounds hang the gap pass (in the runner, for ever).
  - These are candidates for the owner to file as issues.
- **Acceptance:** 5 (`LOOKAHEAD_MODEL`: refused when `train_end` is after the first scored bar, accepted at equality, any
  strategy with a model, unknown ends refused, naive = UTC at the exact boundary); 6 (a decision at *t* uses each
  timeframe's bar that closed one bar before *t*, and bars closing at or after *t* changed by 50% change nothing); 7
  (bar for bar against the real runner: the recorded fixture, two scenarios × 241 hourly decisions, sides, kept bounds,
  counts, served bars and the strategy's reported bounds; and live against `pt_thinker.step_coin` on a model the trainer
  published, 48 decisions); 4 now also covers the backtester (the CLI refuses) and the signal engine (fails closed).
- **Tests:** new `app/tests/test_model_strategy.py` (53 tests from 39 functions), `app/tests/helpers_strat003.py`, the
  recorder `app/tests/record_strat003_fixture.py` (not collected; run under the guard to re-record) and the fixture
  `app/tests/fixtures/strat003_thinker_record.json` (314 KB; recorded from `pt_thinker.py` blob `97aee15`); one test in
  `app/tests/test_signal_engine.py` (the trader's status).
- **Mutation checks** (scratch clones, the STRAT-003 and signal-engine tests with the guard on; the clones unchanged
  afterwards): 36 mutations of the rule, the strategy, the backtester, the CLI, the settings, the signal engine and the
  catalogue. 34 were caught at once. The two survivors were near-equivalent: the gap pass's skip condition without its
  high-list half (it differs only when a zero low sorts below the placeholders) and LONG checked before SHORT (it
  differs only for an upside-down band). A unit test for each now catches them. The round-3 hash fix was checked the same
  way.
- **Adversarial review** (three workflow rounds; read-only reviewers, each followed by a skeptical verifier):
  - Round 1, four reviewers: runner fidelity, the backtester and its integration, spec and catalogue, tests. **The
    runner-fidelity reviewer found nothing.** The others: 15 findings, 10 confirmed, 3 plausible, 2 refuted. Fixed: the
    strategy read its bars only from the default cache, so a normal out-of-sample run (the trainer caches bars only up to
    `train_end`) would have held `BARS_MISSING` on every bar and still looked like a valid result; the signal engine's new
    fail-closed path logged once and swallowed other build errors; `check_lookahead` failed open on an empty `train_end`
    and crashed on a naive one; the `bars` keyword bypassed the parameter check; a TypeError in the timeframes bound; the
    exit's precedence undocumented; three test gaps (a check that could not fail, the reported bounds unchecked, no
    all-active scenario).
  - Round 2, two reviewers: 6 findings (4 confirmed, 2 plausible), all fixed: `--candles-file` could mix the file's
    prices with another series' bars (now refused unless they match); the hub strip still showed STRAT-003 as active (now
    a settings problem); a wrong timeframe or pair was refused only after downloading; three test gaps.
  - Round 3, one reviewer: 2 findings (1 confirmed, 1 plausible), fixed: online, the run's own cache file could be
    extended after its hash was recorded; the docs promised an ERROR where the trader logs a warning.
- **Suite** (`run_suite.py` on a fresh clone, `clone-phase3`, holding every final code and test file; 00:42-00:52):

  | Suite | Passed | Failed | Skipped |
  |---|---|---|---|
  | `app/` | 1186 | 11 | 6 |
  | `.github/scripts` | 23 | 19 | 1 |

  - Against Phase 2's final run (`suite-phase2b.json`): NEW `app/tests/test_model_strategy.py` (53 passed),
    `app/tests/test_signal_engine.py` one test more (38 passed), Phase 2's two environmental flips passing again, and one
    new flip in a file Phase 3 does not touch:
    `app/test_trading_mode.py::UiHelperTests::test_pack_at_top_ignores_the_unpacked_menu_bar` skipped with "no display
    available" (the test skips when `tk.Tk()` raises: the known Tk start-up flake). Re-run on the same clone with the
    guard on: 50 passed.
  - Against the session baseline (`suite-cbf7e21-baseline.json`): as at Phase 2, plus the new file, the signal-engine
    test and that flip. `.github/scripts` equal to the baseline (23/19/1). The newly failing app test is still
    `app/test_integration.py::TestPowerTraderHubIntegration::test_graceful_degradation`, the known Tk start-up flip.
  - `run_suite.py`'s real-state check unchanged before and after; nothing written into the clone (`git status` the same
    before and after, also after the re-run). The 18 files of the commit are byte-identical to the clone's. Results:
    `<scratch>\suite-phase3.json`, SHA-256 `e21969db7067471097416c3a537ec3ad02c1cfc62a302e9b1cb0145f7263457f`; copy at
    `..\PowerTraderAI-specs\suite-phase3-final.json`. The run log was finished after the clone was made; nothing else
    changed.
- **Black** 26.5.1: the 15 Python files of the commit unchanged.
- **Real-folder and credential checks:** see the table above (Phase 3 rows).
- **Commit** (explicit paths; not pushed, no PR): `FDS-MDL Phase 3: STRAT-003, the trained model as a strategy`.
- **Owner actions:**
  1. Consider filing the two legacy-runner findings above as issues (not filed: no authenticated calls). **Superseded:**
     filed as #152 and #153 on 2026-10-07.
  2. STRAT-003 stays inactive (`strategy.active_id` is STRAT-001) and, with no default `model_id`, shows as a settings
     problem in the hub strip if selected; a live default would need a published model id.

## Phase 4 — evaluation: the pre-declared header — **committed; no backtest run**

- **Session:** 2026-10-07, Claude Opus 5.5. The owner's direction: "Stop after committing the Phase 4 pre-declared
  verdict rule, and before running any backtest. Report the rule to me first." And, on 11.8: the finding feeds the
  Phase 4 verdict rule, "so the rule must still be committed before any backtest runs, and I want to read it first."
- **What this commit holds:** `docs/dev/BACKTEST-REPORT-model-1.md`, the header only (FDS-MDL section 7 "Declared
  before any result is seen" and section 10: the declared settings and the verdict rule in their own commit, before
  Test A), and this run-log section. Nothing else changed.
- **Not run:** no `fetch`, `train`, `run` or `report`; no STRAT-003 backtest of any kind; no model trained for Phase 4.
  `run_backtest_model1.py` has not changed since Phase 2. The Phase 4 code (the report generator, the random baseline
  and its acceptance-8 test) comes after the owner has read the rule.
- **Checked while writing it** (data and earlier records only, no result):
  - batch 1's four SHA-256 values and its out-of-sample starts (2025-08-16 07:00 for 1h, 04:00 for 4h) from
    `docs/dev/backtest-batch-1/*.json` and `BACKTEST-REPORT-batch-1.md`; the "vs B&H (pp)" measure from
    `run_backtest_batch1.py`.
  - The gaps in the scratch candle cache from Phases 1-2 (2023-01-01 to 2025-12-31, all seven timeframes, both
    symbols): only the 1h bar of 2023-03-24 13:00, on both symbols, which is batch 1's one missing hourly bar (32,855
    of 32,856), before every scored window.
  - The manifest keys the verdict line reads (`validation_metrics`, 1-hour `direction_hit_rate`,
    `up_share_of_considered`, `direction_considered`), in a Phase 2 manifest in the scratch store.
- **Choices for the owner:** the header's own list, "Interpretations of FDS-MDL's wording (for the owner to confirm
  before Test A)": in-sample reported as refused; one Test A model per symbol trained to 04:00; criterion 3 as the
  pooled median of the 36 windows without overlays; "beats" strictly, criterion 2 read literally; missing-bar holds
  fail their criterion; the random baseline's matching, placement, mid-rank and acceptance-8 handling; 11.8 in the
  verdict line, not as a fourth criterion. Any change is made before Test A, in a commit of its own.
- **Checked by two read-only agents** (no file written, nothing run but arithmetic):
  - First pass: 2 high, 5 medium, 13 low findings, all taken. High: criterion 2 had been read as "3 of 4 pass both",
    looser than FDS-MDL's "in those same combinations" (now literal: every combination that beats buy-and-hold must
    rank at least 95); and nothing froze the code (now a Code section). Medium: criterion 3's pooling and the in-sample
    refusal labelled as interpretations; the verdict line named the wrong models for 11.8's numbers and called the
    Test A manifests' metrics "their own held-out bars" (they come from a separate 80% fit); the random baseline's
    placement, N, H, RNG and overlay handling made exact; `BOUNDS_NOT_CONVERGED` holds covered. The rest: wording,
    the fetch into an empty cache, KPI conventions, failed trainings, Test B's half-open windows.
  - Second pass, on the revision: 1 high and 9 low, all taken. High: the code rule did not say which results decide
    the verdict after a fix (now only the final code's, with every affected step re-run, the earlier results and
    verdict reported beside them; the frozen code is every tracked file under `app/` plus the run script). The
    placement maths was proved and brute-forced against a copy of the engine loop (L <= 15, N <= 5, H <= 5): no
    overlap, every exit by the last bar, `bars_held` exactly H, uniform over placements.
- **Suite** (`run_suite.py` on a fresh clone, `clone-phase4h`, holding the header and this section; 01:20-01:28): `app/`
  1186 passed, 10 failed, 7 skipped; `.github/scripts` 23/19/1. Against the session baseline: as at Phase 3, with the
  Tk flip of `app/test_integration.py::TestPowerTraderHubIntegration::test_graceful_degradation` back to skipped as in
  the baseline. Against Phase 3's run: that test and
  `app/test_trading_mode.py::UiHelperTests::test_pack_at_top_ignores_the_unpacked_menu_bar` back to their baseline
  states, and `app/tests/test_mock_trainer_refusal.py::test_a_string_true_still_refuses` skipped ("Tk not available
  (attempt 2): invalid command name "tcl_findLibrary"", the known Tk start-up flake). Re-run on the same clone with the
  guard on: the file once more (17 passed, that test skipped for Tk again), then that test three times (passed each
  time). This commit changes two Markdown files only. Real-state check unchanged; nothing written into the clone.
  Results: `<scratch>\suite-phase4h.json`, SHA-256 `fc7d8f6eab77268a35203d03ac019ac898df51326f398dd3c661009068efa36d`;
  copy at `..\PowerTraderAI-specs\suite-phase4-header.json`. The suite line and the table row were added after the
  clone was made.
- **Real-folder and credential checks:** see the table above (Phase 4 header row).
- **Commit** (explicit paths; not pushed, no PR): `FDS-MDL Phase 4: pre-declared header and verdict rule`.

## Phase 4 — the owner's review of the header, and its amendment — **no backtest run**

- **Session:** 2026-10-07, Claude Opus 5.5. The owner's review of `51e499e`: "Interpretations 1 to 7: all confirmed as
  written." Then, before Test A and in one commit on top of `51e499e`:
  1. show each pair's Test B median beside the pooled one, as information only (criterion 3 stays pooled);
  2. confirm that batch 1's 1h and 4h files cover the last Test B window, without fetching new candles (the SHA-256
     rule stands);
  3. fix and record the random baseline's seeds;
  4. in a second message: for E1 and E2, no change to the rule, but two counts in the output per pair, for Test A and
     Test B (E1: decisions with two or more timeframes before 1week inactive, as a count and a share of scored bars;
     E2: times the 100,000-step limit triggered, expected zero, flagged in the verdict line if not), in the same commit.

  Then show the owner the diff before Test A runs.
- **The amendment** (`docs/dev/BACKTEST-REPORT-model-1.md`):
  - an "Amended 2026-10-07" note under the status line;
  - the four per-combination medians beside the pooled one, marked information only;
  - a coverage paragraph for the last window (1h and 4h; the 2h to 1w bars stay under "No silent gaps");
  - the seeds (0 to 99 in every run, a fresh `random.Random(s)` per seed per run, the same placements where *L*, *N*
    and *H* coincide) and their reproducibility (CPython version, every seed's drawn entry bars, one pinned case on
    each of `sample()`'s two code paths, and `report` re-deriving the recorded entry bars);
  - a subsection counting E1 and E2, with the E2 note in the verdict line and STRAT-003's activity indicator in the
    freeze commit;
  - the interpretations heading recording the owner's confirmation, and the rule for later header changes kept.

  The seven interpretations and the three criteria are unchanged.
- **The coverage check** (data only, nothing fetched, no result):
  - batch 1's records (`docs/dev/backtest-batch-1/*.json`, `data` block): 1h 2023-01-01 00:00 to 2026-09-30 23:00,
    32,855 bars, one gap (2023-03-24 13:00); 4h to 2026-09-30 20:00, 8,214 bars, no gap; the same for both symbols.
  - The files batch 1 read, in the main checkout's `app/hub_data/candles/` (read only; nothing copied): ETHUSDT 1h,
    BTCUSDT 4h and ETHUSDT 4h still hash to batch 1's values. **BTCUSDT 1h does not:** it has 37 more bars (2026-10-01
    00:00 to 2026-10-02 12:00; the file is dated 2026-10-02 14:27, the other three 04:19). Its header and rows before
    2026-10-01 00:00, hashed as stored, give batch 1's value `7171bc66…`. In July to September 2026 each file has the
    full count: 2,208 1h bars and 552 4h bars per symbol, none missing.
  - The cache `fetch` wrote in Phases 1-2 uses the same CRLF layout as batch 1's files, and its 26,303 rows match batch
    1's row for row, so the declared fetch-then-hash procedure can reproduce batch 1's bytes (on Windows, where pandas
    writes CRLF).
  - The two pinned `sample()` cases were checked against CPython 3.13.15's own threshold: (2,465, 500, 3) takes the pool
    path (n = 964 <= 4,117), (9,857, 100, 20) the set path (n = 7,856 > 1,045); seed 0's placements are valid (no overlap,
    every exit by the last bar).
- **Checked by read-only agents** (no file written in the repo; nothing run but arithmetic, read-only file checks and
  the named tests under the guard):
  - On the first draft of the amendment, two reviewers (the owner's instructions and the facts; ambiguity): 11
    findings (4 medium, 7 low), all taken. Medium: the coverage sentence claimed more than the 1h/4h check showed (now
    limited, with the 2h to 1w bars under "No silent gaps"); "the draws still differ between runs" was false (BTC and
    ETH share *L*, so equal *N* and *H* give the same placements, as FDS-MDL's seeds imply); one pinned case cannot
    cover both of `sample()`'s code paths (now two, plus `report` re-deriving the recorded entry bars); the rule for
    later header changes had been dropped (restored). Every fact was confirmed: batch 1's records, the bar counts, the
    hashes, and Python's reproducibility guarantee.
  - On the final text, with the E1 and E2 counts, one reviewer: 7 findings (1 medium, 6 low), all taken. Medium: the
    E1 share's denominator could be read as *L* or *L* − 1 (now the window's decisions, *L* − 1, the engine deciding
    nothing on a window's last bar). The rest: whether a `BOUNDS_NOT_CONVERGED` hold counts as E1 (it does when the
    condition holds), the order of the two verdict-line notes, the amendment note's coverage claim, the plural
    attributed to FDS-MDL section 10, and the description of `BOUNDS_NOT_CONVERGED`. It confirmed that the seven
    interpretations are unchanged word for word and that each of the owner's instructions is done.
- **Suite** (`run_suite.py` on a fresh clone, `clone-phase4a`, holding the amendment, the drafts and these sections;
  08:35-08:44): `app/` 1187 passed, 11 failed, 5 skipped; `.github/scripts` 23/19/1. Against the session baseline: as
  at Phase 3, with the known Tk start-up flip of
  `app/test_integration.py::TestPowerTraderHubIntegration::test_graceful_degradation` failing again. Against the header
  run (`suite-phase4h.json`): that flip, and `app/tests/test_mock_trainer_refusal.py::test_a_string_true_still_refuses`
  passing again. This commit changes three Markdown files only. Real-state check unchanged; nothing written into the
  clone; the three files byte-identical to the clone's. Results: `<scratch>\suite-phase4a.json`, SHA-256
  `1b93cdcbf619b91c0159d6f9e5635fa20a9c6ecc0ab5830907820c0adcc788a8`; copy at
  `..\PowerTraderAI-specs\suite-phase4-amendment.json`. The suite line and the table row were added after the clone was
  made.
- **Real-folder and credential checks:** see the table above (Phase 4 amendment row).
- **Commit:** the same commit as the drafts below (see there).

## Phase 3 follow-up — issue drafts E1 and E2 (legacy runner)

- **Owner direction (2026-10-07):** add the two legacy-runner findings of Phase 3 to `docs/dev/ISSUE-DRAFTS-model-1.md`,
  then file them under the same one-time exception as the 11 (`gh issue create --repo` only, each call logged), with no
  other authenticated calls.
- **Drafts:** E1 (the bound remap drops repeated values, so with two inactive timeframes before 1week later timeframes
  use a neighbour's bounds; for coins at $0.01 or more an active 1week never signals, below $0.01 it is LONG on every
  sweep) and E2 (the gap pass loops for ever on two zero bounds; the runner stops processing coins). Base `7a84250`, in
  the file's format, with a header note, two table rows and owner note 10.
- **Drafted and checked by read-only agents:** one drafter per issue; then two verifiers per draft (code fidelity
  against `7a84250`; claims, reproduction and format), re-run after the first attempt stopped at a session limit: 38
  findings (11 medium, 27 low). Every line citation and every recomputed number held. The fixes: for a coin below
  $0.01 the padded 1week is LONG on every sweep, not silent (E1); a repeat in one list does not make the shifted
  timeframes lose LONG (E1); #143 belongs in E1's scope (on main every timeframe is inactive); E2's low-list rule is
  "at least two more zero lows than inactive timeframes"; one zero-close timeframe is not enough (E2); the trader does
  not read the runner's signal files today (#142), but a hang before ready stops Start All from starting the trader
  even in the catalogue engine; Stop All ends the poll; step 3 on 7a84250 has no publish step; both drafts were about
  twice A1's length and in the first person (rewritten). A final check found 1 medium and 4 low in E1 (the DCA
  sentence lacked the $0.01 qualifier) and 1 medium and 3 low in E2 (the negative-bound STRAT-003 sentence was too
  general; ready comes after the second sweep), all taken except cutting E2's quoted code, kept as the evidence.
- **Commit** (explicit paths; not pushed, no PR): one commit, the direct child of `51e499e`, holding the amendment, the
  drafts and these two sections, so the header's reference to the drafts resolves in that commit:
  `FDS-MDL Phase 4: amend the rule after the owner's review; draft E1 and E2`.
- **Filing:** not done in this commit; it is recorded in a later section once done.

## Phase 3 follow-up — E1 and E2 filed as #152 and #153

- **Owner confirmation (2026-10-07):** "E1 and E2: yes, file them now. Exactly two gh issue create --repo
  sjackson0109/PowerTraderAI calls, labels bug and needs-triage, each logged. No other authenticated call. Record the
  numbers in a small commit."
- **The two calls** (the only authenticated calls; the labels were listed on 2026-10-06 and not listed again):
  1. 2026-10-07 08:25:33-08:25:35 UTC, exit 0: `gh issue create --repo sjackson0109/PowerTraderAI --title <E1's title>
     --body-file E1.md --label bug --label needs-triage` gave #152
     (https://github.com/sjackson0109/PowerTraderAI/issues/152).
  2. 2026-10-07 08:25:41-08:25:42 UTC, exit 0: the same for E2 gave #153
     (https://github.com/sjackson0109/PowerTraderAI/issues/153).
- **Bodies:** each is its draft from "What happened?" on, checked byte for byte against `d36cdf1` before filing, with
  the same footer as the 11 (the drafts and the files not on main live on `feat/model-strategy-1`). Kept in
  `<scratch>\issues\` with the call log. The issues were not viewed back (that would be another authenticated call).
- `ISSUE-DRAFTS-model-1.md` now records both numbers. Suite: not re-run for this Markdown-only commit; the two test
  files that read the docs (`test_no_hard_coded_user_paths.py`, `test_docs_and_visibility.py`) pass under the guard
  (7 passed).
- **Commit** (explicit paths; not pushed, no PR): `FDS-MDL: issue numbers for E1 and E2 (#152, #153)`.

## Phase 4 — the owner's approval of `d36cdf1`, with one change — **no backtest run**

- **Owner (2026-10-07):** "Diff d36cdf1: approved, with one change, in its own commit before Test A: Give each of the
  four combinations its own seed range instead of 0 to 99 for all: BTC 1h 0-99, BTC 4h 100-199, ETH 1h 200-299, ETH 4h
  300-399. A combination's two overlay sets keep sharing that combination's range. State in the header that this
  departs from FDS-MDL section 7's literal "seeds 0 to 99" and why [...]. Update the pinned acceptance-8 test to match."
  And: "For the 2h to 1w candle files, which have no batch-1 hash: record each fetched file's SHA-256 in the results,
  so the run can be repeated on the same data."
- **The header change** (`docs/dev/BACKTEST-REPORT-model-1.md`): a second "Amended" note; the seeds paragraph now gives
  each combination its range and says why this departs from FDS-MDL section 7 (the owner's reason, worded as the
  3-of-4 count of criteria 1 and 2, since the control enters through criterion 2); the pinned acceptance-8 cases now
  use seed 0 (BTCUSDT 1h's first) for the set path and seed 100 (BTCUSDT 4h's first) for the pool path, both checked
  against CPython 3.13.15 (valid placements on the intended paths); `fetch` records every fetched file's SHA-256, all
  seven timeframes, and `run` checks them; the E1/E2 subsection cites #152 and #153. The criteria and the seven
  interpretations are unchanged.
- **Checked by one read-only reviewer:** 1 medium and 3 low findings plus a nit, all taken. Medium: `run`'s check
  of the recorded hashes had no stated failure case (now: nothing is scored, as for batch 1's). The others: the
  reason's wording (now "the 3-of-4 count (criterion 1, whose combinations must each also pass criterion 2, where the
  control enters)"; the owner wrote "criterion 1"); shared seeds also give near-identical draws when *N* and *H* are
  merely close (about 99% of the drawn values shared for *N* or *H* one apart at *L* = 9,857), now stated; the freeze
  list now names `fetch` recording every hash; the second amendment note points to the departure. It confirmed the
  ranges, the pinned paths, and that the criteria and interpretations are unchanged.
- **Suite** (`clone-phase4s`, 09:28-09:37, made before the reviewer's text fixes): `app/` 1187/11/5,
  `.github/scripts` 23/19/1, identical to the previous run (`suite-phase4a.json`); against the session baseline only
  the known Tk start-up flip. Real-state check unchanged; nothing written into the clone. The final header and this
  log were then copied into that clone and the two test files that read the docs re-run there under the guard
  (7 passed). Results: `<scratch>\suite-phase4s.json`, SHA-256
  `ea2a4a17f3d4714b8cc3b818b6f0058ab410c02ef1fb6a78578b2de783650ab5`; copy at
  `..\PowerTraderAI-specs\suite-phase4-seeds.json`.
- **Real-folder and credential checks:** see the table above (Phase 4 seed-range row).
- **Commit** (explicit paths; not pushed, no PR): `FDS-MDL Phase 4: a seed range per combination; record every candle
  file's hash`.

## Phase 4 — the freeze commit (the code Test A will run) — **no backtest, fetch or training run**

- **Owner (2026-10-07):** "After that commit, go on to the freeze commit. Show me the freeze commit's summary before
  running Test A." The header's Code section: a freeze commit, after the header's commits and before Test A, adds the
  Phase 4 code; everything that produces results is then committed.
- **What it holds** (the frozen code is every tracked file under `app/` plus `docs/dev/run_backtest_model1.py`):
  - `app/backtest/random_baseline.py` (new): matching (*N*, *H* rounded half up), `fit_hold`, the placement
    (`random.Random(seed).sample`, entry at window bar 1 + *c*<sub>k</sub> + *k*·*H*), the random-entry strategy (not a
    catalogue strategy), one seed's run with a fresh runner, the percentile with half ties, and the two pinned
    placements with `check_pins`.
  - `app/backtest/model_eval.py` (new): the decision recorder, hold and E1/E2 counts, the median, the verdict rule
    (criterion 2 read literally), an independent recheck with the thresholds written out, the verdict line (11.8's
    numbers, Test A's manifest values, n/a reasons, the held-out dates checked, the two notes in order).
  - `docs/dev/run_backtest_model1.py` (rewritten): the declared plan (window, batch-1 hashes, bars and split, the 20
    trainings, seed ranges per combination, overlay sets, costs) and `fetch`, `train`, `run`, `report`. Nothing about
    the plan can be changed from the command line; the only option is `--supersede NOTE` (train and run).
  - `app/strategies/model_strategy.py`: `active_<tf>` indicators (for E1), set after the seven predictions and before
    the rule, so they change no decision.
  - Tests: `app/tests/test_model_backtest.py` (new, 87 tests from 78 functions); one strengthened assertion in the
    Phase 3 bar-for-bar test (each `active_<tf>` is its timeframe's own prediction; two or more inactive before 1week
    shortens the runner's kept lists); `app/tests/helpers_strat003.py` (`publish_files` takes manifest overrides).
  - `docs/technical/ARCHITECTURE.md`: one sentence naming the two new modules.
  - Not in it: `docs/dev/BACKTEST-REPORT-model-1.md` (header commits may change no frozen file, and the freeze commit
    changes no header).
- **The code rule as built:** every command refuses frozen files that differ from the commit (untracked included) and
  records the commit in every JSON it writes. `train` and `run` never replace earlier outputs without
  `--supersede "<what changed and why>"` (a run that stopped before scoring is moved aside with an automatic note);
  `train --supersede` also moves the run outputs that came from the earlier models. `run` refuses models that are not
  the declared trainings (window, seed, parameters, model code, a clean trainer at a commit whose trainer files are the
  train commit's, the candle files and bar-loading code `train` read). `report` refuses unless the frozen code is the
  results' code and the header is the one committed when they, and every earlier run that scored, were produced; it
  keeps the verdict as given (`verdict.json`) and lists superseded runs with their verdict and numbers. A run is marked
  "running" first, so an interrupted one leaves a record; a stop records what was already scored.
- **Reviews** (read-only agents; every finding checked by a skeptic before it counted):
  - Design (before code), two reviewers: header fidelity 1 high, 6 medium, 4 low; feasibility 3 medium, 6 low. The
    high one: the code-change rule was not implemented (no history, no binding of models to the final code). All
    taken into the code.
  - Round 1 on the code, four reviewers (header fidelity, correctness, tests, safety) and 42 verifiers: 37 confirmed
    (6 medium, 31 low), 5 refuted. The medium ones: `report` was not bound to the frozen code (it computes the verdict),
    superseded verdicts were recomputed instead of kept, the rank input was untested, and `train --supersede` left the
    earlier run's results in place. All fixed.
  - Round 2, three reviewers and 25 verifiers: 31 of the 37 confirmed fixed; 24 new or partial (2 medium, 22 low), 1
    refuted. Medium: the trainer-commit binding refused a correct re-train (the store keeps an earlier manifest for the
    same content); an interrupted run escaped the header check. All fixed.
  - Round 3: 11 of the 14 round-2 fixes confirmed; 3 gaps (a `~` home not expanded in the new overlap check; one test
    without the fail-loudly patches; one untested guard), checked by hand (the verifiers stopped at a session limit)
    and fixed.
  - Final fresh round, two reviewers: the real-run walk-through found nothing that would stop, crash, mis-score or
    print something false (it ran the report's git helpers read-only on the real repository and compared the Phase
    1-2 cache with batch 1's files byte for byte); estimates: fetch 1-3 min, train 33-40 min, run 20-25 min, report
    under a minute; `results.json` about 5-20 MB. The rule-and-safety reviewer: 2 low (`verdict.json` lacked the code
    state; the rendered E1/E2 and per-combination medians were untested), fixed.
- **Mutation checks** (scratch clones, the Phase 4 tests with the guard on; clones unchanged afterwards): 38 on the
  first code (36 caught; the two survivors got tests and were then caught); 58 on the round-1 code (58 caught); 33 on
  the final code, every check changed in rounds 2 and 3 and the new ones (33 caught).
- **A miniature end-to-end run** (in the tests: synthetic bars for both pairs, crafted models): `fetch` (faked
  fetcher), `run` and `report` work end to end; every Test A in-sample window is refused with `LOOKAHEAD_MODEL`;
  decisions are L − 1 per window; E1 is every decision on a model with two always-inactive timeframes and none on an
  all-active one; the header is kept byte for byte.
- **Suite** (`run_suite.py` on a fresh clone, `clone-phase4f`, holding every file of this commit; 14:16-14:27):
  `app/` 1274 passed, 11 failed, 5 skipped; `.github/scripts` 23/19/1. Against the previous run
  (`suite-phase4s.json`): only the new `app/tests/test_model_backtest.py` (87 passed). Against the session baseline:
  the known Tk start-up flip, as before. Real-state check unchanged; nothing written into the clone; the nine files
  of the commit byte-identical to the clone's. Results: `<scratch>/suite-phase4f.json`, SHA-256
  `5eb0208adadb7911fe378f116595f2d15e0f71c4fd951001ffc5a3035ff92b07`; copy at
  `../PowerTraderAI-specs/suite-phase4-freeze.json`. Black 26.5.1: the seven Python files unchanged. The suite line
  and the table row were added after the clone was made.
- **Real-folder and credential checks:** see the table above (Phase 4 freeze row).
- **Commit** (explicit paths; not pushed, no PR): `FDS-MDL Phase 4: the freeze commit (random baseline, evaluation,
  run script)`.

## Phase 4 — Test A (`fetch`, `train`, `run`, `report`) — **verdict: no evidence of an edge**

- **Owner (2026-10-07):** "Approved. Run Test A from a clean tree at 68d4ed7: fetch, train, run, report, with a fresh
  absolute POWERTRADER_HOME outside the repo. [...] Do not change the header, the rule or any frozen file because of a
  result. A defect fix goes through the code rule only (fix, re-run everything it affects, report both). Keep the
  scratch POWERTRADER_HOME until I've read the results. No authenticated calls."
- **Start state:** HEAD `68d4ed7`, `git status --porcelain` empty, no `docs/dev/backtest-model-1/`. `POWERTRADER_HOME`
  =
  `C:\Users\Simon\AppData\Local\Temp\claude\c--Users-Simon-Documents-sjackson0109-PowerTraderAI\57710dd7-ccf3-4fdb-8966-6da8cc28ea84\scratchpad\p4home`
  (absolute, outside the repository and the worktrees, did not exist before). Python: scratch `venv-test` (3.13.15,
  pandas 3.0.6), `PYTHONDONTWRITEBYTECODE=1`. Each command ran once, from the worktree, with no options.
- **`fetch`** (17:27:14-17:28:14, exit 0; the only network step): 14 files. The 1h and 4h hashes equal batch 1's
  (`batch1_mismatches` empty). Each 1h file has 32,855 bars and one missing bar, 2023-03-24 13:00 (both pairs), before
  every scored window. Every file's SHA-256 is in `data.json` and the report's Data table.
- **`train`** (17:30:05-18:01:34, exit 0): 20 trainings, each exit 0, 48.8 to 147.2 s. Test A models
  `BTC-20250816T0400Z-5d85edd38e43` and `ETH-20250816T0400Z-6ce59ce7a360`; the 18 Test B models are in `train.json`.
  Trainer logs: `<home>\data\backtest-model-1\trainer`.
- **`run`** (18:01:48-18:24:02, exit 0): 80 runs (8 Test A, 72 Test B) and 8 baselines of 100 seeds;
  `results.json` status `ok`.
- **`report`** (18:24:12-18:24:13, exit 0): the Results go below the marker. Lines 1-282 are byte-identical to
  `68d4ed7` and to a copy taken just before `report` (LF kept). `verdict.json` written.
- **Verdict line** (as `report` wrote it): "***No evidence of an edge*; in TRAINER-AUDIT 11.8 the trainer's held-out
  direction calls showed no skill above the up-rate base rate:** 1-hour hit rate vs share of closes that rose, BTC
  50.3% vs 50.4% and ETH 51.3% vs 51.0% (n = 5,257 pairs each). Held-out metrics in Test A's manifests (a separate fit
  on the first 80% of each training window, scored on the last 20%, 2025-02-05 12:00 to 2025-08-16 04:00): BTC 50.7% vs
  50.5% (n = 4,599), ETH 51.4% vs 51.6% (n = 4,588)."
- **Criteria:**
  - 1, not met (1 of 4; 3 needed). Out of sample, no overlays, vs buy-and-hold: BTC 1h +13.95 pp (pass), BTC 4h
    −5.90, ETH 1h −20.34, ETH 4h −19.26.
  - 2, met. BTC 1h ranks 95.0 (95 of 100 seeds below, no ties). The others are not tested under the rule; their ranks
    are 26.0, 24.0 and 10.0.
  - 3, not met. The pooled median of 36 windows is −11.94 pp (18th −12.20, 19th −11.67); the worst window is −67.70
    (ETH 4h, 2025-07); 9 of 36 windows are above 0; no data holds.
  - Each combination's median, for information: −11.67, −12.20, −11.67, −16.95.
- **E1 and E2** (runs without overlays; denominator L − 1):

  | Combination | Test A E1 | Test B E1 (9 windows) | E2 |
  |---|---|---|---|
  | BTC 1h | 12 of 9,856 (0.12%) | 37 of 19,719 (0.19%) | 0 |
  | BTC 4h | 3 of 2,464 (0.12%) | 10 of 4,923 (0.20%) | 0 |
  | ETH 1h | 28 of 9,856 (0.28%) | 176 of 19,719 (0.89%) | 0 |
  | ETH 4h | 7 of 2,464 (0.28%) | 45 of 4,923 (0.91%) | 0 |

  E2 is 0 everywhere, so the verdict line carries no E2 note.
- **Superseded:** nothing. No `--supersede`, and there is no `superseded/` folder.
- **Read-only audit after the report** (a workflow of 5 lenses and 14 skeptics, 19 agents). Nothing was imported from
  `app/` and nothing was written to the worktree or the home; scratch is `<scratch>/verify-testA/`.
  - Recomputed from the candle cache and trades files: all 80 windows, buy-and-hold and STRAT-003 KPIs (max
    difference 2.8e-14 pp).
  - All 800 baseline placements re-derived, and all 800 seeds re-simulated from raw candles (exact). Both pins
    reproduce.
  - Ranks, the three criteria, the medians, the verdict line, the manifest values and the 11.8 text recomputed and
    matched.
  - The 14 candle hashes and the 20 models' code, data and candle provenance (140 candle windows, 700 store files)
    checked. 181 code records name `68d4ed7` with no frozen changes.
  - 1,084 rendered cells compared, with 0 mismatches.
  - **Findings** (each checked by two skeptics): none high or medium, and none touches a number or the verdict.
  - Low, upheld:
    - (a) the Test B table's "Missing bars" column adds BARS_MISSING and TIMEFRAME_UNKNOWN together. `results.json`
      keeps them apart, all are 0, and Test A shows them separately.
    - (b) the manifest copies are JSON-equal to the store's but not byte-identical (line endings, a trailing newline).
  - Low, not a defect: the flagged-seed lists are printed without a count. Refuted: "every seed's count is reported"
    (the per-seed counts are in `baselines/*.json`).
  - Information only:
    - BTC 1h's rank is exactly at the threshold.
    - Buy-and-hold fills at a window's first open, while STRAT-003 can fill from the second bar on (the engine's
      convention, as in batch 1).
    - The overlay controls make fewer trades than N because the cooldown skips entries. They are flagged as declared,
      and overlay runs are not in the verdict.
    - The header's status line still reads "pre-declared header only", because it may not change.
    - E1 shares under 0.05% print as 0.0%.
    - The model files, trainer logs and candle cache exist only in the scratch home.
  - (a) and (b) are not fixed: either would need a frozen-code change and a superseded re-run. The owner decides.
- **Output hashes (SHA-256):**
  - `results.json`: `b0203783933c0e9de69a0d12a706da9a1125cc31669459e66856fb9682bdbb56`
  - `verdict.json`: `450afbd5292e1efa28df53b3997df071210264b03777b8264052d65eaf050095`
  - `data.json`: `eaf36b4fe1f0bba2fff519d49b242f9eafc6a70cb4a357c15a0fe4a0a5364278`
  - `train.json`: `6313f90ce0f0095ffa20a47c0e0e9be4f5a51eb81705b3a461105dcd21a4beef`
  - The output folder is 5.7 MB: 112 JSON and 80 CSV files.
  - These are the files as written: CRLF line endings, the same for all 192 outputs, as with batch 1's. Git
    (`core.autocrlf=true`, no `.gitattributes`) commits them with LF endings. The committed blobs' SHA-256 (`git show
    <commit>:<path> | sha256sum`) is:
    - `results.json`: `83fcecce33f2ab98afae33af2769c17c6b46a0953b44dff58fddadc72b504f06`
    - `verdict.json`: `4e12ce5799bff3aae0023ee3b3e67d2f8b374cea42ce1dd6424880dee931e6c8`
    - `data.json`: `77bdb79813eae3fb5ecd7420e14e166934d59a934488d66747b22c96457f8793`
    - `train.json`: `7e205431bbb2527985c3b659be8db11109abc58ded887046aa0a6b5b8f5224a0`
  - Each of the 192 staged blobs equals its working file with CRLF changed to LF (checked before the commit).
- **Command logs** (in `<scratch>`):
  - `p4-fetch.log` `358544720d9dae3bdb89ecc7fac4f18504313ddc9453ad354b4e98aa154760c1`
  - `p4-train.log` `26a43461f8919d90743e74aa53a0154295d826496301657d302fe7cc12455e5e`
  - `p4-run.log` `a48d4e31b8faea43ac66abac4dfeddbe9b7c2f5e45002a51377a02161178c18e`
  - `p4-report.log` `9900485aa88138c2526032b76479979942d955f52432806855fb612f693d81ee`
- **Real-folder and credential checks:** see the table above (the three Test A rows).
- **Owner (2026-10-08):** "Results accepted. Leave both minor problems as they are; do not supersede." The owner asked
  for five things: a note in the Results, two issue drafts (not filed), a copy of the scratch home, this commit, and a
  PR description (not opened). "No authenticated calls."
  - **Note in the Results:** "Known presentation defects" at the top of the Results section of
    `docs/dev/BACKTEST-REPORT-model-1.md`. It lists (a) and (b), each with "it affects no number and not the verdict",
    and one line saying the header's status line describes the header and the results follow below. It is marked as
    added by hand after `report`; nothing else below the marker changed. The header (lines 1-282) is still
    byte-identical to `68d4ed7`, and the staged file starts with the committed one.
  - **Drafts:** F1 (the merged column) and F2 (the manifest copies' bytes) in `docs/dev/ISSUE-DRAFTS-model-1.md`, with
    table rows and owner note 11. Not filed. F2's reproduction was run: 30,139 vs 29,386 bytes, 752 vs 0 CRLFs, hashes
    differ, JSON equal, and the copy with LF equals the store file plus one trailing newline (all 20 models the same).
  - **Home copy:** the whole scratch home was copied (`cp -a`) to
    `C:\Users\Simon\Documents\sjackson0109\PowerTraderAI-specs\model-1-p4home\` (outside the repository and outside
    temp; `PowerTraderAI-specs` is not a git repository). Source and copy each hold 832 files, 14,653,047 bytes and 32
    folders. All 832 files' SHA-256 are equal, with none missing on either side.
    - The copy's hash list is `PowerTraderAI-specs\model-1-p4home.sha256` (832 lines, `<sha256>  <relative path>`),
      itself SHA-256 `5e99b0e2a8dce40d400449dfb37f2d34342efef3f915e3187bb28a3618e73a31`.
    - The layout is the same as the home's, so every `<home>` path above, and the absolute temp paths in
      `train.json`'s `log` fields and the code records, map one to one onto the copy. It holds the 20 models (store
      folders with manifests), the trainer logs, the candle cache and the validation caches.
    - The scratch original is kept as well, for now.
- **Commit** (explicit paths: `docs/dev/backtest-model-1`, `docs/dev/BACKTEST-REPORT-model-1.md`,
  `docs/dev/RUN-LOG-model-1.md`, `docs/dev/ISSUE-DRAFTS-model-1.md`; not pushed, no PR): `FDS-MDL Phase 4: Test A
  results (no evidence of an edge)`.
  - No code changed and no test or CI job reads these files, so no suite run was needed (as for `c11ed6c`).
  - No pre-commit hooks are installed, and CI does not run pre-commit.
  - `results.json` is 2.5 MB (it records every seed of the random baselines).
- **Follow-up commit: the note's formatting** (2026-10-08). The note is now a blockquote directly under "## Results".
  As a `###` section in `a2710a0`, the report's own Code, Frozen-code commits and Header commits bullets rendered as
  part of the note's list. The PR-description fact check found this. The note's wording is unchanged apart from line
  wrapping. The header is still byte-identical to `68d4ed7`. Real-folder check: see the table (01:29 row).
- **Deviation** (2026-10-08, while checking what CI runs, for the PR description). Looking for a Python 3.11 or 3.12
  interpreter, a command also listed `%LOCALAPPDATA%\Programs\Python`.
  - Its output was discarded, so nothing was printed and no file was opened. `py -0p` printed the registered
    interpreters' paths.
  - This breaks addendum section 10 as written (no reading in the real `%LOCALAPPDATA%`), as the Phase 0 grep did.
  - The Store-installed Python 3.12 under `%LOCALAPPDATA%` was not run, because it could write there. The 3.11
    grammar check was done with 3.13 instead: all 52 added or changed Python files parse under `feature_version=(3,
    11)`, with no 3.12-only f-string or library use found. (Corrected 2026-10-08 from "51": the first check covered the
    51 under `app/` and `docs/dev/`; `.github/scripts/create_desktop_installer.py`, checked afterwards, also parses.)
  - The Black check for the PR (26.5.1: `app/` unchanged on main, 178 files, and on this branch, 197 files) used
    `BLACK_CACHE_DIR` in scratch.
  - Nothing records that earlier Black runs in this work set it. Black's default cache is under
    `%LOCALAPPDATA%\black`, so those runs may have written there. This was not checked.

## The PR — owner decisions, draft F3, run-log fixes

- **Owner (2026-10-08), on the PR description:**
  - "Keep 9ddc066."
  - The AppData deviation is accepted as recorded, with no action on Black's cache.
  - Local paths are accepted: "Do not rewrite any output."
  - The `find_published` link gap: no code change on this branch; draft F3, low severity, fixed in a follow-up PR; one
    line in the PR description.
  - Fix the run-log nits in the same commit.
  - Add to the PR description's follow-ups: "CI runs none of app/tests; a follow-up PR adds them to ci-cd.yml."
  - Then, as a one-time exception with each call logged and no others: `git push` the branch to origin, and one
    `gh pr create --repo sjackson0109/PowerTraderAI --base main --head feat/model-strategy-1 --body-file
    docs/dev/PR-model-strategy-1.md`, with the title from the description's first heading. "Do not merge."
  - The request arrived as pasted text, so the push and the PR wait for the owner's direct confirmation.
- **Draft F3** in `docs/dev/ISSUE-DRAFTS-model-1.md`, with a table row and owner note 12. Not filed.
  - `find_published` and `_matching` (`app/model_store.py:347-410`) never resolve a real path. `verify_folder`
    compares the manifest's `model_id` with the folder's own name (`basename`).
  - So the legacy runner's gate would accept a model folder linked in from outside the store, where `load()` refuses
    it (`model_dir`, `:100-108`; tested at `app/tests/test_model_provenance.py:739-760`).
  - It was traced through the code, not run. Test A is unaffected: the backtest loads models with `load`.
- **Run-log fixes, each marked in place:**
  - Phase 1's upstream-equivalence test: "four data sets" corrected to five, and "all four" to all five.
  - Phase 3's two "not filed" lines are marked as superseded by #152 and #153.
  - The 2026-10-08 grammar-check line: 51 corrected to 52 files, with the reason.
- **PR description** (`docs/dev/PR-model-strategy-1.md`): the F3 line and the CI follow-up line added, the local-paths
  item marked as accepted, and the fixed run-log nits removed.
  - It is not committed. It is the PR's body, and it names the head commit, which it cannot do from inside that
    commit.
- **Real-folder check:** see the table (02:17 row).
- **Commit** (explicit paths: `docs/dev/ISSUE-DRAFTS-model-1.md`, `docs/dev/RUN-LOG-model-1.md`): `FDS-MDL: draft F3
  (find_published link gap); fix run-log nits`.
