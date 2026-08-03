"""Status reducer matrix tests for decision validation dry-run."""

from __future__ import annotations

import pytest

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.decision_review.models import Decision, DecisionPlanReview
from alma_bridge.decision_validation.models import (
    PlanValidationStatus,
    ValidationCheck,
    ValidationCheckCategory,
    ValidationCheckSeverity,
)
from alma_bridge.decision_validation.status import aggregate_status, compute_has_warnings


def _review(decision: Decision = Decision.APPROVED) -> DecisionPlanReview:
    return DecisionPlanReview(
        review_id="review-1",
        plan_id="plan-1",
        application_fingerprint="fp",
        session_id="session-1",
        plan_version="compatibility_decision_v1",
        plan_digest="sha256:abc",
        decision=decision,
        reviewer="operator",
        reviewed_at="2026-08-02T00:00:00+00:00",
        comment="",
        risk_acknowledgements=[],
        evidence_references=[],
    )


def _check(
    *,
    code: str,
    category: ValidationCheckCategory,
    passed: bool,
    severity: ValidationCheckSeverity = ValidationCheckSeverity.BLOCKING,
) -> ValidationCheck:
    return ValidationCheck(
        check_id=sha256_v1({"code": code}),
        category=category,
        code=code,
        message=code,
        severity=severity,
        passed=passed,
    )


class TestValidationStatusReducer:
    def test_all_blocking_pass_returns_valid(self):
        checks = [
            _check(
                code="submitted_digest_matches",
                category=ValidationCheckCategory.PLAN_INTEGRITY,
                passed=True,
            )
        ]
        status, has_warnings = aggregate_status(
            review=_review(), checks=checks, approval_stale_flag=False
        )
        assert status == PlanValidationStatus.VALID
        assert has_warnings is False

    def test_info_check_failure_still_valid(self):
        checks = [
            _check(
                code="prefix_mutation_policy_simulation",
                category=ValidationCheckCategory.POLICY_FEASIBILITY,
                passed=True,
                severity=ValidationCheckSeverity.INFO,
            )
        ]
        status, has_warnings = aggregate_status(
            review=_review(), checks=checks, approval_stale_flag=False
        )
        assert status == PlanValidationStatus.VALID
        assert has_warnings is False

    def test_warning_produces_valid_with_has_warnings(self):
        checks = [
            _check(
                code="optional_unknown_environment",
                category=ValidationCheckCategory.ENVIRONMENT_FEASIBILITY,
                passed=True,
                severity=ValidationCheckSeverity.WARNING,
            )
        ]
        status, has_warnings = aggregate_status(
            review=_review(), checks=checks, approval_stale_flag=False
        )
        assert status == PlanValidationStatus.VALID
        assert has_warnings is True

    def test_blocking_feasibility_failure_returns_blocked(self):
        checks = [
            _check(
                code="runtime_provider_available",
                category=ValidationCheckCategory.RUNTIME_FEASIBILITY,
                passed=False,
            )
        ]
        status, _ = aggregate_status(review=_review(), checks=checks, approval_stale_flag=False)
        assert status == PlanValidationStatus.BLOCKED

    def test_structural_integrity_failure_returns_invalid(self):
        checks = [
            _check(
                code="evidence_resolves",
                category=ValidationCheckCategory.PLAN_INTEGRITY,
                passed=False,
            )
        ]
        status, _ = aggregate_status(review=_review(), checks=checks, approval_stale_flag=False)
        assert status == PlanValidationStatus.INVALID

    def test_stale_digest_returns_stale(self):
        status, _ = aggregate_status(review=_review(), checks=[], approval_stale_flag=True)
        assert status == PlanValidationStatus.STALE

    def test_required_unknown_returns_indeterminate(self):
        checks = [
            _check(
                code="required_unknown_environment",
                category=ValidationCheckCategory.ENVIRONMENT_FEASIBILITY,
                passed=False,
                severity=ValidationCheckSeverity.WARNING,
            )
        ]
        status, _ = aggregate_status(review=_review(), checks=checks, approval_stale_flag=False)
        assert status == PlanValidationStatus.INDETERMINATE

    def test_optional_unknown_does_not_force_indeterminate(self):
        checks = [
            _check(
                code="optional_unknown_environment",
                category=ValidationCheckCategory.ENVIRONMENT_FEASIBILITY,
                passed=True,
                severity=ValidationCheckSeverity.WARNING,
            )
        ]
        status, has_warnings = aggregate_status(
            review=_review(), checks=checks, approval_stale_flag=False
        )
        assert status == PlanValidationStatus.VALID
        assert has_warnings is True

    def test_stale_precedence_over_blocked(self):
        checks = [
            _check(
                code="runtime_provider_available",
                category=ValidationCheckCategory.RUNTIME_FEASIBILITY,
                passed=False,
            )
        ]
        status, _ = aggregate_status(review=_review(), checks=checks, approval_stale_flag=True)
        assert status == PlanValidationStatus.STALE

    def test_unapproved_review_returns_invalid(self):
        status, _ = aggregate_status(
            review=_review(decision=Decision.REJECTED),
            checks=[],
            approval_stale_flag=False,
        )
        assert status == PlanValidationStatus.INVALID
