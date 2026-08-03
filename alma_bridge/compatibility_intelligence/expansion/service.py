"""Orchestration for runtime expansion plan generation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from alma_bridge.compatibility_intelligence.behavior_requirements import (
    get_behavior_profile,
    list_behavior_profiles,
)
from alma_bridge.compatibility_intelligence.calibration_repository import CalibrationRepository
from alma_bridge.compatibility_intelligence.calibration_service import CalibrationService
from alma_bridge.compatibility_intelligence.coverage_validation import compute_coverage_validation
from alma_bridge.compatibility_intelligence.expansion.complexity import (
    assess_complexity,
    engineering_cost_score,
)
from alma_bridge.compatibility_intelligence.expansion.demand import (
    DemandAggregator,
    application_fingerprint_from_analysis,
    build_demand_counts,
    normalize_demand_score,
)
from alma_bridge.compatibility_intelligence.expansion.digest import (
    compute_candidate_id,
    compute_evidence_digest,
    compute_plan_id,
)
from alma_bridge.compatibility_intelligence.expansion.errors import CandidateNotFoundError
from alma_bridge.compatibility_intelligence.expansion.impact import (
    compute_bounded_impact,
    normalize_impact_score,
)
from alma_bridge.compatibility_intelligence.expansion.models import (
    ExcludedCandidate,
    RuntimeExpansionCandidate,
    RuntimeExpansionPlan,
)
from alma_bridge.compatibility_intelligence.expansion.ranking import (
    assess_evidence_quality,
    assess_testability,
    compute_priority_dimensions,
    filter_plan_candidates,
    is_behavior_already_stable,
    is_hard_excluded,
    rank_candidates,
)
from alma_bridge.compatibility_intelligence.expansion.repository import ExpansionPlanRepository
from alma_bridge.compatibility_intelligence.expansion.risk import (
    assess_security_risk,
    assess_semantic_risk,
)
from alma_bridge.compatibility_intelligence.governance.models import CapabilityMaturityState
from alma_bridge.compatibility_intelligence.governance.repository import GovernanceRepository
from alma_bridge.compatibility_intelligence.models import CompatibilityAnalysisResult
from alma_bridge.compatibility_intelligence.repository import AnalysisRepository


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


BEHAVIOR_CANDIDATE_SPECS: Dict[Tuple[str, str], dict] = {
    ("filesystem.basic_io", "append_existing_file"): {
        "implementation_scope": (
            "native_alma / PE64 console / OPEN_EXISTING + FILE_APPEND_DATA append"
        ),
        "dll_symbols": [
            "kernel32.dll!CreateFileW",
            "kernel32.dll!WriteFile",
            "kernel32.dll!CloseHandle",
        ],
        "prerequisites": ["filesystem.basic_io/create_always_write"],
        "evidence_references": [
            "fixture:file_append_unsupported.exe",
            "native-shim:kernel32_shim.c",
        ],
        "limitations": [
            "OPEN_EXISTING without CREATE_ALWAYS not fully supported",
            "FILE_APPEND_DATA access mode unsupported",
        ],
        "fixture_name": "file_append_unsupported.exe",
    },
    ("filesystem.basic_io", "open_existing_readwrite"): {
        "implementation_scope": "native_alma / PE64 console / OPEN_EXISTING read-write",
        "dll_symbols": ["kernel32.dll!CreateFileW", "kernel32.dll!ReadFile", "kernel32.dll!WriteFile"],
        "prerequisites": ["filesystem.basic_io/create_always_write"],
        "evidence_references": ["fixture:file_read.exe"],
        "limitations": ["OPEN_EXISTING without CREATE_ALWAYS not fully supported"],
        "fixture_name": "file_read.exe",
    },
    ("filesystem.basic_io", "overlapped_io"): {
        "implementation_scope": "native_alma / PE64 console / overlapped file I/O",
        "dll_symbols": ["kernel32.dll!ReadFile", "kernel32.dll!WriteFile"],
        "prerequisites": ["filesystem.basic_io/sequential_read"],
        "evidence_references": [],
        "limitations": ["Overlapped I/O not implemented"],
        "fixture_name": None,
    },
    ("process.environment", "set_environment_variable"): {
        "implementation_scope": "native_alma / PE64 console / SetEnvironmentVariableW",
        "dll_symbols": ["kernel32.dll!SetEnvironmentVariableW"],
        "prerequisites": ["process.environment/read_environment_variable"],
        "evidence_references": ["native-shim:kernel32_shim.c"],
        "limitations": ["Environment block from worker only"],
        "fixture_name": None,
    },
}


class ExpansionPlanningService:
    """Aggregate evidence and generate advisory expansion plans on demand."""

    ENGINE_VERSION = "aci_expansion_v1"

    def __init__(
        self,
        analysis_repo: Optional[AnalysisRepository] = None,
        calibration_repo: Optional[CalibrationRepository] = None,
        governance_repo: Optional[GovernanceRepository] = None,
        plan_repo: Optional[ExpansionPlanRepository] = None,
    ) -> None:
        self._analysis_repo = analysis_repo or AnalysisRepository()
        self._calibration_repo = calibration_repo or CalibrationRepository()
        self._calibration = CalibrationService(self._calibration_repo)
        self._governance_repo = governance_repo or GovernanceRepository()
        self._plan_repo = plan_repo or ExpansionPlanRepository()

    def _maturity_for(
        self, provider_id: str, capability_id: str
    ) -> Tuple[CapabilityMaturityState, List[str], List[str], List[str]]:
        registry = self._governance_repo.get_current_version()
        limitations: List[str] = []
        supported: List[str] = []
        unsupported: List[str] = []
        state = CapabilityMaturityState.DECLARED
        for entry in registry.entries:
            if (
                entry.scope.provider_id == provider_id
                and entry.scope.capability_id == capability_id
            ):
                state = entry.maturity_state
                limitations = list(entry.limitations)
                supported = list(entry.supported_behaviors)
                unsupported = list(entry.unsupported_behaviors)
                break
        profile = get_behavior_profile(capability_id, provider_id)
        if profile:
            if not limitations:
                limitations = list(profile.limitations)
            if not supported:
                supported = list(profile.supported_behaviors)
            if not unsupported:
                unsupported = list(profile.unsupported_behaviors)
        return state, limitations, supported, unsupported

    def _aggregate_demand(
        self, analyses: List[CompatibilityAnalysisResult]
    ) -> DemandAggregator:
        aggregator = DemandAggregator()
        records = self._calibration.list_records()

        for analysis in analyses:
            fixture_name = analysis.file_path.rsplit("/", 1)[-1] if analysis.file_path else ""
            validation = compute_coverage_validation(
                analysis.coverage,
                analysis.required_capabilities,
                analysis.imports,
                analysis.api_classifications,
                analysis.metadata,
                provider_id="native_alma",
                fixture_name=fixture_name or None,
            )
            fingerprint = application_fingerprint_from_analysis(
                analysis.binary_digest, analysis.file_path
            )
            blocked = not analysis.prediction.native_compatible

            for cap in analysis.required_capabilities:
                cap_id = cap.capability_id
                profile = get_behavior_profile(cap_id, "native_alma")
                if profile:
                    for gap in validation.behavior_gaps:
                        if gap in profile.unsupported_behaviors:
                            aggregator.record_analysis(
                                provider_id="native_alma",
                                capability_id=cap_id,
                                behavior_id=gap,
                                binary_digest=analysis.binary_digest,
                                analysis_digest=analysis.analysis_id,
                                application_fingerprint=fingerprint,
                                blocked=blocked,
                            )

            for api in analysis.api_classifications:
                if not api.is_known and api.capability_id == "api.unknown":
                    api_key = f"{api.dll}!{api.function}"
                    aggregator.record_analysis(
                        provider_id="native_alma",
                        capability_id="api.unknown",
                        behavior_id=api_key,
                        binary_digest=analysis.binary_digest,
                        analysis_digest=analysis.analysis_id,
                        application_fingerprint=fingerprint,
                        blocked=blocked,
                    )

        for record in records:
            provider_id = str(record.get("provider_id", "native_alma"))
            gaps = record.get("behavior_gaps") or []
            binary_digest = str(record.get("binary_digest", ""))
            analysis_digest = str(record.get("analysis_digest", ""))
            session_id = str(record.get("session_id", ""))
            classification = str(record.get("classification", ""))
            verified = bool(record.get("verified_success"))
            timestamp = record.get("created_at")

            for gap in gaps:
                for cap_id in self._capability_for_behavior(gap):
                    aggregator.record_calibration(
                        provider_id=provider_id,
                        capability_id=cap_id,
                        behavior_id=gap,
                        binary_digest=binary_digest,
                        analysis_digest=analysis_digest,
                        session_id=session_id,
                        classification=classification,
                        behavior_gaps=gaps,
                        verified_success=verified,
                        timestamp=timestamp,
                    )

            if provider_id == "wine" and verified and classification == "true_positive":
                for gap in gaps:
                    for cap_id in self._capability_for_behavior(gap):
                        aggregator.record_wine_success(
                            capability_id=cap_id,
                            behavior_id=gap,
                            binary_digest=binary_digest,
                            session_id=session_id,
                            timestamp=timestamp,
                        )

        return aggregator

    @staticmethod
    def _capability_for_behavior(behavior_id: str) -> List[str]:
        caps: Set[str] = set()
        for profile in list_behavior_profiles():
            if behavior_id in profile.supported_behaviors + profile.unsupported_behaviors:
                caps.add(profile.capability_id)
        if not caps:
            for (cap_id, beh), _spec in BEHAVIOR_CANDIDATE_SPECS.items():
                if beh == behavior_id:
                    caps.add(cap_id)
        return sorted(caps)

    def _build_behavior_candidate(
        self,
        provider_id: str,
        capability_id: str,
        behavior_id: str,
        aggregator: DemandAggregator,
        analyses: List[CompatibilityAnalysisResult],
    ) -> Tuple[Optional[RuntimeExpansionCandidate], Optional[ExcludedCandidate]]:
        spec = BEHAVIOR_CANDIDATE_SPECS.get((capability_id, behavior_id), {})
        implementation_scope = spec.get(
            "implementation_scope",
            f"{provider_id} / {capability_id} / {behavior_id}",
        )
        candidate_id = compute_candidate_id(
            provider_id, capability_id, behavior_id, implementation_scope
        )
        fixture_name = spec.get("fixture_name")
        has_fixture = bool(fixture_name) or bool(spec.get("evidence_references"))

        exclusion = is_hard_excluded(
            capability_id,
            has_reproducible_fixture=has_fixture,
            implementation_scope=implementation_scope,
        )
        if exclusion:
            return None, ExcludedCandidate(
                candidate_id=candidate_id,
                provider_id=provider_id,
                capability_id=capability_id,
                behavior_id=behavior_id,
                exclusion_reason=exclusion,
            )

        maturity, limitations, supported, unsupported = self._maturity_for(
            provider_id, capability_id
        )
        if is_behavior_already_stable(behavior_id, supported, maturity):
            return None, ExcludedCandidate(
                candidate_id=candidate_id,
                provider_id=provider_id,
                capability_id=capability_id,
                behavior_id=behavior_id,
                exclusion_reason=(
                    f"behavior {behavior_id} already stable at maturity {maturity.value}"
                ),
            )

        if behavior_id not in unsupported:
            profile = get_behavior_profile(capability_id, provider_id)
            if not profile or behavior_id not in profile.unsupported_behaviors:
                return None, None

        evidence = aggregator.get_evidence(provider_id, capability_id, behavior_id)
        if not evidence.binary_digests and not spec.get("evidence_references"):
            return None, ExcludedCandidate(
                candidate_id=candidate_id,
                provider_id=provider_id,
                capability_id=capability_id,
                behavior_id=behavior_id,
                exclusion_reason="hard exclusion: no reproducible evidence",
            )

        demand = build_demand_counts(evidence)
        demand_score = normalize_demand_score(demand)

        behavior_before = 0.0
        if demand.distinct_binary_digests > 0:
            behavior_before = round(100.0 / max(demand.distinct_binary_digests + 1, 1), 2)
        behavior_after = min(100.0, behavior_before + 25.0)
        impact = compute_bounded_impact(
            demand, evidence, behavior_coverage_before=behavior_before, behavior_coverage_after=behavior_after
        )
        impact_score = normalize_impact_score(impact)

        dll_symbols = list(spec.get("dll_symbols", []))
        complexity = assess_complexity(capability_id, behavior_id, api_count=len(dll_symbols) or 1)
        security = assess_security_risk(capability_id, behavior_id)
        semantic = assess_semantic_risk(capability_id, behavior_id)

        evidence_refs = list(spec.get("evidence_references", []))
        if fixture_name:
            evidence_refs.append(f"fixture:{fixture_name}")

        testability, testability_score = assess_testability(evidence_refs, behavior_id)
        evidence_quality, evidence_quality_score = assess_evidence_quality(
            demand.distinct_binary_digests,
            evidence_refs,
            len(evidence.verified_native_sessions),
        )

        priority = compute_priority_dimensions(
            demand_score=demand_score,
            bounded_impact_score=impact_score,
            complexity_cost_score=engineering_cost_score(complexity),
            security_risk_score=security.score,
            semantic_risk_score=semantic.score,
            evidence_quality_score=evidence_quality_score,
            testability_score=testability_score,
        )

        architecture = "x64"
        subsystem = "console"
        for analysis in analyses:
            if analysis.binary_digest in evidence.binary_digests:
                architecture = analysis.metadata.architecture
                subsystem = analysis.metadata.subsystem
                break

        candidate = RuntimeExpansionCandidate(
            candidate_id=candidate_id,
            provider_id=provider_id,
            capability_id=capability_id,
            behavior_id=behavior_id,
            dll_symbols=dll_symbols,
            implementation_scope=implementation_scope,
            architecture=architecture,
            subsystem=subsystem,
            affected_application_fingerprints=sorted(evidence.application_fingerprints),
            affected_analysis_digests=sorted(evidence.analysis_digests),
            observed_demand_count=demand.distinct_binary_digests,
            verified_session_count=len(evidence.verified_native_sessions),
            blocked_session_count=demand.blocked_session_count,
            false_positive_gap_count=demand.false_positive_gap_count,
            demand=demand,
            demand_score=demand_score,
            estimated_coverage_gain=impact.behavior_coverage_increase_percent,
            impact=impact,
            bounded_impact_score=impact_score,
            prerequisite_capabilities=list(spec.get("prerequisites", [])),
            engineering_complexity=complexity,
            security_risk=security,
            semantic_risk=semantic,
            testability=testability,
            testability_score=testability_score,
            evidence_quality=evidence_quality,
            evidence_quality_score=evidence_quality_score,
            priority=priority,
            limitations=list(spec.get("limitations", limitations)),
            evidence_references=sorted(set(evidence_refs)),
        )
        return candidate, None

    def _build_unknown_api_candidate(
        self,
        api_key: str,
        aggregator: DemandAggregator,
        analyses: List[CompatibilityAnalysisResult],
    ) -> Tuple[Optional[RuntimeExpansionCandidate], Optional[ExcludedCandidate]]:
        provider_id = "native_alma"
        capability_id = "api.unknown"
        behavior_id = api_key
        implementation_scope = f"{provider_id} / unknown API / {api_key}"
        candidate_id = compute_candidate_id(
            provider_id, capability_id, behavior_id, implementation_scope
        )

        exclusion = is_hard_excluded(
            capability_id,
            has_reproducible_fixture=False,
            implementation_scope=implementation_scope,
        )
        if exclusion:
            return None, ExcludedCandidate(
                candidate_id=candidate_id,
                provider_id=provider_id,
                capability_id=capability_id,
                behavior_id=behavior_id,
                exclusion_reason=exclusion,
            )

        evidence = aggregator.get_evidence(provider_id, capability_id, behavior_id)
        if not evidence.binary_digests:
            return None, None

        demand = build_demand_counts(evidence)
        demand_score = normalize_demand_score(demand)
        impact = compute_bounded_impact(demand, evidence)
        impact_score = normalize_impact_score(impact)
        complexity = assess_complexity(capability_id, behavior_id)
        security = assess_security_risk(capability_id)
        semantic = assess_semantic_risk(capability_id)

        evidence_refs = [f"unknown_api:{api_key}"]
        testability, testability_score = assess_testability(evidence_refs, behavior_id)
        evidence_quality, evidence_quality_score = assess_evidence_quality(
            demand.distinct_binary_digests, evidence_refs, 0
        )
        priority = compute_priority_dimensions(
            demand_score=demand_score,
            bounded_impact_score=impact_score,
            complexity_cost_score=engineering_cost_score(complexity),
            security_risk_score=security.score,
            semantic_risk_score=semantic.score,
            evidence_quality_score=evidence_quality_score,
            testability_score=testability_score,
        )

        return RuntimeExpansionCandidate(
            candidate_id=candidate_id,
            provider_id=provider_id,
            capability_id=capability_id,
            behavior_id=behavior_id,
            dll_symbols=[api_key],
            implementation_scope=implementation_scope,
            affected_application_fingerprints=sorted(evidence.application_fingerprints),
            affected_analysis_digests=sorted(evidence.analysis_digests),
            observed_demand_count=demand.distinct_binary_digests,
            blocked_session_count=demand.blocked_session_count,
            demand=demand,
            demand_score=demand_score,
            impact=impact,
            bounded_impact_score=impact_score,
            engineering_complexity=complexity,
            security_risk=security,
            semantic_risk=semantic,
            testability=testability,
            testability_score=testability_score,
            evidence_quality=evidence_quality,
            evidence_quality_score=evidence_quality_score,
            priority=priority,
            limitations=["Unknown API — no capability mapping; classification confidence explicit only"],
            evidence_references=evidence_refs,
        ), None

    def generate_plan(self, *, persist: bool = False) -> RuntimeExpansionPlan:
        """Generate expansion plan from current evidence — read-only, no registry mutation."""
        registry_version = self._governance_repo.get_current_version().version_id
        analyses = self._analysis_repo.list_recent(limit=500)
        aggregator = self._aggregate_demand(analyses)

        candidates: List[RuntimeExpansionCandidate] = []
        excluded: List[ExcludedCandidate] = []
        seen_ids: Set[str] = set()

        for profile in list_behavior_profiles("native_alma"):
            for behavior_id in profile.unsupported_behaviors:
                candidate, excl = self._build_behavior_candidate(
                    "native_alma",
                    profile.capability_id,
                    behavior_id,
                    aggregator,
                    analyses,
                )
                if candidate and candidate.candidate_id not in seen_ids:
                    candidates.append(candidate)
                    seen_ids.add(candidate.candidate_id)
                elif excl and excl.candidate_id not in seen_ids:
                    excluded.append(excl)
                    seen_ids.add(excl.candidate_id)

        for provider_id, capability_id, behavior_id in aggregator.all_keys():
            if capability_id == "api.unknown" and behavior_id:
                candidate, excl = self._build_unknown_api_candidate(
                    behavior_id, aggregator, analyses
                )
                if candidate and candidate.candidate_id not in seen_ids:
                    candidates.append(candidate)
                    seen_ids.add(candidate.candidate_id)
                elif excl and excl.candidate_id not in seen_ids:
                    excluded.append(excl)
                    seen_ids.add(excl.candidate_id)
            elif provider_id == "native_alma" and behavior_id:
                key = (capability_id, behavior_id)
                if key in BEHAVIOR_CANDIDATE_SPECS:
                    candidate, excl = self._build_behavior_candidate(
                        provider_id, capability_id, behavior_id, aggregator, analyses
                    )
                    if candidate and candidate.candidate_id not in seen_ids:
                        candidates.append(candidate)
                        seen_ids.add(candidate.candidate_id)
                    elif excl and excl.candidate_id not in seen_ids:
                        excluded.append(excl)
                        seen_ids.add(excl.candidate_id)

        ranked, excluded = rank_candidates(candidates, excluded)

        timestamps = [
            a.provenance.detail for a in analyses if a.provenance
        ]
        evidence_payload = {
            "analysis_count": len(analyses),
            "calibration_count": len(self._calibration.list_records()),
            "candidate_count": len(ranked),
            "registry_version": registry_version,
        }
        evidence_digest = compute_evidence_digest(evidence_payload)
        plan_id = compute_plan_id(registry_version, evidence_digest)

        plan = RuntimeExpansionPlan(
            plan_id=plan_id,
            registry_version=registry_version,
            analysis_window={
                "analysis_count": str(len(analyses)),
                "from": timestamps[0] if timestamps else "",
                "to": _utc_now_iso(),
            },
            ranked_candidates=ranked,
            excluded_candidates=excluded,
            assumptions=[
                "Observed demand derived from deduplicated Alma analyses and calibration records",
                "Estimated bounded impact describes identified blocker removal — not guaranteed compatibility",
                "Engineering candidates require human review before implementation",
            ],
            limitations=[
                "Plan does not mutate capability registry or provider selection",
                "No automatic API implementation or code generation",
                "Unknown APIs are not mapped to capabilities without explicit classification",
            ],
            generated_at=_utc_now_iso(),
            evidence_digest=evidence_digest,
        )
        if persist:
            self._plan_repo.save_plan(plan)
            try:
                from alma_bridge.evidence.hooks import on_expansion_plan_generated

                on_expansion_plan_generated(plan.plan_id, plan.evidence_digest)
            except Exception:
                pass
        return plan

    def get_plan(
        self,
        *,
        provider_id: Optional[str] = None,
        architecture: Optional[str] = None,
        subsystem: Optional[str] = None,
        maximum_complexity: Optional[str] = None,
        maximum_security_risk: Optional[float] = None,
        persist: bool = False,
    ) -> RuntimeExpansionPlan:
        plan = self.generate_plan(persist=persist)
        if any([provider_id, architecture, subsystem, maximum_complexity, maximum_security_risk]):
            filtered = filter_plan_candidates(
                plan.ranked_candidates,
                provider_id=provider_id,
                architecture=architecture,
                subsystem=subsystem,
                maximum_complexity=maximum_complexity,
                maximum_security_risk=maximum_security_risk,
            )
            return plan.model_copy(update={"ranked_candidates": filtered})
        return plan

    def get_candidate(self, candidate_id: str) -> RuntimeExpansionCandidate:
        plan = self.generate_plan()
        for candidate in plan.ranked_candidates:
            if candidate.candidate_id == candidate_id:
                return candidate
        for excl in plan.excluded_candidates:
            if excl.candidate_id == candidate_id:
                raise CandidateNotFoundError(
                    f"Candidate {candidate_id} is excluded: {excl.exclusion_reason}"
                )
        raise CandidateNotFoundError(f"Candidate not found: {candidate_id}")

    def get_candidates_for_capability(self, capability_id: str) -> List[RuntimeExpansionCandidate]:
        plan = self.generate_plan()
        return [c for c in plan.ranked_candidates if c.capability_id == capability_id]
