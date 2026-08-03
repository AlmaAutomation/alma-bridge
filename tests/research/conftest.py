"""Shared fixtures for research platform tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from alma_bridge.compatibility_intelligence.calibration_repository import CalibrationRepository
from alma_bridge.compatibility_intelligence.calibration_service import CalibrationService
from alma_bridge.compatibility_intelligence.expansion.repository import ExpansionPlanRepository
from alma_bridge.compatibility_intelligence.governance.repository import GovernanceRepository
from alma_bridge.compatibility_intelligence.repository import AnalysisRepository
from alma_bridge.evidence.repository import EvidenceRepository
from alma_bridge.evidence.service import EvidenceService
from alma_bridge.research.queries import ResearchQueries
from alma_bridge.research.repository import ResearchRepository
from alma_bridge.research.service import ResearchService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "native_runtime" / "bin"


@pytest.fixture
def hello64_path() -> Path:
    path = FIXTURES / "hello64.exe"
    if not path.is_file():
        pytest.skip("native_runtime fixtures not built")
    return path


@pytest.fixture
def research_tmp_paths(tmp_path):
    return {
        "evidence": tmp_path / "evidence",
        "aci": tmp_path / "aci",
        "calibration": tmp_path / "calibration",
        "governance": tmp_path / "governance",
        "expansion": tmp_path / "expansion",
        "research": tmp_path / "research",
    }


@pytest.fixture
def research_queries(research_tmp_paths):
    return ResearchQueries(
        evidence_repo=EvidenceRepository(store_dir=research_tmp_paths["evidence"]),
        analysis_repo=AnalysisRepository(store_dir=research_tmp_paths["aci"]),
        calibration_repo=CalibrationRepository(store_dir=research_tmp_paths["calibration"]),
        calibration_service=CalibrationService(
            CalibrationRepository(store_dir=research_tmp_paths["calibration"])
        ),
        governance_repo=GovernanceRepository(store_dir=research_tmp_paths["governance"]),
        expansion_repo=ExpansionPlanRepository(store_dir=research_tmp_paths["expansion"]),
    )


@pytest.fixture
def research_service(research_queries, research_tmp_paths):
    from alma_bridge.evidence.builder import CompatibilityEvidenceBundleBuilder

    evidence_repo = EvidenceRepository(store_dir=research_tmp_paths["evidence"])
    builder = CompatibilityEvidenceBundleBuilder(
        analysis_repo=AnalysisRepository(store_dir=research_tmp_paths["aci"])
    )
    evidence_service = EvidenceService(repository=evidence_repo, builder=builder)
    return ResearchService(
        queries=research_queries,
        repository=ResearchRepository(store_dir=research_tmp_paths["research"]),
    ), evidence_service
