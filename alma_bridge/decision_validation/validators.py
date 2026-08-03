"""Orchestrate validation dimensions for approved plan dry-run."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.decision.models import DECISION_SCHEMA_VERSION, DecisionPlan
from alma_bridge.decision_review.digest import compute_plan_digest
from alma_bridge.decision_review.models import Decision, DecisionPlanReview
from alma_bridge.decision_review.policy import _collect_evidence_references
from alma_bridge.decision_validation.capability_check import check_runtime_feasibility
from alma_bridge.decision_validation.environment_fields import (
    classify_environment_fields,
    format_field_list,
)
from alma_bridge.decision_validation.models import (
    ValidationCheck,
    ValidationCheckCategory,
    ValidationCheckSeverity,
)
from alma_bridge.decision_validation.policy_check import simulate_policy_feasibility
from alma_bridge.decision_validation.staleness import (
    approval_stale,
    check_approval_staleness,
    check_evidence_freshness,
)
from alma_bridge.storage import outcomes


def _check(
    *,
    category: ValidationCheckCategory,
    code: str,
    message: str,
    passed: bool,
    severity: ValidationCheckSeverity = ValidationCheckSeverity.BLOCKING,
) -> ValidationCheck:
    return ValidationCheck(
        check_id=sha256_v1({"category": category.value, "code": code, "message": message}),
        category=category,
        code=code,
        message=message,
        severity=severity,
        passed=passed,
    )


def check_plan_integrity(
    plan: DecisionPlan,
    review: DecisionPlanReview,
    *,
    submitted_digest: str,
) -> List[ValidationCheck]:
    checks: List[ValidationCheck] = []
    current_digest = compute_plan_digest(plan)

    checks.append(
        _check(
            category=ValidationCheckCategory.PLAN_INTEGRITY,
            code="submitted_digest_matches",
            message=(
                "Submitted plan_digest matches the canonical plan."
                if submitted_digest == current_digest
                else "Submitted plan_digest does not match the canonical plan."
            ),
            passed=submitted_digest == current_digest,
        )
    )

    checks.append(
        _check(
            category=ValidationCheckCategory.PLAN_INTEGRITY,
            code="review_digest_binding",
            message=(
                "Review record binds to the canonical plan digest."
                if review.plan_digest == current_digest
                else "Review record binds to a stale plan digest."
            ),
            passed=review.plan_digest == current_digest,
        )
    )

    checks.append(
        _check(
            category=ValidationCheckCategory.PLAN_INTEGRITY,
            code="schema_supported",
            message=(
                f"Plan schema {plan.schema_version} is supported."
                if plan.schema_version == DECISION_SCHEMA_VERSION
                else f"Plan schema {plan.schema_version} is not supported."
            ),
            passed=plan.schema_version == DECISION_SCHEMA_VERSION,
        )
    )

    evidence_refs = _collect_evidence_references(plan)
    checks.append(
        _check(
            category=ValidationCheckCategory.PLAN_INTEGRITY,
            code="evidence_resolves",
            message=(
                "Plan evidence references resolve."
                if evidence_refs
                else "Plan evidence references are missing."
            ),
            passed=bool(evidence_refs),
        )
    )

    checks.append(check_approval_staleness(review, current_digest=current_digest))
    return checks


def check_application_identity(plan: DecisionPlan) -> List[ValidationCheck]:
    checks: List[ValidationCheck] = []
    session_id = plan.session_id
    if not session_id:
        checks.append(
            _check(
                category=ValidationCheckCategory.APPLICATION_IDENTITY,
                code="session_bound",
                message="Plan is not bound to a session for identity verification.",
                passed=False,
                severity=ValidationCheckSeverity.WARNING,
            )
        )
        return checks

    session = outcomes.get_session(session_id)
    if not session:
        checks.append(
            _check(
                category=ValidationCheckCategory.APPLICATION_IDENTITY,
                code="session_exists",
                message=f"Session {session_id} was not found in outcome store.",
                passed=False,
            )
        )
        return checks

    session_fingerprint = str(session.get("file_hash") or "")
    fingerprint_match = session_fingerprint == plan.application_fingerprint
    checks.append(
        _check(
            category=ValidationCheckCategory.APPLICATION_IDENTITY,
            code="fingerprint_match",
            message=(
                "Session fingerprint matches plan application_fingerprint."
                if fingerprint_match
                else "Session fingerprint does not match plan application_fingerprint."
            ),
            passed=fingerprint_match,
        )
    )

    file_path = session.get("file_path")
    if file_path:
        exists = Path(file_path).exists()
        checks.append(
            _check(
                category=ValidationCheckCategory.APPLICATION_IDENTITY,
                code="executable_path_exists",
                message=(
                    f"Executable path exists (stat only): {file_path}"
                    if exists
                    else f"Executable path is missing (stat only): {file_path}"
                ),
                passed=exists,
                severity=ValidationCheckSeverity.WARNING if not exists else ValidationCheckSeverity.INFO,
            )
        )
    else:
        checks.append(
            _check(
                category=ValidationCheckCategory.APPLICATION_IDENTITY,
                code="executable_path_exists",
                message="Session has no executable path for identity verification.",
                passed=False,
                severity=ValidationCheckSeverity.WARNING,
            )
        )

    checks.append(
        _check(
            category=ValidationCheckCategory.APPLICATION_IDENTITY,
            code="no_substitution",
            message="Application identity is bound to the reviewed session without substitution.",
            passed=fingerprint_match,
            severity=ValidationCheckSeverity.INFO,
        )
    )
    return checks


def check_environment_feasibility(plan: DecisionPlan) -> List[ValidationCheck]:
    checks: List[ValidationCheck] = []
    session_id = plan.session_id
    prefix: Optional[str] = None
    env_fields: dict = {}

    if session_id:
        session = outcomes.get_session(session_id)
        attempts = (session or {}).get("attempts") or []
        if attempts:
            env_fields = attempts[-1].get("env") or {}
            prefix = env_fields.get("WINEPREFIX")

    if prefix:
        prefix_path = Path(str(prefix)).expanduser()
        exists = prefix_path.exists()
        checks.append(
            _check(
                category=ValidationCheckCategory.ENVIRONMENT_FEASIBILITY,
                code="prefix_exists",
                message=(
                    f"Referenced prefix exists (stat only): {prefix}"
                    if exists
                    else f"Referenced prefix is missing (stat only): {prefix}"
                ),
                passed=exists,
            )
        )
    else:
        checks.append(
            _check(
                category=ValidationCheckCategory.ENVIRONMENT_FEASIBILITY,
                code="prefix_exists",
                message="No Wine prefix referenced by plan session evidence.",
                passed=True,
                severity=ValidationCheckSeverity.INFO,
            )
        )

    optional_unknown, required_unknown = classify_environment_fields(env_fields)
    if required_unknown:
        checks.append(
            _check(
                category=ValidationCheckCategory.ENVIRONMENT_FEASIBILITY,
                code="required_unknown_environment",
                message=(
                    "Required environment information remains unknown: "
                    f"{format_field_list(required_unknown)}"
                ),
                passed=False,
                severity=ValidationCheckSeverity.WARNING,
            )
        )
    if optional_unknown:
        checks.append(
            _check(
                category=ValidationCheckCategory.ENVIRONMENT_FEASIBILITY,
                code="optional_unknown_environment",
                message=(
                    "Optional legacy environment fields were observed but are not required "
                    f"for feasibility: {format_field_list(optional_unknown)}"
                ),
                passed=True,
                severity=ValidationCheckSeverity.WARNING,
            )
        )
    if not required_unknown and not optional_unknown:
        checks.append(
            _check(
                category=ValidationCheckCategory.ENVIRONMENT_FEASIBILITY,
                code="environment_fields_known",
                message="Referenced environment fields are recognized or absent.",
                passed=True,
                severity=ValidationCheckSeverity.INFO,
            )
        )

    return checks


def check_verification_readiness(plan: DecisionPlan) -> List[ValidationCheck]:
    checks: List[ValidationCheck] = []
    verification_required = any(
        constraint.code == "verification_authority_required"
        for recommendation in plan.recommendations
        for constraint in recommendation.constraints
    ) or any(
        reason == "verification_required" for recommendation in plan.recommendations for reason in recommendation.approval_reasons
    )

    checks.append(
        _check(
            category=ValidationCheckCategory.VERIFICATION_READINESS,
            code="verification_requirement_explicit",
            message=(
                "Plan explicitly requires verification authority after execution."
                if verification_required
                else "Plan does not explicitly require verification authority."
            ),
            passed=verification_required,
        )
    )

    contract_supported = _verification_contract_supported(plan)
    checks.append(
        _check(
            category=ValidationCheckCategory.VERIFICATION_READINESS,
            code="verification_contract_supported",
            message=(
                "Session verification contract is supported."
                if contract_supported
                else "Session verification contract is missing or unsupported."
            ),
            passed=contract_supported,
        )
    )

    feasible_without = verification_required and contract_supported
    checks.append(
        _check(
            category=ValidationCheckCategory.VERIFICATION_READINESS,
            code="verification_path_available",
            message=(
                "Verification path is available for a feasible dry-run assessment."
                if feasible_without
                else "No feasible verification path without an explicit supported contract."
            ),
            passed=feasible_without,
        )
    )
    return checks


def _verification_contract_supported(plan: DecisionPlan) -> bool:
    session_id = plan.session_id
    if not session_id:
        return False
    session = outcomes.get_session(session_id)
    if not session:
        return False
    attempts = session.get("attempts") or []
    for attempt in reversed(attempts):
        verification = attempt.get("verification") or {}
        policy = verification.get("success_policy") or {}
        if policy.get("policy_id"):
            return True
    return False


def run_all_validations(
    plan: DecisionPlan,
    review: DecisionPlanReview,
    *,
    submitted_digest: str,
) -> tuple[List[ValidationCheck], bool]:
    """Run all validation dimensions and return checks plus approval_stale flag."""
    import shutil

    checks: List[ValidationCheck] = []
    checks.extend(check_plan_integrity(plan, review, submitted_digest=submitted_digest))
    checks.extend(check_application_identity(plan))
    checks.extend(check_runtime_feasibility(plan, which=shutil.which))
    checks.extend(check_environment_feasibility(plan))
    checks.extend(simulate_policy_feasibility(plan, review))
    checks.extend(check_verification_readiness(plan))
    checks.extend(check_evidence_freshness(plan, review))

    stale = approval_stale(review, current_digest=compute_plan_digest(plan))
    return checks, stale
