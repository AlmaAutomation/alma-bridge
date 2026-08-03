"""Deterministic digests for expansion plans and candidates."""

from __future__ import annotations

from alma_bridge.compatibility.profile_fingerprints import sha256_v1


def compute_candidate_id(
    provider_id: str,
    capability_id: str,
    behavior_id: str | None,
    implementation_scope: str,
) -> str:
    return sha256_v1(
        {
            "provider_id": provider_id,
            "capability_id": capability_id,
            "behavior_id": behavior_id or "",
            "implementation_scope": implementation_scope,
        }
    )


def compute_evidence_digest(evidence_payload: dict) -> str:
    return sha256_v1(evidence_payload)


def compute_plan_id(registry_version: str, evidence_digest: str) -> str:
    return sha256_v1(
        {
            "registry_version": registry_version,
            "evidence_digest": evidence_digest,
            "engine": "aci_expansion_v1",
        }
    )
