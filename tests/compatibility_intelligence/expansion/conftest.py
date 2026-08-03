"""Shared fixtures for expansion planning tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from alma_bridge.compatibility_intelligence.calibration_repository import CalibrationRepository
from alma_bridge.compatibility_intelligence.expansion.repository import ExpansionPlanRepository
from alma_bridge.compatibility_intelligence.expansion.service import ExpansionPlanningService
from alma_bridge.compatibility_intelligence.governance.repository import GovernanceRepository
from alma_bridge.compatibility_intelligence.repository import AnalysisRepository

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "native_runtime" / "bin"


@pytest.fixture
def hello64_path() -> Path:
    path = FIXTURES / "hello64.exe"
    if not path.is_file():
        pytest.skip("native_runtime fixtures not built")
    return path


@pytest.fixture
def file_append_unsupported_path() -> Path:
    path = FIXTURES / "file_append_unsupported.exe"
    if not path.is_file():
        pytest.skip("file_append_unsupported fixture not built")
    return path


@pytest.fixture
def tmp_analysis_repo(tmp_path):
    return AnalysisRepository(store_dir=tmp_path / "analyses")


@pytest.fixture
def tmp_calibration_repo(tmp_path):
    return CalibrationRepository(store_dir=tmp_path / "calibration")


@pytest.fixture
def tmp_governance_repo(tmp_path):
    return GovernanceRepository(store_dir=tmp_path / "governance")


@pytest.fixture
def tmp_plan_repo(tmp_path):
    return ExpansionPlanRepository(store_dir=tmp_path / "expansion")


@pytest.fixture
def expansion_service(
    tmp_analysis_repo,
    tmp_calibration_repo,
    tmp_governance_repo,
    tmp_plan_repo,
):
    return ExpansionPlanningService(
        analysis_repo=tmp_analysis_repo,
        calibration_repo=tmp_calibration_repo,
        governance_repo=tmp_governance_repo,
        plan_repo=tmp_plan_repo,
    )
