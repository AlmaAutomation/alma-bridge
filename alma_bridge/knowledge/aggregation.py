"""Deterministic aggregation of persisted evidence into knowledge profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from alma_bridge.graph.queries import environment_identity, manifest_runtime_identity
from alma_bridge.intelligence.models import EvidenceBundle, EvidenceReference, EvidenceSourceType
from alma_bridge.knowledge.models import (
    AGGREGATION_ENGINE_VERSION,
    CompatibilityKnowledgeProfile,
    EvidenceClassification,
    KnowledgeConflict,
    KnowledgeEvidenceReference,
    MalformedKnowledgeEvidenceError,
    ObservedEnvironment,
    ObservedFramework,
    ObservedLaunchStrategy,
    ObservedRuntime,
    VerificationContractAggregate,
)
from alma_bridge.knowledge.queries import build_verification_contract_identity
from alma_bridge.session.stop_on_success_verification import aggregate_verification_passed


class KnowledgeAggregationEngine:
    """Aggregate cross-session evidence into a compatibility knowledge profile."""

    engine_version = AGGREGATION_ENGINE_VERSION

    def aggregate(self, bundle: EvidenceBundle) -> CompatibilityKnowledgeProfile:
        fingerprint = bundle.application_fingerprint
        if not fingerprint:
            raise MalformedKnowledgeEvidenceError(
                "application fingerprint required for knowledge aggregation"
            )

        sessions = bundle.artifacts.get("sessions") or []
        if not sessions:
            raise MalformedKnowledgeEvidenceError("evidence bundle contains no sessions")

        session_outcomes = self._classify_sessions(bundle)
        framework_stats = self._aggregate_frameworks(bundle, session_outcomes)
        strategy_stats = self._aggregate_strategies(bundle, session_outcomes)
        contract_stats = self._aggregate_verification_contracts(bundle)
        runtime_stats = self._aggregate_runtimes(bundle, session_outcomes)
        environment_stats = self._aggregate_environments(bundle, session_outcomes)
        conflicts = self._detect_conflicts(framework_stats)

        verified_successes = sum(
            1 for outcome in session_outcomes.values() if outcome == "verified_success"
        )
        verified_failures = sum(
            1 for outcome in session_outcomes.values() if outcome == "verified_failure"
        )
        unverifiable_sessions = sum(
            1 for outcome in session_outcomes.values() if outcome == "unverifiable"
        )

        distinct_frameworks = {item.framework for item in framework_stats}
        has_framework_conflict = len(distinct_frameworks) > 1
        observed_frameworks = [
            self._finalize_framework(item, has_framework_conflict)
            for item in framework_stats
        ]

        return CompatibilityKnowledgeProfile(
            application_fingerprint=fingerprint,
            application_name=self._application_name(bundle),
            total_sessions=len(sessions),
            verified_successes=verified_successes,
            verified_failures=verified_failures,
            unverifiable_sessions=unverifiable_sessions,
            observed_frameworks=observed_frameworks,
            observed_launch_strategies=strategy_stats,
            verification_contracts=contract_stats,
            observed_runtimes=runtime_stats,
            observed_environments=environment_stats,
            conflicts=conflicts,
        )

    def _classify_sessions(self, bundle: EvidenceBundle) -> Dict[str, str]:
        outcomes: Dict[str, str] = {}
        for session in bundle.artifacts.get("sessions") or []:
            session_id = str(session["session_id"])
            has_verified_success = False
            has_verified_failure = False
            has_verification = False

            for attempt in session.get("attempts") or []:
                attempt_number = int(attempt["attempt_number"])
                verification_key = f"verification:{session_id}:{attempt_number}"
                verification = bundle.artifacts.get(verification_key)
                if not verification:
                    continue
                has_verification = True
                if aggregate_verification_passed({"verification": verification}):
                    has_verified_success = True
                elif verification.get("passed") is False:
                    has_verified_failure = True

            if has_verified_success:
                outcomes[session_id] = "verified_success"
            elif has_verified_failure:
                outcomes[session_id] = "verified_failure"
            elif has_verification:
                outcomes[session_id] = "unverifiable"
            else:
                outcomes[session_id] = "unverifiable"
        return outcomes

    def _aggregate_frameworks(
        self,
        bundle: EvidenceBundle,
        session_outcomes: Dict[str, str],
    ) -> List[ObservedFramework]:
        buckets: Dict[str, Dict[str, Any]] = {}

        for ref in bundle.references:
            if ref.source_type != EvidenceSourceType.FRAMEWORK_DETECTION:
                continue
            artifact = bundle.artifacts.get(ref.artifact_key) or {}
            framework = str(artifact.get("framework") or "").strip().lower()
            if not framework:
                continue
            session_id = str(artifact.get("session_id") or ref.source_id.split(":")[0])
            bucket = buckets.setdefault(
                framework,
                {
                    "observation_count": 0,
                    "verified_session_ids": set(),
                    "confidence_total": 0.0,
                    "evidence_references": [],
                },
            )
            bucket["observation_count"] += 1
            bucket["confidence_total"] += float(artifact.get("confidence") or 0.0)
            if session_outcomes.get(session_id) == "verified_success":
                bucket["verified_session_ids"].add(session_id)
            bucket["evidence_references"].append(self._to_knowledge_ref(ref, artifact))

        results: List[ObservedFramework] = []
        for framework, bucket in sorted(buckets.items()):
            count = int(bucket["observation_count"])
            results.append(
                ObservedFramework(
                    framework=framework,
                    observation_count=count,
                    verified_session_count=len(bucket["verified_session_ids"]),
                    confidence=round(bucket["confidence_total"] / max(count, 1), 4),
                    evidence_references=bucket["evidence_references"],
                    classification=EvidenceClassification.OBSERVED,
                )
            )
        return results

    def _finalize_framework(
        self,
        item: ObservedFramework,
        has_framework_conflict: bool,
    ) -> ObservedFramework:
        if has_framework_conflict:
            classification = EvidenceClassification.CONFLICTING
        elif item.observation_count >= 2:
            classification = EvidenceClassification.REPEATED
        else:
            classification = EvidenceClassification.OBSERVED
        return item.model_copy(update={"classification": classification})

    def _aggregate_strategies(
        self,
        bundle: EvidenceBundle,
        session_outcomes: Dict[str, str],
    ) -> List[ObservedLaunchStrategy]:
        buckets: Dict[str, Dict[str, Any]] = {}

        for key, artifact in sorted(bundle.artifacts.items()):
            if not key.startswith("attempt:"):
                continue
            parts = key.split(":")
            if len(parts) != 3:
                continue
            session_id, attempt_number_str = parts[1], parts[2]
            attempt_number = int(attempt_number_str)
            strategy = str(artifact.get("strategy_id") or "").strip()
            if not strategy:
                continue

            bucket = buckets.setdefault(
                strategy,
                {
                    "attempts": 0,
                    "verified_successes": 0,
                    "verified_failures": 0,
                    "evidence_references": [],
                },
            )
            bucket["attempts"] += 1

            verification_key = f"verification:{session_id}:{attempt_number}"
            verification = bundle.artifacts.get(verification_key) or {}
            session_outcome = session_outcomes.get(session_id, "unverifiable")

            if aggregate_verification_passed({"verification": verification}):
                bucket["verified_successes"] += 1
            elif verification.get("passed") is False:
                bucket["verified_failures"] += 1
            elif session_outcome == "unverifiable":
                pass

            attempt_ref = next(
                (
                    ref
                    for ref in bundle.references
                    if ref.source_type == EvidenceSourceType.ATTEMPT
                    and ref.source_id == f"{session_id}:{attempt_number}"
                ),
                None,
            )
            if attempt_ref:
                bucket["evidence_references"].append(
                    self._to_knowledge_ref(attempt_ref, artifact)
                )

        results: List[ObservedLaunchStrategy] = []
        for strategy, bucket in sorted(buckets.items()):
            verified_total = bucket["verified_successes"] + bucket["verified_failures"]
            success_rate = (
                round(bucket["verified_successes"] / verified_total, 4)
                if verified_total
                else 0.0
            )
            results.append(
                ObservedLaunchStrategy(
                    strategy=strategy,
                    attempts=bucket["attempts"],
                    verified_successes=bucket["verified_successes"],
                    verified_failures=bucket["verified_failures"],
                    success_rate=success_rate,
                    evidence_references=bucket["evidence_references"],
                )
            )
        return results

    def _aggregate_verification_contracts(
        self,
        bundle: EvidenceBundle,
    ) -> List[VerificationContractAggregate]:
        buckets: Dict[str, Dict[str, Any]] = {}

        for key, verification in sorted(bundle.artifacts.items()):
            if not key.startswith("verification:"):
                continue
            if not isinstance(verification, dict):
                continue
            contract = build_verification_contract_identity(verification)
            bucket = buckets.setdefault(
                contract,
                {"passed_count": 0, "failed_count": 0, "evidence_references": []},
            )
            if aggregate_verification_passed({"verification": verification}):
                bucket["passed_count"] += 1
            elif verification.get("passed") is False:
                bucket["failed_count"] += 1

            parts = key.split(":")
            session_id = parts[1] if len(parts) == 3 else ""
            attempt_number = int(parts[2]) if len(parts) == 3 else 0
            ref = next(
                (
                    item
                    for item in bundle.references
                    if item.source_type == EvidenceSourceType.VERIFICATION
                    and item.source_id == f"{session_id}:{attempt_number}"
                ),
                None,
            )
            if ref:
                bucket["evidence_references"].append(self._to_knowledge_ref(ref, verification))

        return [
            VerificationContractAggregate(
                contract=contract,
                passed_count=bucket["passed_count"],
                failed_count=bucket["failed_count"],
                evidence_references=bucket["evidence_references"],
            )
            for contract, bucket in sorted(buckets.items())
        ]

    def _aggregate_runtimes(
        self,
        bundle: EvidenceBundle,
        session_outcomes: Dict[str, str],
    ) -> List[ObservedRuntime]:
        buckets: Dict[str, Dict[str, Any]] = {}

        for key, artifact in sorted(bundle.artifacts.items()):
            if not key.startswith("attempt:"):
                continue
            parts = key.split(":")
            if len(parts) != 3:
                continue
            session_id = parts[1]
            runtime = str(artifact.get("runtime") or "").strip().lower()
            if runtime:
                self._record_runtime_observation(
                    buckets,
                    runtime=runtime,
                    session_id=session_id,
                    session_outcomes=session_outcomes,
                    ref=self._attempt_ref(bundle, session_id, int(parts[2])),
                    artifact=artifact,
                    observation_kind="attempt_runtime",
                )

        for key, manifest in sorted(bundle.artifacts.items()):
            if not key.startswith("manifest_capture:"):
                continue
            parts = key.split(":")
            if len(parts) != 3:
                continue
            session_id = parts[1]
            attempt_number = int(parts[2])
            base_runtime = manifest.get("base_runtime") or {}
            runtime_kind = str(base_runtime.get("kind") or "").strip().lower()
            if not runtime_kind or runtime_kind == "unknown":
                continue
            runtime_identity = manifest_runtime_identity(manifest)
            ref = next(
                (
                    item
                    for item in bundle.references
                    if item.source_type == EvidenceSourceType.MANIFEST_CAPTURE
                    and item.source_id == f"{session_id}:{attempt_number}"
                ),
                None,
            )
            self._record_runtime_observation(
                buckets,
                runtime=runtime_identity,
                session_id=session_id,
                session_outcomes=session_outcomes,
                ref=ref,
                artifact={"runtime_observed": runtime_kind, **dict(base_runtime)},
                observation_kind="runtime_observed",
            )

        return [
            ObservedRuntime(
                runtime=runtime,
                observation_count=bucket["observation_count"],
                verified_success_observation_count=bucket["verified_success_observation_count"],
                evidence_references=bucket["evidence_references"],
            )
            for runtime, bucket in sorted(buckets.items())
        ]

    def _aggregate_environments(
        self,
        bundle: EvidenceBundle,
        session_outcomes: Dict[str, str],
    ) -> List[ObservedEnvironment]:
        buckets: Dict[str, Dict[str, Any]] = {}

        for key, environment in sorted(bundle.artifacts.items()):
            if not key.startswith("run_environment:"):
                continue
            if not isinstance(environment, dict):
                continue
            session_id = key.split(":", 1)[1]
            identity = environment_identity(environment)
            bucket = buckets.setdefault(
                identity,
                {
                    "summary": self._environment_summary(environment),
                    "observation_count": 0,
                    "verified_success_count": 0,
                    "verified_failure_count": 0,
                    "evidence_references": [],
                },
            )
            bucket["observation_count"] += 1
            outcome = session_outcomes.get(session_id, "unverifiable")
            if outcome == "verified_success":
                bucket["verified_success_count"] += 1
            elif outcome == "verified_failure":
                bucket["verified_failure_count"] += 1

            ref = next(
                (
                    item
                    for item in bundle.references
                    if item.source_type == EvidenceSourceType.RUN_ENVIRONMENT
                    and item.source_id == session_id
                ),
                None,
            )
            if ref:
                bucket["evidence_references"].append(self._to_knowledge_ref(ref, environment))

        return [
            ObservedEnvironment(
                environment_identity=identity,
                summary=bucket["summary"],
                observation_count=bucket["observation_count"],
                verified_success_count=bucket["verified_success_count"],
                verified_failure_count=bucket["verified_failure_count"],
                evidence_references=bucket["evidence_references"],
            )
            for identity, bucket in sorted(buckets.items())
        ]

    @staticmethod
    def _environment_summary(environment: Dict[str, Any]) -> str:
        parts: List[str] = []
        wine_version = environment.get("wine_version")
        if wine_version:
            parts.append(str(wine_version))
        host_os = environment.get("host_os")
        host_arch = environment.get("host_architecture")
        if host_os and host_arch:
            parts.append(f"{host_os}/{host_arch}")
        elif host_os:
            parts.append(str(host_os))
        prefix_id = environment.get("prefix_id")
        if prefix_id:
            parts.append(f"prefix:{str(prefix_id)[:12]}")
        return " | ".join(parts) if parts else "environment observed"

    def _record_runtime_observation(
        self,
        buckets: Dict[str, Dict[str, Any]],
        *,
        runtime: str,
        session_id: str,
        session_outcomes: Dict[str, str],
        ref: Optional[EvidenceReference],
        artifact: Dict[str, Any],
        observation_kind: str,
    ) -> None:
        bucket = buckets.setdefault(
            runtime,
            {
                "observation_count": 0,
                "verified_success_observation_count": 0,
                "evidence_references": [],
            },
        )
        bucket["observation_count"] += 1
        if session_outcomes.get(session_id) == "verified_success":
            bucket["verified_success_observation_count"] += 1
        if ref:
            knowledge_ref = self._to_knowledge_ref(ref, artifact)
            knowledge_ref.excerpt = observation_kind
            bucket["evidence_references"].append(knowledge_ref)

    def _detect_conflicts(
        self,
        framework_stats: List[ObservedFramework],
    ) -> List[KnowledgeConflict]:
        if len(framework_stats) <= 1:
            return []

        evidence_by_side = {
            item.framework: item.evidence_references for item in framework_stats
        }
        return [
            KnowledgeConflict(
                relationship="detected_framework",
                conflict_type="competing_framework_observations",
                competing_observations=[item.framework for item in framework_stats],
                evidence_by_side=evidence_by_side,
            )
        ]

    @staticmethod
    def _attempt_ref(
        bundle: EvidenceBundle,
        session_id: str,
        attempt_number: int,
    ) -> Optional[EvidenceReference]:
        return next(
            (
                ref
                for ref in bundle.references
                if ref.source_type == EvidenceSourceType.ATTEMPT
                and ref.source_id == f"{session_id}:{attempt_number}"
            ),
            None,
        )

    @staticmethod
    def _to_knowledge_ref(
        ref: EvidenceReference,
        artifact: Dict[str, Any],
    ) -> KnowledgeEvidenceReference:
        session_id: Optional[str] = None
        attempt_id: Optional[int] = None
        if ref.source_type == EvidenceSourceType.ATTEMPT:
            parts = ref.source_id.split(":")
            if len(parts) == 2:
                session_id, attempt_id = parts[0], int(parts[1])
        elif ref.source_type in (
            EvidenceSourceType.VERIFICATION,
            EvidenceSourceType.FRAMEWORK_DETECTION,
            EvidenceSourceType.MANIFEST_CAPTURE,
            EvidenceSourceType.RUN_ENVIRONMENT,
        ):
            parts = ref.source_id.split(":")
            if len(parts) == 2:
                session_id, attempt_id = parts[0], int(parts[1])
        elif ref.source_type == EvidenceSourceType.SESSION:
            session_id = ref.source_id
        elif ref.source_type == EvidenceSourceType.RUN_ENVIRONMENT:
            session_id = ref.source_id

        excerpt = ref.excerpt
        if not excerpt and artifact.get("framework"):
            excerpt = str(artifact.get("framework"))

        return KnowledgeEvidenceReference(
            source_type=ref.source_type.value,
            source_id=ref.source_id,
            artifact_key=ref.artifact_key,
            session_id=session_id or artifact.get("session_id"),
            attempt_id=attempt_id or artifact.get("attempt_number"),
            captured_at=ref.captured_at,
            excerpt=excerpt,
        )

    @staticmethod
    def _application_name(bundle: EvidenceBundle) -> str:
        if bundle.file_path:
            return Path(bundle.file_path).name
        for session in bundle.artifacts.get("sessions") or []:
            file_path = session.get("file_path")
            if file_path:
                return Path(str(file_path)).name
        return bundle.application_fingerprint or "unknown"
