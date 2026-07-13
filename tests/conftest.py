"""Pytest configuration — isolate tests from developer runtime .env."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_validation_campaign_settings(monkeypatch):
    """Tests default campaign mode off unless they explicitly enable it."""
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_mode", False)
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_id", None)
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_disposable_root", None)
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_primary_prefix", None)
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_source_snapshot", None)
