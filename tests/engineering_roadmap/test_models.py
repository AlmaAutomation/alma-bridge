"""Tests for Engineering Roadmap Generator foundation models and digests."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import ValidationError

from alma_bridge.compatibility_intelligence.expansion.models import (
    ComplexityAssessment,
    EngineeringComplexityLevel,
    EvidenceQualityLevel,
    SecurityRiskAssessment,
    SemanticRiskAssessment,
)
from alma_bridge.engineering_roadmap import (
    ENGINEERING_ROADMAP_ENGINE_VERSION,
    ENGINEERING_ROADMAP_FORMULA_VERSION,
    ENGINEERING_ROADMAP_SCHEMA_VERSION,
    EngineeringRoadmapError,
    EngineeringRoadmapOpportunity,
    EngineeringRoadmapReport,
    InsufficientEvidenceError,
    OpportunityNotFoundError,
    RoadmapOpportunityStatus,
    compute_opportunity_digest,
    compute_opportunity_id,
    compute_report_digest,
)
from alma_bridge.runtime_intelligence.models import BehaviorFamilyId, CorpusKind

ROOT = Path(__file__).resolve().parents[2]
ROADMAP_DIR = ROOT / "alma_bridge" / "engineering_roadmap"

EVIDENCE_SNAPSHOT = "evidence-snapshot-abc123"


def _sample_opportunity(**overrides) -> EngineeringRoadmapOpportunity:
    defaults = {
        "opportunity_id": "opp-placeholder",
        "corpus": CorpusKind.ENGINEERING,
        "provider_id": "native_alma",
        "family_id": BehaviorFamilyId.FILESYSTEM,
        "capability_id": "filesystem.basic_io",
        "behavior_id": "append_existing_file",
        "bounded_scope": "native_alma / PE64 console / OPEN_EXISTING append",
        "title": "Append to existing file",
        "summary": "Bounded append behavior for engineering corpus fixtures.",
        "distinct_applications_blocked": 2,
        "distinct_binaries_blocked": 2,
        "application_classes_blocked": ["fixture"],
        "blocked_session_count": 1,
        "application_mentions": 3,
        "predicted_applications_unlocked": 1,
        "predicted_application_classes_unlocked": 1,
        "engineering_complexity": ComplexityAssessment(
            level=EngineeringComplexityLevel.MEDIUM,
            score=0.55,
            factors=["handle_lifecycle"],
        ),
        "implementation_risk": 0.4,
        "security_risk": SecurityRiskAssessment(score=0.2),
        "semantic_risk": SemanticRiskAssessment(score=0.15),
        "fixture_availability": True,
        "verification_readiness": "partial",
        "evidence_quality": EvidenceQualityLevel.MODERATE,
        "engineering_confidence": "medium",
        "engineering_confidence_factors": ["distinct_apps=2"],
        "existing_expansion_score": 0.62,
        "compatibility_impact_score": 0.58,
        "opportunity_status": RoadmapOpportunityStatus.PRELIMINARY,
        "prerequisites": ["filesystem.basic_io/create_always_write"],
        "affected_application_fingerprints": ["file_append_unsupported.exe"],
        "affected_binary_digests": ["digest-a", "digest-b"],
        "source_expansion_candidate_ids": ["candidate-001"],
        "evidence_references": ["fixture:file_append_unsupported.exe"],
        "evidence_snapshot_digest": EVIDENCE_SNAPSHOT,
        "registry_version": "gov-registry-v1",
        "provider_version": "0.2.1-m2",
        "digest": "digest-placeholder",
    }
    defaults.update(overrides)
    return EngineeringRoadmapOpportunity(**defaults)


class TestEngineeringRoadmapSchemaConstants:
    def test_schema_version_constants(self):
        assert ENGINEERING_ROADMAP_SCHEMA_VERSION == "engineering_roadmap_v1"
        assert ENGINEERING_ROADMAP_FORMULA_VERSION == "engineering_roadmap_composition_v1"
        assert ENGINEERING_ROADMAP_ENGINE_VERSION == "engineering_roadmap_service_v1"


class TestEngineeringRoadmapEnums:
    def test_opportunity_status_values(self):
        assert RoadmapOpportunityStatus.RANKABLE.value == "rankable"
        assert RoadmapOpportunityStatus.DESCRIPTIVE_ONLY.value == "descriptive_only"

    def test_invalid_opportunity_status_rejected(self):
        with pytest.raises(ValidationError):
            _sample_opportunity(opportunity_status="approved")


class TestEngineeringRoadmapOpportunityModel:
    def test_required_fields_validate(self):
        opportunity = _sample_opportunity()
        assert opportunity.provider_id == "native_alma"
        assert opportunity.schema_version == ENGINEERING_ROADMAP_SCHEMA_VERSION
        assert opportunity.formula_version == ENGINEERING_ROADMAP_FORMULA_VERSION

    def test_score_bounds_enforced(self):
        with pytest.raises(ValidationError):
            _sample_opportunity(existing_expansion_score=1.5)

    def test_compatibility_impact_score_may_be_null(self):
        opportunity = _sample_opportunity(compatibility_impact_score=None)
        assert opportunity.compatibility_impact_score is None


class TestEngineeringRoadmapReportModel:
    def test_report_model_fields(self):
        opportunity = _sample_opportunity(
            digest=compute_opportunity_digest(_sample_opportunity()),
        )
        report = EngineeringRoadmapReport(
            corpus=CorpusKind.ENGINEERING,
            provider_id="native_alma",
            generated_at="2026-08-01T00:00:00+00:00",
            evidence_snapshot_digest=EVIDENCE_SNAPSHOT,
            opportunities=[opportunity],
            blocked_application_count=2,
            explained_blocker_count=10,
            unexplained_blocker_count=1,
            limitations=["advisory only"],
            evidence_references=["fixture:file_append_unsupported.exe"],
            report_digest="report-digest-placeholder",
        )
        assert report.engine_version == ENGINEERING_ROADMAP_ENGINE_VERSION
        assert len(report.opportunities) == 1


class TestEngineeringRoadmapDigests:
    def test_opportunity_id_is_deterministic(self):
        kwargs = {
            "corpus": CorpusKind.ENGINEERING,
            "provider_id": "native_alma",
            "family_id": BehaviorFamilyId.FILESYSTEM,
            "capability_id": "filesystem.basic_io",
            "behavior_id": "append_existing_file",
            "bounded_scope": "native_alma / append",
            "evidence_snapshot_digest": EVIDENCE_SNAPSHOT,
        }
        first = compute_opportunity_id(**kwargs)
        second = compute_opportunity_id(**kwargs)
        assert first == second
        assert len(first) == 64

    def test_opportunity_digest_ignores_list_order(self):
        base = _sample_opportunity()
        ordered = compute_opportunity_digest(
            base.model_copy(
                update={
                    "prerequisites": ["a", "b", "c"],
                    "evidence_references": ["ref-1", "ref-2"],
                }
            )
        )
        shuffled = compute_opportunity_digest(
            base.model_copy(
                update={
                    "prerequisites": ["c", "a", "b"],
                    "evidence_references": ["ref-2", "ref-1"],
                }
            )
        )
        assert ordered == shuffled

    def test_opportunity_digest_changes_on_semantic_change(self):
        base = _sample_opportunity()
        original = compute_opportunity_digest(base)
        changed = compute_opportunity_digest(
            base.model_copy(update={"predicted_applications_unlocked": 99})
        )
        assert original != changed

    def test_report_digest_excludes_generated_at(self):
        opportunity = _sample_opportunity(
            digest=compute_opportunity_digest(_sample_opportunity()),
        )
        common = {
            "corpus": CorpusKind.ENGINEERING,
            "provider_id": "native_alma",
            "opportunities": [opportunity],
            "blocked_application_count": 2,
            "explained_blocker_count": 10,
            "unexplained_blocker_count": 1,
            "limitations": ["advisory only"],
            "evidence_references": ["fixture:file_append_unsupported.exe"],
            "evidence_snapshot_digest": EVIDENCE_SNAPSHOT,
        }
        first = compute_report_digest(**common)
        # generated_at is not an input to compute_report_digest
        assert first == compute_report_digest(**common)

    def test_report_digest_stable_for_reordered_opportunities(self):
        opp_a = _sample_opportunity(
            title="A",
            digest=compute_opportunity_digest(_sample_opportunity(title="A")),
        )
        opp_b = _sample_opportunity(
            title="B",
            digest=compute_opportunity_digest(_sample_opportunity(title="B")),
        )
        kwargs = {
            "corpus": CorpusKind.ENGINEERING,
            "provider_id": "native_alma",
            "blocked_application_count": 0,
            "explained_blocker_count": 0,
            "unexplained_blocker_count": 0,
            "limitations": [],
            "evidence_references": [],
            "evidence_snapshot_digest": EVIDENCE_SNAPSHOT,
        }
        forward = compute_report_digest(opportunities=[opp_a, opp_b], **kwargs)
        reverse = compute_report_digest(opportunities=[opp_b, opp_a], **kwargs)
        assert forward == reverse


class TestEngineeringRoadmapErrors:
    def test_error_hierarchy(self):
        assert issubclass(InsufficientEvidenceError, EngineeringRoadmapError)
        assert issubclass(OpportunityNotFoundError, EngineeringRoadmapError)

    def test_errors_are_plain_exceptions(self):
        assert InsufficientEvidenceError("x")
        assert OpportunityNotFoundError("missing")


class TestEngineeringRoadmapImportBoundaries:
    FORBIDDEN_IMPORT_PREFIXES = (
        "alma_bridge.learning.orchestrator",
        "alma_bridge.execution",
        "alma_bridge.cli",
        "alma_bridge.api",
        "fastapi",
    )

    def test_commit1_modules_avoid_forbidden_imports(self):
        for module_path in (
            ROADMAP_DIR / "__init__.py",
            ROADMAP_DIR / "models.py",
            ROADMAP_DIR / "digest.py",
            ROADMAP_DIR / "errors.py",
        ):
            tree = ast.parse(module_path.read_text(encoding="utf-8"))
            imports = [
                node
                for node in ast.walk(tree)
                if isinstance(node, (ast.Import, ast.ImportFrom))
            ]
            for node in imports:
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                else:
                    names = [node.module or ""]
                for name in names:
                    for forbidden in self.FORBIDDEN_IMPORT_PREFIXES:
                        assert not name.startswith(forbidden), (
                            f"{module_path.name} imports forbidden module {name}"
                        )
