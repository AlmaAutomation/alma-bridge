"""Read-only certification queries."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.certification.behavioral_profiles import (
    get_behavior_target,
    list_behavior_targets,
    suite_cases_for_behavior,
)
from alma_bridge.certification.certificates import generate_behavior_certification
from alma_bridge.certification.errors import BehaviorNotFoundError
from alma_bridge.certification.models import (
    BehaviorCertification,
    CertificationHistory,
    CERTIFICATION_PROVIDER_ID,
)
from alma_bridge.certification.repository import CertificationRepository
from alma_bridge.compatibility_intelligence.governance.repository import GovernanceRepository
from alma_bridge.evidence.queries import EvidenceQueries
from alma_bridge.evidence.repository import EvidenceRepository
from alma_bridge.native_engineering.behavior_suites import get_behavior_suite
from alma_bridge.native_engineering.models import TestScenarioStatus
from alma_bridge.native_engineering.queries import NativeEngineeringQueries


class CertificationQueries:
    """Aggregate read-only certification data across engineering, ACI, and evidence."""

    def __init__(
        self,
        *,
        engineering_queries: Optional[NativeEngineeringQueries] = None,
        certification_repo: Optional[CertificationRepository] = None,
        governance_repo: Optional[GovernanceRepository] = None,
        evidence_repo: Optional[EvidenceRepository] = None,
    ) -> None:
        self._engineering = engineering_queries or NativeEngineeringQueries()
        self._cert_repo = certification_repo or CertificationRepository()
        self._governance = governance_repo or GovernanceRepository()
        self._evidence = EvidenceQueries(evidence_repo or EvidenceRepository())

    def _current_registry_version(self) -> str:
        try:
            registry = self._governance.get_current_version()
            return registry.version_id
        except Exception:
            return ""

    def _suite_statuses_for_behavior(
        self, api_symbols: List[str], behavior_id: str
    ) -> dict[str, TestScenarioStatus]:
        statuses: dict[str, TestScenarioStatus] = {}
        for sym in api_symbols:
            suite = get_behavior_suite(sym)
            for case in suite.cases:
                if case.behavior_id == behavior_id:
                    statuses[case.case_id] = case.status
        return statuses

    def _build_certification(self, target) -> BehaviorCertification:
        api_sym = target.api_symbols[0] if target.api_symbols else ""
        profile = None
        if api_sym:
            profile = self._engineering.build_profile(api_sym)

        calibration_links = []
        governance_links = []
        evidence_links = []
        validation_results = []
        benchmark_links = []

        if profile:
            calibration_links = profile.calibration_links
            governance_links = profile.governance_links
            evidence_links = profile.evidence_links
            validation_results = profile.validation_results
            for result in profile.benchmark_results:
                benchmark_links.append(result)

        last_record = self._cert_repo.last_record_metadata(
            target.capability_id, target.behavior_id
        )

        suite_statuses = self._suite_statuses_for_behavior(
            target.api_symbols, target.behavior_id
        )

        return generate_behavior_certification(
            target,
            suite_statuses=suite_statuses,
            calibration_links=calibration_links,
            governance_links=governance_links,
            benchmark_links=benchmark_links,
            evidence_links=evidence_links,
            validation_results=validation_results,
            last_record=last_record,
            current_registry_version=self._current_registry_version(),
        )

    def list_behavior_certifications(self) -> List[BehaviorCertification]:
        return [self._build_certification(t) for t in list_behavior_targets()]

    def get_behavior_certification(
        self, capability_id: str, behavior_id: str
    ) -> BehaviorCertification:
        target = get_behavior_target(capability_id, behavior_id)
        if target is None:
            raise BehaviorNotFoundError(
                f"No behavior target: {capability_id}/{behavior_id}"
            )
        return self._build_certification(target)

    def get_certification_history(
        self, capability_id: str, behavior_id: str
    ) -> CertificationHistory:
        target = get_behavior_target(capability_id, behavior_id)
        if target is None:
            raise BehaviorNotFoundError(
                f"No behavior target: {capability_id}/{behavior_id}"
            )
        return self._cert_repo.get_history(capability_id, behavior_id)
