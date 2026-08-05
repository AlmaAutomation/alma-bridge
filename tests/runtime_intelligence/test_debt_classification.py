"""Compatibility Debt classification tests."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from alma_bridge.native_lab.models import RiskSeverity
from alma_bridge.runtime_intelligence.debt import (
    DEBT_BACKLOG_LIMITATION,
    build_debt_report,
    classify_debt_signal,
    classify_disposition,
    classify_severity,
    compute_age_days,
    compute_debt_id,
    validate_debt_signal,
)
from alma_bridge.runtime_intelligence.models import (
    BehaviorFamilyId,
    CompatibilityDebtDisposition,
    CompatibilityDebtKind,
    CompatibilityDebtSignal,
    CorpusKind,
)

ROOT = Path(__file__).resolve().parents[2]
DEBT_MODULE = ROOT / "alma_bridge" / "runtime_intelligence" / "debt.py"
SNAP = "snap-debt-001"


def _signal(**overrides) -> CompatibilityDebtSignal:
    defaults = {
        "kind": CompatibilityDebtKind.UNSUPPORTED_BEHAVIOR,
        "corpus": CorpusKind.ENGINEERING,
        "family_id": BehaviorFamilyId.FILESYSTEM,
        "capability_id": "filesystem.basic_io",
        "behavior_id": "overlapped_io",
        "evidence_snapshot_digest": SNAP,
        "evidence_references": ["evidence-bundle-debt-001"],
        "distinct_application_count": 1,
        "distinct_binary_count": 1,
    }
    defaults.update(overrides)
    return CompatibilityDebtSignal(**defaults)


ALL_KINDS = list(CompatibilityDebtKind)
ALL_DISPOSITIONS = list(CompatibilityDebtDisposition)


class TestDebtClassification:
    @pytest.mark.parametrize("kind", ALL_KINDS)
    def test_each_debt_category_classifies(self, kind: CompatibilityDebtKind):
        item = classify_debt_signal(_signal(kind=kind))
        assert item.kind == kind

    @pytest.mark.parametrize(
        "signal_kwargs,expected",
        [
            ({"explicitly_out_of_scope": True}, CompatibilityDebtDisposition.ACKNOWLEDGED_OUT_OF_SCOPE),
            ({"evidence_stale": True}, CompatibilityDebtDisposition.STALE_EVIDENCE),
            (
                {
                    "prerequisite_capability_ids": ["crt.startup"],
                    "prerequisites_unmet": True,
                    "kind": CompatibilityDebtKind.UNSUPPORTED_BEHAVIOR,
                },
                CompatibilityDebtDisposition.BLOCKED_BY_PREREQUISITE,
            ),
            ({"kind": CompatibilityDebtKind.UNKNOWN_API}, CompatibilityDebtDisposition.UNKNOWN),
            ({"kind": CompatibilityDebtKind.UNKNOWN_BEHAVIOR}, CompatibilityDebtDisposition.UNKNOWN),
            ({}, CompatibilityDebtDisposition.ADDRESSABLE),
        ],
    )
    def test_disposition_rules(self, signal_kwargs, expected):
        assert classify_disposition(_signal(**signal_kwargs)) == expected

    def test_critical_severity_false_positive_high_security(self):
        severity, factors = classify_severity(
            _signal(
                kind=CompatibilityDebtKind.CALIBRATION_FALSE_POSITIVE,
                authoritative_failure_count=1,
                security_risk_score=0.8,
                calibration_gap_count=1,
            )
        )
        assert severity == RiskSeverity.CRITICAL
        assert factors

    def test_high_severity_unsupported_capability_three_apps(self):
        severity, _ = classify_severity(
            _signal(kind=CompatibilityDebtKind.UNSUPPORTED_CAPABILITY, distinct_application_count=3)
        )
        assert severity == RiskSeverity.HIGH

    def test_medium_severity_unsupported_behavior(self):
        severity, _ = classify_severity(
            _signal(kind=CompatibilityDebtKind.UNSUPPORTED_BEHAVIOR, distinct_application_count=1)
        )
        assert severity == RiskSeverity.MEDIUM

    def test_low_severity_missing_fixture(self):
        severity, _ = classify_severity(_signal(kind=CompatibilityDebtKind.MISSING_FIXTURE))
        assert severity == RiskSeverity.LOW

    def test_out_of_scope_takes_disposition_precedence(self):
        item = classify_debt_signal(
            _signal(
                explicitly_out_of_scope=True,
                evidence_stale=True,
                kind=CompatibilityDebtKind.UNKNOWN_API,
            )
        )
        assert item.disposition == CompatibilityDebtDisposition.ACKNOWLEDGED_OUT_OF_SCOPE

    def test_stale_evidence_precedence_over_unknown(self):
        item = classify_debt_signal(_signal(evidence_stale=True, kind=CompatibilityDebtKind.UNKNOWN_API))
        assert item.disposition == CompatibilityDebtDisposition.STALE_EVIDENCE

    def test_unmet_prerequisite_precedence_over_addressable(self):
        item = classify_debt_signal(
            _signal(
                prerequisite_capability_ids=["crt.startup"],
                prerequisites_unmet=True,
            )
        )
        assert item.disposition == CompatibilityDebtDisposition.BLOCKED_BY_PREREQUISITE

    def test_unknown_remains_unknown_not_unsupported(self):
        item = classify_debt_signal(_signal(kind=CompatibilityDebtKind.UNKNOWN_API))
        assert item.disposition == CompatibilityDebtDisposition.UNKNOWN
        assert item.kind == CompatibilityDebtKind.UNKNOWN_API

    def test_stderr_only_evidence_rejected(self):
        with pytest.raises(ValueError, match="stderr-only"):
            validate_debt_signal(_signal(stderr_only=True))

    def test_missing_evidence_references_rejected(self):
        with pytest.raises(ValueError, match="evidence reference"):
            validate_debt_signal(_signal(evidence_references=[]))

    def test_missing_snapshot_digest_rejected(self):
        with pytest.raises(ValueError, match="evidence_snapshot_digest"):
            validate_debt_signal(_signal(evidence_snapshot_digest=""))

    def test_negative_counts_rejected(self):
        with pytest.raises(ValueError):
            CompatibilityDebtSignal(
                kind=CompatibilityDebtKind.UNSUPPORTED_BEHAVIOR,
                corpus=CorpusKind.ENGINEERING,
                family_id=BehaviorFamilyId.FILESYSTEM,
                capability_id="filesystem.basic_io",
                evidence_snapshot_digest=SNAP,
                evidence_references=["ref"],
                distinct_application_count=-1,
            )

    def test_distinct_app_count_deduplicated_from_fingerprints(self):
        item = classify_debt_signal(
            _signal(
                affected_application_fingerprints=["fp-a", "fp-b", "fp-a"],
                distinct_application_count=99,
            )
        )
        assert item.distinct_application_count == 2

    def test_distinct_binary_count_deduplicated_from_digests(self):
        item = classify_debt_signal(
            _signal(
                affected_binary_digests=["bin-a", "bin-b", "bin-a"],
                distinct_binary_count=99,
            )
        )
        assert item.distinct_binary_count == 2

    def test_application_mentions_not_mislabeled_as_distinct(self):
        report = build_debt_report(
            corpus=CorpusKind.ENGINEERING,
            family_id=BehaviorFamilyId.FILESYSTEM,
            signals=[
                _signal(
                    affected_application_fingerprints=["fp-shared"],
                    distinct_application_count=5,
                ),
                _signal(
                    kind=CompatibilityDebtKind.UNKNOWN_API,
                    capability_id="api.unknown",
                    behavior_id=None,
                    affected_application_fingerprints=["fp-shared"],
                    distinct_application_count=5,
                ),
            ],
            evidence_snapshot_digest=SNAP,
        )
        assert report.summed_item_application_mentions == 10
        assert report.total_distinct_applications == 1

    def test_deterministic_debt_id(self):
        s = _signal()
        id1 = compute_debt_id(
            corpus=s.corpus,
            family_id=s.family_id,
            provider_id=s.provider_id,
            capability_id=s.capability_id,
            behavior_id=s.behavior_id,
            kind=s.kind,
            evidence_snapshot_digest=s.evidence_snapshot_digest,
        )
        id2 = compute_debt_id(
            corpus=s.corpus,
            family_id=s.family_id,
            provider_id=s.provider_id,
            capability_id=s.capability_id,
            behavior_id=s.behavior_id,
            kind=s.kind,
            evidence_snapshot_digest=s.evidence_snapshot_digest,
        )
        assert id1 == id2

    def test_deterministic_item_digest(self):
        item1 = classify_debt_signal(_signal())
        item2 = classify_debt_signal(_signal())
        assert item1.digest == item2.digest

    def test_deterministic_report_digest(self):
        signals = [_signal(), _signal(kind=CompatibilityDebtKind.UNKNOWN_API, capability_id="api.unknown", behavior_id=None)]
        r1 = build_debt_report(
            corpus=CorpusKind.ENGINEERING,
            family_id=BehaviorFamilyId.FILESYSTEM,
            signals=signals,
            evidence_snapshot_digest=SNAP,
        )
        r2 = build_debt_report(
            corpus=CorpusKind.ENGINEERING,
            family_id=BehaviorFamilyId.FILESYSTEM,
            signals=list(reversed(signals)),
            evidence_snapshot_digest=SNAP,
        )
        assert r1.report_digest == r2.report_digest

    def test_ordering_does_not_affect_item_digest(self):
        item = classify_debt_signal(
            _signal(
                evidence_references=["ref-b", "ref-a"],
                prerequisite_capability_ids=["z", "a"],
                limitations=["lim-b", "lim-a"],
            )
        )
        assert item.evidence_references == ["ref-a", "ref-b"]
        assert item.prerequisite_capability_ids == ["a", "z"]

    def test_corpus_changes_digest(self):
        r1 = build_debt_report(
            corpus=CorpusKind.ENGINEERING,
            family_id=BehaviorFamilyId.FILESYSTEM,
            signals=[_signal()],
            evidence_snapshot_digest=SNAP,
        )
        r2 = build_debt_report(
            corpus=CorpusKind.REAL_WORLD,
            family_id=BehaviorFamilyId.FILESYSTEM,
            signals=[_signal(corpus=CorpusKind.REAL_WORLD)],
            evidence_snapshot_digest=SNAP,
        )
        assert r1.report_digest != r2.report_digest

    def test_family_changes_digest(self):
        r1 = build_debt_report(
            corpus=CorpusKind.ENGINEERING,
            family_id=BehaviorFamilyId.FILESYSTEM,
            signals=[_signal()],
            evidence_snapshot_digest=SNAP,
        )
        r2 = build_debt_report(
            corpus=CorpusKind.ENGINEERING,
            family_id=BehaviorFamilyId.CONSOLE,
            signals=[_signal(family_id=BehaviorFamilyId.CONSOLE, capability_id="console.stdout", behavior_id="write_stdout")],
            evidence_snapshot_digest=SNAP,
        )
        assert r1.report_digest != r2.report_digest

    def test_provider_changes_digest(self):
        r1 = build_debt_report(
            corpus=CorpusKind.ENGINEERING,
            family_id=BehaviorFamilyId.FILESYSTEM,
            signals=[_signal(provider_id="native_alma")],
            provider_id="native_alma",
            evidence_snapshot_digest=SNAP,
        )
        r2 = build_debt_report(
            corpus=CorpusKind.ENGINEERING,
            family_id=BehaviorFamilyId.FILESYSTEM,
            signals=[_signal(provider_id="wine")],
            provider_id="wine",
            evidence_snapshot_digest=SNAP,
        )
        assert r1.report_digest != r2.report_digest

    def test_behavior_changes_digest(self):
        item1 = classify_debt_signal(_signal(behavior_id="overlapped_io"))
        item2 = classify_debt_signal(_signal(behavior_id="sequential_read"))
        assert item1.digest != item2.digest

    def test_snapshot_changes_digest(self):
        item1 = classify_debt_signal(_signal(evidence_snapshot_digest="snap-a"))
        item2 = classify_debt_signal(_signal(evidence_snapshot_digest="snap-b"))
        assert item1.digest != item2.digest

    def test_generated_at_does_not_affect_digest(self):
        report = build_debt_report(
            corpus=CorpusKind.ENGINEERING,
            family_id=BehaviorFamilyId.FILESYSTEM,
            signals=[_signal()],
            evidence_snapshot_digest=SNAP,
        )
        with_ts = report.model_copy(update={"generated_at": "2026-08-05T12:00:00+00:00"})
        assert with_ts.report_digest == report.report_digest

    def test_age_computed_from_snapshot_timestamps(self):
        item = classify_debt_signal(
            _signal(
                first_observed="2026-01-01T00:00:00+00:00",
                last_observed="2026-01-15T00:00:00+00:00",
            )
        )
        assert item.age_days == 14
        assert compute_age_days(
            first_observed="2026-01-01T00:00:00+00:00",
            last_observed="2026-01-15T00:00:00+00:00",
        ) == 14

    def test_age_does_not_use_wall_clock(self):
        source = DEBT_MODULE.read_text(encoding="utf-8")
        assert "datetime.now" not in source
        assert "utc_now" not in source

    def test_prerequisite_ids_deduplicated_and_sorted(self):
        item = classify_debt_signal(_signal(prerequisite_capability_ids=["b", "a", "b"]))
        assert item.prerequisite_capability_ids == ["a", "b"]

    def test_evidence_references_deduplicated_and_sorted(self):
        item = classify_debt_signal(_signal(evidence_references=["ref-b", "ref-a", "ref-b"]))
        assert item.evidence_references == ["ref-a", "ref-b"]

    def test_limitations_deduplicated_and_sorted(self):
        item = classify_debt_signal(_signal(limitations=["custom-b", "custom-a"]))
        assert DEBT_BACKLOG_LIMITATION in item.limitations

    def test_severity_factors_exposed(self):
        item = classify_debt_signal(
            _signal(
                kind=CompatibilityDebtKind.CALIBRATION_FALSE_POSITIVE,
                authoritative_failure_count=1,
                security_risk_score=0.8,
            )
        )
        assert item.severity_factors

    def test_raw_counts_always_exposed(self):
        item = classify_debt_signal(
            _signal(blocked_session_count=3, calibration_gap_count=2, distinct_application_count=4)
        )
        assert item.blocked_session_count == 3
        assert item.calibration_gap_count == 2
        assert item.distinct_application_count == 4

    def test_report_counts_by_category_correct(self):
        report = build_debt_report(
            corpus=CorpusKind.ENGINEERING,
            family_id=BehaviorFamilyId.FILESYSTEM,
            signals=[
                _signal(),
                _signal(kind=CompatibilityDebtKind.UNKNOWN_API, capability_id="api.unknown", behavior_id=None),
            ],
            evidence_snapshot_digest=SNAP,
        )
        assert report.counts_by_kind["unsupported_behavior"] == 1
        assert report.counts_by_kind["unknown_api"] == 1

    def test_report_counts_by_disposition_correct(self):
        report = build_debt_report(
            corpus=CorpusKind.ENGINEERING,
            family_id=BehaviorFamilyId.FILESYSTEM,
            signals=[
                _signal(),
                _signal(kind=CompatibilityDebtKind.UNKNOWN_API, capability_id="api.unknown", behavior_id=None),
            ],
            evidence_snapshot_digest=SNAP,
        )
        assert report.counts_by_disposition["addressable"] == 1
        assert report.counts_by_disposition["unknown"] == 1

    def test_report_counts_by_severity_correct(self):
        report = build_debt_report(
            corpus=CorpusKind.ENGINEERING,
            family_id=BehaviorFamilyId.FILESYSTEM,
            signals=[_signal(), _signal(kind=CompatibilityDebtKind.MISSING_FIXTURE)],
            evidence_snapshot_digest=SNAP,
        )
        assert sum(report.counts_by_severity.values()) == 2

    def test_no_merged_corpus_report_constructible(self):
        with pytest.raises(ValueError, match="same explicit corpus"):
            build_debt_report(
                corpus=CorpusKind.ENGINEERING,
                family_id=BehaviorFamilyId.FILESYSTEM,
                signals=[_signal(corpus=CorpusKind.REAL_WORLD)],
                evidence_snapshot_digest=SNAP,
            )

    def test_no_global_debt_report_exists(self):
        tree = ast.parse(DEBT_MODULE.read_text(encoding="utf-8"))
        names = {node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
        assert "build_global_debt_report" not in names

    def test_package_imports_no_orchestrator(self):
        assert "orchestrator" not in DEBT_MODULE.read_text(encoding="utf-8")

    def test_package_imports_no_verification_gateway_mutation(self):
        source = DEBT_MODULE.read_text(encoding="utf-8")
        assert "verification_gateway" not in source
        assert "declare_verified_session_success" not in source

    def test_package_cannot_create_native_lab_work_item(self):
        source = DEBT_MODULE.read_text(encoding="utf-8")
        assert "create_work_item" not in source
        assert "NativeLabService" not in source

    def test_package_cannot_apply_governance(self):
        source = DEBT_MODULE.read_text(encoding="utf-8")
        assert "apply_promotion" not in source
        assert "GovernanceRepository" not in source

    def test_package_cannot_issue_certification(self):
        source = DEBT_MODULE.read_text(encoding="utf-8")
        assert "issue_certification" not in source
        assert "CertificationService" not in source

    def test_package_does_not_import_expansion_ranking_engine(self):
        source = DEBT_MODULE.read_text(encoding="utf-8")
        assert "expansion.ranking" not in source
        assert "compute_priority_dimensions" not in source

    def test_debt_language_does_not_promise_implementation(self):
        item = classify_debt_signal(_signal())
        assert DEBT_BACKLOG_LIMITATION in item.limitations

    def test_unknown_api_remains_visible(self):
        item = classify_debt_signal(
            _signal(kind=CompatibilityDebtKind.UNKNOWN_API, capability_id="api.unknown", behavior_id=None)
        )
        assert item.kind == CompatibilityDebtKind.UNKNOWN_API

    def test_stale_evidence_remains_visible(self):
        item = classify_debt_signal(_signal(evidence_stale=True, kind=CompatibilityDebtKind.STALE_EVIDENCE))
        assert item.disposition == CompatibilityDebtDisposition.STALE_EVIDENCE

    def test_out_of_scope_debt_remains_visible(self):
        item = classify_debt_signal(
            _signal(explicitly_out_of_scope=True, kind=CompatibilityDebtKind.ACKNOWLEDGED_OUT_OF_SCOPE)
        )
        assert item.disposition == CompatibilityDebtDisposition.ACKNOWLEDGED_OUT_OF_SCOPE

    def test_report_retains_all_item_evidence_links(self):
        report = build_debt_report(
            corpus=CorpusKind.ENGINEERING,
            family_id=BehaviorFamilyId.FILESYSTEM,
            signals=[_signal(evidence_references=["ref-a"])],
            evidence_snapshot_digest=SNAP,
        )
        assert report.items[0].evidence_references == ["ref-a"]
        assert "ref-a" in report.evidence_references

    def test_high_stale_certification_production_ready_critical(self):
        severity, _ = classify_severity(
            _signal(
                kind=CompatibilityDebtKind.STALE_CERTIFICATION,
                current_certification="production_ready",
            )
        )
        assert severity == RiskSeverity.CRITICAL

    def test_calibration_false_negative_medium(self):
        severity, _ = classify_severity(
            _signal(kind=CompatibilityDebtKind.CALIBRATION_FALSE_NEGATIVE, calibration_gap_count=1)
        )
        assert severity == RiskSeverity.MEDIUM

    def test_maturity_regression_high_with_demand(self):
        severity, _ = classify_severity(
            _signal(kind=CompatibilityDebtKind.MATURITY_REGRESSION, distinct_application_count=2)
        )
        assert severity == RiskSeverity.HIGH

    def test_corpus_remains_mandatory(self):
        with pytest.raises(ValueError):
            CorpusKind("combined")
