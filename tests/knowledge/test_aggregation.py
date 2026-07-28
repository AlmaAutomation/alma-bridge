"""Tests for knowledge aggregation engine."""

from __future__ import annotations

import pytest

from alma_bridge.knowledge.aggregation import KnowledgeAggregationEngine
from alma_bridge.knowledge.models import EvidenceClassification
from alma_bridge.knowledge.service import CompatibilityKnowledgeService
from alma_bridge.storage import outcomes
from tests.intelligence.conftest import CODEBLOCKS_FINGERPRINT, seed_codeblocks_session
from tests.knowledge.conftest import seed_codeblocks_knowledge_sessions


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


def test_codeblocks_knowledge_acceptance_fixture():
    seed_codeblocks_knowledge_sessions()
    profile = CompatibilityKnowledgeService().profile_for_application(CODEBLOCKS_FINGERPRINT)

    assert profile.total_sessions == 4
    assert profile.verified_successes == 2
    assert profile.verified_failures == 1
    assert profile.unverifiable_sessions == 1

    frameworks = {item.framework: item for item in profile.observed_frameworks}
    assert frameworks["wxwidgets"].observation_count == 3
    assert frameworks["wxwidgets"].classification == EvidenceClassification.CONFLICTING
    assert frameworks["qt"].observation_count == 1
    assert frameworks["qt"].classification == EvidenceClassification.CONFLICTING

    wine_gui = next(item for item in profile.observed_launch_strategies if item.strategy == "wine_gui")
    assert wine_gui.attempts == 4
    assert wine_gui.verified_successes == 2
    assert wine_gui.verified_failures == 1
    assert wine_gui.success_rate == pytest.approx(2 / 3, rel=1e-3)

    assert len(profile.conflicts) == 1
    conflict = profile.conflicts[0]
    assert set(conflict.competing_observations) == {"wxwidgets", "qt"}
    assert "wxwidgets" in conflict.evidence_by_side
    assert "qt" in conflict.evidence_by_side


def test_exit_code_success_without_verification_not_counted_as_verified():
    session_id = outcomes.new_session("/tmp/app.exe", "exit-only-hash", {})
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
    outcomes.finalize_session(session_id, success=True, summary="exit only")

    profile = CompatibilityKnowledgeService().profile_for_application("exit-only-hash")
    assert profile.verified_successes == 0
    assert profile.verified_failures == 1


def test_single_session_framework_is_repeated_not_conflicting():
    seed_codeblocks_session()
    seed_codeblocks_session(session_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    profile = CompatibilityKnowledgeService().profile_for_application(CODEBLOCKS_FINGERPRINT)
    wx = next(item for item in profile.observed_frameworks if item.framework == "wxwidgets")
    assert wx.classification == EvidenceClassification.REPEATED
    assert profile.conflicts == []


def test_aggregation_is_deterministic():
    seed_codeblocks_knowledge_sessions()
    service = CompatibilityKnowledgeService()
    first = service.profile_for_application(CODEBLOCKS_FINGERPRINT).model_dump()
    second = service.profile_for_application(CODEBLOCKS_FINGERPRINT).model_dump()
    first.pop("generated_at")
    second.pop("generated_at")
    assert first == second


def test_all_aggregate_claims_include_evidence_references():
    seed_codeblocks_knowledge_sessions()
    profile = CompatibilityKnowledgeService().profile_for_application(CODEBLOCKS_FINGERPRINT)

    for framework in profile.observed_frameworks:
        assert framework.evidence_references
    for strategy in profile.observed_launch_strategies:
        assert strategy.evidence_references
    for contract in profile.verification_contracts:
        assert contract.evidence_references
    for runtime in profile.observed_runtimes:
        assert runtime.evidence_references


def test_observed_runtimes_use_runtime_observed_not_required():
    seed_codeblocks_knowledge_sessions()
    profile = CompatibilityKnowledgeService().profile_for_application(CODEBLOCKS_FINGERPRINT)
    dumped = profile.model_dump_json()
    assert "runtime_required" not in dumped
    assert "confirmed_required" not in dumped.lower()
    wine = next(item for item in profile.observed_runtimes if item.runtime == "wine")
    assert wine.observation_count == 4


def test_verification_contract_pass_and_fail_counts():
    seed_codeblocks_knowledge_sessions()
    profile = CompatibilityKnowledgeService().profile_for_application(CODEBLOCKS_FINGERPRINT)
    contract = profile.verification_contracts[0]
    assert contract.passed_count == 2
    assert contract.failed_count == 1


def test_competing_frameworks_are_not_collapsed():
    seed_codeblocks_knowledge_sessions()
    profile = CompatibilityKnowledgeService().profile_for_application(CODEBLOCKS_FINGERPRINT)
    framework_names = {item.framework for item in profile.observed_frameworks}
    assert framework_names == {"wxwidgets", "qt"}


def test_engine_has_no_sql():
    source = KnowledgeAggregationEngine.__module__
    from pathlib import Path

    path = Path(source.replace(".", "/") + ".py")
    if not path.is_file():
        path = Path(__file__).resolve().parents[2] / "alma_bridge" / "knowledge" / "aggregation.py"
    text = path.read_text(encoding="utf-8")
    assert "sqlite" not in text.lower()
    assert "execute(" not in text
