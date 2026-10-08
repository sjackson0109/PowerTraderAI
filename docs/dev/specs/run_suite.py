"""Per-file test runner for PowerTraderAI: the method behind every suite number in
docs/dev/RUN-LOG-*.md since the strategy batch.

Run (from anywhere; the checkout is an argument):

    python run_suite.py run <checkout> --python <test-venv python> --out <results.json> [--github]

* Every app/test_*.py and app/tests/test_*.py, one file at a time, with the checkout as the
  working folder; test_phase1_phase2_integration.py is excluded (it kills its own process
  group on Windows). --github also runs every .github/scripts/test_*.py the same way,
  reported separately.
* 300 s per test (pytest-timeout), 1800 s per file; per-test results from JUnit XML.
* Every test process gets a fresh scratch POWERTRADER_HOME and the "fail" keyring backend,
  so nothing can reach the real user folders or credential store even if a conftest guard
  were missing.
* Work files (JUnit XML, the scratch homes) go to --work, default a new folder in the system
  temp folder; never inside the checkout.
* The real per-user folders and the names of PowerTrader entries in Windows Credential
  Manager (names only, never values) are compared before and after every file; the run stops
  if anything changes.

Compare two result files test by test:

    python run_suite.py compare <baseline.json> <final.json>

Exit code: 0 when the run completed (test failures included), 2 on a usage error or when the
real folders or credential entries changed.
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

APP_NAME, APP_AUTHOR = "PowerTraderAI", "SJackson"
EXCLUDE = {"test_phase1_phase2_integration.py"}
KNOWN_FLIP = "TestPowerTraderHubIntegration::test_graceful_degradation"  # skip or fail, by Tk start-up


def real_folders():
    """The real per-user folders PowerTraderAI uses (names only; nothing is created)."""
    if os.name == "nt":
        return [os.path.join(os.environ.get(v, ""), APP_AUTHOR) for v in ("APPDATA", "LOCALAPPDATA")
                if os.environ.get(v)]
    try:
        import platformdirs
    except ImportError:
        return []
    return sorted({
        platformdirs.user_config_dir(APP_NAME, APP_AUTHOR), platformdirs.user_data_dir(APP_NAME, APP_AUTHOR),
        platformdirs.user_log_dir(APP_NAME, APP_AUTHOR), platformdirs.user_cache_dir(APP_NAME, APP_AUTHOR),
    })


def real_state():
    """Every entry under the real folders (path, size, mtime) and the names of PowerTrader
    entries in Windows Credential Manager (names only, never values)."""
    entries = []
    for top in real_folders():
        if os.path.exists(top):
            entries.append((top, "dir", os.stat(top).st_mtime_ns))
        for folder, dirs, files in os.walk(top):
            for name in dirs + files:
                path = os.path.join(folder, name)
                st = os.stat(path)
                entries.append((path, st.st_size, st.st_mtime_ns))
    creds = []
    if os.name == "nt":
        out = subprocess.run(["cmdkey", "/list"], capture_output=True, text=True, errors="replace").stdout
        creds = sorted(line.strip() for line in out.splitlines() if "powertrader" in line.lower())
    return {"entries": sorted(entries), "credentials": creds}


def parse_junit(path):
    out = {"passed": [], "failed": [], "skipped": []}
    if not os.path.exists(path):
        return out
    for case in ET.parse(path).getroot().iter("testcase"):
        name = f"{case.get('classname', '')}::{case.get('name', '')}"
        tags = {child.tag for child in case}
        if "failure" in tags or "error" in tags:
            out["failed"].append(name)
        elif "skipped" in tags:
            out["skipped"].append(name)
        else:
            out["passed"].append(name)
    return out


def run_file(python, checkout, rel, junit_dir, home_root):
    junit = os.path.join(junit_dir, rel.replace("\\", "_").replace("/", "_") + ".xml")
    env = dict(os.environ)
    env["POWERTRADER_HOME"] = tempfile.mkdtemp(prefix="home_", dir=home_root)
    env["PYTHON_KEYRING_BACKEND"] = "keyring.backends.fail.Keyring"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    cmd = [python, "-m", "pytest", rel, "-q", "-p", "no:cacheprovider", "--timeout=300", f"--junitxml={junit}"]
    start = time.time()
    try:
        proc = subprocess.run(cmd, cwd=checkout, env=env, capture_output=True, text=True,
                              timeout=1800, encoding="utf-8", errors="replace")
        code, tail = proc.returncode, (proc.stdout + proc.stderr)[-1500:]
    except subprocess.TimeoutExpired:
        code, tail = "timeout", "file-level timeout (1800 s)"
    res = parse_junit(junit)
    return {
        "file": rel.replace("\\", "/"),
        "exit": code,
        "seconds": round(time.time() - start, 1),
        "passed": len(res["passed"]),
        "failed": len(res["failed"]),
        "skipped": len(res["skipped"]),
        "failed_tests": res["failed"],
        "skipped_tests": res["skipped"],
        "no_tests_collected": code == 5,
        "tail": tail if code not in (0, 5) else "",
    }


def inside(path, folder):
    path, folder = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(folder))
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def cmd_run(args):
    checkout = os.path.abspath(args.checkout)
    work = os.path.abspath(args.work or tempfile.mkdtemp(prefix="pt_suite_"))
    if inside(work, checkout):
        sys.exit("--work must be outside the checkout")
    if not os.path.isfile(os.path.join(checkout, "app", "pt_paths.py")):
        sys.exit(f"not a PowerTraderAI checkout: {checkout}")
    junit_dir, home_root = os.path.join(work, "junit"), os.path.join(work, "homes")
    os.makedirs(junit_dir, exist_ok=True)
    os.makedirs(home_root, exist_ok=True)
    before = real_state()
    files = sorted(glob.glob(os.path.join(checkout, "app", "test_*.py")))
    files += sorted(glob.glob(os.path.join(checkout, "app", "tests", "test_*.py")))
    files = [f for f in files if os.path.basename(f) not in EXCLUDE]
    gh_files = sorted(glob.glob(os.path.join(checkout, ".github", "scripts", "test_*.py"))) if args.github else []
    results = {"checkout": checkout, "python": args.python, "work": work, "app": [], "github": []}
    for group, items in (("app", files), ("github", gh_files)):
        for path in items:
            rel = os.path.relpath(path, checkout)
            print(f"[{group}] {rel}", flush=True)
            results[group].append(run_file(args.python, checkout, rel, junit_dir, home_root))
            if real_state() != before:
                results["aborted"] = f"real folders or credential entries changed after {rel}"
                json.dump(results, open(args.out, "w", encoding="utf-8"), indent=1)
                print(results["aborted"], file=sys.stderr)
                return 2
    for group in ("app", "github"):
        rows = results[group]
        results[f"{group}_totals"] = {k: sum(r[k] for r in rows) for k in ("passed", "failed", "skipped")}
    results["real_state_before"] = before
    results["real_state_unchanged"] = real_state() == before
    json.dump(results, open(args.out, "w", encoding="utf-8"), indent=1)
    print(json.dumps({k: v for k, v in results.items() if k.endswith("totals")}))
    return 0


def cmd_compare(args):
    base = json.load(open(args.baseline, encoding="utf-8"))
    final = json.load(open(args.final, encoding="utf-8"))
    for key in ("aborted",):
        for label, data in (("baseline", base), ("final", final)):
            if data.get(key):
                print(f"{label} run was aborted: {data[key]}")
    for label, data in (("baseline", base), ("final", final)):
        print(f"{label}: real folders and credential entries unchanged: {data.get('real_state_unchanged')}")
    for group in ("app", "github"):
        print(f"\n## {group}: baseline {base.get(group + '_totals')}  final {final.get(group + '_totals')}")
        b = {r["file"]: r for r in base.get(group, [])}
        f = {r["file"]: r for r in final.get(group, [])}
        for name in sorted(set(b) | set(f)):
            x, y = b.get(name), f.get(name)
            if not x:
                print(f"  NEW   {name}: {y['passed']} passed, {y['failed']} failed, {y['skipped']} skipped")
                continue
            if not y:
                print(f"  GONE  {name}")
                continue
            counts = lambda r: (r["passed"], r["failed"], r["skipped"])  # noqa: E731
            changes = []
            for t in sorted(set(y["failed_tests"]) - set(x["failed_tests"])):
                changes.append(f"newly failed: {t}")
            for t in sorted(set(x["failed_tests"]) - set(y["failed_tests"])):
                changes.append(f"no longer failed: {t}")
            for t in sorted(set(y["skipped_tests"]) - set(x["skipped_tests"])):
                changes.append(f"newly skipped: {t}")
            for t in sorted(set(x["skipped_tests"]) - set(y["skipped_tests"])):
                changes.append(f"no longer skipped: {t}")
            if counts(x) != counts(y) or changes:
                print(f"  DIFF  {name}: {counts(x)} -> {counts(y)} (passed, failed, skipped)")
                for line in changes:
                    note = "  (known Tk start-up flip)" if KNOWN_FLIP in line else ""
                    print(f"        {line}{note}")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run the suite one file at a time")
    run.add_argument("checkout", help="the PowerTraderAI checkout to test (a clean clone is best)")
    run.add_argument("--python", required=True, help="interpreter of the test venv (has pytest, pytest-timeout)")
    run.add_argument("--out", required=True, help="where to write the results JSON")
    run.add_argument("--github", action="store_true", help="also run .github/scripts/test_*.py")
    run.add_argument("--work", help="folder for JUnit files and scratch homes (outside the checkout)")
    cmp_ = sub.add_parser("compare", help="compare two results files test by test")
    cmp_.add_argument("baseline")
    cmp_.add_argument("final")
    args = parser.parse_args(argv)
    return cmd_run(args) if args.command == "run" else cmd_compare(args)


if __name__ == "__main__":
    sys.exit(main())
