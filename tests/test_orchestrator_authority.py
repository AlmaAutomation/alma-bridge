"""Verify no route service imports BridgeOrchestrator."""

from __future__ import annotations

import ast
from pathlib import Path


def test_route_services_do_not_reference_orchestrator():
    root = Path(__file__).resolve().parents[1] / "alma_bridge" / "session" / "services"
    offenders = []
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module and "orchestrator" in node.module:
                offenders.append(str(path))
            if isinstance(node, ast.Import) and any("orchestrator" in alias.name for alias in node.names):
                offenders.append(str(path))
    assert offenders == []
