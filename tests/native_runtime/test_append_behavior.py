"""Append_existing_file behavior fixture matrix."""

from __future__ import annotations

from pathlib import Path

import pytest

from alma_bridge.native_runtime.loader.entrypoint import shim_available
from alma_bridge.native_runtime.runtime import run_pe_in_workspace

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "native_runtime" / "bin"

APPEND_FIXTURES = [
    "append_existing_success.exe",
    "append_repeated.exe",
    "append_unicode.exe",
    "append_zero_length.exe",
    "append_invalid_handle.exe",
    "append_missing_file.exe",
    "append_path_traversal.exe",
    "append_overlapped_unsupported.exe",
    "file_append_unsupported.exe",
]


@pytest.fixture
def append_workspace(tmp_path: Path):
    (tmp_path / "seed.txt").write_text("seed\n", encoding="utf-8")
    (tmp_path / "repeat.txt").write_text("seed\n", encoding="utf-8")
    (tmp_path / "ünicode.txt").write_text("seed\n", encoding="utf-8")
    return tmp_path


class TestAppendBehaviorFixtures:
    @pytest.mark.parametrize("fixture_name", APPEND_FIXTURES)
    def test_append_fixture_exits_zero(self, append_workspace, fixture_name):
        path = FIXTURES / fixture_name
        if not path.is_file():
            pytest.skip("fixtures not built")
        if not shim_available():
            pytest.skip("native shim not built")
        result = run_pe_in_workspace(path, workspace=append_workspace)
        assert result.exit_code == 0
        assert result.success
        assert result.simulation_used is False

    def test_append_preserves_and_extends_content(self, append_workspace):
        path = FIXTURES / "append_existing_success.exe"
        if not path.is_file() or not shim_available():
            pytest.skip("native shim/fixtures required")
        run_pe_in_workspace(path, workspace=append_workspace)
        content = (append_workspace / "seed.txt").read_text(encoding="utf-8")
        assert content.startswith("seed\n")
        assert "appended by fixture" in content

    def test_repeated_append_ordering(self, append_workspace):
        path = FIXTURES / "append_repeated.exe"
        if not path.is_file() or not shim_available():
            pytest.skip("native shim/fixtures required")
        run_pe_in_workspace(path, workspace=append_workspace)
        content = (append_workspace / "repeat.txt").read_text(encoding="utf-8")
        assert content.index("first\n") < content.index("second\n")

    def test_historical_gap_fixture_passes(self, append_workspace):
        path = FIXTURES / "file_append_unsupported.exe"
        if not path.is_file() or not shim_available():
            pytest.skip("native shim/fixtures required")
        before = (append_workspace / "seed.txt").read_text(encoding="utf-8")
        result = run_pe_in_workspace(path, workspace=append_workspace)
        assert result.exit_code == 0
        after = (append_workspace / "seed.txt").read_text(encoding="utf-8")
        assert len(after) > len(before)
