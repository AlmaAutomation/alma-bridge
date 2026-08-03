"""Coverage calculation tests."""

from __future__ import annotations

from alma_bridge.compatibility_intelligence.apis import classify_import
from alma_bridge.compatibility_intelligence.coverage import (
    build_required_capabilities,
    classify_all_imports,
    compute_coverage,
)
from alma_bridge.compatibility_intelligence.models import ImportedFunction, ProvenanceEvidence


def _prov() -> ProvenanceEvidence:
    return ProvenanceEvidence(source="test", artifact_id="test")


class TestCoverage:
    def test_hello64_native_full_coverage(self, hello64_path):
        imports = [
            ImportedFunction(dll="kernel32.dll", name="GetStdHandle"),
            ImportedFunction(dll="kernel32.dll", name="WriteFile"),
            ImportedFunction(dll="kernel32.dll", name="ExitProcess"),
        ]
        classifications = classify_all_imports(imports, provenance=_prov())
        required = build_required_capabilities(classifications)
        coverage = compute_coverage(classifications, required)

        native = coverage.providers["native_alma"]
        assert native.coverage_percent == 100.0
        assert native.unsupported == 0
        assert native.unknown == 0
        assert coverage.unknown_apis == 0

    def test_unknown_api_reduces_known_count(self):
        imports = [
            ImportedFunction(dll="kernel32.dll", name="WriteFile"),
            ImportedFunction(dll="kernel32.dll", name="UnknownApiXYZ"),
        ]
        classifications = classify_all_imports(imports, provenance=_prov())
        required = build_required_capabilities(classifications)
        coverage = compute_coverage(classifications, required)

        assert coverage.known_apis == 1
        assert coverage.unknown_apis == 1
        assert "kernel32.dll!UnknownApiXYZ" in coverage.unknown_api_names

    def test_gui_subsystem_adds_capability(self):
        imports = [
            ImportedFunction(dll="user32.dll", name="CreateWindowExW"),
        ]
        classifications = classify_all_imports(imports, provenance=_prov())
        required = build_required_capabilities(classifications)
        coverage = compute_coverage(
            classifications,
            required,
            extra_capability_ids=["gui.windowing"],
        )
        native = coverage.providers["native_alma"]
        assert native.unsupported >= 1
        wine = coverage.providers["wine"]
        assert wine.supported >= 1

    def test_malformed_ordinal_handled(self):
        result = classify_import("kernel32.dll", "ordinal_999")
        assert result.is_known is False
