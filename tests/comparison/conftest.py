"""Shared fixtures for session comparison tests."""

from __future__ import annotations

from typing import Any, Dict

from alma_bridge.storage import outcomes
from tests.catalog.conftest import APP_A_FINGERPRINT, _make_environment
from tests.knowledge.conftest import _seed_session
from tests.intelligence.conftest import sample_wine_gui_verification


COMPARE_BASELINE_SESSION = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
COMPARE_COMPARISON_SESSION = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
COMPARE_OTHER_APP_SESSION = "ffffffff-ffff-4fff-8fff-ffffffffffff"


def sample_wine_gui_verification_failure() -> Dict[str, Any]:
    verification = sample_wine_gui_verification()
    verification = dict(verification)
    verification["passed"] = False
    checks = []
    for check in verification.get("checks") or []:
        item = dict(check)
        item["passed"] = False
        checks.append(item)
    verification["checks"] = checks
    return verification


def seed_session_with_environment_and_outcome(
    *,
    session_id: str,
    fingerprint: str,
    wine_version: str,
    prefix_path: str,
    verification: Dict[str, Any],
    finalize_success: bool,
) -> str:
    _seed_session(
        session_id=session_id,
        fingerprint=fingerprint,
        verification=verification,
        finalize_success=finalize_success,
    )
    outcomes.set_session_run_environment(
        session_id,
        _make_environment(wine_version=wine_version, prefix_path=prefix_path),
    )
    return session_id


def seed_codeblocks_comparison_acceptance() -> None:
    """Code::Blocks-style acceptance: wine 9 success vs wine 10 verified failure."""
    seed_session_with_environment_and_outcome(
        session_id=COMPARE_BASELINE_SESSION,
        fingerprint=APP_A_FINGERPRINT,
        wine_version="wine-9.0 (Ubuntu)",
        prefix_path="/tmp/prefix-wine9",
        verification=sample_wine_gui_verification(),
        finalize_success=True,
    )
    seed_session_with_environment_and_outcome(
        session_id=COMPARE_COMPARISON_SESSION,
        fingerprint=APP_A_FINGERPRINT,
        wine_version="wine-10.0 (Ubuntu)",
        prefix_path="/tmp/prefix-wine10",
        verification=sample_wine_gui_verification_failure(),
        finalize_success=False,
    )


def seed_other_application_session() -> None:
    created = outcomes.new_session("/tmp/other-app.exe", "other-app-fingerprint", {"architecture": "x86_64"})
    from tests.knowledge.conftest import _assign_session_id

    _assign_session_id(created, COMPARE_OTHER_APP_SESSION)
