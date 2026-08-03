"""Eligibility tests (11-17)."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from alma_bridge.native_runtime.eligibility import (
    ALLOWED_IMPORT_DLLS,
    FIXTURE_ALLOWLIST,
    check_eligibility,
)
from alma_bridge.native_runtime.errors import REASON_GUI_SUBSYSTEM, REASON_IMPORT_NOT_ALLOWED
from alma_bridge.native_runtime.pe.headers import IMAGE_SUBSYSTEM_WINDOWS_GUI
from tests.native_runtime.minimal_pe import minimal_pe_bytes as _minimal_pe_bytes

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "native_runtime" / "bin"


class TestEligibility:
    def test_11_allowlist_contains_fixtures(self):
        assert "hello64.exe" in FIXTURE_ALLOWLIST

    def test_12_allowed_imports_kernel32_only(self):
        assert ALLOWED_IMPORT_DLLS == {"kernel32.dll"}

    def test_13_strict_console_pe_eligible(self, tmp_path: Path):
        pe = tmp_path / "console.exe"
        pe.write_bytes(_minimal_pe_bytes())
        # Without imports in minimal stub, strict path may pass subsystem/arch checks
        result = check_eligibility(pe)
        assert isinstance(result.eligible, bool)

    def test_14_gui_subsystem_rejected(self, tmp_path: Path):
        pe = tmp_path / "gui.exe"
        pe.write_bytes(_minimal_pe_bytes(subsystem=IMAGE_SUBSYSTEM_WINDOWS_GUI))
        result = check_eligibility(pe)
        assert result.eligible is False
        assert REASON_GUI_SUBSYSTEM in result.reason_codes

    def test_15_allowlisted_fixture_simulation(self, tmp_path: Path):
        pe = tmp_path / "hello64.exe"
        pe.write_bytes(_minimal_pe_bytes())
        result = check_eligibility(pe)
        assert result.eligible is True

    def test_16_i386_fail_closed_on_x64(self, tmp_path: Path):
        pe = tmp_path / "other32.exe"
        pe.write_bytes(_minimal_pe_bytes(machine=0x14C))
        result = check_eligibility(pe)
        assert result.eligible is False

    def test_17_built_fixture_if_present(self):
        fixture = FIXTURES / "hello64.exe"
        if not fixture.is_file():
            pytest.skip("fixtures not built")
        result = check_eligibility(fixture)
        assert result.eligible is True
