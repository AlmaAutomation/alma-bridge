"""Question classifier tests."""

from __future__ import annotations

from alma_bridge.ask.classifier import QuestionClassifier
from alma_bridge.ask.models import QuestionType


def test_classifier_handles_supported_classes():
    classifier = QuestionClassifier()
    cases = {
        "Has Code::Blocks worked before?": QuestionType.VERIFICATION_HISTORY,
        "What changed in the latest session?": QuestionType.REGRESSION_CHANGES,
        "Which frameworks has Alma observed?": QuestionType.FRAMEWORK_HISTORY,
        "Has wine_gui succeeded before?": QuestionType.LAUNCH_STRATEGY_HISTORY,
        "What runtimes were observed?": QuestionType.RUNTIME_OBSERVATIONS,
        "Why is this session marked as a regression?": QuestionType.REGRESSION_CHANGES,
        "What evidence supports the wxWidgets detection?": QuestionType.EVIDENCE_PROVENANCE,
        "Show conflicting evidence.": QuestionType.CONFLICTING_EVIDENCE,
    }
    for question, expected in cases.items():
        assert classifier.classify(question).question_type == expected


def test_unsupported_question():
    classifier = QuestionClassifier()
    assert classifier.classify("Tell me a joke about linux.").question_type == QuestionType.UNSUPPORTED


def test_remediation_refusal_classification():
    classifier = QuestionClassifier()
    assert classifier.classify("Should I install VC++?").question_type == QuestionType.REMEDIATION_REFUSAL
    assert classifier.classify("Fix this for me.").question_type == QuestionType.REMEDIATION_REFUSAL


def test_strategy_recommendation_refusal():
    classifier = QuestionClassifier()
    assert (
        classifier.classify("Which strategy should I use?").question_type
        == QuestionType.STRATEGY_RECOMMENDATION_REFUSAL
    )
