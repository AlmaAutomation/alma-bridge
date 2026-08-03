"""Coverage engine — compute provider capability coverage for an executable."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Set

from alma_bridge.compatibility_intelligence.apis import classify_import
from alma_bridge.compatibility_intelligence.capabilities import (
    PROVIDER_IDS,
    get_capability,
    provider_status,
)
from alma_bridge.compatibility_intelligence.models import (
    ApiClassificationResult,
    CapabilityRequirement,
    CoverageReport,
    ImplementationStatus,
    ImportedFunction,
    ProviderCoverageBreakdown,
    ProvenanceEvidence,
)


_STATUS_BUCKETS = (
    ImplementationStatus.SUPPORTED,
    ImplementationStatus.PARTIAL,
    ImplementationStatus.UNSUPPORTED,
    ImplementationStatus.DELEGATED,
    ImplementationStatus.EXPERIMENTAL,
    ImplementationStatus.UNKNOWN,
)


def _status_weight(status: ImplementationStatus) -> float:
    return {
        ImplementationStatus.SUPPORTED: 1.0,
        ImplementationStatus.PARTIAL: 0.75,
        ImplementationStatus.DELEGATED: 0.6,
        ImplementationStatus.EXPERIMENTAL: 0.5,
        ImplementationStatus.UNSUPPORTED: 0.0,
        ImplementationStatus.UNKNOWN: 0.0,
    }.get(status, 0.0)


def classify_all_imports(
    imports: List[ImportedFunction],
    *,
    provenance: ProvenanceEvidence,
) -> List[ApiClassificationResult]:
    results: List[ApiClassificationResult] = []
    for imp in imports:
        results.append(classify_import(imp.dll, imp.name, provenance=provenance))
    return results


def build_required_capabilities(
    classifications: List[ApiClassificationResult],
) -> List[CapabilityRequirement]:
    by_cap: Dict[str, CapabilityRequirement] = {}
    for cls in classifications:
        cap_id = cls.capability_id
        if cap_id not in by_cap:
            cap_def = get_capability(cap_id)
            by_cap[cap_id] = CapabilityRequirement(
                capability_id=cap_id,
                description=cap_def.description if cap_def else "Unknown capability",
                complexity=cls.complexity,
                required_by_apis=[],
            )
        api_label = f"{cls.dll}!{cls.function}"
        if api_label not in by_cap[cap_id].required_by_apis:
            by_cap[cap_id].required_by_apis.append(api_label)
    for req in by_cap.values():
        req.required_by_apis.sort()
    return sorted(by_cap.values(), key=lambda r: r.capability_id)


def compute_coverage(
    classifications: List[ApiClassificationResult],
    required_capabilities: List[CapabilityRequirement],
    *,
    extra_capability_ids: List[str] | None = None,
) -> CoverageReport:
    """Compute per-provider coverage from API classifications and required capabilities."""
    cap_ids: Set[str] = {r.capability_id for r in required_capabilities}
    if extra_capability_ids:
        cap_ids.update(extra_capability_ids)

    unknown_apis = sorted(
        f"{c.dll}!{c.function}" for c in classifications if not c.is_known
    )
    unsupported_apis = sorted(
        f"{c.dll}!{c.function}"
        for c in classifications
        if c.is_known
        and c.native_status == ImplementationStatus.UNSUPPORTED
        and c.wine_status == ImplementationStatus.UNSUPPORTED
    )

    providers: Dict[str, ProviderCoverageBreakdown] = {}
    for provider_id in PROVIDER_IDS:
        breakdown = ProviderCoverageBreakdown(
            provider_id=provider_id,
            total=len(cap_ids),
        )
        weighted_sum = 0.0
        blockers: List[str] = []

        for cap_id in sorted(cap_ids):
            status = provider_status(cap_id, provider_id)
            if status == ImplementationStatus.SUPPORTED:
                breakdown.supported += 1
            elif status == ImplementationStatus.PARTIAL:
                breakdown.partial += 1
            elif status == ImplementationStatus.UNSUPPORTED:
                breakdown.unsupported += 1
                blockers.append(f"{cap_id}=unsupported")
            elif status == ImplementationStatus.DELEGATED:
                breakdown.delegated += 1
            elif status == ImplementationStatus.EXPERIMENTAL:
                breakdown.experimental += 1
            else:
                breakdown.unknown += 1
                blockers.append(f"{cap_id}=unknown")
            weighted_sum += _status_weight(status)

        if cap_ids:
            breakdown.coverage_percent = round(100.0 * weighted_sum / len(cap_ids), 2)
        breakdown.blockers = sorted(blockers)
        providers[provider_id] = breakdown

    return CoverageReport(
        total_capabilities=len(cap_ids),
        total_apis=len(classifications),
        known_apis=sum(1 for c in classifications if c.is_known),
        unknown_apis=len(unknown_apis),
        providers=providers,
        unsupported_api_names=unsupported_apis,
        unknown_api_names=unknown_apis,
    )
