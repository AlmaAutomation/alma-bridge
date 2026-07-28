"""Architecture boundary tests for Compatibility Advisor."""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alma_bridge.main import create_app
from alma_bridge.storage import outcomes

ROOT = Path(__file__).resolve().parents[2]
ADVISOR = ROOT / "alma_bridge" / "advisor"

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


class TestAdvisorArchitectureBoundaries:
    def test_advisor_package_has_no_forbidden_imports(self):
        offenders: list[str] = []
        for path in _py_files(ADVISOR):
            offenders.extend(_forbidden_imports(path))
        assert offenders == []

    def test_explanation_engine_has_no_graph_ingestion(self):
        source = (ADVISOR / "explanation.py").read_text(encoding="utf-8")
        assert "GraphIngestionEngine" not in source
        assert "record_attempt" not in source

    def test_advisor_api_routes_are_get_only(self):
        routes_path = ROOT / "alma_bridge" / "api" / "advisor_routes.py"
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

    def test_import_advisor_routes_does_not_load_orchestrator(self):
        modules = (
            "alma_bridge.api.advisor_routes",
            "alma_bridge.learning.orchestrator",
        )
        saved = {mod: sys.modules.get(mod) for mod in modules}
        try:
            for mod in modules:
                sys.modules.pop(mod, None)
            importlib.import_module("alma_bridge.api.advisor_routes")
            assert "alma_bridge.learning.orchestrator" not in sys.modules
        finally:
            for mod, value in saved.items():
                if value is None:
                    sys.modules.pop(mod, None)
                else:
                    sys.modules[mod] = value

    def test_advisor_cannot_emit_action_intent(self):
        for path in _py_files(ADVISOR):
            source = path.read_text(encoding="utf-8")
            assert "ActionIntent" not in source

    @pytest.fixture(autouse=True)
    def _store(self, tmp_path, monkeypatch):
        db = tmp_path / "outcomes.db"
        monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
        monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
        outcomes.init_outcome_store()

    def test_advisor_get_does_not_trigger_graph_ingestion(self):
        from tests.regression.conftest import seed_codeblocks_regression_sessions
        from tests.intelligence.conftest import CODEBLOCKS_FINGERPRINT

        seed_codeblocks_regression_sessions()
        client = TestClient(create_app())
        with patch("alma_bridge.graph.ingestion.GraphIngestionEngine.ingest_session") as mocked:
            response = client.get(f"/bridge/advisor/applications/{CODEBLOCKS_FINGERPRINT}")
            assert response.status_code == 200
            mocked.assert_not_called()

    def test_llm_package_has_no_forbidden_imports(self):
        llm_dir = ROOT / "alma_bridge" / "advisor" / "llm"
        offenders: list[str] = []
        for path in _py_files(llm_dir):
            offenders.extend(_forbidden_imports(path))
        assert offenders == []
