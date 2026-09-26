#!/usr/bin/env python3
"""Verify the repository's src-layout package boundary."""

import ast
from importlib.machinery import PathFinder
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "personal_agent"


def _require(condition, message, failures):
    if not condition:
        failures.append(message)


def _src_constants(node, assignments, seen=()):
    """Yield string constants reachable from ``node`` through module-level names."""
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            yield child.value
        elif isinstance(child, ast.Name) and child.id in assignments and child.id not in seen:
            yield from _src_constants(assignments[child.id], assignments, (*seen, child.id))


def _bootstraps_src(tree):
    """True when a real ``sys.path.insert/append`` call targets a ``src`` root."""
    assignments = {}
    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = statement.value
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("insert", "append")
                and ast.unparse(node.func.value) == "sys.path"):
            for value in _src_constants(node, assignments):
                if value == "src" or value.rstrip("/").endswith("/src"):
                    return True
    return False


def _package_imports(tree):
    """Return ``(module, names)`` for every personal_agent import in the script."""
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((alias.name, ()) for alias in node.names
                           if alias.name.split(".")[0] == "personal_agent")
        elif (isinstance(node, ast.ImportFrom) and node.level == 0 and node.module
              and node.module.split(".")[0] == "personal_agent"):
            imports.append((node.module, tuple(alias.name for alias in node.names)))
    return imports


def _find_spec(module, src_root):
    """Resolve ``module`` against ``src_root`` only, without executing any code."""
    spec, search = None, [str(src_root)]
    parts = module.split(".")
    for index in range(len(parts)):
        spec = PathFinder.find_spec(".".join(parts[:index + 1]), search)
        if spec is None:
            return None
        search = spec.submodule_search_locations
        if search is None and index + 1 < len(parts):
            return None
    return spec


def _top_level_names(tree):
    names, pending = set(), list(tree.body)
    while pending:
        statement = pending.pop()
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(statement.name)
        elif isinstance(statement, (ast.Import, ast.ImportFrom)):
            names.update((alias.asname or alias.name).split(".")[0] for alias in statement.names)
        elif isinstance(statement, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
            for target in targets:
                names.update(node.id for node in ast.walk(target) if isinstance(node, ast.Name))
        for field in ("body", "orelse", "finalbody", "handlers"):
            if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                pending.extend(getattr(statement, field, ()))
    return names


def _defines(spec, name):
    if spec.submodule_search_locations is not None:
        if PathFinder.find_spec(f"{spec.name}.{name}", spec.submodule_search_locations):
            return True
    if not spec.origin or not spec.origin.endswith(".py"):
        return True
    names = _top_level_names(ast.parse(Path(spec.origin).read_text(encoding="utf-8")))
    return "*" in names or "__getattr__" in names or name in names


def check_package_script(script, src_root):
    """Prove ``script`` bootstraps ``src_root`` and every package import it makes resolves there.

    The check is static: it parses the script and the imported package modules
    and uses the import system's path finder, so no script or package code runs.
    """
    tree = ast.parse(script.read_text(encoding="utf-8"), filename=str(script))
    failures = []
    if not _bootstraps_src(tree):
        failures.append(f"{script.name} does not bootstrap the src package root")
    imports = _package_imports(tree)
    if not imports:
        failures.append(f"{script.name} does not import personal_agent from the src root")
    for module, names in imports:
        spec = _find_spec(module, src_root)
        if spec is None:
            failures.append(f"{script.name} imports missing module {module}")
            continue
        for name in names:
            if not _defines(spec, name):
                failures.append(f"{script.name} imports missing name {module}.{name}")
    return failures


def main():
    failures = []
    _require(PACKAGE.is_dir(), "missing src/personal_agent package", failures)
    _require(not (ROOT / "personal_agent").exists(), "legacy root personal_agent exists", failures)

    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    _require('where = ["src"]' in pyproject, "setuptools src discovery is not configured", failures)
    _require('personal_agent = ["web/*.html", "web/*.css", "web/*.js"]' in pyproject,
             "personal_agent web package data is not configured", failures)
    for retired in ("delivery.py", "handoff.py", "delivery-plan.yaml"):
        _require(not (PACKAGE / retired).exists(),
                 f"repository-only {retired} is still shipped in personal_agent", failures)
    _require((ROOT / "scripts" / "dev" / "delivery.py").is_file(),
             "repository delivery controller is missing from scripts/dev", failures)
    _require((ROOT / "scripts" / "dev" / "handoff.py").is_file(),
             "repository handoff loop is missing from scripts/dev", failures)

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    engine_dockerfile = (ROOT / "Dockerfile.engine").read_text(encoding="utf-8")
    egress_dockerfile = (ROOT / "Dockerfile.egress").read_text(encoding="utf-8")
    _require("COPY src/personal_agent /app/src/personal_agent" in dockerfile,
             "Dockerfile does not preserve the src layout", failures)
    _require("COPY src/personal_agent /app/src/personal_agent" in engine_dockerfile,
             "Dockerfile.engine does not preserve the src layout", failures)
    _require("COPY src/personal_agent/limited_egress_proxy.py" in egress_dockerfile,
             "Dockerfile.egress does not copy the source package", failures)

    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
    _require("!src/personal_agent/" in dockerignore and "!src/personal_agent/**" in dockerignore,
             ".dockerignore does not include the source package", failures)

    package_scripts = (
        "agentos-backup.py",
        "agentos-restore.py",
        "operating_preflight.py",
        "verify_continuity_acceptance.py",
        "verify_document_acceptance.py",
        "verify_document_boundary.py",
        "verify_general_agent.py",
        "verify_telegram_task_card_acceptance.py",
        "verify_weather_acceptance.py",
    )
    for name in package_scripts:
        failures.extend(check_package_script(ROOT / "scripts" / name, ROOT / "src"))

    if failures:
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1
    print("src layout verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
