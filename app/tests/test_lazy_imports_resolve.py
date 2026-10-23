"""Every ``from <app module> import <name>`` names something that module defines.

An import inside a function only runs when the function does, so a name removed from
a module can break it without any import-time error: #144 removed
``pt_multi_exchange.multi_exchange_manager``, and the neural runner's
``from pt_multi_exchange import multi_exchange_manager`` then failed on every price
lookup, printing "Multi-exchange system not available, using legacy Robinhood".

This reads the source only (nothing is imported): for each app module it collects the
names defined at its top level, following ``from <app module> import *``.
"""

import ast
import os
import sys

APP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

SKIP_DIRS = {".venv", "venv", "__pycache__", "tests", ".git"}

# Known and left alone: order_execution_engine is used by nothing (roadmap #56, closed
# as not planned). Its ExecutionStatus import has never resolved, so the module always
# reports itself unavailable. Listed by name so a new break is not hidden behind it.
KNOWN = {("order_execution_engine.py", "order_management_models.ExecutionStatus")}


def _app_files():
    for folder, dirs, files in os.walk(APP_DIR):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name.endswith(".py") and not name.startswith("test_"):
                yield os.path.join(folder, name)


def _module_path(module):
    """The app file for a dotted module name, or None (stdlib / third party)."""
    base = os.path.join(APP_DIR, *module.split("."))
    for path in (base + ".py", os.path.join(base, "__init__.py")):
        if os.path.isfile(path):
            return path
    return None


_cache = {}


def _defined(module, seen=()):
    """Names defined at the top level of app ``module`` (None: anything may be, e.g.
    a module ``__getattr__`` or a star import from outside the app)."""
    if module in _cache:
        return _cache[module]
    path = _module_path(module)
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    names = set()
    open_ended = False
    statements = list(tree.body)
    while statements:
        node = statements.pop(0)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            if node.name == "__getattr__":
                open_ended = True
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for n in ast.walk(target):
                    if isinstance(n, ast.Name):
                        names.add(n.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    names.add(alias.asname or alias.name)
                elif (
                    node.module
                    and _module_path(node.module)
                    and node.module not in seen
                ):
                    star = _defined(node.module, seen + (module,))
                    if star is None:
                        open_ended = True
                    else:
                        names |= star
                else:
                    open_ended = True
        elif isinstance(node, (ast.If, ast.Try, ast.With, ast.For, ast.While)):
            for field in ("body", "orelse", "finalbody", "handlers"):
                for child in getattr(node, field, []) or []:
                    statements.extend(
                        child.body if isinstance(child, ast.ExceptHandler) else [child]
                    )
    result = None if open_ended else names
    _cache[module] = result
    return result


def test_every_name_imported_from_an_app_module_exists():
    missing = []
    for path in _app_files():
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read())
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level or not node.module:
                continue
            if _module_path(node.module) is None:
                continue  # stdlib or third party
            defined = _defined(node.module)
            if defined is None:
                continue
            for alias in node.names:
                if alias.name == "*" or alias.name in defined:
                    continue
                if _module_path(f"{node.module}.{alias.name}"):
                    continue  # a submodule
                rel = os.path.relpath(path, APP_DIR)
                if (rel, f"{node.module}.{alias.name}") in KNOWN:
                    continue
                missing.append(f"{rel}:{node.lineno} {node.module}.{alias.name}")
    assert not missing, "\n".join(missing)
