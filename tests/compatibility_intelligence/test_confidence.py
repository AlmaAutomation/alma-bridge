"""Deterministic confidence scoring tests."""

from __future__ import annotations

from alma_bridge.compatibility_intelligence.confidence import ConfidenceScorer
from alma_bridge.compatibility_intelligence.coverage import (
    build_required_capabilities,
    classify_all_imports,
    compute_coverage,
)
from alma_bridge.compatibility_intelligence.models import (
    ConfidenceLevelName,
    ImportedFunction,
    ProvenanceEvidence,
)


class TestConfidence:
    def test_full_coverage_very_high(self):
        imports = [
            ImportedFunction(dll="kernel32.dll", name="WriteFile"),
            ImportedFunction(dll="kernel32.dll", name="ExitProcess"),
        ]
        prov = ProvenanceEvidence(source="test", artifact_id="test")
        cls = classify_all_imports(imports, provenance=prov)
        req = build_required_capabilities(cls)
        cov = compute_coverage(cls, req)
        scorer = ConfidenceScorer()
        assessment = scorer.score(cov, provider_id="native_alma")
        assert assessment.score >= 0.75
        assert assessment.level in {
            ConfidenceLevelName.VERY_HIGH,
            ConfidenceLevelName.HIGH,
        }

    def test_unknown_apis_lower_confidence(self):
        imports = [
            ImportedFunction(dll="kernel32.dll", name="WriteFile"),
            ImportedFunction(dll="kernel32.dll", name="TotallyUnknown"),
        ]
        prov = ProvenanceEvidence(source="test", artifact_id="test")
        cls = classify_all_imports(imports, provenance=prov)
        req = build_required_capabilities(cls)
        cov = compute_coverage(cls, req)
        full_imports = [ImportedFunction(dll="kernel32.dll", name="WriteFile")]
        full_cls = classify_all_imports(full_imports, provenance=prov)
        full_req = build_required_capabilities(full_cls)
        full_cov = compute_coverage(full_cls, full_req)

        scorer = ConfidenceScorer()
        low = scorer.score(cov, provider_id="native_alma")
        high = scorer.score(full_cov, provider_id="native_alma")
        assert low.score <= high.score

    def test_historical_verification_boost(self):
        imports = [ImportedFunction(dll="kernel32.dll", name="WriteFile")]
        prov = ProvenanceEvidence(source="test", artifact_id="test")
        cls = classify_all_imports(imports, provenance=prov)
        req = build_required_capabilities(cls)
        cov = compute_coverage(cls, req)
        scorer = ConfidenceScorer()
        base = scorer.score(cov, provider_id="native_alma")
        boosted = scorer.score(cov, provider_id="native_alma", historical_verification=True)
        assert boosted.score >= base.score
