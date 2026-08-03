"""Runtime registry tests."""

from __future__ import annotations

import pytest

from alma_bridge.runtime.errors import DuplicateProviderError
from alma_bridge.runtime.providers.wine import WineRuntime
from alma_bridge.runtime.registry import RuntimeRegistry, build_default_registry


class TestRuntimeRegistry:
    def test_default_registry_deterministic_order(self):
        reg = build_default_registry()
        assert reg.list_ids() == ["wine", "proton", "container", "native_alma"]

    def test_duplicate_provider_id_fails(self):
        reg = RuntimeRegistry()
        reg.register(WineRuntime())
        with pytest.raises(DuplicateProviderError):
            reg.register(WineRuntime())

    def test_inventory_includes_capabilities(self):
        reg = build_default_registry()
        inventory = reg.inventory()
        assert len(inventory) == 4
        wine = next(item for item in inventory if item.provider_id == "wine")
        assert "pe_console" in wine.capabilities
