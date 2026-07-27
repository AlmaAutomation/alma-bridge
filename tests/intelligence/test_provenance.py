"""Provenance and fact-vs-hypothesis boundary tests."""

from __future__ import annotations

import pytest

from alma_bridge.intelligence.models import (
    CompatibilityFact,
    EvidenceReference,
    EvidenceSourceType,
    FactKind,
    FactStatus,
)
from alma_bridge.intelligence.service import CompatibilityIntelligenceService
from alma_bridge.storage import outcomes
from tests.intelligence.conftest import CODEBLOCKS_SESSION_ID, seed_codeblocks_session


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


def test_facts_require_evidence_references():
    with pytest.raises(ValueError, match="facts require at least one evidence reference"):
        CompatibilityFact(
            fact_id="fact:bad",
            kind=FactKind.VERIFIED_SUCCESSFUL_LAUNCH,
            status=FactStatus.PROVEN,
            statement="missing provenance",
            provenance=[],
            confidence=0.9,
        )


def test_verified_launch_fact_cites_verification_reference():
    seed_codeblocks_session()
    assessment = CompatibilityIntelligenceService().assess_session(CODEBLOCKS_SESSION_ID)
    launch = next(
        fact for fact in assessment.facts if fact.kind == FactKind.VERIFIED_SUCCESSFUL_LAUNCH
    )
    assert all(isinstance(ref, EvidenceReference) for ref in launch.provenance)
    assert all(ref.source_type == EvidenceSourceType.VERIFICATION for ref in launch.provenance)


def test_framework_fact_is_observed_not_proven():
    seed_codeblocks_session()
    assessment = CompatibilityIntelligenceService().assess_session(CODEBLOCKS_SESSION_ID)
    framework = next(fact for fact in assessment.facts if fact.kind == FactKind.USES_FRAMEWORK)
    assert framework.status == FactStatus.OBSERVED
