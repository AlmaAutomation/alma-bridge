"""Deterministic rule evaluation for the Decision Engine."""

from __future__ import annotations

from typing import Iterable, List, Optional

from alma_bridge.advisor.models import AdvisorContext, AdvisorExplanation, ObservationCategory
from alma_bridge.advisor.queries import union_evidence_references
from alma_bridge.comparison.models import SessionEnvironmentComparison
from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.decision.models import (
    DECISION_SCHEMA_VERSION,
    ConfidenceLevel,
    Constraint,
    DecisionRecommendation,
    ProvenanceRef,
    RecommendationKind,
)
from alma_bridge.knowledge.models import CompatibilityKnowledgeProfile, KnowledgeEvidenceReference
from alma_bridge.regression.models import CompatibilityRegressionReport, RegressionSeverity


EXECUTION_BOUNDARY_CONSTRAINTS = (
    Constraint(
        code="read_only_boundary",
        description="Decision output is a recommendation only; it does not authorize execution.",
    ),
    Constraint(
        code="no_auto_execute",
        description="No recommendation may trigger automatic execution or prefix mutation.",
    ),
    Constraint(
        code="verification_authority_required",
        description="Verified outcomes require VerificationEngine authority; this plan does not consume it.",
    ),
)


def build_recommendation_id(
    *,
    application_fingerprint: str,
    kind: RecommendationKind,
    subject: str,
) -> str:
    return sha256_v1(
        {
            "schema": DECISION_SCHEMA_VERSION,
            "application_fingerprint": application_fingerprint,
            "kind": kind.value,
            "subject": subject,
        }
    )


def provenance_from_references(
    refs: Iterable[KnowledgeEvidenceReference],
    *,
    source: str,
    limit: int = 8,
) -> List[ProvenanceRef]:
    merged = union_evidence_references(refs)
    return [
        ProvenanceRef.from_knowledge_reference(ref, source=source)
        for ref in merged[: min(len(merged), limit)]
    ]


def _confidence_from_score(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def _base_constraints(extra: Optional[List[Constraint]] = None) -> List[Constraint]:
    items = list(EXECUTION_BOUNDARY_CONSTRAINTS)
    if extra:
        items.extend(extra)
    return sorted(items, key=lambda item: (item.code, item.description))


class DecisionRuleEvaluator:
    """Evaluate deterministic decision rules from composed read-only evidence."""

    def evaluate(
        self,
        *,
        application_fingerprint: str,
        application_name: str,
        knowledge: CompatibilityKnowledgeProfile,
        regression: CompatibilityRegressionReport,
        advisor: AdvisorExplanation,
        comparison: Optional[SessionEnvironmentComparison] = None,
    ) -> List[DecisionRecommendation]:
        recommendations: List[DecisionRecommendation] = []

        if self._insufficient_evidence(knowledge):
            recommendations.append(self._hold_recommendation(application_fingerprint, knowledge, advisor))
        else:
            recommendations.extend(
                self._remediation_review_recommendations(
                    application_fingerprint,
                    regression,
                )
            )
            recommendations.extend(
                self._strategy_recommendations(
                    application_fingerprint,
                    application_name,
                    knowledge,
                )
            )
            recommendations.extend(
                self._verification_review_recommendations(
                    application_fingerprint,
                    advisor,
                )
            )

        if comparison is not None:
            recommendations.extend(
                self._environment_recommendations(
                    application_fingerprint,
                    comparison,
                )
            )

        if not recommendations:
            recommendations.append(
                self._evidence_review_recommendation(
                    application_fingerprint,
                    knowledge,
                    advisor,
                )
            )

        return sorted(recommendations, key=lambda item: (item.kind.value, item.recommendation_id))

    @staticmethod
    def _insufficient_evidence(profile: CompatibilityKnowledgeProfile) -> bool:
        return profile.total_sessions <= 1 or profile.unverifiable_sessions == profile.total_sessions

    def _hold_recommendation(
        self,
        fingerprint: str,
        profile: CompatibilityKnowledgeProfile,
        advisor: AdvisorExplanation,
    ) -> DecisionRecommendation:
        refs = union_evidence_references(
            *(
                obs.evidence_references
                for obs in advisor.observations
                if obs.category == ObservationCategory.INSUFFICIENT_EVIDENCE
            )
        )
        if not refs:
            for strategy in profile.observed_launch_strategies:
                refs.extend(strategy.evidence_references)
        score = 0.25
        return DecisionRecommendation(
            recommendation_id=build_recommendation_id(
                application_fingerprint=fingerprint,
                kind=RecommendationKind.HOLD,
                subject="insufficient_evidence",
            ),
            kind=RecommendationKind.HOLD,
            action=(
                "Hold execution planning until additional verified session evidence is available."
            ),
            confidence=ConfidenceLevel(
                level=_confidence_from_score(score),
                score=score,
                factors=["insufficient_verified_sessions", "read_only_evidence_only"],
            ),
            constraints=_base_constraints(
                [
                    Constraint(
                        code="evidence_threshold_not_met",
                        description="At least two verifiable sessions are required before strategy planning.",
                    )
                ]
            ),
            provenance=provenance_from_references(refs, source="advisor"),
            human_approval_required=True,
            approval_reasons=["insufficient_evidence", "execution_not_authorized"],
        )

    def _remediation_review_recommendations(
        self,
        fingerprint: str,
        regression: CompatibilityRegressionReport,
    ) -> List[DecisionRecommendation]:
        findings = regression.findings or regression.regressions
        recommendations: List[DecisionRecommendation] = []
        for finding in findings:
            if finding.severity not in {
                RegressionSeverity.CRITICAL,
                RegressionSeverity.WARNING,
            }:
                continue
            score = min(1.0, 0.55 + finding.confidence * 0.35)
            recommendations.append(
                DecisionRecommendation(
                    recommendation_id=build_recommendation_id(
                        application_fingerprint=fingerprint,
                        kind=RecommendationKind.REMEDIATION_REVIEW,
                        subject=finding.regression_id,
                    ),
                    kind=RecommendationKind.REMEDIATION_REVIEW,
                    action=(
                        f"Review regression finding ({finding.regression_type.value}): "
                        f"{finding.summary}"
                    ),
                    confidence=ConfidenceLevel(
                        level=_confidence_from_score(score),
                        score=round(score, 4),
                        factors=[
                            f"regression_severity:{finding.severity.value}",
                            f"regression_type:{finding.regression_type.value}",
                        ],
                    ),
                    constraints=_base_constraints(
                        [
                            Constraint(
                                code="human_review_before_remediation",
                                description="Regression review does not authorize remediation or execution.",
                            )
                        ]
                    ),
                    provenance=provenance_from_references(
                        finding.evidence_references,
                        source="regression",
                    ),
                    human_approval_required=True,
                    approval_reasons=[
                        "execution_not_authorized",
                        "regression_detected",
                        "verification_required",
                    ],
                )
            )
        return recommendations

    def _strategy_recommendations(
        self,
        fingerprint: str,
        application_name: str,
        profile: CompatibilityKnowledgeProfile,
    ) -> List[DecisionRecommendation]:
        if not profile.observed_launch_strategies:
            return []

        ranked = sorted(
            profile.observed_launch_strategies,
            key=lambda item: (
                -item.verified_successes,
                -item.success_rate,
                -item.attempts,
                item.strategy,
            ),
        )
        best = ranked[0]
        if best.verified_successes == 0 and best.verified_failures == 0:
            return []

        score = min(
            1.0,
            0.35
            + 0.15 * best.verified_successes
            + 0.25 * best.success_rate
            + 0.05 * min(best.attempts, 4),
        )
        return [
            DecisionRecommendation(
                recommendation_id=build_recommendation_id(
                    application_fingerprint=fingerprint,
                    kind=RecommendationKind.STRATEGY,
                    subject=best.strategy,
                ),
                kind=RecommendationKind.STRATEGY,
                action=(
                    f"For human review: {application_name} has strongest verified history with "
                    f"launch strategy '{best.strategy}' "
                    f"({best.verified_successes} verified success(es), "
                    f"{best.verified_failures} verified failure(s))."
                ),
                confidence=ConfidenceLevel(
                    level=_confidence_from_score(score),
                    score=round(score, 4),
                    factors=[
                        "verified_strategy_history",
                        f"strategy:{best.strategy}",
                    ],
                ),
                constraints=_base_constraints(
                    [
                        Constraint(
                            code="strategy_not_auto_selected",
                            description="Strategy selection remains a human decision; this plan does not launch.",
                        )
                    ]
                ),
                provenance=provenance_from_references(
                    best.evidence_references,
                    source="knowledge",
                ),
                human_approval_required=True,
                approval_reasons=["execution_not_authorized", "strategy_review_required"],
            )
        ]

    def _verification_review_recommendations(
        self,
        fingerprint: str,
        advisor: AdvisorExplanation,
    ) -> List[DecisionRecommendation]:
        recommendations: List[DecisionRecommendation] = []
        for observation in advisor.observations:
            if observation.category != ObservationCategory.VERIFICATION_CONTRACT:
                continue
            score = min(1.0, 0.4 + observation.confidence * 0.5)
            recommendations.append(
                DecisionRecommendation(
                    recommendation_id=build_recommendation_id(
                        application_fingerprint=fingerprint,
                        kind=RecommendationKind.VERIFICATION_REVIEW,
                        subject=observation.observation_id,
                    ),
                    kind=RecommendationKind.VERIFICATION_REVIEW,
                    action=f"Review verification contract evidence: {observation.statement}",
                    confidence=ConfidenceLevel(
                        level=_confidence_from_score(score),
                        score=round(score, 4),
                        factors=["verification_contract_observed"],
                    ),
                    constraints=_base_constraints(
                        [
                            Constraint(
                                code="verification_not_bypassed",
                                description="Verification authority remains with VerificationEngine.",
                            )
                        ]
                    ),
                    provenance=provenance_from_references(
                        observation.evidence_references,
                        source="advisor",
                    ),
                    human_approval_required=True,
                    approval_reasons=["verification_required", "execution_not_authorized"],
                )
            )
        return recommendations

    def _environment_recommendations(
        self,
        fingerprint: str,
        comparison: SessionEnvironmentComparison,
    ) -> List[DecisionRecommendation]:
        changed = [
            item
            for item in comparison.environment_changes
            if item.changed
        ]
        if not changed:
            return []

        refs: List[KnowledgeEvidenceReference] = []
        for item in changed:
            refs.extend(item.evidence_references)

        score = min(1.0, 0.45 + 0.1 * len(changed))
        fields = ", ".join(sorted(item.field for item in changed))
        return [
            DecisionRecommendation(
                recommendation_id=build_recommendation_id(
                    application_fingerprint=fingerprint,
                    kind=RecommendationKind.ENVIRONMENT,
                    subject=fields,
                ),
                kind=RecommendationKind.ENVIRONMENT,
                action=(
                    f"Review environment differences between sessions "
                    f"({comparison.baseline_session_id} → {comparison.comparison_session_id}): "
                    f"changed fields: {fields}."
                ),
                confidence=ConfidenceLevel(
                    level=_confidence_from_score(score),
                    score=round(score, 4),
                    factors=["session_comparison", "environment_delta_observed"],
                ),
                constraints=_base_constraints(
                    [
                        Constraint(
                            code="non_causal_comparison",
                            description="Environment changes are observed only; causality is not inferred.",
                        )
                    ]
                ),
                provenance=provenance_from_references(refs, source="comparison"),
                human_approval_required=True,
                approval_reasons=["environment_review_required", "execution_not_authorized"],
            )
        ]

    def _evidence_review_recommendation(
        self,
        fingerprint: str,
        profile: CompatibilityKnowledgeProfile,
        advisor: AdvisorExplanation,
    ) -> DecisionRecommendation:
        refs = union_evidence_references(
            *(obs.evidence_references for obs in advisor.observations)
        )
        if not refs:
            for strategy in profile.observed_launch_strategies:
                refs.extend(strategy.evidence_references)
        score = min(1.0, 0.35 + 0.05 * profile.total_sessions)
        return DecisionRecommendation(
            recommendation_id=build_recommendation_id(
                application_fingerprint=fingerprint,
                kind=RecommendationKind.EVIDENCE_REVIEW,
                subject="general_review",
            ),
            kind=RecommendationKind.EVIDENCE_REVIEW,
            action="Review accumulated compatibility evidence before any execution planning step.",
            confidence=ConfidenceLevel(
                level=_confidence_from_score(score),
                score=round(score, 4),
                factors=["baseline_evidence_available"],
            ),
            constraints=_base_constraints(),
            provenance=provenance_from_references(refs, source="advisor"),
            human_approval_required=True,
            approval_reasons=["execution_not_authorized", "human_review_required"],
        )
