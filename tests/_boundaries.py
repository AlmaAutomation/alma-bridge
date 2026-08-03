"""Shared read-only boundary helpers for architecture tests."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_IMPORT_FRAGMENTS = (
    "orchestrator",
    "verification_gateway",
    "session.mutations",
    "winetricks",
    "ActionIntent",
    "execution.",
    "learning.orchestrator",
    "session.services.planner",
    "remediation",
    "automation",
    "operator",
)

READ_ONLY_PACKAGES = (
    "graph",
    "knowledge",
    "regression",
    "comparison",
    "advisor",
    "ask",
    "catalog",
    "intelligence",
    "decision",
    "decision_review",
)


def py_files(path: Path) -> list[Path]:
    return sorted(p for p in path.rglob("*.py") if p.is_file())


def forbidden_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for fragment in FORBIDDEN_IMPORT_FRAGMENTS:
                if fragment in node.module:
                    hits.append(f"{path.relative_to(ROOT)}:{fragment}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                for fragment in FORBIDDEN_IMPORT_FRAGMENTS:
                    if fragment in alias.name:
                        hits.append(f"{path.relative_to(ROOT)}:{fragment}")
    return hits


def package_has_boundary_test(package: str) -> bool:
    tests_root = ROOT / "tests"
    if package == "intelligence":
        candidate = tests_root / "intelligence" / "test_architecture_boundaries.py"
    else:
        candidate = tests_root / package / f"test_{package}_architecture_boundaries.py"
    return candidate.is_file()
