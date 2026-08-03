"""Architecture boundary tests for compatibility runtime providers."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "alma_bridge" / "runtime"

FORBIDDEN_IMPORT_FRAGMENTS = (
    "verification_gateway",
    "VerificationGateway",
    "learning.orchestrator",
    "BridgeOrchestrator",
    "session.mutations",
)


def _py_files(path: Path) -> list[Path]:
    return sorted(p for p in path.rglob("*.py") if p.is_file())


def _forbidden_imports(path: Path) -> list[str]:
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


class TestRuntimeArchitectureBoundaries:
    def test_providers_have_no_verification_gateway_imports(self):
        providers_dir = RUNTIME / "providers"
        offenders: list[str] = []
        for path in _py_files(providers_dir):
            offenders.extend(_forbidden_imports(path))
        assert offenders == []

    def test_runtime_package_has_no_orchestrator_imports(self):
        offenders: list[str] = []
        for path in _py_files(RUNTIME):
            offenders.extend(_forbidden_imports(path))
        assert offenders == []
