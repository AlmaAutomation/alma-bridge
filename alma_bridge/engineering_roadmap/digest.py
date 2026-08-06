"""Deterministic digests for engineering roadmap opportunities and reports."""

from __future__ import annotations

from typing import Any, List, Mapping, Optional, TYPE_CHECKING

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.runtime_intelligence.models import BehaviorFamilyId, CorpusKind

from alma_bridge.engineering_roadmap.models import (
    ENGINEERING_ROADMAP_FORMULA_VERSION,
    ENGINEERING_ROADMAP_SCHEMA_VERSION,
    EngineeringRoadmapOpportunity,
    RoadmapOpportunityStatus,
)

if TYPE_CHECKING:
    from alma_bridge.engineering_roadmap.models import EngineeringRoadmapReport


def _dedupe_sorted(values: List[str]) -> List[str]:
    return sorted(set(values))


def compute_opportunity_id(
    *,
    corpus: CorpusKind,
    provider_id: str,
    family_id: BehaviorFamilyId,
    capability_id: str,
    behavior_id: Optional[str],
    bounded_scope: str,
    evidence_snapshot_digest: str,
) -> str:
    return sha256_v1(
        {
            "corpus": corpus.value,
            "provider_id": provider_id,
            "family_id": family_id.value,
            "capability_id": capability_id,
            "behavior_id": behavior_id or "",
            "bounded_scope": bounded_scope,
            "evidence_snapshot_digest": evidence_snapshot_digest,
        }
    )


def _complexity_payload(complexity: Any) -> Mapping[str, Any]:
    return {
        "level": complexity.level.value,
        "score": complexity.score,
        "factors": _dedupe_sorted(list(complexity.factors)),
    }


def _security_payload(risk: Any) -> Mapping[str, Any]:
    return {
        "categories": _dedupe_sorted([category.value for category in risk.categories]),
        "score": risk.score,
        "explanations": dict(sorted(risk.explanations.items())),
    }


def _semantic_payload(risk: Any) -> Mapping[str, Any]:
    return {
        "categories": _dedupe_sorted([category.value for category in risk.categories]),
        "score": risk.score,
        "explanations": dict(sorted(risk.explanations.items())),
    }


def compute_opportunity_digest(opportunity: EngineeringRoadmapOpportunity) -> str:
    """Hash semantic opportunity fields; excludes opportunity_id and digest."""
    payload: Mapping[str, Any] = {
        "corpus": opportunity.corpus.value,
        "provider_id": opportunity.provider_id,
        "family_id": opportunity.family_id.value,
        "capability_id": opportunity.capability_id,
        "behavior_id": opportunity.behavior_id or "",
        "bounded_scope": opportunity.bounded_scope,
        "title": opportunity.title,
        "summary": opportunity.summary,
        "distinct_applications_blocked": opportunity.distinct_applications_blocked,
        "distinct_binaries_blocked": opportunity.distinct_binaries_blocked,
        "application_classes_blocked": _dedupe_sorted(opportunity.application_classes_blocked),
        "blocked_session_count": opportunity.blocked_session_count,
        "application_mentions": opportunity.application_mentions,
        "predicted_applications_unlocked": opportunity.predicted_applications_unlocked,
        "predicted_application_classes_unlocked": opportunity.predicted_application_classes_unlocked,
        "predicted_unlock_disclaimer": opportunity.predicted_unlock_disclaimer,
        "engineering_complexity": _complexity_payload(opportunity.engineering_complexity),
        "implementation_risk": opportunity.implementation_risk,
        "security_risk": _security_payload(opportunity.security_risk),
        "semantic_risk": _semantic_payload(opportunity.semantic_risk),
        "maintenance_cost": opportunity.maintenance_cost or "",
        "fixture_availability": opportunity.fixture_availability,
        "verification_readiness": opportunity.verification_readiness,
        "evidence_quality": opportunity.evidence_quality.value,
        "engineering_confidence": opportunity.engineering_confidence.value,
        "engineering_confidence_factors": _dedupe_sorted(opportunity.engineering_confidence_factors),
        "existing_expansion_score": opportunity.existing_expansion_score,
        "compatibility_impact_score": opportunity.compatibility_impact_score,
        "opportunity_status": opportunity.opportunity_status.value,
        "prerequisites": _dedupe_sorted(opportunity.prerequisites),
        "prerequisite_opportunity_ids": _dedupe_sorted(opportunity.prerequisite_opportunity_ids),
        "known_limitations": _dedupe_sorted(opportunity.known_limitations),
        "affected_application_fingerprints": _dedupe_sorted(opportunity.affected_application_fingerprints),
        "affected_binary_digests": _dedupe_sorted(opportunity.affected_binary_digests),
        "source_debt_item_ids": _dedupe_sorted(opportunity.source_debt_item_ids),
        "source_expansion_candidate_ids": _dedupe_sorted(opportunity.source_expansion_candidate_ids),
        "existing_work_item_ids": _dedupe_sorted(opportunity.existing_work_item_ids),
        "certification_state": opportunity.certification_state or "",
        "governance_state": opportunity.governance_state or "",
        "evidence_references": _dedupe_sorted(opportunity.evidence_references),
        "evidence_snapshot_digest": opportunity.evidence_snapshot_digest,
        "registry_version": opportunity.registry_version,
        "provider_version": opportunity.provider_version,
        "formula_version": opportunity.formula_version,
        "schema_version": opportunity.schema_version,
    }
    return sha256_v1(payload)


def compute_report_digest(
    *,
    corpus: CorpusKind,
    provider_id: str,
    opportunities: List[EngineeringRoadmapOpportunity],
    blocked_application_count: int,
    explained_blocker_count: int,
    unexplained_blocker_count: int,
    limitations: List[str],
    evidence_references: List[str],
    evidence_snapshot_digest: str,
) -> str:
    """Hash report semantic fields; excludes generated_at and report_digest."""
    payload: Mapping[str, Any] = {
        "corpus": corpus.value,
        "provider_id": provider_id,
        "opportunities": sorted(opportunity.digest for opportunity in opportunities),
        "blocked_application_count": blocked_application_count,
        "explained_blocker_count": explained_blocker_count,
        "unexplained_blocker_count": unexplained_blocker_count,
        "limitations": _dedupe_sorted(limitations),
        "evidence_references": _dedupe_sorted(evidence_references),
        "evidence_snapshot_digest": evidence_snapshot_digest,
        "formula_version": ENGINEERING_ROADMAP_FORMULA_VERSION,
        "schema_version": ENGINEERING_ROADMAP_SCHEMA_VERSION,
    }
    return sha256_v1(payload)
