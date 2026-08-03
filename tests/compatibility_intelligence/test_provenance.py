"""Evidence provenance tests."""

from __future__ import annotations

from alma_bridge.compatibility_intelligence.service import CompatibilityIntelligenceService


class TestProvenance:
    def test_all_classifications_have_provenance(self, hello64_path):
        svc = CompatibilityIntelligenceService()
        result = svc.analyze(str(hello64_path), persist=False)
        for cls in result.api_classifications:
            assert cls.provenance.source
            assert cls.provenance.artifact_id

    def test_analysis_provenance_includes_digest(self, hello64_path):
        svc = CompatibilityIntelligenceService()
        result = svc.analyze(str(hello64_path), persist=False)
        assert result.provenance.digest == result.binary_digest

    def test_graph_evidence_chain(self, hello64_path):
        svc = CompatibilityIntelligenceService()
        result = svc.analyze(str(hello64_path), persist=False)
        app_nodes = [n for n in result.graph.nodes if n.node_type == "application"]
        cap_nodes = [n for n in result.graph.nodes if n.node_type == "capability"]
        assert app_nodes
        assert cap_nodes
