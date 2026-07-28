"""Tests for pure RegressionDiffEngine."""

from __future__ import annotations

import pytest

from alma_bridge.knowledge.models import EvidenceClassification
from alma_bridge.knowledge.service import CompatibilityKnowledgeService
from alma_bridge.regression.diff import (
    MIN_BASELINE_ATTEMPTS,
    MIN_RATE_DELTA,
    RegressionDiffEngine,
    SUCCESS_RATE_DROP_THRESHOLD,
)
from alma_bridge.regression.models import RegressionSeverity, RegressionType
from alma_bridge.regression.queries import filter_evidence_bundle
from alma_bridge.regression.service import CompatibilityRegressionService
from alma_bridge.storage import outcomes
from tests.intelligence.conftest import CODEBLOCKS_FINGERPRINT
from tests.regression.conftest import (
    KNOWLEDGE_SESSION_C,
    KNOWLEDGE_SESSION_D,
    KNOWLEDGE_SESSION_E,
    seed_codeblocks_regression_sessions,
)


@pytest.fixture(autouse=True)
def _store(tmp_path, monkeypatch):
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    yield


def _profiles_for_comparison(comparison_session_id: str):
    service = CompatibilityRegressionService()
    bundle = service._builder.for_application(CODEBLOCKS_FINGERPRINT)  # noqa: SLF001
    baseline_bundle = filter_evidence_bundle(bundle, exclude_session_ids={comparison_session_id})
    aggregation = service._aggregation  # noqa: SLF001
    before = aggregation.aggregate(baseline_bundle)
    after = aggregation.aggregate(bundle)
    return before, after


def test_diff_engine_constants():
    assert MIN_BASELINE_ATTEMPTS == 3
    assert MIN_RATE_DELTA == 0.25
    assert SUCCESS_RATE_DROP_THRESHOLD == 0.75


def test_strategy_rate_drop_when_comparing_session_c():
    seed_codeblocks_regression_sessions()
    before, after = _profiles_for_comparison(KNOWLEDGE_SESSION_C)

    wine_before = next(s for s in before.observed_launch_strategies if s.strategy == "wine_gui")
    wine_after = next(s for s in after.observed_launch_strategies if s.strategy == "wine_gui")
    assert wine_before.success_rate == pytest.approx(1.0, rel=1e-3)
    assert wine_after.success_rate == pytest.approx(0.75, rel=1e-3)
    assert round(wine_before.success_rate - wine_after.success_rate, 4) == MIN_RATE_DELTA

    findings = RegressionDiffEngine().compare(before, after)
    rate_findings = [
        f for f in findings if f.regression_type == RegressionType.STRATEGY_SUCCESS_RATE_DROPPED
    ]
    assert len(rate_findings) == 1
    finding = rate_findings[0]
    assert finding.subject == "wine_gui"
    assert finding.severity == RegressionSeverity.WARNING
    assert finding.previous_state.evidence_references
    assert finding.current_state.evidence_references
    assert finding.evidence_references
    assert "Observed verified success rate" in finding.summary
    assert "broken" not in finding.summary.lower()


def test_verified_success_to_failure_when_comparing_session_c():
    seed_codeblocks_regression_sessions()
    before, after = _profiles_for_comparison(KNOWLEDGE_SESSION_C)
    assert before.verified_failures == 0
    assert after.verified_failures == 1

    findings = RegressionDiffEngine().compare(before, after)
    verified = [
        f
        for f in findings
        if f.regression_type == RegressionType.VERIFIED_SUCCESS_TO_VERIFIED_FAILURE
    ]
    assert len(verified) == 1
    assert "Compatibility regression" in verified[0].summary
    assert verified[0].severity == RegressionSeverity.CRITICAL


def test_new_conflict_when_comparing_session_d():
    seed_codeblocks_regression_sessions()
    before, after = _profiles_for_comparison(KNOWLEDGE_SESSION_D)
    assert before.conflicts == []
    assert after.conflicts

    findings = RegressionDiffEngine().compare(before, after)
    conflict_findings = [f for f in findings if f.regression_type == RegressionType.NEW_CONFLICT]
    assert len(conflict_findings) == 1
    assert "New conflicting evidence" in conflict_findings[0].summary
    assert conflict_findings[0].previous_state.evidence_references
    assert conflict_findings[0].current_state.evidence_references


def test_verification_contract_changed_when_comparing_session_c():
    seed_codeblocks_regression_sessions()
    before, after = _profiles_for_comparison(KNOWLEDGE_SESSION_C)
    findings = RegressionDiffEngine().compare(before, after)
    contract_findings = [
        f for f in findings if f.regression_type == RegressionType.VERIFICATION_CONTRACT_CHANGED
    ]
    assert contract_findings
    assert all("Verification contract changed" in f.summary for f in contract_findings)


def test_runtime_observation_changed_when_comparing_session_d():
    seed_codeblocks_regression_sessions()
    before, after = _profiles_for_comparison(KNOWLEDGE_SESSION_D)
    findings = RegressionDiffEngine().compare(before, after)
    runtime_findings = [
        f for f in findings if f.regression_type == RegressionType.RUNTIME_OBSERVATION_CHANGED
    ]
    assert runtime_findings
    assert all("Runtime observation changed" in f.summary for f in runtime_findings)


def test_every_finding_has_before_and_after_evidence():
    seed_codeblocks_regression_sessions()
    before, after = _profiles_for_comparison(KNOWLEDGE_SESSION_C)
    findings = RegressionDiffEngine().compare(before, after)
    assert findings
    for finding in findings:
        assert finding.previous_state.evidence_references
        assert finding.current_state.evidence_references
        assert finding.evidence_references
        keys = {
            (ref.source_type, ref.source_id, ref.artifact_key)
            for ref in finding.evidence_references
        }
        for ref in finding.previous_state.evidence_references + finding.current_state.evidence_references:
            assert (ref.source_type, ref.source_id, ref.artifact_key) in keys


def test_diff_is_deterministic():
    seed_codeblocks_regression_sessions()
    before, after = _profiles_for_comparison(KNOWLEDGE_SESSION_C)
    engine = RegressionDiffEngine()
    first = [f.model_dump() for f in engine.compare(before, after)]
    second = [f.model_dump() for f in engine.compare(before, after)]
    assert first == second


def test_unchanged_summary_when_no_findings():
    seed_codeblocks_regression_sessions()
    before, after = _profiles_for_comparison(KNOWLEDGE_SESSION_E)
    findings = RegressionDiffEngine().compare(before, after)
    summary = RegressionDiffEngine().unchanged_summary(before, after, findings)
    assert findings == [] or summary == ""
    if findings == []:
        assert "No compatibility regressions" in summary or "Insufficient baseline" in summary
