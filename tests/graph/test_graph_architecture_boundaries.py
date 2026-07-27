"""Architecture boundary tests for Compatibility Graph."""

from __future__ import annotations

import ast
import importlib
import sqlite3
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[2]
GRAPH = ROOT / "alma_bridge" / "graph"

FORBIDDEN_IMPORT_FRAGMENTS = (
    "orchestrator",
    "verification_gateway",
    "session.mutations",
    "winetricks",
    "ActionIntent",
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


class TestGraphArchitectureBoundaries:
    def test_graph_package_has_no_forbidden_imports(self):
        offenders: list[str] = []
        for path in _py_files(GRAPH):
            offenders.extend(_forbidden_imports(path))
        assert offenders == []

    def test_ingestion_has_no_subprocess_or_execution_writes(self):
        source = (GRAPH / "ingestion.py").read_text(encoding="utf-8")
        assert "import subprocess" not in source
        assert "record_attempt" not in source
        assert "finalize_session" not in source

    def test_graph_api_routes_are_get_only(self):
        routes_path = ROOT / "alma_bridge" / "api" / "graph_routes.py"
        tree = ast.parse(routes_path.read_text(encoding="utf-8"))
        http_methods: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        if dec.func.attr == "get":
                            http_methods.append("GET")
                    if isinstance(dec, ast.Attribute) and dec.attr == "get":
                        http_methods.append("GET")
        assert http_methods
        assert all(method == "GET" for method in http_methods)

    def test_import_graph_routes_does_not_load_orchestrator(self):
        modules = (
            "alma_bridge.api.graph_routes",
            "alma_bridge.learning.orchestrator",
        )
        saved = {mod: sys.modules.get(mod) for mod in modules}
        try:
            for mod in modules:
                sys.modules.pop(mod, None)
            importlib.import_module("alma_bridge.api.graph_routes")
            assert "alma_bridge.learning.orchestrator" not in sys.modules
        finally:
            for mod, previous in saved.items():
                if previous is None:
                    sys.modules.pop(mod, None)
                else:
                    sys.modules[mod] = previous

    def test_import_graph_package_has_no_db_side_effects(self):
        calls: list[str] = []

        def _track(name: str):
            def _wrapper(*args, **kwargs):
                calls.append(name)

            return _wrapper

        with patch("alma_bridge.storage.outcomes.init_outcome_store", _track("init_outcome_store")):
            with patch(
                "alma_bridge.compatibility.profile_store.ensure_profile_tables",
                _track("ensure_profile_tables"),
            ):
                importlib.import_module("alma_bridge.graph")
        assert calls == []

    def test_graph_repository_reads_do_not_mutate_execution_stores(self, tmp_path, monkeypatch):
        db_path = tmp_path / "outcomes.db"
        monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
        monkeypatch.setattr("alma_bridge.config.settings.db_path", db_path)
        sqlite3.connect(db_path).close()

        from alma_bridge.graph.repository import ReadOnlyGraphEvidenceAdapter

        adapter = ReadOnlyGraphEvidenceAdapter()
        adapter.get_shadow_comparison("missing-session")

        with sqlite3.connect(db_path) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        assert "compatibility_profile_shadow_comparisons" not in tables

    def test_graph_service_source_has_no_action_intent(self):
        offenders: list[str] = []
        for path in _py_files(GRAPH):
            if "ActionIntent" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(ROOT)))
        assert offenders == []
