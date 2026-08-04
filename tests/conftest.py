"""Pytest configuration — isolate tests from developer runtime .env."""

from __future__ import annotations

import sys

import pytest

import alma_bridge.api.routes as api_routes
import alma_bridge.execution.electron_handoff as electron_handoff_module
import alma_bridge.execution.wine_process as wine_process_module
import alma_bridge.learning.orchestrator as orchestrator_module
from alma_bridge.learning.orchestrator import BridgeOrchestrator
from alma_bridge.storage import outcomes

_ORCHESTRATOR_MODULE = orchestrator_module
_ELECTRON_HANDOFF_MODULE = electron_handoff_module
_WINE_PROCESS_MODULE = wine_process_module


@pytest.fixture(autouse=True)
def _reset_validation_campaign_settings(monkeypatch):
    """Tests default campaign mode off unless they explicitly enable it."""
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_mode", False)
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_id", None)
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_disposable_root", None)
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_primary_prefix", None)
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_source_snapshot", None)
    monkeypatch.setattr("alma_bridge.config.settings.bridge_auto_remediate", True)


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


# Import-boundary tests may pop orchestrator from sys.modules without restoring it,
# leaving api.routes.orchestrator and collection-time imports on a stale module while
# later monkeypatch calls bind to a new sys.modules entry. Pin the canonical module
# and refresh the routes singleton after every test so full-suite runs stay aligned.
@pytest.fixture(autouse=True)
def _stabilize_orchestrator_bindings():
    """Keep sys.modules and api.routes.orchestrator on the collected orchestrator module."""
    sys.modules["alma_bridge.learning.orchestrator"] = _ORCHESTRATOR_MODULE
    yield
    sys.modules["alma_bridge.learning.orchestrator"] = _ORCHESTRATOR_MODULE
    api_routes.orchestrator = BridgeOrchestrator()


@pytest.fixture(autouse=True)
def _stabilize_electron_handoff_bindings():
    """Restore electron handoff callables after tests that patch wine_process symbols."""
    yield
    _ELECTRON_HANDOFF_MODULE.wine_has_main_launcher_process = (
        _WINE_PROCESS_MODULE.wine_has_main_launcher_process
    )
    _ELECTRON_HANDOFF_MODULE.wait_for_main_launcher_process = (
        _WINE_PROCESS_MODULE.wait_for_main_launcher_process
    )
