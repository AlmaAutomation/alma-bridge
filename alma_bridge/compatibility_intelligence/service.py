"""Orchestration service for compatibility intelligence."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.compatibility_intelligence.analyzer import analyze_pe
from alma_bridge.compatibility_intelligence.apis import list_registry_entries
from alma_bridge.compatibility_intelligence.capabilities import list_capabilities
from alma_bridge.compatibility_intelligence.coverage import (
    build_required_capabilities,
    classify_all_imports,
    compute_coverage,
)
from alma_bridge.compatibility_intelligence.graph import build_compatibility_graph
from alma_bridge.compatibility_intelligence.imports import build_import_graph, extract_imports
from alma_bridge.compatibility_intelligence.metrics import compute_registry_metrics
from alma_bridge.compatibility_intelligence.models import (
    ACI_SCHEMA_VERSION,
    CompatibilityAnalysisResult,
    ProvenanceEvidence,
    RegistryMetrics,
)
from alma_bridge.compatibility_intelligence.prediction import CompatibilityPredictor
from alma_bridge.compatibility_intelligence.repository import AnalysisRepository


class CompatibilityIntelligenceService:
    """Read-only PE compatibility analysis orchestrator."""

    ENGINE_VERSION = "aci_service_v1"

    def __init__(
        self,
        repository: Optional[AnalysisRepository] = None,
        predictor: Optional[CompatibilityPredictor] = None,
    ) -> None:
        self._repo = repository or AnalysisRepository()
        self._predictor = predictor or CompatibilityPredictor()

    def analyze(self, file_path: str, *, persist: bool = True) -> CompatibilityAnalysisResult:
        path = Path(file_path)
        if not path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")

        parsed, metadata, digest = analyze_pe(str(path))
        provenance = ProvenanceEvidence(
            source="aci_analyzer",
            artifact_id=self.ENGINE_VERSION,
            digest=digest,
            detail="read_only_pe_analysis",
        )

        imports = extract_imports(parsed)
        import_graph = build_import_graph(parsed)
        classifications = classify_all_imports(imports, provenance=provenance)
        required = build_required_capabilities(classifications)

        extra_caps: List[str] = []
        if metadata.has_clr:
            extra_caps.append("dotnet.clr")
        if metadata.subsystem.lower().find("gui") >= 0:
            extra_caps.append("gui.windowing")

        coverage = compute_coverage(classifications, required, extra_capability_ids=extra_caps)
        prediction = self._predictor.predict(coverage, metadata, provenance=provenance)
        graph = build_compatibility_graph(
            str(path),
            digest,
            imports,
            classifications,
            required,
            provenance=provenance,
        )

        analysis_id = sha256_v1(
            {
                "schema": ACI_SCHEMA_VERSION,
                "digest": digest,
                "engine": self.ENGINE_VERSION,
            }
        )

        result = CompatibilityAnalysisResult(
            analysis_id=analysis_id,
            file_path=str(path.resolve()),
            binary_digest=digest,
            metadata=metadata,
            imports=imports,
            import_graph=import_graph,
            api_classifications=classifications,
            required_capabilities=required,
            coverage=coverage,
            prediction=prediction,
            graph=graph,
            provenance=provenance,
        )

        if persist:
            self._repo.save(result)
        return result

    def get_by_digest(self, digest: str) -> Optional[CompatibilityAnalysisResult]:
        return self._repo.get_by_digest(digest)

    def list_history(self, limit: int = 50) -> List[CompatibilityAnalysisResult]:
        return self._repo.list_recent(limit)

    def get_registry_metrics(self) -> RegistryMetrics:
        return compute_registry_metrics()

    def get_capability_registry(self):
        return list_capabilities()

    def get_api_registry(self):
        return list_registry_entries()
