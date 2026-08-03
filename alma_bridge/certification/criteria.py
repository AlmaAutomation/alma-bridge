"""Deterministic certification criteria per level."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from alma_bridge.certification.models import (
    CertificationLevel,
    ComplianceStatus,
    StaleReason,
)
from alma_bridge.native_engineering.models import TestScenarioStatus


@dataclass
class CertificationInputs:
    """Evidence inputs for deterministic level computation."""

    capability_id: str
    behavior_id: str
    supported: bool = True
    has_specification: bool = False
    spec_digest: str = ""
    has_behavior_suite: bool = False
    suite_pass_count: int = 0
    suite_total_count: int = 0
    has_negative_fixture_pass: bool = False
    validation_pass_count: int = 0
    validation_total_count: int = 0
    fixture_coverage_pct: float = 0.0
    calibration_link_count: int = 0
    governance_maturity: str = ""
    evidence_bundle_count: int = 0
    benchmark_history_count: int = 0
    verified_scenario_present: bool = False
    verification_pct: float = 0.0
    stale_reasons: List[StaleReason] = field(default_factory=list)
    implementation_version: str = ""
    last_recorded_spec_digest: str = ""
    last_recorded_implementation_version: str = ""
    last_recorded_registry_version: str = ""
    current_registry_version: str = ""
    has_regression: bool = False


LEVEL_ORDER = [
    CertificationLevel.UNVERIFIED,
    CertificationLevel.SPECIFIED,
    CertificationLevel.BEHAVIOR_TESTED,
    CertificationLevel.VERIFIED,
    CertificationLevel.CALIBRATED,
    CertificationLevel.GOVERNED,
    CertificationLevel.CERTIFIED,
    CertificationLevel.PRODUCTION_READY,
]


def _level_index(level: CertificationLevel) -> int:
    if level == CertificationLevel.REQUIRES_REVALIDATION:
        return -1
    try:
        return LEVEL_ORDER.index(level)
    except ValueError:
        return 0


def detect_stale_reasons(inputs: CertificationInputs) -> List[StaleReason]:
    """Deterministic stale detection from evidence deltas vs last record."""
    reasons: List[StaleReason] = []
    has_prior = bool(inputs.last_recorded_spec_digest or inputs.last_recorded_implementation_version)

    if has_prior and inputs.has_regression:
        reasons.append(StaleReason.BEHAVIOR_REGRESSION)
    if (
        inputs.last_recorded_spec_digest
        and inputs.spec_digest
        and inputs.last_recorded_spec_digest != inputs.spec_digest
    ):
        reasons.append(StaleReason.ABI_CHANGE)
    if (
        inputs.last_recorded_implementation_version
        and inputs.implementation_version
        and inputs.last_recorded_implementation_version != inputs.implementation_version
    ):
        reasons.append(StaleReason.PROVIDER_CHANGE)
    if (
        inputs.last_recorded_registry_version
        and inputs.current_registry_version
        and inputs.last_recorded_registry_version != inputs.current_registry_version
    ):
        reasons.append(StaleReason.REGISTRY_CHANGE)
    if has_prior and inputs.validation_total_count > 0:
        failed = inputs.validation_total_count - inputs.validation_pass_count
        if failed > 0 and inputs.verification_pct < 100.0:
            reasons.append(StaleReason.FAILED_VERIFICATION)
    return reasons


def compute_certification_level(inputs: CertificationInputs) -> CertificationLevel:
    """Compute certification level deterministically from evidence."""
    stale = detect_stale_reasons(inputs)
    if stale:
        return CertificationLevel.REQUIRES_REVALIDATION

    if not inputs.has_specification:
        return CertificationLevel.UNVERIFIED

    if not inputs.supported:
        if inputs.has_negative_fixture_pass:
            return CertificationLevel.BEHAVIOR_TESTED
        return CertificationLevel.SPECIFIED

    level = CertificationLevel.SPECIFIED

    suite_ok = inputs.has_behavior_suite and (
        inputs.suite_pass_count > 0 or inputs.verified_scenario_present
    )
    if suite_ok:
        level = CertificationLevel.BEHAVIOR_TESTED

    if (
        inputs.validation_pass_count > 0
        and inputs.fixture_coverage_pct >= 100.0
        and inputs.verification_pct >= 100.0
    ):
        level = CertificationLevel.VERIFIED
    elif inputs.verified_scenario_present and inputs.fixture_coverage_pct >= 100.0:
        level = CertificationLevel.VERIFIED

    if inputs.calibration_link_count > 0 and _level_index(level) >= _level_index(
        CertificationLevel.VERIFIED
    ):
        level = CertificationLevel.CALIBRATED

    gov_maturity = inputs.governance_maturity.lower()
    if gov_maturity in ("verified_bounded", "production", "governed") and _level_index(
        level
    ) >= _level_index(CertificationLevel.CALIBRATED):
        level = CertificationLevel.GOVERNED

    if (
        inputs.evidence_bundle_count > 0
        and _level_index(level) >= _level_index(CertificationLevel.VERIFIED)
    ):
        level = CertificationLevel.CERTIFIED

    if (
        inputs.benchmark_history_count > 0
        and inputs.verification_pct >= 100.0
        and _level_index(level) >= _level_index(CertificationLevel.CERTIFIED)
    ):
        level = CertificationLevel.PRODUCTION_READY

    return level


def compute_compliance_status(
    level: CertificationLevel,
    supported: bool,
    stale_reasons: List[StaleReason],
) -> ComplianceStatus:
    """Map certification level to compliance matrix status."""
    if stale_reasons or level == CertificationLevel.REQUIRES_REVALIDATION:
        return ComplianceStatus.REQUIRES_REVALIDATION
    if not supported:
        return ComplianceStatus.UNSUPPORTED
    if level in (CertificationLevel.CERTIFIED, CertificationLevel.PRODUCTION_READY):
        return ComplianceStatus.CERTIFIED
    if level == CertificationLevel.UNVERIFIED:
        return ComplianceStatus.NOT_CERTIFIED
    return ComplianceStatus.IN_PROGRESS


def scenario_status_passes(status: TestScenarioStatus) -> bool:
    return status in (TestScenarioStatus.PASS, TestScenarioStatus.NOT_APPLICABLE)


def criteria_documentation() -> dict[str, str]:
    """Documented criteria for each certification level (for tests)."""
    return {
        "unverified": "No specification link from native_engineering",
        "specified": "Deterministic API spec exists for linked api_symbol",
        "behavior_tested": "Behavior suite has passing cases or verified_scenario in ACI profile",
        "verified": "Validation results pass and fixture_coverage_pct >= 100",
        "calibrated": "At least one calibration snapshot link present",
        "governed": "Governance maturity is verified_bounded or production (read-only)",
        "certified": "Evidence bundle links present with level >= verified",
        "production_ready": "Benchmark history + 100% verification + certified",
        "requires_revalidation": "Stale: regression, ABI change, provider/registry change, or failed verification",
    }
