"""Pytest configuration — isolate tests from developer runtime .env."""

from __future__ import annotations

import pytest

from alma_bridge.storage import outcomes


@pytest.fixture(autouse=True)
def _reset_validation_campaign_settings(monkeypatch):
    """Tests default campaign mode off unless they explicitly enable it."""
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_mode", False)
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_id", None)
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_disposable_root", None)
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_primary_prefix", None)
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_source_snapshot", None)


@pytest.fixture(autouse=True)
def _isolate_bridge_data_paths(tmp_path, monkeypatch):
    """Keep bridge prefixes and outcomes DB off the developer home directory."""
    data_dir = tmp_path / "alma-bridge-data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / "outcomes.db"
    monkeypatch.setenv("ALMA_BRIDGE_DATA_DIR", str(data_dir))
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", data_dir)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db_path)
    outcomes.init_outcome_store()
    try:
        from alma_bridge.learning.remediation_learning import init_remediation_store

        init_remediation_store()
    except ImportError:
        pass
    yield
