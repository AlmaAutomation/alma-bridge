"""Tests for read-only evidence bundle construction."""

from __future__ import annotations

import pytest

from alma_bridge.intelligence.evidence import EvidenceBundleBuilder
from alma_bridge.intelligence.models import EvidenceSourceType, IntelligenceNotFoundError
from alma_bridge.intelligence.repository import OutcomesStoreAdapter
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


def test_for_session_builds_references_for_codeblocks():
    seed_codeblocks_session()
    builder = EvidenceBundleBuilder(OutcomesStoreAdapter())
    bundle = builder.for_session(CODEBLOCKS_SESSION_ID)

    source_types = {ref.source_type for ref in bundle.references}
    assert EvidenceSourceType.SESSION in source_types
    assert EvidenceSourceType.ATTEMPT in source_types
    assert EvidenceSourceType.VERIFICATION in source_types
    assert EvidenceSourceType.FRAMEWORK_DETECTION in source_types
    assert bundle.references == sorted(
        bundle.references,
        key=lambda ref: (ref.source_type.value, ref.source_id, ref.artifact_key),
    )


def test_for_application_aggregates_sessions_by_fingerprint():
    seed_codeblocks_session()
    builder = EvidenceBundleBuilder(OutcomesStoreAdapter())
    bundle = builder.for_application(CODEBLOCKS_FINGERPRINT)

    assert bundle.application_fingerprint == CODEBLOCKS_FINGERPRINT
    assert len(bundle.artifacts["sessions"]) == 1


def test_for_session_missing_raises_not_found():
    builder = EvidenceBundleBuilder(OutcomesStoreAdapter())
    with pytest.raises(IntelligenceNotFoundError):
        builder.for_session("missing-session")
