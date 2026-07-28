"""Shared fixtures for Compatibility Catalog tests."""

from __future__ import annotations

from typing import Any, Dict

from alma_bridge.storage import outcomes
from tests.knowledge.conftest import (
    CODEBLOCKS_FINGERPRINT,
    _assign_session_id,
    _seed_session,
    seed_codeblocks_knowledge_sessions,
)

APP_A_FINGERPRINT = "catalog-app-a-fingerprint"
APP_B_FINGERPRINT = "catalog-app-b-fingerprint"
ENV_SESSION_WINE_9 = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
ENV_SESSION_WINE_10 = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _make_environment(*, wine_version: str, prefix_path: str) -> Dict[str, Any]:
    from alma_bridge.compatibility.profile_fingerprints import sha256_v1

    return {
        "schema_version": "compatibility_run_environment_v1",
        "alma_bridge_version": "0.1.0",
        "host_os": "Linux (Ubuntu)",
        "kernel_version": "6.8.0-generic",
        "host_architecture": "x86_64",
        "wine_version": wine_version,
        "wine_architecture": "win64",
        "prefix_id": sha256_v1({"prefix_path": prefix_path}),
        "relevant_runtime_identities": ["phase:wine_gui", "runtime:wine"],
        "execution_strategy_version": "wine_gui",
    }


def seed_session_with_environment(
    *,
    session_id: str,
    fingerprint: str,
    wine_version: str,
    prefix_path: str,
    verification=None,
    finalize_success: bool = True,
) -> str:
    from tests.intelligence.conftest import sample_wine_gui_verification

    _seed_session(
        session_id=session_id,
        fingerprint=fingerprint,
        verification=verification or sample_wine_gui_verification(),
        finalize_success=finalize_success,
    )
    outcomes.set_session_run_environment(
        session_id,
        _make_environment(wine_version=wine_version, prefix_path=prefix_path),
    )
    return session_id


def seed_catalog_acceptance_data() -> None:
    """Two wine versions for app A; unrelated app B for isolation."""
    seed_codeblocks_knowledge_sessions(fingerprint=APP_A_FINGERPRINT)
    seed_session_with_environment(
        session_id=ENV_SESSION_WINE_9,
        fingerprint=APP_A_FINGERPRINT,
        wine_version="wine-9.0 (Ubuntu)",
        prefix_path="/tmp/prefix-wine9",
    )
    seed_session_with_environment(
        session_id=ENV_SESSION_WINE_10,
        fingerprint=APP_A_FINGERPRINT,
        wine_version="wine-10.0 (Ubuntu)",
        prefix_path="/tmp/prefix-wine10",
    )
    created = outcomes.new_session("/tmp/other-app.exe", APP_B_FINGERPRINT, {"architecture": "x86_64"})
    _assign_session_id(created, "cccccccc-cccc-4ccc-8ccc-cccccccccccc")
