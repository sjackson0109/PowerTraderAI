"""FDS-SIG-001 section 16, items 4 to 10 and 12: refusals, rows and floors, verdicts
checked twice, no pooling, verdict lines, confirmation, evidence, nothing else changed.

The refusals run against a throwaway git repository (local git only); everything else
on synthetic rows. Nothing touches the network.
"""

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(TESTS_DIR)
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from pt_exchange_abstraction import ListedMarket, MarketListing  # noqa: E402
from signal_audit import engine, ranking  # noqa: E402
from signal_audit import registration as reg  # noqa: E402
from signal_audit import report as rp  # noqa: E402
from signal_audit import stats as st  # noqa: E402
from signal_audit.pairs import RowPairs  # noqa: E402

UTC = timezone.utc


# --- a throwaway repository --------------------------------------------------------------


def _git(repo, *args, when=None):
    env = dict(os.environ)
    if when is not None:
        stamp = when.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        env.update(GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout


def _write(repo, rel, text):
    path = os.path.join(str(repo), rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _git(r, "config", "user.email", "audit@example.invalid")
    _git(r, "config", "user.name", "audit test")
    _git(r, "config", "commit.gpgsign", "false")
    _write(r, "app/code.py", "x = 1\n")
    _write(r, "docs/dev/run_signal_audit.py", "# the script\n")
    _git(r, "add", "-A")
    _git(r, "commit", "-q", "-m", "code", when=datetime(2026, 11, 1, tzinfo=UTC))
    return r


REG = "docs/dev/sig-audit/round-1/registration.json"
FREEZE = "docs/dev/sig-audit/round-1/freeze.json"


def registered(
    repo,
    start="2026-11-08T00:00:00Z",
    end="2027-02-01T00:00:00Z",
    when=datetime(2026, 11, 6, 12, tzinfo=UTC),
    candidates=None,
    freeze=True,
):
    record = {
        "window": {"start": start, "end": end},
        "candidates": candidates or [{"key": "SIG-A"}],
    }
    _write(repo, REG, json.dumps(record, indent=1) + "\n")
    _git(repo, "add", REG)
    _git(repo, "commit", "-q", "-m", "registration", when=when)
    if freeze:
        _write(repo, FREEZE, json.dumps({"round": 1}) + "\n")
        _git(repo, "add", FREEZE)
        _git(repo, "commit", "-q", "-m", "freeze", when=when + timedelta(hours=1))
    return record


AFTER = datetime(2027, 3, 1, tzinfo=UTC)


def test_a_run_with_everything_in_order_is_not_refused(repo):
    registered(repo)
    state = reg.check_can_run(str(repo), 1, now=AFTER)
    assert (
        state.registration_commit
        == _git(repo, "log", "-1", "--format=%H", "--", REG).strip()
    )
    assert (
        state.freeze_commit
        == _git(repo, "log", "-1", "--format=%H", "--", FREEZE).strip()
    )
    assert state.frozen_files_dirty == [] and len(state.registration_sha256) == 64
    assert set(state.to_dict()) >= {
        "head",
        "registration_sha256",
        "python",
        "powertrader_home",
        "frozen_files_changed_since_freeze",
    }


def _refused(repo, match, caplog, now=AFTER):
    with caplog.at_level(logging.ERROR, logger="signal_audit"):
        with pytest.raises(reg.Refused, match=match):
            reg.check_can_run(str(repo), 1, now=now)
    assert any("refused" in r.getMessage() for r in caplog.records)


def test_refused_without_a_registration_file(repo, caplog):
    _refused(repo, "no registration file", caplog)


def test_refused_when_the_registration_is_not_committed(repo, caplog):
    _write(
        repo,
        REG,
        json.dumps(
            {"window": {"start": "2026-11-08T00:00:00Z", "end": "2027-02-01T00:00:00Z"}}
        ),
    )
    _refused(repo, "not committed", caplog)


def test_refused_when_the_registration_changed_since_its_commit(repo, caplog):
    registered(repo)
    with open(os.path.join(str(repo), REG), "a", encoding="utf-8") as f:
        f.write(" ")
    _refused(repo, "uncommitted changes", caplog)


def test_refused_when_the_registration_commit_is_not_before_the_window(repo, caplog):
    registered(
        repo, start="2026-11-08T00:00:00Z", when=datetime(2026, 11, 8, 3, tzinfo=UTC)
    )
    _refused(repo, "not dated before the window start", caplog)


def test_refused_when_the_window_starts_before_the_earliest_start(repo, caplog):
    # registered at 12:00 on 6 November: the earliest start is 00:00 on 7 November
    registered(
        repo, start="2026-11-06T13:00:00Z", when=datetime(2026, 11, 6, 12, tzinfo=UTC)
    )
    _refused(repo, "before the earliest start", caplog)


def test_refused_when_a_registration_commit_touches_a_frozen_path(repo, caplog):
    _write(
        repo,
        REG,
        json.dumps(
            {"window": {"start": "2026-11-08T00:00:00Z", "end": "2027-02-01T00:00:00Z"}}
        ),
    )
    _write(repo, "app/code.py", "x = 2\n")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "both", when=datetime(2026, 11, 6, tzinfo=UTC))
    _write(repo, FREEZE, "{}\n")
    _git(repo, "add", FREEZE)
    _git(
        repo, "commit", "-q", "-m", "freeze", when=datetime(2026, 11, 6, 1, tzinfo=UTC)
    )
    _refused(repo, "changed the registration and frozen paths", caplog)


def test_refused_when_a_frozen_path_is_dirty(repo, caplog):
    registered(repo)
    _write(repo, "app/code.py", "x = 3\n")
    _refused(repo, "frozen paths have uncommitted changes", caplog)
    _git(repo, "checkout", "--", "app/code.py")
    _write(repo, "app/new.py", "y = 1\n")  # an untracked file in a frozen path
    _refused(repo, "frozen paths have uncommitted changes", caplog)


def test_refused_without_a_freeze_or_with_the_registration_after_it(repo, caplog):
    registered(repo, freeze=False)
    _refused(repo, "no code freeze", caplog)
    # a freeze committed before the registration: the registration is not its ancestor
    _git(repo, "checkout", "-q", "-b", "other", "HEAD~1")
    _write(repo, FREEZE, "{}\n")
    _git(repo, "add", FREEZE)
    _git(
        repo, "commit", "-q", "-m", "freeze", when=datetime(2026, 11, 6, 13, tzinfo=UTC)
    )
    _git(repo, "checkout", "-q", "-")
    _git(repo, "merge", "-q", "--no-ff", "-m", "merge", "other")
    _refused(repo, "not an ancestor of the freeze commit", caplog)


def test_refused_before_the_window_ends(repo, caplog):
    registered(repo)
    _refused(
        repo, "no scoring before then", caplog, now=datetime(2027, 1, 31, tzinfo=UTC)
    )


def test_refused_when_a_trained_model_ends_after_the_window_start(repo, caplog):
    registered(
        repo,
        candidates=[
            {"key": "STRAT-003", "model": {"train_end": "2026-11-09T00:00:00Z"}}
        ],
    )
    _refused(repo, "train_end", caplog)


def _commit(repo, rel, text, when=datetime(2026, 11, 7, tzinfo=UTC), msg="change"):
    _write(repo, rel, text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg, when=when)


def test_refused_when_frozen_code_changed_in_a_commit_after_the_freeze(repo, caplog):
    """The review's case: a committed change to frozen code after the freeze was only
    listed, and the round would have been scored with other code."""
    registered(repo)
    _commit(repo, "app/code.py", "x = 2  # another rule\n")
    _refused(
        repo, r"frozen paths changed since the freeze commit .*app/code.py", caplog
    )
    # a note alone does not allow it: before results there is nothing to supersede
    with pytest.raises(reg.Refused, match="no results exist"):
        reg.check_can_run(str(repo), 1, now=AFTER, supersede="a fix")
    # after results, only with the defect fix's note
    with pytest.raises(reg.Refused, match="needs --supersede"):
        reg.check_can_run(str(repo), 1, now=AFTER, results_exist=True)
    with pytest.raises(reg.Refused, match="needs --supersede"):
        reg.check_can_run(str(repo), 1, now=AFTER, supersede="  ", results_exist=True)
    state = reg.check_can_run(
        str(repo), 1, now=AFTER, supersede=" the CMF sign ", results_exist=True
    )
    assert state.frozen_files_changed_since_freeze == ["app/code.py"]
    assert state.supersede == "the CMF sign"
    assert state.to_dict()["supersede"] == "the CMF sign"


def test_a_new_frozen_file_after_the_freeze_is_refused_too(repo, caplog):
    registered(repo)
    _commit(repo, "docs/dev/run_signal_audit.py", "# another script\n")
    _refused(repo, "run_signal_audit.py", caplog)
    _git(repo, "reset", "-q", "--hard", "HEAD~1")
    _commit(repo, "app/signal_audit/extra.py", "y = 1\n")
    _refused(repo, "extra.py", caplog)


def test_code_changed_before_the_freeze_is_the_frozen_code(repo):
    """Between the registration and the freeze the code may change (step 2 freezes
    it as it then is): the freeze commit's code is what is run."""
    registered(repo, freeze=False)
    before = datetime(2026, 11, 6, 12, 30, tzinfo=UTC)
    _commit(repo, "app/code.py", "x = 5\n", when=before)
    _commit(repo, FREEZE, "{}\n", when=before + timedelta(minutes=30), msg="freeze")
    state = reg.check_can_run(str(repo), 1, now=AFTER)
    assert state.frozen_files_changed_since_freeze == [] and state.supersede is None


def test_uncommitted_frozen_changes_are_refused_before_and_after_the_freeze(
    repo, caplog
):
    registered(repo, freeze=False)
    _write(repo, "app/code.py", "x = 6\n")  # uncommitted when the freeze is committed
    _write(repo, FREEZE, "{}\n")
    _git(repo, "add", FREEZE)
    _git(
        repo, "commit", "-q", "-m", "freeze", when=datetime(2026, 11, 6, 13, tzinfo=UTC)
    )
    _refused(repo, "frozen paths have uncommitted changes", caplog)
    _git(repo, "checkout", "--", "app/code.py")
    assert reg.check_can_run(str(repo), 1, now=AFTER).frozen_files_dirty == []
    _write(repo, "app/code.py", "x = 7\n")  # uncommitted after the freeze
    _refused(repo, "frozen paths have uncommitted changes", caplog)
    # with results and a note: still refused (an uncommitted fix is never run)
    with pytest.raises(reg.Refused, match="uncommitted"):
        reg.check_can_run(
            str(repo), 1, now=AFTER, supersede="a fix", results_exist=True
        )


def test_a_change_reverted_or_outside_the_frozen_paths_is_not_refused(repo):
    registered(repo)
    _commit(repo, "app/code.py", "x = 2\n")
    _commit(repo, "app/code.py", "x = 1\n", when=datetime(2026, 11, 8, tzinfo=UTC))
    _commit(
        repo, "docs/dev/notes.md", "a note\n", when=datetime(2026, 11, 9, tzinfo=UTC)
    )
    state = reg.check_can_run(str(repo), 1, now=AFTER)
    assert state.frozen_files_changed_since_freeze == []  # the frozen code, as frozen


def test_refused_when_the_freeze_record_changes_after_its_freeze_commit(repo, caplog):
    """The review's case: committing freeze.json again moved the freeze point past a
    code change, which then was not even listed."""
    registered(repo)
    _commit(repo, "app/code.py", "x = 2\n")
    again = datetime(2026, 11, 8, tzinfo=UTC)
    _commit(repo, FREEZE, '{"round": 1, "again": true}\n', when=again)
    _refused(repo, "changed after its freeze commit", caplog)
    _git(repo, "reset", "-q", "--hard", "HEAD~2")
    _write(repo, FREEZE, '{"round": 1, "edited": true}\n')
    _refused(repo, "freeze record .* has uncommitted changes", caplog)


# --- a defect before results: cancellation (owner D9) ---------------------------------

CANCEL = "docs/dev/sig-audit/round-1/cancellation.json"


def _cancel(repo, defect="SIG-A's CMF sign is inverted", when=None):
    when = when or datetime(2026, 11, 7, 9, tzinfo=UTC)
    rec = reg.cancellation_record(str(repo), 1, defect, now=when)
    _commit(repo, CANCEL, json.dumps(rec, indent=1) + "\n", when=when, msg="cancel")
    return rec


def test_a_defect_before_results_cancels_the_registration(repo, caplog):
    """D9: never run frozen code known to be defective to make a result to supersede:
    the registration is cancelled, with an auditable record, and never run."""
    registered(repo)
    reg_commit = _git(repo, "log", "-1", "--format=%H", "--", REG).strip()
    freeze_commit = _git(repo, "log", "-1", "--format=%H", "--", FREEZE).strip()
    # before the window starts
    before = reg.cancellation_record(
        str(repo), 1, "a defect", now=datetime(2026, 11, 7, tzinfo=UTC)
    )
    assert before["window_started"] is False and before["window_ended"] is False
    assert before["registration"]["commit"] == reg_commit
    assert before["registration"]["sha256"] == reg.file_sha256(os.path.join(repo, REG))
    assert before["freeze_commit"] == freeze_commit and before["results"] is None
    # after it started (the record says so; the cancellation is the same)
    during = reg.cancellation_record(
        str(repo), 1, "a defect", now=datetime(2026, 12, 1, tzinfo=UTC)
    )
    assert during["window_started"] is True and during["window_ended"] is False
    # the code changed to fix it is recorded too
    _commit(repo, "app/code.py", "x = 2  # the fix\n")
    rec = reg.cancellation_record(
        str(repo), 1, "a defect", now=datetime(2026, 11, 7, 12, tzinfo=UTC)
    )
    assert rec["frozen_files_changed_since_freeze"] == ["app/code.py"]
    # written, even before it is committed, the round is never run
    _write(repo, CANCEL, json.dumps(rec) + "\n")
    _refused(repo, "registration was cancelled \\(a defect\\)", caplog)
    _git(repo, "add", CANCEL)
    _git(
        repo, "commit", "-q", "-m", "cancel", when=datetime(2026, 11, 7, 13, tzinfo=UTC)
    )
    _refused(repo, "never run", caplog)
    with pytest.raises(reg.Refused, match="never run"):
        reg.check_can_run(
            str(repo), 1, now=AFTER, supersede="the fix", results_exist=True
        )


def test_a_cancellation_needs_a_defect_and_no_results(repo):
    with pytest.raises(reg.Refused, match="no committed registration"):
        reg.cancellation_record(str(repo), 1, "a defect")
    registered(repo)
    with pytest.raises(reg.Refused, match="states the defect"):
        reg.cancellation_record(str(repo), 1, "  ")
    _write(repo, "docs/dev/sig-audit/round-1/results.json", "{}\n")
    with pytest.raises(reg.Refused, match="corrected through --supersede"):
        reg.cancellation_record(str(repo), 1, "a defect")
    os.remove(os.path.join(repo, "docs/dev/sig-audit/round-1/results.json"))
    _cancel(repo)
    with pytest.raises(reg.Refused, match="already cancelled"):
        reg.cancellation_record(str(repo), 1, "another")


def _register(repo, n, record, when, freeze_when=None):
    rel = f"docs/dev/sig-audit/round-{n}"
    _commit(
        repo, f"{rel}/registration.json", json.dumps(record, indent=1) + "\n", when=when
    )
    _commit(
        repo,
        f"{rel}/freeze.json",
        json.dumps({"round": n}) + "\n",
        when=freeze_when or when + timedelta(hours=1),
        msg="freeze",
    )


def test_a_replacement_registration_names_its_committed_cancellation(repo, caplog):
    registered(repo)
    _cancel(repo)
    replaces = reg.replacement_record(str(repo), 1)
    assert replaces["round"] == 1 and replaces["window_started_when_cancelled"] is False
    assert replaces["cancelled_window"]["start"] == "2026-11-08T00:00:00Z"
    record = {
        "window": {"start": "2026-11-10T00:00:00Z", "end": "2027-03-01T00:00:00Z"},
        "candidates": [{"key": "SIG-A"}],
        "replaces": replaces,
    }
    _register(repo, 2, record, when=datetime(2026, 11, 8, 12, tzinfo=UTC))
    after = datetime(2027, 4, 1, tzinfo=UTC)
    state = reg.check_can_run(str(repo), 2, now=after)
    assert state.registration_commit
    # the cancelled round still never runs
    with pytest.raises(reg.Refused, match="cancelled"):
        reg.check_can_run(str(repo), 1, now=after)
    # a changed cancellation record no longer matches what round 2 recorded
    _commit(
        repo,
        CANCEL,
        '{"defect": "rewritten", "registration": {"window": {}}}\n',
        when=datetime(2026, 11, 9, tzinfo=UTC),
    )
    with caplog.at_level(logging.ERROR, logger="signal_audit"):
        with pytest.raises(reg.Refused, match="differs from the SHA-256"):
            reg.check_can_run(str(repo), 2, now=after)


def test_a_replacement_comes_after_its_cancellation_with_a_future_window(repo):
    registered(repo)
    rec = reg.cancellation_record(
        str(repo), 1, "a defect", now=datetime(2026, 12, 1, tzinfo=UTC)
    )
    _write(repo, CANCEL, json.dumps(rec) + "\n")
    _git(repo, "add", CANCEL)
    # the cancellation and the replacement in one commit: not committed before it
    when = datetime(2026, 12, 1, 12, tzinfo=UTC)
    _git(repo, "commit", "-q", "-m", "cancel", when=when)
    replaces = reg.replacement_record(str(repo), 1)
    assert replaces["window_started_when_cancelled"] is True
    _git(repo, "reset", "-q", "--soft", "HEAD~1")
    record = {
        "window": {"start": "2026-12-03T00:00:00Z", "end": "2027-06-01T00:00:00Z"},
        "candidates": [{"key": "SIG-A"}],
        "replaces": replaces,
    }
    _write(
        repo, "docs/dev/sig-audit/round-2/registration.json", json.dumps(record) + "\n"
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "cancel and replace", when=when)
    _commit(
        repo,
        "docs/dev/sig-audit/round-2/freeze.json",
        "{}\n",
        when=when + timedelta(hours=1),
        msg="freeze",
    )
    after = datetime(2027, 7, 1, tzinfo=UTC)
    with pytest.raises(reg.Refused, match="not committed before"):
        reg.check_can_run(str(repo), 2, now=after)
    # a replacement whose window had already started when registered: refused as any
    # registration is (section 11); the window starts after its own registration
    _git(repo, "reset", "-q", "--hard", "HEAD~2")
    _commit(repo, CANCEL, json.dumps(rec) + "\n", when=when, msg="cancel")
    late = dict(record, replaces=reg.replacement_record(str(repo), 1))
    late["window"] = {"start": "2026-12-01T00:00:00Z", "end": "2027-06-01T00:00:00Z"}
    _register(repo, 2, late, when=when + timedelta(hours=2))
    with pytest.raises(reg.Refused, match="not dated before the window start"):
        reg.check_can_run(str(repo), 2, now=after)
    # and a round cannot replace itself
    selfish = dict(record, replaces=dict(record["replaces"], round=3))
    _register(repo, 3, selfish, when=when + timedelta(hours=3))
    with pytest.raises(reg.Refused, match="cannot replace itself"):
        reg.check_can_run(str(repo), 3, now=after)


# --- a defect after results: supersession keeps the earlier results ---------------------


def test_supersede_keeps_the_earlier_results_with_their_provenance(tmp_path):
    folder = tmp_path / "round-1"
    report = tmp_path / "SIG-AUDIT-REPORT-round-1.md"
    assert reg.supersede_results(str(folder), None) == []  # no results yet
    folder.mkdir()
    (folder / "results.json").write_text(json.dumps({"state": {"head": "abc1234def"}}))
    (folder / "series").mkdir()
    (folder / "series" / "SIG-A_x_BTC_1h.csv").write_text("open_time_utc\n")
    report.write_text("# report one\n")
    shas = {
        "results.json": reg.file_sha256(str(folder / "results.json")),
        "series/SIG-A_x_BTC_1h.csv": reg.file_sha256(
            str(folder / "series" / "SIG-A_x_BTC_1h.csv")
        ),
        "report.md": reg.file_sha256(str(report)),
    }
    with pytest.raises(reg.Refused, match="needs --supersede"):
        reg.supersede_results(str(folder), " ", str(report))
    earlier = reg.supersede_results(str(folder), " the CMF sign ", str(report))
    kept = folder / "superseded" / "1-abc1234"
    assert [e["note"] for e in earlier] == ["the CMF sign"]
    assert earlier[0]["commit"] == "abc1234def"
    assert not (folder / "results.json").exists() and not (folder / "series").exists()
    assert (kept / "results.json").exists() and (kept / "report.md").exists()
    assert (kept / "series" / "SIG-A_x_BTC_1h.csv").exists()
    note = json.loads((kept / "note.json").read_text())
    assert note["files_sha256"] == shas and note["results_commit"] == "abc1234def"
    assert reg.has_results(str(folder))  # the earlier results still count
    # a second fix keeps both, oldest first
    (folder / "results.json").write_text(json.dumps({"state": {"head": "fff0000aaa"}}))
    both = reg.supersede_results(str(folder), "a second fix", str(report))
    assert [e["note"] for e in both] == ["the CMF sign", "a second fix"]
    assert (folder / "superseded" / "2-fff0000").is_dir()


def test_the_run_records_the_numerical_packages(repo):
    registered(repo)
    state = reg.check_can_run(str(repo), 1, now=AFTER)
    import numpy
    import scipy

    assert state.packages["numpy"] == numpy.__version__
    assert state.packages["scipy"] == scipy.__version__
    assert set(state.to_dict()["packages"]) == {"numpy", "scipy", "pandas"}


# --- a long round runs from its own worktree (follow-up review, item 4) -----------------


def test_a_round_runs_from_its_research_worktree_while_main_moves_on(repo, tmp_path):
    """The registration and freeze are committed on a research branch, and the run
    happens in a worktree of it: development goes on in the main checkout, and every
    guarantee holds where the run happens."""
    registered(repo)
    freeze_commit = _git(repo, "log", "-1", "--format=%H", "--", FREEZE).strip()
    main = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    _git(repo, "branch", "research/sig-round-1")
    # a year of development in the main checkout
    _commit(
        repo,
        "app/code.py",
        "x = 2  # new work\n",
        when=datetime(2026, 12, 1, tzinfo=UTC),
    )
    _commit(repo, "app/more.py", "y = 3\n", when=datetime(2027, 1, 5, tzinfo=UTC))
    worktree = tmp_path / "research"
    _git(repo, "worktree", "add", "-q", str(worktree), "research/sig-round-1")
    with pytest.raises(reg.Refused, match="frozen paths changed"):
        reg.check_can_run(str(repo), 1, now=AFTER)  # main is not the frozen code
    state = reg.check_can_run(str(worktree), 1, now=AFTER)
    assert state.head == freeze_commit and state.frozen_files_changed_since_freeze == []
    # the fetch and the results are committed on the research branch: still the frozen
    # code (the round's folder is not frozen)
    _commit(
        worktree,
        "docs/dev/sig-audit/round-1/data.json",
        "{}\n",
        when=datetime(2027, 2, 2, tzinfo=UTC),
        msg="fetch",
    )
    assert (
        reg.check_can_run(str(worktree), 1, now=AFTER).frozen_files_changed_since_freeze
        == []
    )
    # bringing main's code into the research branch is refused: it fails safe
    _git(worktree, "merge", "-q", "--no-edit", main)
    with pytest.raises(reg.Refused, match="frozen paths changed"):
        reg.check_can_run(str(worktree), 1, now=AFTER)


# --- rows, floors, Holm and verdicts ------------------------------------------------------


def row(calls, up, ret=None, kind=st.TWO_SIDED, tf="1h"):
    calls = np.asarray(calls, dtype=np.int8)
    up = np.asarray(up, dtype=np.int8)
    ret = np.asarray(
        ret if ret is not None else np.where(up == 1, 0.004, -0.004), float
    )
    E = len(calls)
    opens = 1_767_225_600 + 3600 * np.arange(E, dtype=np.int64)
    return RowPairs(
        st.Pairs(calls, up, ret, kind, tf), opens, np.ones(E), np.ones(E), E, 0, 0, 0
    )


def fixture_round(seed=0, draws=2000):
    """Four rows: a strong signal (PASS), anti-skill (WORSE), noise (FAIL), and one with
    2,400 eligible pairs but only 600 calls (NOT ASSESSABLE)."""
    rng = np.random.default_rng(seed)
    E = 2400
    out = []
    calls = rng.choice([1, -1], size=E)
    right = rng.random(E) < 0.62
    out.append(
        (
            engine.RowKey("SIG-X", "ex", "AAA", "1h"),
            row(calls, np.where(calls == 1, right, ~right)),
        )
    )
    calls = rng.choice([1, -1], size=E)
    right = rng.random(E) < 0.38
    out.append(
        (
            engine.RowKey("SIG-X", "ex", "BBB", "1h"),
            row(calls, np.where(calls == 1, right, ~right)),
        )
    )
    out.append(
        (
            engine.RowKey("SIG-X", "ex", "CCC", "1h"),
            row(rng.choice([1, -1], size=E), rng.integers(0, 2, E)),
        )
    )
    calls = np.where(rng.random(E) < 0.25, rng.choice([1, -1], size=E), 0)
    out.append(
        (engine.RowKey("SIG-X", "ex", "DDD", "1h"), row(calls, rng.integers(0, 2, E)))
    )
    return engine.evaluate_round(out, draws=draws, seed=seed)


def test_rows_floors_and_the_verdict_rule():
    res = fixture_round()
    verdicts = [r.verdict for r in res.rows]
    assert verdicts == [engine.PASS, engine.WORSE, engine.FAIL, engine.NOT_ASSESSABLE]
    assert res.family_size == 8  # NOT ASSESSABLE rows stay in F
    na = res.rows[3]
    assert na.counts.eligible == 2400 and na.counts.n < 1000
    # its members entered both Holm procedures with p = 1
    assert all(
        na.results[s].p_holm == 1.0 and na.results[s].q_holm == 1.0
        for s in st.STATISTICS
    )
    # WORSE is information only: never a pass
    assert res.rows[1].passing == []
    # a statistic that survives Holm but fails its extra condition is not a pass
    pass_row = res.rows[0]
    assert pass_row.passing and all(
        pass_row.results[s].extra_met for s in pass_row.passing
    )


def test_the_holm_family_is_every_registered_member():
    res = fixture_round()
    members = [r.results[s].p_holm for r in res.rows for s in st.STATISTICS]
    adj = st.holm_adjusted(members)
    got = [r.holm[s] for r in res.rows for s in st.STATISTICS]
    assert got == adj


def test_verdicts_are_checked_twice():
    res = fixture_round()
    assert engine.recheck_verdicts(res) == [r.verdict for r in res.rows]
    engine.check_verdicts(res)
    res.rows[2].verdict = engine.PASS  # a wrong verdict is caught
    with pytest.raises(AssertionError, match="re-derived"):
        engine.check_verdicts(res)


def test_the_report_has_every_row_and_no_pooled_verdict():
    res = fixture_round()
    record = rp.results_record(res, 9, "a" * 64, {"head": "abc", "python": "3.x"})
    text = rp.report_markdown(
        {"window": {"start": "s", "end": "e"}, "exchange": "ex"}, record
    )
    for r in record["rows"]:
        assert r["verdict_line"] in text
        for s in st.STATISTICS:
            assert r["statistics"][s]["verdict_line"] in text
    for phrase in rp.FORBIDDEN:
        assert phrase not in text.lower()
    with pytest.raises(rp.NoPooling):
        rp.pooled_verdict(record["rows"])
    with pytest.raises(rp.NoPooling):
        rp.check_report(text + "\nThe overall verdict is PASS.\n", record)
    # a header with counts for information only, and the dependence caveat
    assert "for information only" in text and "positively dependent" in text


def test_every_row_has_its_section_13_fields():
    res = fixture_round()
    record = rp.results_record(res, 9, "a" * 64, {"head": "abc"})
    for r in record["rows"]:
        c = r["counts"]
        for key in (
            "eligible_pairs",
            "skipped_pairs",
            "ties",
            "calls",
            "coverage",
            "q",
            "p_c",
            "best_constant",
            "chance_at_mix",
            "up_share_all",
            "h",
            "m",
            "k",
        ):
            assert key in c
        for s in st.STATISTICS:
            x = r["statistics"][s]
            for key in (
                "value",
                "p_exact",
                "bootstrap",
                "batch_means",
                "holm_adjusted",
                "q_exact",
                "bootstrap_opposite",
                "batch_means_opposite",
                "holm_opposite_adjusted",
                "mde",
                "upper_95",
            ):
                assert key in x
            assert x["bootstrap"] is None or "mcse_upper" in x["bootstrap"]
        assert set(r["magnitude_conditions"]) == {
            "raw_mean_c_r",
            "called_mean_return",
            "round_trip_cost",
        }
        for key in (
            "tau_by_indicator",
            "L",
            "K",
            "batch_means_dropped",
            "mean_call_run",
            "hit_lag1_autocorrelation",
        ):
            assert key in r["dependence"]


def test_verdict_lines_carry_their_caveat():
    res = fixture_round()
    F = res.family_size
    lines = {
        r.key.coin: {s: rp.verdict_line(r, s, F, 0.05) for s in st.STATISTICS}
        for r in res.rows
    }
    passing = lines["AAA"]["hit_rate"]
    assert passing.startswith(
        f"**PASS (provisional, not yet confirmed; hit rate; family of {F} tests at 5%)**: "
    )
    assert re.search(r"hit rate \d+\.\d% vs best constant \d+\.\d%", passing)
    assert "n = 2,400" in passing and re.search(r"m = [\d,]+, k = [\d,]+", passing)
    assert "Holm p = " in passing
    fail = lines["CCC"]["hit_rate"]
    assert fail.startswith(
        f"**FAIL, no evidence of an edge at this power (hit rate; family of {F} tests at 5%)**: "
    )
    assert re.search(
        r"edge at most -?\d+\.\d points \(95%\); smallest detectable edge", fail
    )
    na = lines["DDD"]["magnitude"]
    assert na.startswith("**NOT ASSESSABLE (magnitude; family of 8 tests at 5%)**")
    assert "calls < 1000" in na
    worse = lines["BBB"]["hit_rate"]
    assert worse.startswith("**WORSE, information only, not a pass (hit rate;")
    assert "chance at the mix" in worse


# --- confirmation -----------------------------------------------------------------------


def test_a_confirmation_round_takes_exactly_the_provisional_members():
    res = fixture_round()
    provisional = [(r.key, s) for r in res.rows for s in r.passing]
    assert provisional and all(r.verdict == engine.PASS for r in res.rows if r.passing)
    members = [engine.Member(k, s, st.TWO_SIDED, {"rule": "x"}) for k, s in provisional]
    rng = np.random.default_rng(99)
    E = 2400
    fresh = []
    for i, m in enumerate(members):
        calls = rng.choice([1, -1], size=E)
        right = rng.random(E) < (0.62 if i == 0 else 0.5)  # only the first holds up
        fresh.append(row(calls, np.where(calls == 1, right, ~right)))
    out = engine.confirm(members, fresh, draws=2000, seed=5)
    assert out[0].outcome == engine.CONFIRMED
    assert all(o.outcome == engine.NOT_CONFIRMED for o in out[1:])
    adj = st.holm_adjusted([o.result.p_holm for o in out])
    assert [o.holm for o in out] == adj  # Holm over the members only
    # below a floor on the confirmation window: FAIL (not confirmed)
    short = row(rng.choice([1, -1], size=500), rng.integers(0, 2, 500))
    assert (
        engine.confirm(members[:1], [short], 2000, 5)[0].outcome == engine.NOT_CONFIRMED
    )


def _confirmation_fixture():
    earlier = {
        "candidates": [
            {
                "key": "SIG-A",
                "rule": "r",
                "parameters": {"length": 20},
                "kind": "two-sided",
                "inputs": "i",
                "input_coins": [],
            }
        ],
        "window": {"start": "2026-11-08T00:00:00Z", "end": "2027-08-01T00:00:00Z"},
    }
    results = {
        "provisional": [
            {
                "candidate": "SIG-A",
                "exchange": "ex",
                "coin": "AAA",
                "timeframe": "1h",
                "statistic": "hit_rate",
            }
        ]
    }
    member = {
        "candidate": "SIG-A",
        "exchange": "ex",
        "coin": "AAA",
        "timeframe": "1h",
        "statistic": "hit_rate",
        "registration": dict(earlier["candidates"][0]),
    }
    ok = {
        "window": {"start": "2027-08-02T00:00:00Z", "end": "2028-02-01T00:00:00Z"},
        "members": [member],
    }
    return earlier, results, ok


def test_a_confirmation_round_is_refused_when_anything_differs():
    earlier, results, ok = _confirmation_fixture()
    windows = [{"round": 1, "window": earlier["window"], "status": "results"}]
    at = datetime(2027, 6, 30, tzinfo=UTC)
    reg.check_confirmation(ok, earlier, results, windows, at)
    overlap = dict(
        ok, window={"start": "2027-07-01T00:00:00Z", "end": "2028-01-01T00:00:00Z"}
    )
    with pytest.raises(reg.Refused, match="overlaps round 1's window"):
        reg.check_confirmation(overlap, earlier, results, windows, at)
    changed = json.loads(json.dumps(ok))
    changed["members"][0]["registration"]["parameters"] = {"length": 21}
    with pytest.raises(reg.Refused, match="parameters differs"):
        reg.check_confirmation(changed, earlier, results, windows, at)
    other_stat = json.loads(json.dumps(ok))
    other_stat["members"][0]["statistic"] = "magnitude"
    with pytest.raises(reg.Refused, match="exactly the provisional"):
        reg.check_confirmation(other_stat, earlier, results, windows, at)
    model = json.loads(json.dumps(ok))
    model["members"][0]["registration"]["model"] = {"id": "other"}
    with pytest.raises(reg.Refused, match="model differs"):
        reg.check_confirmation(model, earlier, results, windows, at)


def _rounds_for_confirmation(repo):
    """Round 1 with results; round 2 cancelled before results, its window started;
    round 3 registered and not yet evaluated."""
    w1 = {"start": "2026-11-08T00:00:00Z", "end": "2027-02-01T00:00:00Z"}
    w2 = {"start": "2027-02-10T00:00:00Z", "end": "2027-08-01T00:00:00Z"}
    w3 = {"start": "2027-09-01T00:00:00Z", "end": "2028-01-01T00:00:00Z"}
    _register(repo, 1, {"window": w1}, when=datetime(2026, 11, 6, 12, tzinfo=UTC))
    _register(repo, 2, {"window": w2}, when=datetime(2027, 2, 5, tzinfo=UTC))
    rel1, rel2 = "docs/dev/sig-audit/round-1", "docs/dev/sig-audit/round-2"
    _commit(repo, f"{rel1}/results.json", "{}\n", when=datetime(2027, 2, 6, tzinfo=UTC))
    rec = reg.cancellation_record(
        str(repo), 2, "a defect", now=datetime(2027, 3, 1, tzinfo=UTC)
    )
    assert rec["window_started"] is True and rec["results"] is None
    _commit(
        repo,
        f"{rel2}/{reg.CANCELLATION}",
        json.dumps(rec, indent=1) + "\n",
        when=datetime(2027, 3, 1, tzinfo=UTC),
        msg="cancel",
    )
    _register(repo, 3, {"window": w3}, when=datetime(2027, 3, 1, 12, tzinfo=UTC))
    return w1, w2, w3


def test_a_confirmation_does_not_reuse_evaluated_observations(repo):
    """A6: a confirmation round never reuses observations another round evaluated or
    will evaluate. An unexamined cancelled window alone does not bar it, and, as for a
    replacement (A3), it evaluates only observations after its own registration."""
    w1, w2, w3 = _rounds_for_confirmation(repo)
    windows = reg.round_windows(str(repo))
    assert [(w["round"], w["status"]) for w in windows] == [
        (1, "results"),
        (2, reg.CANCELLED_UNEXAMINED),
        (3, "registered"),
    ]
    assert windows[1]["window"] == w2
    assert [w["round"] for w in reg.round_windows(str(repo), exclude=[3])] == [1, 2]
    earlier, results, ok = _confirmation_fixture()
    at = datetime(2027, 3, 2, 12, tzinfo=UTC)

    def confirm(start, end, when=at):
        c = dict(ok, window={"start": start, "end": end})
        reg.check_confirmation(c, earlier, results, windows, when)

    # inside the cancelled window, after its own registration: allowed
    confirm("2027-03-03T00:00:00Z", "2027-08-20T00:00:00Z")
    # the cancelled window's elapsed part is never evaluated: refused, as section 11
    # refuses any window that starts before its registration
    with pytest.raises(reg.Refused, match="not after its registration commit"):
        confirm("2027-02-20T00:00:00Z", "2027-08-20T00:00:00Z")
    with pytest.raises(reg.Refused, match="not after its registration commit"):
        confirm("2027-03-02T00:00:00Z", "2027-08-20T00:00:00Z")
    # a round with results, or a registered round still to be evaluated: refused
    with pytest.raises(reg.Refused, match=r"round 1's window .* \(results\)"):
        confirm(
            "2027-01-01T00:00:00Z",
            "2027-08-20T00:00:00Z",
            when=datetime(2026, 12, 1, tzinfo=UTC),
        )
    with pytest.raises(reg.Refused, match=r"round 3's window .* \(registered\)"):
        confirm("2027-03-03T00:00:00Z", "2027-09-02T00:00:00Z")


def test_only_a_committed_cancellation_before_results_frees_a_window(repo):
    """A6, failing safe: a cancellation not committed, changed since, or beside
    results leaves the round's window barred."""
    _rounds_for_confirmation(repo)
    earlier, results, ok = _confirmation_fixture()
    at = datetime(2027, 3, 2, 12, tzinfo=UTC)
    c = dict(
        ok, window={"start": "2027-03-03T00:00:00Z", "end": "2027-08-20T00:00:00Z"}
    )
    rel2 = "docs/dev/sig-audit/round-2"
    status = {w["round"]: w["status"] for w in reg.round_windows(str(repo))}
    assert status[2] == reg.CANCELLED_UNEXAMINED
    # changed since its commit
    cancel = os.path.join(repo, rel2, reg.CANCELLATION)
    with open(cancel, encoding="utf-8") as f:
        text = f.read()
    _write(repo, f"{rel2}/{reg.CANCELLATION}", text.replace("a defect", "rewritten"))
    windows = reg.round_windows(str(repo))
    assert {w["round"]: w["status"] for w in windows}[2] == "registered"
    with pytest.raises(reg.Refused, match=r"round 2's window .* \(registered\)"):
        reg.check_confirmation(c, earlier, results, windows, at)
    # beside results
    _write(repo, f"{rel2}/{reg.CANCELLATION}", text)
    _write(repo, f"{rel2}/results.json", "{}\n")
    windows = reg.round_windows(str(repo))
    assert {w["round"]: w["status"] for w in windows}[2] == "results"
    with pytest.raises(reg.Refused, match=r"round 2's window .* \(results\)"):
        reg.check_confirmation(c, earlier, results, windows, at)
    os.remove(os.path.join(repo, rel2, "results.json"))
    # not committed: the cancellation removed from HEAD and only written on disk
    _git(repo, "rm", "-q", "--cached", f"{rel2}/{reg.CANCELLATION}")
    _git(repo, "commit", "-q", "-m", "uncommit the cancellation")
    windows = reg.round_windows(str(repo))
    assert {w["round"]: w["status"] for w in windows}[2] == "registered"
    with pytest.raises(reg.Refused, match="overlaps round 2's window"):
        reg.check_confirmation(c, earlier, results, windows, at)
    # an uncommitted draft registration is not a round yet
    _write(repo, "docs/dev/sig-audit/round-4/registration.json", '{"window": {}}\n')
    assert 4 not in {w["round"] for w in reg.round_windows(str(repo))}


# --- evidence ---------------------------------------------------------------------------


def market(pair, coin, status="TRADING", leveraged=None, base=None):
    return ListedMarket(
        pair, coin, base or coin, "USDT", status, status == "TRADING", leveraged
    )


def test_ranking_exclusions_and_replacements_with_a_gapped_coin():
    listing = MarketListing(
        "ex",
        "USDT",
        (
            market("BTCUSDT", "BTC"),
            market("ETHUSDT", "ETH"),
            market("USDCUSDT", "USDC"),
            market("BTCUPUSDT", "BTCUP"),
            market("JUPUSDT", "JUP"),
            market("WBTCUSDT", "WBTC"),
            market("XYZUSDT", "XYZ", leveraged=True),
            market("SOLUSDT", "SOL"),
            market("OLDUSDT", "OLD", status="BREAK"),
            market("ADAUSDT", "ADA"),
        ),
        (),
    )
    from pt_exchange_abstraction import DailyQuoteVolume

    days = ranking.ranking_days("2026-11-06")
    vols = {
        m.pair: DailyQuoteVolume("ex", m.pair, tuple((d, v) for d in days), "f", ())
        for m, v in zip(
            listing.markets, (900, 800, 999, 700, 600, 650, 500, 400, 300, 200)
        )
    }
    ranked = ranking.rank_markets(listing, vols, "2026-11-06", ranking.Exclusions())
    by = {r.coin: r for r in ranked}
    assert [r.coin for r in ranked][:3] == ["USDC", "BTC", "ETH"]
    assert abs(by["BTC"].quote_volume_30d - 900 * 30) < 1e-9 and by["BTC"].days == 30
    assert not by["USDC"].included and "stablecoin" in by["USDC"].reason
    assert not by["BTCUP"].included and "BTC plus UP" in by["BTCUP"].reason
    assert by["JUP"].included  # its stem J is not a listed base
    assert not by["WBTC"].included and "wrapped" in by["WBTC"].reason
    assert not by["XYZ"].included and "marked by the exchange" in by["XYZ"].reason

    def history(r):
        if r.coin == "ETH":  # a coin with a gap fails and is replaced
            return ranking.History(False, 0, 0, 30, 0.05, 30, "a gap of 30 hours")
        return ranking.History(True, 720, 720, 0, 0.0, 0, "")

    sel = ranking.select_coins(ranked, history, count=3)
    assert sel.coins == ["BTC", "JUP", "SOL"]
    assert sel.replacements == [
        {
            "failed": "ETH",
            "rank": by["ETH"].rank,
            "reason": "a gap of 30 hours",
            "replaced_by": "SOL",
        }
    ]


def test_the_history_rule():
    start, end = 0, 3600 * 1000
    all_bars = np.arange(0, end, 3600)
    assert ranking.check_history(all_bars, start, end).ok
    one = np.delete(all_bars, 500)  # 1 of 1,000 missing: 0.1%, allowed
    assert ranking.check_history(one, start, end).ok
    two = np.delete(all_bars, [500, 700])  # 0.2%
    assert not ranking.check_history(two, start, end).ok
    gap = np.delete(np.arange(0, 3600 * 40_000, 3600), range(1000, 1025))  # 25 hours
    h = ranking.check_history(gap, 0, 3600 * 40_000)
    assert not h.ok and h.longest_gap_hours == 25 and "a gap of 25 hours" in h.reason


def test_raw_answers_are_kept_with_matching_sha256(tmp_path):
    from pt_exchange_abstraction import RawAnswer

    answers = [
        RawAnswer("https://example.invalid/a", (("x", "1"),), 200, b'{"a": 1}'),
        RawAnswer("https://example.invalid/b", (), 200, b"[1, 2, 3]"),
    ]
    path = str(tmp_path / "raw.jsonl.gz")
    record = ranking.write_raw_answers(path, answers)
    assert ranking.verify_raw_answers(path, record) == []
    assert record["answers"][0]["sha256"] == answers[0].sha256
    again = ranking.write_raw_answers(str(tmp_path / "again.jsonl.gz"), answers)
    assert again["file_sha256"] == record["file_sha256"]  # the same bytes again
    tampered = dict(
        record,
        answers=[dict(record["answers"][0], sha256="0" * 64), record["answers"][1]],
    )
    assert ranking.verify_raw_answers(path, tampered)


def test_the_output_record_and_the_registered_seed_and_draws():
    res = fixture_round(seed=4, draws=1500)
    state = {
        "head": "c0ffee",
        "registration_sha256": "r" * 64,
        "python": sys.version,
        "powertrader_home": "/sandbox",
        "frozen_files_dirty": [],
        "frozen_files_changed_since_freeze": [],
    }
    record = rp.results_record(res, 1, "r" * 64, state)
    assert record["seed"] == 4 and record["bootstrap_draws"] == 1500
    assert record["state"] == state and record["registration_sha256"] == "r" * 64
    for r in record["rows"]:
        for s in st.STATISTICS:
            b = r["statistics"][s]["bootstrap"]
            assert b is None or b["draws"] == 1500
    # the floors the code applies are the registered defaults of section 7.4
    assert (st.MIN_CALLS, st.MIN_BLOCKS, st.MIN_DISCORDANT, st.MIN_ABSTAINED) == (
        1000,
        30,
        200,
        200,
    )
    assert st.min_bootstrap_draws(76) == 152_000


# --- nothing else changes ----------------------------------------------------------------


def test_the_audit_touches_no_trading_code():
    """Section 16 item 12: the audit reads candles and writes reports. No module of it
    imports the trader, the runner, the trainer, the strategies or the strategy engine.
    """
    forbidden = re.compile(
        r"^\s*(from|import)\s+(pt_trader|pt_thinker|pt_pattern_trainer|strategies|"
        r"strategy|pt_hub)\b",
        re.MULTILINE,
    )
    folder = os.path.join(APP_DIR, "signal_audit")
    for name in os.listdir(folder):
        if name.endswith(".py"):
            text = open(os.path.join(folder, name), encoding="utf-8").read()
            assert not forbidden.search(text), name
