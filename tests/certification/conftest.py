"""Shared fixtures for certification platform tests."""

from __future__ import annotations

import pytest

from alma_bridge.certification.queries import CertificationQueries
from alma_bridge.certification.repository import CertificationRepository
from alma_bridge.certification.service import CertificationService
from alma_bridge.compatibility_intelligence.calibration_repository import CalibrationRepository
from alma_bridge.compatibility_intelligence.governance.repository import GovernanceRepository
from alma_bridge.evidence.repository import EvidenceRepository
from alma_bridge.native_engineering.queries import NativeEngineeringQueries
from alma_bridge.native_engineering.repository import NativeEngineeringRepository


@pytest.fixture
def certification_tmp_paths(tmp_path):
    return {
        "calibration": tmp_path / "calibration",
        "governance": tmp_path / "governance",
        "evidence": tmp_path / "evidence",
        "engineering": tmp_path / "native_engineering",
        "certification": tmp_path / "certification",
    }


@pytest.fixture
def certification_queries(certification_tmp_paths):
    engineering = NativeEngineeringQueries(
        calibration_repo=CalibrationRepository(store_dir=certification_tmp_paths["calibration"]),
        governance_repo=GovernanceRepository(store_dir=certification_tmp_paths["governance"]),
        evidence_repo=EvidenceRepository(store_dir=certification_tmp_paths["evidence"]),
        engineering_repo=NativeEngineeringRepository(store_dir=certification_tmp_paths["engineering"]),
    )
    return CertificationQueries(
        engineering_queries=engineering,
        certification_repo=CertificationRepository(store_dir=certification_tmp_paths["certification"]),
        governance_repo=GovernanceRepository(store_dir=certification_tmp_paths["governance"]),
        evidence_repo=EvidenceRepository(store_dir=certification_tmp_paths["evidence"]),
    )


@pytest.fixture
def certification_service(certification_queries, certification_tmp_paths):
    repo = CertificationRepository(store_dir=certification_tmp_paths["certification"])
    return CertificationService(queries=certification_queries, repository=repo)
