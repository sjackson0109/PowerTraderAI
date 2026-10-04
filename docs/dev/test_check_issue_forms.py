"""Tests for docs/dev/check_issue_forms.py.

Run:  python -m pytest docs/dev/test_check_issue_forms.py
Needs pytest and PyYAML; skipped without PyYAML. CI doesn't run this file (it collects
app/test_*.py and .github/scripts/ only).

Each case writes a small valid set of forms to a temporary folder, breaks one thing
and runs the checker. It must exit 1 with the expected message, with no traceback,
without reaching the safety net ("checker error"), and still report every other file.
The cases use their own sample forms, so rewording the real forms doesn't break them.
"""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("yaml")

CHECKER = Path(__file__).resolve().with_name("check_issue_forms.py")

AREA_A = """\
  - type: dropdown
    id: area
    attributes:
      label: Area
      options:
        - Hub GUI
        - Backtester
        - Other
"""
AREA_B = AREA_A
CONFIG_LINKS = """\
contact_links:
  - name: Questions
    url: https://example.com/discussions
    about: Ask here.
"""
SAMPLE = {
    "config.yml": "blank_issues_enabled: false\n" + CONFIG_LINKS,
    "form_a.yml": """\
name: Form A
description: First form.
title: "[A]: "
labels: ["bug"]
body:
  - type: markdown
    attributes:
      value: Hello.
  - type: textarea
    id: summary
    attributes:
      label: Summary
      placeholder: "#123"
    validations:
      required: true
  - type: dropdown
    id: mode
    attributes:
      label: Mode
      options:
        - Paper
        - Live
        - Not sure
  - type: dropdown
    id: answer
    attributes:
      label: Answer
      options:
        - "Yes"
        - "No"
"""
    + AREA_A
    + """\
  - type: checkboxes
    id: confirm
    attributes:
      label: Before you submit
      options:
        - label: I have removed secrets.
          required: true
""",
    "form_b.yml": """\
name: Form B
description: Second form.
body:
  - type: textarea
    id: details
    attributes:
      label: Details
"""
    + AREA_B,
}
FORM_A_OPTIONS = "      options:\n        - Paper\n        - Live\n        - Not sure\n"
AREA_B_ATTRIBUTES = AREA_B[AREA_B.index("    attributes:") :]

# (id, file, text to replace or None to replace the whole file, new text, message)
CASES = [
    # Structure and GitHub's issue-form rules
    ("duplicate id", "form_a.yml", "id: mode", "id: summary", "duplicate id"),
    ("invalid type", "form_a.yml", "type: textarea", "type: textbox", "invalid type"),
    (
        "duplicate option",
        "form_a.yml",
        "        - Not sure",
        "        - Paper",
        "options must be unique",
    ),
    (
        "empty options",
        "form_a.yml",
        FORM_A_OPTIONS,
        "      options: []\n",
        "non-empty list",
    ),
    (
        "missing name",
        "form_b.yml",
        "name: Form B\n",
        "",
        "missing top-level name",
    ),
    (
        "unquoted colon",
        "form_a.yml",
        "description: First form.",
        "description: First: form.",
        "does not parse",
    ),
    (
        "area differs",
        "form_b.yml",
        "        - Backtester",
        "        - Back-tester",
        "area dropdown differs",
    ),
    ("markdown template", "old.md", None, "# Old\n", "markdown template"),
    (
        "auto-label word",
        "form_b.yml",
        "label: Details",
        "label: Security details",
        "auto-label word",
    ),
    (
        "misspelt attribute",
        "form_a.yml",
        'placeholder: "#123"',
        'placehoder: "#123"',
        "'placehoder' not allowed",
    ),
    (
        "http contact url",
        "config.yml",
        "url: https://example.com/discussions",
        "url: http://example.com",
        "must start with https",
    ),
    (
        "only markdown body",
        "only.yml",
        None,
        "name: x\ndescription: y\nbody:\n"
        "  - type: markdown\n    attributes:\n      value: hi\n",
        "isn't markdown",
    ),
    ("missing id", "form_b.yml", "    id: details\n", "", "needs a text id"),
    # Values that load as the wrong type, missing parts
    (
        "unquoted Yes/No",
        "form_a.yml",
        '- "Yes"\n        - "No"',
        "- Yes\n        - No",
        "non-empty text",
    ),
    ("null option", "form_a.yml", "        - Not sure", "        -", "non-empty text"),
    (
        "empty-string option",
        "form_a.yml",
        "        - Not sure",
        '        - ""',
        "non-empty text",
    ),
    ("empty file", "form_b.yml", None, "", "not a mapping"),
    ("list at the root", "form_b.yml", None, "- a\n- b\n", "not a mapping"),
    (
        "area attributes null",
        "form_b.yml",
        AREA_B_ATTRIBUTES,
        "    attributes:\n",
        "missing attributes",
    ),
    ("area dropdown removed", "form_b.yml", AREA_B, "", "no area dropdown"),
    (
        "checkbox label null",
        "form_a.yml",
        "        - label: I have removed secrets.",
        "        - label:",
        "every checkbox needs a label",
    ),
    # Malformed input that used to crash the checker
    (
        "contact_links is a boolean",
        "config.yml",
        CONFIG_LINKS,
        "contact_links: true\n",
        "contact_links must be a list",
    ),
    (
        "type is a list",
        "form_b.yml",
        "type: textarea",
        "type: [textarea]",
        "invalid type",
    ),
    ("id is a list", "form_b.yml", "id: details", "id: [details]", "needs a text id"),
    ("id is a number", "form_b.yml", "id: details", "id: 123", "needs a text id"),
    (
        "mixed-type attribute keys",
        "form_b.yml",
        "      label: Details\n",
        "      label: Details\n      1: x\n      foo: y\n",
        "attribute 'foo' not allowed",
    ),
    (
        "mixed-type top-level keys",
        "form_b.yml",
        "name: Form B",
        "1: a\nfoo: b\nname: Form B",
        "unknown top-level key 'foo'",
    ),
    ("not UTF-8", "form_b.yml", None, b"name: \xff\xfe bad\n", "does not parse"),
    (
        "validations not a boolean",
        "form_a.yml",
        "    validations:\n      required: true",
        '    validations:\n      required: "yes"',
        "validations may only hold",
    ),
    (
        "validations is a list",
        "form_a.yml",
        "    validations:\n      required: true",
        "    validations: []",
        "validations may only hold",
    ),
    (
        "unknown element key",
        "form_b.yml",
        "    id: details\n",
        "    id: details\n    idd: x\n",
        "key 'idd' not allowed",
    ),
    (
        "label is a list",
        "form_b.yml",
        "label: Details",
        "label: [Details]",
        "needs a label",
    ),
    (
        "contact link not a mapping",
        "config.yml",
        "    about: Ask here.\n",
        "    about: Ask here.\n  - just text\n",
        "not a mapping",
    ),
]


def write_sample(folder):
    folder.mkdir()
    for name, text in SAMPLE.items():
        (folder / name).write_text(text, encoding="utf-8")
    return folder


def run_checker(*args):
    return subprocess.run(
        [sys.executable, str(CHECKER), *map(str, args)],
        capture_output=True,
        text=True,
    )


def reported(output, name):
    return re.search(rf"^(OK  |FAIL) {re.escape(name)}(:|$)", output, re.M) is not None


def test_sample_forms_pass(tmp_path):
    result = run_checker(write_sample(tmp_path / "forms"))
    assert result.returncode == 0, result.stdout
    assert "area dropdown identical in 2 forms" in result.stdout


def test_real_forms_pass():
    result = run_checker()
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize(
    "file, old, new, message", [c[1:] for c in CASES], ids=[c[0] for c in CASES]
)
def test_broken_form_is_reported(tmp_path, file, old, new, message):
    folder = write_sample(tmp_path / "forms")
    path = folder / file
    if old is None:
        if isinstance(new, bytes):
            path.write_bytes(new)
        else:
            path.write_text(new, encoding="utf-8")
    else:
        text = path.read_text(encoding="utf-8")
        assert old in text, f"test setup: {old!r} not in {file}"
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    result = run_checker(folder)
    output = result.stdout + result.stderr
    assert result.returncode == 1, output
    assert message in result.stdout, output
    assert "Traceback" not in output
    assert "checker error" not in output
    for name in SAMPLE:
        assert reported(result.stdout, name), f"{name} not reported:\n{output}"


def test_safety_net_reports_a_checker_bug_and_continues(tmp_path, monkeypatch, capsys):
    spec = importlib.util.spec_from_file_location("check_issue_forms", CHECKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def broken(data):
        raise ZeroDivisionError("boom")

    monkeypatch.setattr(module, "check_config", broken)
    code = module.main(["check_issue_forms.py", str(write_sample(tmp_path / "forms"))])
    output = capsys.readouterr().out
    assert code == 1
    assert "FAIL config.yml" in output
    assert "checker error: ZeroDivisionError" in output
    assert reported(output, "form_a.yml") and reported(output, "form_b.yml")
