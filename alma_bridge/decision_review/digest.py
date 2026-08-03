"""Deterministic plan digest for approval binding."""

from __future__ import annotations

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.decision.models import DecisionPlan


def plan_version_for(plan: DecisionPlan) -> str:
    return plan.schema_version


def canonical_plan_payload(plan: DecisionPlan) -> dict:
    payload = plan.model_dump(mode="json")
    payload.pop("generated_at", None)
    return payload


def compute_plan_digest(plan: DecisionPlan) -> str:
    digest = sha256_v1(canonical_plan_payload(plan))
    return f"sha256:{digest}"
