# FDS-MDL-A — Addendum to FDS-MDL after FDS-108a (v3)

| Field | Value |
|---|---|
| Applies to | `FDS-MDL-trained-model-strategy.md` (STRAT-003, honest train/test split) |
| Branch | `feat/model-strategy-1` |
| Run log | `docs/dev/RUN-LOG-model-1.md` (unchanged) |
| Models | Opus 5.5 high for Phases 0–1; Sonnet 5.5 high for Phases 2–4 (unchanged) |
| Version | v3: corrects v2 after a second review against `7832240` |

---

## 1. Purpose and precedence

FDS-MDL was written before FDS-108a moved runtime state out of the program directory and changed how the trainer is launched. FDS-MDL itself is **not edited**. This addendum reconciles it with the merged code.

**Read FDS-MDL first, then this addendum.** Where they conflict, this addendum wins. Everything FDS-MDL says that this addendum doesn't mention stands unchanged.

## 2. Branch base and spec files

Do these in order: check the base, cut the branch, then commit the spec files.

**Base:**
- **Preferred:** cut `feat/model-strategy-1` from `main` after these PRs have merged with merge commits: `feat/strategy-batch-1`, `fix/coinbase-connector` and `feat/user-data-separation` (which brings in `chore/untrack-trading-config`).
- **Check before starting:** `git log --merges --oneline -n 10 main` shows those merges, and `app/pt_paths.py` and `app/pt_secrets.py` exist on `main`.
- **Fallback, if they haven't merged:** cut from `feat/user-data-separation` at `7832240`. Record the base and the reason in the run log.
- **This replaces FDS-MDL's fallback** (cutting from `feat/strategy-batch-1`), which would miss the paths and secrets modules.

**Then cut** `feat/model-strategy-1` from the chosen base.

**Spec files.** As the first commit on the new branch, add these to `docs/dev/specs/`, unchanged:
- `FDS-MDL-trained-model-strategy.md`
- `FDS-MDL-A-addendum-after-108a.md` (this file)
- `00-RUN-ORDER.md`
- `run_suite.py`, the per-file test runner supplied with this addendum (section 9.2)

## 3. Environment

- **Run tests from a scratch venv outside the repo,** never the repo's `.venv`, so test packages stay out of the environment the app runs from. Match the baseline: Python 3.13, created with `--system-site-packages`.
- Install `requirements.txt`, **then also install `pytest` and `pytest-timeout`**, which are commented out in `requirements.txt`. PyYAML is optional: without it, two YAML tests skip, as at baseline.
- Pass that venv's interpreter to `run_suite.py` (section 9.2).
- Record the venv location and every package installed beyond `requirements.txt` in the run log.
- Don't edit `requirements.txt` in this spec.

## 4. Paths

Every runtime path goes through `pt_paths`. Nothing at runtime writes inside the program directory.

### 4.1 Model artifacts get their own folder

`pt_paths.models_dir()` is **not** a dedicated model folder. It is the trainer's default working root:

- `neural_dir()` defaults to it.
- BTC trains in the root itself, and each other coin uses `<root>/<SYM>`.
- Before every training run the hub deletes `memories_*.txt`, `memory_weights_*.txt` and similar from the coin folder (`pt_hub.py:5655`).
- A `model_id` such as `ETH` would collide with a coin folder, and anything placed under `models_dir()` sits inside BTC's working folder.

So STRAT-003 artifacts go in a **sibling** of `models_dir()`, never inside it:

- **Add a new function `pt_paths.strategy_models_dir()`** returning `hub_dir() / "strategy_models"`, which is `<data>/hub_data/strategy_models`. Create it lazily like the others, and add it with a test. Don't add path logic anywhere else.
- **Refuse an overlap:** if the configured trainer root (`neural_dir(main_neural_dir)`) is or contains `strategy_models_dir()`, or vice versa, the model loader and the provenance step refuse to run with a clear message. Add a test.
- **Correct `models_dir()`'s docstring** in Phase 1 (or Phase 2 if Phase 1 is skipped). It still says "one `<model_id>/` folder per model", which is no longer what it is. Describe it as the default trainer working root.
- **STRAT-003 artifacts and manifests** live at `strategy_models_dir() / <model_id> /`, with `manifest.json` inside.
- **Manifests store paths relative to `strategy_models_dir()`,** never absolute paths.
- **The trainer's working folders are untouched.** Training output from the legacy trainer stays where the hub puts it today. Copying a trained model into `strategy_models_dir()` with its manifest is the provenance step from FDS-MDL Phase 2.
- **Add a test** that a `model_id` equal to a coin symbol (for example `ETH`) never resolves inside the trainer root or any coin folder under it.

| FDS-MDL says | Use instead |
|---|---|
| `hub_data/models/<model_id>/manifest.json` | `pt_paths.strategy_models_dir() / <model_id> / "manifest.json"` |
| Model artifacts under `hub_data/models/` | `pt_paths.strategy_models_dir() / <model_id> /` |
| Candle downloads | `pt_paths.cache_dir()`, which `app/market_data/candles.py` already uses |
| Runtime backtest scratch output | `pt_paths.data_dir()` |

### 4.2 Committed report outputs

These stay in the repo, because they are documentation, not runtime state:
- `docs/dev/BACKTEST-REPORT-model-1.md`
- `docs/dev/backtest-model-1/`
- `docs/dev/run_backtest_model1.py`

`run_backtest_model1.py report` writes to an explicit `--out` path that defaults to `docs/dev/backtest-model-1/`.

### 4.3 Every agent run of the backtest script is sandboxed

Without `POWERTRADER_HOME`, `cache_dir()` and `data_dir()` resolve to the real `%LOCALAPPDATA%\SJackson\PowerTraderAI\`, which would break the real-folder check in section 9.

- **Every agent run of `run_backtest_model1.py`** (`fetch`, `train`, `run` and `report`) sets `POWERTRADER_HOME` to one scratch folder **outside the repo**, reused across the whole session so cached candles and trained models carry between steps.
- Record that folder in the run log.
- The script prints the resolved cache, data and strategy-models folders at start-up, so the run log shows where everything went.

## 5. Phase 0 — trainer audit: extra scope

FDS-108a changed how the trainer is launched. The audit must cover **both** sides and say so.

### 5.1 On the new base

- Every coin runs `app/pt_trainer.py`.
- **BTC** runs with its working folder at the trainer root itself.
- **Every other coin** runs with its working folder at `<root>/<SYM>`.
- **The root is `neural_dir(main_neural_dir)`.** It is configurable and only defaults to `models_dir()`. Record how it is resolved and where it can be overridden.
- The training-results path also moved. Record where.

Audit `app/pt_trainer.py` as "the trainer the hub actually launches".

### 5.2 On `main` before FDS-108a (`858a0eb`)

- BTC ran `app/pt_trainer.py` from `app/`.
- Each other coin ran `app/<SYM>/pt_trainer.py`, which the hub re-copied from `app/pt_trainer.py` before every launch.

**Known facts to confirm, not rediscover** (from a verified audit; the values are git blob IDs, not SHA-256):
- `app/{BNB,DOGE,ETH,XRP}/pt_trainer.py` were byte-identical to `app/pt_trainer.py` (blob `f0c5fc4`).
- `app/BTC/pt_trainer.py` differs (blob `6c11e97`) and was never launched by the hub.
- Every `app/<SYM>/pt_trainer_standalone.py` (blob `34b0d95`) differs from `app/pt_trainer_standalone.py` (blob `c29fdc5`). The hub launches a standalone script only if the settings point at one.
- Commit `dae9b3e`'s message says "the legacy neural trainer is a mock". Treat that as a claim to test, not a finding.

### 5.3 Additions to `docs/dev/TRAINER-AUDIT.md`

- **A table:** script, SHA-256 of the file contents, git blob ID, launched by (hub, CLI or nothing), and verdict (REAL, STUB or MIXED) for every trainer file found at both `858a0eb` and the new base.
- **The single verdict that gates Phase 1** applies to **the script the hub launches on the new base.**
- **The determinism and data-dependence checks must execute real training** on fixture candles, end to end. Don't replicate `__init__` setup or assert on hard-coded paths. The existing `app/test_hub_trainer.py` and `app/test_subprocess_trainer.py` test nothing, and their pattern must not be copied.

## 6. Phase 1 — port: adjustments (only if STUB or MIXED)

- The ported trainer reads and writes only through `pt_paths`.
- It runs correctly with BTC at the root and other coins at `<root>/<SYM>`, as the hub now launches it.
- **`allow_mock_trainer`** (default false) is a key in `pt_config.json` under `config_dir()`, read the same way as the trading settings. Don't use the YAML `ConfigurationManager` in `pt_config.py`, which the hub doesn't load.
- **Don't delete or untrack the per-coin `app/<SYM>/pt_trainer*.py` copies** in this spec. Record them in the audit. Removing them is a separate chore after this spec merges.
- **Don't extend the FDS-108a migration.** Legacy model files under `app/` aren't migrated by this spec.

## 7. Phase 3 — STRAT-003 adapter: adjustments

- The model loader resolves `model_id` through `strategy_models_dir()` and refuses any artifact without a matching manifest, as FDS-MDL says.
- `strategy.active_id` stays STRAT-001. The selection is read from and written to `config_dir()`, not a file under `app/`.

## 8. Credentials and network

- **This spec needs no exchange credentials.** Training and backtesting use public Binance candles.
- **Never call `pt_secrets` setters,** and never read keyring entries.
- **Network access is allowed only in `run_backtest_model1.py fetch`,** sandboxed as in section 4.3. Tests use fixtures only.

## 9. Test isolation and baseline

### 9.1 Isolation

- **The guard lives in `app/tests/isolation.py`.** It is loaded only by `app/conftest.py`, `app/tests/conftest.py` and `.github/scripts/conftest.py`.
- **New tests must live under `app/`,** or in a folder whose `conftest.py` loads the guard.
- **Proving a test fails on old code:** swap in the old production code and keep the guard on. **Never run a test unguarded.** That is how the real `%APPDATA%` folder got created once before.
- **After every phase,** check that `%APPDATA%\SJackson` and `%LOCALAPPDATA%\SJackson` are still absent and that `cmdkey /list` shows 0 entries containing "PowerTraderAI". Record the result in the run log.

### 9.2 Baseline method

Use **`docs/dev/specs/run_suite.py`**, the per-file runner that produced every number so far. It is supplied with this addendum and committed with the spec files. Don't rebuild or edit it. If it can't run, write `BLOCKED` and stop.

It takes the test interpreter as an argument, and:
- runs each `app/test_*.py`, `app/tests/test_*.py` and `.github/scripts/test_*.py` one file at a time
- excludes `test_phase1_phase2_integration.py`, which kills its own process group on Windows
- applies a 300-second per-test timeout
- records per-test results from JUnit XML
- gives every test process a fresh scratch `POWERTRADER_HOME` and the fail keyring backend

Numbers from a single pytest run, or from any other runner, are not comparable.

Run the baseline on the new base before Phase 0, and compare test by test at the end of every phase.

**Expected at `7832240`:**

| Suite | Passed | Failed | Skipped |
|---|---|---|---|
| `app/` | 1010 | 10–11 | 5–6 |
| `.github/scripts` | 23 | 19 | 1 |

- `test_integration.py::TestPowerTraderHubIntegration::test_graceful_degradation` flips between skip and fail depending on whether Tk finds `tk.tcl`. List it by name every time.
- `test_pr_validation` collects no tests.
- If the base is `main` after the merges, the numbers should match. Record any difference before starting Phase 0.

## 10. Run protocol additions

These add to FDS-MDL section "Run protocol" and `00-RUN-ORDER.md`:

- Stage files by explicit path only. Never `git add .` or `git add -A`.
- **Never open, read, print or copy** any real config file, anything in the real `%APPDATA%` or `%LOCALAPPDATA%` folders, Credential Manager values, or `app/pt_config.json.backup.*`.
- Don't push, open PRs or merge.

## 11. Extra acceptance criteria

These add to FDS-MDL's 10 criteria:

11. `TRAINER-AUDIT.md` covers both `858a0eb` and the new base, with a SHA-256, blob ID, launcher and verdict for every trainer file.
12. No runtime file is written inside the program directory by any phase. The existing static test passes, and any new runtime path goes through `pt_paths`.
13. `strategy_models_dir()` exists with a test and is a sibling of `models_dir()` (`<data>/hub_data/strategy_models`). With default settings, no STRAT-003 artifact is written inside the trainer root or any coin folder; an overlapping configuration is refused; and a `model_id` equal to a coin symbol can't collide with a trainer folder.
14. Model manifests contain no absolute paths, and a model folder copied to a different `POWERTRADER_HOME` still loads.
15. Every agent run of `run_backtest_model1.py` used the recorded scratch `POWERTRADER_HOME`.
16. The real-folder and `cmdkey` checks are clean after every phase.

## 12. Session kickoff

Paste into a fresh Claude Code session, with the three spec files, `run_suite.py` and `suite-9bc2392.json` attached:

```
Implement FDS-MDL-trained-model-strategy.md as amended by FDS-MDL-A-addendum-after-108a.md (v3). Read both fully before acting. Where they conflict, the addendum wins.
Order: branch-base check, cut feat/model-strategy-1, spec-files commit including run_suite.py (section 2), environment (section 3), baseline with run_suite.py (section 9.2), then Phase 0. Phase 0 is a read-only gate: stop after writing TRAINER-AUDIT.md and report the verdict before starting Phase 1.
Base is main at d815910 or later (all prerequisites merged). d815910 adds only .git-blame-ignore-revs and a run-log note on top of 9bc2392, so the tested code and suite-9bc2392.json still apply; record that in the run log. Black has reformatted app/ since the addendum was written: locate cited code by symbol, not line number, and record the baseline against the expected numbers in section 9.2 and suite-9bc2392.json (run_suite.py compare), listing any difference before Phase 0.
Phase 0 covers issue #136 (trainer tests that don't exercise the real launch). In TRAINER-AUDIT.md, say how the new trainer tests meet its acceptance criteria, so the eventual PR can close #136.
```
