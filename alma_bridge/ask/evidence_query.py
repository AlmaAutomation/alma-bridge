"""Evidence query planning for Ask Alma."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Set

from alma_bridge.ask.models import QuestionType

ServiceName = Literal["knowledge", "regression", "advisor"]


@dataclass(frozen=True)
class EvidencePlan:
    services: Set[ServiceName]


_PLANS: dict[QuestionType, EvidencePlan] = {
    QuestionType.COMPATIBILITY_SUMMARY: EvidencePlan(services={"knowledge", "advisor"}),
    QuestionType.VERIFICATION_HISTORY: EvidencePlan(services={"knowledge"}),
    QuestionType.FRAMEWORK_HISTORY: EvidencePlan(services={"knowledge"}),
    QuestionType.LAUNCH_STRATEGY_HISTORY: EvidencePlan(services={"knowledge"}),
    QuestionType.RUNTIME_OBSERVATIONS: EvidencePlan(services={"knowledge"}),
    QuestionType.REGRESSION_CHANGES: EvidencePlan(services={"regression", "knowledge"}),
    QuestionType.CONFLICTING_EVIDENCE: EvidencePlan(services={"knowledge"}),
    QuestionType.EVIDENCE_PROVENANCE: EvidencePlan(services={"knowledge"}),
    QuestionType.REMEDIATION_REFUSAL: EvidencePlan(services={"knowledge"}),
    QuestionType.STRATEGY_RECOMMENDATION_REFUSAL: EvidencePlan(services={"knowledge"}),
    QuestionType.UNSUPPORTED: EvidencePlan(services=set()),
}


class EvidenceQueryPlanner:
    """Map question class to minimal read-only service fetches."""

    def plan(self, question_type: QuestionType) -> EvidencePlan:
        return _PLANS.get(question_type, EvidencePlan(services=set()))
