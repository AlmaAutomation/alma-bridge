from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from alma_bridge.compatibility.profile_store import load_candidate_for_session_attempt
from alma_bridge.compatibility.program_kind import classify_program_kind
from alma_bridge.config import settings
from alma_bridge.learning.orchestrator import BridgeOrchestrator
from alma_bridge.schemas.models import BridgeRequest
from alma_bridge.storage import outcomes


def retrieve_persisted_verification(session_id: str) -> Optional[Dict[str, Any]]:
    """Read persisted VerificationResult via the repository session API."""
    session = outcomes.get_session(session_id)
    if not session:
        return None
    winning = session.get("winning_attempt")
    if not winning:
        return None
    verification = winning.get("verification")
    return verification if isinstance(verification, dict) else None


def retrieve_promoted_profile_id(candidate_id: str) -> Optional[str]:
    from alma_bridge.compatibility.profile_store import _connect, ensure_profile_tables

    with _connect() as conn:
        ensure_profile_tables(conn)
        row = conn.execute(
            """
            SELECT promoted_profile_id
            FROM compatibility_profile_candidates
            WHERE candidate_id = ?
            """,
            (candidate_id,),
        ).fetchone()
    if not row:
        return None
    return row["promoted_profile_id"]


def run_setup_target(
    *,
    setup_id: str,
    exe_path: Path,
    wine_prefix: Optional[Path] = None,
    data_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    if data_dir is not None:
        settings.data_dir = data_dir
        settings.db_path = data_dir / "outcomes.db"
    outcomes.init_outcome_store()

    if wine_prefix is not None:
        import os

        os.environ["WINEPREFIX"] = str(wine_prefix)

    kind = classify_program_kind(str(exe_path))
    result = BridgeOrchestrator().run(
        BridgeRequest(
            file_path=str(exe_path),
            max_attempts=3,
            auto_remediate=False,
            wine_prefix=str(wine_prefix) if wine_prefix else None,
        )
    )
    winning = result.winning_attempt
    verification = retrieve_persisted_verification(result.session_id)
    snap = (
        load_candidate_for_session_attempt(result.session_id, winning.attempt_number)
        if winning
        else None
    )
    candidate_id = getattr(snap, "candidate_id", None)
    profile_id = retrieve_promoted_profile_id(candidate_id) if candidate_id else None
    return {
        "setup_id": setup_id,
        "success": result.success,
        "session_id": result.session_id,
        "program_kind": kind.get("program_kind"),
        "phase": winning.phase if winning else None,
        "verification_passed": (verification or {}).get("passed"),
        "verification_policy": ((verification or {}).get("success_policy") or {}).get(
            "policy_id"
        ),
        "checks": [c.get("check_kind") for c in (verification or {}).get("checks", [])],
        "candidate_id": candidate_id,
        "profile_id": profile_id,
        "wine_prefix": str(wine_prefix) if wine_prefix else None,
        "exe_path": str(exe_path),
    }
