"""FDS-108a review item 3: Remove old files checks every legacy file against
the migration record first (recorded as migrated, unchanged since, migrated
copy still there), keeps the settings other branches use in a git checkout,
and treats a SQLite database with its -wal/-shm files as one unit. The hub
dialog and ``--remove-old-files`` share one code path. Fixture legacy files
only (conftest points the legacy folders at temp dirs)."""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import sys
from contextlib import closing
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
from pt_migrate import CHANGED, IN_USE, KEPT_FOR_BRANCHES, NO_COPY, NOT_MIGRATED  # noqa: E402
from test_pt_migrate import legacy, no_credential_env, write  # noqa: E402,F401  (fixtures)


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def state():
    with open(pt_paths.config_file(pt_migrate.STATE_FILE), encoding="utf-8") as f:
        return json.load(f)


def legacy_db(legacy):
    return os.path.join(legacy["app"], "order_management.db")


def migrated_db():
    return os.path.join(pt_paths.data_dir(), "order_management.db")


def no_aside(folder):
    return not [n for n in os.listdir(folder) if n.endswith(pt_migrate.REMOVING_SUFFIX)]


def make_checkout(folder, git=True):
    """``<folder>/app`` with the legacy settings files, and a ``.git`` folder."""
    app = os.path.join(folder, "app")
    write(os.path.join(app, "pt_config.json"), {"trading": {"mode": "paper"}})
    write(os.path.join(app, "gui_settings.json"), {"coins": ["BTC"], "trade_start_level": 3})
    write(os.path.join(app, "trading_config.json"), {"user_region": "EU", "exchanges": []})
    if git:
        os.makedirs(os.path.join(folder, ".git"))
    return app


def run_from(monkeypatch, folder):
    """The program now runs from ``folder`` (its legacy folders are there)."""
    monkeypatch.setattr(pt_paths, "legacy_dir", lambda: os.path.join(folder, "app"))
    monkeypatch.setattr(pt_paths, "legacy_install_dir", lambda: folder)


def link_folder(target, link):
    """``link`` -> ``target``: a junction on Windows, a symlink elsewhere."""
    if os.name == "nt":
        import _winapi

        _winapi.CreateJunction(target, link)
    else:
        os.symlink(target, link, target_is_directory=True)


def drop_keep_flags():
    """Strip the keep flags from the record, so only the file's location decides."""
    data = state()
    for record in data["files"].values():
        record.pop("keep", None)
    write(pt_paths.config_file(pt_migrate.STATE_FILE), data)


def make_wal_database(db, work):
    """A real SQLite database in WAL mode as an old app that crashed (or still
    runs) leaves it: the table is in ``db``, one committed row only in its
    -wal. Built in ``work``, copied to ``db`` while the connection is open."""
    built = os.path.join(work, "built.db")
    with closing(sqlite3.connect(built)) as conn:
        conn.execute("pragma journal_mode=wal")
        conn.execute("pragma wal_autocheckpoint=0")
        conn.execute("create table t (x text)")
        conn.commit()
        conn.execute("pragma wal_checkpoint(truncate)")
        conn.execute("insert into t values ('only in the wal')")
        conn.commit()
        shutil.copy2(built, db)
        shutil.copy2(built + "-wal", db + "-wal")


def rows(db, work):
    """The rows of ``db`` (with its -wal, if any), read from copies made in a
    new folder under ``work``: opening the file itself would change it."""
    folder = os.path.join(work, f"read{len(os.listdir(work))}")
    os.makedirs(folder)
    shutil.copy2(db, os.path.join(folder, "x.db"))
    if os.path.exists(db + "-wal"):
        shutil.copy2(db + "-wal", os.path.join(folder, "x.db-wal"))
    with closing(sqlite3.connect(os.path.join(folder, "x.db"))) as conn:
        return [x for x, in conn.execute("select x from t").fetchall()]


@pytest.fixture
def read_only():
    """Marks files read-only; makes them (and any part renamed aside) writable
    again afterwards, so the temp folder can be cleaned up."""
    marked = []

    def mark(path):
        os.chmod(path, stat.S_IREAD)
        marked.append(path)

    yield mark
    for path in marked:
        for name in (path, path + pt_migrate.REMOVING_SUFFIX):
            if os.path.exists(name):
                os.chmod(name, stat.S_IREAD | stat.S_IWRITE)


not_as_root = pytest.mark.skipif(
    hasattr(os, "geteuid") and os.geteuid() == 0, reason="root may write to a read-only file"
)
READ_ONLY = "could not be removed (read-only)"


# --- the record -----------------------------------------------------------------------


def test_the_record_holds_the_hash_and_copy_of_every_removable_file(legacy):
    report = pt_migrate.migrate()
    files = state()["files"]
    for path in report.removable:
        assert files[path]["sha256"] == sha(path), path
        assert files[path]["copy"], path
    app = legacy["app"]
    assert files[os.path.join(app, "trading_config.json")]["copy"] == [
        pt_paths.trading_config_file(),
        "keyring:coinbase:key_name", "keyring:coinbase:private_key",
        "keyring:binance:api_key", "keyring:binance:api_secret",
    ]
    assert files[os.path.join(app, "r_key.txt")]["copy"] == [
        "keyring:robinhood:api_key", "keyring:robinhood:private_key",
    ]
    paper = os.path.join(app, "hub_data", "paper", "trader_status.json")
    assert files[paper]["copy"] == [os.path.join(pt_paths.hub_dir(), "paper", "trader_status.json")]
    # a database and its -wal are one unit; the copy of each part is the migrated .db
    db = legacy_db(legacy)
    assert [db, db + "-wal"] in state()["removable"]
    assert files[db + "-wal"]["copy"] == [migrated_db()]


# --- the review's data loss -------------------------------------------------------------


def test_remove_old_files_refuses_what_main_changed_after_the_migration(legacy, capsys):
    """Migrate, then main runs before --remove-old-files: it saves a setting,
    appends to a paper-trading file, and one migrated copy is gone. Before this
    fix all three legacy files were deleted from the list stored at migration."""
    app = legacy["app"]
    report = pt_migrate.migrate()
    gui = os.path.join(app, "gui_settings.json")
    paper = os.path.join(app, "hub_data", "paper", "trader_status.json")
    runner = os.path.join(app, "hub_data", "runner_ready.json")
    assert {gui, paper, runner} <= set(report.removable)

    write(gui, {"coins": ["BTC", "ETH", "SOL"], "main_neural_dir": app, "trade_start_level": 4})
    with open(paper, "a", encoding="utf-8") as f:
        f.write('\n{"account": 2}')
    os.remove(os.path.join(pt_paths.hub_dir(), "runner_ready.json"))
    refused = {p: sha(p) for p in (gui, paper, runner)}

    assert pt_migrate.main(["--remove-old-files", "--yes"]) == 1
    out = capsys.readouterr().out
    assert f"not removed: {gui}: changed since it was migrated" in out
    assert f"not removed: {paper}: changed since it was migrated" in out
    assert f"not removed: {runner}: no migrated copy" in out
    assert {p: sha(p) for p in refused} == refused  # still there, untouched
    # unchanged files whose migrated copy exists are removed
    for rel in ("pt_config.json", "trading_config.json", "exchange_config.json", "r_key.txt",
                "r_secret.txt", "memories_1hour.txt", os.path.join("ETH", "memories_1hour.txt"),
                os.path.join("hub_data", "candles", "BTCUSDT_1h.csv"),
                "order_management.db", "order_management.db-wal"):
        assert not os.path.exists(os.path.join(app, rel)), rel
    assert not os.path.exists(os.path.join(legacy["root"], "market_data.db"))
    assert os.path.exists(os.path.join(app, "ETH", "pt_trainer.py"))


def test_a_change_that_keeps_size_and_time_is_still_refused(legacy):
    pt_migrate.migrate()
    path = os.path.join(legacy["app"], "low_bound_prices.html")
    st = os.stat(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write("<p>2</p>")  # same size as "<p>1</p>"
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    result = pt_migrate.remove_old_files([path], confirmed=True)
    assert result.refused == [(path, CHANGED)] and result.removed == []
    assert os.path.exists(path)


def test_a_credential_file_whose_keyring_entry_is_gone_is_refused(legacy):
    pt_migrate.migrate()
    pt_secrets.delete_secret("robinhood", "private_key")
    r_key = os.path.join(legacy["app"], "r_key.txt")
    result = pt_migrate.remove_old_files([r_key], confirmed=True)
    assert result.refused == [(r_key, NO_COPY)] and os.path.exists(r_key)


# --- not in the record ---------------------------------------------------------------------


def test_files_not_in_the_record_are_refused(legacy):
    pt_secrets.set_secret("binance", "api_secret", "already-in-keyring")
    report = pt_migrate.migrate()
    conflicted = os.path.join(legacy["app"], "trading_config.json")  # not migrated: a keyring conflict
    code = os.path.join(legacy["app"], "ETH", "pt_trainer.py")
    assert conflicted not in report.removable
    assert conflicted not in pt_migrate.remove_old_files().removable
    result = pt_migrate.remove_old_files([conflicted, code], confirmed=True)
    assert result.refused == [(conflicted, NOT_MIGRATED), (code, NOT_MIGRATED)]
    assert result.removed == [] and os.path.exists(conflicted) and os.path.exists(code)


def test_a_record_without_hash_or_copy_is_refused(legacy):
    pt_migrate.migrate()
    path = pt_paths.config_file(pt_migrate.STATE_FILE)
    data = state()
    no_hash = os.path.join(legacy["app"], "memories_1hour.txt")
    no_copy = os.path.join(legacy["app"], "low_bound_prices.html")
    del data["files"][no_hash]["sha256"]
    del data["files"][no_copy]["copy"]
    write(path, data)
    result = pt_migrate.remove_old_files([no_hash, no_copy], confirmed=True)
    assert result.refused == [(no_hash, NOT_MIGRATED), (no_copy, NOT_MIGRATED)]
    # the record before this fix: a list of paths, no hash, no copy
    write(path, {"items": data["items"], "removable": [no_hash, no_copy]})
    assert pt_migrate.remove_old_files().removable == []
    result = pt_migrate.remove_old_files([no_hash, no_copy], confirmed=True)
    assert result.refused == [(no_hash, NOT_MIGRATED), (no_copy, NOT_MIGRATED)]
    assert os.path.exists(no_hash) and os.path.exists(no_copy)


def test_a_config_file_with_a_credential_that_could_not_be_moved_is_not_offered(isolated_user_dirs):
    path = write(
        os.path.join(isolated_user_dirs["legacy"], "trading_config.json"),
        {"exchanges": [{"exchange_type": "coinbase", "api_key": "organizations/o/apiKeys/k",
                        "api_secret": "secret", "passphrase": "old-pro-passphrase"}]},
    )
    report = pt_migrate.migrate()
    assert (path, "coinbase.passphrase: no keyring field for it, not moved") in report.errors
    assert path not in report.removable
    assert pt_migrate.remove_old_files([path], confirmed=True).refused == [(path, NOT_MIGRATED)]
    assert os.path.exists(path)


# --- git checkout ----------------------------------------------------------------------------


@pytest.mark.parametrize("git", ["folder", "file"])
def test_in_a_git_checkout_the_settings_other_branches_use_are_kept(legacy, capsys, git):
    git_path = os.path.join(legacy["root"], ".git")
    if git == "folder":
        os.mkdir(git_path)
    else:  # a worktree or submodule
        write(git_path, "gitdir: ../elsewhere/.git/worktrees/x\n")
    report = pt_migrate.migrate()
    settings = [os.path.join(legacy["app"], n) for n in ("pt_config.json", "gui_settings.json")]
    assert set(settings) <= set(report.removable)  # migrated, but kept
    with open(report.report_path, encoding="utf-8") as f:
        assert f"* `{settings[0]}` ({KEPT_FOR_BRANCHES})" in f.read()

    assert pt_migrate.main(["--remove-old-files", "--yes"]) == 0
    out = capsys.readouterr().out
    for path in settings:
        assert os.path.exists(path)
        assert f"not removed: {path}: {KEPT_FOR_BRANCHES}" in out
    assert not os.path.exists(os.path.join(legacy["app"], "trading_config.json"))
    result = pt_migrate.remove_old_files(settings, confirmed=True)  # asked for by name: still kept
    assert result.kept == [(p, KEPT_FOR_BRANCHES) for p in settings] and result.removed == []


@pytest.mark.parametrize("flag", [True, False], ids=["recorded", "not recorded"])
@pytest.mark.parametrize("other", ["checkout", "release folder"])
def test_the_git_rule_follows_the_file_not_the_program_that_runs(tmp_path, monkeypatch, capsys,
                                                                 other, flag):
    """The record is per user, so it can list another checkout's files. The hub
    migrated checkout A; Remove old files then runs from B (another clone or
    worktree, or a release folder without .git). Before this fix the rule
    looked at B, and A's settings were deleted. Without the keep flag recorded
    at migration, A's own .git decides."""
    a, b = str(tmp_path / "A"), str(tmp_path / "B")
    app_a = make_checkout(a)
    make_checkout(b, git=other == "checkout")
    run_from(monkeypatch, a)
    pt_migrate.migrate()
    settings = [os.path.join(app_a, n) for n in ("pt_config.json", "gui_settings.json")]
    assert [state()["files"][p].get("keep") for p in settings] == [True, True]
    if not flag:
        drop_keep_flags()

    run_from(monkeypatch, b)
    assert pt_migrate.main(["--remove-old-files", "--yes"]) == 0
    out = capsys.readouterr().out
    for path in settings:
        assert os.path.exists(path)
        assert f"not removed: {path}: {KEPT_FOR_BRANCHES}" in out
    assert not os.path.exists(os.path.join(app_a, "trading_config.json"))  # not a shared setting


def test_the_keep_flag_recorded_at_migration_is_honoured(legacy, tmp_path, monkeypatch):
    """Here the legacy folder is not inside the install root (the conftest
    layout), so only the flag recorded at migration, when the root had .git,
    can keep the settings once Remove old files runs from a release folder."""
    os.mkdir(os.path.join(legacy["root"], ".git"))
    pt_migrate.migrate()
    settings = [os.path.join(legacy["app"], n) for n in ("pt_config.json", "gui_settings.json")]
    files = state()["files"]
    assert [files[p].get("keep") for p in settings] == [True, True]
    assert "keep" not in files[os.path.join(legacy["app"], "trading_config.json")]
    run_from(monkeypatch, str(tmp_path / "release"))
    result = pt_migrate.remove_old_files(settings, confirmed=True)
    assert result.kept == [(p, KEPT_FOR_BRANCHES) for p in settings] and result.removed == []
    assert all(os.path.exists(p) for p in settings)


def test_the_git_rule_holds_through_another_spelling_of_the_checkout(tmp_path, monkeypatch, capsys):
    """``alias`` is a junction (a symlink off Windows) to the checkout ``real``.
    The hub migrated through ``alias``; Remove old files runs from ``real``.
    Before this fix the paths were compared as text, so both settings were
    deleted. The keep flags are dropped: the file's location alone decides."""
    real, alias = str(tmp_path / "real"), str(tmp_path / "alias")
    make_checkout(real)
    link_folder(real, alias)
    try:
        run_from(monkeypatch, alias)
        pt_migrate.migrate()
        drop_keep_flags()
        run_from(monkeypatch, real)
        assert pt_migrate.main(["--remove-old-files", "--yes"]) == 0
        out = capsys.readouterr().out
        for name in ("pt_config.json", "gui_settings.json"):
            assert os.path.exists(os.path.join(real, "app", name))
            assert f"not removed: {os.path.join(alias, 'app', name)}: {KEPT_FOR_BRANCHES}" in out
        assert not os.path.exists(os.path.join(real, "app", "trading_config.json"))
    finally:
        os.unlink(alias) if os.path.islink(alias) else os.rmdir(alias)
    assert os.path.isdir(os.path.join(real, ".git"))  # removing the junction left the checkout alone


# --- the folders PowerTrader uses now are never an old copy ------------------------------------


@pytest.mark.parametrize("home", ["install root", "app"])
def test_with_powertrader_home_in_the_checkout_its_own_files_are_never_old_copies(
        legacy, monkeypatch, capsys, home):
    """README allows ``POWERTRADER_HOME`` inside a checkout. At the install
    root its data/ and logs/ are also legacy locations (data/holdings.db,
    logs/); in app/ the same holds for app/data/ and app/logs/. Before this fix
    the new app's own database was recorded as its own copy, so Remove old
    files deleted it with its -wal, the only copies, and logs/ was copied into
    logs/legacy, one level deeper on every run."""
    base = legacy["root"] if home == "install root" else legacy["app"]
    monkeypatch.setenv("POWERTRADER_HOME", base)
    live = pt_paths.data_file("holdings.db")
    assert live == os.path.join(base, "data", "holdings.db")
    write(live, b"SQLite format 3\x00the new app's holdings")
    write(live + "-wal", b"the new app's wal")
    log = write(pt_paths.log_file("powertrader.log"), "the new app's log\n")
    own = {p: sha(p) for p in (live, live + "-wal", log)}

    runs = [pt_migrate.migrate(), pt_migrate.migrate()]
    for report in runs:
        assert not set(own) & set(report.removable)
        assert not set(own) & {s for s, _ in report.copied + report.conflicts}
    assert not os.path.exists(os.path.join(pt_paths.log_dir(), "legacy", "legacy"))

    assert pt_migrate.main(["--remove-old-files", "--yes"]) == 0
    assert {p: sha(p) for p in own} == own
    assert "not removed" not in capsys.readouterr().out
    # the old files outside the folders in use were migrated and removed as usual
    assert not os.path.exists(os.path.join(legacy["app"], "trading_config.json"))
    assert not os.path.exists(os.path.join(legacy["root"], "market_data.db"))


def test_a_recorded_file_in_a_folder_powertrader_uses_now_is_refused(legacy, monkeypatch):
    """A record made with another ``POWERTRADER_HOME`` (its config folder
    copied along): an old file that is now in the data folder in use is the
    new app's file, even though it is unchanged and its copy still exists."""
    pt_migrate.migrate()
    db = os.path.join(legacy["root"], "data", "holdings.db")
    assert db in pt_migrate.remove_old_files().removable
    record = pt_paths.config_file(pt_migrate.STATE_FILE)
    monkeypatch.setenv("POWERTRADER_HOME", legacy["root"])
    shutil.copy2(record, pt_paths.config_file(pt_migrate.STATE_FILE))
    result = pt_migrate.remove_old_files([db], confirmed=True)
    assert result.refused == [(db, IN_USE)] and result.removed == []
    assert os.path.exists(db)


@pytest.mark.parametrize("spelling", ["same", "junction"])
def test_a_record_whose_copy_is_the_file_itself_is_refused(legacy, tmp_path, spelling):
    """A record like the one this fix no longer writes: the copy of a file is
    the file itself (spelled the same, or through a junction)."""
    pt_migrate.migrate()
    path = os.path.join(legacy["app"], "memories_1hour.txt")
    copy = path
    if spelling == "junction":
        link_folder(legacy["app"], str(tmp_path / "alias"))
        copy = str(tmp_path / "alias" / "memories_1hour.txt")
    data = state()
    data["files"][path]["copy"] = [copy]
    write(pt_paths.config_file(pt_migrate.STATE_FILE), data)
    try:
        check = pt_migrate.remove_old_files([path])  # what the dialog and the CLI offer
        result = pt_migrate.remove_old_files([path], confirmed=True)
    finally:
        if spelling == "junction":
            alias = str(tmp_path / "alias")
            os.unlink(alias) if os.path.islink(alias) else os.rmdir(alias)
    assert check.removable == [] and check.refused == [(path, NO_COPY)]
    assert result.refused == [(path, NO_COPY)] and result.removed == []
    assert os.path.exists(path)


# --- a write between the check and the delete ---------------------------------------------------


def test_a_write_between_the_check_and_the_delete_keeps_the_file(legacy, monkeypatch):
    """An old hub still running from app/ rewrites a hub_data file right after
    Remove old files hashed it. Before this fix the file, with the new trade
    that was never migrated, was deleted. Now every part is hashed again once
    renamed aside (no writer can reach it by its name then), and put back."""
    pt_migrate.migrate()
    paper = os.path.join(legacy["app"], "hub_data", "paper", "trader_status.json")
    real_sha256 = pt_migrate._sha256
    written = []

    def sha256_then_write(path):
        digest = real_sha256(path)
        if path == paper and not written:
            with open(paper, "a", encoding="utf-8") as f:
                f.write('\n{"account": 2}')
            written.append(path)
        return digest

    monkeypatch.setattr(pt_migrate, "_sha256", sha256_then_write)
    result = pt_migrate.remove_old_files([paper], confirmed=True)
    assert written and result.removed == [] and result.refused == [(paper, CHANGED)]
    with open(paper, encoding="utf-8") as f:
        assert f.read().endswith('{"account": 2}')
    assert no_aside(os.path.dirname(paper))


def test_a_file_that_appears_at_an_old_name_during_the_delete_keeps_the_database(legacy, monkeypatch):
    """SQLite opens the database by its old name while its parts are renamed
    aside, which creates a new -shm: every part is put back."""
    pt_migrate.migrate()
    db = legacy_db(legacy)
    before = {p: sha(p) for p in (db, db + "-wal")}
    real_rename = os.rename

    def rename(src, dst):
        real_rename(src, dst)
        if src == db:
            write(db + "-shm", b"opened meanwhile")

    monkeypatch.setattr(pt_migrate.os, "rename", rename)
    result = pt_migrate.remove_old_files([db], confirmed=True)
    assert result.removed == [] and result.refused == [(db, CHANGED), (db + "-wal", CHANGED)]
    assert {p: sha(p) for p in before} == before and os.path.exists(db + "-shm")
    assert no_aside(legacy["app"])


def test_a_part_written_again_at_its_old_name_during_the_delete_keeps_the_database(legacy, monkeypatch):
    """A -wal of the unit is written again under its old name once renamed
    aside: nothing is deleted. The .db is put back; the old -wal cannot be put
    back over the new one, so it stays renamed aside, with its content."""
    pt_migrate.migrate()
    db = legacy_db(legacy)
    before = {p: sha(p) for p in (db, db + "-wal")}
    real_rename = os.rename

    def rename(src, dst):
        real_rename(src, dst)
        if src == db + "-wal":
            write(db + "-wal", b"a new wal")

    monkeypatch.setattr(pt_migrate.os, "rename", rename)
    result = pt_migrate.remove_old_files([db], confirmed=True)
    left = f"{CHANGED}, left as order_management.db-wal{pt_migrate.REMOVING_SUFFIX}"
    assert result.removed == [] and result.refused == [(db, CHANGED), (db + "-wal", left)]
    assert sha(db) == before[db]
    with open(db + "-wal", "rb") as f:
        assert f.read() == b"a new wal"
    assert sha(db + "-wal" + pt_migrate.REMOVING_SUFFIX) == before[db + "-wal"]


# --- a database with its -wal/-shm files is one unit -------------------------------------------


def test_an_identical_database_unit_is_not_copied_again_and_can_be_removed(legacy):
    db, target = legacy_db(legacy), migrated_db()
    for suffix in ("", "-wal"):
        shutil.copy2(db + suffix, target + suffix)
    report = pt_migrate.migrate()
    assert db not in {s for s, _ in report.conflicts}
    assert db not in {s for s, _ in report.copied}
    assert {db, db + "-wal"} <= set(report.removable)
    assert pt_migrate.remove_old_files([db], confirmed=True).removed == [db, db + "-wal"]


@pytest.mark.parametrize("target_wal", [b"another wal", None], ids=["different", "missing"])
def test_a_different_or_missing_wal_makes_the_database_a_conflict(legacy, target_wal):
    db, target = legacy_db(legacy), migrated_db()
    shutil.copy2(db, target)  # the .db alone is identical
    if target_wal is not None:
        write(target + "-wal", target_wal)
    report = pt_migrate.migrate()
    assert (db, target) in report.conflicts
    # saved whole as the conflict copy, so removable (FDS-108a review item 4)
    copy = os.path.join(pt_paths.data_dir(), "order_management.conflict-app.db")
    assert report.conflict_copies == {db: copy, db + "-wal": copy + "-wal"}
    assert sha(copy) == sha(db) and sha(copy + "-wal") == sha(db + "-wal")
    assert db in report.removable and db + "-wal" in report.removable
    if target_wal is None:
        assert not os.path.exists(target + "-wal")  # nothing copied next to the existing database
    else:
        with open(target + "-wal", "rb") as f:
            assert f.read() == target_wal  # never overwritten


def test_a_database_unit_is_copied_whole_or_not_at_all(legacy, monkeypatch):
    db, target = legacy_db(legacy), migrated_db()
    write(db + "-shm", b"shm")
    real_copy = shutil.copy2

    def copy_failing_on_shm(src, dst, *args, **kwargs):
        if src.endswith("-shm"):
            raise PermissionError(src)
        return real_copy(src, dst, *args, **kwargs)

    monkeypatch.setattr(pt_migrate.shutil, "copy2", copy_failing_on_shm)
    report = pt_migrate.migrate()
    assert (db, "copy failed (PermissionError)") in report.errors
    for suffix in ("", "-wal", "-shm"):
        assert not os.path.exists(target + suffix)  # parts copied before the failure are gone again
        assert db + suffix not in report.removable
    monkeypatch.setattr(pt_migrate.shutil, "copy2", real_copy)
    retry = pt_migrate.migrate()
    for suffix in ("", "-wal", "-shm"):
        assert sha(target + suffix) == sha(db + suffix)
        assert db + suffix in retry.removable


def test_a_database_whose_wal_changed_is_kept_whole(legacy):
    pt_migrate.migrate()
    db = legacy_db(legacy)
    with open(db + "-wal", "ab") as f:
        f.write(b" more")
    result = pt_migrate.remove_old_files(confirmed=True)
    assert (db, CHANGED) in result.refused and (db + "-wal", CHANGED) in result.refused
    assert os.path.exists(db) and os.path.exists(db + "-wal")


def test_a_wal_that_appeared_after_the_migration_keeps_the_database(legacy):
    pt_migrate.migrate()
    db = os.path.join(legacy["root"], "market_data.db")  # migrated without a -wal
    write(db + "-wal", b"written by main after the migration")
    result = pt_migrate.remove_old_files([db], confirmed=True)
    assert result.refused == [(db, CHANGED)] and result.removed == []
    assert os.path.exists(db) and os.path.exists(db + "-wal")


def test_a_database_part_that_cannot_be_removed_keeps_every_part(legacy, monkeypatch):
    pt_migrate.migrate()
    db = legacy_db(legacy)
    before = {p: sha(p) for p in (db, db + "-wal")}
    real_rename = os.rename

    def rename(src, dst):
        if src.endswith("-wal"):
            raise PermissionError(src)  # held open by another program
        return real_rename(src, dst)

    monkeypatch.setattr(pt_migrate.os, "rename", rename)
    result = pt_migrate.remove_old_files([db], confirmed=True)
    assert result.removed == []
    assert result.refused == [(p, "could not be removed (PermissionError)") for p in (db, db + "-wal")]
    assert {p: sha(p) for p in before} == before
    assert not [n for n in os.listdir(legacy["app"]) if n.endswith(pt_migrate.REMOVING_SUFFIX)]


@pytest.mark.skipif(os.name != "nt", reason="Windows refuses to rename a file another handle holds open")
def test_a_database_part_held_open_keeps_every_part_on_windows(legacy):
    pt_migrate.migrate()
    db = legacy_db(legacy)
    with open(db + "-wal", "rb"):
        result = pt_migrate.remove_old_files([db], confirmed=True)
    assert result.removed == []
    assert result.refused == [(p, "could not be removed (PermissionError)") for p in (db, db + "-wal")]
    assert os.path.exists(db) and os.path.exists(db + "-wal")
    assert not [n for n in os.listdir(legacy["app"]) if n.endswith(pt_migrate.REMOVING_SUFFIX)]


def test_the_migrated_database_is_the_copy_of_every_part(legacy):
    pt_migrate.migrate()
    db, target = legacy_db(legacy), migrated_db()
    # the new app opened and closed its database: SQLite merged the -wal into the .db
    os.remove(target + "-wal")
    write(target, b"SQLite format 3\x00orders, checkpointed")
    assert pt_migrate.remove_old_files([db]).removable == [db, db + "-wal"]
    os.remove(target)  # without the migrated database there is no copy
    result = pt_migrate.remove_old_files([db], confirmed=True)
    assert result.refused == [(db, NO_COPY), (db + "-wal", NO_COPY)]
    assert os.path.exists(db) and os.path.exists(db + "-wal")


# --- a -wal that SQLite never merged into the migrated database ---------------------------------


def test_a_wal_whose_copy_went_before_sqlite_merged_it_is_refused(legacy, tmp_path):
    """The review's probe: a committed row exists only in the legacy -wal.
    Something (a clean-up or sync tool) deletes the migrated -wal and -shm
    before the new app ever opens its database. Before this fix the legacy
    database and its -wal were removed, as the migrated .db still existed, and
    the row was lost everywhere."""
    db, target = legacy_db(legacy), migrated_db()
    work = str(tmp_path / "sqlite")
    os.makedirs(work)
    make_wal_database(db, work)
    pt_migrate.migrate()
    assert rows(target, work) == ["only in the wal"]
    os.remove(target + "-wal")
    assert rows(target, work) == []  # the migrated database alone does not hold the row

    check = pt_migrate.remove_old_files([db])
    result = pt_migrate.remove_old_files([db], confirmed=True)
    assert check.removable == [] and check.refused == [(db, NO_COPY), (db + "-wal", NO_COPY)]
    assert result.removed == [] and result.refused == [(db, NO_COPY), (db + "-wal", NO_COPY)]
    assert rows(db, work) == ["only in the wal"]  # still in the legacy files


def test_once_sqlite_merged_the_wal_into_the_migrated_database_both_parts_go(legacy, tmp_path):
    """The normal case: the new app opens and closes its database, SQLite
    merges the -wal into the .db (which changes) and deletes the -wal."""
    db, target = legacy_db(legacy), migrated_db()
    work = str(tmp_path / "sqlite")
    os.makedirs(work)
    make_wal_database(db, work)
    pt_migrate.migrate()
    copied = sha(target)
    with closing(sqlite3.connect(target)) as conn:  # the new app uses its database
        assert [x for x, in conn.execute("select x from t").fetchall()] == ["only in the wal"]
    assert not os.path.exists(target + "-wal") and sha(target) != copied

    result = pt_migrate.remove_old_files([db], confirmed=True)
    assert result.removed == [db, db + "-wal"] and result.refused == []
    assert rows(target, work) == ["only in the wal"]


def test_an_empty_wal_needs_no_copy_of_its_own(legacy):
    pt_migrate.migrate()  # with the fixture's -wal, which holds data
    db, target = legacy_db(legacy), migrated_db()
    os.remove(target + "-wal")
    assert pt_migrate.remove_old_files([db]).refused == [(db, NO_COPY), (db + "-wal", NO_COPY)]
    other = os.path.join(legacy["root"], "data", "automation.db")  # an empty -wal: nothing to lose
    write(other, b"SQLite format 3\x00automation")
    write(other + "-wal", b"")
    pt_migrate.migrate()
    os.remove(pt_paths.data_file("automation.db-wal"))
    result = pt_migrate.remove_old_files([other], confirmed=True)
    assert result.removed == [other, other + "-wal"] and result.refused == []


# --- a hot -journal (a rollback-mode database that crashed mid-commit) ---------------------------


ROWS = 2000


def make_hot_journal_database(db, work):
    """A real SQLite database in rollback-journal mode as an old app that
    crashed mid-commit leaves it: pages of an uncommitted update are already
    in ``db``, the committed ones only in its hot -journal. Built in ``work``,
    copied to ``db`` while the transaction is open."""
    built = os.path.join(work, "built.db")
    with closing(sqlite3.connect(built, isolation_level=None)) as conn:
        conn.execute("pragma journal_mode=delete")
        conn.execute("create table t (x text)")
        conn.execute("begin")
        conn.executemany("insert into t values (?)", [("a" * 200,)] * ROWS)
        conn.execute("commit")
        conn.execute("pragma cache_size=1")  # the update spills pages into the .db
        conn.execute("begin")
        conn.execute("update t set x = 'b' || substr(x, 2)")
        shutil.copy2(built, db)
        shutil.copy2(built + "-journal", db + "-journal")
        conn.execute("rollback")


def letters(db, work, sidecars=True):
    """``(first letter, count)`` of the rows of ``db``, read (with its sidecar
    files unless ``sidecars`` is False) from copies in a new folder under
    ``work``: opening the file itself would change it."""
    folder = os.path.join(work, f"read{len(os.listdir(work))}")
    os.makedirs(folder)
    shutil.copy2(db, os.path.join(folder, "x.db"))
    for side in ("-wal", "-shm", "-journal") if sidecars else ():
        if os.path.exists(db + side):
            shutil.copy2(db + side, os.path.join(folder, "x.db" + side))
    with closing(sqlite3.connect(os.path.join(folder, "x.db"))) as conn:
        return conn.execute("select substr(x, 1, 1), count(*) from t group by 1 order by 1").fetchall()


@pytest.fixture
def crashed(legacy, tmp_path):
    """A crashed rollback-mode database in the legacy folder; returns
    ``(legacy .db, migrated .db, work folder)``."""
    db = os.path.join(legacy["app"], "risk_management.db")
    work = str(tmp_path / "sqlite")
    os.makedirs(work)
    make_hot_journal_database(db, work)
    assert letters(db, work) == [("a", ROWS)]  # SQLite rolls the hot journal back
    assert letters(db, work, sidecars=False) != [("a", ROWS)]  # the .db alone is half-updated
    return db, pt_paths.data_file("risk_management.db"), work


def test_a_hot_journal_is_migrated_and_removed_with_its_database(crashed):
    """The review's probe: before -journal was part of the unit, the .db was
    copied without it (the migrated database showed the half-applied update
    as committed data) and Remove old files deleted the legacy .db, leaving
    the -journal, the only record of the committed rows, orphaned."""
    db, target, work = crashed
    pt_migrate.migrate()
    assert os.path.isfile(target + "-journal")
    assert letters(target, work) == [("a", ROWS)]
    with closing(sqlite3.connect(target)) as conn:  # the new app opens its database
        assert conn.execute("select count(*) from t where x like 'a%'").fetchone() == (ROWS,)
    assert not os.path.exists(target + "-journal")  # SQLite rolled it back into the .db

    result = pt_migrate.remove_old_files([db], confirmed=True)
    assert result.removed == [db, db + "-journal"] and result.refused == []
    assert not os.path.exists(db) and not os.path.exists(db + "-journal")
    assert letters(target, work) == [("a", ROWS)]


def test_a_hot_journal_whose_copy_went_before_sqlite_rolled_it_back_is_refused(crashed):
    db, target, work = crashed
    pt_migrate.migrate()
    os.remove(target + "-journal")  # before the new app ever opened its database
    assert letters(target, work) != [("a", ROWS)]  # the migrated .db alone is half-updated

    result = pt_migrate.remove_old_files([db], confirmed=True)
    assert result.removed == []
    assert result.refused == [(db, NO_COPY), (db + "-journal", NO_COPY)]
    assert letters(db, work) == [("a", ROWS)]  # still in the legacy files


# --- a part that cannot be deleted --------------------------------------------------------------


@not_as_root
@pytest.mark.parametrize("part", ["", "-wal"], ids=[".db", "-wal"])
def test_a_read_only_part_keeps_the_whole_database(legacy, read_only, part):
    """The review's probe: Windows renames a read-only file but will not delete
    it. Before this fix the other part was deleted, the read-only one was left
    as <name>.pt-removing, and both were reported as removed."""
    pt_migrate.migrate()
    db = legacy_db(legacy)
    before = {p: sha(p) for p in (db, db + "-wal")}
    read_only(db + part)
    check = pt_migrate.remove_old_files()
    assert db not in check.removable and (db, READ_ONLY) in check.refused  # not offered
    result = pt_migrate.remove_old_files([db], confirmed=True)
    assert result.removed == [] and result.refused == [(db, READ_ONLY), (db + "-wal", READ_ONLY)]
    assert {p: sha(p) for p in before} == before
    assert no_aside(legacy["app"])


@not_as_root
def test_a_read_only_credential_file_is_kept_and_the_cli_says_so(legacy, read_only, capsys):
    """The review's probe: read-only ``r_key.txt`` and ``trading_config.json``
    (plaintext keys). Before this fix the CLI said they were removed (exit 0)
    and left them as <name>.pt-removing, a name git did not ignore."""
    app = legacy["app"]
    pt_migrate.migrate()
    paths = [os.path.join(app, n) for n in ("r_key.txt", "trading_config.json")]
    before = {p: sha(p) for p in paths}
    for path in paths:
        read_only(path)
    assert pt_migrate.main(["--remove-old-files", "--yes"]) == 1
    out = capsys.readouterr().out
    for path in paths:
        assert f"not removed: {path}: {READ_ONLY}" in out
    assert {p: sha(p) for p in paths} == before
    assert no_aside(app)
    assert not os.path.exists(os.path.join(app, "r_secret.txt"))  # the others went


@pytest.mark.parametrize("failing", ["-wal", ""], ids=["first (-wal)", "last (.db)"])
def test_a_part_whose_delete_fails_after_the_rename_is_not_reported_as_removed(legacy, monkeypatch,
                                                                               failing):
    """``os.remove`` fails on a part already renamed aside (another program
    opened it meanwhile). Before this fix the unit was reported as removed and
    the part was left as <name>.pt-removing. Now it is put back and refused.
    The -wal is deleted first and the .db last, so a failure never leaves a
    -wal without its database; a part deleted before the failure is gone
    (every part passed every check) and is reported as removed."""
    pt_migrate.migrate()
    db = legacy_db(legacy)
    before = {p: sha(p) for p in (db, db + "-wal")}
    real_remove = os.remove

    def remove(path):
        if path == db + failing + pt_migrate.REMOVING_SUFFIX:
            raise PermissionError(path)
        return real_remove(path)

    monkeypatch.setattr(pt_migrate.os, "remove", remove)
    result = pt_migrate.remove_old_files([db], confirmed=True)
    reason = "could not be removed (PermissionError)"
    if failing == "-wal":
        assert result.removed == [] and result.refused == [(db, reason), (db + "-wal", reason)]
        assert {p: sha(p) for p in before} == before
    else:
        assert result.removed == [db + "-wal"] and result.refused == [(db, reason)]
        assert sha(db) == before[db] and not os.path.exists(db + "-wal")
    assert no_aside(legacy["app"])


def test_a_credential_file_whose_delete_fails_is_put_back_and_the_cli_says_so(legacy, monkeypatch,
                                                                              capsys):
    app = legacy["app"]
    pt_migrate.migrate()
    r_key = os.path.join(app, "r_key.txt")
    before = sha(r_key)
    real_remove = os.remove

    def remove(path):
        if path == r_key + pt_migrate.REMOVING_SUFFIX:
            raise PermissionError(path)
        return real_remove(path)

    monkeypatch.setattr(pt_migrate.os, "remove", remove)
    assert pt_migrate.main(["--remove-old-files", "--yes"]) == 1
    out = capsys.readouterr().out
    assert f"not removed: {r_key}: could not be removed (PermissionError)" in out
    assert sha(r_key) == before and no_aside(app)
    assert not os.path.exists(os.path.join(app, "r_secret.txt"))


def test_a_file_left_renamed_aside_earlier_is_never_overwritten(legacy):
    """A part an earlier removal could not put back keeps its old content as
    <name>.pt-removing. Renaming the file aside again would replace it (on
    macOS and Linux a rename overwrites), so the file is refused instead."""
    pt_migrate.migrate()
    path = os.path.join(legacy["app"], "memories_1hour.txt")
    left = write(path + pt_migrate.REMOVING_SUFFIX, "content an earlier removal could not put back")
    kept = sha(left)
    reason = f"could not be removed (memories_1hour.txt{pt_migrate.REMOVING_SUFFIX} is in the way)"
    assert (path, reason) in pt_migrate.remove_old_files().refused
    result = pt_migrate.remove_old_files([path], confirmed=True)
    assert result.removed == [] and result.refused == [(path, reason)]
    assert sha(left) == kept and os.path.exists(path)


def test_git_ignores_a_file_left_renamed_aside():
    with open(os.path.join(os.path.dirname(APP_DIR), ".gitignore"), encoding="utf-8") as f:
        assert "*" + pt_migrate.REMOVING_SUFFIX in {line.strip() for line in f}


# --- the hub dialog --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def tk_root():
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        pytest.skip(f"Tk not available: {exc}")
    root.withdraw()
    yield root
    root.destroy()


def test_the_dialog_uses_the_same_checks(legacy, tk_root):
    app = legacy["app"]
    report = pt_migrate.migrate()
    paper = os.path.join(app, "hub_data", "paper", "trader_status.json")
    runner = os.path.join(app, "hub_data", "runner_ready.json")
    with open(paper, "a", encoding="utf-8") as f:
        f.write('\n{"account": 2}')
    os.remove(os.path.join(pt_paths.hub_dir(), "runner_ready.json"))
    box = mock.MagicMock()
    box.askyesno.return_value = True
    win = pt_migrate.show_migration_dialog(tk_root, report, messagebox=box)
    try:
        with mock.patch.object(pt_migrate, "remove_old_files", wraps=pt_migrate.remove_old_files) as shared:
            win.remove_old_files()
    finally:
        win.destroy()
    assert shared.call_args_list[0] == mock.call()
    assert shared.call_args_list[1][1] == {"confirmed": True}
    question = box.askyesno.call_args[0][1]
    offered, not_removed = question.split("Not removed:")
    assert paper not in offered and runner not in offered
    assert f"{paper}: changed since it was migrated" in not_removed
    assert f"{runner}: no migrated copy" in not_removed
    done = box.showinfo.call_args[0][1]
    assert f"{paper}: changed since it was migrated" in done and f"{runner}: no migrated copy" in done
    assert os.path.exists(paper) and os.path.exists(runner)
    assert not os.path.exists(os.path.join(app, "r_key.txt"))


@not_as_root
def test_the_dialog_reports_what_it_could_not_delete(legacy, tk_root, read_only, monkeypatch):
    """A read-only key file is not offered; a database whose delete fails
    after the rename is put back and not counted as removed. Before this fix
    the dialog counted both as removed and only the log said otherwise."""
    app = legacy["app"]
    report = pt_migrate.migrate()
    r_key, db = os.path.join(app, "r_key.txt"), legacy_db(legacy)
    read_only(r_key)
    real_remove = os.remove

    def remove(path):
        if path == db + pt_migrate.REMOVING_SUFFIX:
            raise PermissionError(path)
        return real_remove(path)

    monkeypatch.setattr(pt_migrate.os, "remove", remove)
    box = mock.MagicMock()
    box.askyesno.return_value = True
    win = pt_migrate.show_migration_dialog(tk_root, report, messagebox=box)
    try:
        win.remove_old_files()
    finally:
        win.destroy()
    question = box.askyesno.call_args[0][1]
    offered, not_removed = question.split("Not removed:")
    assert r_key not in offered.splitlines() and f"{r_key}: {READ_ONLY}" in not_removed
    count =int(re.search(r"Delete these (\d+) old file", question).group(1))
    done = box.showinfo.call_args[0][1]
    assert f"Removed {count - 1} file(s)." in done  # the -wal went, its database did not
    assert f"{db}: could not be removed (PermissionError)" in done and f"{r_key}: {READ_ONLY}" in done
    assert os.path.exists(db) and os.path.exists(r_key) and not os.path.exists(db + "-wal")
    assert no_aside(app)


# --- links and junctions (safety audit) ---------------------------------------------------------


def outside_folder(tmp_path, name):
    """A folder outside every legacy folder, holding one file ``name``."""
    folder = tmp_path / "outside"
    folder.mkdir()
    path = folder / name
    path.write_text("shared, not PowerTrader's", encoding="utf-8")
    return str(folder), str(path)


def copied_sources(report):
    return {os.path.normcase(source) for source, _ in report.copied}


def test_a_folder_linked_into_a_legacy_folder_is_neither_copied_nor_removed(legacy, tmp_path):
    """The safety audit's probe: a junction in app/hub_data pointing at a folder
    outside every legacy folder. Its files were copied, recorded as migrated,
    and then deleted by Remove old files (and the junction pruned)."""
    outside, shared = outside_folder(tmp_path, "shared_state.json")
    link = os.path.join(legacy["app"], "hub_data", "shared")
    link_folder(outside, link)
    report = pt_migrate.migrate()
    assert os.path.normcase(os.path.join(link, "shared_state.json")) not in copied_sources(report)
    assert not os.path.exists(os.path.join(pt_paths.hub_dir(), "shared"))

    result = pt_migrate.remove_old_files(confirmed=True)
    assert result.removed and not [p for p in result.removed if p.startswith(link)]
    assert os.path.isfile(shared) and os.path.isdir(link)


def test_a_linked_logs_folder_in_the_install_root_is_left_alone(legacy, tmp_path):
    """The same for a whole legacy folder: the install root's logs/ is a
    junction to a folder elsewhere."""
    logs = os.path.join(legacy["root"], "logs")
    outside = str(tmp_path / "outside_logs")
    shutil.move(logs, outside)
    link_folder(outside, logs)
    report = pt_migrate.migrate()
    log = os.path.join(logs, "powertrader.log")
    assert os.path.normcase(log) not in copied_sources(report)
    assert log not in report.removable

    pt_migrate.remove_old_files(confirmed=True)
    assert os.path.isfile(os.path.join(outside, "powertrader.log")) and os.path.isdir(logs)


def test_a_folder_replaced_by_a_link_after_the_migration_is_refused(legacy, tmp_path):
    """Migrated as a real folder, then moved elsewhere and linked back: the
    recorded files still hash the same through the link, but they no longer
    live in the legacy folder, so they are refused."""
    pt_migrate.migrate()
    paper = os.path.join(legacy["app"], "hub_data", "paper")
    moved = str(tmp_path / "moved_paper")
    shutil.move(paper, moved)
    link_folder(moved, paper)
    status = os.path.join(paper, "trader_status.json")

    result = pt_migrate.remove_old_files(confirmed=True)
    assert (status, pt_migrate.LINKED) in result.refused and status not in result.removed
    assert os.path.isfile(os.path.join(moved, "trader_status.json")) and os.path.isdir(paper)

