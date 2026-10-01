"""Architecture test: enforces the layering rules from PLAN.md.

Allowed imports between moneyflow subpackages:

    models   -> (stdlib / pydantic only)
    common   -> models
    ingest   -> models, common
    compute  -> models (pure: no I/O path, not even via common)
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
    # NOTE (red-team M7): PLAN.md says ingest/compute depend on models only.
    # ingest keeps common for the shared HTTP client; compute is pure and
    # gets models only. If compute ever needs a pure helper, it lives in
    # compute itself -- it must never gain an I/O path via common.
    "compute": frozenset({"models"}),
    "store": frozenset({"models", "common"}),
    "services": frozenset({"models", "common", "ingest", "compute", "store"}),
    "pipeline": frozenset({"models", "common", "ingest", "compute", "store", "services"}),
    "api": frozenset({"models", "common", "services"}),
}


def _package_of(path: Path) -> str:
    return path.relative_to(SRC).parts[0]


def _resolve_relative_import(path: Path, level: int, module: str | None) -> str | None:
    """Resolve `from .[.]* [module] import x` to an absolute dotted name.

    Red-team B2: the old code ignored relative imports entirely, so
    `from ..store import x` inside ingest/ passed the suite. Relative
    imports are now resolved against the importing file's package.
    """
    rel = path.relative_to(SRC).parts
    pkg_parts = ["moneyflow", *rel[:-1]]  # package containing this file
    if level - 1 > len(pkg_parts) - 1:
        return None  # escapes the top-level package; not our concern
    base = pkg_parts[: len(pkg_parts) - (level - 1)]
    if module:
        base = base + module.split(".")
    return ".".join(base)


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
            if node.level and node.level > 0:
                # Relative import (with or without a module part, e.g.
                # `from . import x` or `from ..store import x`): resolve
                # against the importing file's package, then check.
                resolved = _resolve_relative_import(path, node.level, node.module)
                if resolved:
                    parts = resolved.split(".")
                    if parts[0] == "moneyflow" and len(parts) > 1:
                        found.add(parts[1])
            elif node.module:
                parts = node.module.split(".")
                if parts[0] == "moneyflow" and len(parts) > 1:
                    found.add(parts[1])
    return found


def test_relative_imports_are_resolved():
    """Regression for red-team B2: relative-import smuggling must be caught."""
    from moneyflow import ingest  # noqa: F401  (package must exist)

    base = SRC / "ingest" / "ssga.py"
    assert _resolve_relative_import(base, 2, "store") == "moneyflow.store"
    assert _resolve_relative_import(base, 1, None) == "moneyflow.ingest"
    assert _resolve_relative_import(base, 1, "http") == "moneyflow.ingest.http"
    # level escaping the top-level package is ignored, not crashed on
    assert _resolve_relative_import(base, 5, "x") is None


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
