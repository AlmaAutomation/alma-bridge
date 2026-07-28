"""Ask Alma language policy guards."""

from __future__ import annotations

from typing import List

from alma_bridge.advisor.policy import validate_statement
from alma_bridge.ask.models import AskAlmaAnswer, AskAlmaValidationError, QuestionType


def validate_answer(answer: AskAlmaAnswer) -> None:
    violations: List[str] = []
    violations.extend(validate_statement(answer.answer))
    for limitation in answer.limitations:
        violations.extend(validate_statement(limitation))
    if not answer.evidence_references and answer.question_type not in {
        QuestionType.UNSUPPORTED,
    }:
        if answer.question_type not in {
            QuestionType.REMEDIATION_REFUSAL,
            QuestionType.STRATEGY_RECOMMENDATION_REFUSAL,
        }:
            violations.append("missing evidence references")
    if violations:
        raise AskAlmaValidationError(
            "ask answer violates language policy",
            details=sorted(set(violations)),
        )
