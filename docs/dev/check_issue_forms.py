"""Check the issue forms in .github/ISSUE_TEMPLATE against GitHub's issue-form rules.

Usage:  python docs/dev/check_issue_forms.py [folder]
Needs PyYAML (``pip install pyyaml``). Prints one line per file and exits 1 if any
check fails. Malformed input is reported as a problem, never a traceback, and the
remaining files are still checked. Tests: docs/dev/test_check_issue_forms.py.

GitHub rules checked (a subset of GitHub's schema):
* every .yml/.yaml file parses;
* config.yml: ``blank_issues_enabled`` is a boolean; every contact link has a name,
  an https url and an about text;
* every form has a top-level name, description and body, and no unknown top-level keys;
* body is a non-empty list with at least one element that isn't markdown;
* each element has a valid type, only the keys and attributes that type allows, and
  ``validations`` holding at most ``required: true/false``; markdown has a value;
  every other element has a label and a unique text id;
* dropdown options are a non-empty list of unique, non-empty strings (an unquoted
  Yes/No loads as a boolean and fails); checkboxes have labelled options.

Project rules checked:
* no markdown (.md) templates beside the forms;
* every form has an "area" dropdown, the same word for word in all of them;
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
ELEMENT_KEYS = {"type", "id", "attributes", "validations"}
ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+")
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
    links = data.get("contact_links")
    if links is None:
        links = []
    elif not isinstance(links, list):
        problems.append("contact_links must be a list")
        links = []
    for i, link in enumerate(links):
        if not isinstance(link, dict):
            problems.append(f"contact_links[{i}]: not a mapping")
            continue
        for key in ("name", "url", "about"):
            if not is_text(link.get(key)):
                problems.append(f"contact_links[{i}]: missing {key}")
        if is_text(link.get("url")) and not link["url"].startswith("https://"):
            problems.append(f"contact_links[{i}]: url must start with https://")
    return problems


def is_text(value):
    return isinstance(value, str) and bool(value.strip())


def unknown_keys(mapping, allowed):
    """Keys not in ``allowed``, sorted as text (YAML keys need not be strings)."""
    return sorted(set(mapping) - allowed, key=str)


def check_element(i, element, ids):
    where = f"body[{i}]"
    if not isinstance(element, dict):
        return [f"{where}: not a mapping"]
    kind = element.get("type")
    if not isinstance(kind, str) or kind not in ATTRIBUTES:
        return [f"{where}: invalid type {kind!r}"]
    where = f"body[{i}] ({kind})"
    problems = [
        f"{where}: key {key!r} not allowed"
        for key in unknown_keys(element, ELEMENT_KEYS)
    ]
    validations = element.get("validations")
    if validations is not None and (
        not isinstance(validations, dict)
        or unknown_keys(validations, {"required"})
        or not isinstance(validations.get("required", False), bool)
    ):
        problems.append(f"{where}: validations may only hold required: true/false")
    attrs = element.get("attributes")
    if not isinstance(attrs, dict):
        return problems + [f"{where}: missing attributes"]
    problems += [
        f"{where}: attribute {key!r} not allowed"
        for key in unknown_keys(attrs, ATTRIBUTES[kind])
    ]
    if kind == "markdown":
        if not is_text(attrs.get("value")):
            problems.append(f"{where}: markdown needs a value")
        return problems

    element_id = element.get("id")
    if not isinstance(element_id, str) or not ID_PATTERN.fullmatch(element_id):
        problems.append(f"{where}: needs a text id of letters, digits, '-' or '_'")
    elif element_id in ids:
        problems.append(f"{where}: duplicate id {element_id!r}")
    else:
        ids.add(element_id)
    label = attrs.get("label")
    if not is_text(label):
        problems.append(f"{where}: needs a label")

    texts = [label if isinstance(label, str) else ""]
    if kind in ("dropdown", "checkboxes"):
        options = attrs.get("options")
        if not isinstance(options, list) or not options:
            problems.append(f"{where}: options must be a non-empty list")
            options = []
        if kind == "dropdown":
            if not all(is_text(option) for option in options):
                problems.append(
                    f"{where}: every option must be non-empty text (quote Yes/No)"
                )
            names = [str(option) for option in options]
            if len(set(names)) != len(names):
                problems.append(f"{where}: options must be unique")
        else:
            labels = [o.get("label") if isinstance(o, dict) else None for o in options]
            if not all(is_text(lab) for lab in labels):
                problems.append(f"{where}: every checkbox needs a label")
            names = [str(lab) for lab in labels]
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
        f"unknown top-level key {key!r}" for key in unknown_keys(data, TOP_LEVEL_KEYS)
    ]
    for key in ("name", "description"):
        if not is_text(data.get(key)):
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
    """The area dropdown's options as a tuple of strings, or None if there is none."""
    body = data.get("body") if isinstance(data, dict) else None
    for element in body if isinstance(body, list) else []:
        if isinstance(element, dict) and element.get("id") == "area":
            attrs = element.get("attributes")
            options = attrs.get("options") if isinstance(attrs, dict) else None
            return tuple(map(str, options)) if isinstance(options, list) else None
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
        except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
            print(f"FAIL {path.name}: does not parse: {exc}")
            failed = True
            continue
        try:
            if path.stem == "config":
                problems = check_config(data)
            else:
                problems = check_form(data)
                options = area_options(data)
                if options is None:
                    problems.append("no area dropdown with options (id: area)")
                else:
                    areas[path.name] = options
        except Exception as exc:  # a checker bug must not stop the other files
            problems = [f"checker error: {exc!r}"]
        print(f"{'FAIL' if problems else 'OK  '} {path.name}")
        for problem in problems:
            print(f"     - {problem}")
        failed = failed or bool(problems)

    if len(set(areas.values())) > 1:
        print("FAIL the area dropdown differs between forms:")
        for name, options in areas.items():
            print(f"     - {name}: {list(options)}")
        failed = True
    elif areas:
        print(f"OK   area dropdown identical in {len(areas)} forms")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
