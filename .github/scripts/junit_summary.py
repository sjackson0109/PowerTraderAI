"""Summarise a pytest JUnit XML report for a GitHub Actions run.

Usage: python junit_summary.py JUNIT_XML PYTEST_LOG [--title TITLE] [--prefix app/]

Writes Markdown to $GITHUB_STEP_SUMMARY (stdout when it is unset): pytest's own result
line, the counts, every failed or errored test with a one-line reason and its
traceback, the skip reasons, and the slowest tests. It also prints a GitHub error
annotation for the first failures, so they show on the pull request's checks page.

The pytest step decides pass or fail; this script only reports. It exits 1 when the
report is missing or unreadable (pytest did not finish), so a run without evidence is
never green, and 0 otherwise.

The report must be written with ``-o junit_family=xunit1``, which records each test's
file and line. Test ids are relative to pytest's root folder (``app/`` in CI);
``--prefix`` turns them into repository paths for the annotations.
"""

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter

MAX_LISTED = 100  # failed/errored tests listed in the table
MAX_DETAILS = 30  # of those, how many get a traceback block
MAX_TRACE_LINES = 60  # last lines of each traceback shown
MAX_ANNOTATIONS = 10  # GitHub shows at most 10 error annotations per step
MAX_REASON = 200
LOG_TAIL_LINES = 60
RESULT_LINE = re.compile(
    r"^=+ .*\b(passed|failed|error|errors|skipped|deselected|no tests ran)\b.* in [0-9.]+s.*=+$"
)


def _test_id(case):
    """pytest's node id (``tests/test_x.py::TestC::test_y``) from an xunit1 testcase."""
    name = case.get("name", "")
    classname = case.get("classname", "")
    path = (case.get("file") or "").replace("\\", "/")
    if path and not classname:  # a collection error: the module itself
        return path
    if path:
        module = path[:-3] if path.endswith(".py") else path
        module = module.replace("/", ".")
        if classname == module:
            return f"{path}::{name}"
        if classname.startswith(module + "."):
            classes = classname[len(module) + 1 :].split(".")
            return "::".join([path, *classes, name])
        return f"{path}::{name}"
    return f"{classname}::{name}" if classname else name


def _one_line(text, limit=MAX_REASON):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _cell(text):
    """Safe inside a Markdown table cell."""
    return text.replace("|", "\\|").replace("`", "'")


def _escape_data(text):
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(text):
    return _escape_data(text).replace(":", "%3A").replace(",", "%2C")


def _cases(root):
    if root.tag == "testcase":
        return [root]
    return list(root.iter("testcase"))


def _classify(case):
    """("failed" | "error" | "xfailed" | "skipped" | "passed", element or None)."""
    for tag in ("failure", "error"):
        element = case.find(tag)
        if element is not None:
            return ("failed" if tag == "failure" else "error"), element
    element = case.find("skipped")
    if element is not None:
        if element.get("type") == "pytest.xfail":
            return "xfailed", element
        return "skipped", element
    return "passed", None


def _result_line(log_path):
    """pytest's final "N passed, M skipped in Xs" line from the log, if any."""
    try:
        with open(log_path, encoding="utf-8", errors="replace") as log:
            lines = log.read().splitlines()
    except OSError:
        return None, []
    for line in reversed(lines):
        if RESULT_LINE.match(line.strip()):
            return line.strip().strip("=").strip(), lines
    return None, lines


def _format_seconds(seconds):
    minutes, secs = divmod(int(round(seconds)), 60)
    return f"{minutes}m {secs:02d}s" if minutes else f"{seconds:.1f}s"


def summarise(junit_path, log_path, title, prefix):
    """(markdown, annotations, exit_code)."""
    out = [f"## {title}", ""]
    result_line, log_lines = _result_line(log_path)
    try:
        root = ET.parse(junit_path).getroot()
    except (OSError, ET.ParseError) as exc:
        out += [
            "**No test report**: pytest did not finish (it timed out, crashed or never "
            f"started), so there is no result to show. `{os.path.basename(junit_path)}`: "
            f"{_one_line(str(exc))}",
            "",
        ]
        if log_lines:
            out += [
                f"Last {min(LOG_TAIL_LINES, len(log_lines))} lines of the log "
                "(the whole log is in the run's artifacts):",
                "",
                "```text",
                *log_lines[-LOG_TAIL_LINES:],
                "```",
            ]
        return "\n".join(out) + "\n", [], 1

    cases = _cases(root)
    groups = {"passed": [], "failed": [], "error": [], "skipped": [], "xfailed": []}
    for case in cases:
        kind, element = _classify(case)
        groups[kind].append((case, element))
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    duration = float(suite.get("time") or 0) if suite is not None else 0.0
    if not duration:
        duration = sum(float(case.get("time") or 0) for case in cases)
    bad = groups["failed"] + groups["error"]

    verdict = "FAILED" if bad else "PASSED"
    out += [f"**{verdict}**" + (f": `{result_line}`" if result_line else ""), ""]
    out += [
        "| Test cases | Passed | Failed | Errors | Skipped | xfailed | Duration |",
        "|---:|---:|---:|---:|---:|---:|---:|",
        f"| {len(cases)} | {len(groups['passed'])} | {len(groups['failed'])} "
        f"| {len(groups['error'])} | {len(groups['skipped'])} | {len(groups['xfailed'])} "
        f"| {_format_seconds(duration)} |",
        "",
        "Counts are per test case in the JUnit report; a test that passes and then "
        "fails at teardown counts once, as an error. Test ids are relative to "
        f"`{prefix or './'}`.",
        "",
    ]

    annotations = []
    if bad:
        out += [f"### Failed and errored tests ({len(bad)})", ""]
        out += ["| Test | Outcome | Reason |", "|---|---|---|"]
        for case, element in bad[:MAX_LISTED]:
            kind = "failed" if element.tag == "failure" else "error"
            reason = _one_line(element.get("message") or element.text or "")
            out.append(f"| `{_cell(_test_id(case))}` | {kind} | {_cell(reason)} |")
        if len(bad) > MAX_LISTED:
            out.append(
                f"| ... and {len(bad) - MAX_LISTED} more (see the artifacts) | | |"
            )
        out.append("")
        for case, element in bad[:MAX_DETAILS]:
            trace = (element.text or element.get("message") or "").rstrip().splitlines()
            if len(trace) > MAX_TRACE_LINES:
                trace = ["...", *trace[-MAX_TRACE_LINES:]]
            out += [
                f"<details><summary><code>{_test_id(case)}</code></summary>",
                "",
                "```text",
                *trace,
                "```",
                "",
                "</details>",
                "",
            ]
        for case, element in bad[:MAX_ANNOTATIONS]:
            props = [f"title={_escape_property('Test ' + _test_id(case))}"]
            path = (case.get("file") or "").replace("\\", "/")
            if path:
                props.insert(0, f"file={_escape_property(prefix + path)}")
                line = case.get("line")
                if line and line.isdigit():
                    props.insert(1, f"line={int(line) + 1}")
            reason = _one_line(element.get("message") or element.text or "", 500)
            annotations.append(f"::error {','.join(props)}::{_escape_data(reason)}")

    skipped = groups["skipped"] + groups["xfailed"]
    if skipped:
        reasons = Counter(
            _one_line(element.get("message") or element.text or "(no reason)")
            for _, element in skipped
        )
        out += [f"### Skipped tests ({len(skipped)}), by reason", ""]
        out += ["| Tests | Reason |", "|---:|---|"]
        for reason, count in reasons.most_common():
            out.append(f"| {count} | {_cell(reason)} |")
        out.append("")

    slowest = sorted(cases, key=lambda case: float(case.get("time") or 0), reverse=True)
    if slowest:
        out += ["<details><summary>Slowest 15 tests</summary>", ""]
        out += ["| Seconds | Test |", "|---:|---|"]
        for case in slowest[:15]:
            out.append(
                f"| {float(case.get('time') or 0):.1f} | `{_cell(_test_id(case))}` |"
            )
        out += ["", "</details>", ""]

    out += [
        "The JUnit XML report and the whole pytest log are attached to this run as "
        "artifacts.",
        "",
    ]
    return "\n".join(out) + "\n", annotations, 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("junit")
    parser.add_argument("log")
    parser.add_argument("--title", default="Test results")
    parser.add_argument("--prefix", default="", help="added to test file paths")
    args = parser.parse_args(argv)
    # Failure messages can hold any character; a Windows runner's pipe is cp1252.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    markdown, annotations, code = summarise(
        args.junit, args.log, args.title, args.prefix
    )
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as summary:
            summary.write(markdown)
    else:
        sys.stdout.write(markdown)
    for annotation in annotations:
        print(annotation)
    if code:
        print(f"::error title=No test report::{args.junit} is missing or unreadable")
    return code


if __name__ == "__main__":
    sys.exit(main())
