"""Compatibility Debt classification — pure deterministic rules (Commit 4)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Mapping, Optional, Sequence

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.native_lab.models import RiskSeverity

from alma_bridge.runtime_intelligence.models import (
    DEBT_CLASSIFICATION_FORMULA_VERSION,
    RUNTIME_INTELLIGENCE_DEBT_SCHEMA_VERSION,
    BehaviorFamilyId,
    CompatibilityDebtDisposition,
    CompatibilityDebtItem,
    CompatibilityDebtKind,
    CompatibilityDebtReport,
    CompatibilityDebtSignal,
    CorpusKind,
)

DEBT_BACKLOG_LIMITATION = "measured backlog only; not an implementation commitment"


def _dedupe_sorted(values: List[str]) -> List[str]:
    return sorted(set(values))


def _parse_iso8601(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def compute_age_days(*, first_observed: str, last_observed: str) -> int:
    """Snapshot-bound age; never uses wall-clock time."""
    first = _parse_iso8601(first_observed)
    last = _parse_iso8601(last_observed)
    delta = last - first
    return max(0, delta.days)


def _effective_binary_count(signal: CompatibilityDebtSignal) -> int:
    if signal.affected_binary_digests:
        return len(set(signal.affected_binary_digests))
    return signal.distinct_binary_count


def _effective_application_count(signal: CompatibilityDebtSignal) -> int:
    if signal.affected_application_fingerprints:
        return len(set(signal.affected_application_fingerprints))
    return signal.distinct_application_count


def validate_debt_signal(signal: CompatibilityDebtSignal) -> None:
    """Reject signals that do not meet evidence qualification rules."""
    if signal.stderr_only:
        raise ValueError("generic stderr-only evidence is insufficient for debt classification")
    if not (signal.evidence_snapshot_digest or "").strip():
        raise ValueError("evidence_snapshot_digest is required")
    if not signal.evidence_references:
        raise ValueError("at least one evidence reference is required")
    if not (signal.capability_id or "").strip():
        raise ValueError("capability_id is required")


def classify_disposition(signal: CompatibilityDebtSignal) -> CompatibilityDebtDisposition:
    if signal.explicitly_out_of_scope:
        return CompatibilityDebtDisposition.ACKNOWLEDGED_OUT_OF_SCOPE
    if signal.evidence_stale:
        return CompatibilityDebtDisposition.STALE_EVIDENCE
    if signal.prerequisite_capability_ids and signal.prerequisites_unmet:
        return CompatibilityDebtDisposition.BLOCKED_BY_PREREQUISITE
    if signal.kind in (CompatibilityDebtKind.UNKNOWN_API, CompatibilityDebtKind.UNKNOWN_BEHAVIOR):
        return CompatibilityDebtDisposition.UNKNOWN
    return CompatibilityDebtDisposition.ADDRESSABLE


def classify_severity(signal: CompatibilityDebtSignal) -> tuple[RiskSeverity, List[str]]:
    factors: List[str] = []

    if signal.kind == CompatibilityDebtKind.CALIBRATION_FALSE_POSITIVE:
        factors.append(f"calibration_false_positive:gap={signal.calibration_gap_count}")
        if signal.authoritative_failure_count >= 1:
            factors.append(f"authoritative_failures={signal.authoritative_failure_count}")
        if signal.security_risk_score is not None and signal.security_risk_score >= 0.7:
            factors.append(f"security_risk_score={signal.security_risk_score}")
            if signal.authoritative_failure_count >= 1:
                return RiskSeverity.CRITICAL, factors

    if signal.kind in (CompatibilityDebtKind.STALE_EVIDENCE, CompatibilityDebtKind.STALE_CERTIFICATION):
        factors.append(f"stale_kind={signal.kind.value}")
        if (signal.current_certification or "").lower() == "production_ready":
            factors.append("previously_production_ready")
            return RiskSeverity.CRITICAL, factors

    if signal.kind == CompatibilityDebtKind.UNSUPPORTED_CAPABILITY:
        factors.append(f"unsupported_capability:apps={signal.distinct_application_count}")
        if signal.distinct_application_count >= 3:
            return RiskSeverity.HIGH, factors

    if signal.kind == CompatibilityDebtKind.STALE_CERTIFICATION:
        factors.append(f"stale_certification:apps={signal.distinct_application_count}")
        maturity = (signal.current_maturity or "").lower()
        if maturity in ("verified_bounded", "stable"):
            factors.append(f"current_maturity={maturity}")
            return RiskSeverity.HIGH, factors

    if signal.kind == CompatibilityDebtKind.MATURITY_REGRESSION:
        factors.append(f"maturity_regression:apps={signal.distinct_application_count}")
        if signal.distinct_application_count >= 1:
            return RiskSeverity.HIGH, factors

    if signal.kind == CompatibilityDebtKind.UNSUPPORTED_BEHAVIOR:
        factors.append(f"unsupported_behavior:apps={signal.distinct_application_count}")
        if signal.distinct_application_count >= 1:
            return RiskSeverity.MEDIUM, factors

    if signal.kind == CompatibilityDebtKind.UNKNOWN_API:
        factors.append(f"unknown_api:apps={signal.distinct_application_count}")
        if signal.distinct_application_count >= 1:
            return RiskSeverity.MEDIUM, factors

    if signal.prerequisites_unmet and signal.prerequisite_capability_ids:
        factors.append(f"blocked_prerequisite:apps={signal.distinct_application_count}")
        if signal.distinct_application_count >= 1:
            return RiskSeverity.MEDIUM, factors

    if signal.kind == CompatibilityDebtKind.CALIBRATION_FALSE_NEGATIVE:
        factors.append(f"calibration_false_negative:gap={signal.calibration_gap_count}")
        return RiskSeverity.MEDIUM, factors

    if signal.kind == CompatibilityDebtKind.MISSING_FIXTURE:
        factors.append("missing_fixture")
        return RiskSeverity.LOW, factors

    if signal.kind == CompatibilityDebtKind.UNKNOWN_BEHAVIOR:
        factors.append(f"unknown_behavior:apps={signal.distinct_application_count}")
        if signal.distinct_application_count < 2:
            return RiskSeverity.LOW, factors
        return RiskSeverity.MEDIUM, factors

    if signal.explicitly_out_of_scope or signal.kind == CompatibilityDebtKind.ACKNOWLEDGED_OUT_OF_SCOPE:
        factors.append("acknowledged_out_of_scope")
        return RiskSeverity.LOW, factors

    factors.append(f"default:kind={signal.kind.value}")
    return RiskSeverity.MEDIUM, factors


def compute_debt_id(
    *,
    corpus: CorpusKind,
    family_id: BehaviorFamilyId,
    provider_id: Optional[str],
    capability_id: str,
    behavior_id: Optional[str],
    kind: CompatibilityDebtKind,
    evidence_snapshot_digest: str,
) -> str:
    return sha256_v1(
        {
            "corpus": corpus.value,
            "family_id": family_id.value,
            "provider_id": provider_id or "",
            "capability_id": capability_id,
            "behavior_id": behavior_id or "",
            "kind": kind.value,
            "evidence_snapshot_digest": evidence_snapshot_digest,
        }
    )


def compute_debt_item_digest(item: CompatibilityDebtItem) -> str:
    payload: Mapping[str, Any] = {
        "debt_id": item.debt_id,
        "kind": item.kind.value,
        "disposition": item.disposition.value,
        "severity": item.severity,
        "corpus": item.corpus.value,
        "family_id": item.family_id.value,
        "provider_id": item.provider_id or "",
        "capability_id": item.capability_id,
        "behavior_id": item.behavior_id or "",
        "distinct_binary_count": item.distinct_binary_count,
        "distinct_application_count": item.distinct_application_count,
        "blocked_session_count": item.blocked_session_count,
        "calibration_gap_count": item.calibration_gap_count,
        "first_observed": item.first_observed or "",
        "last_observed": item.last_observed or "",
        "age_days": item.age_days,
        "prerequisite_capability_ids": _dedupe_sorted(item.prerequisite_capability_ids),
        "fixture_available": item.fixture_available,
        "current_maturity": item.current_maturity or "",
        "current_certification": item.current_certification or "",
        "severity_factors": _dedupe_sorted(item.severity_factors),
        "limitations": _dedupe_sorted(item.limitations),
        "evidence_references": _dedupe_sorted(item.evidence_references),
        "evidence_snapshot_digest": item.evidence_snapshot_digest,
        "formula_version": item.formula_version,
        "schema_version": item.schema_version,
    }
    return sha256_v1(payload)


def compute_debt_report_digest(
    *,
    corpus: CorpusKind,
    family_id: BehaviorFamilyId,
    provider_id: Optional[str],
    items: List[CompatibilityDebtItem],
    counts_by_kind: Dict[str, int],
    counts_by_disposition: Dict[str, int],
    counts_by_severity: Dict[str, int],
    total_distinct_binaries: int,
    total_distinct_applications: int,
    summed_item_application_mentions: int,
    limitations: List[str],
    evidence_references: List[str],
    evidence_snapshot_digest: str,
) -> str:
    payload: Mapping[str, Any] = {
        "corpus": corpus.value,
        "family_id": family_id.value,
        "provider_id": provider_id or "",
        "items": sorted([item.digest for item in items]),
        "counts_by_kind": dict(sorted(counts_by_kind.items())),
        "counts_by_disposition": dict(sorted(counts_by_disposition.items())),
        "counts_by_severity": dict(sorted(counts_by_severity.items())),
        "total_distinct_binaries": total_distinct_binaries,
        "total_distinct_applications": total_distinct_applications,
        "summed_item_application_mentions": summed_item_application_mentions,
        "limitations": _dedupe_sorted(limitations),
        "evidence_references": _dedupe_sorted(evidence_references),
        "evidence_snapshot_digest": evidence_snapshot_digest,
        "formula_version": DEBT_CLASSIFICATION_FORMULA_VERSION,
        "schema_version": RUNTIME_INTELLIGENCE_DEBT_SCHEMA_VERSION,
    }
    return sha256_v1(payload)


def classify_debt_signal(signal: CompatibilityDebtSignal) -> CompatibilityDebtItem:
    validate_debt_signal(signal)

    effective_signal = signal.model_copy(
        update={
            "distinct_binary_count": _effective_binary_count(signal),
            "distinct_application_count": _effective_application_count(signal),
        }
    )

    disposition = classify_disposition(effective_signal)
    severity, severity_factors = classify_severity(effective_signal)

    age_days: Optional[int] = None
    if signal.first_observed and signal.last_observed:
        age_days = compute_age_days(
            first_observed=signal.first_observed,
            last_observed=signal.last_observed,
        )

    limitations = _dedupe_sorted([DEBT_BACKLOG_LIMITATION, *signal.limitations])
    evidence_references = _dedupe_sorted(signal.evidence_references)
    prerequisite_capability_ids = _dedupe_sorted(signal.prerequisite_capability_ids)

    debt_id = compute_debt_id(
        corpus=signal.corpus,
        family_id=signal.family_id,
        provider_id=signal.provider_id,
        capability_id=signal.capability_id,
        behavior_id=signal.behavior_id,
        kind=signal.kind,
        evidence_snapshot_digest=signal.evidence_snapshot_digest,
    )

    item = CompatibilityDebtItem(
        debt_id=debt_id,
        kind=signal.kind,
        disposition=disposition,
        severity=severity.value,
        corpus=signal.corpus,
        family_id=signal.family_id,
        provider_id=signal.provider_id,
        capability_id=signal.capability_id,
        behavior_id=signal.behavior_id,
        distinct_binary_count=_effective_binary_count(signal),
        distinct_application_count=_effective_application_count(signal),
        blocked_session_count=signal.blocked_session_count,
        calibration_gap_count=signal.calibration_gap_count,
        first_observed=signal.first_observed,
        last_observed=signal.last_observed,
        age_days=age_days,
        prerequisite_capability_ids=prerequisite_capability_ids,
        fixture_available=signal.fixture_available,
        current_maturity=signal.current_maturity,
        current_certification=signal.current_certification,
        severity_factors=severity_factors,
        limitations=limitations,
        evidence_references=evidence_references,
        evidence_snapshot_digest=signal.evidence_snapshot_digest,
        expansion_candidate_id=signal.expansion_candidate_id,
        work_item_id=signal.work_item_id,
        schema_version=RUNTIME_INTELLIGENCE_DEBT_SCHEMA_VERSION,
        formula_version=DEBT_CLASSIFICATION_FORMULA_VERSION,
        digest="",
    )
    digest = compute_debt_item_digest(item)
    return item.model_copy(update={"digest": digest})


def build_debt_report(
    *,
    corpus: CorpusKind,
    family_id: BehaviorFamilyId,
    signals: Sequence[CompatibilityDebtSignal],
    provider_id: Optional[str] = None,
    evidence_snapshot_digest: str,
    limitations: Optional[List[str]] = None,
) -> CompatibilityDebtReport:
    if not (evidence_snapshot_digest or "").strip():
        raise ValueError("evidence_snapshot_digest is required")

    items: List[CompatibilityDebtItem] = []
    all_binaries: set[str] = set()
    all_fingerprints: set[str] = set()
    all_refs: List[str] = []
    summed_mentions = 0

    for signal in signals:
        if signal.corpus != corpus:
            raise ValueError("all debt signals must bind to the same explicit corpus")
        if signal.family_id != family_id:
            raise ValueError("all debt signals must bind to the same behavior family")
        if provider_id is not None and signal.provider_id not in (None, provider_id):
            raise ValueError("provider_id mismatch across debt signals")
        if signal.evidence_snapshot_digest != evidence_snapshot_digest:
            raise ValueError("all debt signals must share the same evidence snapshot digest")

        item = classify_debt_signal(signal)
        items.append(item)
        all_binaries.update(signal.affected_binary_digests)
        all_fingerprints.update(signal.affected_application_fingerprints)
        all_refs.extend(item.evidence_references)
        summed_mentions += signal.distinct_application_count

    items.sort(key=lambda i: i.debt_id)

    counts_by_kind: Dict[str, int] = {}
    counts_by_disposition: Dict[str, int] = {}
    counts_by_severity: Dict[str, int] = {}
    for item in items:
        counts_by_kind[item.kind.value] = counts_by_kind.get(item.kind.value, 0) + 1
        counts_by_disposition[item.disposition.value] = counts_by_disposition.get(item.disposition.value, 0) + 1
        counts_by_severity[item.severity] = counts_by_severity.get(item.severity, 0) + 1

    report_limitations = _dedupe_sorted([DEBT_BACKLOG_LIMITATION, *(limitations or [])])
    evidence_references = _dedupe_sorted(all_refs)

    report_digest = compute_debt_report_digest(
        corpus=corpus,
        family_id=family_id,
        provider_id=provider_id,
        items=items,
        counts_by_kind=counts_by_kind,
        counts_by_disposition=counts_by_disposition,
        counts_by_severity=counts_by_severity,
        total_distinct_binaries=len(all_binaries) if all_binaries else sum(i.distinct_binary_count for i in items),
        total_distinct_applications=len(all_fingerprints)
        if all_fingerprints
        else max((i.distinct_application_count for i in items), default=0),
        summed_item_application_mentions=summed_mentions,
        limitations=report_limitations,
        evidence_references=evidence_references,
        evidence_snapshot_digest=evidence_snapshot_digest,
    )

    return CompatibilityDebtReport(
        corpus=corpus,
        family_id=family_id,
        provider_id=provider_id,
        items=items,
        counts_by_kind=counts_by_kind,
        counts_by_disposition=counts_by_disposition,
        counts_by_severity=counts_by_severity,
        total_distinct_binaries=len(all_binaries) if all_binaries else sum(i.distinct_binary_count for i in items),
        total_distinct_applications=len(all_fingerprints)
        if all_fingerprints
        else max((i.distinct_application_count for i in items), default=0),
        summed_item_application_mentions=summed_mentions,
        limitations=report_limitations,
        evidence_references=evidence_references,
        evidence_snapshot_digest=evidence_snapshot_digest,
        report_digest=report_digest,
        schema_version=RUNTIME_INTELLIGENCE_DEBT_SCHEMA_VERSION,
        formula_version=DEBT_CLASSIFICATION_FORMULA_VERSION,
    )
