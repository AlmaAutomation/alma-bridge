from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

CANDIDATE_SCHEMA_VERSION = "profile_candidate_v1"


@dataclass(frozen=True)
class ProfileCandidateSnapshot:
    """Immutable source material captured before session SUCCEEDED."""

    candidate_id: str
    source_session_id: str
    source_attempt_number: int
    program_identity_payload: Dict[str, Any]
    program_identity_key: str
    host_compatibility_class_payload: Dict[str, Any]
    host_compatibility_class_id: str
    bridge_family_key: str
    bridge_family_payload: Dict[str, Any]
    bridge_manifest: Dict[str, Any]
    bridge_manifest_hash: str
    verification_binding_payload: Dict[str, Any]
    verification_binding_key: str
    verification_payload: Dict[str, Any]
    artifact_provenance: List[Dict[str, Any]] = field(default_factory=list)
    strategy_id: str = ""
    strategy_version: str = "1"
    remediation_protocol: List[Dict[str, str]] = field(default_factory=list)
    trust_source: str = "locally_verified"
    candidate_schema_version: str = CANDIDATE_SCHEMA_VERSION
    profile_lineage_key: str = ""
    idempotency_key: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "source_session_id": self.source_session_id,
            "source_attempt_number": self.source_attempt_number,
            "program_identity_payload": self.program_identity_payload,
            "program_identity_key": self.program_identity_key,
            "host_compatibility_class_payload": self.host_compatibility_class_payload,
            "host_compatibility_class_id": self.host_compatibility_class_id,
            "bridge_family_key": self.bridge_family_key,
            "bridge_family_payload": self.bridge_family_payload,
            "bridge_manifest": self.bridge_manifest,
            "bridge_manifest_hash": self.bridge_manifest_hash,
            "verification_binding_payload": self.verification_binding_payload,
            "verification_binding_key": self.verification_binding_key,
            "verification_payload": self.verification_payload,
            "artifact_provenance": self.artifact_provenance,
            "strategy_id": self.strategy_id,
            "strategy_version": self.strategy_version,
            "remediation_protocol": self.remediation_protocol,
            "trust_source": self.trust_source,
            "candidate_schema_version": self.candidate_schema_version,
            "profile_lineage_key": self.profile_lineage_key,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> ProfileCandidateSnapshot:
        return cls(
            candidate_id=str(data["candidate_id"]),
            source_session_id=str(data["source_session_id"]),
            source_attempt_number=int(data["source_attempt_number"]),
            program_identity_payload=dict(data["program_identity_payload"]),
            program_identity_key=str(data["program_identity_key"]),
            host_compatibility_class_payload=dict(data["host_compatibility_class_payload"]),
            host_compatibility_class_id=str(data["host_compatibility_class_id"]),
            bridge_family_key=str(data["bridge_family_key"]),
            bridge_family_payload=dict(data.get("bridge_family_payload") or {}),
            bridge_manifest=dict(data["bridge_manifest"]),
            bridge_manifest_hash=str(data["bridge_manifest_hash"]),
            verification_binding_payload=dict(data["verification_binding_payload"]),
            verification_binding_key=str(data["verification_binding_key"]),
            verification_payload=dict(data["verification_payload"]),
            artifact_provenance=list(data.get("artifact_provenance") or []),
            strategy_id=str(data.get("strategy_id") or ""),
            strategy_version=str(data.get("strategy_version") or "1"),
            remediation_protocol=list(data.get("remediation_protocol") or []),
            trust_source=str(data.get("trust_source") or "locally_verified"),
            candidate_schema_version=str(
                data.get("candidate_schema_version") or CANDIDATE_SCHEMA_VERSION
            ),
            profile_lineage_key=str(data.get("profile_lineage_key") or ""),
            idempotency_key=str(data.get("idempotency_key") or ""),
            created_at=str(data.get("created_at") or datetime.now(timezone.utc).isoformat()),
        )


def new_candidate_id() -> str:
    return str(uuid4())
