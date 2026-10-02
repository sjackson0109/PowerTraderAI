"""Static guard (FDS-108a): only pt_paths (and the migration) know where user
files live. No other module may build a path to the legacy config files or to
hub_data from ``__file__``, the CWD, or a bare relative name."""

import ast
import os
import re

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

LEGACY_NAMES = {
    "pt_config.json",
    "trading_config.json",
    "exchange_config.json",
    "gui_settings.json",
    "hub_data",
}
# Constants in pt_paths that hold those names.
LEGACY_CONSTANTS = {
    "SETTINGS_FILE",
    "GUI_SETTINGS_FILE",
    "TRADING_CONFIG_FILE",
    "EXCHANGE_CONFIG_FILE",
    "HUB_DIR_NAME",
}
ALLOWED = {"pt_paths.py", "pt_migrate.py"}
ANCHORS = re.compile(r"__file__|getcwd|Path\.cwd")


def production_files():
    for root, dirs, files in os.walk(APP_DIR):
        dirs[:] = [d for d in dirs if d not in ("tests", "__pycache__", "node_modules")]
        for name in files:
            if not name.endswith(".py") or name in ALLOWED:
                continue
            if name.startswith("test_") or name == "conftest.py":
                continue
            yield os.path.join(root, name)


def docstring_nodes(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                out.add(id(body[0].value))
    return out


def names_a_legacy_path(value: str) -> bool:
    if any(ch.isspace() for ch in value):
        return False  # prose (messages, help text), not a path
    parts = [p for p in re.split(r"[\\/]", value) if p]
    return any(p in LEGACY_NAMES for p in parts)


def violations_in(path):
    with open(path, encoding="utf-8", errors="ignore") as f:
        source = f.read()
    tree = ast.parse(source, filename=path)
    docs = docstring_nodes(tree)
    found = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docs
            and names_a_legacy_path(node.value)
        ):
            found.append((node.lineno, repr(node.value)))
        if isinstance(node, (ast.Call, ast.BinOp)):
            text = ast.unparse(node)
            if ANCHORS.search(text) and any(
                re.search(rf"\b{name}\b", text) for name in LEGACY_CONSTANTS
            ):
                found.append((node.lineno, text[:80]))
    return found


def test_no_module_builds_a_legacy_user_path():
    problems = {}
    for path in production_files():
        hits = violations_in(path)
        if hits:
            problems[os.path.relpath(path, APP_DIR)] = hits
    assert not problems, "legacy user paths built outside pt_paths:\n" + "\n".join(
        f"  {f}: " + "; ".join(f"line {ln} {txt}" for ln, txt in hits)
        for f, hits in sorted(problems.items())
    )


def test_the_checker_catches_the_old_patterns(tmp_path):
    sample = tmp_path / "sample.py"
    sample.write_text(
        "import os\n"
        "A = os.path.join(os.path.dirname(__file__), 'pt_config.json')\n"
        "B = os.path.join(os.getcwd(), 'hub_data', 'x.json')\n"
        "C = 'hub_data/trader_status.json'\n"
        "D = os.path.join(os.path.dirname(__file__), SETTINGS_FILE)\n"
        "E = 'see pt_config.json for details'\n"
        "def f():\n"
        "    '''Reads trading_config.json'''\n",
        encoding="utf-8",
    )
    lines = sorted(ln for ln, _ in violations_in(str(sample)))
    assert lines == [2, 3, 4, 5]
