"""Shared fixtures for governance tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from alma_bridge.compatibility_intelligence.calibration_repository import CalibrationRepository
from alma_bridge.compatibility_intelligence.governance.repository import GovernanceRepository

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
def tmp_calibration_repo(tmp_path):
    return CalibrationRepository(store_dir=tmp_path / "calibration")


@pytest.fixture
def tmp_governance_repo(tmp_path):
    return GovernanceRepository(store_dir=tmp_path / "governance")


@pytest.fixture
def governance_service(tmp_governance_repo, tmp_calibration_repo):
    from alma_bridge.compatibility_intelligence.calibration_service import CalibrationService
    from alma_bridge.compatibility_intelligence.governance.service import GovernanceService

    return GovernanceService(
        repository=tmp_governance_repo,
        calibration=CalibrationService(repository=tmp_calibration_repo),
    )
