from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from alma_bridge.compatibility.program_kind import (
    IMAGE_SUBSYSTEM_WINDOWS_CUI,
    IMAGE_SUBSYSTEM_WINDOWS_GUI,
    classify_program_kind,
    detect_installer,
    read_pe_subsystem,
)
from alma_bridge.execution.wine_gui_handoff import (
    WINE_GUI_HANDOFF_CONTRACT_VERSION,
    evaluate_wine_gui_launch_result,
)
from alma_bridge.execution.wine_process import (
    TargetGuiObservation,
    TargetProcessMatch,
    find_target_gui_processes,
    observe_target_gui_process,
    wine_has_target_gui_process,
)
from alma_bridge.learning.orchestrator import BridgeOrchestrator
from alma_bridge.schemas.models import BridgeRequest
from alma_bridge.session.services.verification import (
    WINE_GUI_POLICY_ID,
    DefaultVerificationEngine,
    ExecutionEvidence,
)
from alma_bridge.storage import outcomes
from alma_bridge.validation.setup_preflight import retrieve_persisted_verification
from tests.pe_test_helpers import write_minimal_pe


@pytest.fixture
def pe_gui(tmp_path):
    path = tmp_path / "app_gui.exe"
    write_minimal_pe(path, subsystem=IMAGE_SUBSYSTEM_WINDOWS_GUI)
    return path


@pytest.fixture
def pe_console(tmp_path):
    path = tmp_path / "app_console.exe"
    write_minimal_pe(path, subsystem=IMAGE_SUBSYSTEM_WINDOWS_CUI)
    return path


def test_pe_subsystem_fixture_values(pe_gui, pe_console):
    assert read_pe_subsystem(pe_gui) == IMAGE_SUBSYSTEM_WINDOWS_GUI
    assert read_pe_subsystem(pe_console) == IMAGE_SUBSYSTEM_WINDOWS_CUI


def test_classify_ordinary_gui_as_pe_windows_gui(pe_gui):
    kind = classify_program_kind(str(pe_gui))
    assert kind["program_kind"] == "pe_windows_gui"
    assert kind["is_wine_gui"] is True
    assert kind["needs_gui"] is True


def test_classify_console_pe_as_pe_windows(pe_console):
    kind = classify_program_kind(str(pe_console))
    assert kind["program_kind"] == "pe_windows"
    assert kind["is_wine_gui"] is False


def test_installer_precedence_over_gui_subsystem(tmp_path):
    installer = tmp_path / "game-setup.exe"
    write_minimal_pe(installer, subsystem=IMAGE_SUBSYSTEM_WINDOWS_GUI)
    assert detect_installer(installer) is True
    kind = classify_program_kind(str(installer))
    assert kind["program_kind"] == "pe_installer"


def test_electron_precedence_over_gui_subsystem(tmp_path):
    app_dir = tmp_path / "MyApp"
    app_dir.mkdir()
    exe = app_dir / "MyApp.exe"
    write_minimal_pe(exe, subsystem=IMAGE_SUBSYSTEM_WINDOWS_GUI)
    (app_dir / "resources.pak").write_bytes(b"x")
    (app_dir / "snapshot_blob.bin").write_bytes(b"x")
    (app_dir / "v8_context_snapshot.bin").write_bytes(b"x")
    kind = classify_program_kind(str(exe))
    assert kind["program_kind"] == "pe_electron_launcher"


def test_wine_gui_verification_uses_process_survives_policy():
    engine = DefaultVerificationEngine()
    evidence = ExecutionEvidence(
        session_id="sess",
        attempt_number=1,
        phase="wine_gui",
        result={
            "success": True,
            "stderr": "[Alma] GUI detached — process still running after 5s bootstrap.",
            "stdout": "",
            "exit_code": 0,
            "launch_verification": [
                "target_path=/tmp/notepad.exe",
                "appeared=True",
                "survived=True",
                "target_executable=notepad.exe",
                "process_survives=true",
            ],
        },
        file_path="/tmp/notepad.exe",
        wine_gui=True,
        wine_prefix="/tmp/prefix",
        launcher_path="/tmp/notepad.exe",
    )
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "alma_bridge.execution.wine_gui_handoff.observe_target_gui_process",
            lambda *args, **kwargs: TargetGuiObservation(
                target_path="/tmp/notepad.exe",
                appeared=True,
                survived=True,
                matches=[
                    TargetProcessMatch(
                        pid=4242,
                        cmdline="C:\\windows\\system32\\notepad.exe",
                        observed_at_monotonic=0.0,
                    )
                ],
            ),
        )
        result = engine.verify_execution(evidence)
    assert result.passed is True
    assert result.success_policy.policy_id == WINE_GUI_POLICY_ID
    assert any(c.check_kind == "process_survives" for c in result.checks)
    assert not any(c.check_kind == "exit_code_zero" for c in result.checks)


def test_wine_gui_rejects_unrelated_wineserver_only(monkeypatch, tmp_path):
    target = tmp_path / "notepad.exe"
    target.write_bytes(b"MZ")
    prefix = tmp_path / "prefix"
    prefix.mkdir()

    def fake_iter(_prefix):
        yield 100, "wineserver -p0"

    monkeypatch.setattr(
        "alma_bridge.execution.wine_process._iter_wine_cmdlines",
        fake_iter,
    )
    assert wine_has_target_gui_process(str(prefix), str(target)) is False


def test_wine_gui_recognizes_notepad_cmdline(monkeypatch, tmp_path):
    target = tmp_path / "system32/notepad.exe"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"MZ")
    prefix = tmp_path / "prefix"
    prefix.mkdir()

    def fake_iter(_prefix):
        yield 200, "Z:\\prefix\\drive_c\\windows\\system32\\notepad.exe"

    monkeypatch.setattr(
        "alma_bridge.execution.wine_process._iter_wine_cmdlines",
        fake_iter,
    )
    matches = find_target_gui_processes(str(prefix), str(target))
    assert len(matches) == 1
    assert matches[0].pid == 200


def test_wine_gui_recognizes_wordpad_cmdline(monkeypatch, tmp_path):
    target = tmp_path / "Accessories/wordpad.exe"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"MZ")
    prefix = tmp_path / "prefix"
    prefix.mkdir()

    def fake_iter(_prefix):
        yield 300, "C:\\Program Files\\Windows NT\\Accessories\\wordpad.exe"

    monkeypatch.setattr(
        "alma_bridge.execution.wine_process._iter_wine_cmdlines",
        fake_iter,
    )
    assert wine_has_target_gui_process(str(prefix), str(target)) is True


def test_immediate_process_death_fails(monkeypatch, tmp_path):
    target = tmp_path / "notepad.exe"
    target.write_bytes(b"MZ")
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    seen = {"count": 0}

    def fake_find(*args, **kwargs):
        seen["count"] += 1
        if seen["count"] == 1:
            return [
                TargetProcessMatch(
                    pid=400,
                    cmdline="system32\\notepad.exe",
                    observed_at_monotonic=0.0,
                )
            ]
        return []

    monkeypatch.setattr(
        "alma_bridge.execution.wine_process.find_target_gui_processes",
        fake_find,
    )
    monkeypatch.setattr("alma_bridge.execution.wine_process.time.sleep", lambda _sec: None)
    observation = observe_target_gui_process(
        str(prefix),
        str(target),
        startup_timeout_sec=1.0,
        survival_sec=0.1,
    )
    assert observation.appeared is True
    assert observation.survived is False


def test_evaluate_wine_gui_launch_result_success(monkeypatch, tmp_path):
    target = tmp_path / "notepad.exe"
    target.write_bytes(b"MZ")
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    monkeypatch.setattr(
        "alma_bridge.execution.wine_gui_handoff.observe_target_gui_process",
        lambda *args, **kwargs: TargetGuiObservation(
            target_path=str(target),
            appeared=True,
            survived=True,
            matches=[
                TargetProcessMatch(
                    pid=500,
                    cmdline="system32\\notepad.exe",
                    observed_at_monotonic=0.0,
                )
            ],
        ),
    )
    updated, signature, verification = evaluate_wine_gui_launch_result(
        {
            "success": True,
            "stderr": "[Alma] GUI detached — process still running after 5s bootstrap.",
            "stdout": "",
            "exit_code": 0,
        },
        wine_prefix=str(prefix),
        target_path=str(target),
    )
    assert signature is None
    assert updated["success"] is True
    assert any("process_survives=true" in line for line in verification)
    assert WINE_GUI_HANDOFF_CONTRACT_VERSION in "".join(verification)


def test_setup_preflight_retrieves_verification_via_get_session(tmp_path, monkeypatch):
    script = tmp_path / "ok.sh"
    script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    outcomes.init_outcome_store()
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.execute_attempt",
        lambda **kwargs: {
            "success": True,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "duration_ms": 1,
            "error_signature": None,
            "likely_causes": [],
        },
    )
    result = BridgeOrchestrator().run(
        BridgeRequest(file_path=str(script), max_attempts=1, auto_remediate=False)
    )
    verification = retrieve_persisted_verification(result.session_id)
    assert verification is not None
    assert verification.get("passed") is True
    assert "checks" in verification


def test_ordinary_wine_gui_skips_dotnet_bootstrap(tmp_path):
    from alma_bridge.learning.orchestrator import _artifact_needs_dotnet_bootstrap

    gui = tmp_path / "notepad.exe"
    write_minimal_pe(gui, subsystem=IMAGE_SUBSYSTEM_WINDOWS_GUI)
    kind = classify_program_kind(str(gui))
    assert kind["program_kind"] == "pe_windows_gui"
    assert _artifact_needs_dotnet_bootstrap(str(gui), kind) is False


def test_native_console_pe_still_uses_exit_code_contract(tmp_path, monkeypatch):
    script = tmp_path / "console.exe"
    write_minimal_pe(script, subsystem=IMAGE_SUBSYSTEM_WINDOWS_CUI)
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    outcomes.init_outcome_store()
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.execute_attempt",
        lambda **kwargs: {
            "success": True,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
            "duration_ms": 1,
            "error_signature": None,
            "likely_causes": [],
        },
    )
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.fresh_prefix_path",
        lambda _sid: str(tmp_path / "prefix"),
    )
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator._ensure_prefix_runtimes",
        lambda *args, **kwargs: None,
    )
    result = BridgeOrchestrator().run(
        BridgeRequest(file_path=str(script), max_attempts=1, auto_remediate=False)
    )
    verification = retrieve_persisted_verification(result.session_id)
    assert verification is not None
    assert any(
        check.get("check_kind") == "exit_code_zero"
        for check in verification.get("checks", [])
    )
