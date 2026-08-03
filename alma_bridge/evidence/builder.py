"""Assemble CompatibilityEvidenceBundle from subsystem artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.compatibility_intelligence.calibration_repository import CalibrationRepository
from alma_bridge.compatibility_intelligence.expansion.repository import ExpansionPlanRepository
from alma_bridge.compatibility_intelligence.governance.repository import GovernanceRepository
from alma_bridge.compatibility_intelligence.repository import AnalysisRepository
from alma_bridge.compatibility_intelligence.models import ACI_SCHEMA_VERSION
from alma_bridge.decision.service import DecisionService
from alma_bridge.evidence.digest import compute_bundle_digest
from alma_bridge.evidence.models import (
    EVIDENCE_ENGINE_VERSION,
    EVIDENCE_SCHEMA_VERSION,
    CompatibilityEvidenceBundle,
    Provenance,
    SectionReference,
    utc_now_iso,
)
from alma_bridge.intelligence.evidence import EvidenceBundleBuilder
from alma_bridge.intelligence.repository import OutcomesStoreAdapter


class CompatibilityEvidenceBundleBuilder:
    """Aggregate references from existing repositories — no duplication."""

    def __init__(
        self,
        *,
        analysis_repo: Optional[AnalysisRepository] = None,
        calibration_repo: Optional[CalibrationRepository] = None,
        governance_repo: Optional[GovernanceRepository] = None,
        expansion_repo: Optional[ExpansionPlanRepository] = None,
        session_repo: Optional[OutcomesStoreAdapter] = None,
        decision_service: Optional[DecisionService] = None,
    ) -> None:
        self._analysis = analysis_repo or AnalysisRepository()
        self._calibration = calibration_repo or CalibrationRepository()
        self._governance = governance_repo or GovernanceRepository()
        self._expansion = expansion_repo or ExpansionPlanRepository()
        self._sessions = session_repo or OutcomesStoreAdapter()
        self._session_builder = EvidenceBundleBuilder(self._sessions)
        self._decision = decision_service or DecisionService()

    def build_for_binary(
        self,
        binary_digest: str,
        *,
        file_path: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> CompatibilityEvidenceBundle:
        limitations: List[str] = []
        now = utc_now_iso()
        analysis = self._analysis.get_by_digest(binary_digest)
        application_name = ""
        application_fingerprint = binary_digest

        if analysis is not None:
            application_name = Path(analysis.file_path).name if analysis.file_path else ""
            application_fingerprint = analysis.binary_digest

        executable = SectionReference(
            section="executable",
            artifact_id=binary_digest,
            digest=binary_digest,
            provenance=Provenance(
                source="pe_analyzer",
                artifact_id=binary_digest,
                digest=binary_digest,
            ),
        )

        static_analysis = self._section_from_analysis(analysis, "static_analysis") if analysis else None
        capability_graph = self._section_from_analysis(analysis, "capability_graph") if analysis else None
        coverage = self._section_from_analysis(analysis, "coverage") if analysis else None
        prediction = self._section_from_analysis(analysis, "prediction") if analysis else None

        prediction_snapshot = None
        if session_id:
            snapshot = self._calibration.get_snapshot_by_session(session_id)
            if snapshot is not None:
                prediction_snapshot = SectionReference(
                    section="prediction_snapshot",
                    artifact_id=snapshot.snapshot_id,
                    digest=snapshot.snapshot_id,
                    provenance=Provenance(
                        source="aci_calibration",
                        artifact_id=snapshot.snapshot_id,
                        digest=snapshot.snapshot_id,
                        session_id=session_id,
                    ),
                    schema_version=snapshot.schema_version,
                )

        execution = None
        runtime_provider = None
        verification = None
        if session_id:
            try:
                session_bundle = self._session_builder.for_session(session_id)
                for ref in session_bundle.references:
                    if ref.source_type.value == "verification":
                        verification = SectionReference(
                            section="verification",
                            artifact_id=ref.source_id,
                            digest=ref.artifact_key,
                            provenance=Provenance(
                                source="verification_engine",
                                artifact_id=ref.source_id,
                                digest=ref.artifact_key,
                                session_id=session_id,
                                captured_at=ref.captured_at,
                            ),
                        )
                    elif ref.source_type.value == "attempt":
                        execution = SectionReference(
                            section="execution",
                            artifact_id=ref.source_id,
                            digest=ref.artifact_key,
                            provenance=Provenance(
                                source="bridge_orchestrator",
                                artifact_id=ref.source_id,
                                digest=ref.artifact_key,
                                session_id=session_id,
                                captured_at=ref.captured_at,
                            ),
                        )
                run_env = session_bundle.artifacts.get(f"run_environment:{session_id}")
                if run_env and isinstance(run_env, dict):
                    provider_id = run_env.get("runtime_provider_id") or run_env.get("provider_id") or ""
                    if provider_id:
                        runtime_provider = SectionReference(
                            section="runtime_provider",
                            artifact_id=provider_id,
                            digest=sha256_v1({"provider_id": provider_id, "session_id": session_id}),
                            provenance=Provenance(
                                source="runtime_provider",
                                artifact_id=provider_id,
                                digest=provider_id,
                                session_id=session_id,
                            ),
                        )
            except Exception:
                limitations.append("session_evidence_unavailable")

        knowledge = self._optional_section(
            "knowledge",
            f"knowledge:{application_fingerprint}",
            application_fingerprint,
            "knowledge_aggregation",
        )
        regression = self._optional_section(
            "regression",
            f"regression:{application_fingerprint}",
            application_fingerprint,
            "regression_diff",
        )
        advisor = self._optional_section(
            "advisor",
            f"advisor:{application_fingerprint}",
            application_fingerprint,
            "advisor_service",
        )

        decision = None
        review = None
        validation = None
        try:
            plan = self._decision.plan_for_application(application_fingerprint, session_id=session_id)
            plan_digest = sha256_v1({"plan_id": plan.plan_id, "fingerprint": application_fingerprint})
            decision = SectionReference(
                section="decision",
                artifact_id=plan.plan_id,
                digest=plan_digest,
                provenance=Provenance(
                    source="decision_engine",
                    artifact_id=plan.plan_id,
                    digest=plan_digest,
                    session_id=session_id,
                ),
            )
        except Exception:
            limitations.append("decision_plan_unavailable")

        governance = self._governance_section()
        expansion = self._expansion_section()

        if analysis is None:
            limitations.append("static_analysis_not_found")
        if not session_id:
            limitations.append("no_session_context")

        bundle_id = sha256_v1(
            {
                "binary_digest": binary_digest,
                "schema": EVIDENCE_SCHEMA_VERSION,
            }
        )

        bundle = CompatibilityEvidenceBundle(
            bundle_id=bundle_id,
            binary_digest=binary_digest,
            application_fingerprint=application_fingerprint,
            application_name=application_name,
            created_at=now,
            updated_at=now,
            bundle_digest="",
            executable=executable,
            static_analysis=static_analysis,
            capability_graph=capability_graph,
            coverage=coverage,
            prediction=prediction,
            prediction_snapshot=prediction_snapshot,
            execution=execution,
            runtime_provider=runtime_provider,
            verification=verification,
            knowledge=knowledge,
            regression=regression,
            advisor=advisor,
            decision=decision,
            review=review,
            validation=validation,
            governance=governance,
            expansion=expansion,
            limitations=sorted(set(limitations)),
            engine_version=EVIDENCE_ENGINE_VERSION,
        )
        bundle = bundle.model_copy(update={"bundle_digest": compute_bundle_digest(bundle)})
        return bundle

    def build_for_file(self, file_path: str, *, session_id: Optional[str] = None) -> CompatibilityEvidenceBundle:
        from alma_bridge.compatibility_intelligence.analyzer import analyze_pe

        _, _, digest = analyze_pe(file_path)
        return self.build_for_binary(digest, file_path=file_path, session_id=session_id)

    def _section_from_analysis(self, analysis: Any, section: str) -> SectionReference:
        section_digest = sha256_v1(
            {
                "analysis_id": analysis.analysis_id,
                "section": section,
                "binary_digest": analysis.binary_digest,
            }
        )
        return SectionReference(
            section=section,
            artifact_id=analysis.analysis_id,
            digest=section_digest,
            provenance=Provenance(
                source="aci_service",
                artifact_id=analysis.analysis_id,
                digest=analysis.binary_digest,
                detail=section,
            ),
            schema_version=ACI_SCHEMA_VERSION,
        )

    def _optional_section(
        self,
        section: str,
        artifact_id: str,
        digest_key: str,
        source: str,
    ) -> SectionReference:
        digest = sha256_v1({section: digest_key})
        return SectionReference(
            section=section,
            artifact_id=artifact_id,
            digest=digest,
            provenance=Provenance(source=source, artifact_id=artifact_id, digest=digest),
        )

    def _governance_section(self) -> Optional[SectionReference]:
        try:
            version = self._governance.get_current_version()
            if version is None:
                return None
            return SectionReference(
                section="governance",
                artifact_id=version.version_id,
                digest=version.digest,
                provenance=Provenance(
                    source="aci_governance",
                    artifact_id=version.version_id,
                    digest=version.digest,
                ),
            )
        except Exception:
            return None

    def _expansion_section(self) -> Optional[SectionReference]:
        try:
            plan = self._expansion.get_latest_plan()
            if plan is None:
                return None
            return SectionReference(
                section="expansion",
                artifact_id=plan.plan_id,
                digest=plan.plan_digest,
                provenance=Provenance(
                    source="aci_expansion",
                    artifact_id=plan.plan_id,
                    digest=plan.plan_digest,
                ),
            )
        except Exception:
            return None
