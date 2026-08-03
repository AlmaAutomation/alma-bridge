"""Historical replay and version tracking."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.evidence.models import BundleVersion, CompatibilityEvidenceBundle
from alma_bridge.evidence.repository import EvidenceRepository


class EvidenceHistory:
    """Replay prior bundle versions — old predictions retain old registry interpretation."""

    def __init__(self, repository: Optional[EvidenceRepository] = None) -> None:
        self._repo = repository or EvidenceRepository()

    def list_versions(self, bundle_id: str) -> List[BundleVersion]:
        bundle = self._repo.get_bundle(bundle_id)
        if bundle is None:
            return []
        current = BundleVersion(
            version=bundle.version,
            bundle_digest=bundle.bundle_digest,
            created_at=bundle.updated_at,
            event_count=len(self._repo.list_timeline_events(bundle_id)),
            registry_version=(
                bundle.governance.digest if bundle.governance else None
            ),
            prediction_snapshot_id=(
                bundle.prediction_snapshot.artifact_id if bundle.prediction_snapshot else None
            ),
        )
        versions = list(bundle.historical_versions)
        versions.append(current)
        return sorted(versions, key=lambda v: v.version)

    def get_version(self, bundle_id: str, version: int) -> Optional[CompatibilityEvidenceBundle]:
        if version == 0:
            return None
        for snapshot in self._repo.list_bundle_history(bundle_id):
            if snapshot.version == version:
                return snapshot
        current = self._repo.get_bundle(bundle_id)
        if current is not None and current.version == version:
            return current
        return None

    def replay_at_version(
        self,
        bundle_id: str,
        version: int,
    ) -> Optional[CompatibilityEvidenceBundle]:
        """Return bundle state as it existed at a specific version."""
        return self.get_version(bundle_id, version)
