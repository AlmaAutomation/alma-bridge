"""Compatibility graph tests."""

from __future__ import annotations

from alma_bridge.compatibility_intelligence.coverage import (
    build_required_capabilities,
    classify_all_imports,
)
from alma_bridge.compatibility_intelligence.graph import build_compatibility_graph
from alma_bridge.compatibility_intelligence.models import ImportedFunction, ProvenanceEvidence


class TestGraph:
    def test_graph_has_provenance_on_all_nodes(self):
        imports = [
            ImportedFunction(dll="kernel32.dll", name="WriteFile"),
        ]
        prov = ProvenanceEvidence(source="test", artifact_id="test", digest="abc")
        cls = classify_all_imports(imports, provenance=prov)
        req = build_required_capabilities(cls)
        graph = build_compatibility_graph(
            "/tmp/hello64.exe",
            "abc123",
            imports,
            cls,
            req,
            provenance=prov,
        )
        assert graph.nodes
        assert graph.edges
        for node in graph.nodes:
            assert node.provenance.source == "test"
        for edge in graph.edges:
            assert edge.provenance.source == "test"

    def test_graph_links_api_to_capability(self):
        imports = [ImportedFunction(dll="kernel32.dll", name="ExitProcess")]
        prov = ProvenanceEvidence(source="test", artifact_id="test")
        cls = classify_all_imports(imports, provenance=prov)
        req = build_required_capabilities(cls)
        graph = build_compatibility_graph(
            "/tmp/test.exe", "digest", imports, cls, req, provenance=prov
        )
        relations = {e.relation for e in graph.edges}
        assert "requires" in relations
        assert "imports" in relations
