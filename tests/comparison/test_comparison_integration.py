"""Integration tests for environment-aware session comparison."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alma_bridge.comparison.service import SessionComparisonService
from alma_bridge.storage import outcomes
from tests.catalog.conftest import APP_A_FINGERPRINT
from tests.comparison.conftest import (
    COMPARE_BASELINE_SESSION,
    COMPARE_COMPARISON_SESSION,
    COMPARE_OTHER_APP_SESSION,
    seed_codeblocks_comparison_acceptance,
    seed_other_application_session,
)
from tests.intelligence.conftest import seed_codeblocks_session


@pytest.fixture
def isolated_comparison_store(tmp_path, monkeypatch):
    db_path = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db_path)
    outcomes.init_outcome_store()
    yield tmp_path


class TestSessionComparison:
    def test_same_app_sessions_compare_successfully(self, isolated_comparison_store):
        seed_codeblocks_comparison_acceptance()
        service = SessionComparisonService()
        report = service.compare_sessions(COMPARE_BASELINE_SESSION, COMPARE_COMPARISON_SESSION)
        assert report.application_fingerprint == APP_A_FINGERPRINT
        assert report.baseline_session_id == COMPARE_BASELINE_SESSION
        assert report.comparison_session_id == COMPARE_COMPARISON_SESSION

    def test_different_app_fingerprints_rejected(self, isolated_comparison_store):
        seed_codeblocks_comparison_acceptance()
        seed_other_application_session()
        service = SessionComparisonService()
        with pytest.raises(Exception) as exc:
            service.compare_sessions(COMPARE_BASELINE_SESSION, COMPARE_OTHER_APP_SESSION)
        assert "same application fingerprint" in str(exc.value).lower()

    def test_wine_version_change_detected(self, isolated_comparison_store):
        seed_codeblocks_comparison_acceptance()
        report = SessionComparisonService().compare_sessions(
            COMPARE_BASELINE_SESSION,
            COMPARE_COMPARISON_SESSION,
        )
        wine = next(item for item in report.environment_changes if item.field == "Wine")
        assert wine.changed is True
        assert "9.0" in (wine.before or "")
        assert "10.0" in (wine.after or "")

    def test_strategy_unchanged(self, isolated_comparison_store):
        seed_codeblocks_comparison_acceptance()
        report = SessionComparisonService().compare_sessions(
            COMPARE_BASELINE_SESSION,
            COMPARE_COMPARISON_SESSION,
        )
        strategy = next(item for item in report.execution_changes if item.field == "Strategy")
        assert strategy.changed is False
        assert strategy.before == strategy.after == "wine_gui"

    def test_verified_success_to_verified_failure(self, isolated_comparison_store):
        seed_codeblocks_comparison_acceptance()
        report = SessionComparisonService().compare_sessions(
            COMPARE_BASELINE_SESSION,
            COMPARE_COMPARISON_SESSION,
        )
        outcome = next(item for item in report.verification_changes if item.field == "Outcome")
        assert outcome.changed is True
        assert outcome.before == "verified success"
        assert outcome.after == "verified failure"

    def test_missing_legacy_environment_values_remain_null(self, isolated_comparison_store):
        seed_codeblocks_session()
        report = SessionComparisonService().compare_sessions(
            "4ecb0e85-af0c-4143-8b29-668cfccad37a",
            "4ecb0e85-af0c-4143-8b29-668cfccad37a",
        )
        wine = next(item for item in report.environment_changes if item.field == "Wine")
        assert wine.before is None
        assert wine.after is None
        assert wine.changed is False

    def test_no_causal_language(self, isolated_comparison_store):
        seed_codeblocks_comparison_acceptance()
        report = SessionComparisonService().compare_sessions(
            COMPARE_BASELINE_SESSION,
            COMPARE_COMPARISON_SESSION,
        )
        serialized = report.model_dump_json().lower()
        assert "caused" not in serialized
        assert "downgrade" not in serialized
        assert "install" not in serialized
        assert report.non_causality_notice is not None
        assert "does not infer causality" in report.non_causality_notice

    def test_every_changed_field_has_provenance(self, isolated_comparison_store):
        seed_codeblocks_comparison_acceptance()
        report = SessionComparisonService().compare_sessions(
            COMPARE_BASELINE_SESSION,
            COMPARE_COMPARISON_SESSION,
        )
        changed = [
            *report.environment_changes,
            *report.execution_changes,
            *report.verification_changes,
            *report.framework_changes,
            *report.runtime_changes,
        ]
        for item in changed:
            if item.changed:
                assert item.evidence_references, f"missing provenance for {item.field}"

    def test_deterministic_ordering(self, isolated_comparison_store):
        seed_codeblocks_comparison_acceptance()
        first = SessionComparisonService().compare_sessions(
            COMPARE_BASELINE_SESSION,
            COMPARE_COMPARISON_SESSION,
        )
        second = SessionComparisonService().compare_sessions(
            COMPARE_BASELINE_SESSION,
            COMPARE_COMPARISON_SESSION,
        )
        first_payload = first.model_dump()
        second_payload = second.model_dump()
        first_payload.pop("generated_at", None)
        second_payload.pop("generated_at", None)
        assert first_payload == second_payload

    def test_no_graph_ingestion_on_read(self, isolated_comparison_store):
        from unittest.mock import patch

        from alma_bridge.main import app

        seed_codeblocks_comparison_acceptance()
        client = TestClient(app)
        with patch("alma_bridge.graph.ingestion.GraphIngestionEngine.ingest_session") as mocked:
            response = client.get(
                f"/bridge/comparison/sessions/{COMPARE_BASELINE_SESSION}/{COMPARE_COMPARISON_SESSION}"
            )
            assert response.status_code == 200
            mocked.assert_not_called()

    def test_api_compare_sessions(self, isolated_comparison_store):
        from alma_bridge.main import app

        seed_codeblocks_comparison_acceptance()
        client = TestClient(app)
        response = client.get(
            f"/bridge/comparison/sessions/{COMPARE_BASELINE_SESSION}/{COMPARE_COMPARISON_SESSION}"
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["non_causality_notice"] is not None
        wine = next(item for item in payload["environment_changes"] if item["field"] == "Wine")
        assert wine["changed"] is True

    def test_api_rejects_different_fingerprints(self, isolated_comparison_store):
        from alma_bridge.main import app

        seed_codeblocks_comparison_acceptance()
        seed_other_application_session()
        client = TestClient(app)
        response = client.get(
            f"/bridge/comparison/sessions/{COMPARE_BASELINE_SESSION}/{COMPARE_OTHER_APP_SESSION}"
        )
        assert response.status_code == 422

    def test_api_missing_session_404(self, isolated_comparison_store):
        from alma_bridge.main import app

        client = TestClient(app)
        response = client.get(
            f"/bridge/comparison/sessions/{COMPARE_BASELINE_SESSION}/{COMPARE_COMPARISON_SESSION}"
        )
        assert response.status_code == 404
