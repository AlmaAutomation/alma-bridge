"""Runtime conformance classification tests."""

from __future__ import annotations

from alma_bridge.runtime.conformance.comparison import classify_baseline_comparison
from alma_bridge.runtime.conformance.models import ConformanceClassification
from alma_bridge.runtime.conformance.service import ConformanceService


class TestConformanceClassification:
    def test_equivalent_exit_and_stdout(self):
        result = classify_baseline_comparison(
            baseline={"exit_code": 0, "stdout": "ok"},
            candidate={"exit_code": 0, "stdout": "ok"},
        )
        assert result == ConformanceClassification.EQUIVALENT

    def test_functionally_equivalent_different_stdout(self):
        result = classify_baseline_comparison(
            baseline={"exit_code": 0, "stdout": "a"},
            candidate={"exit_code": 0, "stdout": "b"},
        )
        assert result == ConformanceClassification.FUNCTIONALLY_EQUIVALENT

    def test_candidate_failed(self):
        result = classify_baseline_comparison(
            baseline={"exit_code": 0},
            candidate={"failed": True, "error": "not supported"},
        )
        assert result == ConformanceClassification.CANDIDATE_FAILED

    def test_behavior_changed(self):
        result = classify_baseline_comparison(
            baseline={"exit_code": 0},
            candidate={"exit_code": 1},
        )
        assert result == ConformanceClassification.BEHAVIOR_CHANGED

    def test_insufficient_evidence(self):
        result = classify_baseline_comparison(
            baseline={},
            candidate={},
            required_signals=["exit_code"],
        )
        assert result == ConformanceClassification.INSUFFICIENT_EVIDENCE

    def test_default_suite_runs(self):
        service = ConformanceService()
        report = service.run_default_suite()
        assert len(report.results) == 4
        native = next(r for r in report.results if r.scenario_id == "native_alma_fail_closed")
        assert native.classification == ConformanceClassification.CANDIDATE_FAILED
