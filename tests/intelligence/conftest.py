"""Shared fixtures for Compatibility Intelligence tests."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from alma_bridge.storage import outcomes

CODEBLOCKS_SESSION_ID = "4ecb0e85-af0c-4143-8b29-668cfccad37a"
CODEBLOCKS_FINGERPRINT = "codeblocks-sha256-fixture"

FIXTURE_STDERR = (
    Path(__file__).resolve().parents[1] / "fixtures" / "codeblocks_startup_stderr.txt"
).read_text(encoding="utf-8")


def sample_wine_gui_verification() -> Dict[str, Any]:
    return {
        "passed": True,
        "confidence": 0.95,
        "success_policy": {
            "policy_id": "wine_gui_process_v1",
            "policy_version": "1.1.0",
            "required_checks": {"wine_gui": ["process_survives"]},
        },
        "checks": [
            {
                "verifier_id": "wine_gui_handoff",
                "verifier_version": "1.1.0",
                "check_kind": "process_survives",
                "passed": True,
                "confidence": 0.95,
                "evidence": ["process_survives"],
            }
        ],
        "evidence": ["process_survives", "target_process_identity"],
    }


def seed_codeblocks_session(
    *,
    session_id: str = CODEBLOCKS_SESSION_ID,
    fingerprint: str = CODEBLOCKS_FINGERPRINT,
    file_path: str = "/opt/CodeBlocks/codeblocks.exe",
) -> str:
    """Persist a synthetic session matching the Code::Blocks verified-launch structure."""
    created_id = outcomes.new_session(file_path, fingerprint, {"architecture": "x86_64"})
    if created_id != session_id:
        with outcomes._connect() as conn:  # noqa: SLF001
            conn.execute(
                "UPDATE bridge_session_transitions SET session_id = ? WHERE session_id = ?",
                (session_id, created_id),
            )
            conn.execute(
                "UPDATE bridge_sessions SET session_id = ? WHERE session_id = ?",
                (session_id, created_id),
            )
            conn.commit()

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
        stderr=FIXTURE_STDERR,
        duration_ms=1200,
        phase="wine_gui",
        verification=sample_wine_gui_verification(),
    )
    outcomes.finalize_session(session_id, success=True, summary="Verified wine_gui launch")
    return session_id
