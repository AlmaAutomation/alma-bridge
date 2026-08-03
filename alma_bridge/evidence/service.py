"""Evidence lifecycle orchestration and integration hooks."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from alma_bridge.compatibility_intelligence.calibration_service import CalibrationService
from alma_bridge.compatibility_intelligence.expansion.repository import ExpansionPlanRepository
from alma_bridge.compatibility_intelligence.governance.repository import GovernanceRepository
from alma_bridge.compatibility_intelligence.metrics import compute_registry_metrics
from alma_bridge.compatibility_intelligence.repository import AnalysisRepository
from alma_bridge.evidence.builder import CompatibilityEvidenceBundleBuilder
from alma_bridge.evidence.digest import compute_event_id
from alma_bridge.evidence.history import EvidenceHistory
from alma_bridge.evidence.models import (
    CompatibilityEvidenceBundle,
    PlatformHealthMetric,
    PlatformHealthReport,
    Provenance,
    TimelineEvent,
    TimelineEventType,
    utc_now_iso,
)
from alma_bridge.evidence.queries import EvidenceQueries
from alma_bridge.evidence.repository import EvidenceRepository
from alma_bridge.evidence.timeline import EvidenceTimeline


class EvidenceService:
    """Orchestrate bundle assembly, timeline events, and platform health."""

    _instance: Optional[EvidenceService] = None

    def __init__(
        self,
        *,
        repository: Optional[EvidenceRepository] = None,
        builder: Optional[CompatibilityEvidenceBundleBuilder] = None,
    ) -> None:
        self._repo = repository or EvidenceRepository()
        self._builder = builder or CompatibilityEvidenceBundleBuilder()
        self._queries = EvidenceQueries(self._repo)
        self._history = EvidenceHistory(self._repo)

    @classmethod
    def shared(cls) -> EvidenceService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def assemble_bundle(
        self,
        binary_digest: str,
        *,
        session_id: Optional[str] = None,
        persist: bool = True,
    ) -> CompatibilityEvidenceBundle:
        bundle = self._builder.build_for_binary(binary_digest, session_id=session_id)
        if persist:
            bundle = self._repo.save_bundle(bundle)
        return bundle

    def assemble_for_file(
        self,
        file_path: str,
        *,
        session_id: Optional[str] = None,
        persist: bool = True,
    ) -> CompatibilityEvidenceBundle:
        bundle = self._builder.build_for_file(file_path, session_id=session_id)
        if persist:
            bundle = self._repo.save_bundle(bundle)
        return bundle

    def get_bundle_by_digest(self, binary_digest: str) -> Optional[CompatibilityEvidenceBundle]:
        return self._queries.by_binary_digest(binary_digest)

    def get_bundle_by_fingerprint(self, fingerprint: str) -> Optional[CompatibilityEvidenceBundle]:
        return self._queries.by_application_fingerprint(fingerprint)

    def get_timeline(self, bundle_id: str) -> List[TimelineEvent]:
        return self._queries.timeline(bundle_id)

    def get_history(self, bundle_id: str):
        return self._history.list_versions(bundle_id)

    def append_event(
        self,
        bundle_id: str,
        event_type: TimelineEventType,
        *,
        source: str,
        evidence_digest: str,
        references: Optional[List[str]] = None,
        provenance: Optional[Provenance] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TimelineEvent:
        """Append-only timeline event — never modifies prior events."""
        timeline = EvidenceTimeline(self._repo.list_timeline_events(bundle_id))
        event = timeline.append(
            event_type,
            source=source,
            evidence_digest=evidence_digest,
            references=references,
            provenance=provenance,
            metadata=metadata,
        )
        self._repo.append_timeline_event(bundle_id, event)
        return event

    def record_analysis(self, binary_digest: str, analysis_id: str, analysis_digest: str) -> None:
        bundle = self.assemble_bundle(binary_digest, persist=True)
        self.append_event(
            bundle.bundle_id,
            TimelineEventType.ANALYSIS_CREATED,
            source="aci_service",
            evidence_digest=analysis_digest,
            references=[analysis_id],
            provenance=Provenance(
                source="aci_service", artifact_id=analysis_id, digest=analysis_digest
            ),
        )

    def record_prediction(self, bundle_id: str, snapshot_id: str, snapshot_digest: str) -> None:
        self.append_event(
            bundle_id,
            TimelineEventType.PREDICTION_GENERATED,
            source="aci_predictor",
            evidence_digest=snapshot_digest,
            references=[snapshot_id],
            provenance=Provenance(
                source="aci_predictor", artifact_id=snapshot_id, digest=snapshot_digest
            ),
        )

    def record_execution(self, bundle_id: str, session_id: str, execution_digest: str) -> None:
        self.append_event(
            bundle_id,
            TimelineEventType.EXECUTION_STARTED,
            source="bridge_orchestrator",
            evidence_digest=execution_digest,
            references=[session_id],
            provenance=Provenance(
                source="bridge_orchestrator",
                artifact_id=session_id,
                digest=execution_digest,
                session_id=session_id,
            ),
        )

    def record_verification(
        self, bundle_id: str, session_id: str, verification_digest: str, verified: bool
    ) -> None:
        self.append_event(
            bundle_id,
            TimelineEventType.VERIFICATION_COMPLETED,
            source="verification_engine",
            evidence_digest=verification_digest,
            references=[session_id],
            provenance=Provenance(
                source="verification_engine",
                artifact_id=session_id,
                digest=verification_digest,
                session_id=session_id,
            ),
            metadata={"verified": verified},
        )

    def record_decision(self, bundle_id: str, plan_id: str, plan_digest: str) -> None:
        self.append_event(
            bundle_id,
            TimelineEventType.DECISION_GENERATED,
            source="decision_engine",
            evidence_digest=plan_digest,
            references=[plan_id],
        )

    def record_review(self, bundle_id: str, review_id: str, review_digest: str) -> None:
        self.append_event(
            bundle_id,
            TimelineEventType.REVIEW_APPROVED,
            source="decision_review",
            evidence_digest=review_digest,
            references=[review_id],
        )

    def record_validation(self, bundle_id: str, validation_id: str, validation_digest: str) -> None:
        self.append_event(
            bundle_id,
            TimelineEventType.VALIDATION_COMPLETED,
            source="decision_validation",
            evidence_digest=validation_digest,
            references=[validation_id],
        )

    def record_governance(self, bundle_id: str, version_id: str, registry_digest: str) -> None:
        self.append_event(
            bundle_id,
            TimelineEventType.GOVERNANCE_APPLIED,
            source="aci_governance",
            evidence_digest=registry_digest,
            references=[version_id],
        )

    def record_expansion(self, bundle_id: str, plan_id: str, plan_digest: str) -> None:
        self.append_event(
            bundle_id,
            TimelineEventType.EXPANSION_CANDIDATE_GENERATED,
            source="aci_expansion",
            evidence_digest=plan_digest,
            references=[plan_id],
        )

    def platform_health(self) -> PlatformHealthReport:
        """Evidence-backed platform health metrics with sample sizes."""
        limitations: List[str] = []
        metrics: List[PlatformHealthMetric] = []

        try:
            registry = compute_registry_metrics()
            cap_count = max(registry.capability_count, 1)
            api_count = max(registry.total_registry_apis, 1)
            native_cov = (registry.native_supported_capabilities / cap_count) * 100.0
            from alma_bridge.compatibility_intelligence.behavior_requirements import (
                list_behavior_profiles,
            )

            behaviors = list_behavior_profiles()
            behavior_count = max(len(behaviors), 1)
            metrics.extend(
                [
                    PlatformHealthMetric(
                        name="native_runtime_coverage_percent",
                        value=round(native_cov, 2),
                        sample_size=registry.capability_count,
                        unit="percent",
                        evidence_source="aci_registry",
                    ),
                    PlatformHealthMetric(
                        name="behavior_coverage_percent",
                        value=round(
                            (registry.native_supported_capabilities / behavior_count) * 100.0, 2
                        ),
                        sample_size=behavior_count,
                        unit="percent",
                        evidence_source="aci_registry",
                    ),
                    PlatformHealthMetric(
                        name="unknown_apis",
                        value=float(registry.total_registry_apis - registry.classified_apis),
                        sample_size=api_count,
                        unit="count",
                        evidence_source="aci_registry",
                    ),
                ]
            )
        except Exception:
            limitations.append("registry_metrics_unavailable")

        try:
            calibration = CalibrationService()
            cal_metrics = calibration.compute_metrics()
            authoritative = (
                cal_metrics.true_positive_count
                + cal_metrics.false_positive_count
                + cal_metrics.true_negative_count
                + cal_metrics.false_negative_count
            )
            precision = (
                cal_metrics.true_positive_count
                / max(cal_metrics.true_positive_count + cal_metrics.false_positive_count, 1)
            )
            recall = (
                cal_metrics.true_positive_count
                / max(cal_metrics.true_positive_count + cal_metrics.false_negative_count, 1)
            )
            accuracy = (
                (cal_metrics.true_positive_count + cal_metrics.true_negative_count)
                / max(authoritative, 1)
            )
            metrics.extend(
                [
                    PlatformHealthMetric(
                        name="prediction_precision",
                        value=round(precision, 4),
                        sample_size=authoritative,
                        unit="ratio",
                        evidence_source="aci_calibration",
                    ),
                    PlatformHealthMetric(
                        name="prediction_recall",
                        value=round(recall, 4),
                        sample_size=authoritative,
                        unit="ratio",
                        evidence_source="aci_calibration",
                    ),
                    PlatformHealthMetric(
                        name="calibration_accuracy",
                        value=round(accuracy, 4),
                        sample_size=authoritative,
                        unit="ratio",
                        evidence_source="aci_calibration",
                    ),
                ]
            )
        except Exception:
            limitations.append("calibration_metrics_unavailable")

        try:
            gov_repo = GovernanceRepository()
            proposals = gov_repo.list_proposals(limit=1000)
            metrics.append(
                PlatformHealthMetric(
                    name="governance_proposals",
                    value=float(len(proposals)),
                    sample_size=len(proposals),
                    unit="count",
                    evidence_source="aci_governance",
                )
            )
            version = gov_repo.get_current_version()
            stable_count = sum(
                1
                for entry in version.entries
                if entry.maturity_state.value in ("stable", "verified_bounded")
            )
            metrics.append(
                PlatformHealthMetric(
                    name="capability_maturity_stable_count",
                    value=float(stable_count),
                    sample_size=len(version.entries),
                    unit="count",
                    evidence_source="aci_governance",
                )
            )
        except Exception:
            limitations.append("governance_metrics_unavailable")

        try:
            expansion_repo = ExpansionPlanRepository()
            plan = expansion_repo.get_latest_plan()
            backlog = len(plan.candidates) if plan else 0
            metrics.append(
                PlatformHealthMetric(
                    name="expansion_backlog",
                    value=float(backlog),
                    sample_size=backlog,
                    unit="count",
                    evidence_source="aci_expansion",
                )
            )
        except Exception:
            limitations.append("expansion_metrics_unavailable")

        analysis_repo = AnalysisRepository()
        recent = analysis_repo.list_recent(limit=100)
        metrics.append(
            PlatformHealthMetric(
                name="analyzed_executables",
                value=float(len(recent)),
                sample_size=len(recent),
                unit="count",
                evidence_source="aci_analysis",
            )
        )

        bundle_count = len(self._repo.list_all_bundle_ids())
        metrics.append(
            PlatformHealthMetric(
                name="evidence_bundles",
                value=float(bundle_count),
                sample_size=bundle_count,
                unit="count",
                evidence_source="evidence_repository",
            )
        )

        return PlatformHealthReport(
            generated_at=utc_now_iso(),
            metrics=metrics,
            limitations=sorted(set(limitations)),
        )


def bundle_id_for_digest(binary_digest: str) -> str:
    return compute_event_id({"binary_digest": binary_digest, "kind": "bundle"})
