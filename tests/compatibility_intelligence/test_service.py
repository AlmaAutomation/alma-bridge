"""Service orchestration tests."""

from __future__ import annotations

from alma_bridge.compatibility_intelligence.service import CompatibilityIntelligenceService


class TestService:
    def test_analyze_produces_complete_result(self, hello64_path):
        svc = CompatibilityIntelligenceService()
        result = svc.analyze(str(hello64_path), persist=False)
        assert result.analysis_id
        assert result.binary_digest
        assert result.metadata
        assert result.imports
        assert result.api_classifications
        assert result.required_capabilities
        assert result.coverage.total_apis >= 1
        assert result.prediction
        assert result.graph.nodes
        assert result.provenance.source == "aci_analyzer"

    def test_persist_and_retrieve(self, hello64_path, tmp_path):
        from alma_bridge.compatibility_intelligence.repository import AnalysisRepository

        repo = AnalysisRepository(store_dir=tmp_path / "aci")
        svc = CompatibilityIntelligenceService(repository=repo)
        result = svc.analyze(str(hello64_path), persist=True)
        loaded = svc.get_by_digest(result.binary_digest)
        assert loaded is not None
        assert loaded.analysis_id == result.analysis_id

    def test_registry_metrics(self):
        svc = CompatibilityIntelligenceService()
        metrics = svc.get_registry_metrics()
        assert metrics.total_registry_apis >= 18
        assert metrics.capability_count >= 10
        assert "kernel32.dll" in metrics.by_dll

    def test_file_not_found(self):
        svc = CompatibilityIntelligenceService()
        import pytest

        with pytest.raises(FileNotFoundError):
            svc.analyze("/nonexistent/path.exe", persist=False)
