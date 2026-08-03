"""Deterministic priority ranking with hard exclusions."""

from __future__ import annotations

from typing import List, Optional, Tuple

from alma_bridge.compatibility_intelligence.expansion.complexity import engineering_cost_score
from alma_bridge.compatibility_intelligence.expansion.models import (
    EngineeringComplexityLevel,
    EvidenceQualityLevel,
    ExcludedCandidate,
    PriorityDimensions,
    RuntimeExpansionCandidate,
    SecurityRiskCategory,
    TestabilityLevel,
)
from alma_bridge.compatibility_intelligence.governance.models import CapabilityMaturityState

HARD_EXCLUDED_CAPABILITIES = frozenset(
    {
        "kernel.driver",
        "anti_cheat",
        "dll.loading.arbitrary",
        "process.creation",
    }
)

HARD_EXCLUDED_CAPABILITY_PREFIXES = (
    "kernel.",
    "anticheat.",
    "anti_cheat.",
)

MAX_COMPLEXITY_FILTER = {
    "trivial": EngineeringComplexityLevel.TRIVIAL,
    "low": EngineeringComplexityLevel.LOW,
    "medium": EngineeringComplexityLevel.MEDIUM,
    "high": EngineeringComplexityLevel.HIGH,
    "very_high": EngineeringComplexityLevel.VERY_HIGH,
}

COMPLEXITY_ORDER = {
    EngineeringComplexityLevel.TRIVIAL: 0,
    EngineeringComplexityLevel.LOW: 1,
    EngineeringComplexityLevel.MEDIUM: 2,
    EngineeringComplexityLevel.HIGH: 3,
    EngineeringComplexityLevel.VERY_HIGH: 4,
    EngineeringComplexityLevel.UNKNOWN: 5,
}


def is_hard_excluded(
    capability_id: str,
    *,
    has_reproducible_fixture: bool,
    implementation_scope: str,
) -> Optional[str]:
    if capability_id in HARD_EXCLUDED_CAPABILITIES:
        return f"hard exclusion: capability {capability_id} is out of bounded scope"
    for prefix in HARD_EXCLUDED_CAPABILITY_PREFIXES:
        if capability_id.startswith(prefix):
            return f"hard exclusion: capability prefix {prefix} not eligible"
    if SecurityRiskCategory.ARBITRARY_PROCESS_CREATION.value in capability_id:
        return "hard exclusion: unbounded process creation"
    if not has_reproducible_fixture and capability_id != "api.unknown":
        return "hard exclusion: no reproducible test fixture"
    if not implementation_scope or implementation_scope.strip() == "":
        return "hard exclusion: undocumented scope"
    return None


def is_behavior_already_stable(
    behavior_id: Optional[str],
    supported_behaviors: List[str],
    maturity_state: CapabilityMaturityState,
) -> bool:
    if not behavior_id:
        return False
    if behavior_id not in supported_behaviors:
        return False
    stable_states = {
        CapabilityMaturityState.VERIFIED_BOUNDED,
        CapabilityMaturityState.STABLE,
    }
    return maturity_state in stable_states


def assess_testability(
    evidence_references: List[str],
    behavior_id: Optional[str],
) -> Tuple[TestabilityLevel, float]:
    fixture_refs = [r for r in evidence_references if "fixture" in r.lower() or r.endswith(".exe")]
    if fixture_refs and behavior_id:
        return TestabilityLevel.HIGH, 0.9
    if fixture_refs:
        return TestabilityLevel.MEDIUM, 0.65
    if evidence_references:
        return TestabilityLevel.LOW, 0.35
    return TestabilityLevel.NONE, 0.0


def assess_evidence_quality(
    distinct_binaries: int,
    evidence_references: List[str],
    verified_sessions: int,
) -> Tuple[EvidenceQualityLevel, float]:
    if distinct_binaries >= 2 and evidence_references and verified_sessions > 0:
        return EvidenceQualityLevel.STRONG, 0.9
    if distinct_binaries >= 1 and evidence_references:
        return EvidenceQualityLevel.MODERATE, 0.65
    if evidence_references:
        return EvidenceQualityLevel.WEAK, 0.35
    return EvidenceQualityLevel.INSUFFICIENT, 0.0


def compute_priority_dimensions(
    *,
    demand_score: float,
    bounded_impact_score: float,
    complexity_cost_score: float,
    security_risk_score: float,
    semantic_risk_score: float,
    evidence_quality_score: float,
    testability_score: float,
) -> PriorityDimensions:
    """Weighted composite — all dimensions preserved in output."""
    composite = round(
        demand_score * 0.25
        + bounded_impact_score * 0.25
        + complexity_cost_score * 0.15
        + (1.0 - security_risk_score) * 0.1
        + (1.0 - semantic_risk_score) * 0.1
        + evidence_quality_score * 0.1
        + testability_score * 0.05,
        4,
    )
    return PriorityDimensions(
        demand_score=demand_score,
        bounded_impact_score=bounded_impact_score,
        engineering_cost_score=complexity_cost_score,
        security_risk_score=security_risk_score,
        semantic_risk_score=semantic_risk_score,
        evidence_quality_score=evidence_quality_score,
        testability_score=testability_score,
        composite_score=composite,
    )


def rank_candidates(
    candidates: List[RuntimeExpansionCandidate],
    excluded: List[ExcludedCandidate],
) -> Tuple[List[RuntimeExpansionCandidate], List[ExcludedCandidate]]:
    """Sort by composite score descending, then candidate_id for stability."""
    ranked = sorted(
        candidates,
        key=lambda c: (-c.priority.composite_score, c.candidate_id),
    )
    return ranked, excluded


def filter_plan_candidates(
    candidates: List[RuntimeExpansionCandidate],
    *,
    provider_id: Optional[str] = None,
    architecture: Optional[str] = None,
    subsystem: Optional[str] = None,
    maximum_complexity: Optional[str] = None,
    maximum_security_risk: Optional[float] = None,
) -> List[RuntimeExpansionCandidate]:
    results = candidates
    if provider_id:
        results = [c for c in results if c.provider_id == provider_id]
    if architecture:
        results = [c for c in results if c.architecture == architecture]
    if subsystem:
        results = [c for c in results if c.subsystem == subsystem]
    if maximum_complexity:
        max_level = MAX_COMPLEXITY_FILTER.get(maximum_complexity.lower())
        if max_level is not None:
            max_ord = COMPLEXITY_ORDER[max_level]
            results = [
                c
                for c in results
                if COMPLEXITY_ORDER[c.engineering_complexity.level] <= max_ord
            ]
    if maximum_security_risk is not None:
        results = [
            c for c in results if c.security_risk.score <= maximum_security_risk
        ]
    return results
