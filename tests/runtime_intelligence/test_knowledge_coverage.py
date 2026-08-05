"""Compatibility Knowledge Coverage formula tests."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from alma_bridge.runtime_intelligence.index import compute_compatibility_index
from alma_bridge.runtime_intelligence.knowledge import (
    KNOWLEDGE_COVERAGE_WEIGHTS_V1,
    compute_knowledge_coverage,
    compute_knowledge_report_digest,
    qualifies_as_attributed_failure,
    qualifies_as_documented_limitation,
    qualifies_as_explained_blocker,
)
from alma_bridge.runtime_intelligence.models import (
    BehaviorFamilyId,
    CompatibilityIndexInput,
    CompatibilityKnowledgeCoverageReport,
    CompatibilityKnowledgeInput,
    CorpusKind,
    EvidenceRatio,
)

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE_MODULE = ROOT / "alma_bridge" / "runtime_intelligence" / "knowledge.py"


def _ratio(numerator: int, denominator: int, **kwargs) -> EvidenceRatio:
    return EvidenceRatio(numerator=numerator, denominator=denominator, **kwargs)


def _full_input(**overrides) -> CompatibilityKnowledgeInput:
    defaults = {
        "corpus": CorpusKind.ENGINEERING,
        "family_id": BehaviorFamilyId.FILESYSTEM,
        "provider_id": "native_alma",
        "behavior_classification_coverage": _ratio(9, 10),
        "blocker_explanation_coverage": _ratio(4, 5),
        "failure_attribution_coverage": _ratio(3, 4),
        "prediction_outcome_linkage_coverage": _ratio(6, 8),
        "limitation_documentation_coverage": _ratio(5, 6),
        "contradiction_quality": _ratio(2, 2),
        "observed_behavior_count": 10,
        "classified_behavior_count": 9,
        "explained_blocker_count": 4,
        "unknown_behavior_ids": ["overlapped_io"],
        "unknown_api_names": ["CreateFileMappingW"],
        "attributed_failure_count": 3,
        "unattributed_failure_count": 1,
        "contradictory_evidence_count": 2,
        "evidence_backed_limitations": ["append_existing_file: workspace-confined only"],
        "evidence_snapshot_digest": "snap-knowledge-001",
        "registry_version": "aci_governance_registry_v1",
        "provider_version": "0.2.1-m2",
        "evidence_references": ["evidence-bundle-001"],
    }
    defaults.update(overrides)
    return CompatibilityKnowledgeInput(**defaults)


class TestKnowledgeCoverageFormula:
    def test_complete_six_component_calculation(self):
        report = compute_knowledge_coverage(_full_input())
        assert report.status.value == "computed"
        assert report.knowledge_coverage_value is not None
        assert len(report.components) == 6
        assert all(c.available for c in report.components if c.component_id != "contradiction_quality" or c.denominator > 0)

    def test_exact_approved_weights(self):
        report = compute_knowledge_coverage(_full_input())
        by_id = {c.component_id: c for c in report.components}
        assert KNOWLEDGE_COVERAGE_WEIGHTS_V1 == {
            "behavior_classification_coverage": 0.25,
            "blocker_explanation_coverage": 0.20,
            "failure_attribution_coverage": 0.20,
            "prediction_outcome_linkage_coverage": 0.15,
            "limitation_documentation_coverage": 0.15,
            "contradiction_quality": 0.05,
        }
        assert by_id["behavior_classification_coverage"].raw_weight == 0.25
        assert by_id["contradiction_quality"].raw_weight == 0.05

    def test_missing_component_dropped(self):
        report = compute_knowledge_coverage(
            _full_input(
                failure_attribution_coverage=EvidenceRatio(
                    numerator=0,
                    denominator=0,
                    available=False,
                    insufficient_reason="no_authoritative_failures",
                ),
            )
        )
        failure = next(c for c in report.components if c.component_id == "failure_attribution_coverage")
        assert failure.available is False
        assert failure.effective_weight == 0.0

    def test_available_weights_renormalized(self):
        report = compute_knowledge_coverage(
            _full_input(
                failure_attribution_coverage=EvidenceRatio(numerator=0, denominator=0, available=False),
            )
        )
        available_weight = sum(c.raw_weight for c in report.components if c.available)
        assert available_weight == pytest.approx(0.80)
        assert report.knowledge_coverage_value is not None

    def test_unknown_evidence_is_not_scored_zero(self):
        report = compute_knowledge_coverage(
            _full_input(
                behavior_classification_coverage=EvidenceRatio(
                    numerator=0,
                    denominator=0,
                    available=False,
                    insufficient_reason="unknown_behavior_profile",
                ),
            )
        )
        behavior = next(c for c in report.components if c.component_id == "behavior_classification_coverage")
        assert behavior.available is False
        assert behavior.value is None

    def test_no_components_yields_insufficient_evidence(self):
        unavailable = EvidenceRatio(numerator=0, denominator=0, available=False)
        report = compute_knowledge_coverage(
            _full_input(
                behavior_classification_coverage=unavailable,
                blocker_explanation_coverage=unavailable,
                failure_attribution_coverage=unavailable,
                prediction_outcome_linkage_coverage=unavailable,
                limitation_documentation_coverage=unavailable,
                contradiction_quality=unavailable,
            )
        )
        assert report.status.value == "insufficient_evidence"
        assert report.knowledge_coverage_value is None

    def test_final_score_rounds_to_four_decimals(self):
        report = compute_knowledge_coverage(
            _full_input(
                behavior_classification_coverage=_ratio(1, 3),
                blocker_explanation_coverage=_ratio(1, 3),
                failure_attribution_coverage=_ratio(1, 3),
                prediction_outcome_linkage_coverage=_ratio(1, 3),
                limitation_documentation_coverage=_ratio(1, 3),
                contradiction_quality=_ratio(1, 3),
            )
        )
        decimal_part = str(report.knowledge_coverage_value).split(".")[-1]
        assert len(decimal_part) <= 4

    def test_intermediate_values_not_rounded(self):
        report = compute_knowledge_coverage(_full_input(behavior_classification_coverage=_ratio(1, 3)))
        behavior = next(c for c in report.components if c.component_id == "behavior_classification_coverage")
        assert behavior.value == pytest.approx(1 / 3)

    def test_deterministic_digest(self):
        input_data = _full_input()
        r1 = compute_knowledge_coverage(input_data)
        r2 = compute_knowledge_coverage(input_data)
        assert r1.report_digest == r2.report_digest

    def test_input_ordering_does_not_affect_digest(self):
        r1 = compute_knowledge_coverage(
            _full_input(
                unknown_behavior_ids=["b", "a"],
                unknown_api_names=["Z", "A"],
                evidence_references=["ref-b", "ref-a"],
            )
        )
        r2 = compute_knowledge_coverage(
            _full_input(
                unknown_behavior_ids=["a", "b"],
                unknown_api_names=["A", "Z"],
                evidence_references=["ref-a", "ref-b"],
            )
        )
        assert r1.report_digest == r2.report_digest
        assert r1.unknown_behavior_ids == ["a", "b"]
        assert r1.unknown_api_names == ["A", "Z"]

    def test_generated_at_does_not_affect_digest(self):
        base = compute_knowledge_coverage(_full_input())
        with_ts = base.model_copy(update={"generated_at": "2026-08-05T12:00:00+00:00"})
        assert with_ts.report_digest == base.report_digest

    def test_corpus_changes_digest(self):
        r1 = compute_knowledge_coverage(_full_input(corpus=CorpusKind.ENGINEERING))
        r2 = compute_knowledge_coverage(_full_input(corpus=CorpusKind.REAL_WORLD))
        assert r1.report_digest != r2.report_digest

    def test_family_changes_digest(self):
        r1 = compute_knowledge_coverage(_full_input(family_id=BehaviorFamilyId.FILESYSTEM))
        r2 = compute_knowledge_coverage(_full_input(family_id=BehaviorFamilyId.CONSOLE))
        assert r1.report_digest != r2.report_digest

    def test_provider_changes_digest(self):
        r1 = compute_knowledge_coverage(_full_input(provider_id="native_alma"))
        r2 = compute_knowledge_coverage(_full_input(provider_id="wine"))
        assert r1.report_digest != r2.report_digest

    def test_evidence_snapshot_changes_digest(self):
        r1 = compute_knowledge_coverage(_full_input(evidence_snapshot_digest="snap-a"))
        r2 = compute_knowledge_coverage(_full_input(evidence_snapshot_digest="snap-b"))
        assert r1.report_digest != r2.report_digest

    def test_unknown_behavior_ids_remain_visible(self):
        report = compute_knowledge_coverage(_full_input(unknown_behavior_ids=["overlapped_io", "unknown_x"]))
        assert "overlapped_io" in report.unknown_behavior_ids
        assert "unknown_x" in report.unknown_behavior_ids

    def test_unknown_api_names_remain_visible(self):
        report = compute_knowledge_coverage(_full_input(unknown_api_names=["CreateFileMappingW"]))
        assert report.unknown_api_names == ["CreateFileMappingW"]

    def test_unattributed_failures_remain_visible(self):
        report = compute_knowledge_coverage(_full_input(unattributed_failure_count=3))
        assert report.unattributed_failure_count == 3

    def test_high_knowledge_score_does_not_imply_compatibility(self):
        report = compute_knowledge_coverage(_full_input())
        assert report.knowledge_coverage_value is not None
        assert not hasattr(report, "index_value")
        assert "CompatibilityIndexReport" not in KNOWLEDGE_MODULE.read_text(encoding="utf-8")
        source = ast.parse(KNOWLEDGE_MODULE.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(source)
            if isinstance(node, ast.ImportFrom) and node.module
            for alias in node.names
        }
        assert "alma_bridge.runtime_intelligence.index" not in imported

    def test_compatibility_index_model_not_imported_or_rewritten(self):
        source = KNOWLEDGE_MODULE.read_text(encoding="utf-8")
        assert "compute_compatibility_index" not in source
        assert "CompatibilityIndexInput" not in source

    def test_blocker_without_evidence_cannot_count_as_explained(self):
        assert qualifies_as_explained_blocker(
            has_bounded_classification=True,
            has_evidence_references=False,
            stderr_only=False,
        ) is False

    def test_stderr_only_classification_cannot_count_as_evidence_backed(self):
        assert qualifies_as_explained_blocker(
            has_bounded_classification=True,
            has_evidence_references=True,
            stderr_only=True,
        ) is False

    def test_authoritative_attributed_failure_counts(self):
        assert qualifies_as_attributed_failure(
            authoritative=True,
            attribution_category="unsupported_behavior",
            has_evidence_references=True,
        ) is True

    def test_non_authoritative_failure_does_not_count(self):
        assert qualifies_as_attributed_failure(
            authoritative=False,
            attribution_category="unsupported_behavior",
            has_evidence_references=True,
        ) is False

    def test_documented_limitation_requires_bounded_scope(self):
        assert qualifies_as_documented_limitation(
            has_bounded_scope=True,
            has_unsupported_semantics=True,
            has_profile_or_evidence_ref=True,
        ) is True
        assert qualifies_as_documented_limitation(
            has_bounded_scope=False,
            has_unsupported_semantics=True,
            has_profile_or_evidence_ref=True,
        ) is False

    def test_contradictory_evidence_preserved_improves_contradiction_quality(self):
        report_low = compute_knowledge_coverage(_full_input(contradiction_quality=_ratio(1, 2)))
        report_high = compute_knowledge_coverage(_full_input(contradiction_quality=_ratio(2, 2)))
        low = next(c for c in report_low.components if c.component_id == "contradiction_quality")
        high = next(c for c in report_high.components if c.component_id == "contradiction_quality")
        assert high.value > low.value

    def test_contradictory_evidence_count_remains_visible(self):
        report = compute_knowledge_coverage(_full_input(contradictory_evidence_count=5))
        assert report.contradictory_evidence_count == 5

    def test_zero_contradictions_unavailable_not_perfect_score(self):
        report = compute_knowledge_coverage(_full_input(contradiction_quality=_ratio(0, 0)))
        contradiction = next(c for c in report.components if c.component_id == "contradiction_quality")
        assert contradiction.available is False
        assert contradiction.value is None
        assert contradiction.insufficient_reason == "no_contradictory_evidence_observed"

    def test_numerator_greater_than_denominator_rejected(self):
        with pytest.raises(ValueError):
            EvidenceRatio(numerator=5, denominator=4)

    def test_negative_counts_rejected(self):
        with pytest.raises(ValueError):
            CompatibilityKnowledgeInput(
                corpus=CorpusKind.ENGINEERING,
                family_id=BehaviorFamilyId.FILESYSTEM,
                behavior_classification_coverage=_ratio(1, 1),
                blocker_explanation_coverage=_ratio(1, 1),
                failure_attribution_coverage=_ratio(1, 1),
                prediction_outcome_linkage_coverage=_ratio(1, 1),
                limitation_documentation_coverage=_ratio(1, 1),
                contradiction_quality=_ratio(0, 0),
                observed_behavior_count=-1,
                evidence_snapshot_digest="snap",
            )

    def test_duplicate_evidence_references_deduplicated(self):
        report = compute_knowledge_coverage(
            _full_input(
                evidence_references=["ref-a", "ref-b", "ref-a"],
                behavior_classification_coverage=_ratio(1, 1, evidence_references=["ref-c", "ref-a"]),
            )
        )
        assert report.evidence_references == sorted(set(["ref-a", "ref-b", "ref-c"]))

    def test_duplicate_unknown_api_names_deduplicated(self):
        report = compute_knowledge_coverage(
            _full_input(unknown_api_names=["A", "B", "A"]),
        )
        assert report.unknown_api_names == ["A", "B"]

    def test_report_retains_all_components(self):
        report = compute_knowledge_coverage(_full_input(limitations=["knowledge_not_compatibility"]))
        assert len(report.components) == 6
        assert report.limitations == ["knowledge_not_compatibility"]

    def test_formula_version_exposed(self):
        report = compute_knowledge_coverage(_full_input())
        assert report.formula_version == "knowledge_coverage_v1"
        assert report.schema_version == "runtime_intelligence_knowledge_v1"

    def test_package_imports_no_orchestrator(self):
        source = KNOWLEDGE_MODULE.read_text(encoding="utf-8")
        assert "orchestrator" not in source

    def test_package_imports_no_verification_gateway_mutation(self):
        source = KNOWLEDGE_MODULE.read_text(encoding="utf-8")
        assert "verification_gateway" not in source
        assert "declare_verified_session_success" not in source

    def test_package_cannot_mutate_registry(self):
        source = KNOWLEDGE_MODULE.read_text(encoding="utf-8")
        assert "GovernanceRepository" not in source
        assert "apply_promotion" not in source

    def test_package_cannot_issue_certification(self):
        source = KNOWLEDGE_MODULE.read_text(encoding="utf-8")
        assert "CertificationService" not in source
        assert "issue_certification" not in source

    def test_no_global_knowledge_model_or_function_exists(self):
        source = KNOWLEDGE_MODULE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert "compute_global_knowledge_coverage" not in names

    def test_corpus_remains_mandatory(self):
        with pytest.raises(ValueError):
            CorpusKind("combined")

    def test_knowledge_and_compatibility_are_separate_calculators(self):
        knowledge = compute_knowledge_coverage(_full_input())
        index_input = CompatibilityIndexInput(
            corpus=CorpusKind.ENGINEERING,
            family_id=BehaviorFamilyId.FILESYSTEM,
            provider_id="native_alma",
            behavior_coverage=_ratio(2, 10),
            authoritative_verification_rate=_ratio(1, 10),
            calibration_accuracy=_ratio(1, 10),
            governance_maturity=_ratio(1, 1, value=0.2),
            certification_level=_ratio(1, 1, value=0.15),
            evidence_snapshot_digest="snap-index",
        )
        index = compute_compatibility_index(index_input)
        assert knowledge.knowledge_coverage_value > index.index_value

    def test_compute_knowledge_report_digest_excludes_generated_at(self):
        input_data = _full_input()
        report = compute_knowledge_coverage(input_data)
        digest = compute_knowledge_report_digest(
            corpus=input_data.corpus.value,
            family_id=input_data.family_id.value,
            provider_id=input_data.provider_id,
            components=report.components,
            observed_behavior_count=report.observed_behavior_count,
            classified_behavior_count=report.classified_behavior_count,
            explained_blocker_count=report.explained_blocker_count,
            unknown_behavior_ids=report.unknown_behavior_ids,
            unknown_api_names=report.unknown_api_names,
            attributed_failure_count=report.attributed_failure_count,
            unattributed_failure_count=report.unattributed_failure_count,
            contradictory_evidence_count=report.contradictory_evidence_count,
            evidence_backed_limitations=report.evidence_backed_limitations,
            evidence_references=report.evidence_references,
            registry_version=input_data.registry_version,
            provider_version=input_data.provider_version,
            evidence_snapshot_digest=input_data.evidence_snapshot_digest,
            formula_version=report.formula_version,
            schema_version=report.schema_version,
            knowledge_coverage_value=report.knowledge_coverage_value,
            status=report.status.value,
        )
        assert digest == report.report_digest

    def test_import_knowledge_module_has_no_side_effects(self):
        mod = importlib.import_module("alma_bridge.runtime_intelligence.knowledge")
        assert hasattr(mod, "compute_knowledge_coverage")
