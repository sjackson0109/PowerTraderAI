"""FDS-108a review item 4: a legacy file that conflicts is kept too. Nothing in
the new location is replaced; the legacy copy is saved next to it as
``<name>.conflict-<source>.<ext>`` (``app`` for app/, ``root`` for the
install root). When both legacy folders hold a different version of a file
the new location does not have yet, the newer one gets ``<name>``. Both files
are listed in the report, the dialog and the CLI, and the conflict copy is the
migrated copy that Remove old files checks. Fixture legacy files only
(conftest points the legacy folders at temp dirs)."""

import json
import os
import shutil
import sys
from unittest import mock

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
for folder in (APP_DIR, TESTS_DIR):
    if folder not in sys.path:
        sys.path.insert(0, folder)

import pt_migrate  # noqa: E402
import pt_paths  # noqa: E402
import pt_secrets  # noqa: E402
from helpers_coinbase import KEY_NAME  # noqa: E402
from pt_migrate import APP, CHANGED, KEPT_FOR_BRANCHES, NO_COPY, ROOT  # noqa: E402
from test_pt_migrate import digest_tree, entries, legacy, no_credential_env, write  # noqa: E402,F401
from test_pt_migrate_removal import legacy_db, migrated_db, sha, state, tk_root  # noqa: E402,F401

T = 1_700_000_000 * 10**9  # a fixed modification time (ns); offsets below are seconds


def stamp(path, seconds):
    t = T + seconds * 10**9
    os.utime(path, ns=(t, t))


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def user_tree():
    return digest_tree(pt_paths.config_dir(), pt_paths.data_dir(), pt_paths.cache_dir(), pt_paths.log_dir())


def legacy_logs(legacy):
    return {APP: os.path.join(legacy["app"], "logs"), ROOT: os.path.join(legacy["root"], "logs")}


def migrated_logs():
    return os.path.join(pt_paths.log_dir(), "legacy")


def two_logs(legacy, newer, name="powertrader.log"):
    """``name`` in app/logs and in <root>/logs with different content; ``newer``
    is the folder whose copy was written last. Returns the two paths."""
    folders = legacy_logs(legacy)
    paths = {}
    for label, folder in folders.items():
        paths[label] = write(os.path.join(folder, name), f"{label} {name}\n")
        stamp(paths[label], 100 if label == newer else 0)
    return paths


def two_databases(legacy, newer):
    """order_management.db in app/ (with its -wal, fixture) and in the root;
    ``newer``'s parts were written last. Returns the two .db paths."""
    dbs = {APP: legacy_db(legacy)}
    dbs[ROOT] = write(os.path.join(legacy["root"], "order_management.db"), b"SQLite format 3\x00root orders")
    for label, db in dbs.items():
        for part in (db, db + "-wal"):
            if os.path.exists(part):
                stamp(part, 100 if label == newer else 0)
    return dbs


def label_text(win):
    return "\n".join(w.cget("text") for w in win.winfo_children() if w.winfo_class() == "TLabel")


# --- two legacy copies in the same run: the newer one gets the name -----------------------------


@pytest.mark.parametrize("newer", [ROOT, APP], ids=["root newer", "app newer"])
def test_the_newer_of_two_legacy_copies_gets_the_name_and_the_older_is_kept_beside_it(
        legacy, monkeypatch, newer):
    """The owner's machine: <root>/logs/errors.log and powertrader.log are
    newer than app/logs/*. Both go to logs/legacy/: the newer one as <name>,
    the older one as <name>.conflict-<its folder>.<ext>. Each file is written
    once, straight to its final name (the choice is made before copying)."""
    older = APP if newer == ROOT else ROOT
    names = ("powertrader.log", "errors.log", "trace")  # trace: a name without an extension
    sources = {name: two_logs(legacy, newer, name) for name in names}
    written = []
    real_copy = shutil.copy2

    def copy2(src, dst, *args, **kwargs):
        written.append(dst)
        return real_copy(src, dst, *args, **kwargs)

    monkeypatch.setattr(pt_migrate.shutil, "copy2", copy2)
    report = pt_migrate.migrate()
    expected = set()
    for name in names:
        target = os.path.join(migrated_logs(), name)
        stem, ext = os.path.splitext(name)
        copy = os.path.join(migrated_logs(), f"{stem}.conflict-{older}{ext}")
        expected |= {name, os.path.basename(copy)}
        assert read(target) == f"{newer} {name}\n"
        assert read(copy) == f"{older} {name}\n"
        assert written.count(target) == 1 and written.count(copy) == 1
        assert (sources[name][newer], target) in report.copied
        assert (sources[name][older], target) in report.conflicts
        assert report.conflict_copies[sources[name][older]] == copy
        assert report.newer[target] == sources[name][newer]
        assert {sources[name][newer], sources[name][older]} <= set(report.removable)
    assert set(os.listdir(migrated_logs())) == expected
    assert os.path.basename(report.conflict_copies[sources["trace"][older]]) == f"trace.conflict-{older}"
    if newer == ROOT:  # the names the owner will see
        assert os.path.isfile(os.path.join(migrated_logs(), "powertrader.conflict-app.log"))
        assert os.path.isfile(os.path.join(migrated_logs(), "errors.conflict-app.log"))


@pytest.mark.parametrize("newer", [ROOT, APP], ids=["root newer", "app newer"])
def test_a_database_goes_with_its_wal_and_shm_and_its_newest_part_decides(legacy, newer):
    """app/ and the root both hold order_management.db. The unit whose newest
    part was written last gets the name, with its own -wal/-shm; the other is
    saved whole as order_management.conflict-<folder>.db with its -wal/-shm.
    In the root-newer case app's .db is newer than root's .db: only root's
    -shm makes root the newer unit."""
    app_db = legacy_db(legacy)  # with a -wal, no -shm (fixture)
    root_db = write(os.path.join(legacy["root"], "order_management.db"), b"SQLite format 3\x00root orders")
    write(root_db + "-wal", b"root wal")
    write(root_db + "-shm", b"root shm")
    stamp(app_db, 50)
    stamp(app_db + "-wal", 100 if newer == APP else 10)
    stamp(root_db, 0)
    stamp(root_db + "-wal", 20)
    stamp(root_db + "-shm", 100 if newer == ROOT else 30)
    units = {APP: [app_db, app_db + "-wal"], ROOT: [root_db, root_db + "-wal", root_db + "-shm"]}
    digests = {p: sha(p) for unit in units.values() for p in unit}
    older = APP if newer == ROOT else ROOT

    report = pt_migrate.migrate()
    target = migrated_db()
    copy = os.path.join(pt_paths.data_dir(), f"order_management.conflict-{older}.db")
    winner, loser = units[newer], units[older]
    for part in winner:
        assert sha(target + part[len(winner[0]):]) == digests[part]
    for part in loser:
        assert sha(copy + part[len(loser[0]):]) == digests[part]
    for suffix in ("-wal", "-shm"):  # nothing at a name its own unit does not have
        assert os.path.exists(target + suffix) == (winner[0] + suffix in winner)
        assert os.path.exists(copy + suffix) == (loser[0] + suffix in loser)
    assert report.conflicts == [(loser[0], target)]
    assert report.conflict_copies == {p: copy + p[len(loser[0]):] for p in loser}
    assert report.newer == {target: winner[0]}
    record = state()
    assert loser in record["removable"] and winner in record["removable"]
    assert all(record["files"][p]["copy"] == [copy] for p in loser)  # the conflict .db, as in item 3
    assert all(record["files"][p]["copy"] == [target] for p in winner)


def test_if_the_newer_copy_cannot_be_made_the_older_one_waits(legacy, monkeypatch):
    """The older copy is not put at <name> in the meantime: the next start
    copies the newer one there first."""
    paths = two_logs(legacy, ROOT)
    target = os.path.join(migrated_logs(), "powertrader.log")
    real_copy = shutil.copy2

    def copy2(src, dst, *args, **kwargs):
        if src == paths[ROOT]:
            raise PermissionError(src)
        return real_copy(src, dst, *args, **kwargs)

    monkeypatch.setattr(pt_migrate.shutil, "copy2", copy2)
    report = pt_migrate.migrate()
    assert (paths[ROOT], "copy failed (PermissionError)") in report.errors
    assert (paths[APP], f"not copied yet: the newer {paths[ROOT]} could not be copied first") in report.errors
    assert os.listdir(migrated_logs()) == []
    assert not set(paths.values()) & set(report.removable)
    monkeypatch.setattr(pt_migrate.shutil, "copy2", real_copy)
    retry = pt_migrate.migrate()
    assert read(target) == f"{ROOT} powertrader.log\n"
    assert read(os.path.join(migrated_logs(), "powertrader.conflict-app.log")) == f"{APP} powertrader.log\n"
    assert set(paths.values()) <= set(retry.removable)


# --- a file already in the new location is never replaced ---------------------------------------


def test_a_file_already_in_the_new_location_is_never_replaced(legacy):
    """Older than both legacy copies, and used by the hub since an earlier
    start: it stays as it is, and each legacy copy is saved beside it."""
    paths = two_logs(legacy, ROOT)
    log = write(os.path.join(migrated_logs(), "powertrader.log"), "the new app's log\n")
    db = write(migrated_db(), b"SQLite format 3\x00the new app's orders")
    for path in (log, db):
        stamp(path, -1000)
    kept = {p: (sha(p), os.stat(p).st_mtime_ns) for p in (log, db)}

    report = pt_migrate.migrate()
    assert {p: (sha(p), os.stat(p).st_mtime_ns) for p in kept} == kept
    assert not os.path.exists(db + "-wal")  # the legacy -wal went with its own .db
    for label in (APP, ROOT):
        copy = os.path.join(migrated_logs(), f"powertrader.conflict-{label}.log")
        assert read(copy) == f"{label} powertrader.log\n"
        assert (paths[label], log) in report.conflicts and report.conflict_copies[paths[label]] == copy
    app_db = legacy_db(legacy)
    db_copy = os.path.join(pt_paths.data_dir(), "order_management.conflict-app.db")
    assert sha(db_copy) == sha(app_db) and sha(db_copy + "-wal") == sha(app_db + "-wal")
    assert (app_db, db) in report.conflicts
    assert report.newer == {}  # nothing of this run is at <name>
    lines = report.conflict_lines()
    assert f"{log}: was already there, kept (in use)" in lines
    assert f"{db}: was already there, kept (in use)" in lines
    assert set(paths.values()) | {app_db, app_db + "-wal"} <= set(report.removable)


def test_a_newer_live_legacy_config_never_turns_an_existing_paper_config_live(legacy):
    """The config folder holds a paper pt_config.json from an earlier start.
    The legacy one is newer and says live: it is saved as
    pt_config.conflict-app.json, and the trading mode stays paper."""
    from trading_mode import read_trading_settings

    existing = write(pt_paths.settings_file(), {"trading": {"mode": "paper"}, "kept": True})
    stamp(existing, -1000)
    source = write(os.path.join(legacy["app"], "pt_config.json"),
                   {"trading": {"mode": "live", "active_broker": "binance"}, "coins": ["BTC"]})
    stamp(source, 1000)
    before = sha(existing)
    report = pt_migrate.migrate()
    copy = pt_paths.config_file("pt_config.conflict-app.json")
    assert sha(existing) == before
    assert not read_trading_settings().is_live
    assert read_trading_settings(copy).is_live  # the live settings are only in the conflict copy
    assert report.conflict_copies[source] == copy and (source, existing) in report.conflicts
    assert not pt_migrate.migrate().changed  # the next start changes nothing either
    assert sha(existing) == before and not read_trading_settings().is_live


def test_a_conflict_copy_of_a_config_file_is_stripped_like_a_migrated_one(
        legacy, isolated_user_dirs, monkeypatch, tmp_path, memory_keyring):
    """The conflict copy is byte-identical to what a normal migration writes
    for the same legacy file (credential fields removed, folders that pointed
    into app/ blanked), and the credentials go to the keyring as usual."""
    names = ("trading_config.json", "exchange_config.json", "gui_settings.json")
    monkeypatch.setenv("POWERTRADER_HOME", str(tmp_path / "plain_home"))
    pt_migrate.migrate()
    plain = {}
    for name in names:
        with open(pt_paths.config_file(name), "rb") as f:
            plain[name] = f.read()
    stored = entries(memory_keyring)
    memory_keyring.entries.clear()

    monkeypatch.setenv("POWERTRADER_HOME", isolated_user_dirs["home"])
    for name in names:
        write(pt_paths.config_file(name), {"already": "there"})
    report = pt_migrate.migrate()
    for name in names:
        copy = pt_paths.config_file(name.replace(".json", ".conflict-app.json"))
        with open(copy, "rb") as f:
            assert f.read() == plain[name], name
        with open(pt_paths.config_file(name), encoding="utf-8") as f:
            assert json.load(f) == {"already": "there"}
        text = read(copy)
        for leak in ("bin-secret", "kr-secret", "BEGIN EC", KEY_NAME, "rh.legacy"):
            assert leak not in text, name
        assert report.conflict_copies[os.path.join(legacy["app"], name)] == copy
    assert entries(memory_keyring) == stored
    trading = os.path.join(legacy["app"], "trading_config.json")
    assert trading in report.removable
    assert state()["files"][trading]["copy"] == [
        pt_paths.config_file("trading_config.conflict-app.json"),
        "keyring:coinbase:key_name", "keyring:coinbase:private_key",
        "keyring:binance:api_key", "keyring:binance:api_secret",
    ]


def test_an_import_with_from_still_writes_no_conflict_copy(tmp_path):
    """Conflict copies are for the legacy folders; ``--from`` is unchanged."""
    write(pt_paths.settings_file(), {"trading": {"mode": "paper"}, "mine": 1})
    other = write(str(tmp_path / "old-settings.json"), {"trading": {"mode": "live"}, "strategy": {}})
    report = pt_migrate.import_config_file(other)
    assert report.conflicts == [(other, pt_paths.settings_file())] and report.conflict_copies == {}
    assert not [n for n in os.listdir(pt_paths.config_dir()) if pt_migrate.CONFLICT in n]
    assert f"{other} was not copied; kept {pt_paths.settings_file()}" in report.conflict_lines()


# --- conflict copies are never overwritten ------------------------------------------------------


def test_a_taken_conflict_name_is_never_overwritten(legacy):
    """Earlier conflict copies with other content keep their content; the new
    one takes the next free name (-2, -3, ...)."""
    root_log = os.path.join(legacy["root"], "logs", "powertrader.log")  # fixture: "old log line"
    write(os.path.join(migrated_logs(), "powertrader.log"), "the new app's log\n")
    earlier = write(os.path.join(migrated_logs(), "powertrader.conflict-root.log"), "an earlier copy\n")
    write(pt_paths.settings_file(), {"trading": {"mode": "paper"}, "kept": True})
    taken = [
        write(pt_paths.config_file("pt_config.conflict-app.json"), {"earlier": 1}),
        write(pt_paths.config_file("pt_config.conflict-app-2.json"), {"earlier": 2}),
    ]
    before = {p: sha(p) for p in [earlier] + taken}

    report = pt_migrate.migrate()
    assert {p: sha(p) for p in before} == before
    second = os.path.join(migrated_logs(), "powertrader.conflict-root-2.log")
    assert read(second) == "old log line\n" and report.conflict_copies[root_log] == second
    third = pt_paths.config_file("pt_config.conflict-app-3.json")
    with open(third, encoding="utf-8") as f:
        assert json.load(f) == {"trading": {"mode": "paper"}, "coins": ["BTC"]}
    assert report.conflict_copies[os.path.join(legacy["app"], "pt_config.json")] == third


def test_a_database_conflict_copy_whose_name_is_taken_by_a_part_moves_on(legacy):
    """A stray -shm at the conflict name is never overwritten either."""
    write(migrated_db(), b"SQLite format 3\x00the new app's orders")
    stray = write(os.path.join(pt_paths.data_dir(), "order_management.conflict-app.db-shm"), b"stray")
    report = pt_migrate.migrate()
    db = legacy_db(legacy)
    copy = os.path.join(pt_paths.data_dir(), "order_management.conflict-app-2.db")
    assert report.conflict_copies == {db: copy, db + "-wal": copy + "-wal"}
    with open(stray, "rb") as f:
        assert f.read() == b"stray"
    assert not os.path.exists(copy + "-shm")


def test_an_earlier_conflict_copy_with_the_same_content_is_reused(legacy):
    """Nothing new: no second copy, nothing reported, and the legacy file is
    migrated with the earlier copy as its copy."""
    root_log = os.path.join(legacy["root"], "logs", "powertrader.log")
    write(os.path.join(migrated_logs(), "powertrader.log"), "the new app's log\n")
    same = write(os.path.join(migrated_logs(), "powertrader.conflict-root.log"), "old log line\n")
    stamp(same, -1000)
    report = pt_migrate.migrate()
    assert os.stat(same).st_mtime_ns == T - 1000 * 10**9
    assert not os.path.exists(os.path.join(migrated_logs(), "powertrader.conflict-root-2.log"))
    assert root_log not in report.conflict_copies and root_log not in {s for s, _ in report.conflicts}
    assert root_log in report.removable and state()["files"][root_log]["copy"] == [same]


# --- the report, the dialog and the CLI list both files ------------------------------------------


def conflict_scenario(legacy):
    """A legacy-vs-legacy log (root newer), and a pt_config.json already in
    the config folder. Returns the paths the listings must name."""
    logs = two_logs(legacy, ROOT)
    write(pt_paths.settings_file(), {"trading": {"mode": "paper"}, "kept": True})
    return {
        "log": os.path.join(migrated_logs(), "powertrader.log"),
        "log copy": os.path.join(migrated_logs(), "powertrader.conflict-app.log"),
        "root log": logs[ROOT],
        "app log": logs[APP],
        "config": pt_paths.settings_file(),
        "config copy": pt_paths.config_file("pt_config.conflict-app.json"),
        "legacy config": os.path.join(legacy["app"], "pt_config.json"),
    }


def test_the_report_lists_both_files_of_each_conflict(legacy):
    paths = conflict_scenario(legacy)
    report = pt_migrate.migrate()
    text = read(report.report_path)
    section = text.split("## Conflicts (nothing in the new location was replaced)")[1].split("\n## ")[0]
    assert f"* `{paths['log']}`: copy of the newer `{paths['root log']}` (in use)" in section
    assert f"  * `{paths['log copy']}`: copy of `{paths['app log']}`" in section
    assert f"* `{paths['config']}`: was already there, kept (in use)" in section
    assert f"  * `{paths['config copy']}`: copy of `{paths['legacy config']}`" in section
    assert "`<name>.conflict-app.<ext>`" in section and "`<name>.conflict-root.<ext>`" in section
    # both legacy files are offered for removal, and listed so in the report
    removable = text.split("## Old copies that can be removed")[1]
    for key in ("root log", "app log", "legacy config"):
        assert f"* `{paths[key]}`" in removable


def test_the_dialog_lists_both_files_of_each_conflict(legacy, tk_root):
    paths = conflict_scenario(legacy)
    report = pt_migrate.migrate()
    win = pt_migrate.show_migration_dialog(tk_root, report, messagebox=mock.MagicMock())
    try:
        text = label_text(win)
    finally:
        win.destroy()
    assert "conflict(s): nothing in the new location was replaced\n\nConflicts:\n" in text
    assert f"{paths['log']}: copy of the newer {paths['root log']} (in use)" in text
    assert f"    {paths['log copy']}: copy of {paths['app log']}" in text
    assert f"{paths['config']}: was already there, kept (in use)" in text
    assert f"    {paths['config copy']}: copy of {paths['legacy config']}" in text
    assert f"Full report: {report.report_path}" in text


def test_the_cli_lists_both_files_of_each_conflict(legacy, capsys):
    paths = conflict_scenario(legacy)
    assert pt_migrate.main([]) == 0
    out = capsys.readouterr().out
    for key in paths:
        assert paths[key] in out, key
    assert f"{paths['config']}: was already there, kept (in use)" in out


# --- idempotent ----------------------------------------------------------------------------------


def test_a_second_run_after_conflicts_does_nothing(legacy):
    """No new copies, no report, no dialog: with the record, after a legacy
    file is only touched, and with the record gone (every copy is found
    again, conflict copies by their content)."""
    conflict_scenario(legacy)
    two_databases(legacy, ROOT)
    first = pt_migrate.migrate()
    assert len(first.conflict_copies) == 4  # the log, the config, app's database and its -wal
    record = pt_paths.config_file(pt_migrate.STATE_FILE)
    stamps = {p: os.stat(p).st_mtime_ns for p in (record, first.report_path)}
    tree = user_tree()

    second = pt_migrate.migrate()
    assert not second.changed and second.conflicts == [] and second.conflict_copies == {}
    assert user_tree() == tree and {p: os.stat(p).st_mtime_ns for p in stamps} == stamps
    assert pt_migrate.run_startup_migration() is None
    assert sorted(second.removable) == sorted(first.removable)

    app_log = os.path.join(legacy["app"], "logs", "powertrader.log")
    stamp(app_log, 10**7)  # touched, same content: now the newest, but <name> is taken
    assert not pt_migrate.migrate().changed
    os.remove(record)
    again = pt_migrate.migrate()
    assert not again.changed and again.report_path is None
    after = user_tree()
    assert os.path.isfile(record) and after.keys() == tree.keys()
    assert {p: d for p, d in after.items() if p != record} == {p: d for p, d in tree.items() if p != record}
    assert sorted(again.removable) == sorted(first.removable)


@pytest.mark.parametrize("gone", ["conflict copy", "name"])
def test_the_next_run_looks_for_the_conflict_copy_a_file_was_saved_as(legacy, gone):
    """Each legacy file is offered for removal while its own copy is there:
    the older log while its conflict copy is, the newer one while <name> is
    (the hub may rotate its log). Nothing is copied again."""
    paths = two_logs(legacy, ROOT)
    pt_migrate.migrate()
    target = os.path.join(migrated_logs(), "powertrader.log")
    copy = os.path.join(migrated_logs(), "powertrader.conflict-app.log")
    os.remove(copy if gone == "conflict copy" else target)
    again = pt_migrate.migrate()
    assert not again.changed
    assert (paths[APP] in again.removable) == (gone == "name")
    assert (paths[ROOT] in again.removable) == (gone == "conflict copy")


# --- Remove old files: the same checks as item 3 ---------------------------------------------------


def test_old_files_saved_as_conflict_copies_are_removed_after_the_same_checks(legacy, capsys):
    paths = conflict_scenario(legacy)
    dbs = two_databases(legacy, ROOT)  # app's database and -wal become the conflict copy
    app_db, root_db = dbs[APP], dbs[ROOT]
    report = pt_migrate.migrate()
    conflicted = [paths["app log"], paths["legacy config"], app_db, app_db + "-wal"]
    assert set(conflicted) <= set(report.removable)
    in_use = user_tree()

    assert pt_migrate.main(["--remove-old-files", "--yes"]) == 0
    assert "not removed" not in capsys.readouterr().out
    for path in conflicted + [paths["root log"], root_db]:
        assert not os.path.exists(path), path
    assert user_tree() == in_use  # every file in the new location, conflict copies included, untouched


def test_a_conflicted_old_file_whose_copy_is_gone_or_that_changed_is_kept(legacy, capsys):
    paths = conflict_scenario(legacy)
    dbs = two_databases(legacy, ROOT)
    app_db, root_db = dbs[APP], dbs[ROOT]
    pt_migrate.migrate()
    db_copy = os.path.join(pt_paths.data_dir(), "order_management.conflict-app.db")
    with open(paths["app log"], "a", encoding="utf-8") as f:
        f.write("written by main after the migration\n")
    os.remove(paths["config copy"])
    os.remove(db_copy + "-wal")  # its -wal holds data that is now nowhere else
    kept = {p: sha(p) for p in (paths["app log"], paths["legacy config"], app_db, app_db + "-wal")}

    assert pt_migrate.main(["--remove-old-files", "--yes"]) == 1
    out = capsys.readouterr().out
    assert f"not removed: {paths['app log']}: {CHANGED}" in out
    assert f"not removed: {paths['legacy config']}: {NO_COPY}" in out
    assert f"not removed: {app_db}: {NO_COPY}" in out and f"not removed: {app_db + '-wal'}: {NO_COPY}" in out
    assert {p: sha(p) for p in kept} == kept
    assert not os.path.exists(paths["root log"]) and not os.path.exists(root_db)


def test_in_a_git_checkout_a_conflicted_pt_config_is_still_kept(legacy):
    os.mkdir(os.path.join(legacy["root"], ".git"))
    write(pt_paths.settings_file(), {"trading": {"mode": "paper"}, "kept": True})
    report = pt_migrate.migrate()
    source = os.path.join(legacy["app"], "pt_config.json")
    assert source in report.removable and state()["files"][source].get("keep") is True
    result = pt_migrate.remove_old_files([source], confirmed=True)
    assert result.kept == [(source, KEPT_FOR_BRANCHES)] and result.removed == []
    assert os.path.exists(source)


def test_keyring_conflicts_are_unchanged(legacy, memory_keyring):
    """A different value already in the keyring is kept; the legacy file is
    not offered for removal, and no conflict copy holds the value."""
    pt_secrets.set_secret("binance", "api_secret", "already-in-keyring")
    report = pt_migrate.migrate()
    trading = os.path.join(legacy["app"], "trading_config.json")
    assert (trading, "binance:api_secret") in report.secret_conflicts
    assert entries(memory_keyring)["binance:api_secret"] == "already-in-keyring"
    assert trading not in report.removable and trading not in report.conflict_copies
    line = f"binance:api_secret from {trading} was not stored; the keyring already holds a different value"
    assert line in report.conflict_lines()
    for folder, _, files in os.walk(pt_paths.config_dir()):
        for name in files:
            with open(os.path.join(folder, name), "rb") as f:
                assert b"bin-secret-legacy" not in f.read(), name


def test_a_config_that_is_the_same_file_as_the_one_in_use_is_left_alone(legacy):
    """The safety audit's probe: the config folder's trading_config.json is a
    hard link to app/trading_config.json (the same file). It was treated as a
    conflict, recorded as migrated and deleted by Remove old files; through a
    link from the new file to the legacy one, the config in use would then
    have been left dangling. It is now the new app's own file: skipped."""
    source = os.path.join(legacy["app"], "trading_config.json")
    target = pt_paths.config_file("trading_config.json")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    os.link(source, target)
    report = pt_migrate.migrate()
    assert source not in report.conflict_copies and (source, target) not in report.conflicts
    assert not os.path.exists(pt_paths.config_file("trading_config.conflict-app.json"))
    assert source not in report.removable

    result = pt_migrate.remove_old_files([source], confirmed=True)
    assert result.removed == [] and result.refused == [(source, pt_migrate.NOT_MIGRATED)]
    assert os.path.samefile(source, target)

    imported = pt_migrate.import_config_file(target)  # --from the file in use
    assert imported.errors == [(target, "is the config file in use; nothing to import")]
