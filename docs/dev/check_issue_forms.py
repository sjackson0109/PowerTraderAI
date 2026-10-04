"""Check the issue forms in .github/ISSUE_TEMPLATE against GitHub's issue-form rules.

Usage:  python docs/dev/check_issue_forms.py [folder]
Needs PyYAML (``pip install pyyaml``). Prints one line per file and exits 1 if any
check fails.

GitHub rules checked (a subset of GitHub's schema):
* every .yml/.yaml file parses;
* config.yml: ``blank_issues_enabled`` is a boolean; every contact link has a name,
  an https url and an about text;
* every form has a top-level name, description and body, and no unknown top-level keys;
* body is a non-empty list with at least one element that isn't markdown;
* each element has a valid type and only the attributes that type allows; markdown
  has a value; every other element has a label and a unique id;
* dropdown options are non-empty and unique; checkboxes have labelled options.

Project rules checked:
* no markdown (.md) templates beside the forms;
* the "area" dropdown is the same, word for word, in every form;
* no field label or option contains a word that
  .github/workflows/project-management.yml turns into a priority, phase or security
  label (markdown text and descriptions are not part of the issue body, so are fine).
"""

import re
import sys
from pathlib import Path

import yaml

DEFAULT_FOLDER = Path(__file__).resolve().parents[2] / ".github" / "ISSUE_TEMPLATE"

TOP_LEVEL_KEYS = {
    "name",
    "description",
    "body",
    "title",
    "labels",
    "assignees",
    "projects",
    "type",
}
ATTRIBUTES = {
    "markdown": {"value"},
    "input": {"label", "description", "placeholder", "value"},
    "textarea": {"label", "description", "placeholder", "value", "render"},
    "dropdown": {"label", "description", "multiple", "options", "default"},
    "checkboxes": {"label", "description", "options"},
}
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
AUTO_LABEL_WORDS = (
    "security",
    "credential",
    "stability",
    "functional",
    "production",
    "optimization",
)


def check_config(data):
    problems = []
    if not isinstance(data, dict):
        return ["not a mapping"]
    if not isinstance(data.get("blank_issues_enabled"), bool):
        problems.append("blank_issues_enabled must be true or false")
    for i, link in enumerate(data.get("contact_links") or []):
        for key in ("name", "url", "about"):
            if not isinstance(link, dict) or not link.get(key):
                problems.append(f"contact_links[{i}]: missing {key}")
        if isinstance(link, dict) and not str(link.get("url", "")).startswith(
            "https://"
        ):
            problems.append(f"contact_links[{i}]: url must start with https://")
    return problems


def check_element(i, element, ids):
    where = f"body[{i}]"
    if not isinstance(element, dict):
        return [f"{where}: not a mapping"]
    kind = element.get("type")
    if kind not in ATTRIBUTES:
        return [f"{where}: invalid type {kind!r}"]
    where = f"body[{i}] ({kind})"
    attrs = element.get("attributes")
    if not isinstance(attrs, dict):
        return [f"{where}: missing attributes"]
    problems = [
        f"{where}: attribute {key!r} not allowed"
        for key in sorted(set(attrs) - ATTRIBUTES[kind])
    ]
    if kind == "markdown":
        if not attrs.get("value"):
            problems.append(f"{where}: markdown needs a value")
        return problems

    element_id = element.get("id")
    if not element_id or not ID_PATTERN.match(str(element_id)):
        problems.append(f"{where}: needs an id of letters, digits, '-' or '_'")
    elif element_id in ids:
        problems.append(f"{where}: duplicate id {element_id!r}")
    ids.add(element_id)
    if not attrs.get("label"):
        problems.append(f"{where}: needs a label")

    texts = [str(attrs.get("label", ""))]
    if kind in ("dropdown", "checkboxes"):
        options = attrs.get("options")
        if not isinstance(options, list) or not options:
            problems.append(f"{where}: options must be a non-empty list")
            options = []
        if kind == "dropdown":
            names = [str(option) for option in options]
            if len(set(names)) != len(names):
                problems.append(f"{where}: options must be unique")
        else:
            names = [
                str(o.get("label", "")) if isinstance(o, dict) else "" for o in options
            ]
            if not all(names):
                problems.append(f"{where}: every checkbox needs a label")
        texts += names
    for text in texts:
        for word in AUTO_LABEL_WORDS:
            if word in text.lower():
                problems.append(f"{where}: {text!r} contains auto-label word {word!r}")
    return problems


def check_form(data):
    if not isinstance(data, dict):
        return ["not a mapping"]
    problems = [
        f"unknown top-level key {key!r}" for key in sorted(set(data) - TOP_LEVEL_KEYS)
    ]
    for key in ("name", "description"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            problems.append(f"missing top-level {key}")
    body = data.get("body")
    if not isinstance(body, list) or not body:
        return problems + ["body must be a non-empty list"]
    if all(isinstance(e, dict) and e.get("type") == "markdown" for e in body):
        problems.append("body needs at least one element that isn't markdown")
    ids = set()
    for i, element in enumerate(body):
        problems += check_element(i, element, ids)
    return problems


def area_options(data):
    for element in data.get("body") or []:
        if isinstance(element, dict) and element.get("id") == "area":
            return element.get("attributes", {}).get("options")
    return None


def main(argv):
    folder = Path(argv[1]) if len(argv) > 1 else DEFAULT_FOLDER
    failed = False
    areas = {}
    for path in sorted(folder.iterdir()):
        if path.suffix.lower() == ".md":
            print(f"FAIL {path.name}: markdown template; use an issue form (.yml)")
            failed = True
            continue
        if path.suffix.lower() not in (".yml", ".yaml"):
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            print(f"FAIL {path.name}: does not parse: {exc}")
            failed = True
            continue
        if path.stem == "config":
            problems = check_config(data)
        else:
            problems = check_form(data)
            if area_options(data) is not None:
                areas[path.name] = area_options(data)
        print(f"{'FAIL' if problems else 'OK  '} {path.name}")
        for problem in problems:
            print(f"     - {problem}")
        failed = failed or bool(problems)

    if len({tuple(options) for options in areas.values()}) > 1:
        print("FAIL the area dropdown differs between forms:")
        for name, options in areas.items():
            print(f"     - {name}: {options}")
        failed = True
    elif areas:
        print(f"OK   area dropdown identical in {len(areas)} forms")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
