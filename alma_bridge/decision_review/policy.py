"""Approval policy validation for decision plan reviews."""

from __future__ import annotations

import re
from typing import Iterable, List, Set

from alma_bridge.advisor.queries import union_evidence_references
from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.decision.models import DecisionPlan, RecommendationKind
from alma_bridge.decision_review.digest import compute_plan_digest
from alma_bridge.decision_review.models import (
    DecisionPlanReviewRequest,
    DecisionPlanSummary,
    PolicyValidationResult,
    PolicyViolation,
    PlanRisk,
)
from alma_bridge.knowledge.models import KnowledgeEvidenceReference


_AUTO_REMEDIATION_PATTERNS = (
    re.compile(r"\bauto[- ]?remediat", re.I),
    re.compile(r"\brun winetricks\b", re.I),
    re.compile(r"\bapply remediation\b", re.I),
)

_MUTATION_PATTERNS = (
    re.compile(r"\bmutate prefix\b", re.I),
    re.compile(r"\bchange prefix\b", re.I),
    re.compile(r"\binstall\b", re.I),
    re.compile(r"\bapply\b", re.I),
    re.compile(r"\bexecute\b", re.I),
    re.compile(r"\brun strategy\b", re.I),
)

_UNSUPPORTED_RUNTIME_PATTERNS = (
    re.compile(r"\brequires runtime\b", re.I),
    re.compile(r"\bunsupported runtime requirement\b", re.I),
)


def _collect_evidence_references(plan: DecisionPlan) -> List[KnowledgeEvidenceReference]:
    refs: List[KnowledgeEvidenceReference] = []
    for recommendation in plan.recommendations:
        for prov in recommendation.provenance:
            refs.append(
                KnowledgeEvidenceReference(
                    source_type=prov.source,
                    source_id=prov.artifact_id,
                    artifact_key=prov.digest,
                    session_id=prov.session_id,
                    attempt_id=prov.attempt_id,
                    captured_at=prov.captured_at,
                )
            )
    return union_evidence_references(refs)


def extract_risks(plan: DecisionPlan) -> List[PlanRisk]:
    risks: List[PlanRisk] = []
    seen: Set[str] = set()

    def add_risk(*, summary: str, source: str, severity: str = "warning") -> None:
        text = summary.strip()
        if not text:
            return
        risk_id = sha256_v1({"summary": text, "source": source})
        if risk_id in seen:
            return
        seen.add(risk_id)
        risks.append(
            PlanRisk(
                risk_id=risk_id,
                summary=text,
                source=source,
                severity=severity,
            )
        )

    for recommendation in plan.recommendations:
        if recommendation.kind == RecommendationKind.HOLD:
            add_risk(summary=recommendation.action, source="hold", severity="critical")
        for reason in recommendation.approval_reasons:
            if reason in {"regression_detected", "verification_required", "insufficient_evidence"}:
                add_risk(
                    summary=f"{reason.replace('_', ' ')}: {recommendation.action}",
                    source=recommendation.kind.value,
                    severity="warning",
                )
        if recommendation.kind == RecommendationKind.REMEDIATION_REVIEW:
            add_risk(
                summary=recommendation.action,
                source="regression",
                severity="critical",
            )

    for notice in plan.notices:
        if "does not authorize" not in notice.lower():
            add_risk(summary=notice, source="notice", severity="info")

    return sorted(risks, key=lambda item: (item.severity, item.risk_id))


def validate_approval_policy(
    *,
    plan: DecisionPlan,
    summary: DecisionPlanSummary,
    request: DecisionPlanReviewRequest,
) -> PolicyValidationResult:
    violations: List[PolicyViolation] = []
    current_digest = compute_plan_digest(plan)
    evidence_refs = _collect_evidence_references(plan)

    if not evidence_refs:
        violations.append(
            PolicyViolation(
                code="evidence_references_required",
                message="Approval requires non-empty evidence references.",
            )
        )

    verification_required = any(
        "verification" in reason or reason == "verification_required"
        for rec in plan.recommendations
        for reason in rec.approval_reasons
    ) or any(
        constraint.code == "verification_authority_required"
        for rec in plan.recommendations
        for constraint in rec.constraints
    )
    if not verification_required:
        violations.append(
            PolicyViolation(
                code="verification_required_after_execution",
                message="Plan must acknowledge verification authority after future execution.",
            )
        )

    serialized = plan.model_dump_json().lower()
    for pattern in _UNSUPPORTED_RUNTIME_PATTERNS:
        if pattern.search(serialized):
            violations.append(
                PolicyViolation(
                    code="unsupported_runtime_requirement",
                    message="Plan must not assert unsupported runtime requirements.",
                )
            )
            break

    for recommendation in plan.recommendations:
        action = recommendation.action or ""
        for pattern in _AUTO_REMEDIATION_PATTERNS:
            if pattern.search(action):
                violations.append(
                    PolicyViolation(
                        code="no_automatic_remediation",
                        message="Plan must not include automatic remediation commands.",
                    )
                )
                break
        for pattern in _MUTATION_PATTERNS:
            if pattern.search(action) and recommendation.kind not in {
                RecommendationKind.HOLD,
                RecommendationKind.EVIDENCE_REVIEW,
                RecommendationKind.REMEDIATION_REVIEW,
                RecommendationKind.VERIFICATION_REVIEW,
            }:
                violations.append(
                    PolicyViolation(
                        code="no_direct_mutation_instruction",
                        message="Plan must not include direct mutation or execution instructions.",
                    )
                )
                break

    if not plan.recommendations or not all(rec.confidence for rec in plan.recommendations):
        violations.append(
            PolicyViolation(
                code="confidence_required",
                message="Every recommendation must include confidence metadata.",
            )
        )
    if not evidence_refs and any(rec.confidence.score >= 0.75 for rec in plan.recommendations):
        violations.append(
            PolicyViolation(
                code="confidence_not_substitute_for_evidence",
                message="High confidence cannot substitute for missing evidence references.",
            )
        )

    required_risks = {risk.risk_id for risk in summary.risks if risk.severity in {"warning", "critical"}}
    acknowledged = set(request.risk_acknowledgements)
    missing = sorted(required_risks - acknowledged)
    if missing:
        violations.append(
            PolicyViolation(
                code="risk_acknowledgements_incomplete",
                message=f"Reviewer must acknowledge listed risks: {', '.join(missing)}",
            )
        )

    if request.plan_digest != current_digest:
        violations.append(
            PolicyViolation(
                code="plan_digest_mismatch",
                message="plan_digest does not match the current canonical plan.",
            )
        )

    return PolicyValidationResult(allowed=not violations, violations=violations)
