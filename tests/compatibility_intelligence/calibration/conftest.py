"""Shared fixtures for calibration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

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
    from alma_bridge.compatibility_intelligence.calibration_repository import CalibrationRepository

    return CalibrationRepository(store_dir=tmp_path / "calibration")
