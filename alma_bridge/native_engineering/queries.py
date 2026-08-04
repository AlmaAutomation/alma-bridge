"""Read-only queries for API engineering profiles."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.compatibility_intelligence.behavior_requirements import (
    BEHAVIOR_REGISTRY_VERSION,
    get_behavior_profile,
    list_behavior_profiles,
)
from alma_bridge.compatibility_intelligence.calibration_repository import CalibrationRepository
from alma_bridge.compatibility_intelligence.governance.repository import GovernanceRepository
from alma_bridge.evidence.queries import EvidenceQueries
from alma_bridge.evidence.repository import EvidenceRepository
from alma_bridge.native_engineering.behavior_suites import get_all_behavior_suites, get_behavior_suite
from alma_bridge.native_engineering.benchmarks import list_benchmark_definitions
from alma_bridge.native_engineering.conformance import generate_conformance_report
from alma_bridge.native_engineering.digest import digest_of
from alma_bridge.native_engineering.filesystem_semantics import validate_filesystem_semantics
from alma_bridge.native_engineering.handle_lifecycle import validate_handle_lifecycle
from alma_bridge.native_engineering.longitudinal import build_history_from_results
from alma_bridge.native_engineering.memory_tests import validate_memory_correctness
from alma_bridge.native_engineering.models import (
    NATIVE_IMPLEMENTATION_VERSION,
    NATIVE_PROVIDER_ID,
    ApiEngineeringProfile,
    BehaviorCoverageDashboard,
    BehaviorCoverageEntry,
    BenchmarkHistory,
    CalibrationLink,
    EvidenceLink,
    GovernanceLink,
    TestScenarioStatus,
)
from alma_bridge.native_engineering.repository import NativeEngineeringRepository
from alma_bridge.native_engineering.semantic_validation import validate_api_semantics
from alma_bridge.native_engineering.specifications import (
    API_CAPABILITY_MAP,
    get_all_specifications,
    get_specification,
    list_api_symbols,
)
from alma_bridge.native_engineering.threading_validation import validate_threading
from alma_bridge.native_engineering.unicode_validation import validate_unicode_correctness


class NativeEngineeringQueries:
    """Aggregate read-only engineering data across ACI, evidence, and benchmarks."""

    def __init__(
        self,
        *,
        calibration_repo: Optional[CalibrationRepository] = None,
        governance_repo: Optional[GovernanceRepository] = None,
        evidence_repo: Optional[EvidenceRepository] = None,
        engineering_repo: Optional[NativeEngineeringRepository] = None,
    ) -> None:
        self._calibration = calibration_repo or CalibrationRepository()
        self._governance = governance_repo or GovernanceRepository()
        self._evidence = EvidenceQueries(evidence_repo or EvidenceRepository())
        self._engineering = engineering_repo or NativeEngineeringRepository()

    def registry_versions(self) -> dict[str, str]:
        return {
            "behavior_registry": BEHAVIOR_REGISTRY_VERSION,
            "provider_id": NATIVE_PROVIDER_ID,
            "implementation_version": NATIVE_IMPLEMENTATION_VERSION,
        }

    def calibration_links_for_capability(self, capability_id: str) -> List[CalibrationLink]:
        links: List[CalibrationLink] = []
        for snap in self._calibration.list_snapshots():
            if snap.provider_id != NATIVE_PROVIDER_ID:
                continue
            gaps = snap.static_coverage.behavior_gaps if snap.static_coverage else []
            if capability_id and gaps:
                pass
            links.append(
                CalibrationLink(
                    snapshot_id=snap.snapshot_id,
                    classification="",
                    binary_digest=snap.binary_digest,
                    recorded_at=snap.created_at,
                )
            )
        return links[:20]

    def governance_links_for_capability(self, capability_id: str) -> List[GovernanceLink]:
        links: List[GovernanceLink] = []
        try:
            registry = self._governance.get_current_version()
        except Exception:
            return links
        for entry in registry.entries:
            if entry.scope.capability_id != capability_id:
                continue
            if entry.scope.provider_id != NATIVE_PROVIDER_ID:
                continue
            links.append(
                GovernanceLink(
                    capability_id=entry.scope.capability_id,
                    maturity_state=entry.maturity_state.value if hasattr(entry.maturity_state, "value") else str(entry.maturity_state),
                    scope_key=entry.scope.scope_key() if hasattr(entry.scope, "scope_key") else "",
                    registry_version=registry.version_id,
                )
            )
        return links

    def evidence_links_for_api(self, api_symbol: str) -> List[EvidenceLink]:
        links: List[EvidenceLink] = []
        suite = get_behavior_suite(api_symbol)
        for case in suite.cases:
            if case.fixture_path:
                links.append(
                    EvidenceLink(
                        source="fixture",
                        artifact_id=case.case_id,
                        fixture_path=case.fixture_path,
                    )
                )
        links.append(
            EvidenceLink(
                source="native-shim",
                artifact_id="kernel32_shim.c",
                digest="native-shim:kernel32_shim.c",
            )
        )
        for bundle_id in self._evidence.list_bundle_ids()[:5]:
            bundle = self._evidence.by_bundle_id(bundle_id)
            if bundle is None:
                continue
            links.append(
                EvidenceLink(
                    source="evidence_bundle",
                    artifact_id=bundle.bundle_id,
                    digest=bundle.bundle_digest,
                )
            )
        return links

    def build_profile(self, api_symbol: str) -> ApiEngineeringProfile:
        spec = get_specification(api_symbol)
        suite = get_behavior_suite(api_symbol)
        cap_id, behavior_ids = API_CAPABILITY_MAP.get(api_symbol, ("unknown", []))

        validations = (
            validate_api_semantics()
            + validate_memory_correctness()
            + validate_handle_lifecycle()
            + validate_filesystem_semantics()
            + validate_unicode_correctness()
            + validate_threading()
        )
        api_validations = [v for v in validations if v.api_symbol == api_symbol or v.api_symbol == "*"]

        body = {
            "api_symbol": api_symbol,
            "capability_id": cap_id,
            "spec_digest": spec.spec_digest,
        }
        return ApiEngineeringProfile(
            api_symbol=api_symbol,
            capability_id=cap_id,
            behavior_ids=behavior_ids,
            specification=spec,
            behavior_suite=suite,
            calibration_links=self.calibration_links_for_capability(cap_id),
            governance_links=self.governance_links_for_capability(cap_id),
            benchmark_results=[r for r in self._engineering.list_benchmark_results() if r.api_symbol == api_symbol or not r.api_symbol][:10],
            evidence_links=self.evidence_links_for_api(api_symbol),
            validation_results=api_validations,
            profile_digest=digest_of(body),
        )

    def list_profiles(self) -> List[ApiEngineeringProfile]:
        return [self.build_profile(sym) for sym in list_api_symbols()]

    def behavior_coverage_dashboard(self) -> BehaviorCoverageDashboard:
        entries: List[BehaviorCoverageEntry] = []
        unsupported: set[str] = set()

        for profile in list_behavior_profiles(NATIVE_PROVIDER_ID):
            for behavior in profile.supported_behaviors:
                apis = [sym for sym, (_, bs) in API_CAPABILITY_MAP.items() if behavior in bs]
                fixtures = []
                for sym in apis:
                    suite = get_behavior_suite(sym)
                    fixtures.extend(c.fixture_path for c in suite.cases if c.fixture_path and c.behavior_id == behavior)
                entries.append(
                    BehaviorCoverageEntry(
                        behavior_id=behavior,
                        capability_id=profile.capability_id,
                        api_symbols=apis,
                        supported=True,
                        test_status=TestScenarioStatus.PASS if profile.verified_scenarios else TestScenarioStatus.PENDING,
                        fixture_paths=sorted(set(fixtures)),
                    )
                )
            for behavior in profile.unsupported_behaviors:
                unsupported.add(behavior)
                apis = [sym for sym, (_, bs) in API_CAPABILITY_MAP.items() if behavior in bs]
                status = TestScenarioStatus.PASS if behavior == "overlapped_io" else TestScenarioStatus.NOT_APPLICABLE
                entries.append(
                    BehaviorCoverageEntry(
                        behavior_id=behavior,
                        capability_id=profile.capability_id,
                        api_symbols=apis,
                        supported=False,
                        test_status=status,
                        fixture_paths=["tests/fixtures/native_runtime/bin/append_overlapped_unsupported.exe"] if behavior == "overlapped_io" else [],
                    )
                )

        return BehaviorCoverageDashboard(
            entries=sorted(entries, key=lambda e: (e.capability_id, e.behavior_id)),
            unsupported_behaviors=sorted(unsupported),
        )

    def benchmark_history(self) -> List[BenchmarkHistory]:
        stored = self._engineering.list_benchmark_history()
        if stored:
            return stored
        results = self._engineering.list_benchmark_results()
        if results:
            return build_history_from_results(results)
        return build_history_from_results([])

    def list_benchmark_catalog(self) -> List[dict]:
        return list_benchmark_definitions()

    def conformance_report(self):
        return generate_conformance_report()

    def all_specifications(self):
        return get_all_specifications()
