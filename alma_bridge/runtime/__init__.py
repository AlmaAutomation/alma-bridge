"""Compatibility runtime package — provider contracts and registry."""

from alma_bridge.runtime.capabilities import CapabilityState, RuntimeCapabilities
from alma_bridge.runtime.models import RuntimeRequirements
from alma_bridge.runtime.provider import CompatibilityRuntimeProvider
from alma_bridge.runtime.registry import RuntimeRegistry, build_default_registry

__all__ = [
    "CapabilityState",
    "CompatibilityRuntimeProvider",
    "RuntimeCapabilities",
    "RuntimeRegistry",
    "RuntimeRequirements",
    "build_default_registry",
]
