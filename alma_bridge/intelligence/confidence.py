"""Transparent confidence weighting for compatibility assessments."""

from __future__ import annotations

from alma_bridge.intelligence.models import (
    CompatibilityFact,
    CompatibilityHypothesis,
    ConfidenceSummary,
    FactStatus,
    HypothesisStatus,
)


class ConfidencePolicy:
    """Deterministic, documented weights for assessment confidence."""

    WEIGHT_VERIFIED_FACT = 0.45
    WEIGHT_OBSERVED_FACT = 0.20
    WEIGHT_RESOLVED_HYPOTHESIS = 0.10
    WEIGHT_OPEN_HYPOTHESIS_PENALTY = 0.08
    WEIGHT_CONFLICT_PENALTY = 0.25

    def summarize(
        self,
        facts: list[CompatibilityFact],
        hypotheses: list[CompatibilityHypothesis],
    ) -> ConfidenceSummary:
        weights = {
            "verified_fact": self.WEIGHT_VERIFIED_FACT,
            "observed_fact": self.WEIGHT_OBSERVED_FACT,
            "resolved_hypothesis": self.WEIGHT_RESOLVED_HYPOTHESIS,
            "open_hypothesis_penalty": self.WEIGHT_OPEN_HYPOTHESIS_PENALTY,
            "conflict_penalty": self.WEIGHT_CONFLICT_PENALTY,
        }

        score = 0.0
        for fact in facts:
            if fact.status == FactStatus.PROVEN:
                score += self.WEIGHT_VERIFIED_FACT * fact.confidence
            else:
                score += self.WEIGHT_OBSERVED_FACT * fact.confidence
            if fact.kind.value == "conflicting_evidence":
                score -= self.WEIGHT_CONFLICT_PENALTY

        open_questions = 0
        for hypothesis in hypotheses:
            if hypothesis.status == HypothesisStatus.OPEN:
                open_questions += 1
                score -= self.WEIGHT_OPEN_HYPOTHESIS_PENALTY
            elif hypothesis.status in (HypothesisStatus.SUPPORTED, HypothesisStatus.REFUTED):
                score += self.WEIGHT_RESOLVED_HYPOTHESIS * 0.5

        overall = max(0.0, min(1.0, round(score, 4)))
        return ConfidenceSummary(
            overall=overall,
            fact_count=len(facts),
            hypothesis_count=len(hypotheses),
            open_questions=open_questions,
            weights_applied=weights,
        )
