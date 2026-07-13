from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from alma_bridge.operator.failures import _consolidate_mitigations, _plan_mitigations


def test_plan_mitigations_includes_sudo_retry_and_permission_fix():
    failures = [
        {
            "source": "automation",
            "error_text": "Sudo is enabled but no cached credentials exist.",
            "failed_step_ids": [],
        },
        {
            "source": "bridge",
            "file_path": "/tmp/game.AppImage",
            "error_text": "[Errno 13] Permission denied: '/tmp/game.AppImage'",
        },
    ]
    mitigations = _plan_mitigations(failures, None, [])
    kinds = {m["kind"] for m in mitigations}
    ids = {m["id"] for m in mitigations}
    assert "modernize_apply" in kinds
    assert "fix_permissions" in kinds
    assert "heal:sudo_credentials" in ids


def test_consolidate_runs_prerequisites_before_best_route():
    mitigations = [
        {"id": "route:best", "kind": "best_route"},
        {"id": "modernize:apply_host", "kind": "modernize_apply"},
        {"id": "fix_permissions:game", "kind": "fix_permissions"},
        {"id": "heal:sudo_credentials", "kind": "heal"},
        {"id": "bridge-retry:game", "kind": "bridge"},
    ]
    kept = _consolidate_mitigations(mitigations)
    assert [m["kind"] for m in kept] == [
        "heal",
        "modernize_apply",
        "fix_permissions",
        "best_route",
    ]


def test_mitigation_report_extracts_phase_errors():
    from alma_bridge.operator.failures import _mitigation_report

    outcome = {
        "mitigation_id": "modernize:apply_host",
        "kind": "modernize_apply",
        "title": "Retry host modernization",
        "success": False,
        "execution": {
            "success": False,
            "phases": [
                {"phase": "apply", "ok": False, "error": "sudo password rejected"},
            ],
        },
    }
    report = _mitigation_report(outcome)
    assert report["status"] == "failed"
    assert "sudo" in report["detail"].lower()


def test_mitigation_report_skipped():
    from alma_bridge.operator.failures import _mitigation_report

    report = _mitigation_report(
        {"skipped": True, "reason": "not auto-eligible"},
    )
    assert report["status"] == "skipped"
    assert "auto-eligible" in report["detail"]


def test_ensure_binary_executable_uses_sudo_when_needed(tmp_path, monkeypatch):
    from alma_bridge.execution.binary_access import ensure_binary_executable

    target = tmp_path / "game.AppImage"
    target.write_bytes(b"#!/bin/sh\necho hi\n")
    target.chmod(0o644)

    monkeypatch.setattr(
        "alma_bridge.execution.binary_access.prepare_sudo",
        lambda **kwargs: (True, ""),
    )
    monkeypatch.setattr(
        "alma_bridge.execution.binary_access._privileged_shell",
        lambda cmd, **kwargs: {"ok": True, "stderr": "", "stdout": ""},
    )
    access_results = iter([False, True])
    monkeypatch.setattr(
        "alma_bridge.execution.binary_access.os.access",
        lambda path, mode: next(access_results, True),
    )

    result = ensure_binary_executable(str(target), sudo_password="secret")
    assert result["ok"] is True
    assert result["changed"] is True
    assert result["method"] == "sudo_chmod"


def test_ensure_binary_executable_user_chmod_sufficient(tmp_path):
    from alma_bridge.execution.binary_access import ensure_binary_executable

    target = tmp_path / "game.AppImage"
    target.write_bytes(b"#!/bin/sh\necho hi\n")
    target.chmod(0o644)

    result = ensure_binary_executable(str(target))
    assert result["ok"] is True
    assert result["changed"] is True
    assert result["method"] == "chmod_user"
