"""Shared fixtures for Compatibility Regression tests."""

from __future__ import annotations

from tests.knowledge.conftest import (
    CODEBLOCKS_FINGERPRINT,
    KNOWLEDGE_SESSION_A,
    KNOWLEDGE_SESSION_B,
    KNOWLEDGE_SESSION_C,
    KNOWLEDGE_SESSION_D,
    _seed_session,
    seed_codeblocks_knowledge_sessions,
)

KNOWLEDGE_SESSION_E = "55555555-5555-4555-8555-555555555555"


def seed_codeblocks_regression_sessions(
    *,
    fingerprint: str = CODEBLOCKS_FINGERPRINT,
) -> str:
    """Seed A,B,C,D plus E (verified success) for strategy-rate regression tests."""
    seed_codeblocks_knowledge_sessions(fingerprint=fingerprint)
    from tests.intelligence.conftest import sample_wine_gui_verification

    _seed_session(
        session_id=KNOWLEDGE_SESSION_E,
        fingerprint=fingerprint,
        verification=sample_wine_gui_verification(),
        finalize_success=True,
    )
    return fingerprint
