from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alma_bridge.learning.remediation import remediations_for_signature
from alma_bridge.execution.errors import (
    ERROR_RETRY_POLICIES,
    NON_RETRYABLE_SIGNATURES,
    RetryScope,
    retry_scope_for_signature,
)
from alma_bridge.main import create_app
from alma_bridge.storage.outcomes import init_outcome_store


@pytest.fixture(autouse=True)
def _disable_slow_wine_prefix_bootstrap(monkeypatch):
    """`.exe` bridge runs trigger dotnet bootstrap that can hang in CI/sandbox."""
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator._ensure_prefix_runtimes",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.require_wine_windows_version",
        lambda _prefix: (True, ""),
    )


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    init_outcome_store()
    return TestClient(create_app())


def test_permission_denied_has_remediations():
    ids = {action["id"] for action in remediations_for_signature("permission_denied")}
    assert "permission_fresh_prefix" in ids
    assert "baseline_retry" not in ids


def test_permission_denied_is_attempt_scoped_not_session():
    assert retry_scope_for_signature("permission_denied") is None
    assert "permission_denied" not in NON_RETRYABLE_SIGNATURES
    assert "permission_denied" not in ERROR_RETRY_POLICIES


def test_session_scoped_errors_stop_entire_session():
    for signature in ("single_instance_detected", "architecture_mismatch", "invalid_launch_args"):
        assert retry_scope_for_signature(signature) == RetryScope.SESSION
        assert signature in NON_RETRYABLE_SIGNATURES


def test_unknown_signature_has_no_retry_scope():
    assert retry_scope_for_signature("totally_made_up_error") is None
    assert retry_scope_for_signature(None) is None


def test_unknown_signature_falls_back_to_wildcards():
    actions = remediations_for_signature("totally_made_up_error")
    assert len(actions) >= 1
    assert actions[0]["id"] in {None, "baseline_retry", "container_isolation"}


def test_orchestrator_retries_multiple_strategies(tmp_path, client, monkeypatch):
    exe = tmp_path / "game.exe"
    exe.write_bytes(b"MZ")
    exe.chmod(0o755)

    calls: list[str] = []

    def fake_execute(*, command, **kwargs):
        runtime = "wine" if "wine" in str(command[0]).lower() else command[0]
        calls.append(str(command[0]))
        return {
            "success": False,
            "exit_code": 1,
            "error_signature": "permission_denied",
            "detected_error": "permission denied",
            "suggested_fix": "retry",
            "likely_causes": ["Try fresh prefix"],
            "stdout": "",
            "stderr": "permission denied",
            "duration_ms": 10,
        }

    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.execute_attempt",
        fake_execute,
    )
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.fresh_prefix_path",
        lambda _sid: str(tmp_path / "prefix"),
    )
    monkeypatch.setattr(
        "alma_bridge.hardware.prefixes.find_best_prefix",
        lambda _path: None,
    )

    response = client.post(
        "/bridge/run",
        json={"file_path": str(exe), "sandbox": False, "max_attempts": 6},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    attempts = body["attempts"]
    assert len(attempts) >= 2
    remediation_ids = [attempt["remediation_id"] for attempt in attempts]
    assert remediation_ids[0] is None
    assert any(remediation_ids[1:])


def test_orchestrator_reranks_remaining_strategies(tmp_path, client, monkeypatch):
    exe = tmp_path / "game.exe"
    exe.write_bytes(b"MZ")
    exe.chmod(0o755)

    rerank_calls: list[str | None] = []

    def tracking_rerank(plans, *, file_path, hardware_profile, error_signature=None):
        rerank_calls.append(error_signature)
        return plans

    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.rerank_plans",
        tracking_rerank,
    )
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.execute_attempt",
        lambda **kwargs: {
            "success": False,
            "exit_code": 1,
            "error_signature": "permission_denied",
            "detected_error": "permission denied",
            "suggested_fix": "retry",
            "likely_causes": ["Try fresh prefix"],
            "stdout": "",
            "stderr": "permission denied",
            "duration_ms": 10,
        },
    )
    monkeypatch.setattr(
        "alma_bridge.learning.orchestrator.fresh_prefix_path",
        lambda _sid: str(tmp_path / "prefix"),
    )
    monkeypatch.setattr(
        "alma_bridge.hardware.prefixes.find_best_prefix",
        lambda _path: None,
    )

    response = client.post(
        "/bridge/run",
        json={"file_path": str(exe), "sandbox": False, "max_attempts": 4, "auto_remediate": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert rerank_calls
    assert rerank_calls[0] == "permission_denied"
    assert "Re-ranked remaining strategies" in body["summary"]
    assert body.get("rerank_events")
    assert body["rerank_events"][0]["error_signature"] == "permission_denied"
    assert body["rerank_events"][0]["after_strategy_id"]


def test_orchestrator_applies_preferred_remediation_first(tmp_path, client, monkeypatch):
    exe = tmp_path / "game.exe"
    exe.write_bytes(b"MZ")
    exe.chmod(0o755)

    attempts_seen: list[str | None] = []

    def fake_execute(**kwargs):
        return {
            "success": True,
            "exit_code": 0,
            "error_signature": None,
            "detected_error": None,
            "suggested_fix": None,
            "likely_causes": [],
            "stdout": "ok",
            "stderr": "",
            "duration_ms": 5,
        }

    original_next = None

    def tracking_next(plan_signature, tried_ids, **kwargs):
        remediation = original_next(plan_signature, tried_ids, **kwargs)
        if remediation:
            attempts_seen.append(remediation.get("id"))
        return remediation

    import alma_bridge.learning.orchestrator as orch

    original_next = orch._next_remediation
    monkeypatch.setattr(orch, "_next_remediation", tracking_next)
    monkeypatch.setattr(orch, "execute_attempt", fake_execute)
    monkeypatch.setattr(orch, "fresh_prefix_path", lambda _sid: str(tmp_path / "prefix"))
    monkeypatch.setattr("alma_bridge.hardware.prefixes.find_best_prefix", lambda _path: None)

    response = client.post(
        "/bridge/run",
        json={
            "file_path": str(exe),
            "sandbox": False,
            "max_attempts": 2,
            "preferred_strategy_id": "wine_host",
            "preferred_remediation_id": "software_rendering",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["attempts"][0]["strategy_id"] == "wine_host"
    assert body["attempts"][0]["remediation_id"] == "software_rendering"
    assert attempts_seen[0] == "software_rendering"
