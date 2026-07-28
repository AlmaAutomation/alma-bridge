"""Compatibility Catalog service — read-only application listing."""

from __future__ import annotations

from alma_bridge.catalog.aggregation import CatalogAggregationEngine
from alma_bridge.catalog.models import CatalogNotFoundError, CompatibilityCatalogResponse
from alma_bridge.catalog.repository import ReadOnlyCatalogEvidenceAdapter
from alma_bridge.intelligence.evidence import EvidenceBundleBuilder


class CompatibilityCatalogService:
    """Read-only catalog queries backed by evidence aggregation only."""

    def __init__(
        self,
        repository: ReadOnlyCatalogEvidenceAdapter | None = None,
        engine: CatalogAggregationEngine | None = None,
    ) -> None:
        self._repository = repository or ReadOnlyCatalogEvidenceAdapter()
        self._builder = EvidenceBundleBuilder(self._repository)
        self._engine = engine or CatalogAggregationEngine()

    def list_applications(self) -> CompatibilityCatalogResponse:
        fingerprints = self._repository.list_application_fingerprints()
        if not fingerprints:
            raise CatalogNotFoundError("no applications in catalog")
        return self._engine.build_catalog(fingerprints, self._builder)
