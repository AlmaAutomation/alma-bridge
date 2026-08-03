"""Multi-dimensional coverage validation — symbol, capability, behavior, verified scenario."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set

from alma_bridge.compatibility_intelligence.behavior_requirements import (
    BEHAVIOR_REGISTRY_VERSION,
    get_behavior_profile,
    infer_required_behaviors,
)
from alma_bridge.compatibility_intelligence.models import (
    ApiClassificationResult,
    CapabilityRequirement,
    CoverageReport,
    ImportedFunction,
    PeAnalysisMetadata,
)


@dataclass
class CoverageValidation:
    """Multi-dimensional coverage — do not collapse dimensions."""

    symbol_coverage_percent: float = 0.0
    capability_coverage_percent: float = 0.0
    behavior_coverage_percent: float = 0.0
    verified_scenario_coverage_percent: float = 0.0
    unknown_api_count: int = 0
    unresolved_dynamic_behavior_count: int = 0
    required_behaviors: List[str] = field(default_factory=list)
    unsupported_behaviors: List[str] = field(default_factory=list)
    supported_behaviors: List[str] = field(default_factory=list)
    behavior_gaps: List[str] = field(default_factory=list)
    registry_version: str = BEHAVIOR_REGISTRY_VERSION


def _capability_ids(required: List[CapabilityRequirement]) -> Set[str]:
    return {r.capability_id for r in required}


def compute_coverage_validation(
    coverage: CoverageReport,
    required_capabilities: List[CapabilityRequirement],
    imports: List[ImportedFunction],
    classifications: List[ApiClassificationResult],
    metadata: PeAnalysisMetadata,
    *,
    provider_id: str = "native_alma",
    fixture_name: Optional[str] = None,
) -> CoverageValidation:
    """Compute symbol, capability, behavior, and verified-scenario coverage."""
    provider = coverage.providers.get(provider_id)
    symbol_cov = provider.coverage_percent if provider else 0.0
    cap_cov = symbol_cov

    required_behaviors = infer_required_behaviors(imports, classifications, metadata)
    if fixture_name:
        from alma_bridge.compatibility_intelligence.behavior_requirements import infer_fixture_behaviors

        required_behaviors = required_behaviors | infer_fixture_behaviors(fixture_name)

    supported: Set[str] = set()
    unsupported: Set[str] = set()
    verified_scenarios: Set[str] = set()
    cap_ids = _capability_ids(required_capabilities)

    for cap_id in cap_ids:
        profile = get_behavior_profile(cap_id, provider_id)
        if profile is None:
            continue
        for b in profile.supported_behaviors:
            if b in required_behaviors:
                supported.add(b)
        for b in profile.unsupported_behaviors:
            if b in required_behaviors:
                unsupported.add(b)
        verified_scenarios.update(profile.verified_scenarios)

    # Behaviors required but not in any profile
    unresolved = required_behaviors - supported - unsupported

    behavior_gaps = sorted(unsupported)
    if required_behaviors:
        behavior_cov = round(100.0 * len(supported) / len(required_behaviors), 2)
    else:
        behavior_cov = 100.0

    if verified_scenarios:
        scenario_cov = round(
            100.0 * len(supported & required_behaviors) / max(len(required_behaviors), 1),
            2,
        )
    else:
        scenario_cov = 0.0

    return CoverageValidation(
        symbol_coverage_percent=symbol_cov,
        capability_coverage_percent=cap_cov,
        behavior_coverage_percent=behavior_cov,
        verified_scenario_coverage_percent=scenario_cov,
        unknown_api_count=coverage.unknown_apis,
        unresolved_dynamic_behavior_count=len(unresolved),
        required_behaviors=sorted(required_behaviors),
        unsupported_behaviors=sorted(unsupported),
        supported_behaviors=sorted(supported),
        behavior_gaps=behavior_gaps,
    )
