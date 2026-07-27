"""Unit tests for wxWidgets-aware Wine GUI handoff evaluation."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from alma_bridge.compatibility.program_kind import IMAGE_SUBSYSTEM_WINDOWS_GUI
from alma_bridge.execution.wine_gui_handoff import (
    WXWIDGETS_READINESS_CONTRACT_VERSION,
    WINE_GUI_HANDOFF_CONTRACT_VERSION,
    evaluate_wine_gui_launch_result,
    evaluate_wxwidgets_readiness,
)
from tests.pe_test_helpers import write_minimal_pe

FIXTURE_STDERR = (
    Path(__file__).parent / "fixtures" / "codeblocks_startup_stderr.txt"
).read_text(encoding="utf-8")

CODEBLOCKS_SINGLE_INSTANCE_STDERR = (
    "Starting Code::Blocks Release 25.03  rev 13644 Mar 30 2025, 09:20:24 - wxWidgets 3.2.7\r\n"
    "Ending application because another instance has been detected!\r\n"
)


def _wxwidgets_app_dir(tmp_path: Path) -> Path:
    app_dir = tmp_path / "CodeBlocks"
    app_dir.mkdir()
    exe = app_dir / "codeblocks.exe"
    write_minimal_pe(exe, subsystem=IMAGE_SUBSYSTEM_WINDOWS_GUI, pe32plus=False)
    (app_dir / "wxmsw32u_gcc_custom.dll").write_bytes(b"MZ")
    return exe


def test_single_instance_with_live_process_passes_wine_gui(monkeypatch, tmp_path):
    target = _wxwidgets_app_dir(tmp_path)
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    monkeypatch.setattr(
        "alma_bridge.execution.wine_gui_handoff.observe_target_gui_process",
        lambda *args, **kwargs: SimpleNamespace(
            appeared=True,
            survived=True,
            to_evidence_lines=lambda: ["target_process=codeblocks.exe"],
            to_dict=lambda: {"pid": 9001},
        ),
    )
    updated, signature, verification = evaluate_wine_gui_launch_result(
        {
            "success": False,
            "exit_code": 255,
            "stderr": CODEBLOCKS_SINGLE_INSTANCE_STDERR,
            "stdout": "",
        },
        wine_prefix=str(prefix),
        target_path=str(target),
        framework="wxwidgets",
    )
    assert signature is None
    assert updated["success"] is True
    assert "single_instance_guard=true" in verification
    assert "existing_target_process=true" in verification


def test_single_instance_without_process_fails(monkeypatch, tmp_path):
    target = _wxwidgets_app_dir(tmp_path)
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    monkeypatch.setattr(
        "alma_bridge.execution.wine_gui_handoff.observe_target_gui_process",
        lambda *args, **kwargs: SimpleNamespace(
            appeared=False,
            survived=False,
            to_evidence_lines=lambda: [],
            to_dict=lambda: {},
        ),
    )
    updated, signature, verification = evaluate_wine_gui_launch_result(
        {
            "success": False,
            "exit_code": 255,
            "stderr": CODEBLOCKS_SINGLE_INSTANCE_STDERR,
            "stdout": "",
        },
        wine_prefix=str(prefix),
        target_path=str(target),
        framework="wxwidgets",
    )
    assert signature == "single_instance_detected"
    assert updated["success"] is False
    assert "single_instance_guard_blocked_launch" in verification


def test_wxwidgets_readiness_passes_with_codeblock_progression():
    ok, evidence = evaluate_wxwidgets_readiness(FIXTURE_STDERR)
    assert ok is True
    assert "manager_initialized=true" in evidence
    assert "compiler_plugin_activated=true" in evidence
    assert "compiler_detection_progress=true" in evidence
    assert WXWIDGETS_READINESS_CONTRACT_VERSION in "".join(evidence)


def test_splash_only_wxwidgets_readiness_fails():
    stderr = (
        "Starting Code::Blocks Release 25.03 - wxWidgets 3.2.7 - gcc 14.2.0"
    )
    ok, evidence = evaluate_wxwidgets_readiness(stderr)
    assert ok is False
    assert "splash_only_insufficient=true" in evidence


def test_wxwidgets_readiness_passes_end_to_end(monkeypatch, tmp_path):
    target = _wxwidgets_app_dir(tmp_path)
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    monkeypatch.setattr(
        "alma_bridge.execution.wine_gui_handoff.observe_target_gui_process",
        lambda *args, **kwargs: SimpleNamespace(
            appeared=True,
            survived=True,
            to_evidence_lines=lambda: ["target_process=codeblocks.exe"],
            to_dict=lambda: {"pid": 9001},
        ),
    )
    updated, signature, verification = evaluate_wine_gui_launch_result(
        {
            "success": True,
            "stderr": FIXTURE_STDERR,
            "stdout": "",
            "exit_code": 0,
        },
        wine_prefix=str(prefix),
        target_path=str(target),
        framework="wxwidgets",
    )
    assert signature is None
    assert updated["success"] is True
    assert WINE_GUI_HANDOFF_CONTRACT_VERSION == "wine_gui_process_v2"
    assert any("compiler_plugin_activated=true" in line for line in verification)


def test_wxwidgets_evidence_has_detector_provenance(tmp_path):
    target = _wxwidgets_app_dir(tmp_path)
    from alma_bridge.compatibility.framework_detection import detect_gui_framework

    detection = detect_gui_framework(target)
    assert detection.framework == "wxwidgets"
    assert detection.evidence
