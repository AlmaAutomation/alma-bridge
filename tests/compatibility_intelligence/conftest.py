"""Shared fixtures for compatibility intelligence tests."""

from __future__ import annotations

from pathlib import Path

import pytest

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "native_runtime" / "bin"


@pytest.fixture
def hello64_path() -> Path:
    path = FIXTURES / "hello64.exe"
    if not path.is_file():
        pytest.skip("native_runtime fixtures not built")
    return path


@pytest.fixture
def exit_code_path() -> Path:
    path = FIXTURES / "exit_code.exe"
    if not path.is_file():
        pytest.skip("native_runtime fixtures not built")
    return path
