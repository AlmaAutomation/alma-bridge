"""Shared fixtures for Compatibility Knowledge tests."""

from __future__ import annotations

import uuid
from typing import Any, Dict

from alma_bridge.storage import outcomes
from tests.intelligence.conftest import (
    CODEBLOCKS_FINGERPRINT,
    FIXTURE_STDERR,
    sample_wine_gui_verification,
)

KNOWLEDGE_SESSION_A = "11111111-1111-4111-8111-111111111111"
KNOWLEDGE_SESSION_B = "22222222-2222-4222-8222-222222222222"
KNOWLEDGE_SESSION_C = "33333333-3333-4333-8333-333333333333"
KNOWLEDGE_SESSION_D = "44444444-4444-4444-8444-444444444444"


def _assign_session_id(created_id: str, target_id: str) -> None:
    if created_id == target_id:
        return
    with outcomes._connect() as conn:  # noqa: SLF001
        conn.execute(
            "UPDATE bridge_session_transitions SET session_id = ? WHERE session_id = ?",
            (target_id, created_id),
        )
        conn.execute(
            "UPDATE bridge_sessions SET session_id = ? WHERE session_id = ?",
            (target_id, created_id),
        )
        conn.commit()


def _seed_session(
    *,
    session_id: str,
    fingerprint: str = CODEBLOCKS_FINGERPRINT,
    file_path: str = "/opt/CodeBlocks/codeblocks.exe",
    stderr: str = FIXTURE_STDERR,
    verification: Dict[str, Any] | None = None,
    finalize_success: bool = True,
) -> str:
    created_id = outcomes.new_session(file_path, fingerprint, {"architecture": "x86_64"})
    _assign_session_id(created_id, session_id)
    outcomes.record_attempt(
        session_id=session_id,
        attempt_number=1,
        strategy_id="wine_gui",
        remediation_id=None,
        runtime="wine",
        command=["wine", file_path],
        env={"WINEPREFIX": "/tmp/prefix"},
        mode="host_prefix",
        success=True,
        exit_code=0,
        error_signature=None,
        detected_error=None,
        stdout="",
        stderr=stderr,
        duration_ms=1200,
        phase="wine_gui",
        verification=verification,
    )
    outcomes.finalize_session(
        session_id,
        success=finalize_success,
        summary=f"Knowledge fixture session {session_id}",
    )
    return session_id


def seed_codeblocks_knowledge_sessions(
    *,
    fingerprint: str = CODEBLOCKS_FINGERPRINT,
) -> str:
    """Seed four sessions under one fingerprint for knowledge aggregation acceptance."""
    _seed_session(
        session_id=KNOWLEDGE_SESSION_A,
        fingerprint=fingerprint,
        verification=sample_wine_gui_verification(),
        finalize_success=True,
    )
    _seed_session(
        session_id=KNOWLEDGE_SESSION_B,
        fingerprint=fingerprint,
        verification=sample_wine_gui_verification(),
        finalize_success=True,
    )
    _seed_session(
        session_id=KNOWLEDGE_SESSION_C,
        fingerprint=fingerprint,
        verification={
            "passed": False,
            "confidence": 0.2,
            "success_policy": {
                "policy_id": "wine_gui_process_v1",
                "policy_version": "1.1.0",
                "required_checks": {"wine_gui": ["process_survives"]},
            },
            "checks": [],
            "evidence": [],
        },
        finalize_success=False,
    )
    _seed_session(
        session_id=KNOWLEDGE_SESSION_D,
        fingerprint=fingerprint,
        stderr="Qt 5.15 startup banner\n",
        verification=None,
        finalize_success=False,
    )
    return fingerprint


def seed_unrelated_session() -> str:
    session_id = str(uuid.uuid4())
    outcomes.new_session("/tmp/other.exe", "other-fingerprint", {})
    return session_id
