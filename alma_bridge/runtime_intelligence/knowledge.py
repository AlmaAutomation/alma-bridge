"""Compatibility Knowledge Coverage — pure deterministic formula (Commit 3)."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from alma_bridge.compatibility.profile_fingerprints import sha256_v1

from alma_bridge.runtime_intelligence.models import (
    KNOWLEDGE_COVERAGE_FORMULA_VERSION,
    RUNTIME_INTELLIGENCE_KNOWLEDGE_SCHEMA_VERSION,
    CompatibilityKnowledgeCoverageReport,
    CompatibilityKnowledgeInput,
    EvidenceRatio,
    KnowledgeCoverageComponent,
    KnowledgeCoverageStatus,
)

KNOWLEDGE_COVERAGE_WEIGHTS_V1: Dict[str, float] = {
    "behavior_classification_coverage": 0.25,
    "blocker_explanation_coverage": 0.20,
    "failure_attribution_coverage": 0.20,
    "prediction_outcome_linkage_coverage": 0.15,
    "limitation_documentation_coverage": 0.15,
    "contradiction_quality": 0.05,
}

_COMPONENT_ORDER: tuple[str, ...] = tuple(KNOWLEDGE_COVERAGE_WEIGHTS_V1.keys())


def qualifies_as_explained_blocker(
    *,
    has_bounded_classification: bool,
    has_evidence_references: bool,
    stderr_only: bool,
) -> bool:
    """Blocker counts as explained only with bounded classification and evidence."""
    if stderr_only:
        return False
    if not has_bounded_classification:
        return False
    return has_evidence_references


def qualifies_as_attributed_failure(
    *,
    authoritative: bool,
    attribution_category: Optional[str],
    has_evidence_references: bool,
) -> bool:
    """Failure counts as attributed only when authoritative and evidence-backed."""
    if not authoritative:
        return False
    if not attribution_category:
        return False
    return has_evidence_references


def qualifies_as_documented_limitation(
    *,
    has_bounded_scope: bool,
    has_unsupported_semantics: bool,
    has_profile_or_evidence_ref: bool,
) -> bool:
    """Limitation counts as documented only with explicit scope and references."""
    return has_bounded_scope and has_unsupported_semantics and has_profile_or_evidence_ref


def _dedupe_sorted(values: List[str]) -> List[str]:
    return sorted(set(values))


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
    *,
    zero_denominator_reason: Optional[str] = None,
) -> KnowledgeCoverageComponent:
    refs = _dedupe_sorted(ratio.evidence_references)

    if component_id == "contradiction_quality" and ratio.denominator == 0:
        return KnowledgeCoverageComponent(
            component_id=component_id,
            numerator=ratio.numerator,
            denominator=ratio.denominator,
            raw_weight=raw_weight,
            effective_weight=0.0,
            value=None,
            available=False,
            insufficient_reason=zero_denominator_reason or "no_contradictory_evidence_observed",
            limitations=[],
            evidence_references=refs,
            snapshot_digest=ratio.snapshot_digest,
        )

    if not ratio.available or ratio.denominator == 0:
        return KnowledgeCoverageComponent(
            component_id=component_id,
            numerator=ratio.numerator,
            denominator=ratio.denominator,
            raw_weight=raw_weight,
            effective_weight=0.0,
            value=None,
            available=False,
            insufficient_reason=ratio.insufficient_reason or "insufficient_evidence",
            limitations=[],
            evidence_references=refs,
            snapshot_digest=ratio.snapshot_digest,
        )

    value = _resolve_ratio_value(ratio)
    if value is None:
        return KnowledgeCoverageComponent(
            component_id=component_id,
            numerator=ratio.numerator,
            denominator=ratio.denominator,
            raw_weight=raw_weight,
            effective_weight=0.0,
            value=None,
            available=False,
            insufficient_reason=ratio.insufficient_reason or "insufficient_evidence",
            limitations=[],
            evidence_references=refs,
            snapshot_digest=ratio.snapshot_digest,
        )

    return KnowledgeCoverageComponent(
        component_id=component_id,
        numerator=ratio.numerator,
        denominator=ratio.denominator,
        raw_weight=raw_weight,
        effective_weight=raw_weight,
        value=value,
        available=True,
        insufficient_reason=None,
        limitations=[],
        evidence_references=refs,
        snapshot_digest=ratio.snapshot_digest,
    )


def _build_components(input_data: CompatibilityKnowledgeInput) -> List[KnowledgeCoverageComponent]:
    ratios = {
        "behavior_classification_coverage": input_data.behavior_classification_coverage,
        "blocker_explanation_coverage": input_data.blocker_explanation_coverage,
        "failure_attribution_coverage": input_data.failure_attribution_coverage,
        "prediction_outcome_linkage_coverage": input_data.prediction_outcome_linkage_coverage,
        "limitation_documentation_coverage": input_data.limitation_documentation_coverage,
        "contradiction_quality": input_data.contradiction_quality,
    }
    return [
        _component_from_ratio(
            component_id,
            KNOWLEDGE_COVERAGE_WEIGHTS_V1[component_id],
            ratios[component_id],
            zero_denominator_reason="no_contradictory_evidence_observed"
            if component_id == "contradiction_quality"
            else None,
        )
        for component_id in _COMPONENT_ORDER
    ]


def _renormalize_effective_weights(components: List[KnowledgeCoverageComponent]) -> None:
    for component in components:
        component.effective_weight = component.raw_weight if component.available else 0.0


def _compute_knowledge_value(components: List[KnowledgeCoverageComponent]) -> Optional[float]:
    available = [c for c in components if c.available and c.value is not None]
    if not available:
        return None
    weight_sum = sum(c.raw_weight for c in available)
    if weight_sum <= 0:
        return None
    weighted = sum(c.value * c.raw_weight for c in available)
    return round(weighted / weight_sum, 4)


def compute_knowledge_report_digest(
    *,
    corpus: str,
    family_id: str,
    provider_id: Optional[str],
    components: List[KnowledgeCoverageComponent],
    observed_behavior_count: int,
    classified_behavior_count: int,
    explained_blocker_count: int,
    unknown_behavior_ids: List[str],
    unknown_api_names: List[str],
    attributed_failure_count: int,
    unattributed_failure_count: int,
    contradictory_evidence_count: int,
    evidence_backed_limitations: List[str],
    evidence_references: List[str],
    registry_version: Optional[str],
    provider_version: Optional[str],
    evidence_snapshot_digest: str,
    formula_version: str,
    schema_version: str,
    knowledge_coverage_value: Optional[float],
    status: str,
) -> str:
    payload: Mapping[str, Any] = {
        "corpus": corpus,
        "family_id": family_id,
        "provider_id": provider_id or "",
        "components": [
            {
                "component_id": c.component_id,
                "numerator": c.numerator,
                "denominator": c.denominator,
                "raw_weight": c.raw_weight,
                "effective_weight": c.effective_weight,
                "value": c.value,
                "available": c.available,
                "snapshot_digest": c.snapshot_digest,
            }
            for c in components
        ],
        "observed_behavior_count": observed_behavior_count,
        "classified_behavior_count": classified_behavior_count,
        "explained_blocker_count": explained_blocker_count,
        "unknown_behavior_ids": _dedupe_sorted(unknown_behavior_ids),
        "unknown_api_names": _dedupe_sorted(unknown_api_names),
        "attributed_failure_count": attributed_failure_count,
        "unattributed_failure_count": unattributed_failure_count,
        "contradictory_evidence_count": contradictory_evidence_count,
        "evidence_backed_limitations": _dedupe_sorted(evidence_backed_limitations),
        "evidence_references": _dedupe_sorted(evidence_references),
        "registry_version": registry_version or "",
        "provider_version": provider_version or "",
        "evidence_snapshot_digest": evidence_snapshot_digest,
        "formula_version": formula_version,
        "schema_version": schema_version,
        "knowledge_coverage_value": knowledge_coverage_value,
        "status": status,
    }
    return sha256_v1(payload)


def compute_knowledge_coverage(
    input_data: CompatibilityKnowledgeInput,
) -> CompatibilityKnowledgeCoverageReport:
    """Pure calculator — prepared component inputs only; no repository access."""
    components = _build_components(input_data)
    knowledge_value = _compute_knowledge_value(components)
    _renormalize_effective_weights(components)

    if knowledge_value is None:
        status = KnowledgeCoverageStatus.INSUFFICIENT_EVIDENCE
    else:
        status = KnowledgeCoverageStatus.COMPUTED

    all_refs: List[str] = list(input_data.evidence_references)
    for component in components:
        all_refs.extend(component.evidence_references)
    for field in (
        input_data.behavior_classification_coverage,
        input_data.blocker_explanation_coverage,
        input_data.failure_attribution_coverage,
        input_data.prediction_outcome_linkage_coverage,
        input_data.limitation_documentation_coverage,
        input_data.contradiction_quality,
    ):
        all_refs.extend(field.evidence_references)

    unknown_behavior_ids = _dedupe_sorted(input_data.unknown_behavior_ids)
    unknown_api_names = _dedupe_sorted(input_data.unknown_api_names)
    evidence_backed_limitations = _dedupe_sorted(input_data.evidence_backed_limitations)
    evidence_references = _dedupe_sorted(all_refs)

    report_digest = compute_knowledge_report_digest(
        corpus=input_data.corpus.value,
        family_id=input_data.family_id.value,
        provider_id=input_data.provider_id,
        components=components,
        observed_behavior_count=input_data.observed_behavior_count,
        classified_behavior_count=input_data.classified_behavior_count,
        explained_blocker_count=input_data.explained_blocker_count,
        unknown_behavior_ids=unknown_behavior_ids,
        unknown_api_names=unknown_api_names,
        attributed_failure_count=input_data.attributed_failure_count,
        unattributed_failure_count=input_data.unattributed_failure_count,
        contradictory_evidence_count=input_data.contradictory_evidence_count,
        evidence_backed_limitations=evidence_backed_limitations,
        evidence_references=evidence_references,
        registry_version=input_data.registry_version,
        provider_version=input_data.provider_version,
        evidence_snapshot_digest=input_data.evidence_snapshot_digest,
        formula_version=KNOWLEDGE_COVERAGE_FORMULA_VERSION,
        schema_version=RUNTIME_INTELLIGENCE_KNOWLEDGE_SCHEMA_VERSION,
        knowledge_coverage_value=knowledge_value,
        status=status.value,
    )

    return CompatibilityKnowledgeCoverageReport(
        corpus=input_data.corpus,
        family_id=input_data.family_id,
        provider_id=input_data.provider_id,
        status=status,
        knowledge_coverage_value=knowledge_value,
        components=components,
        observed_behavior_count=input_data.observed_behavior_count,
        classified_behavior_count=input_data.classified_behavior_count,
        explained_blocker_count=input_data.explained_blocker_count,
        unknown_behavior_ids=unknown_behavior_ids,
        unknown_api_names=unknown_api_names,
        attributed_failure_count=input_data.attributed_failure_count,
        unattributed_failure_count=input_data.unattributed_failure_count,
        contradictory_evidence_count=input_data.contradictory_evidence_count,
        evidence_backed_limitations=evidence_backed_limitations,
        formula_version=KNOWLEDGE_COVERAGE_FORMULA_VERSION,
        schema_version=RUNTIME_INTELLIGENCE_KNOWLEDGE_SCHEMA_VERSION,
        limitations=list(input_data.limitations),
        evidence_references=evidence_references,
        report_digest=report_digest,
        registry_version=input_data.registry_version,
        provider_version=input_data.provider_version,
        evidence_snapshot_digest=input_data.evidence_snapshot_digest,
    )
