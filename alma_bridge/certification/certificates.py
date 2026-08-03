"""Generate certification certificates from evidence."""

from __future__ import annotations

from alma_bridge.certification.criteria import (
    CertificationInputs,
    compute_certification_level,
    compute_compliance_status,
    detect_stale_reasons,
    scenario_status_passes,
)
from alma_bridge.certification.digest import digest_of
from alma_bridge.certification.models import (
    BehaviorCertification,
    BehaviorSuiteLink,
    BenchmarkHistoryLink,
    CalibrationHistoryLink,
    EvidenceReferenceLink,
    GovernanceHistoryLink,
    ResearchReferenceLink,
    SpecificationLink,
    TimelineReferenceLink,
    VerificationContractLink,
    CERTIFICATION_IMPLEMENTATION_VERSION,
    CERTIFICATION_PROVIDER_ID,
)
from alma_bridge.compatibility_intelligence.behavior_requirements import get_behavior_profile
from alma_bridge.native_engineering.models import TestScenarioStatus
from alma_bridge.native_engineering.specifications import get_specification

from alma_bridge.certification.behavioral_profiles import BehaviorTarget, suite_cases_for_behavior


def _primary_api(api_symbols: list[str]) -> str:
    return api_symbols[0] if api_symbols else ""


def _build_inputs(
    target: BehaviorTarget,
    *,
    spec_digest: str,
    has_spec: bool,
    suite_data: dict,
    suite_statuses: dict[str, TestScenarioStatus],
    validation_results: list,
    calibration_links: list,
    governance_links: list,
    benchmark_links: list,
    evidence_links: list,
    research_links: list,
    timeline_links: list,
    verified_scenario_present: bool,
    last_record: dict | None = None,
    current_registry_version: str = "",
) -> CertificationInputs:
    suite_cases = suite_data.get("case_ids", [])
    pass_count = sum(
        1
        for cid in suite_cases
        if scenario_status_passes(suite_statuses.get(cid, TestScenarioStatus.PENDING))
    )
    has_negative_pass = (
        not target.supported
        and pass_count > 0
        and any(
            suite_statuses.get(cid) == TestScenarioStatus.PASS
            for cid in suite_cases
        )
    )
    val_pass = sum(1 for v in validation_results if v.status == TestScenarioStatus.PASS)
    val_total = len(validation_results)
    fixture_paths = suite_data.get("fixture_paths", [])
    fixture_cov = 100.0 if fixture_paths or verified_scenario_present else 0.0
    if target.supported and verified_scenario_present:
        fixture_cov = 100.0
    verification_pct = (val_pass / val_total * 100.0) if val_total else (
        100.0 if verified_scenario_present else 0.0
    )
    gov_maturity = governance_links[0].maturity_state if governance_links else ""
    evidence_bundles = sum(1 for e in evidence_links if e.source == "evidence_bundle")
    has_regression = any(
        suite_statuses.get(cid) == TestScenarioStatus.FAIL for cid in suite_cases
    )

    inputs = CertificationInputs(
        capability_id=target.capability_id,
        behavior_id=target.behavior_id,
        supported=target.supported,
        has_specification=has_spec,
        spec_digest=spec_digest,
        has_behavior_suite=bool(suite_cases),
        suite_pass_count=pass_count,
        suite_total_count=len(suite_cases),
        has_negative_fixture_pass=has_negative_pass,
        validation_pass_count=val_pass,
        validation_total_count=val_total,
        fixture_coverage_pct=fixture_cov,
        calibration_link_count=len(calibration_links),
        governance_maturity=gov_maturity,
        evidence_bundle_count=evidence_bundles,
        benchmark_history_count=len(benchmark_links),
        verified_scenario_present=verified_scenario_present,
        verification_pct=verification_pct,
        implementation_version=CERTIFICATION_IMPLEMENTATION_VERSION,
        current_registry_version=current_registry_version,
        has_regression=has_regression,
    )
    if last_record:
        inputs.last_recorded_spec_digest = last_record.get("spec_digest", "")
        inputs.last_recorded_implementation_version = last_record.get(
            "implementation_version", ""
        )
        inputs.last_recorded_registry_version = last_record.get("registry_version", "")
    return inputs


def generate_behavior_certification(
    target: BehaviorTarget,
    *,
    suite_statuses: dict[str, TestScenarioStatus] | None = None,
    calibration_links: list | None = None,
    governance_links: list | None = None,
    benchmark_links: list | None = None,
    evidence_links: list | None = None,
    research_links: list | None = None,
    timeline_links: list | None = None,
    validation_results: list | None = None,
    last_record: dict | None = None,
    current_registry_version: str = "",
) -> BehaviorCertification:
    """Build a BehaviorCertification from evidence references."""
    suite_statuses = suite_statuses or {}
    calibration_links = calibration_links or []
    governance_links = governance_links or []
    benchmark_links = benchmark_links or []
    evidence_links = evidence_links or []
    research_links = research_links or []
    timeline_links = timeline_links or []
    validation_results = validation_results or []

    api_sym = _primary_api(target.api_symbols)
    spec = get_specification(api_sym) if api_sym else None
    has_spec = spec is not None
    spec_digest = spec.spec_digest if spec else ""

    profile = get_behavior_profile(target.capability_id, CERTIFICATION_PROVIDER_ID)
    verified_scenario_present = bool(profile and profile.verified_scenarios)
    if target.behavior_id == "write_stdout" and profile:
        verified_scenario_present = "hello64_fixture" in profile.verified_scenarios

    suite_data = suite_cases_for_behavior(target.api_symbols, target.behavior_id)

    inputs = _build_inputs(
        target,
        spec_digest=spec_digest,
        has_spec=has_spec,
        suite_data=suite_data,
        suite_statuses=suite_statuses,
        validation_results=validation_results,
        calibration_links=calibration_links,
        governance_links=governance_links,
        benchmark_links=benchmark_links,
        evidence_links=evidence_links,
        research_links=research_links,
        timeline_links=timeline_links,
        verified_scenario_present=verified_scenario_present,
        last_record=last_record,
        current_registry_version=current_registry_version,
    )
    stale_reasons = detect_stale_reasons(inputs)
    level = compute_certification_level(inputs)
    compliance = compute_compliance_status(level, target.supported, stale_reasons)

    spec_link = None
    if spec:
        spec_link = SpecificationLink(
            api_symbol=api_sym,
            spec_digest=spec.spec_digest,
            supported=target.supported,
            limitations=list(target.limitations),
        )

    primary_status = TestScenarioStatus.PENDING
    for cid in suite_data.get("case_ids", []):
        st = suite_statuses.get(cid)
        if st:
            primary_status = st
            break

    cert_body = {
        "capability_id": target.capability_id,
        "behavior_id": target.behavior_id,
        "level": level.value,
        "spec_digest": spec_digest,
    }

    return BehaviorCertification(
        capability_id=target.capability_id,
        behavior_id=target.behavior_id,
        api_symbols=target.api_symbols,
        supported=target.supported,
        certification_level=level,
        compliance_status=compliance,
        specification=spec_link,
        behavior_suite=BehaviorSuiteLink(
            suite_id=suite_data.get("suite_id", ""),
            case_ids=suite_data.get("case_ids", []),
            fixture_paths=suite_data.get("fixture_paths", []),
            test_status=primary_status.value,
        ),
        verification_contracts=[
            VerificationContractLink(
                check_id=v.check_id,
                category=v.category.value if hasattr(v.category, "value") else str(v.category),
                status=v.status.value,
            )
            for v in validation_results
        ],
        calibration_history=[
            CalibrationHistoryLink(
                snapshot_id=c.snapshot_id,
                binary_digest=c.binary_digest,
                recorded_at=c.recorded_at,
            )
            for c in calibration_links
        ],
        governance_history=[
            GovernanceHistoryLink(
                capability_id=g.capability_id,
                maturity_state=g.maturity_state,
                registry_version=g.registry_version,
            )
            for g in governance_links
        ],
        benchmark_history=[
            BenchmarkHistoryLink(
                benchmark_id=b.benchmark_id,
                run_digest=b.run_digest,
                recorded_at=b.recorded_at,
            )
            for b in benchmark_links
        ],
        research_references=[
            ResearchReferenceLink(
                reference_id=r.reference_id,
                source=r.source,
                digest=r.digest,
            )
            for r in research_links
        ],
        evidence_references=[
            EvidenceReferenceLink(
                source=e.source,
                artifact_id=e.artifact_id,
                digest=e.digest,
                fixture_path=e.fixture_path,
            )
            for e in evidence_links
        ],
        timeline_references=[
            TimelineReferenceLink(
                timeline_id=t.timeline_id,
                event_type=t.event_type,
                recorded_at=t.recorded_at,
            )
            for t in timeline_links
        ],
        known_limitations=list(target.limitations),
        fixture_coverage_pct=inputs.fixture_coverage_pct,
        verification_pct=inputs.verification_pct,
        evidence_count=len(evidence_links),
        regression_status="regression" if inputs.has_regression else "none",
        governance_level=inputs.governance_maturity,
        stale_reasons=stale_reasons,
        stale_detail="; ".join(r.value for r in stale_reasons),
        certification_digest=digest_of(cert_body),
        provider_id=CERTIFICATION_PROVIDER_ID,
        implementation_version=CERTIFICATION_IMPLEMENTATION_VERSION,
    )
