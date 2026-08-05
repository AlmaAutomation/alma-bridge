"""Engineering hypothesis tracking tests."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from alma_bridge.compatibility_intelligence.models import ConfidenceLevelName
from alma_bridge.runtime_intelligence.hypotheses import (
    build_hypothesis_created_event_payload,
    build_hypothesis_outcome_linked_event_payload,
    compute_hypothesis_id,
    compute_outcome_link_id,
    create_hypothesis_snapshot,
    create_outcome_link,
    derive_hypothesis_confidence,
    evaluate_hypothesis,
    validate_bounded_scope,
)
from alma_bridge.runtime_intelligence.models import (
    BehaviorFamilyId,
    CorpusKind,
    EngineeringHypothesisResult,
)

ROOT = Path(__file__).resolve().parents[2]
HYPOTHESES_MODULE = ROOT / "alma_bridge" / "runtime_intelligence" / "hypotheses.py"
SNAP = "snap-hyp-001"
CREATED = "2026-08-01T00:00:00+00:00"
LINKED = "2026-08-15T00:00:00+00:00"


def _snapshot(**overrides):
    defaults = {
        "created_at": CREATED,
        "corpus": CorpusKind.ENGINEERING,
        "provider_id": "native_alma",
        "provider_version_scope": "0.2.1-m2",
        "family_id": BehaviorFamilyId.FILESYSTEM,
        "capability_id": "filesystem.basic_io",
        "behavior_id": "append_existing_file",
        "bounded_scope": "append_existing_file within workspace-confined PE64",
        "evidence_snapshot_digest": SNAP,
        "evidence_references": ["evidence-pre-001"],
        "predicted_application_fingerprints": ["fp-app-1", "fp-app-2"],
        "predicted_application_classes": ["cli-hash"],
        "predicted_applications_unblocked_count": 2,
        "predicted_application_classes_unblocked_count": 1,
        "source_expansion_candidate_ids": ["exp-cand-001"],
    }
    defaults.update(overrides)
    return create_hypothesis_snapshot(**defaults)


def _link(snapshot, **overrides):
    defaults = {
        "snapshot": snapshot,
        "linked_at": LINKED,
        "evidence_snapshot_digest": "snap-outcome-001",
        "evidence_references": ["evidence-post-001"],
        "authoritative_outcome_references": ["auth-outcome-001"],
        "observed_application_fingerprints": ["fp-app-1", "fp-app-2"],
        "observed_application_classes": ["cli-hash"],
        "observed_verified_successes": 2,
        "observed_verified_failures": 0,
    }
    defaults.update(overrides)
    return create_outcome_link(**defaults)


class TestEngineeringHypotheses:
    def test_immutable_snapshot_construction(self):
        snap = _snapshot()
        assert snap.hypothesis_id
        assert snap.snapshot_digest

    def test_immutable_outcome_link_construction(self):
        snap = _snapshot()
        link = _link(snap)
        assert link.outcome_link_id
        assert link.link_digest

    def test_deterministic_hypothesis_id(self):
        s = _snapshot()
        id2 = compute_hypothesis_id(
            corpus=s.corpus,
            provider_id=s.provider_id,
            provider_version_scope=s.provider_version_scope,
            family_id=s.family_id,
            capability_id=s.capability_id,
            behavior_id=s.behavior_id,
            bounded_scope=s.bounded_scope,
            source_expansion_candidate_ids=s.source_expansion_candidate_ids,
            evidence_snapshot_digest=s.evidence_snapshot_digest,
        )
        assert s.hypothesis_id == id2

    def test_deterministic_snapshot_digest(self):
        s1 = _snapshot()
        s2 = _snapshot()
        assert s1.snapshot_digest == s2.snapshot_digest

    def test_deterministic_outcome_link_digest(self):
        snap = _snapshot()
        l1 = _link(snap)
        l2 = _link(snap)
        assert l1.link_digest == l2.link_digest

    def test_deterministic_evaluation_digest(self):
        snap = _snapshot()
        link = _link(snap)
        e1 = evaluate_hypothesis(snapshot=snap, outcome_links=[link], fixture_available=True)
        e2 = evaluate_hypothesis(snapshot=snap, outcome_links=[link], fixture_available=True)
        assert e1.evaluation_digest == e2.evaluation_digest

    def test_ordering_does_not_affect_digest(self):
        snap = _snapshot(
            predicted_application_fingerprints=["fp-b", "fp-a"],
            source_expansion_candidate_ids=["cand-b", "cand-a"],
        )
        s2 = _snapshot(
            predicted_application_fingerprints=["fp-a", "fp-b"],
            source_expansion_candidate_ids=["cand-a", "cand-b"],
        )
        assert snap.snapshot_digest == s2.snapshot_digest

    def test_corpus_changes_id(self):
        s1 = _snapshot(corpus=CorpusKind.ENGINEERING)
        s2 = _snapshot(corpus=CorpusKind.REAL_WORLD)
        assert s1.hypothesis_id != s2.hypothesis_id

    def test_family_changes_id(self):
        s1 = _snapshot(family_id=BehaviorFamilyId.FILESYSTEM)
        s2 = _snapshot(family_id=BehaviorFamilyId.CONSOLE, capability_id="console.stdout", behavior_id="write_stdout")
        assert s1.hypothesis_id != s2.hypothesis_id

    def test_provider_changes_id(self):
        s1 = _snapshot(provider_id="native_alma")
        s2 = _snapshot(provider_id="wine")
        assert s1.hypothesis_id != s2.hypothesis_id

    def test_behavior_changes_id(self):
        s1 = _snapshot(behavior_id="append_existing_file")
        s2 = _snapshot(behavior_id="sequential_read")
        assert s1.hypothesis_id != s2.hypothesis_id

    def test_scope_changes_id(self):
        s1 = _snapshot(bounded_scope="append within workspace")
        s2 = _snapshot(bounded_scope="read within workspace")
        assert s1.hypothesis_id != s2.hypothesis_id

    def test_evidence_snapshot_changes_id(self):
        s1 = _snapshot(evidence_snapshot_digest="snap-a")
        s2 = _snapshot(evidence_snapshot_digest="snap-b")
        assert s1.hypothesis_id != s2.hypothesis_id

    def test_source_candidate_changes_id(self):
        s1 = _snapshot(source_expansion_candidate_ids=["cand-a"])
        s2 = _snapshot(source_expansion_candidate_ids=["cand-b"])
        assert s1.hypothesis_id != s2.hypothesis_id

    def test_confirmed_result(self):
        snap = _snapshot()
        link = _link(snap)
        evaluation = evaluate_hypothesis(snapshot=snap, outcome_links=[link], fixture_available=True)
        assert evaluation.result == EngineeringHypothesisResult.CONFIRMED

    def test_partially_confirmed_result(self):
        snap = _snapshot(predicted_applications_unblocked_count=3)
        link = _link(snap, observed_application_fingerprints=["fp-app-1"])
        evaluation = evaluate_hypothesis(snapshot=snap, outcome_links=[link])
        assert evaluation.result == EngineeringHypothesisResult.PARTIALLY_CONFIRMED

    def test_contradicted_by_authoritative_failure(self):
        snap = _snapshot()
        link = _link(snap, observed_verified_failures=1, authoritative_outcome_references=["auth-fail-001"])
        evaluation = evaluate_hypothesis(snapshot=snap, outcome_links=[link])
        assert evaluation.result == EngineeringHypothesisResult.CONTRADICTED

    def test_contradicted_by_zero_unlocks_after_implementation(self):
        snap = _snapshot(predicted_applications_unblocked_count=2)
        link = _link(
            snap,
            implementation_work_item_id="wi-001",
            observed_application_fingerprints=[],
            authoritative_outcome_references=["auth-001"],
        )
        evaluation = evaluate_hypothesis(snapshot=snap, outcome_links=[link])
        assert evaluation.result == EngineeringHypothesisResult.CONTRADICTED

    def test_indeterminate_with_no_authoritative_evidence(self):
        snap = _snapshot()
        link = _link(snap, authoritative_outcome_references=[], evidence_references=["ev-001"])
        evaluation = evaluate_hypothesis(snapshot=snap, outcome_links=[link])
        assert evaluation.result == EngineeringHypothesisResult.INDETERMINATE

    def test_stderr_only_failure_does_not_contradict(self):
        snap = _snapshot()
        link = _link(
            snap,
            observed_verified_failures=1,
            stderr_only_failure=True,
            authoritative_outcome_references=["auth-stderr-001"],
        )
        evaluation = evaluate_hypothesis(snapshot=snap, outcome_links=[link])
        assert evaluation.result != EngineeringHypothesisResult.CONTRADICTED

    def test_provider_mismatch_handled(self):
        snap = _snapshot()
        link = _link(snap)
        evaluation = evaluate_hypothesis(
            snapshot=snap,
            outcome_links=[link],
            provider_version_consistent=False,
        )
        assert evaluation.result == EngineeringHypothesisResult.CONTRADICTED

    def test_scope_mismatch_handled(self):
        snap = _snapshot()
        link = _link(snap)
        evaluation = evaluate_hypothesis(snapshot=snap, outcome_links=[link], scope_consistent=False)
        assert evaluation.result == EngineeringHypothesisResult.CONTRADICTED

    def test_repeated_sessions_do_not_inflate_app_count(self):
        snap = _snapshot()
        link = _link(
            snap,
            observed_application_fingerprints=["fp-app-1", "fp-app-1", "fp-app-1"],
            observed_verified_successes=10,
        )
        evaluation = evaluate_hypothesis(snapshot=snap, outcome_links=[link])
        assert evaluation.observed_applications_unblocked_count == 1

    def test_repeated_apps_across_links_deduplicated(self):
        snap = _snapshot()
        link1 = _link(snap, observed_application_fingerprints=["fp-app-1"])
        link2 = _link(
            snap,
            evidence_snapshot_digest="snap-outcome-002",
            evidence_references=["evidence-post-002"],
            authoritative_outcome_references=["auth-002"],
            observed_application_fingerprints=["fp-app-1", "fp-app-2"],
        )
        evaluation = evaluate_hypothesis(snapshot=snap, outcome_links=[link1, link2])
        assert evaluation.observed_applications_unblocked_count == 2

    def test_application_classes_deduplicated(self):
        snap = _snapshot()
        link = _link(snap, observed_application_classes=["cli-hash", "cli-hash"])
        evaluation = evaluate_hypothesis(snapshot=snap, outcome_links=[link])
        assert evaluation.observed_application_classes_unblocked_count == 1

    def test_multiple_links_combined_deterministically(self):
        snap = _snapshot()
        link1 = _link(snap)
        link2 = _link(
            snap,
            evidence_snapshot_digest="snap-outcome-002",
            evidence_references=["evidence-post-002"],
            authoritative_outcome_references=["auth-002"],
        )
        e1 = evaluate_hypothesis(snapshot=snap, outcome_links=[link1, link2])
        e2 = evaluate_hypothesis(snapshot=snap, outcome_links=[link2, link1])
        assert e1.evaluation_digest == e2.evaluation_digest

    def test_contradictory_links_remain_visible(self):
        snap = _snapshot()
        link1 = _link(snap)
        link2 = _link(
            snap,
            evidence_snapshot_digest="snap-outcome-002",
            evidence_references=["evidence-post-002"],
            authoritative_outcome_references=["auth-fail-002"],
            observed_verified_failures=1,
        )
        evaluation = evaluate_hypothesis(snapshot=snap, outcome_links=[link1, link2])
        assert len(evaluation.outcome_link_digests) == 2

    def test_observed_new_blocker_affects_evaluation(self):
        snap = _snapshot()
        link = _link(snap, observed_new_blockers=["overlapped_io"])
        evaluation = evaluate_hypothesis(snapshot=snap, outcome_links=[link])
        assert evaluation.result == EngineeringHypothesisResult.CONTRADICTED

    def test_confidence_very_high(self):
        level, factors = derive_hypothesis_confidence(
            authoritative_outcome_count=5,
            distinct_application_count=3,
            distinct_class_count=2,
            evidence_fresh=True,
            fixture_available=True,
            contradictory_evidence_count=0,
            provider_version_consistent=True,
            calibration_linkage_count=2,
        )
        assert level == ConfidenceLevelName.VERY_HIGH
        assert factors

    def test_confidence_high(self):
        level, _ = derive_hypothesis_confidence(
            authoritative_outcome_count=3,
            distinct_application_count=2,
            distinct_class_count=1,
            evidence_fresh=True,
            fixture_available=False,
            contradictory_evidence_count=0,
            provider_version_consistent=True,
            calibration_linkage_count=1,
        )
        assert level == ConfidenceLevelName.HIGH

    def test_confidence_medium(self):
        level, _ = derive_hypothesis_confidence(
            authoritative_outcome_count=1,
            distinct_application_count=1,
            distinct_class_count=1,
            evidence_fresh=True,
            fixture_available=False,
            contradictory_evidence_count=0,
            provider_version_consistent=True,
            calibration_linkage_count=0,
        )
        assert level == ConfidenceLevelName.MEDIUM

    def test_confidence_low_via_downgrade(self):
        level, _ = derive_hypothesis_confidence(
            authoritative_outcome_count=1,
            distinct_application_count=1,
            distinct_class_count=0,
            evidence_fresh=False,
            fixture_available=False,
            contradictory_evidence_count=1,
            provider_version_consistent=True,
            calibration_linkage_count=0,
        )
        assert level in (ConfidenceLevelName.LOW, ConfidenceLevelName.UNKNOWN)

    def test_confidence_unknown(self):
        level, _ = derive_hypothesis_confidence(
            authoritative_outcome_count=0,
            distinct_application_count=0,
            distinct_class_count=0,
            evidence_fresh=False,
            fixture_available=False,
            contradictory_evidence_count=0,
            provider_version_consistent=True,
            calibration_linkage_count=0,
        )
        assert level == ConfidenceLevelName.UNKNOWN

    def test_confidence_factors_exposed(self):
        snap = _snapshot()
        link = _link(snap)
        evaluation = evaluate_hypothesis(snapshot=snap, outcome_links=[link])
        assert evaluation.confidence_factors

    def test_contradictory_evidence_lowers_confidence(self):
        level_clean, _ = derive_hypothesis_confidence(
            authoritative_outcome_count=5,
            distinct_application_count=3,
            distinct_class_count=2,
            evidence_fresh=True,
            fixture_available=True,
            contradictory_evidence_count=0,
            provider_version_consistent=True,
            calibration_linkage_count=2,
        )
        level_dirty, factors = derive_hypothesis_confidence(
            authoritative_outcome_count=5,
            distinct_application_count=3,
            distinct_class_count=2,
            evidence_fresh=True,
            fixture_available=True,
            contradictory_evidence_count=2,
            provider_version_consistent=True,
            calibration_linkage_count=2,
        )
        assert level_clean == ConfidenceLevelName.VERY_HIGH
        assert level_dirty != ConfidenceLevelName.VERY_HIGH
        assert "contradictory_evidence_lowers_confidence" in factors

    def test_snapshot_cannot_be_mutated(self):
        snap = _snapshot()
        with pytest.raises(Exception):
            snap.predicted_applications_unblocked_count = 99  # type: ignore[misc]

    def test_outcome_link_cannot_mutate_snapshot(self):
        snap = _snapshot()
        original_digest = snap.snapshot_digest
        _link(snap)
        assert snap.snapshot_digest == original_digest

    def test_original_predictions_remain_unchanged_after_evaluation(self):
        snap = _snapshot()
        predicted = snap.predicted_applications_unblocked_count
        link = _link(snap, observed_application_fingerprints=["fp-app-1"])
        evaluate_hypothesis(snapshot=snap, outcome_links=[link])
        assert snap.predicted_applications_unblocked_count == predicted

    def test_broad_scope_rejected(self):
        with pytest.raises(ValueError, match="too broad"):
            _snapshot(bounded_scope="Implement full kernel32 support")

    def test_missing_evidence_snapshot_rejected(self):
        with pytest.raises(ValueError, match="evidence_snapshot_digest"):
            _snapshot(evidence_snapshot_digest="")

    def test_missing_evidence_refs_rejected(self):
        with pytest.raises(ValueError, match="evidence reference"):
            _snapshot(evidence_references=[])

    def test_missing_predicted_apps_classes_rejected(self):
        with pytest.raises(ValueError, match="predicted application"):
            _snapshot(predicted_application_fingerprints=[], predicted_application_classes=[])

    def test_cross_corpus_ids_rejected(self):
        with pytest.raises(ValueError, match="cross-corpus"):
            _snapshot(
                fingerprint_corpus={"fp-app-1": CorpusKind.REAL_WORLD},
            )

    def test_timeline_created_payload_deterministic(self):
        snap = _snapshot()
        p1 = build_hypothesis_created_event_payload(snap)
        p2 = build_hypothesis_created_event_payload(snap)
        assert p1 == p2
        assert p1["event_type"] == "EngineeringHypothesisCreated"

    def test_timeline_outcome_payload_deterministic(self):
        snap = _snapshot()
        link = _link(snap)
        p1 = build_hypothesis_outcome_linked_event_payload(link)
        p2 = build_hypothesis_outcome_linked_event_payload(link)
        assert p1 == p2
        assert p1["event_type"] == "EngineeringHypothesisOutcomeLinked"

    def test_timeline_payload_has_no_persistence_side_effect(self):
        source = HYPOTHESES_MODULE.read_text(encoding="utf-8")
        assert "EvidenceRepository" not in source
        assert "append_event" not in source
        assert "timeline.append" not in source

    def test_no_evidence_repository_mutation_imported(self):
        source = HYPOTHESES_MODULE.read_text(encoding="utf-8")
        assert "evidence.repository" not in source
        assert "EvidenceService" not in source

    def test_no_orchestrator_imported(self):
        assert "orchestrator" not in HYPOTHESES_MODULE.read_text(encoding="utf-8")

    def test_no_verification_gateway_mutation_imported(self):
        source = HYPOTHESES_MODULE.read_text(encoding="utf-8")
        assert "verification_gateway" not in source
        assert "declare_verified_session_success" not in source

    def test_no_work_item_creation(self):
        source = HYPOTHESES_MODULE.read_text(encoding="utf-8")
        assert "create_work_item" not in source
        assert "NativeLabService" not in source

    def test_no_governance_apply(self):
        source = HYPOTHESES_MODULE.read_text(encoding="utf-8")
        assert "apply_promotion" not in source
        assert "GovernanceRepository" not in source

    def test_no_certification_issue(self):
        source = HYPOTHESES_MODULE.read_text(encoding="utf-8")
        assert "issue_certification" not in source

    def test_no_global_hypothesis_model(self):
        tree = ast.parse(HYPOTHESES_MODULE.read_text(encoding="utf-8"))
        names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
        assert "build_global_hypothesis_report" not in names

    def test_corpus_remains_mandatory(self):
        with pytest.raises(ValueError):
            CorpusKind("combined")

    def test_all_limitations_and_evidence_retained(self):
        snap = _snapshot()
        link = _link(snap)
        evaluation = evaluate_hypothesis(snapshot=snap, outcome_links=[link])
        assert evaluation.limitations
        assert evaluation.evidence_references
        assert "evidence-pre-001" in evaluation.evidence_references

    def test_outcome_link_id_deterministic(self):
        snap = _snapshot()
        id1 = compute_outcome_link_id(
            hypothesis_id=snap.hypothesis_id,
            implementation_work_item_id="wi-001",
            implementation_version="0.2.2",
            evidence_snapshot_digest="snap-out",
        )
        id2 = compute_outcome_link_id(
            hypothesis_id=snap.hypothesis_id,
            implementation_work_item_id="wi-001",
            implementation_version="0.2.2",
            evidence_snapshot_digest="snap-out",
        )
        assert id1 == id2

    def test_validate_bounded_scope_rejects_fix_compatibility(self):
        with pytest.raises(ValueError):
            validate_bounded_scope("We should fix compatibility for all apps")
