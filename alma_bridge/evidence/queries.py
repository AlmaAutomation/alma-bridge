"""Query bundles by binary digest, application fingerprint, etc."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.evidence.models import CompatibilityEvidenceBundle, TimelineEvent
from alma_bridge.evidence.repository import EvidenceRepository


class EvidenceQueries:
    """Read-only query interface for evidence bundles."""

    def __init__(self, repository: Optional[EvidenceRepository] = None) -> None:
        self._repo = repository or EvidenceRepository()

    def by_binary_digest(self, binary_digest: str) -> Optional[CompatibilityEvidenceBundle]:
        return self._repo.get_by_binary_digest(binary_digest)

    def by_application_fingerprint(self, fingerprint: str) -> Optional[CompatibilityEvidenceBundle]:
        return self._repo.get_by_fingerprint(fingerprint)

    def by_bundle_id(self, bundle_id: str) -> Optional[CompatibilityEvidenceBundle]:
        return self._repo.get_bundle(bundle_id)

    def timeline(self, bundle_id: str) -> List[TimelineEvent]:
        return self._repo.list_timeline_events(bundle_id)

    def list_bundle_ids(self) -> List[str]:
        return self._repo.list_all_bundle_ids()
