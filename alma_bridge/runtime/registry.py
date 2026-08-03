"""Deterministic runtime provider registry."""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from alma_bridge.runtime.errors import DuplicateProviderError, ProviderNotFoundError
from alma_bridge.runtime.models import ProviderInventoryEntry
from alma_bridge.runtime.provider import CompatibilityRuntimeProvider


class RuntimeRegistry:
    """Startup registry with deterministic ordering and duplicate-ID rejection."""

    def __init__(self) -> None:
        self._providers: Dict[str, CompatibilityRuntimeProvider] = {}
        self._order: List[str] = []

    def register(self, provider: CompatibilityRuntimeProvider) -> None:
        provider_id = provider.provider_id
        if provider_id in self._providers:
            raise DuplicateProviderError(f"provider already registered: {provider_id}")
        self._providers[provider_id] = provider
        self._order.append(provider_id)

    def get(self, provider_id: str) -> CompatibilityRuntimeProvider:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise ProviderNotFoundError(f"provider not found: {provider_id}")
        return provider

    def list_ids(self) -> List[str]:
        return list(self._order)

    def all(self) -> List[CompatibilityRuntimeProvider]:
        return [self._providers[pid] for pid in self._order]

    def inventory(self) -> List[ProviderInventoryEntry]:
        entries: List[ProviderInventoryEntry] = []
        for provider in self.all():
            caps = provider.capabilities()
            entries.append(
                ProviderInventoryEntry(
                    provider_id=provider.provider_id,
                    provider_version=provider.provider_version,
                    capabilities=caps.to_dict(),
                    experimental=provider.provider_id == "native_alma",
                )
            )
        return entries


def build_default_registry(
    providers: Optional[Iterable[CompatibilityRuntimeProvider]] = None,
) -> RuntimeRegistry:
    """Construct the default Phase 0B registry in deterministic order."""
    from alma_bridge.runtime.providers.container import ContainerRuntime
    from alma_bridge.runtime.providers.native_alma import NativeAlmaRuntime
    from alma_bridge.runtime.providers.proton import ProtonRuntime
    from alma_bridge.runtime.providers.wine import WineRuntime

    registry = RuntimeRegistry()
    default_providers = providers or (
        WineRuntime(),
        ProtonRuntime(),
        ContainerRuntime(),
        NativeAlmaRuntime(),
    )
    for provider in default_providers:
        registry.register(provider)
    return registry
