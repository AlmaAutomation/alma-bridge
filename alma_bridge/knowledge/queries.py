"""Stable deterministic helpers for knowledge aggregation."""

from __future__ import annotations

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.knowledge.models import KNOWLEDGE_SCHEMA_VERSION


def build_profile_id(*, application_fingerprint: str) -> str:
    return sha256_v1(
        {
            "schema": KNOWLEDGE_SCHEMA_VERSION,
            "application_fingerprint": application_fingerprint,
        }
    )


def build_verification_contract_identity(verification: dict) -> str:
    policy = verification.get("success_policy") or {}
    policy_id = str(policy.get("policy_id") or "unknown")
    policy_version = str(policy.get("policy_version") or "unknown")
    required_checks = policy.get("required_checks") or {}
    flat_checks: list[str] = []
    if isinstance(required_checks, dict):
        for check_kind, values in sorted(required_checks.items()):
            for value in values or []:
                flat_checks.append(f"{check_kind}:{value}")
    elif isinstance(required_checks, list):
        flat_checks = [str(item) for item in required_checks]
    return f"{policy_id}:{policy_version}:{','.join(sorted(flat_checks))}"


def build_conflict_id(*, relationship: str, conflict_type: str, sides: list[str]) -> str:
    return sha256_v1(
        {
            "schema": KNOWLEDGE_SCHEMA_VERSION,
            "relationship": relationship,
            "conflict_type": conflict_type,
            "sides": sorted(sides),
        }
    )
