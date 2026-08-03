"""PE parser tests (1-10)."""

from __future__ import annotations

import struct
from pathlib import Path

import pytest

from alma_bridge.native_runtime.errors import PEParseError
from alma_bridge.native_runtime.pe.headers import (
    IMAGE_DOS_SIGNATURE,
    IMAGE_NT_SIGNATURE,
    IMAGE_SUBSYSTEM_WINDOWS_CUI,
    read_dos_header,
)
from alma_bridge.native_runtime.pe.parser import parse_pe_bytes, parse_pe_file
from alma_bridge.native_runtime.pe.sections import read_section_headers
from tests.native_runtime.minimal_pe import minimal_pe_bytes as _minimal_pe_bytes

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "native_runtime" / "bin"


class TestPEParser:
    def test_01_dos_header_valid(self):
        dos = read_dos_header(_minimal_pe_bytes())
        assert dos.e_magic == IMAGE_DOS_SIGNATURE
        assert dos.e_lfanew == 128

    def test_02_dos_header_invalid(self):
        with pytest.raises(ValueError):
            read_dos_header(b"\x00" * 128)

    def test_03_pe_signature(self):
        data = _minimal_pe_bytes()
        sig = struct.unpack_from("<I", data, 128)[0]
        assert sig == IMAGE_NT_SIGNATURE

    def test_04_parse_pe_bytes_amd64(self):
        parsed = parse_pe_bytes("test.exe", _minimal_pe_bytes())
        assert parsed.is_pe32_plus is True
        assert parsed.coff.machine == 0x8664

    def test_05_parse_pe_bytes_i386(self):
        parsed = parse_pe_bytes("test.exe", _minimal_pe_bytes(machine=0x14C))
        assert parsed.is_pe32_plus is False

    def test_06_subsystem_console(self):
        parsed = parse_pe_bytes("test.exe", _minimal_pe_bytes())
        assert parsed.optional.subsystem == IMAGE_SUBSYSTEM_WINDOWS_CUI

    def test_07_section_headers(self):
        data = _minimal_pe_bytes()
        pe_off = struct.unpack_from("<I", data, 60)[0]
        sec_off = pe_off + 4 + 20 + 240
        sections = read_section_headers(data, sec_off, 1)
        assert sections[0].name == ".text"

    def test_08_invalid_pe_raises(self):
        with pytest.raises(PEParseError):
            parse_pe_bytes("bad.exe", b"not a pe")

    def test_09_parse_file_roundtrip(self, tmp_path: Path):
        pe = tmp_path / "sample.exe"
        pe.write_bytes(_minimal_pe_bytes())
        parsed = parse_pe_file(pe)
        assert parsed.file_path == str(pe)

    def test_10_fixture_pe_if_built(self):
        fixture = FIXTURES / "hello64.exe"
        if not fixture.is_file():
            pytest.skip("fixtures not built")
        parsed = parse_pe_file(fixture)
        assert parsed.is_pe32_plus
        assert "kernel32.dll" in parsed.import_dlls
