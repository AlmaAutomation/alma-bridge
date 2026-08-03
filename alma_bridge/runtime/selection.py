"""Capability-based runtime provider selection."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from alma_bridge.runtime.capabilities import CapabilityState
from alma_bridge.runtime.models import RuntimeRequirements
from alma_bridge.runtime.provider import CompatibilityRuntimeProvider
from alma_bridge.runtime.registry import RuntimeRegistry

# Stable mapping from existing strategy IDs to runtime provider IDs.
STRATEGY_PROVIDER_MAP: Dict[str, str] = {
    "wine_host": "wine",
    "proton_host": "proton",
    "container_compat": "container",
    "container_podman": "container",
}

STRATEGY_REQUIRED_CAPABILITIES: Dict[str, List[str]] = {
    "wine_host": ["pe_console", "pe_gui"],
    "proton_host": ["pe_console", "pe_gui"],
    "container_compat": ["container_isolation"],
    "container_podman": ["container_isolation"],
}


def provider_id_for_strategy(strategy_id: str) -> Optional[str]:
    return STRATEGY_PROVIDER_MAP.get(strategy_id)


def requirements_for_strategy(strategy_id: str) -> RuntimeRequirements:
    required = list(STRATEGY_REQUIRED_CAPABILITIES.get(strategy_id, []))
    return RuntimeRequirements(required=required, strategy_id=strategy_id)


def _score_provider(
    provider: CompatibilityRuntimeProvider,
    requirements: RuntimeRequirements,
) -> Tuple[int, List[str]]:
    caps = provider.capabilities()
    score = 0
    blockers: List[str] = []
    for capability in requirements.required:
        state = caps.state_of(capability)
        if state == CapabilityState.UNSUPPORTED:
            blockers.append(f"{capability}=unsupported")
            return -1, blockers
        if state == CapabilityState.UNKNOWN:
            blockers.append(f"{capability}=unknown")
            return -1, blockers
        if state == CapabilityState.SUPPORTED:
            score += 3
        elif state == CapabilityState.PARTIAL:
            score += 2
        elif state == CapabilityState.DELEGATED:
            score += 1
    for capability in requirements.preferred:
        state = caps.state_of(capability)
        if state == CapabilityState.SUPPORTED:
            score += 1
        elif state == CapabilityState.PARTIAL:
            score += 1
    return score, blockers


def select_providers(
    requirements: RuntimeRequirements,
    registry: RuntimeRegistry,
    *,
    strategy_id: Optional[str] = None,
) -> List[CompatibilityRuntimeProvider]:
    """Return providers sorted by capability fitness (best first)."""
    sid = strategy_id or requirements.strategy_id
    if sid and sid in STRATEGY_PROVIDER_MAP:
        preferred_id = STRATEGY_PROVIDER_MAP[sid]
        try:
            provider = registry.get(preferred_id)
            score, blockers = _score_provider(provider, requirements)
            if score >= 0:
                return [provider]
        except Exception:
            pass

    ranked: List[Tuple[int, CompatibilityRuntimeProvider]] = []
    for provider in registry.all():
        score, _blockers = _score_provider(provider, requirements)
        if score >= 0:
            ranked.append((score, provider))
    ranked.sort(key=lambda item: (-item[0], item[1].provider_id))
    return [provider for _score, provider in ranked]


def select_provider_for_strategy(
    strategy_id: str,
    registry: RuntimeRegistry,
) -> Optional[CompatibilityRuntimeProvider]:
    requirements = requirements_for_strategy(strategy_id)
    selected = select_providers(requirements, registry, strategy_id=strategy_id)
    return selected[0] if selected else None
