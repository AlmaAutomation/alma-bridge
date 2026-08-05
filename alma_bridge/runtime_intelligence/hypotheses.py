"""Engineering hypothesis tracking — immutable snapshots and outcome evaluation (Commit 5)."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.compatibility_intelligence.models import ConfidenceLevelName

from alma_bridge.runtime_intelligence.models import (
    HYPOTHESIS_FORMULA_VERSION,
    RUNTIME_INTELLIGENCE_HYPOTHESIS_SCHEMA_VERSION,
    BehaviorFamilyId,
    CorpusKind,
    EngineeringHypothesisEvaluation,
    EngineeringHypothesisOutcomeLink,
    EngineeringHypothesisResult,
    EngineeringHypothesisSnapshot,
)

PROHIBITED_BROAD_SCOPE_PHRASES = (
    "implement full kernel32",
    "support windows applications",
    "fix compatibility",
    "full win32",
    "all applications",
)

HYPOTHESIS_EVENT_TYPE_CREATED = "EngineeringHypothesisCreated"
HYPOTHESIS_EVENT_TYPE_OUTCOME_LINKED = "EngineeringHypothesisOutcomeLinked"


def _dedupe_sorted(values: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def validate_bounded_scope(bounded_scope: str) -> None:
    normalized = (bounded_scope or "").strip().lower()
    if not normalized:
        raise ValueError("bounded_scope is required")
    for phrase in PROHIBITED_BROAD_SCOPE_PHRASES:
        if phrase in normalized:
            raise ValueError(f"bounded_scope is too broad: contains prohibited phrase '{phrase}'")


def validate_application_fingerprints_for_corpus(
    *,
    corpus: CorpusKind,
    fingerprints: Sequence[str],
    fingerprint_corpus: Optional[Mapping[str, CorpusKind]] = None,
) -> None:
    if fingerprint_corpus:
        for fingerprint in fingerprints:
            mapped = fingerprint_corpus.get(fingerprint)
            if mapped is not None and mapped != corpus:
                raise ValueError("cross-corpus application fingerprint rejected")


def compute_hypothesis_id(
    *,
    corpus: CorpusKind,
    provider_id: str,
    provider_version_scope: str,
    family_id: BehaviorFamilyId,
    capability_id: str,
    behavior_id: Optional[str],
    bounded_scope: str,
    source_expansion_candidate_ids: Sequence[str],
    evidence_snapshot_digest: str,
) -> str:
    return sha256_v1(
        {
            "corpus": corpus.value,
            "provider_id": provider_id,
            "provider_version_scope": provider_version_scope,
            "family_id": family_id.value,
            "capability_id": capability_id,
            "behavior_id": behavior_id or "",
            "bounded_scope": bounded_scope,
            "source_expansion_candidate_ids": _dedupe_sorted(source_expansion_candidate_ids),
            "evidence_snapshot_digest": evidence_snapshot_digest,
        }
    )


def compute_snapshot_digest_fields(
    *,
    hypothesis_id: str,
    corpus: CorpusKind,
    provider_id: str,
    provider_version_scope: str,
    family_id: BehaviorFamilyId,
    capability_id: str,
    behavior_id: Optional[str],
    bounded_scope: str,
    predicted_application_fingerprints: Sequence[str],
    predicted_binary_digests: Sequence[str],
    predicted_application_classes: Sequence[str],
    predicted_applications_unblocked_count: int,
    predicted_application_classes_unblocked_count: int,
    predicted_confidence: str,
    predicted_limitations: Sequence[str],
    source_expansion_candidate_ids: Sequence[str],
    source_debt_item_ids: Sequence[str],
    source_registry_version: str,
    source_expansion_plan_version: str,
    evidence_snapshot_digest: str,
    evidence_references: Sequence[str],
    formula_version: str,
    schema_version: str,
) -> str:
    payload: Mapping[str, Any] = {
        "hypothesis_id": hypothesis_id,
        "corpus": corpus.value,
        "provider_id": provider_id,
        "provider_version_scope": provider_version_scope,
        "family_id": family_id.value,
        "capability_id": capability_id,
        "behavior_id": behavior_id or "",
        "bounded_scope": bounded_scope,
        "predicted_application_fingerprints": _dedupe_sorted(predicted_application_fingerprints),
        "predicted_binary_digests": _dedupe_sorted(predicted_binary_digests),
        "predicted_application_classes": _dedupe_sorted(predicted_application_classes),
        "predicted_applications_unblocked_count": predicted_applications_unblocked_count,
        "predicted_application_classes_unblocked_count": predicted_application_classes_unblocked_count,
        "predicted_confidence": predicted_confidence,
        "predicted_limitations": _dedupe_sorted(predicted_limitations),
        "source_expansion_candidate_ids": _dedupe_sorted(source_expansion_candidate_ids),
        "source_debt_item_ids": _dedupe_sorted(source_debt_item_ids),
        "source_registry_version": source_registry_version,
        "source_expansion_plan_version": source_expansion_plan_version,
        "evidence_snapshot_digest": evidence_snapshot_digest,
        "evidence_references": _dedupe_sorted(evidence_references),
        "formula_version": formula_version,
        "schema_version": schema_version,
    }
    return sha256_v1(payload)


def create_hypothesis_snapshot(
    *,
    created_at: str,
    corpus: CorpusKind,
    provider_id: str,
    provider_version_scope: str,
    family_id: BehaviorFamilyId,
    capability_id: str,
    bounded_scope: str,
    evidence_snapshot_digest: str,
    evidence_references: Sequence[str],
    behavior_id: Optional[str] = None,
    predicted_application_fingerprints: Optional[Sequence[str]] = None,
    predicted_binary_digests: Optional[Sequence[str]] = None,
    predicted_application_classes: Optional[Sequence[str]] = None,
    predicted_applications_unblocked_count: int = 0,
    predicted_application_classes_unblocked_count: int = 0,
    predicted_confidence: str = "unknown",
    predicted_limitations: Optional[Sequence[str]] = None,
    source_expansion_candidate_ids: Optional[Sequence[str]] = None,
    source_debt_item_ids: Optional[Sequence[str]] = None,
    source_registry_version: str = "",
    source_expansion_plan_version: str = "",
    fingerprint_corpus: Optional[Mapping[str, CorpusKind]] = None,
) -> EngineeringHypothesisSnapshot:
    validate_bounded_scope(bounded_scope)
    if not (evidence_snapshot_digest or "").strip():
        raise ValueError("evidence_snapshot_digest is required")
    if not evidence_references:
        raise ValueError("at least one evidence reference is required")
    if not (provider_id or "").strip():
        raise ValueError("provider_id is required")
    if not (provider_version_scope or "").strip():
        raise ValueError("provider_version_scope is required")

    predicted_fps = _dedupe_sorted(predicted_application_fingerprints or [])
    predicted_bins = _dedupe_sorted(predicted_binary_digests or [])
    predicted_classes = _dedupe_sorted(predicted_application_classes or [])

    if not predicted_fps and not predicted_classes:
        raise ValueError("at least one predicted application fingerprint or application class is required")

    validate_application_fingerprints_for_corpus(
        corpus=corpus,
        fingerprints=predicted_fps,
        fingerprint_corpus=fingerprint_corpus,
    )

    candidate_ids = _dedupe_sorted(source_expansion_candidate_ids or [])
    debt_ids = _dedupe_sorted(source_debt_item_ids or [])
    limitations = _dedupe_sorted(predicted_limitations or [])
    refs = _dedupe_sorted(evidence_references)

    hypothesis_id = compute_hypothesis_id(
        corpus=corpus,
        provider_id=provider_id,
        provider_version_scope=provider_version_scope,
        family_id=family_id,
        capability_id=capability_id,
        behavior_id=behavior_id,
        bounded_scope=bounded_scope,
        source_expansion_candidate_ids=candidate_ids,
        evidence_snapshot_digest=evidence_snapshot_digest,
    )

    snapshot_digest = compute_snapshot_digest_fields(
        hypothesis_id=hypothesis_id,
        corpus=corpus,
        provider_id=provider_id,
        provider_version_scope=provider_version_scope,
        family_id=family_id,
        capability_id=capability_id,
        behavior_id=behavior_id,
        bounded_scope=bounded_scope,
        predicted_application_fingerprints=predicted_fps,
        predicted_binary_digests=predicted_bins,
        predicted_application_classes=predicted_classes,
        predicted_applications_unblocked_count=predicted_applications_unblocked_count,
        predicted_application_classes_unblocked_count=predicted_application_classes_unblocked_count,
        predicted_confidence=predicted_confidence,
        predicted_limitations=limitations,
        source_expansion_candidate_ids=candidate_ids,
        source_debt_item_ids=debt_ids,
        source_registry_version=source_registry_version,
        source_expansion_plan_version=source_expansion_plan_version,
        evidence_snapshot_digest=evidence_snapshot_digest,
        evidence_references=refs,
        formula_version=HYPOTHESIS_FORMULA_VERSION,
        schema_version=RUNTIME_INTELLIGENCE_HYPOTHESIS_SCHEMA_VERSION,
    )

    return EngineeringHypothesisSnapshot(
        hypothesis_id=hypothesis_id,
        created_at=created_at,
        corpus=corpus,
        provider_id=provider_id,
        provider_version_scope=provider_version_scope,
        family_id=family_id,
        capability_id=capability_id,
        behavior_id=behavior_id,
        bounded_scope=bounded_scope,
        predicted_application_fingerprints=predicted_fps,
        predicted_binary_digests=predicted_bins,
        predicted_application_classes=predicted_classes,
        predicted_applications_unblocked_count=predicted_applications_unblocked_count,
        predicted_application_classes_unblocked_count=predicted_application_classes_unblocked_count,
        predicted_confidence=predicted_confidence,
        predicted_limitations=limitations,
        source_expansion_candidate_ids=candidate_ids,
        source_debt_item_ids=debt_ids,
        source_registry_version=source_registry_version,
        source_expansion_plan_version=source_expansion_plan_version,
        evidence_snapshot_digest=evidence_snapshot_digest,
        evidence_references=refs,
        schema_version=RUNTIME_INTELLIGENCE_HYPOTHESIS_SCHEMA_VERSION,
        formula_version=HYPOTHESIS_FORMULA_VERSION,
        snapshot_digest=snapshot_digest,
    )


def compute_outcome_link_id(
    *,
    hypothesis_id: str,
    implementation_work_item_id: Optional[str],
    implementation_version: Optional[str],
    evidence_snapshot_digest: str,
) -> str:
    return sha256_v1(
        {
            "hypothesis_id": hypothesis_id,
            "implementation_work_item_id": implementation_work_item_id or "",
            "implementation_version": implementation_version or "",
            "evidence_snapshot_digest": evidence_snapshot_digest,
        }
    )


def compute_outcome_link_digest_fields(
    *,
    outcome_link_id: str,
    hypothesis_id: str,
    implementation_work_item_id: Optional[str],
    implementation_version: Optional[str],
    provider_version: Optional[str],
    observed_application_fingerprints: Sequence[str],
    observed_binary_digests: Sequence[str],
    observed_application_classes: Sequence[str],
    observed_verified_successes: int,
    observed_verified_failures: int,
    observed_unverifiable: int,
    observed_blockers_removed: Sequence[str],
    observed_new_blockers: Sequence[str],
    authoritative_outcome_references: Sequence[str],
    calibration_record_ids: Sequence[str],
    certification_artifact_ids: Sequence[str],
    governance_artifact_ids: Sequence[str],
    evidence_snapshot_digest: str,
    evidence_references: Sequence[str],
    schema_version: str,
) -> str:
    payload: Mapping[str, Any] = {
        "outcome_link_id": outcome_link_id,
        "hypothesis_id": hypothesis_id,
        "implementation_work_item_id": implementation_work_item_id or "",
        "implementation_version": implementation_version or "",
        "provider_version": provider_version or "",
        "observed_application_fingerprints": _dedupe_sorted(observed_application_fingerprints),
        "observed_binary_digests": _dedupe_sorted(observed_binary_digests),
        "observed_application_classes": _dedupe_sorted(observed_application_classes),
        "observed_verified_successes": observed_verified_successes,
        "observed_verified_failures": observed_verified_failures,
        "observed_unverifiable": observed_unverifiable,
        "observed_blockers_removed": _dedupe_sorted(observed_blockers_removed),
        "observed_new_blockers": _dedupe_sorted(observed_new_blockers),
        "authoritative_outcome_references": _dedupe_sorted(authoritative_outcome_references),
        "calibration_record_ids": _dedupe_sorted(calibration_record_ids),
        "certification_artifact_ids": _dedupe_sorted(certification_artifact_ids),
        "governance_artifact_ids": _dedupe_sorted(governance_artifact_ids),
        "evidence_snapshot_digest": evidence_snapshot_digest,
        "evidence_references": _dedupe_sorted(evidence_references),
        "schema_version": schema_version,
    }
    return sha256_v1(payload)


def create_outcome_link(
    *,
    snapshot: EngineeringHypothesisSnapshot,
    linked_at: str,
    evidence_snapshot_digest: str,
    evidence_references: Sequence[str],
    implementation_work_item_id: Optional[str] = None,
    implementation_version: Optional[str] = None,
    provider_version: Optional[str] = None,
    observed_application_fingerprints: Optional[Sequence[str]] = None,
    observed_binary_digests: Optional[Sequence[str]] = None,
    observed_application_classes: Optional[Sequence[str]] = None,
    observed_verified_successes: int = 0,
    observed_verified_failures: int = 0,
    observed_unverifiable: int = 0,
    observed_blockers_removed: Optional[Sequence[str]] = None,
    observed_new_blockers: Optional[Sequence[str]] = None,
    authoritative_outcome_references: Optional[Sequence[str]] = None,
    calibration_record_ids: Optional[Sequence[str]] = None,
    certification_artifact_ids: Optional[Sequence[str]] = None,
    governance_artifact_ids: Optional[Sequence[str]] = None,
    stderr_only_failure: bool = False,
    fingerprint_corpus: Optional[Mapping[str, CorpusKind]] = None,
) -> EngineeringHypothesisOutcomeLink:
    if not (evidence_snapshot_digest or "").strip():
        raise ValueError("evidence_snapshot_digest is required")
    if not evidence_references and not authoritative_outcome_references:
        raise ValueError("at least one evidence or authoritative outcome reference is required")

    observed_fps = _dedupe_sorted(observed_application_fingerprints or [])
    validate_application_fingerprints_for_corpus(
        corpus=snapshot.corpus,
        fingerprints=observed_fps,
        fingerprint_corpus=fingerprint_corpus,
    )

    outcome_link_id = compute_outcome_link_id(
        hypothesis_id=snapshot.hypothesis_id,
        implementation_work_item_id=implementation_work_item_id,
        implementation_version=implementation_version,
        evidence_snapshot_digest=evidence_snapshot_digest,
    )

    link_digest = compute_outcome_link_digest_fields(
        outcome_link_id=outcome_link_id,
        hypothesis_id=snapshot.hypothesis_id,
        implementation_work_item_id=implementation_work_item_id,
        implementation_version=implementation_version,
        provider_version=provider_version,
        observed_application_fingerprints=observed_fps,
        observed_binary_digests=_dedupe_sorted(observed_binary_digests or []),
        observed_application_classes=_dedupe_sorted(observed_application_classes or []),
        observed_verified_successes=observed_verified_successes,
        observed_verified_failures=observed_verified_failures,
        observed_unverifiable=observed_unverifiable,
        observed_blockers_removed=_dedupe_sorted(observed_blockers_removed or []),
        observed_new_blockers=_dedupe_sorted(observed_new_blockers or []),
        authoritative_outcome_references=_dedupe_sorted(authoritative_outcome_references or []),
        calibration_record_ids=_dedupe_sorted(calibration_record_ids or []),
        certification_artifact_ids=_dedupe_sorted(certification_artifact_ids or []),
        governance_artifact_ids=_dedupe_sorted(governance_artifact_ids or []),
        evidence_snapshot_digest=evidence_snapshot_digest,
        evidence_references=_dedupe_sorted(evidence_references or []),
        schema_version=RUNTIME_INTELLIGENCE_HYPOTHESIS_SCHEMA_VERSION,
    )

    return EngineeringHypothesisOutcomeLink(
        outcome_link_id=outcome_link_id,
        hypothesis_id=snapshot.hypothesis_id,
        linked_at=linked_at,
        implementation_work_item_id=implementation_work_item_id,
        implementation_version=implementation_version,
        provider_version=provider_version,
        observed_application_fingerprints=observed_fps,
        observed_binary_digests=_dedupe_sorted(observed_binary_digests or []),
        observed_application_classes=_dedupe_sorted(observed_application_classes or []),
        observed_verified_successes=observed_verified_successes,
        observed_verified_failures=observed_verified_failures,
        observed_unverifiable=observed_unverifiable,
        observed_blockers_removed=_dedupe_sorted(observed_blockers_removed or []),
        observed_new_blockers=_dedupe_sorted(observed_new_blockers or []),
        authoritative_outcome_references=_dedupe_sorted(authoritative_outcome_references or []),
        calibration_record_ids=_dedupe_sorted(calibration_record_ids or []),
        certification_artifact_ids=_dedupe_sorted(certification_artifact_ids or []),
        governance_artifact_ids=_dedupe_sorted(governance_artifact_ids or []),
        evidence_snapshot_digest=evidence_snapshot_digest,
        evidence_references=_dedupe_sorted(evidence_references or []),
        stderr_only_failure=stderr_only_failure,
        schema_version=RUNTIME_INTELLIGENCE_HYPOTHESIS_SCHEMA_VERSION,
        link_digest=link_digest,
    )


def _aggregate_outcome_links(
    links: Sequence[EngineeringHypothesisOutcomeLink],
) -> Dict[str, Any]:
    sorted_links = sorted(links, key=lambda link: link.link_digest)
    observed_apps: set[str] = set()
    observed_classes: set[str] = set()
    observed_blockers_removed: set[str] = set()
    observed_new_blockers: set[str] = set()
    authoritative_refs: set[str] = set()
    evidence_refs: set[str] = set()
    verified_successes = 0
    verified_failures = 0
    stderr_only_failures = 0
    has_implementation = False

    for link in sorted_links:
        observed_apps.update(link.observed_application_fingerprints)
        observed_classes.update(link.observed_application_classes)
        observed_blockers_removed.update(link.observed_blockers_removed)
        observed_new_blockers.update(link.observed_new_blockers)
        authoritative_refs.update(link.authoritative_outcome_references)
        evidence_refs.update(link.evidence_references)
        verified_successes += link.observed_verified_successes
        verified_failures += link.observed_verified_failures
        if link.stderr_only_failure:
            stderr_only_failures += link.observed_verified_failures
        if link.implementation_work_item_id:
            has_implementation = True

    return {
        "sorted_links": sorted_links,
        "observed_apps": observed_apps,
        "observed_classes": observed_classes,
        "observed_blockers_removed": observed_blockers_removed,
        "observed_new_blockers": observed_new_blockers,
        "authoritative_refs": authoritative_refs,
        "evidence_refs": evidence_refs,
        "verified_successes": verified_successes,
        "verified_failures": verified_failures,
        "stderr_only_failures": stderr_only_failures,
        "has_implementation": has_implementation,
    }


def derive_hypothesis_confidence(
    *,
    authoritative_outcome_count: int,
    distinct_application_count: int,
    distinct_class_count: int,
    evidence_fresh: bool,
    fixture_available: bool,
    contradictory_evidence_count: int,
    provider_version_consistent: bool,
    calibration_linkage_count: int,
) -> tuple[ConfidenceLevelName, List[str]]:
    factors: List[str] = [
        f"authoritative_outcomes={authoritative_outcome_count}",
        f"distinct_applications={distinct_application_count}",
        f"distinct_classes={distinct_class_count}",
        f"evidence_fresh={evidence_fresh}",
        f"fixture_available={fixture_available}",
        f"contradictory_evidence={contradictory_evidence_count}",
        f"provider_version_consistent={provider_version_consistent}",
        f"calibration_linkage={calibration_linkage_count}",
    ]

    if authoritative_outcome_count == 0:
        return ConfidenceLevelName.UNKNOWN, factors

    level = ConfidenceLevelName.UNKNOWN
    if (
        authoritative_outcome_count >= 5
        and distinct_application_count >= 3
        and distinct_class_count >= 2
        and evidence_fresh
        and fixture_available
        and provider_version_consistent
        and contradictory_evidence_count == 0
    ):
        level = ConfidenceLevelName.VERY_HIGH
    elif (
        authoritative_outcome_count >= 3
        and distinct_application_count >= 2
        and contradictory_evidence_count == 0
    ):
        level = ConfidenceLevelName.HIGH
    elif authoritative_outcome_count >= 1:
        level = ConfidenceLevelName.MEDIUM
    else:
        level = ConfidenceLevelName.LOW

    if contradictory_evidence_count > 0:
        factors.append("contradictory_evidence_lowers_confidence")
        downgrade = {
            ConfidenceLevelName.VERY_HIGH: ConfidenceLevelName.HIGH,
            ConfidenceLevelName.HIGH: ConfidenceLevelName.MEDIUM,
            ConfidenceLevelName.MEDIUM: ConfidenceLevelName.LOW,
            ConfidenceLevelName.LOW: ConfidenceLevelName.UNKNOWN,
        }
        level = downgrade.get(level, ConfidenceLevelName.UNKNOWN)

    if not provider_version_consistent:
        factors.append("provider_version_inconsistent")
        if level == ConfidenceLevelName.VERY_HIGH:
            level = ConfidenceLevelName.HIGH

    return level, factors


def classify_hypothesis_result(
    *,
    snapshot: EngineeringHypothesisSnapshot,
    aggregated: Mapping[str, Any],
    provider_version_consistent: bool,
    scope_consistent: bool,
) -> EngineeringHypothesisResult:
    authoritative_count = len(aggregated["authoritative_refs"])
    verified_failures = aggregated["verified_failures"]
    stderr_only_failures = aggregated["stderr_only_failures"]
    authoritative_failures = verified_failures - stderr_only_failures

    observed_apps = len(aggregated["observed_apps"])
    observed_classes = len(aggregated["observed_classes"])
    predicted_apps = snapshot.predicted_applications_unblocked_count
    predicted_classes = snapshot.predicted_application_classes_unblocked_count

    if not provider_version_consistent or not scope_consistent:
        return EngineeringHypothesisResult.CONTRADICTED

    if aggregated["observed_new_blockers"]:
        return EngineeringHypothesisResult.CONTRADICTED

    if authoritative_failures > 0:
        return EngineeringHypothesisResult.CONTRADICTED

    if (
        aggregated["has_implementation"]
        and predicted_apps > 0
        and observed_apps == 0
        and authoritative_count > 0
    ):
        return EngineeringHypothesisResult.CONTRADICTED

    if authoritative_count == 0:
        return EngineeringHypothesisResult.INDETERMINATE

    if (
        observed_apps >= predicted_apps
        and observed_classes >= predicted_classes
    ):
        return EngineeringHypothesisResult.CONFIRMED

    if observed_apps > 0 or observed_classes > 0:
        return EngineeringHypothesisResult.PARTIALLY_CONFIRMED

    return EngineeringHypothesisResult.INDETERMINATE


def compute_evaluation_digest(
    *,
    snapshot_digest: str,
    outcome_link_digests: Sequence[str],
    result: EngineeringHypothesisResult,
    application_variance: int,
    application_class_variance: int,
    confidence: str,
    limitations: Sequence[str],
    evidence_references: Sequence[str],
) -> str:
    payload: Mapping[str, Any] = {
        "snapshot_digest": snapshot_digest,
        "outcome_link_digests": sorted(outcome_link_digests),
        "result": result.value,
        "application_variance": application_variance,
        "application_class_variance": application_class_variance,
        "confidence": confidence,
        "limitations": _dedupe_sorted(limitations),
        "evidence_references": _dedupe_sorted(evidence_references),
        "formula_version": HYPOTHESIS_FORMULA_VERSION,
        "schema_version": RUNTIME_INTELLIGENCE_HYPOTHESIS_SCHEMA_VERSION,
    }
    return sha256_v1(payload)


def evaluate_hypothesis(
    *,
    snapshot: EngineeringHypothesisSnapshot,
    outcome_links: Sequence[EngineeringHypothesisOutcomeLink],
    provider_version_consistent: bool = True,
    scope_consistent: bool = True,
    evidence_fresh: bool = True,
    fixture_available: bool = False,
    contradictory_evidence_count: int = 0,
    limitations: Optional[Sequence[str]] = None,
) -> EngineeringHypothesisEvaluation:
    aggregated = _aggregate_outcome_links(outcome_links)

    observed_apps = len(aggregated["observed_apps"])
    observed_classes = len(aggregated["observed_classes"])
    predicted_apps = snapshot.predicted_applications_unblocked_count
    predicted_classes = snapshot.predicted_application_classes_unblocked_count

    application_variance = observed_apps - predicted_apps
    application_class_variance = observed_classes - predicted_classes

    result = classify_hypothesis_result(
        snapshot=snapshot,
        aggregated=aggregated,
        provider_version_consistent=provider_version_consistent,
        scope_consistent=scope_consistent,
    )

    calibration_count = sum(len(link.calibration_record_ids) for link in aggregated["sorted_links"])
    confidence, confidence_factors = derive_hypothesis_confidence(
        authoritative_outcome_count=len(aggregated["authoritative_refs"]),
        distinct_application_count=observed_apps,
        distinct_class_count=observed_classes,
        evidence_fresh=evidence_fresh,
        fixture_available=fixture_available,
        contradictory_evidence_count=contradictory_evidence_count,
        provider_version_consistent=provider_version_consistent,
        calibration_linkage_count=calibration_count,
    )

    eval_limitations = list(limitations or [])
    eval_limitations.append("planning accuracy measurement only; not authorization to implement")
    eval_refs = sorted(set(list(snapshot.evidence_references) + list(aggregated["evidence_refs"])))
    link_digests = sorted(link.link_digest for link in aggregated["sorted_links"])

    evaluation_digest = compute_evaluation_digest(
        snapshot_digest=snapshot.snapshot_digest,
        outcome_link_digests=link_digests,
        result=result,
        application_variance=application_variance,
        application_class_variance=application_class_variance,
        confidence=confidence.value,
        limitations=eval_limitations,
        evidence_references=eval_refs,
    )

    return EngineeringHypothesisEvaluation(
        hypothesis_id=snapshot.hypothesis_id,
        corpus=snapshot.corpus,
        family_id=snapshot.family_id,
        capability_id=snapshot.capability_id,
        behavior_id=snapshot.behavior_id,
        result=result,
        predicted_applications_unblocked_count=predicted_apps,
        observed_applications_unblocked_count=observed_apps,
        predicted_application_classes_unblocked_count=predicted_classes,
        observed_application_classes_unblocked_count=observed_classes,
        application_variance=application_variance,
        application_class_variance=application_class_variance,
        observed_verified_successes=aggregated["verified_successes"],
        observed_verified_failures=aggregated["verified_failures"],
        confidence=confidence.value,
        confidence_factors=confidence_factors,
        limitations=eval_limitations,
        evidence_references=eval_refs,
        outcome_link_digests=link_digests,
        snapshot_digest=snapshot.snapshot_digest,
        evaluation_digest=evaluation_digest,
    )


def build_hypothesis_created_event_payload(
    snapshot: EngineeringHypothesisSnapshot,
) -> Dict[str, Any]:
    """Deterministic timeline payload — no persistence."""
    return {
        "event_type": HYPOTHESIS_EVENT_TYPE_CREATED,
        "schema_version": RUNTIME_INTELLIGENCE_HYPOTHESIS_SCHEMA_VERSION,
        "hypothesis_id": snapshot.hypothesis_id,
        "created_at": snapshot.created_at,
        "corpus": snapshot.corpus.value,
        "provider_id": snapshot.provider_id,
        "provider_version_scope": snapshot.provider_version_scope,
        "family_id": snapshot.family_id.value,
        "capability_id": snapshot.capability_id,
        "behavior_id": snapshot.behavior_id or "",
        "bounded_scope": snapshot.bounded_scope,
        "snapshot_digest": snapshot.snapshot_digest,
        "evidence_snapshot_digest": snapshot.evidence_snapshot_digest,
        "evidence_references": list(snapshot.evidence_references),
        "predicted_applications_unblocked_count": snapshot.predicted_applications_unblocked_count,
        "predicted_application_classes_unblocked_count": snapshot.predicted_application_classes_unblocked_count,
    }


def build_hypothesis_outcome_linked_event_payload(
    link: EngineeringHypothesisOutcomeLink,
) -> Dict[str, Any]:
    """Deterministic timeline payload — no persistence."""
    return {
        "event_type": HYPOTHESIS_EVENT_TYPE_OUTCOME_LINKED,
        "schema_version": RUNTIME_INTELLIGENCE_HYPOTHESIS_SCHEMA_VERSION,
        "outcome_link_id": link.outcome_link_id,
        "hypothesis_id": link.hypothesis_id,
        "linked_at": link.linked_at,
        "link_digest": link.link_digest,
        "evidence_snapshot_digest": link.evidence_snapshot_digest,
        "implementation_work_item_id": link.implementation_work_item_id or "",
        "implementation_version": link.implementation_version or "",
        "observed_verified_successes": link.observed_verified_successes,
        "observed_verified_failures": link.observed_verified_failures,
        "authoritative_outcome_references": list(link.authoritative_outcome_references),
        "evidence_references": list(link.evidence_references),
    }
