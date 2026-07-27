"""Shared fixtures for Compatibility Graph tests."""

from __future__ import annotations

import pytest

from alma_bridge.storage import outcomes
from tests.intelligence.conftest import (
    CODEBLOCKS_FINGERPRINT,
    CODEBLOCKS_SESSION_ID,
    seed_codeblocks_session,
)

__all__ = [
    "CODEBLOCKS_FINGERPRINT",
    "CODEBLOCKS_SESSION_ID",
    "seed_codeblocks_session",
]


@pytest.fixture
def isolated_graph_store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield
