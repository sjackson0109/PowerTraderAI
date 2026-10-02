# Run log — FDS-108a review fixes (round 2)

Fixes from the post-build review of FDS-108a (`RUN-LOG-paths-1.md` is the build). One commit per
review item; each item adds its own section below.

## Branch rebuild (before item 2)

* `feat/user-data-separation` was rebuilt **without** the owner's commit `25bf2b8` ("pushing config
  changes"). The old tip `7bbb810` is kept, untouched, as `backup/user-data-separation-7bbb810`.
* New history: chore merge `23243b0` (`chore/untrack-trading-config`), then the FDS-108a commits
  `4938e39` (phase 0) .. `d949df4` (phase 5).
* The new tree is identical to `7bbb810` except the five root `config/*.yaml` files. Those were
  byte-identical to `app/config/*.yaml` (same blob ids) and no code reads them.
* `RUN-LOG-paths-1.md` still names the old ids (chore merge `58efed2`; `25bf2b8` and its root
  `config/*.yaml`). They refer to the history before the rebuild; the phase work itself is unchanged.

## Merge plan (decided by the owner)

The PRs merge in the order 2 -> 3 -> 4, each with a merge commit. PR1's commits arrive inside PR4.

## Rules followed

* Nothing pushed. The backup branch is never touched. No checkout, switch, reset, rebase or stash in the
  working repo; other revisions are read with `git show` or in clones under the session scratchpad.
* `%APPDATA%\SJackson` and `%LOCALAPPDATA%\SJackson` are checked absent before and after each item and
  are never created or read; the real credential store is never read or written.
* The owner's untracked runtime files in the checkout (`app/pt_config.json`, `app/gui_settings.json`,
  backups, databases, logs, `hub_data/`, `data/`) are never opened, changed, moved, staged or deleted.
* Every test process runs with `POWERTRADER_HOME` = a fresh folder in the scratchpad,
  `PYTHON_KEYRING_BACKEND=keyring.backends.fail.Keyring` and `PYTHONDONTWRITEBYTECODE=1`
  (`app/conftest.py` then isolates each test). `.github/scripts` tests run only in a scratch clone.
* No existing test is skipped or deleted and no assertion weakened; any changed assertion is listed in
  its item. `test_no_legacy_paths` and `test_program_dir_read_only` stay green.
* Staging by explicit path only; exactly one commit per item.

## Item 2 — Trainer: program-folder script, Settings change without a restart

Kept from FDS-108a (`0000a23`): the hub runs `app/pt_trainer.py` for every coin with the coin's neural
folder under the user data folder as working directory (BTC: `<data>/hub_data/models`, other coins:
`models/<SYM>`); main's per-coin copying of the trainer stays removed.

* `app/pt_hub.py`: new `_refresh_trainer_path()` sets `proc_trainer_path` from `script_neural_trainer`,
  resolved against the program folder. `__init__` and the Settings window's Save both call it. Before,
  the path was computed once in `__init__`, so a trainer script changed in Settings was only used after
  a restart. `proc_trainer_path` keeps its name and meaning; `start_trainer_for_selected_coin` is
  unchanged apart from a comment.
* The comment at the start-up call of `_ensure_alt_coin_folders_and_trainer_on_startup` no longer says
  the trainer is copied into the coin folders; the method's docstring says its name is historical. Not
  renamed.
* Not changed (outside this item): the runner and trader script paths (`proc_neural.path`,
  `proc_trader.path`) and `hub_dir` are also computed once in `__init__`, so changing those settings
  still needs a restart.
* New `app/tests/test_trainer_launch.py` (4 tests). The hub is built with `PowerTraderHub.__new__` plus
  the `__init__` path set-up calls (no main window); the real `start_trainer_for_selected_coin` runs with
  `subprocess.Popen` patched; the test CWD is a temp folder.
  * `test_every_coin_runs_the_program_folder_trainer_in_its_user_data_folder[BTC/ETH]`: the command is
    `[python, -u, -W, ignore, app/pt_trainer.py, <coin>]`; the working folder is the models folder (BTC)
    or `models/ETH`, inside `POWERTRADER_HOME`'s data folder and not inside the program folder;
    `POWERTRADER_HUB_DIR` is the user hub folder; old training files are cleared there and no `.py` is
    copied in.
  * `test_the_trainer_writes_its_results_to_the_user_data_folder`: reads `app/pt_trainer.py` with `ast`
    (training is not run). `NeuralTrainer.train` assigns `results_file` once, from `pt_paths.data_file`,
    and opens it with `"w"`; that expression, evaluated for BTC and ETH, equals
    `pt_paths.data_file("training_results", "<coin>_training_results.json")` in the user data folder.
  * `test_a_trainer_script_saved_in_settings_is_used_by_the_next_launch`: a hidden Tk root; opens the
    real Settings window, types `pt_trainer_standalone.py` (shipped in `app/`) into "pt_trainer.py path:",
    adds SOL to the coins and presses Save (the real save code). The same hub's next launches (BTC, SOL)
    run `app/pt_trainer_standalone.py` from `models/` and `models/SOL`. Like the existing Tk tests it
    skips only when Tk cannot start; it ran here.
  * Checked in a scratch clone: with the new `_refresh_trainer_path()` call removed from Save, the
    Settings test fails (`proc_trainer_path` still `pt_trainer.py`).
* `app/test_hub_trainer.py` and `app/test_subprocess_trainer.py` pass without testing anything (left
  unchanged). Neither imports `pt_hub`. Both hard-code paths under
  `C:\Users\Administrator\PowerTrader\PowerTrader_AI\app` (`<app>` below) and re-implement main's
  copy-and-run logic themselves: `test_hub_trainer.py:76-107` copies
  `pt_trainer.py` into `<app>\XRP` and runs that copy, `test_subprocess_trainer.py:37-39` runs
  `<app>\XRP\pt_trainer.py` from `<app>\XRP`. On any other machine the trainer or folder is missing, the
  function catches it and returns -1, and there is no assert, so pytest counts a pass. Not re-run in this
  round (`test_hub_trainer` would try to create folders under `C:\Users\Administrator`); round 1 records
  them as 1 passed each. A one-line note was added to their rows in `RUN-LOG-paths-1.md`.

Tests (real checkout, one file per run, Python 3.13 venv with PyYAML):

| File | Result |
|---|---|
| tests/test_trainer_launch (new) | 4 passed |
| tests/test_pt_migrate | 12 passed |
| tests/test_pt_paths | 11 passed, 1 skipped (POSIX-only) |
| tests/test_pt_secrets | 24 passed |
| tests/test_isolation_guard | 6 passed |
| tests/test_program_dir_read_only | 5 passed |
| tests/test_no_legacy_paths | 4 passed |
| tests/test_docs_and_visibility | 5 passed |
| tests/test_credentials_single_source | 15 passed |
| tests/test_config_no_secrets | 7 passed |

The files that import `pt_hub` (several build the full hub, so `__init__` runs the new call) were run in
two scratch clones, one at `d949df4` and one with this change; results are identical:
`test_advanced_features` 22 passed, `test_comprehensive` no tests, `test_core` 1 passed,
`test_credential_audit` 9 passed, `test_gui_exchange_integration` 3 passed, `test_integration` 8 passed
and the 2 known failures, `test_real_app` 1 passed, `test_suite` 16 passed and the 8 known failures,
`test_tabbed_interface` 1 passed. They ran in clones so that no hub start could reach the owner's
untracked files in the checkout.

Note: on Windows a long pytest `--basetemp` pushes the per-test paths past 260 characters and many
tests fail with `FileNotFoundError`; the runs above use a short one.

No existing test changed; no assertion changed.
