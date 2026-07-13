from __future__ import annotations

from pathlib import Path

from alma_bridge.execution.electron_handoff import (
    SIDECAR_HANDOFF_CONTRACT_VERSION,
    client_services_handoff_verified,
    detect_electron_launcher_failure,
    evaluate_electron_launch_result,
    format_electron_launch_stderr,
    parse_sidecar_handoff_evidence,
    sidecar_exited_successfully,
    sidecar_produced_output,
    watch_sidecar_handoff,
)
from alma_bridge.execution.errors import detect_error_signature
from alma_bridge.execution.wine_process import wine_has_main_launcher_process
from alma_bridge.learning.remediation import (
    next_electron_launcher_remediation,
    next_launcher_remediation,
)


def test_detect_client_services_stalled(tmp_path):
    stderr = "[client-services] Launching elevated: C:\\Program Files\\Ascension Launcher\\resources\\AscensionClientServices.exe\n"
    prefix = tmp_path / "prefix"
    (prefix / "drive_c").mkdir(parents=True)
    assert (
        detect_electron_launcher_failure(
            stderr, "", exit_code=3, wine_prefix=str(prefix)
        )
        == "client_services_stalled"
    )


def test_crashpad_log_does_not_mask_client_services_stall(tmp_path):
    prefix = tmp_path / "prefix"
    (prefix / "drive_c").mkdir(parents=True)
    stderr = (
        "[client-services] Launching elevated\n"
        "crash server failed to launch, self-terminating\n"
    )
    assert (
        detect_electron_launcher_failure(
            stderr, "", exit_code=3, wine_prefix=str(prefix)
        )
        == "client_services_stalled"
    )


def test_crashpad_signature_beats_file_not_found():
    log = "CreateFile: File not found.\ncrash server failed to launch, self-terminating"
    assert detect_error_signature(log, "") == "electron_crashpad_failure"


def test_launcher_remediation_chain_order():
    tried = set()
    first = next_electron_launcher_remediation(tried)
    assert first and first["id"] == "ascension_int3_full_repair"
    tried.add(first["id"])
    second = next_electron_launcher_remediation(tried)
    assert second and second["id"] == "ascension_int3_guard_refresh"
    tried.add(second["id"])
    third = next_electron_launcher_remediation(tried)
    assert third and third["id"] == "electron_update_check_offline"
    tried.add(third["id"])
    fourth = next_electron_launcher_remediation(tried)
    assert fourth and fourth["id"] == "electron_disable_crashpad"


def test_signature_specific_launcher_remediation_precedes_generic_chain():
    tried: set[str | None] = set()
    action = next_launcher_remediation("wine_int3_crash", tried)
    assert action and action["id"] == "ascension_int3_full_repair"


def test_sidecar_only_does_not_succeed(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "alma_bridge.execution.electron_handoff.wait_for_main_launcher_process",
        lambda *args, **kwargs: False,
    )
    monkeypatch.setattr(
        "alma_bridge.execution.electron_handoff.watch_sidecar_handoff",
        lambda *args, **kwargs: (
            "client_services_stalled",
            "No sidecar progress within 30s after handoff.",
        ),
    )
    prefix = tmp_path / "prefix"
    (prefix / "drive_c").mkdir(parents=True)
    stderr = "[client-services] Launching elevated\n"
    result, signature, _ = evaluate_electron_launch_result(
        {"success": False, "exit_code": 3, "stderr": stderr, "stdout": ""},
        wine_prefix=str(prefix),
        launcher_path="/tmp/drive_c/Program Files/Ascension Launcher/Ascension Launcher.exe",
        wait_sec=0.1,
    )
    assert result["success"] is False
    assert signature == "client_services_stalled"


def test_bootstrap_alive_does_not_override_stalled_handoff(monkeypatch, tmp_path):
    """Main launcher during bootstrap must not count as success when sidecar is empty."""
    monkeypatch.setattr(
        "alma_bridge.execution.electron_handoff.wait_for_main_launcher_process",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "alma_bridge.execution.electron_handoff.wine_has_main_launcher_process",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "alma_bridge.execution.electron_handoff.watch_sidecar_handoff",
        lambda *args, **kwargs: (
            "client_services_stalled",
            "No sidecar progress within 30s after handoff.",
        ),
    )
    prefix = tmp_path / "prefix"
    (prefix / "drive_c").mkdir(parents=True)
    stderr = "[client-services] Launching elevated\n"
    result, signature, _ = evaluate_electron_launch_result(
        {"success": False, "exit_code": 3, "stderr": stderr, "stdout": ""},
        wine_prefix=str(prefix),
        launcher_path="/tmp/Ascension Launcher.exe",
        wait_sec=0.1,
    )
    assert result["success"] is False
    assert signature == "client_services_stalled"


def test_evaluate_marks_success_when_sidecar_output_exists(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "alma_bridge.execution.electron_handoff.wait_for_main_launcher_process",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "alma_bridge.execution.electron_handoff.wine_has_main_launcher_process",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "alma_bridge.execution.electron_handoff.watch_sidecar_handoff",
        lambda *args, **kwargs: (None, "Sidecar handoff verified during watchdog."),
    )
    prefix = tmp_path / "prefix"
    drive_c = prefix / "drive_c"
    drive_c.mkdir(parents=True)
    (drive_c / "alma-cs-output.log").write_text("sidecar listening on 127.0.0.1\n", encoding="utf-8")
    stderr = "[client-services] Launching elevated\n"
    result, signature, reasons = evaluate_electron_launch_result(
        {"success": False, "exit_code": 3, "stderr": stderr, "stdout": ""},
        wine_prefix=str(prefix),
        launcher_path="/tmp/Ascension Launcher.exe",
        wait_sec=0.1,
    )
    assert result["success"] is True
    assert signature is None
    assert reasons


def test_sidecar_output_detection(tmp_path):
    prefix = tmp_path / "prefix"
    drive_c = prefix / "drive_c"
    drive_c.mkdir(parents=True)
    assert not sidecar_produced_output(str(prefix))
    (drive_c / "alma-cs-output.log").write_bytes(b"ok")
    assert sidecar_produced_output(str(prefix))
    assert client_services_handoff_verified(str(prefix), "Launching elevated")


def test_benign_winsock_note_on_success():
    stderr = "WSALookupServiceBegin failed with: 8\nLaunching elevated"
    formatted = format_electron_launch_stderr(stderr, success=True)
    assert "normal Wine noise" in formatted


def test_main_launcher_excludes_alma_guard_decoy():
    assert not wine_has_main_launcher_process(
        "/tmp/prefix",
        "/tmp/prefix/drive_c/Program Files/Ascension Launcher/Ascension Launcher.exe",
    )


def test_watch_detects_silent_sidecar_crash(tmp_path):
    prefix = tmp_path / "prefix"
    drive_c = prefix / "drive_c"
    drive_c.mkdir(parents=True)
    invoke = drive_c / "alma-cs-invoke.log"
    invoke.write_text(
        '[cs-wrapper] cmdline="C:\\sidecar\\AscensionClientServices.real.exe"\n',
        encoding="utf-8",
    )
    signature, detail = watch_sidecar_handoff(
        str(prefix),
        watch_sec=0.2,
        silent_crash_sec=0.05,
        poll_sec=0.02,
    )
    assert signature == "sidecar_silent_crash"
    assert "no output" in detail.lower()


def test_watch_verified_when_output_grows(tmp_path):
    prefix = tmp_path / "prefix"
    drive_c = prefix / "drive_c"
    drive_c.mkdir(parents=True)
    (drive_c / "alma-cs-output.log").write_bytes(b"listening\n")
    signature, detail = watch_sidecar_handoff(
        str(prefix),
        watch_sec=0.2,
        silent_crash_sec=0.05,
        poll_sec=0.02,
    )
    assert signature is None
    assert "verified" in detail.lower() or "growing" in detail.lower()


def test_evaluate_runs_watchdog_for_stalled_handoff(monkeypatch, tmp_path):
    prefix = tmp_path / "prefix"
    drive_c = prefix / "drive_c"
    drive_c.mkdir(parents=True)
    (drive_c / "alma-cs-invoke.log").write_text(
        '[cs-wrapper] cmdline="foo.real.exe"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "alma_bridge.execution.electron_handoff.wait_for_main_launcher_process",
        lambda *args, **kwargs: False,
    )
    stderr = "[client-services] Launching elevated\n"
    result, signature, recommended = evaluate_electron_launch_result(
        {"success": False, "exit_code": 3, "stderr": stderr, "stdout": ""},
        wine_prefix=str(prefix),
        launcher_path="/tmp/Ascension Launcher.exe",
        wait_sec=0.1,
    )
    assert result["success"] is False
    assert signature == "sidecar_silent_crash"
    assert "Sidecar watchdog" in result["stderr"]
    assert recommended


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "sidecar"


def _write_fixture(prefix: Path, invoke_name: str, *, output: str = "") -> Path:
    drive_c = prefix / "drive_c"
    drive_c.mkdir(parents=True, exist_ok=True)
    invoke = drive_c / "alma-cs-invoke.log"
    invoke.write_text((FIXTURES / invoke_name).read_text(encoding="utf-8"), encoding="utf-8")
    if output:
        (drive_c / "alma-cs-output.log").write_text(output, encoding="utf-8")
    return prefix


def test_parse_current_wrapper_exit_format(tmp_path):
    prefix = _write_fixture(tmp_path / "prefix", "current_wrapper_success_invoke.log")
    evidence = parse_sidecar_handoff_evidence(str(prefix))
    assert evidence.wrapper_exit_code == 0
    assert evidence.wrapper_log_format == "current_cs_wrapper"
    assert evidence.real_exe_invoked
    assert evidence.decoy_spawned
    assert evidence.contract_version == SIDECAR_HANDOFF_CONTRACT_VERSION


def test_parse_c7_legacy_wrapper_exit_format(tmp_path):
    prefix = _write_fixture(tmp_path / "prefix", "c7_legacy_exit0_invoke.log")
    evidence = parse_sidecar_handoff_evidence(str(prefix))
    assert evidence.wrapper_exit_code == 0
    assert evidence.wrapper_log_format == "legacy_cs_wrapper"
    assert evidence.real_exe_invoked
    assert not evidence.decoy_spawned


def test_sidecar_exited_successfully_supports_legacy_and_current(tmp_path):
    legacy = _write_fixture(tmp_path / "legacy", "c7_legacy_exit0_invoke.log")
    current = _write_fixture(tmp_path / "current", "current_wrapper_success_invoke.log")
    assert sidecar_exited_successfully(str(legacy))
    assert sidecar_exited_successfully(str(current))


def test_exit0_without_corroboration_fails_handoff(tmp_path):
    prefix = _write_fixture(tmp_path / "prefix", "exit0_no_downstream_invoke.log")
    assert not client_services_handoff_verified(
        str(prefix),
        "",
        launcher_path="/tmp/Ascension Launcher.exe",
    )


def test_exit0_with_launcher_process_passes_handoff(monkeypatch, tmp_path):
    prefix = _write_fixture(tmp_path / "prefix", "c7_legacy_exit0_invoke.log")
    monkeypatch.setattr(
        "alma_bridge.execution.electron_handoff.wine_has_main_launcher_process",
        lambda *args, **kwargs: True,
    )
    assert client_services_handoff_verified(
        str(prefix),
        "",
        launcher_path="/tmp/Ascension Launcher.exe",
    )


def test_exit0_with_output_success_marker_passes_without_launcher(tmp_path):
    prefix = _write_fixture(
        tmp_path / "prefix",
        "c7_legacy_exit0_invoke.log",
        output="client services ready\n",
    )
    assert client_services_handoff_verified(str(prefix), "")


def test_nonzero_wrapper_exit_fails_handoff(tmp_path):
    prefix = _write_fixture(tmp_path / "prefix", "silent_crash_invoke.log")
    assert not client_services_handoff_verified(str(prefix), "")


def test_malformed_invoke_log_fails_closed(tmp_path):
    prefix = tmp_path / "prefix"
    (prefix / "drive_c").mkdir(parents=True)
    (prefix / "drive_c" / "alma-cs-invoke.log").write_text("truncated [cs-wrap\n", encoding="utf-8")
    assert not client_services_handoff_verified(str(prefix), "")


def test_fatal_signature_overrides_positive_wrapper_exit(monkeypatch, tmp_path):
    prefix = _write_fixture(tmp_path / "prefix", "c7_legacy_exit0_invoke.log")
    monkeypatch.setattr(
        "alma_bridge.execution.electron_handoff.wait_for_main_launcher_process",
        lambda *args, **kwargs: False,
    )
    stderr = "[client-services] Launching elevated\nwine: int3 trap\n"
    result, signature, _ = evaluate_electron_launch_result(
        {"success": False, "exit_code": 3, "stderr": stderr, "stdout": ""},
        wine_prefix=str(prefix),
        launcher_path="/tmp/Ascension Launcher.exe",
        wait_sec=0.1,
    )
    assert result["success"] is False
    assert signature == "wine_int3_crash"


def test_c7_fixture_reproduces_old_failure_without_launcher(tmp_path):
    prefix = _write_fixture(tmp_path / "prefix", "c7_legacy_exit0_invoke.log")
    signature, detail = watch_sidecar_handoff(
        str(prefix),
        watch_sec=0.2,
        silent_crash_sec=0.05,
        poll_sec=0.02,
        launcher_path="/tmp/Ascension Launcher.exe",
    )
    assert signature == "sidecar_silent_crash"


def test_c7_fixture_passes_with_launcher_corroboration(monkeypatch, tmp_path):
    prefix = _write_fixture(tmp_path / "prefix", "c7_legacy_exit0_invoke.log")
    monkeypatch.setattr(
        "alma_bridge.execution.electron_handoff.wine_has_main_launcher_process",
        lambda *args, **kwargs: True,
    )
    signature, detail = watch_sidecar_handoff(
        str(prefix),
        watch_sec=0.2,
        silent_crash_sec=0.05,
        poll_sec=0.02,
        launcher_path="/tmp/Ascension Launcher.exe",
    )
    assert signature is None
    assert "handoff verified" in detail.lower() or "corroborated" in detail.lower()


def test_verification_records_handoff_contract(monkeypatch, tmp_path):
    from alma_bridge.session.services.verification import VERIFIER_VERSION, DefaultVerificationEngine

    monkeypatch.setattr(
        "alma_bridge.execution.electron_handoff.wait_for_main_launcher_process",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "alma_bridge.execution.electron_handoff.wine_has_main_launcher_process",
        lambda *args, **kwargs: True,
    )
    prefix = _write_fixture(tmp_path / "prefix", "current_wrapper_success_invoke.log")
    engine = DefaultVerificationEngine()
    outcome = engine.verify_launcher(
        result={"success": False, "exit_code": 0, "stderr": "[client-services] Launching elevated\n", "stdout": ""},
        wine_prefix=str(prefix),
        launcher_path="/tmp/Ascension Launcher.exe",
    )
    assert VERIFIER_VERSION == "1.1.0"
    assert outcome.checks[0].verifier_id == "electron_handoff"
    assert outcome.checks[0].verifier_version == "1.1.0"
    assert any("handoff_contract=" in line for line in outcome.checks[0].evidence)
