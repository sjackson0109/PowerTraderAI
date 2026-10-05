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
