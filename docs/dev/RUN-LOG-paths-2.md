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

## Item 3 — Remove old files: check every file against the migration record

The review found data loss: `--remove-old-files` (and the dialog) deleted every path in the `removable`
list stored at migration time, without looking at the files again. If main ran in between (it still
uses `app/`), its newer settings, appended paper-trading data, or a file whose new copy had gone were
deleted. Reproduced in a scratch clone at `a922518`: after migrate, edit `app/gui_settings.json`, append
to `hub_data/paper/trader_status.json`, delete the new `runner_ready.json`, then
`main(["--remove-old-files", "--yes"])` deleted all three (19 files removed, exit 0).

* `app/pt_migrate.py`: new `remove_old_files(paths=None, confirmed=False) -> Removal` is the one code
  path for the hub dialog (`show_migration_dialog`) and `--remove-old-files`. Without `confirmed` it only
  checks (the list shown before asking); with it, each unit is checked again just before it is deleted.
  `remove_legacy_files` and `removable_legacy_files` stay, as thin wrappers over it.
* Checks, in order; a file that fails is never deleted and is reported with the reason (dialog: a
  "Not removed:" list in the question and in the result; CLI: `  not removed: <file>: <reason>` lines):
  1. recorded as migrated and safe to remove, with a hash and a copy, else `not part of the migration`
     (also a record without hash or copy, e.g. the earlier format: no compatibility path);
  2. the current SHA-256 equals the one recorded at migration, else `changed since it was migrated`;
  3. the recorded copy exists, else `no migrated copy`. A copy is a path, or
     `keyring:<exchange>:<field>` for a credential file (checked by name with `pt_secrets.stored_fields`).
* `migration-state.json` now holds, per legacy file, `files[path] = {fp, sha256, copy}` and
  `removable` as a list of units. The hash is that of the content migrated: the copy just written, the
  identical target, or the bytes the config file was parsed from. An unchanged file keeps its first
  record, so the hash stays the one taken at migration and is not recomputed at each start-up.
* Git checkout: when `legacy_install_dir()` has a `.git` folder or file, `app/pt_config.json` and
  `app/gui_settings.json` are never deleted and are reported as `kept: other branches in this git
  checkout still use it` (also marked in `migration-report.md`). Kept files do not count as refused.
* SQLite: a `.db` and its `-wal`/`-shm` are one unit everywhere (loose databases, and any database under
  `hub_data/` or `logs/`). Identical only if the same parts exist on both sides with the same content,
  else a conflict and nothing copied. All parts are copied, or none (parts copied before a failure are
  removed again, so the next start retries). The unit is removable only if every part was copied or
  identical. Before deleting, every part is checked, and a `-wal`/`-shm` that appeared after the
  migration counts as a change. Deletion renames every part aside (`.pt-removing`) first, then deletes:
  on Windows a part held open (checked: also every part of an open SQLite database) cannot be renamed,
  so the renamed parts are put back and nothing is deleted.
* Design choice (a deviation from (a)(3), narrowed by the second review below): the recorded copy of
  each part of a database is the migrated `.db`, not its own `-wal`/`-shm` copy. SQLite merges the
  `-wal` into the `.db` and deletes `-wal`/`-shm` when it closes the database (checked), so once the new
  app has used the database those copies are gone by design.
* Also fixed, same rule (a file whose content was not migrated is never offered): a config file with a
  credential that has no keyring field (for example a Coinbase `passphrase`) was marked removable; it no
  longer is. `r_key.txt.bak_*` copies now need the Robinhood keyring entries (before, credentials in
  environment variables were enough), because those entries are their recorded copy.
* CLI exit code: `--remove-old-files` returns 1 when any file was refused (as before when the prompt is
  declined), 0 otherwise. The checks hash every candidate, so on a large `market_data.db` the dialog
  waits for the hash before asking.
* Docs: README "Upgrading from an older version" and `docs/technical/ARCHITECTURE.md` (`pt_migrate`)
  describe the checks, the database unit and the git-checkout rule. `docs/setup/CREDENTIAL_SETUP.md`
  ("the old files stay until you press Remove old files") is still accurate; unchanged.
* New `app/tests/test_pt_migrate_removal.py` (19 tests; it reuses the `legacy` fixture of
  `test_pt_migrate.py`):
  * `test_remove_old_files_refuses_what_main_changed_after_the_migration`: the review scenario above
    through `main(["--remove-old-files", "--yes"])`; exit 1; the three files are reported (`changed
    since it was migrated` x2, `no migrated copy`) and are byte-identical afterwards; the unchanged files
    with a copy (config files, Robinhood keys, neural files, candles, the database unit, `market_data.db`)
    are removed; `ETH/pt_trainer.py` stays.
  * Record: hash and copy for every removable file; trading config copy = config file + 4 keyring
    entries; the database unit `[db, db-wal]` with the migrated `.db` as copy.
  * Content, not size and time: a same-size edit with the old mtime restored is refused. A Robinhood key
    file whose keyring entry is gone is refused (`no migrated copy`).
  * Not in the record: a conflicted `pt_config.json` and `ETH/pt_trainer.py` are refused; a record
    without `sha256` or without `copy`, and the earlier list-of-paths format, are refused; the
    unmovable-credential config file is not offered.
  * Git checkout (`.git` folder and `.git` file): both settings files kept through the CLI (exit 0) and
    when asked for by name; the report marks them.
  * Database unit: identical unit not copied again and removable; different or missing target `-wal`
    is a conflict and nothing is written next to the existing database; a failed `-shm` copy leaves no
    part at the target and the retry copies all three; a changed `-wal` keeps both parts; a new `-wal`
    keeps the database; a part that cannot be renamed keeps every part (patched `os.rename`, and on
    Windows a real open handle); after a checkpoint the migrated `.db` still counts as the copy, and
    without it both parts are refused.
  * Dialog: with a changed file and a missing copy, `remove_old_files` is called first without
    arguments, then with the offered files and `confirmed=True`; the question lists both files under
    "Not removed:" with their reasons and does not offer them; the result repeats them; they still exist.
* Checked in a scratch clone by disabling each check in turn (hash, copy, git rule, sidecar presence,
  rename aside, record, new `-wal`): each makes at least one new test fail; restored, all pass.

### Review of item 3 (fixed in the same commit)

Three blocking findings, all valid. Each was reproduced with the new tests below, run in a scratch clone
against the code before this fix (the first version of this commit, `998682e`): all 14 new tests fail
there, and the 19 earlier ones pass.

1. **A file could be its own copy.** README allows `POWERTRADER_HOME` inside a checkout. At the install
   root its `data/` and `logs/` are also legacy locations (`data/holdings.db`, `logs/`), and in `app/` the
   same holds for `app/data/` and `app/logs/`. The new app's own database was recorded with itself as its
   copy, and Remove old files deleted it and its `-wal`, the only copies. `logs/` was also copied into
   `logs/legacy` again on every run, one level deeper each time.
   * `_copy_file` now skips a source in a folder PowerTrader uses now (config, data, logs, cache,
     compared after resolving links, junctions, subst drives and short names) or whose target is the
     same file (`os.path.samefile`). It is not copied, recorded or offered. This also covers the files of
     the `hub_data/` and `logs/` trees, so `_copy_tree` is unchanged.
   * `_refusal` refuses `no migrated copy` when a recorded copy is the same file as a part of the unit,
     and refuses a part in a folder in use with a new reason, `in a folder PowerTrader uses now`. Only a
     record carried over from another `POWERTRADER_HOME` (its config folder copied along) can list such a
     file, since the record lives in the config folder.
2. **The git-checkout rule looked at the program that runs, not at the file.** The record is per user,
   so it can list another checkout's files. Remove old files run from another clone, a worktree or a
   release folder deleted the first checkout's `app/pt_config.json` and `app/gui_settings.json`. The same
   checkout reached through a junction was missed too, because paths were compared as text.
   * At migration, both settings files get `keep: true` in their record when the install root (or the
     folder above `app/`) has `.git`.
   * `_kept_reason(path, record)` keeps them when the record says `keep`, or when the file's own install
     root (the folder above its folder) has `.git`, or when it is the same file as this program's legacy
     settings and `legacy_install_dir()` has `.git`. Unit lookup and the `_prune_empty` roots compare
     resolved paths.
3. **A write between the check and the delete was lost.** `_refusal` hashed each part, then
   `_delete_unit` renamed it aside and deleted it without looking again. A write by an old hub still
   running from `app/` in that gap was deleted without having been migrated.
   * `_delete_unit` now renames every part aside, then checks that nothing exists under the unit's names
     (its parts, `-wal` and `-shm`) and runs `_refusal` again on the renamed files (hash, copy). On any
     failure every part is put back and the unit is refused. On Windows no program can write to a part
     once it is renamed (one that holds it open makes the rename fail), so what is deleted is what was
     checked.

Notes and limits:

* A part written again under its old name while renamed aside cannot be put back over the new file. It
  stays as `<name>.pt-removing` with its content, and a warning is logged; nothing is deleted. A failed
  rename already behaved this way.
* On macOS and Linux a program that already had a part open can still write to it after the rename. The
  second hash narrows that window but cannot close it.
* Confirmed removal hashes each file twice (before and after the rename). With the check shown before
  asking, that makes three hashes of a large database.
* Not covered: a `hub_data_dir` or `main_neural_dir` that the user points at the old `app/` folders. That
  is only allowed when `POWERTRADER_HOME` contains them, and the migration does not read those settings.
  Such files still have a real copy in the new data folder, so removing them loses no content.
* Docs: README ("Upgrading from an older version") adds that files in the folders in use are never
  treated as old files; `ARCHITECTURE.md` (`pt_migrate`) adds the second check after the rename, the
  git rule decided from the file, and the folders in use.

New tests in `app/tests/test_pt_migrate_removal.py` (14; 33 in the file):

* `test_the_git_rule_follows_the_file_not_the_program_that_runs[checkout|release folder × recorded|not
  recorded]`: checkout A (with `.git`) is migrated, then `main(["--remove-old-files", "--yes"])` runs from
  B (another checkout, or a folder without `.git`), with and without the `keep` flags in the record.
  A's two settings stay and are reported as kept; exit 0; A's `trading_config.json` is removed.
* `test_the_keep_flag_recorded_at_migration_is_honoured`: in the conftest layout (legacy folder not
  inside the install root) only the flag keeps the settings once removal runs from a release folder.
* `test_the_git_rule_holds_through_another_spelling_of_the_checkout`: `alias` is a junction to the
  checkout `real`; migrated through `alias`, removed from `real`, with the flags dropped. Both settings
  stay; the junction is removed afterwards and the checkout is untouched.
* `test_with_powertrader_home_in_the_checkout_its_own_files_are_never_old_copies[install root|app]`:
  `POWERTRADER_HOME` is the install root or `app/`. The new app's `data/holdings.db` with its `-wal` and a
  log in its `logs/` are never copied, conflicting or removable over two migration runs, no
  `logs/legacy/legacy` appears, and they are byte-identical after `--remove-old-files --yes` (exit 0, no
  "not removed"). The other old files are removed as usual.
* `test_a_recorded_file_in_a_folder_powertrader_uses_now_is_refused`: a record carried over to a home at
  the install root; the unchanged `data/holdings.db`, whose copy exists, is refused with the new reason.
* `test_a_record_whose_copy_is_the_file_itself_is_refused[same|junction]`: a record whose copy is the file
  (same spelling, or through a junction) is refused with `no migrated copy` by the check the dialog and
  the CLI show, and when confirmed.
* `test_a_write_between_the_check_and_the_delete_keeps_the_file`: `_sha256` is wrapped to append a trade
  to `hub_data/paper/trader_status.json` right after hashing it (the review's reproduction). It is refused
  as changed, keeps the appended trade, and no `.pt-removing` file is left.
* `test_a_file_that_appears_at_an_old_name_during_the_delete_keeps_the_database`: a new `-shm` appears
  once the `.db` is renamed aside; both parts are put back unchanged and refused.
* `test_a_part_written_again_at_its_old_name_during_the_delete_keeps_the_database`: the unit's `-wal` is
  written again under its name once renamed aside. Nothing is deleted: the `.db` is put back, the new
  `-wal` stays, and the old one stays as `.pt-removing` with its content.

Checked in a scratch clone by disabling each new check in turn (the guard in `_copy_file`, the
folder-in-use refusal, the same-file copy refusal, the `keep` flag, the file's own install root, the
second check after the rename, the names check after the rename): each makes at least one new test fail;
restored, all pass. With both the file's own root and the `samefile` comparison disabled, the junction
test fails too.

Tests (real checkout, one file per run):

| File | Result |
|---|---|
| tests/test_pt_migrate_removal (new) | 33 passed |
| tests/test_pt_migrate | 12 passed |
| tests/test_pt_paths | 11 passed, 1 skipped (POSIX-only) |
| tests/test_pt_secrets | 24 passed |
| tests/test_isolation_guard | 6 passed |
| tests/test_program_dir_read_only | 5 passed |
| tests/test_no_legacy_paths | 4 passed |
| tests/test_docs_and_visibility | 5 passed |
| tests/test_credentials_single_source | 15 passed |
| tests/test_config_no_secrets | 7 passed |
| tests/test_trainer_launch | 4 passed |

Files that import `pt_hub` (whose start-up runs the migration) and `.github/scripts`, in two scratch
clones (`a922518`, and `a922518` plus this change), with identical results: `test_advanced_features` 22
passed, `test_comprehensive` no tests, `test_core` 1 passed, `test_credential_audit` 9 passed,
`test_gui_exchange_integration` 3 passed, `test_integration` 8 passed and the 2 known failures,
`test_real_app` 1 passed, `test_suite` 16 passed and the 8 known failures, `test_tabbed_interface` 1
passed, `.github/scripts/test_powertrader_system.py` 3 passed, 1 skipped. All of `app/tests` in the same
two clones: 481 passed, 3 skipped before; 501 passed, 2 skipped after; no failures. The difference in
skips is Tk failing to start now and then on this machine ("Can't find a usable tk.tcl"), in either
clone, from run to run.

After the review fixes, the same files in a scratch clone of `998682e` plus the fixes give the same
results. In `test_integration` the 2 known failures are `test_graceful_degradation` and
`test_powertrader_hub_creation` (`hasattr(hub, "style")` is false). The second is skipped instead in some
runs, when Tk does not start. That happens from run to run in both the clone with the fixes and a clone
of `998682e` alone. All of `app/tests` in the clone with the fixes: 515 passed, 2 skipped (`PyJWT` not
installed, POSIX permission bits), no failures.

No existing test changed; no assertion changed.

### Second review of item 3 (fixed in the same commit)

Three blocking findings. All valid; the second and third are the same defect (a failed delete after the
rename was reported as a success). Reproduced with the new tests below against the previous version of
this commit (`9977743`): 11 of the 12 new tests fail there. The twelfth, the normal SQLite merge, passes
there as it should.

1. **A `-wal` whose content exists nowhere else could be deleted.** Every part of a database unit has
   the migrated `.db` as its recorded copy. If the migrated `-wal` is deleted before the new app opens the
   database (a clean-up or sync tool), its committed rows are in no migrated file, yet the legacy `.db`
   and `-wal` were removed. Reproduced with a real SQLite database in WAL mode (one row only in the
   `-wal`): the row was lost everywhere.
   * `_refusal`: a `-wal` part that is not empty also needs, unless its own copy (`<migrated db>-wal`)
     still exists, a migrated `.db` that differs from what was copied (SQLite merged the `-wal` into it).
     If the migrated `.db` is still as copied and its `-wal` is gone, the unit is refused with `no
     migrated copy`. An empty `-wal` holds nothing and needs no copy of its own; a `-shm` holds no data
     (SQLite rebuilds it) and still needs only the `.db`. The record format is unchanged.
2. **and 3. A part that could not be deleted after the rename was reported as removed.** `_delete_unit`
   only logged a failed `os.remove`. The unit was counted as removed (CLI exit 0, the dialog said the
   same), and the part stayed as `<name>.pt-removing`, a name git did not ignore: for `trading_config.json`
   or `r_key.txt`, plaintext keys that could be committed. Windows renames a read-only file but will not
   delete it, so a read-only part triggered it every time (checked: read-only `.db`, `-wal`, `r_key.txt`,
   `trading_config.json`).
   * New `_cannot_delete`, run before anything is renamed (and in the check shown before asking, so such
     a file is not offered): a read-only part refuses the whole unit with `could not be removed
     (read-only)`. `os.access(path, os.W_OK)`, so this holds on every platform (a read-only file signals
     "keep" on macOS and Linux too).
   * The parts are deleted `-shm`, `-wal`, then `.db`. If an `os.remove` still fails (something opened the
     part after the rename), the parts not yet deleted are put back under their names and refused with
     `could not be removed (<error>)`; only the parts actually deleted are reported as removed. So a
     failure leaves a database, never a `-wal` without one. The CLI exits 1 and the dialog lists them.
   * A part that cannot be put back (a file appeared under its name meanwhile) is reported with `, left as
     <name>.pt-removing` added to its reason, in the dialog and on the CLI, not only in the log.
   * `.gitignore`: `*.pt-removing`.
   * Also (not in the review, same code): `_cannot_delete` refuses a unit when a `<name>.pt-removing` from
     an earlier run is in the way (`could not be removed (<name>.pt-removing is in the way)`). Windows
     refused that rename already; on macOS and Linux the rename would have replaced that file and its
     content.

Deviations and limits:

* (a)(3): the copy of a `-wal` is still recorded as the migrated `.db`; the check above adds its own copy
  only while SQLite has not merged it. If the migrated `-wal` is deleted by something else and the new app
  then writes to the database, the `.db` changes and the check cannot tell that the legacy `-wal` was
  never merged. Telling would need reading the `-wal` frames against the database pages.
* (c) "all parts or none": holds when a part is read-only (refused first), held open (the rename fails),
  or changed (found after the rename). If an `os.remove` fails after the rename on a later part, the parts
  already deleted cannot be brought back. They passed every check, so their content is in the new
  location; they are reported as removed and the rest as not removed. The review asked that nothing be
  reported as removed then; that would tell the user a deleted file is still there.

New tests in `app/tests/test_pt_migrate_removal.py` (12; 45 in the file):

* `test_a_wal_whose_copy_went_before_sqlite_merged_it_is_refused`: the review's probe with a real
  SQLite database (one row only in the legacy `-wal`; the migrated `-wal` deleted before the new app
  opens the database). The check and the confirmed removal refuse both parts with `no migrated copy`; a
  copy of the legacy files still yields the row.
* `test_once_sqlite_merged_the_wal_into_the_migrated_database_both_parts_go`: the new app opens and
  closes the migrated database (SQLite merges and deletes the `-wal`; the `.db` changes); both legacy
  parts are removed and the migrated database holds the row.
* `test_an_empty_wal_needs_no_copy_of_its_own`: the fixture's `-wal` (with data) is refused without its
  own copy; a database with an empty `-wal` is removed.
* `test_a_read_only_part_keeps_the_whole_database[.db|-wal]`: not offered; when confirmed both parts are
  refused (`read-only`), byte-identical, no `.pt-removing` left.
* `test_a_read_only_credential_file_is_kept_and_the_cli_says_so`: the review's probe (`r_key.txt` and
  `trading_config.json` read-only); `--remove-old-files --yes` exits 1, prints both with the reason,
  they are unchanged under their own names, the other files are removed.
* `test_a_part_whose_delete_fails_after_the_rename_is_not_reported_as_removed[first (-wal)|last (.db)]`:
  `os.remove` fails on the `-wal` (deleted first): nothing deleted, both refused and unchanged. On the
  `.db` (deleted last): the `-wal` is reported removed, the `.db` is put back unchanged and refused. No
  `.pt-removing` left in either case.
* `test_a_credential_file_whose_delete_fails_is_put_back_and_the_cli_says_so`: the same for `r_key.txt`
  through the CLI: exit 1, the reason printed, the file back unchanged.
* `test_a_file_left_renamed_aside_earlier_is_never_overwritten`: an earlier `.pt-removing` is in the way:
  not offered, refused when confirmed, its content unchanged.
* `test_git_ignores_a_file_left_renamed_aside`: `.gitignore` has `*.pt-removing`.
* `test_the_dialog_reports_what_it_could_not_delete`: the dialog does not offer a read-only `r_key.txt`
  and lists it with the reason. When the `.db` delete fails, the result counts one file fewer than
  offered (the `-wal` went), and lists the `.db` with `could not be removed (PermissionError)`.

Checked in a scratch clone by disabling each new piece in turn (the `-wal` check, the read-only check,
the in-the-way check, the check shown before asking, the handling of a failed delete, the delete order,
the "left as" note): each makes at least one test fail; restored, all 45 pass.

Existing assertion changed (a test added earlier in this same item, `test_pt_migrate_removal.py`):
`test_a_part_written_again_at_its_old_name_during_the_delete_keeps_the_database`, the `-wal`'s reason
`changed since it was migrated` -> `changed since it was migrated, left as
order_management.db-wal.pt-removing`. That part is the one left renamed aside, and the reason now says
so. No other assertion changed; no test from before this round changed.

Docs: README ("Upgrading from an older version": a read-only file is kept; if a part of a database
cannot be deleted, the database is kept) and `ARCHITECTURE.md` (`pt_migrate`: the `-wal` rule, read-only
parts, the delete order).

Tests (real checkout, one file per run):

| File | Result |
|---|---|
| tests/test_pt_migrate_removal | 45 passed |
| tests/test_pt_migrate | 12 passed |
| tests/test_pt_paths | 11 passed, 1 skipped (POSIX-only) |
| tests/test_pt_secrets | 24 passed |
| tests/test_isolation_guard | 6 passed |
| tests/test_program_dir_read_only | 5 passed |
| tests/test_no_legacy_paths | 4 passed |
| tests/test_docs_and_visibility | 5 passed |
| tests/test_credentials_single_source | 15 passed |
| tests/test_config_no_secrets | 7 passed |
| tests/test_trainer_launch | 4 passed |

All of `app/tests` in a scratch clone with these changes: 527 passed, 2 skipped (`PyJWT` not installed,
POSIX permission bits), no failures. Not run again: the files that import `pt_hub`, and
`.github/scripts`. This fix changes only what runs when Remove old files is used; the start-up migration
they run is unchanged, and the hub only opens the dialog.

### Review round 3: a hot `-journal` is part of the database unit

The workflow's third review round left one finding open: a database in SQLite's default rollback-journal
mode (every legacy database except `order_management.db`) was not one unit with its `-journal`. After a
crash mid-commit the `.db` holds half-written pages and the hot `-journal` the committed ones. The `.db`
was copied without it, so the migrated database showed the half-applied update as committed data, and
Remove old files then deleted the legacy `.db` (its hash matched that copy) and left the `-journal`, the
only record of the committed rows, orphaned. The reviewer reproduced it with a real SQLite database.

Fix (folded into this item's commit after the workflow stopped on a usage limit):

* `SQLITE_SIDECARS` is now `-wal`, `-shm`, `-journal`, so a `-journal` is compared, copied, recorded,
  checked and deleted with its `.db` (the `.db` still goes last).
* The `-wal` rule in `_refusal` now covers both data-holding sidecars (`SQLITE_DATA_SIDECARS`): a non-empty
  `-journal` counts as migrated only while its own copy exists or once SQLite has rolled it back into the
  migrated `.db` (which then differs from what was copied).
* Tests (`test_pt_migrate_removal.py`, real SQLite, 2000 rows, an update spilled into the `.db` with
  `cache_size=1` and copied with its hot `-journal` while the transaction is open):
  * `test_a_hot_journal_is_migrated_and_removed_with_its_database`: the `-journal` is copied, the migrated
    database reads as the 2000 committed rows, the new app opening it rolls the journal back, and both
    legacy parts are removed together.
  * `test_a_hot_journal_whose_copy_went_before_sqlite_rolled_it_back_is_refused`: the migrated `-journal`
    deleted before the new app opened its database: both legacy parts refused (`no migrated copy`), the
    legacy files still read as the committed rows.
  * Against the code before this fix both fail (no `-journal` is copied); with it both pass.
* Docs: README and `ARCHITECTURE.md` name `-journal` with `-wal`/`-shm`.
