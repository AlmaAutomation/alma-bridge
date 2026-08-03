"""Prediction engine tests."""

from __future__ import annotations

from alma_bridge.compatibility_intelligence.analyzer import analyze_pe
from alma_bridge.compatibility_intelligence.coverage import (
    build_required_capabilities,
    classify_all_imports,
    compute_coverage,
)
from alma_bridge.compatibility_intelligence.imports import extract_imports
from alma_bridge.compatibility_intelligence.models import ProvenanceEvidence
from alma_bridge.compatibility_intelligence.prediction import CompatibilityPredictor
from alma_bridge.compatibility_intelligence.service import CompatibilityIntelligenceService


class TestPrediction:
    def test_hello64_native_and_wine_compatible(self, hello64_path):
        svc = CompatibilityIntelligenceService()
        result = svc.analyze(str(hello64_path), persist=False)
        assert result.prediction.native_compatible is True
        assert result.prediction.wine_compatible is True
        assert result.prediction.needs_unsupported_apis is False
        assert result.prediction.confidence.score >= 0.75

    def test_gui_api_blocks_native(self):
        from alma_bridge.compatibility_intelligence.models import ImportedFunction

        imports = [ImportedFunction(dll="user32.dll", name="CreateWindowExW")]
        prov = ProvenanceEvidence(source="test", artifact_id="test")
        cls = classify_all_imports(imports, provenance=prov)
        req = build_required_capabilities(cls)
        cov = compute_coverage(cls, req, extra_capability_ids=["gui.windowing"])
        from alma_bridge.compatibility_intelligence.models import PeAnalysisMetadata

        meta = PeAnalysisMetadata(
            architecture="AMD64",
            subsystem="Windows GUI",
            entry_point_rva=0x1000,
            image_size=0x2000,
            is_pe32_plus=True,
            has_tls=False,
            has_relocations=True,
            has_clr=False,
            has_manifest=False,
            has_debug=False,
            has_load_config=False,
            has_exception_directory=False,
            export_count=0,
        )
        pred = CompatibilityPredictor().predict(cov, meta, provenance=prov)
        assert pred.native_compatible is False
        assert pred.wine_compatible is True

    def test_exit_code_fixture(self, exit_code_path):
        svc = CompatibilityIntelligenceService()
        result = svc.analyze(str(exit_code_path), persist=False)
        cap_ids = {r.capability_id for r in result.required_capabilities}
        assert "process.exit" in cap_ids
