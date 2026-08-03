"""Architecture boundary tests for the Decision Engine."""

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
from tests._boundaries import FORBIDDEN_IMPORT_FRAGMENTS, forbidden_imports, py_files

ROOT = Path(__file__).resolve().parents[2]
DECISION = ROOT / "alma_bridge" / "decision"


class TestDecisionArchitectureBoundaries:
    def test_decision_package_has_no_forbidden_imports(self):
        offenders: list[str] = []
        for path in py_files(DECISION):
            offenders.extend(forbidden_imports(path))
        assert offenders == []

    def test_decision_engine_has_no_graph_ingestion(self):
        source = (DECISION / "engine.py").read_text(encoding="utf-8")
        assert "GraphIngestionEngine" not in source
        assert "ingest_session" not in source
        assert "ingest_application" not in source

    def test_decision_engine_has_no_orchestrator(self):
        source = (DECISION / "engine.py").read_text(encoding="utf-8")
        assert "BridgeOrchestrator" not in source
        assert "orchestrator" not in source.lower()

    def test_decision_cannot_emit_action_intent(self):
        for path in py_files(DECISION):
            assert "ActionIntent" not in path.read_text(encoding="utf-8")

    def test_import_decision_routes_does_not_load_orchestrator(self):
        modules = (
            "alma_bridge.api.decision_routes",
            "alma_bridge.learning.orchestrator",
        )
        saved = {mod: sys.modules.get(mod) for mod in modules}
        try:
            for mod in modules:
                sys.modules.pop(mod, None)
            importlib.import_module("alma_bridge.api.decision_routes")
            assert "alma_bridge.learning.orchestrator" not in sys.modules
        finally:
            for mod, value in saved.items():
                if value is None:
                    sys.modules.pop(mod, None)
                else:
                    sys.modules[mod] = value

    def test_decision_routes_have_no_mutating_side_effect_markers(self):
        routes_path = ROOT / "alma_bridge" / "api" / "decision_routes.py"
        source = routes_path.read_text(encoding="utf-8")
        for banned in ("orchestrator", "record_attempt", "finalize_session", "ActionIntent"):
            assert banned not in source

    @pytest.fixture(autouse=True)
    def _store(self, tmp_path, monkeypatch):
        db = tmp_path / "outcomes.db"
        monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
        monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
        outcomes.init_outcome_store()

    def test_decision_get_does_not_trigger_graph_ingestion(self):
        from tests.intelligence.conftest import CODEBLOCKS_FINGERPRINT
        from tests.regression.conftest import seed_codeblocks_regression_sessions

        seed_codeblocks_regression_sessions()
        client = TestClient(create_app())
        with patch("alma_bridge.graph.ingestion.GraphIngestionEngine.ingest_application") as mocked:
            response = client.get(
                "/bridge/decision/plan",
                params={"application_fingerprint": CODEBLOCKS_FINGERPRINT},
            )
            assert response.status_code == 200
            mocked.assert_not_called()

    def test_decision_post_does_not_trigger_graph_ingestion(self):
        from tests.intelligence.conftest import CODEBLOCKS_FINGERPRINT
        from tests.regression.conftest import seed_codeblocks_regression_sessions

        seed_codeblocks_regression_sessions()
        client = TestClient(create_app())
        with patch("alma_bridge.graph.ingestion.GraphIngestionEngine.ingest_session") as mocked:
            response = client.post(
                "/bridge/decision/plan",
                json={"application_fingerprint": CODEBLOCKS_FINGERPRINT},
            )
            assert response.status_code == 200
            mocked.assert_not_called()

    def test_forbidden_fragments_include_execution_paths(self):
        assert "execution." in FORBIDDEN_IMPORT_FRAGMENTS
        assert "operator" in FORBIDDEN_IMPORT_FRAGMENTS
