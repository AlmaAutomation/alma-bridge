"""Unit tests for wxWidgets framework detection and related error signatures."""

from __future__ import annotations

from pathlib import Path

import pytest

from alma_bridge.compatibility.framework_detection import (
    detect_gui_framework,
    is_wxwidgets_dll_name,
)
from alma_bridge.compatibility.program_kind import (
    IMAGE_SUBSYSTEM_WINDOWS_GUI,
    classify_program_kind,
)
from alma_bridge.execution.errors import (
    NON_RETRYABLE_SIGNATURES,
    detect_error_signature,
    is_single_instance_message,
    launch_failure_in_log,
)
from tests.pe_test_helpers import write_minimal_pe

FIXTURE_STDERR = (
    Path(__file__).parent / "fixtures" / "codeblocks_startup_stderr.txt"
).read_text(encoding="utf-8")


def _wxwidgets_app_dir(tmp_path: Path) -> Path:
    app_dir = tmp_path / "CodeBlocks"
    app_dir.mkdir()
    exe = app_dir / "codeblocks.exe"
    write_minimal_pe(exe, subsystem=IMAGE_SUBSYSTEM_WINDOWS_GUI, pe32plus=False)
    (app_dir / "wxmsw32u_gcc_custom.dll").write_bytes(b"MZ")
    return exe


def test_is_wxwidgets_dll_name_matches_imports():
    assert is_wxwidgets_dll_name("wxmsw32u_gcc_custom.dll")
    assert is_wxwidgets_dll_name("wxbase32u_vc.dll")
    assert not is_wxwidgets_dll_name("kernel32.dll")


def test_detect_wxwidgets_from_bundled_dlls(tmp_path):
    exe = _wxwidgets_app_dir(tmp_path)
    detection = detect_gui_framework(exe)
    assert detection.framework == "wxwidgets"
    assert detection.confidence >= 0.5
    assert detection.linkage == "dynamic"
    assert any(item.startswith("bundled_dll:") for item in detection.evidence)


def test_detect_wxwidgets_from_dll_imports(tmp_path, monkeypatch):
    exe = tmp_path / "app.exe"
    write_minimal_pe(exe, subsystem=IMAGE_SUBSYSTEM_WINDOWS_GUI)

    def fake_imports(path):
        assert path == exe
        return ["KERNEL32.dll", "wxmsw32u_gcc_custom.dll"]

    monkeypatch.setattr(
        "alma_bridge.compatibility.framework_detection._pe_import_dlls",
        fake_imports,
    )
    detection = detect_gui_framework(exe)
    assert detection.framework == "wxwidgets"
    assert detection.linkage == "dynamic"
    assert any(item == "pe_import:wxmsw32u_gcc_custom.dll" for item in detection.evidence)


def test_detect_wxwidgets_from_static_strings(tmp_path):
    exe = tmp_path / "custom.exe"
    payload = (
        b"MZ" + b"\x00" * 128
        + b"D:\\Devel\\wxWidgets32\\include/wx/event.h\x00"
        + b"wxmsw32u_gcc_custom.dll\x00"
    )
    exe.write_bytes(payload)
    detection = detect_gui_framework(exe)
    assert detection.framework == "wxwidgets"
    assert any("embedded_string" in item for item in detection.evidence)


def test_no_wxwidgets_from_name_alone(tmp_path):
    exe = tmp_path / "notepad.exe"
    write_minimal_pe(exe, subsystem=IMAGE_SUBSYSTEM_WINDOWS_GUI)
    detection = detect_gui_framework(exe)
    assert detection.framework == "unknown"
    assert detection.confidence == 0.0


def test_wxwidgets_preserves_pe_windows_gui(tmp_path):
    exe = _wxwidgets_app_dir(tmp_path)
    kind = classify_program_kind(str(exe))
    assert kind["program_kind"] == "pe_windows_gui"
    assert kind["is_wine_gui"] is True
    assert kind["framework"] == "wxwidgets"
    assert kind["is_electron"] is False


def test_compiler_inventory_does_not_trigger_missing_visual_c_runtime():
    assert detect_error_signature(FIXTURE_STDERR, "") != "missing_visual_c_runtime"
    assert launch_failure_in_log(FIXTURE_STDERR, "") is None


def test_actual_missing_vcruntime_still_triggers_signature():
    stderr = (
        "The program can't start because VCRUNTIME140.dll is missing from your computer."
    )
    assert detect_error_signature(stderr, "") == "missing_visual_c_runtime"
    assert launch_failure_in_log(stderr, "") == "missing_visual_c_runtime"


CODEBLOCKS_SINGLE_INSTANCE_STDERR = (
    "Starting Code::Blocks Release 25.03  rev 13644 Mar 30 2025, 09:20:24 - wxWidgets 3.2.7\r\n"
    "Ending application because another instance has been detected!\r\n"
)


def test_codeblock_single_instance_message_detected():
    assert is_single_instance_message(CODEBLOCKS_SINGLE_INSTANCE_STDERR)
    assert detect_error_signature(CODEBLOCKS_SINGLE_INSTANCE_STDERR, "") == "single_instance_detected"
    assert launch_failure_in_log(CODEBLOCKS_SINGLE_INSTANCE_STDERR, "") == "single_instance_detected"
    assert "single_instance_detected" in NON_RETRYABLE_SIGNATURES


def test_wxwidgets_detection_is_deterministic(tmp_path):
    exe = _wxwidgets_app_dir(tmp_path)
    first = detect_gui_framework(exe)
    second = detect_gui_framework(exe)
    assert first == second


def test_wxwidgets_detection_does_not_mutate_global_registry(tmp_path):
    exe = _wxwidgets_app_dir(tmp_path)
    before = detect_gui_framework(exe)
    after = detect_gui_framework(exe)
    assert before.framework == after.framework == "wxwidgets"


def test_non_wxwidgets_application_plan_is_unchanged(tmp_path):
    exe = tmp_path / "notepad.exe"
    write_minimal_pe(exe, subsystem=IMAGE_SUBSYSTEM_WINDOWS_GUI)
    kind = classify_program_kind(str(exe))
    assert kind["framework"] == "unknown"
    assert kind["program_kind"] == "pe_windows_gui"
