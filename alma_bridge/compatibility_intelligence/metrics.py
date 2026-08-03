"""Registry and coverage metrics for planner consumption."""

from __future__ import annotations

from alma_bridge.compatibility_intelligence.apis import registry_stats
from alma_bridge.compatibility_intelligence.capabilities import (
    CAPABILITY_REGISTRY,
    list_capabilities,
)
from alma_bridge.compatibility_intelligence.models import ImplementationStatus
from alma_bridge.compatibility_intelligence.models import RegistryMetrics


def compute_registry_metrics() -> RegistryMetrics:
    stats = registry_stats()
    by_dll = stats.get("by_dll", {})
    native_supported = sum(
        1
        for cap in CAPABILITY_REGISTRY.values()
        if cap.capability_id != "api.unknown"
        and cap.native == ImplementationStatus.SUPPORTED
    )
    return RegistryMetrics(
        total_registry_apis=int(stats.get("total_registry_apis", 0)),
        classified_apis=int(stats.get("classified_apis", 0)),
        by_dll=by_dll,
        capability_count=len(list_capabilities()),
        native_supported_capabilities=native_supported,
    )
