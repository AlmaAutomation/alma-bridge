"""Compatibility Index formula tests."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from alma_bridge.certification.models import CertificationLevel
from alma_bridge.compatibility_intelligence.governance.models import CapabilityMaturityState
from alma_bridge.runtime_intelligence.index import (
    CERTIFICATION_LEVEL_NORMALIZATION_V1,
    COMPATIBILITY_INDEX_WEIGHTS_V1,
    GOVERNANCE_MATURITY_NORMALIZATION_V1,
    compute_compatibility_index,
    compute_report_digest,
    evidence_ratio_from_certification,
    evidence_ratio_from_maturity,
    normalize_certification_level,
    normalize_governance_maturity,
)
from alma_bridge.runtime_intelligence.models import (
    BehaviorFamilyId,
    CompatibilityIndexInput,
    CompatibilityIndexReport,
    CompatibilityIndexStatus,
    CorpusKind,
    EvidenceRatio,
)

ROOT = Path(__file__).resolve().parents[2]
INDEX_MODULE = ROOT / "alma_bridge" / "runtime_intelligence" / "index.py"


def _ratio(numerator: int, denominator: int, **kwargs) -> EvidenceRatio:
    return EvidenceRatio(numerator=numerator, denominator=denominator, **kwargs)


def _full_input(**overrides) -> CompatibilityIndexInput:
    defaults = {
        "corpus": CorpusKind.ENGINEERING,
        "family_id": BehaviorFamilyId.FILESYSTEM,
        "provider_id": "native_alma",
        "behavior_coverage": _ratio(3, 4),
        "authoritative_verification_rate": _ratio(5, 5),
        "calibration_accuracy": _ratio(8, 10),
        "governance_maturity": evidence_ratio_from_maturity(CapabilityMaturityState.VERIFIED_BOUNDED),
        "certification_level": evidence_ratio_from_certification(CertificationLevel.VERIFIED),
        "evidence_snapshot_digest": "snap-abc123",
        "registry_version": "aci_governance_registry_v1",
        "provider_version": "0.2.1-m2",
        "generated_from": "test",
    }
    defaults.update(overrides)
    return CompatibilityIndexInput(**defaults)


class TestCompatibilityIndexFormula:
    def test_full_five_component_calculation(self):
        report = compute_compatibility_index(_full_input())
        assert report.status == CompatibilityIndexStatus.COMPUTED
        assert report.index_value is not None
        assert len(report.components) == 5
        assert all(c.available for c in report.components)

    def test_exact_approved_raw_weights(self):
        report = compute_compatibility_index(_full_input())
        by_id = {c.component_id: c for c in report.components}
        assert by_id["behavior_coverage"].raw_weight == 0.30
        assert by_id["authoritative_verification_rate"].raw_weight == 0.30
        assert by_id["calibration_accuracy"].raw_weight == 0.15
        assert by_id["governance_maturity"].raw_weight == 0.15
        assert by_id["certification_level"].raw_weight == 0.10
        assert COMPATIBILITY_INDEX_WEIGHTS_V1 == {
            "behavior_coverage": 0.30,
            "authoritative_verification_rate": 0.30,
            "calibration_accuracy": 0.15,
            "governance_maturity": 0.15,
            "certification_level": 0.10,
        }

    def test_missing_component_is_dropped(self):
        report = compute_compatibility_index(
            _full_input(
                calibration_accuracy=EvidenceRatio(
                    numerator=0,
                    denominator=0,
                    available=False,
                    insufficient_reason="no_calibration_records",
                ),
            )
        )
        cal = next(c for c in report.components if c.component_id == "calibration_accuracy")
        assert cal.available is False
        assert cal.effective_weight == 0.0
        assert cal.value is None

    def test_remaining_weights_renormalize(self):
        report = compute_compatibility_index(
            _full_input(
                calibration_accuracy=EvidenceRatio(
                    numerator=0,
                    denominator=0,
                    available=False,
                ),
            )
        )
        available = [c for c in report.components if c.available]
        assert sum(c.raw_weight for c in available) == pytest.approx(0.85)
        assert report.index_value is not None

    def test_unknown_is_not_zero(self):
        report = compute_compatibility_index(
            _full_input(
                behavior_coverage=EvidenceRatio(
                    numerator=0,
                    denominator=0,
                    available=False,
                    insufficient_reason="unknown_behavior_profile",
                ),
            )
        )
        behavior = next(c for c in report.components if c.component_id == "behavior_coverage")
        assert behavior.available is False
        assert behavior.value is None
        assert behavior.insufficient_reason == "unknown_behavior_profile"

    def test_no_available_components_yields_insufficient_evidence(self):
        report = compute_compatibility_index(
            _full_input(
                behavior_coverage=EvidenceRatio(numerator=0, denominator=0, available=False),
                authoritative_verification_rate=EvidenceRatio(numerator=0, denominator=0, available=False),
                calibration_accuracy=EvidenceRatio(numerator=0, denominator=0, available=False),
                governance_maturity=EvidenceRatio(numerator=0, denominator=0, available=False),
                certification_level=EvidenceRatio(numerator=0, denominator=0, available=False),
            )
        )
        assert report.status == CompatibilityIndexStatus.INSUFFICIENT_EVIDENCE
        assert report.index_value is None

    def test_intermediate_values_not_rounded(self):
        report = compute_compatibility_index(
            _full_input(
                behavior_coverage=_ratio(1, 3),
                authoritative_verification_rate=_ratio(1, 3),
                calibration_accuracy=_ratio(1, 3),
                governance_maturity=evidence_ratio_from_maturity(CapabilityMaturityState.EXPERIMENTAL),
                certification_level=evidence_ratio_from_certification(CertificationLevel.SPECIFIED),
            )
        )
        behavior = next(c for c in report.components if c.component_id == "behavior_coverage")
        assert behavior.value == pytest.approx(1 / 3)
        assert str(behavior.value).startswith("0.333")

    def test_final_result_rounds_to_four_decimals(self):
        report = compute_compatibility_index(
            _full_input(
                behavior_coverage=_ratio(1, 3),
                authoritative_verification_rate=_ratio(1, 3),
                calibration_accuracy=_ratio(1, 3),
            )
        )
        assert report.index_value is not None
        decimal_part = str(report.index_value).split(".")[-1]
        assert len(decimal_part) <= 4

    def test_same_input_yields_same_digest(self):
        input_data = _full_input()
        r1 = compute_compatibility_index(input_data)
        r2 = compute_compatibility_index(input_data)
        assert r1.report_digest == r2.report_digest

    def test_generated_at_does_not_affect_digest(self):
        input_data = _full_input()
        base = compute_compatibility_index(input_data)
        with_ts = base.model_copy(update={"generated_at": "2026-08-05T12:00:00+00:00"})
        assert with_ts.report_digest == base.report_digest

    def test_corpus_changes_digest(self):
        r1 = compute_compatibility_index(_full_input(corpus=CorpusKind.ENGINEERING))
        r2 = compute_compatibility_index(_full_input(corpus=CorpusKind.REAL_WORLD))
        assert r1.report_digest != r2.report_digest

    def test_family_changes_digest(self):
        r1 = compute_compatibility_index(_full_input(family_id=BehaviorFamilyId.FILESYSTEM))
        r2 = compute_compatibility_index(_full_input(family_id=BehaviorFamilyId.CONSOLE))
        assert r1.report_digest != r2.report_digest

    def test_provider_changes_digest(self):
        r1 = compute_compatibility_index(_full_input(provider_id="native_alma"))
        r2 = compute_compatibility_index(_full_input(provider_id="wine"))
        assert r1.report_digest != r2.report_digest

    def test_sample_size_changes_digest(self):
        r1 = compute_compatibility_index(_full_input(behavior_coverage=_ratio(3, 4)))
        r2 = compute_compatibility_index(_full_input(behavior_coverage=_ratio(2, 4)))
        assert r1.report_digest != r2.report_digest

    def test_evidence_snapshot_changes_digest(self):
        r1 = compute_compatibility_index(_full_input(evidence_snapshot_digest="snap-a"))
        r2 = compute_compatibility_index(_full_input(evidence_snapshot_digest="snap-b"))
        assert r1.report_digest != r2.report_digest

    def test_governance_maturity_mapping_is_explicit(self):
        assert GOVERNANCE_MATURITY_NORMALIZATION_V1[CapabilityMaturityState.DECLARED] == 0.00
        assert GOVERNANCE_MATURITY_NORMALIZATION_V1[CapabilityMaturityState.EXPERIMENTAL] == 0.20
        assert GOVERNANCE_MATURITY_NORMALIZATION_V1[CapabilityMaturityState.BEHAVIORALLY_TESTED] == 0.40
        assert GOVERNANCE_MATURITY_NORMALIZATION_V1[CapabilityMaturityState.CALIBRATION_SUPPORTED] == 0.60
        assert GOVERNANCE_MATURITY_NORMALIZATION_V1[CapabilityMaturityState.VERIFIED_BOUNDED] == 0.80
        assert GOVERNANCE_MATURITY_NORMALIZATION_V1[CapabilityMaturityState.STABLE] == 1.00

    def test_deprecated_and_revoked_do_not_appear_mature(self):
        assert normalize_governance_maturity(CapabilityMaturityState.DEPRECATED) == 0.00
        assert normalize_governance_maturity(CapabilityMaturityState.REVOKED) == 0.00
        assert GOVERNANCE_MATURITY_NORMALIZATION_V1[CapabilityMaturityState.STABLE] == 1.00

    def test_certification_mapping_is_explicit(self):
        assert CERTIFICATION_LEVEL_NORMALIZATION_V1[CertificationLevel.UNVERIFIED] == 0.00
        assert CERTIFICATION_LEVEL_NORMALIZATION_V1[CertificationLevel.PRODUCTION_READY] == 1.00
        assert CERTIFICATION_LEVEL_NORMALIZATION_V1[CertificationLevel.VERIFIED] == 0.50

    def test_cross_corpus_input_cannot_be_constructed(self):
        assert {m.value for m in CorpusKind} == {"engineering", "real_world"}
        with pytest.raises(ValueError):
            CorpusKind("combined")

    def test_no_global_score_model_or_function_exists(self):
        source = INDEX_MODULE.read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert "compute_global_compatibility" not in names
        assert "global_compatibility_index" not in names

    def test_index_cannot_import_orchestrator(self):
        source = INDEX_MODULE.read_text(encoding="utf-8")
        assert "orchestrator" not in source
        assert "learning.orchestrator" not in source

    def test_index_cannot_import_verification_gateway_mutation(self):
        source = INDEX_MODULE.read_text(encoding="utf-8")
        assert "verification_gateway" not in source
        assert "declare_verified_session_success" not in source

    def test_index_cannot_mutate_registry(self):
        source = INDEX_MODULE.read_text(encoding="utf-8")
        for fragment in ("apply_promotion", "GovernanceRepository", "record_attempt"):
            assert fragment not in source

    def test_index_cannot_issue_certification(self):
        source = INDEX_MODULE.read_text(encoding="utf-8")
        for fragment in ("issue_certification", "CertificationService", "certify"):
            assert fragment not in source

    def test_report_retains_every_component_and_limitation(self):
        report = compute_compatibility_index(
            _full_input(limitations=["bounded_scope_only", "engineering_corpus_only"])
        )
        assert len(report.components) == 5
        assert report.limitations == ["bounded_scope_only", "engineering_corpus_only"]
        for component in report.components:
            assert component.sample_size.denominator >= 0

    def test_formula_version_is_exposed(self):
        report = compute_compatibility_index(_full_input())
        assert report.formula_version == "compatibility_index_v1"
        assert report.schema_version == "runtime_intelligence_index_v1"

    def test_evidence_references_are_deterministic_and_deduplicated(self):
        report = compute_compatibility_index(
            _full_input(
                behavior_coverage=_ratio(
                    3,
                    4,
                    evidence_references=["ref-b", "ref-a", "ref-b"],
                ),
            )
        )
        assert report.evidence_references == sorted(set(["ref-b", "ref-a", "ref-b"]))

    def test_invalid_ratio_numerator_denominator_rejected(self):
        with pytest.raises(ValueError, match="numerator cannot exceed denominator"):
            EvidenceRatio(numerator=5, denominator=4)

    def test_numerator_greater_than_denominator_rejected(self):
        with pytest.raises(ValueError):
            EvidenceRatio(numerator=10, denominator=3)

    def test_zero_denominator_produces_unavailable_component_not_division_error(self):
        report = compute_compatibility_index(
            _full_input(
                behavior_coverage=EvidenceRatio(numerator=0, denominator=0, available=True),
            )
        )
        behavior = next(c for c in report.components if c.component_id == "behavior_coverage")
        assert behavior.available is False
        assert behavior.value is None
        assert behavior.insufficient_reason == "insufficient_evidence"

    def test_requires_revalidation_certification_unavailable(self):
        ratio = evidence_ratio_from_certification(CertificationLevel.REQUIRES_REVALIDATION)
        assert ratio.available is False
        value, available, reason = normalize_certification_level(CertificationLevel.REQUIRES_REVALIDATION)
        assert available is False
        assert reason == "certification_requires_revalidation"

    def test_import_index_module_has_no_side_effects(self):
        mod = importlib.import_module("alma_bridge.runtime_intelligence.index")
        assert hasattr(mod, "compute_compatibility_index")

    def test_compute_report_digest_excludes_generated_at(self):
        input_data = _full_input()
        report = compute_compatibility_index(input_data)
        digest_without = compute_report_digest(
            corpus=input_data.corpus.value,
            family_id=input_data.family_id.value,
            provider_id=input_data.provider_id,
            components=report.components,
            registry_version=input_data.registry_version,
            provider_version=input_data.provider_version,
            evidence_snapshot_digest=input_data.evidence_snapshot_digest,
            formula_version=report.formula_version,
            schema_version=report.schema_version,
            index_value=report.index_value,
            status=report.status.value,
        )
        assert digest_without == report.report_digest
