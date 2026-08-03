"""Analyzer tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from alma_bridge.compatibility_intelligence.analyzer import analyze_pe
from tests.native_runtime.minimal_pe import minimal_pe_bytes


class TestAnalyzer:
    def test_minimal_pe_metadata(self, tmp_path: Path):
        pe = tmp_path / "minimal.exe"
        pe.write_bytes(minimal_pe_bytes())
        _parsed, meta, digest = analyze_pe(str(pe))
        assert meta.architecture
        assert meta.subsystem
        assert meta.entry_point_rva >= 0
        assert meta.image_size > 0
        assert len(digest) == 64

    def test_hello64_imports(self, hello64_path):
        parsed, meta, digest = analyze_pe(str(hello64_path))
        assert "kernel32.dll" in parsed.import_dlls
        assert meta.is_pe32_plus is True
        assert not meta.has_clr

    def test_no_execution_occurs(self, hello64_path, monkeypatch):
        def _fail(*args, **kwargs):
            raise RuntimeError("execution attempted")

        monkeypatch.setattr("alma_bridge.native_runtime.runtime.run_pe_in_workspace", _fail)
        parsed, meta, digest = analyze_pe(str(hello64_path))
        assert parsed.file_path
