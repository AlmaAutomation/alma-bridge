"""Shared fixtures for native engineering platform tests."""

from __future__ import annotations

import pytest

from alma_bridge.compatibility_intelligence.calibration_repository import CalibrationRepository
from alma_bridge.compatibility_intelligence.governance.repository import GovernanceRepository
from alma_bridge.evidence.repository import EvidenceRepository
from alma_bridge.native_engineering.queries import NativeEngineeringQueries
from alma_bridge.native_engineering.repository import NativeEngineeringRepository
from alma_bridge.native_engineering.service import NativeEngineeringService


@pytest.fixture
def engineering_tmp_paths(tmp_path):
    return {
        "calibration": tmp_path / "calibration",
        "governance": tmp_path / "governance",
        "evidence": tmp_path / "evidence",
        "engineering": tmp_path / "native_engineering",
    }


@pytest.fixture
def engineering_queries(engineering_tmp_paths):
    return NativeEngineeringQueries(
        calibration_repo=CalibrationRepository(store_dir=engineering_tmp_paths["calibration"]),
        governance_repo=GovernanceRepository(store_dir=engineering_tmp_paths["governance"]),
        evidence_repo=EvidenceRepository(store_dir=engineering_tmp_paths["evidence"]),
        engineering_repo=NativeEngineeringRepository(store_dir=engineering_tmp_paths["engineering"]),
    )


@pytest.fixture
def engineering_service(engineering_queries, engineering_tmp_paths):
    repo = NativeEngineeringRepository(store_dir=engineering_tmp_paths["engineering"])
    return NativeEngineeringService(queries=engineering_queries, repository=repo)
