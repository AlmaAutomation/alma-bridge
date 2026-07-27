"""Tests for transparent confidence weighting."""

from __future__ import annotations

from alma_bridge.intelligence.confidence import ConfidencePolicy
from alma_bridge.intelligence.models import (
    CompatibilityFact,
    CompatibilityHypothesis,
    EvidenceReference,
    EvidenceSourceType,
    FactKind,
    FactStatus,
    HypothesisStatus,
)


def _fact(kind: FactKind, status: FactStatus, confidence: float) -> CompatibilityFact:
    ref = EvidenceReference(
        source_type=EvidenceSourceType.VERIFICATION,
        source_id="s:1",
        artifact_key="verification:s:1",
    )
    return CompatibilityFact(
        fact_id=f"fact:{kind.value}",
        kind=kind,
        status=status,
        statement="test",
        provenance=[ref],
        confidence=confidence,
    )


def test_confidence_increases_with_verified_facts():
    policy = ConfidencePolicy()
    low = policy.summarize([], [])
    high = policy.summarize(
        [_fact(FactKind.VERIFIED_SUCCESSFUL_LAUNCH, FactStatus.PROVEN, 0.95)],
        [],
    )
    assert high.overall > low.overall
    assert high.weights_applied["verified_fact"] == ConfidencePolicy.WEIGHT_VERIFIED_FACT


def test_open_hypothesis_reduces_confidence():
    policy = ConfidencePolicy()
    base = policy.summarize(
        [_fact(FactKind.VERIFIED_SUCCESSFUL_LAUNCH, FactStatus.PROVEN, 0.9)],
        [],
    )
    with_open = policy.summarize(
        [_fact(FactKind.VERIFIED_SUCCESSFUL_LAUNCH, FactStatus.PROVEN, 0.9)],
        [
            CompatibilityHypothesis(
                hypothesis_id="hypothesis:runtime_requirements",
                question="runtime?",
                status=HypothesisStatus.OPEN,
            )
        ],
    )
    assert with_open.open_questions == 1
    assert with_open.overall < base.overall


def test_conflict_fact_applies_penalty():
    policy = ConfidencePolicy()
    ref = EvidenceReference(
        source_type=EvidenceSourceType.SESSION,
        source_id="s",
        artifact_key="session:s",
    )
    conflict = CompatibilityFact(
        fact_id="fact:conflicting_evidence",
        kind=FactKind.CONFLICTING_EVIDENCE,
        status=FactStatus.OBSERVED,
        statement="conflict",
        provenance=[ref],
        confidence=0.6,
    )
    proven = _fact(FactKind.VERIFIED_SUCCESSFUL_LAUNCH, FactStatus.PROVEN, 0.9)
    without = policy.summarize([proven], [])
    with_conflict = policy.summarize([proven, conflict], [])
    assert with_conflict.overall < without.overall
