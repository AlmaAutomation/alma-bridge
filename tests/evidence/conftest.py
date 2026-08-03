"""Shared fixtures for evidence lifecycle tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from alma_bridge.evidence.repository import EvidenceRepository
from alma_bridge.evidence.service import EvidenceService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "native_runtime" / "bin"


@pytest.fixture
def hello64_path() -> Path:
    path = FIXTURES / "hello64.exe"
    if not path.is_file():
        pytest.skip("native_runtime fixtures not built")
    return path


@pytest.fixture
def evidence_repo(tmp_path) -> EvidenceRepository:
    return EvidenceRepository(store_dir=tmp_path / "evidence")


@pytest.fixture
def evidence_service(evidence_repo, tmp_path) -> EvidenceService:
    from alma_bridge.compatibility_intelligence.repository import AnalysisRepository
    from alma_bridge.evidence.builder import CompatibilityEvidenceBundleBuilder

    analysis_repo = AnalysisRepository(store_dir=tmp_path / "aci")
    builder = CompatibilityEvidenceBundleBuilder(analysis_repo=analysis_repo)
    return EvidenceService(repository=evidence_repo, builder=builder)
