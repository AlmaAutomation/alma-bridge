"""Tests for assessment engine and service integration."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alma_bridge.intelligence.models import FactKind, FactStatus, HypothesisStatus
from alma_bridge.intelligence.service import CompatibilityIntelligenceService
from alma_bridge.main import create_app
from alma_bridge.storage import outcomes
from tests.intelligence.conftest import (
    CODEBLOCKS_FINGERPRINT,
    CODEBLOCKS_SESSION_ID,
    seed_codeblocks_session,
)


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


def test_codeblocks_assessment_labels_expected_facts_and_hypothesis():
    seed_codeblocks_session()
    assessment = CompatibilityIntelligenceService().assess_session(CODEBLOCKS_SESSION_ID)

    kinds = {fact.kind for fact in assessment.facts}
    assert FactKind.VERIFIED_SUCCESSFUL_LAUNCH in kinds
    assert FactKind.USES_FRAMEWORK in kinds
    assert FactKind.VERIFIED_WITH_STRATEGY in kinds

    launch_fact = next(
        fact for fact in assessment.facts if fact.kind == FactKind.VERIFIED_SUCCESSFUL_LAUNCH
    )
    assert launch_fact.status == FactStatus.PROVEN
    assert launch_fact.provenance

    framework_fact = next(fact for fact in assessment.facts if fact.kind == FactKind.USES_FRAMEWORK)
    assert framework_fact.status == FactStatus.OBSERVED
    assert framework_fact.attributes.get("framework") == "wxwidgets"

    strategy_fact = next(
        fact for fact in assessment.facts if fact.kind == FactKind.VERIFIED_WITH_STRATEGY
    )
    assert strategy_fact.attributes.get("strategy_id") == "wine_gui"
    assert strategy_fact.status == FactStatus.PROVEN

    runtime = next(
        hyp for hyp in assessment.hypotheses if hyp.hypothesis_id == "hypothesis:runtime_requirements"
    )
    assert runtime.status == HypothesisStatus.OPEN


def test_exit_code_zero_without_verification_pass_is_not_verified_launch():
    session_id = outcomes.new_session("/tmp/app.exe", "hash-exit-only", {})
    outcomes.record_attempt(
        session_id=session_id,
        attempt_number=1,
        strategy_id="native_host",
        remediation_id=None,
        runtime="native",
        command=["/tmp/app.exe"],
        env={},
        mode="host",
        success=True,
        exit_code=0,
        error_signature=None,
        detected_error=None,
        stdout="",
        stderr="",
        duration_ms=10,
        phase="native",
        verification={"passed": False, "confidence": 0.1, "checks": []},
    )
    assessment = CompatibilityIntelligenceService().assess_session(session_id)
    kinds = {fact.kind for fact in assessment.facts}
    assert FactKind.VERIFIED_SUCCESSFUL_LAUNCH not in kinds
    assert any("exit_code zero" in item for item in assessment.limitations)


def test_api_session_endpoint_returns_assessment():
    seed_codeblocks_session()
    client = TestClient(create_app())
    response = client.get(f"/bridge/intelligence/sessions/{CODEBLOCKS_SESSION_ID}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["engine_version"] == "compatibility_intelligence_v1"
    assert any(f["kind"] == "verified_successful_launch" for f in payload["facts"])


def test_api_application_endpoint_404_when_missing():
    client = TestClient(create_app())
    response = client.get("/bridge/intelligence/applications/unknown-fingerprint")
    assert response.status_code == 404


def test_api_application_endpoint_by_fingerprint():
    seed_codeblocks_session()
    client = TestClient(create_app())
    response = client.get(f"/bridge/intelligence/applications/{CODEBLOCKS_FINGERPRINT}")
    assert response.status_code == 200
    assert response.json()["application_fingerprint"] == CODEBLOCKS_FINGERPRINT
