"""Read-only evidence adapter for catalog aggregation."""

from __future__ import annotations

from alma_bridge.intelligence.repository import OutcomesStoreAdapter
from alma_bridge.storage import outcomes


class ReadOnlyCatalogEvidenceAdapter(OutcomesStoreAdapter):
    """Catalog reads over persisted session evidence only."""

    def list_application_fingerprints(self) -> list[str]:
        return outcomes.list_distinct_application_fingerprints()
