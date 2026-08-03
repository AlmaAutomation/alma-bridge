"""Extract comparable session snapshots from evidence bundles."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from alma_bridge.compatibility.run_environment import environment_from_dict
from alma_bridge.graph.queries import manifest_runtime_identity
from alma_bridge.intelligence.models import EvidenceBundle, EvidenceReference, EvidenceSourceType
from alma_bridge.knowledge.aggregation import KnowledgeAggregationEngine
from alma_bridge.knowledge.models import KnowledgeEvidenceReference, MalformedKnowledgeEvidenceError
from alma_bridge.knowledge.queries import build_verification_contract_identity
from alma_bridge.session.stop_on_success_verification import aggregate_verification_passed


@dataclass
class SessionEvidenceSnapshot:
    session_id: str
    application_fingerprint: str
    application_name: str
    alma_bridge_version: Optional[str] = None
    host_os: Optional[str] = None
    kernel_version: Optional[str] = None
    host_architecture: Optional[str] = None
    wine_version: Optional[str] = None
    wine_architecture: Optional[str] = None
    prefix_id: Optional[str] = None
    prefix_schema_version: Optional[str] = None
    launch_strategy: Optional[str] = None
    strategy_version: Optional[str] = None
    authoritative_outcome: Optional[str] = None
    verification_contract_identity: Optional[str] = None
    verification_policy_version: Optional[str] = None
    detected_frameworks: List[str] = field(default_factory=list)
    runtime_observations: Dict[str, str] = field(default_factory=dict)
    evidence_by_field: Dict[str, List[KnowledgeEvidenceReference]] = field(default_factory=dict)


def build_session_evidence_snapshot(
    bundle: EvidenceBundle,
    *,
    session_id: str,
) -> SessionEvidenceSnapshot:
    sessions = bundle.artifacts.get("sessions") or []
    session = next(
        (item for item in sessions if str(item.get("session_id")) == session_id),
        None,
    )
    if not session:
        raise MalformedKnowledgeEvidenceError(f"session {session_id} missing from evidence bundle")

    fingerprint = str(session.get("file_hash") or bundle.application_fingerprint or "")
    if not fingerprint:
        raise MalformedKnowledgeEvidenceError(f"session {session_id} has no application fingerprint")

    snapshot = SessionEvidenceSnapshot(
        session_id=session_id,
        application_fingerprint=fingerprint,
        application_name=_application_name(bundle, session),
    )
    _apply_environment(snapshot, bundle, session_id)
    _apply_execution(snapshot, bundle, session)
    _apply_verification(snapshot, bundle, session)
    _apply_frameworks(snapshot, bundle, session_id)
    _apply_runtimes(snapshot, bundle, session_id)
    return snapshot


def _application_name(bundle: EvidenceBundle, session: Dict[str, Any]) -> str:
    file_path = session.get("file_path") or bundle.file_path
    if file_path:
        return Path(str(file_path)).name
    return str(session.get("file_hash") or "unknown")


def _apply_environment(
    snapshot: SessionEvidenceSnapshot,
    bundle: EvidenceBundle,
    session_id: str,
) -> None:
    env_key = f"run_environment:{session_id}"
    env_payload = bundle.artifacts.get(env_key)
    if not env_payload:
        return
    environment = environment_from_dict(env_payload)
    if not environment:
        return
    snapshot.alma_bridge_version = environment.alma_bridge_version
    snapshot.host_os = environment.host_os
    snapshot.kernel_version = environment.kernel_version
    snapshot.host_architecture = environment.host_architecture
    snapshot.wine_version = environment.wine_version
    snapshot.wine_architecture = environment.wine_architecture
    snapshot.prefix_id = environment.prefix_id
    snapshot.prefix_schema_version = environment.prefix_schema_version
    refs = _refs_for_artifact(bundle, EvidenceSourceType.RUN_ENVIRONMENT, session_id)
    for field_name in (
        "alma_bridge_version",
        "host_os",
        "kernel_version",
        "host_architecture",
        "wine_version",
        "wine_architecture",
        "prefix_id",
        "prefix_schema_version",
    ):
        snapshot.evidence_by_field[field_name] = refs


def _apply_execution(
    snapshot: SessionEvidenceSnapshot,
    bundle: EvidenceBundle,
    session: Dict[str, Any],
) -> None:
    attempts = session.get("attempts") or []
    if not attempts:
        return
    winning = next((item for item in attempts if item.get("success")), attempts[-1])
    attempt_number = int(winning.get("attempt_number") or 1)
    snapshot.launch_strategy = str(
        winning.get("phase") or winning.get("strategy_id") or ""
    ).strip() or None
    env_key = f"run_environment:{snapshot.session_id}"
    env_payload = bundle.artifacts.get(env_key) or {}
    snapshot.strategy_version = str(
        env_payload.get("execution_strategy_version") or snapshot.launch_strategy or ""
    ).strip() or None
    refs = _refs_for_artifact(
        bundle,
        EvidenceSourceType.ATTEMPT,
        f"{snapshot.session_id}:{attempt_number}",
    )
    snapshot.evidence_by_field["launch_strategy"] = refs
    snapshot.evidence_by_field["strategy_version"] = refs


def _apply_verification(
    snapshot: SessionEvidenceSnapshot,
    bundle: EvidenceBundle,
    session: Dict[str, Any],
) -> None:
    attempts = session.get("attempts") or []
    verification: Optional[Dict[str, Any]] = None
    verification_refs: List[KnowledgeEvidenceReference] = []
    for attempt in attempts:
        attempt_number = int(attempt.get("attempt_number") or 0)
        verification_key = f"verification:{snapshot.session_id}:{attempt_number}"
        candidate = bundle.artifacts.get(verification_key)
        if not isinstance(candidate, dict):
            continue
        verification = candidate
        verification_refs = _refs_for_artifact(
            bundle,
            EvidenceSourceType.VERIFICATION,
            f"{snapshot.session_id}:{attempt_number}",
        )
        if aggregate_verification_passed({"verification": candidate}):
            break
        if candidate.get("passed") is False:
            break

    if not verification:
        snapshot.authoritative_outcome = "unverifiable"
        return

    if aggregate_verification_passed({"verification": verification}):
        snapshot.authoritative_outcome = "verified_success"
    elif verification.get("passed") is False:
        snapshot.authoritative_outcome = "verified_failure"
    else:
        snapshot.authoritative_outcome = "unverifiable"

    snapshot.verification_contract_identity = build_verification_contract_identity(verification)
    policy = verification.get("success_policy") or {}
    snapshot.verification_policy_version = str(policy.get("policy_version") or "").strip() or None
    snapshot.evidence_by_field["authoritative_outcome"] = verification_refs
    snapshot.evidence_by_field["verification_contract_identity"] = verification_refs
    snapshot.evidence_by_field["verification_policy_version"] = verification_refs


def _apply_frameworks(
    snapshot: SessionEvidenceSnapshot,
    bundle: EvidenceBundle,
    session_id: str,
) -> None:
    frameworks: Set[str] = set()
    refs: List[KnowledgeEvidenceReference] = []
    for key, artifact in sorted(bundle.artifacts.items()):
        if not key.startswith("framework_detection:"):
            continue
        parts = key.split(":")
        if len(parts) != 3 or parts[1] != session_id:
            continue
        framework = str(artifact.get("framework") or "").strip().lower()
        if framework:
            frameworks.add(framework)
        attempt_number = int(parts[2])
        refs.extend(
            _refs_for_artifact(
                bundle,
                EvidenceSourceType.FRAMEWORK_DETECTION,
                f"{session_id}:{attempt_number}",
            )
        )
    snapshot.detected_frameworks = sorted(frameworks)
    snapshot.evidence_by_field["detected_frameworks"] = _dedupe_refs(refs)


def _apply_runtimes(
    snapshot: SessionEvidenceSnapshot,
    bundle: EvidenceBundle,
    session_id: str,
) -> None:
    observations: Dict[str, str] = {}
    refs_by_runtime: Dict[str, List[KnowledgeEvidenceReference]] = {}

    for key, artifact in sorted(bundle.artifacts.items()):
        if not key.startswith("attempt:"):
            continue
        parts = key.split(":")
        if len(parts) != 3 or parts[1] != session_id:
            continue
        runtime = str(artifact.get("runtime") or "").strip().lower()
        if not runtime:
            continue
        label = runtime
        observations[label] = "observed"
        attempt_number = int(parts[2])
        refs_by_runtime.setdefault(label, []).extend(
            _refs_for_artifact(
                bundle,
                EvidenceSourceType.ATTEMPT,
                f"{session_id}:{attempt_number}",
            )
        )

    for key, manifest in sorted(bundle.artifacts.items()):
        if not key.startswith("manifest_capture:"):
            continue
        parts = key.split(":")
        if len(parts) != 3 or parts[1] != session_id:
            continue
        runtime_identity = manifest_runtime_identity(manifest)
        if not runtime_identity:
            continue
        observations[runtime_identity] = "observed"
        attempt_number = int(parts[2])
        refs_by_runtime.setdefault(runtime_identity, []).extend(
            _refs_for_artifact(
                bundle,
                EvidenceSourceType.MANIFEST_CAPTURE,
                f"{session_id}:{attempt_number}",
            )
        )

    snapshot.runtime_observations = dict(sorted(observations.items()))
    for runtime, refs in refs_by_runtime.items():
        snapshot.evidence_by_field[f"runtime:{runtime}"] = _dedupe_refs(refs)


def _refs_for_artifact(
    bundle: EvidenceBundle,
    source_type: EvidenceSourceType,
    source_id: str,
) -> List[KnowledgeEvidenceReference]:
    refs: List[KnowledgeEvidenceReference] = []
    engine = KnowledgeAggregationEngine()
    for ref in bundle.references:
        if ref.source_type != source_type or ref.source_id != source_id:
            continue
        artifact = bundle.artifacts.get(ref.artifact_key) or {}
        refs.append(engine._to_knowledge_ref(ref, artifact))  # noqa: SLF001
    return _dedupe_refs(refs)


def _dedupe_refs(
    refs: List[KnowledgeEvidenceReference],
) -> List[KnowledgeEvidenceReference]:
    seen: set[tuple[str, str, str]] = set()
    merged: List[KnowledgeEvidenceReference] = []
    for ref in refs:
        key = (ref.source_type, ref.source_id, ref.artifact_key)
        if key in seen:
            continue
        seen.add(key)
        merged.append(ref)
    return sorted(merged, key=lambda ref: (ref.source_type, ref.source_id, ref.artifact_key))
