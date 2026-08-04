"""Security and lifecycle coverage for workspace-confined append."""

from __future__ import annotations

from pathlib import Path

import pytest

from alma_bridge.native_runtime.filesystem.paths import PathViolationError, resolve_workspace_path
from alma_bridge.native_runtime.loader.entrypoint import shim_available
from alma_bridge.native_runtime.runtime import run_pe_in_workspace

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "native_runtime" / "bin"


class TestAppendSecurity:
    def test_path_traversal_blocked_at_resolver(self, tmp_path: Path):
        with pytest.raises(PathViolationError):
            resolve_workspace_path(tmp_path, "..\\etc\\passwd")

    def test_absolute_outside_workspace_rejected(self, tmp_path: Path):
        with pytest.raises(PathViolationError):
            resolve_workspace_path(tmp_path, "..\\outside\\secret.txt")

    def test_traversal_fixture_fails_closed(self, tmp_path: Path):
        path = FIXTURES / "append_path_traversal.exe"
        if not path.is_file() or not shim_available():
            pytest.skip("native shim/fixtures required")
        (tmp_path / "seed.txt").write_text("secret\n", encoding="utf-8")
        result = run_pe_in_workspace(path, workspace=tmp_path)
        assert result.exit_code == 0
        assert (tmp_path / "seed.txt").read_text() == "secret\n"

    def test_missing_file_fixture(self, tmp_path: Path):
        path = FIXTURES / "append_missing_file.exe"
        if not path.is_file() or not shim_available():
            pytest.skip("native shim/fixtures required")
        result = run_pe_in_workspace(path, workspace=tmp_path)
        assert result.exit_code == 0
        assert not (tmp_path / "missing.txt").exists()

    def test_invalid_handle_fixture(self, tmp_path: Path):
        path = FIXTURES / "append_invalid_handle.exe"
        if not path.is_file() or not shim_available():
            pytest.skip("native shim/fixtures required")
        (tmp_path / "seed.txt").write_text("x\n", encoding="utf-8")
        result = run_pe_in_workspace(path, workspace=tmp_path)
        assert result.exit_code == 0

    def test_overlapped_unsupported_fixture(self, tmp_path: Path):
        path = FIXTURES / "append_overlapped_unsupported.exe"
        if not path.is_file() or not shim_available():
            pytest.skip("native shim/fixtures required")
        (tmp_path / "seed.txt").write_text("seed\n", encoding="utf-8")
        before = (tmp_path / "seed.txt").read_text()
        result = run_pe_in_workspace(path, workspace=tmp_path)
        assert result.exit_code == 0
        assert (tmp_path / "seed.txt").read_text() == before

    def test_oversized_write_within_workspace(self, tmp_path: Path):
        path = FIXTURES / "append_existing_success.exe"
        if not path.is_file() or not shim_available():
            pytest.skip("native shim/fixtures required")
        (tmp_path / "seed.txt").write_text("x" * 4096 + "\n", encoding="utf-8")
        result = run_pe_in_workspace(path, workspace=tmp_path)
        assert result.success
        assert (tmp_path / "seed.txt").stat().st_size > 4096
