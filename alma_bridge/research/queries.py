"""Read-only evidence queries for research — no mutation."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from alma_bridge.compatibility_intelligence.behavior_requirements import (
    BEHAVIOR_REGISTRY_VERSION,
    list_behavior_profiles,
)
from alma_bridge.compatibility_intelligence.calibration_repository import CalibrationRepository
from alma_bridge.compatibility_intelligence.calibration_service import CalibrationService
from alma_bridge.compatibility_intelligence.expansion.repository import ExpansionPlanRepository
from alma_bridge.compatibility_intelligence.governance.repository import GovernanceRepository
from alma_bridge.compatibility_intelligence.models import (
    CAPABILITY_REGISTRY_VERSION,
    CompatibilityAnalysisResult,
)
from alma_bridge.compatibility_intelligence.repository import AnalysisRepository
from alma_bridge.compatibility_intelligence.apis import REGISTRY_VERSION as API_REGISTRY_VERSION
from alma_bridge.evidence.models import CompatibilityEvidenceBundle, TimelineEvent
from alma_bridge.evidence.queries import EvidenceQueries
from alma_bridge.evidence.repository import EvidenceRepository

from alma_bridge.research.models import TimeWindow


def _parse_ts(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _in_window(ts: Optional[str], window: TimeWindow) -> bool:
    if not ts:
        return window.label == "all_time"
    dt = _parse_ts(ts)
    if dt is None:
        return True
    start = _parse_ts(window.start)
    end = _parse_ts(window.end)
    if start and dt < start:
        return False
    if end and dt > end:
        return False
    return True


class ResearchQueries:
    """Aggregate read-only queries across evidence subsystems."""

    def __init__(
        self,
        *,
        evidence_repo: Optional[EvidenceRepository] = None,
        analysis_repo: Optional[AnalysisRepository] = None,
        calibration_repo: Optional[CalibrationRepository] = None,
        calibration_service: Optional[CalibrationService] = None,
        governance_repo: Optional[GovernanceRepository] = None,
        expansion_repo: Optional[ExpansionPlanRepository] = None,
    ) -> None:
        self._evidence = EvidenceQueries(evidence_repo or EvidenceRepository())
        self._evidence_repo = evidence_repo or EvidenceRepository()
        self._analysis = analysis_repo or AnalysisRepository()
        self._calibration_repo = calibration_repo or CalibrationRepository()
        self._calibration = calibration_service or CalibrationService(self._calibration_repo)
        self._governance = governance_repo or GovernanceRepository()
        self._expansion = expansion_repo or ExpansionPlanRepository()

    def time_window_from_params(
        self,
        *,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> TimeWindow:
        if not start and not end:
            return TimeWindow(label="all_time")
        label_parts = []
        if start:
            label_parts.append(f"from_{start[:10]}")
        if end:
            label_parts.append(f"to_{end[:10]}")
        return TimeWindow(start=start, end=end, label="_".join(label_parts) or "custom")

    def list_bundles(
        self,
        window: TimeWindow,
        *,
        provider_id: Optional[str] = None,
    ) -> List[CompatibilityEvidenceBundle]:
        bundles: List[CompatibilityEvidenceBundle] = []
        for bundle_id in self._evidence.list_bundle_ids():
            bundle = self._evidence.by_bundle_id(bundle_id)
            if bundle is None:
                continue
            if not _in_window(bundle.updated_at, window):
                continue
            bundles.append(bundle)
        return sorted(bundles, key=lambda b: b.updated_at)

    def list_analyses(
        self,
        window: TimeWindow,
        *,
        limit: int = 500,
    ) -> List[CompatibilityAnalysisResult]:
        analyses = self._analysis.list_recent(limit=limit)
        if window.label == "all_time":
            return analyses
        return [a for a in analyses if _in_window(getattr(a, "created_at", None), window)]

    def list_calibration_records(
        self,
        window: TimeWindow,
        *,
        provider_id: Optional[str] = None,
        limit: int = 500,
    ) -> List[dict]:
        records = self._calibration.list_records(limit=limit)
        filtered: List[dict] = []
        for record in records:
            if not _in_window(record.get("created_at"), window):
                continue
            if provider_id and record.get("provider_id") != provider_id:
                continue
            filtered.append(record)
        return filtered

    def list_timeline_events(
        self,
        window: TimeWindow,
        *,
        event_type: Optional[str] = None,
    ) -> List[Tuple[str, TimelineEvent]]:
        events: List[Tuple[str, TimelineEvent]] = []
        for bundle_id in self._evidence.list_bundle_ids():
            for event in self._evidence.timeline(bundle_id):
                if event_type and event.event_type.value != event_type:
                    continue
                if not _in_window(event.timestamp, window):
                    continue
                events.append((bundle_id, event))
        return sorted(events, key=lambda item: item[1].timestamp)

    def registry_version(self) -> str:
        try:
            version = self._governance.get_current_version()
            return version.version_id
        except Exception:
            return CAPABILITY_REGISTRY_VERSION

    def provider_versions(self) -> Dict[str, str]:
        versions: Dict[str, str] = {}
        for profile in list_behavior_profiles():
            key = profile.provider_id
            if key not in versions or profile.implementation_version > versions[key]:
                versions[key] = profile.implementation_version
        return versions

    def api_registry_version(self) -> str:
        return API_REGISTRY_VERSION

    def behavior_registry_version(self) -> str:
        return BEHAVIOR_REGISTRY_VERSION

    def list_governance_versions(self) -> List[dict]:
        try:
            versions = self._governance.list_versions()
            return [
                {
                    "version_id": v.version_id,
                    "created_at": v.created_at,
                    "entry_count": len(v.entries),
                    "parent_version_id": v.parent_version_id,
                    "change_summary": v.change_summary,
                }
                for v in versions
            ]
        except Exception:
            return []

    def list_governance_proposals(self, limit: int = 500) -> List[dict]:
        try:
            return self._governance.list_proposals(limit=limit)
        except Exception:
            return []

    def get_expansion_plan(self):
        return self._expansion.get_latest_plan()

    def list_snapshots(self, limit: int = 500) -> list:
        return self._calibration_repo.list_snapshots(limit=limit)
