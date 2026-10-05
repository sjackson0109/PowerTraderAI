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

## Phase 0 — trainer audit

In progress.
