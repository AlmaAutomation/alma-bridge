"""Compatibility Index — pure deterministic formula (Commit 2)."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from alma_bridge.certification.models import CertificationLevel
from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.compatibility_intelligence.governance.models import CapabilityMaturityState
from alma_bridge.research.models import SampleSize

from alma_bridge.runtime_intelligence.models import (
    COMPATIBILITY_INDEX_FORMULA_VERSION,
    RUNTIME_INTELLIGENCE_INDEX_SCHEMA_VERSION,
    CompatibilityIndexComponent,
    CompatibilityIndexInput,
    CompatibilityIndexReport,
    CompatibilityIndexStatus,
    EvidenceRatio,
)

COMPATIBILITY_INDEX_WEIGHTS_V1: Dict[str, float] = {
    "behavior_coverage": 0.30,
    "authoritative_verification_rate": 0.30,
    "calibration_accuracy": 0.15,
    "governance_maturity": 0.15,
    "certification_level": 0.10,
}

GOVERNANCE_MATURITY_NORMALIZATION_V1: Dict[CapabilityMaturityState, float] = {
    CapabilityMaturityState.DECLARED: 0.00,
    CapabilityMaturityState.EXPERIMENTAL: 0.20,
    CapabilityMaturityState.BEHAVIORALLY_TESTED: 0.40,
    CapabilityMaturityState.CALIBRATION_SUPPORTED: 0.60,
    CapabilityMaturityState.VERIFIED_BOUNDED: 0.80,
    CapabilityMaturityState.STABLE: 1.00,
    CapabilityMaturityState.DEPRECATED: 0.00,
    CapabilityMaturityState.REVOKED: 0.00,
}

CERTIFICATION_LEVEL_NORMALIZATION_V1: Dict[CertificationLevel, float] = {
    CertificationLevel.UNVERIFIED: 0.00,
    CertificationLevel.SPECIFIED: 0.15,
    CertificationLevel.BEHAVIOR_TESTED: 0.30,
    CertificationLevel.VERIFIED: 0.50,
    CertificationLevel.CALIBRATED: 0.65,
    CertificationLevel.GOVERNED: 0.80,
    CertificationLevel.CERTIFIED: 0.90,
    CertificationLevel.PRODUCTION_READY: 1.00,
    CertificationLevel.REQUIRES_REVALIDATION: 0.00,
}

_COMPONENT_ORDER: tuple[str, ...] = tuple(COMPATIBILITY_INDEX_WEIGHTS_V1.keys())


def normalize_governance_maturity(state: CapabilityMaturityState) -> float:
    """Explicit versioned maturity normalization — never ordinal position."""
    return GOVERNANCE_MATURITY_NORMALIZATION_V1[state]


def normalize_certification_level(level: CertificationLevel) -> tuple[float, bool, Optional[str]]:
    """Return (value, available, insufficient_reason)."""
    if level == CertificationLevel.REQUIRES_REVALIDATION:
        return 0.00, False, "certification_requires_revalidation"
    return CERTIFICATION_LEVEL_NORMALIZATION_V1[level], True, None


def evidence_ratio_from_maturity(
    state: CapabilityMaturityState,
    *,
    evidence_references: Optional[List[str]] = None,
    snapshot_digest: Optional[str] = None,
) -> EvidenceRatio:
    value = normalize_governance_maturity(state)
    return EvidenceRatio(
        numerator=1,
        denominator=1,
        value=value,
        available=True,
        evidence_references=evidence_references or [],
        snapshot_digest=snapshot_digest,
    )


def evidence_ratio_from_certification(
    level: CertificationLevel,
    *,
    evidence_references: Optional[List[str]] = None,
    snapshot_digest: Optional[str] = None,
) -> EvidenceRatio:
    value, available, reason = normalize_certification_level(level)
    return EvidenceRatio(
        numerator=1 if available else 0,
        denominator=1 if available else 0,
        value=value if available else None,
        available=available,
        insufficient_reason=reason,
        evidence_references=evidence_references or [],
        snapshot_digest=snapshot_digest,
    )


def _dedupe_refs(refs: List[str]) -> List[str]:
    return sorted(set(refs))


def _resolve_ratio_value(ratio: EvidenceRatio) -> Optional[float]:
    if ratio.value is not None:
        return ratio.value
    if ratio.denominator == 0:
        return None
    return ratio.numerator / ratio.denominator


def _component_from_ratio(
    component_id: str,
    raw_weight: float,
    ratio: EvidenceRatio,
) -> CompatibilityIndexComponent:
    sample_size = SampleSize(numerator=ratio.numerator, denominator=ratio.denominator)
    refs = _dedupe_refs(ratio.evidence_references)

    if not ratio.available or ratio.denominator == 0:
        return CompatibilityIndexComponent(
            component_id=component_id,
            raw_weight=raw_weight,
            effective_weight=0.0,
            value=None,
            available=False,
            sample_size=sample_size,
            limitations=[],
            evidence_references=refs,
            insufficient_reason=ratio.insufficient_reason or "insufficient_evidence",
            snapshot_digest=ratio.snapshot_digest,
        )

    value = _resolve_ratio_value(ratio)
    if value is None:
        return CompatibilityIndexComponent(
            component_id=component_id,
            raw_weight=raw_weight,
            effective_weight=0.0,
            value=None,
            available=False,
            sample_size=sample_size,
            limitations=[],
            evidence_references=refs,
            insufficient_reason=ratio.insufficient_reason or "insufficient_evidence",
            snapshot_digest=ratio.snapshot_digest,
        )

    return CompatibilityIndexComponent(
        component_id=component_id,
        raw_weight=raw_weight,
        effective_weight=raw_weight,
        value=value,
        available=True,
        sample_size=sample_size,
        limitations=[],
        evidence_references=refs,
        insufficient_reason=None,
        snapshot_digest=ratio.snapshot_digest,
    )


def _build_components(input_data: CompatibilityIndexInput) -> List[CompatibilityIndexComponent]:
    ratios = {
        "behavior_coverage": input_data.behavior_coverage,
        "authoritative_verification_rate": input_data.authoritative_verification_rate,
        "calibration_accuracy": input_data.calibration_accuracy,
        "governance_maturity": input_data.governance_maturity,
        "certification_level": input_data.certification_level,
    }
    return [
        _component_from_ratio(component_id, COMPATIBILITY_INDEX_WEIGHTS_V1[component_id], ratios[component_id])
        for component_id in _COMPONENT_ORDER
    ]


def _renormalize_effective_weights(components: List[CompatibilityIndexComponent]) -> None:
    available_weight = sum(c.raw_weight for c in components if c.available)
    if available_weight <= 0:
        for component in components:
            component.effective_weight = 0.0
        return
    for component in components:
        if component.available:
            component.effective_weight = component.raw_weight
        else:
            component.effective_weight = 0.0


def _compute_index_value(components: List[CompatibilityIndexComponent]) -> Optional[float]:
    available = [c for c in components if c.available and c.value is not None]
    if not available:
        return None
    weight_sum = sum(c.raw_weight for c in available)
    if weight_sum <= 0:
        return None
    weighted = sum(c.value * c.raw_weight for c in available)
    return round(weighted / weight_sum, 4)


def compute_report_digest(
    *,
    corpus: str,
    family_id: str,
    provider_id: str,
    components: List[CompatibilityIndexComponent],
    registry_version: Optional[str],
    provider_version: Optional[str],
    evidence_snapshot_digest: str,
    formula_version: str,
    schema_version: str,
    index_value: Optional[float],
    status: str,
) -> str:
    payload: Mapping[str, Any] = {
        "corpus": corpus,
        "family_id": family_id,
        "provider_id": provider_id,
        "components": [
            {
                "component_id": c.component_id,
                "raw_weight": c.raw_weight,
                "effective_weight": c.effective_weight,
                "value": c.value,
                "available": c.available,
                "sample_size": {
                    "numerator": c.sample_size.numerator,
                    "denominator": c.sample_size.denominator,
                },
                "snapshot_digest": c.snapshot_digest,
            }
            for c in components
        ],
        "registry_version": registry_version or "",
        "provider_version": provider_version or "",
        "evidence_snapshot_digest": evidence_snapshot_digest,
        "formula_version": formula_version,
        "schema_version": schema_version,
        "index_value": index_value,
        "status": status,
    }
    return sha256_v1(payload)


def compute_compatibility_index(input_data: CompatibilityIndexInput) -> CompatibilityIndexReport:
    """Pure calculator — prepared component inputs only; no repository access."""
    components = _build_components(input_data)
    index_value = _compute_index_value(components)
    _renormalize_effective_weights(components)

    if index_value is None:
        status = CompatibilityIndexStatus.INSUFFICIENT_EVIDENCE
    else:
        status = CompatibilityIndexStatus.COMPUTED

    all_refs: List[str] = []
    for component in components:
        all_refs.extend(component.evidence_references)
    for field in (
        input_data.behavior_coverage,
        input_data.authoritative_verification_rate,
        input_data.calibration_accuracy,
        input_data.governance_maturity,
        input_data.certification_level,
    ):
        all_refs.extend(field.evidence_references)

    report_digest = compute_report_digest(
        corpus=input_data.corpus.value,
        family_id=input_data.family_id.value,
        provider_id=input_data.provider_id,
        components=components,
        registry_version=input_data.registry_version,
        provider_version=input_data.provider_version,
        evidence_snapshot_digest=input_data.evidence_snapshot_digest,
        formula_version=COMPATIBILITY_INDEX_FORMULA_VERSION,
        schema_version=RUNTIME_INTELLIGENCE_INDEX_SCHEMA_VERSION,
        index_value=index_value,
        status=status.value,
    )

    return CompatibilityIndexReport(
        corpus=input_data.corpus,
        family_id=input_data.family_id,
        provider_id=input_data.provider_id,
        index_value=index_value,
        status=status,
        components=components,
        formula_version=COMPATIBILITY_INDEX_FORMULA_VERSION,
        schema_version=RUNTIME_INTELLIGENCE_INDEX_SCHEMA_VERSION,
        limitations=list(input_data.limitations),
        evidence_references=_dedupe_refs(all_refs),
        report_digest=report_digest,
        registry_version=input_data.registry_version,
        provider_version=input_data.provider_version,
        evidence_snapshot_digest=input_data.evidence_snapshot_digest,
        generated_from=input_data.generated_from,
    )
