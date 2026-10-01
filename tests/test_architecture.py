"""Architecture test: enforces the layering rules from PLAN.md.

Allowed imports between moneyflow subpackages:

    models   -> (stdlib / pydantic only)
    common   -> models
    ingest   -> models, common
    compute  -> models, common
    store    -> models, common
    services -> models, common, ingest, compute, store
    pipeline -> models, common, ingest, compute, store, services
    api      -> models, common, services

Rationale: adapters and pure compute must never touch the DB, the API
layer, or each other -- this is what keeps god objects from forming.
A violation fails the suite; it cannot be merged on a "looks fine".
"""

from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "moneyflow"

ALLOWED: dict[str, frozenset[str]] = {
    "models": frozenset(),
    "common": frozenset({"models"}),
    "ingest": frozenset({"models", "common"}),
    "compute": frozenset({"models", "common"}),
    "store": frozenset({"models", "common"}),
    "services": frozenset({"models", "common", "ingest", "compute", "store"}),
    "pipeline": frozenset({"models", "common", "ingest", "compute", "store", "services"}),
    "api": frozenset({"models", "common", "services"}),
}


def _package_of(path: Path) -> str:
    rel = path.relative_to(SRC).parts
    return rel[0] if path.name != "__init__.py" else (rel[0] if len(rel) > 1 else rel[0])


def _imported_subpackages(path: Path) -> set[str]:
    """Top-level moneyflow subpackages imported by this file."""
    tree = ast.parse(path.read_text())
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "moneyflow" and len(parts) > 1:
                    found.add(parts[1])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                parts = node.module.split(".")
                if parts[0] == "moneyflow" and len(parts) > 1:
                    found.add(parts[1])
            elif node.level and node.level > 0:
                # relative import: resolves inside the current subpackage
                pass
    return found


def test_layering_rules_hold():
    violations: list[str] = []
    for path in SRC.rglob("*.py"):
        pkg = _package_of(path)
        if pkg not in ALLOWED:
            continue
        for dep in _imported_subpackages(path):
            if dep == pkg:
                continue
            if dep not in ALLOWED[pkg]:
                violations.append(f"{path.relative_to(SRC)} [{pkg}] -> moneyflow.{dep}")
    assert not violations, "layering violations:\n" + "\n".join(violations)


def test_no_module_imports_api():
    """Nobody may depend on the web layer (api)."""
    offenders: list[str] = []
    for path in SRC.rglob("*.py"):
        if "moneyflow.api" in path.read_text():
            offenders.append(str(path.relative_to(SRC)))
    # api's own files legitimately mention moneyflow.api
    offenders = [o for o in offenders if not o.startswith("api/")]
    assert not offenders, f"non-api modules importing moneyflow.api: {offenders}"
