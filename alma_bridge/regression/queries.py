"""Stable deterministic helpers for regression comparison."""

from __future__ import annotations

from typing import Any, Dict, List, Set

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.intelligence.models import EvidenceBundle, EvidenceReference
from alma_bridge.knowledge.models import KnowledgeEvidenceReference
from alma_bridge.regression.models import REGRESSION_SCHEMA_VERSION, RegressionType


def build_regression_id(
    *,
    application_fingerprint: str,
    regression_type: RegressionType,
    subject: str,
) -> str:
    return sha256_v1(
        {
            "schema": REGRESSION_SCHEMA_VERSION,
            "application_fingerprint": application_fingerprint,
            "regression_type": regression_type.value,
            "subject": subject,
        }
    )


def session_sort_key(session: Dict[str, Any]) -> tuple[str, str]:
    return (str(session.get("started_at") or ""), str(session.get("session_id") or ""))


def sort_sessions(sessions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(sessions, key=session_sort_key)


def latest_session_id(sessions: List[Dict[str, Any]]) -> str:
    ordered = sort_sessions(sessions)
    if not ordered:
        raise ValueError("no sessions available")
    return str(ordered[-1]["session_id"])


def _artifact_belongs_to_session(artifact_key: str, session_id: str) -> bool:
    if artifact_key == "sessions":
        return False
    if ":" not in artifact_key:
        return False
    parts = artifact_key.split(":")
    if len(parts) < 2:
        return False
    return parts[1] == session_id


def filter_evidence_bundle(
    bundle: EvidenceBundle,
    *,
    include_session_ids: Set[str] | None = None,
    exclude_session_ids: Set[str] | None = None,
) -> EvidenceBundle:
    """Return a bundle subset filtered by session membership."""
    include = include_session_ids
    exclude = exclude_session_ids or set()

    session_records = bundle.artifacts.get("sessions") or []
    kept_sessions = []
    kept_ids: Set[str] = set()
    for session in session_records:
        session_id = str(session["session_id"])
        if session_id in exclude:
            continue
        if include is not None and session_id not in include:
            continue
        kept_sessions.append(session)
        kept_ids.add(session_id)

    filtered_artifacts: Dict[str, Any] = {"sessions": sort_sessions(kept_sessions)}
    for key, value in bundle.artifacts.items():
        if key == "sessions":
            continue
        owner_session = key.split(":")[1] if ":" in key else None
        if owner_session and owner_session not in kept_ids:
            continue
        filtered_artifacts[key] = value

    filtered_refs: List[EvidenceReference] = []
    for ref in bundle.references:
        session_id = _reference_session_id(ref)
        if session_id and session_id not in kept_ids:
            continue
        if ref.artifact_key != "session_record" and ref.artifact_key not in filtered_artifacts:
            continue
        filtered_refs.append(ref)

    return EvidenceBundle(
        session_id=bundle.session_id,
        application_fingerprint=bundle.application_fingerprint,
        file_path=bundle.file_path,
        references=filtered_refs,
        artifacts=filtered_artifacts,
        limitations=list(bundle.limitations),
    )


def _reference_session_id(ref: EvidenceReference) -> str | None:
    if ref.source_type.value == "session":
        return ref.source_id
    if ":" in ref.source_id:
        return ref.source_id.split(":")[0]
    return None


def union_evidence_references(
    *groups: List[KnowledgeEvidenceReference],
) -> List[KnowledgeEvidenceReference]:
    seen: set[tuple[str, str, str]] = set()
    merged: List[KnowledgeEvidenceReference] = []
    for group in groups:
        for ref in group:
            key = (ref.source_type, ref.source_id, ref.artifact_key)
            if key in seen:
                continue
            seen.add(key)
            merged.append(ref)
    return sorted(merged, key=lambda ref: (ref.source_type, ref.source_id, ref.artifact_key))
