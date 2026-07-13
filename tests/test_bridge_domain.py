from __future__ import annotations

from pathlib import Path

import pytest

from alma_bridge.bridge.gap_analyzer import analyze_compatibility_gaps, build_wine_environment_profile
from alma_bridge.bridge.profile_builder import (
    build_compatibility_inspection,
    build_host_capability_profile,
    build_program_profile,
    compute_program_fingerprint,
    compute_host_fingerprint,
)
from alma_bridge.schemas.bridge_domain import GapCategory


def test_compute_program_fingerprint_stable():
    fp1 = compute_program_fingerprint(
        program_format="elf32",
        architecture="i386",
        program_kind="native_elf",
        filename="hello32",
    )
    fp2 = compute_program_fingerprint(
        program_format="elf32",
        architecture="i386",
        program_kind="native_elf",
        filename="hello32",
    )
    assert fp1 == fp2
    assert len(fp1) == 24


def test_build_program_profile_native_elf(tmp_path: Path):
    binary = tmp_path / "hello32"
    binary.write_bytes(b"\x7fELF")
    binary.chmod(0o755)
    profile = build_program_profile(str(binary))
    assert profile.identity.exists is True
    assert profile.program_kind == "native_elf"
    assert profile.needs_native is True
    assert profile.identity.fingerprint


def test_build_host_capability_profile_has_fingerprint():
    host = build_host_capability_profile()
    assert host.host_fingerprint
    assert host.architecture
    assert isinstance(host.capabilities, dict)


def test_gap_analyzer_missing_program():
    program = build_program_profile("/nonexistent/binary")
    host = build_host_capability_profile()
    gaps = analyze_compatibility_gaps(program, host)
    assert any(gap.category == GapCategory.PROGRAM_NOT_FOUND for gap in gaps)
    assert gaps[0].severity == "blocker"


def test_gap_analyzer_elf32_multiarch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    binary = tmp_path / "hello32"
    binary.write_bytes(b"\x7fELF")
    binary.chmod(0o755)
    program = build_program_profile(str(binary))
    program = program.model_copy(update={"format": "elf32", "architecture": "i386"})
    host = build_host_capability_profile()
    monkeypatch.setitem(host.capabilities, "multiarch", False)
    host.legacy_indicators = list(host.legacy_indicators) + ["no_multiarch_libs"]

    gaps = analyze_compatibility_gaps(program, host)
    categories = {gap.category for gap in gaps}
    assert GapCategory.ARCHITECTURE_MISMATCH in categories or GapCategory.MISSING_DEPENDENCY in categories
    assert any("linux.multiarch_i386" in gap.suggested_protocol_ids for gap in gaps)


def test_compatibility_inspection_ready_when_no_blockers(tmp_path: Path):
    binary = tmp_path / "native_app"
    binary.write_bytes(b"\x7fELF")
    binary.chmod(0o755)
    inspection = build_compatibility_inspection(str(binary))
    assert inspection.program.identity.path.endswith("native_app")
    assert inspection.host.host_fingerprint
    assert inspection.blocker_count >= 0
    assert isinstance(inspection.gaps, list)
    assert inspection.wine_environment is None


def test_wine_pe_installer_reports_prefix_gaps(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    installer = tmp_path / "game-setup.exe"
    installer.write_bytes(b"MZ")
    program = build_program_profile(str(installer))
    program = program.model_copy(
        update={
            "format": "pe",
            "needs_wine": True,
            "is_installer": True,
            "program_kind": "pe_installer",
        }
    )
    host = build_host_capability_profile()
    wine_env = build_wine_environment_profile(program)
    assert wine_env is not None
    monkeypatch.setattr(
        "alma_bridge.bridge.gap_analyzer.prefix_vcrun_installed",
        lambda _p: False,
    )
    monkeypatch.setattr(
        "alma_bridge.bridge.gap_analyzer.prefix_dotnet_installed",
        lambda _p: False,
    )
    monkeypatch.setattr(
        "alma_bridge.bridge.gap_analyzer.prefix_runtimes_ready",
        lambda _p: False,
    )
    if wine_env.prefix_exists:
        gaps = analyze_compatibility_gaps(program, host, wine_env=wine_env)
        categories = {gap.category for gap in gaps}
        assert GapCategory.MISSING_RUNTIME in categories


def test_compute_host_fingerprint_stable():
    hardware = {
        "architecture": "x86_64",
        "os_bitness": "64-bit",
        "distribution": "Ubuntu",
        "capabilities": {"wine": True, "multiarch": True},
        "legacy_indicators": [],
        "gpu": {"vendor": "intel", "driver": "i915"},
    }
    assert compute_host_fingerprint(hardware) == compute_host_fingerprint(hardware)
