"""Deterministic demand aggregation — no double-counting sessions per binary."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from alma_bridge.compatibility_intelligence.expansion.models import DemandCounts


@dataclass
class DemandEvidence:
    """Accumulated evidence for one scoped candidate key."""

    binary_digests: Set[str] = field(default_factory=set)
    application_fingerprints: Set[str] = field(default_factory=set)
    analysis_digests: Set[str] = field(default_factory=set)
    blocked_sessions: Set[str] = field(default_factory=set)
    false_positive_sessions: Set[str] = field(default_factory=set)
    verified_wine_sessions: Set[str] = field(default_factory=set)
    verified_native_sessions: Set[str] = field(default_factory=set)
    most_recent_evidence_at: Optional[str] = None


def candidate_demand_key(
    provider_id: str,
    capability_id: str,
    behavior_id: Optional[str],
) -> str:
    return f"{provider_id}|{capability_id}|{behavior_id or '*'}"


def normalize_demand_score(counts: DemandCounts, *, max_reference: int = 10) -> float:
    """Normalize observed demand to 0–1 using distinct binary digests."""
    if counts.distinct_binary_digests <= 0:
        return 0.0
    return round(min(1.0, counts.distinct_binary_digests / max_reference), 4)


def build_demand_counts(evidence: DemandEvidence) -> DemandCounts:
    return DemandCounts(
        distinct_binary_digests=len(evidence.binary_digests),
        distinct_application_fingerprints=len(evidence.application_fingerprints),
        blocked_session_count=len(evidence.blocked_sessions),
        false_positive_gap_count=len(evidence.false_positive_sessions),
        verified_wine_session_count=len(evidence.verified_wine_sessions),
        most_recent_evidence_at=evidence.most_recent_evidence_at,
    )


def merge_evidence_timestamp(current: Optional[str], new_ts: Optional[str]) -> Optional[str]:
    if not new_ts:
        return current
    if not current:
        return new_ts
    return max(current, new_ts)


def application_fingerprint_from_analysis(
    binary_digest: str,
    file_path: Optional[str] = None,
) -> str:
    """Use binary digest as primary fingerprint; fixture basename when available."""
    if file_path:
        name = file_path.rsplit("/", 1)[-1].lower()
        if name.endswith(".exe"):
            return name
    return binary_digest


class DemandAggregator:
    """Collect deduplicated demand from analyses, snapshots, and calibration."""

    def __init__(self) -> None:
        self._evidence: Dict[str, DemandEvidence] = {}

    def _bucket(self, provider_id: str, capability_id: str, behavior_id: Optional[str]) -> DemandEvidence:
        key = candidate_demand_key(provider_id, capability_id, behavior_id)
        if key not in self._evidence:
            self._evidence[key] = DemandEvidence()
        return self._evidence[key]

    def record_analysis(
        self,
        *,
        provider_id: str,
        capability_id: str,
        behavior_id: Optional[str],
        binary_digest: str,
        analysis_digest: str,
        application_fingerprint: str,
        blocked: bool = False,
        timestamp: Optional[str] = None,
    ) -> None:
        bucket = self._bucket(provider_id, capability_id, behavior_id)
        bucket.binary_digests.add(binary_digest)
        bucket.application_fingerprints.add(application_fingerprint)
        bucket.analysis_digests.add(analysis_digest)
        if blocked:
            bucket.blocked_sessions.add(f"analysis:{analysis_digest}")
        bucket.most_recent_evidence_at = merge_evidence_timestamp(
            bucket.most_recent_evidence_at, timestamp
        )

    def record_calibration(
        self,
        *,
        provider_id: str,
        capability_id: str,
        behavior_id: Optional[str],
        binary_digest: str,
        analysis_digest: str,
        session_id: str,
        classification: str,
        behavior_gaps: List[str],
        verified_success: bool,
        timestamp: Optional[str] = None,
    ) -> None:
        if behavior_id and behavior_id not in behavior_gaps and classification != "false_positive":
            return
        bucket = self._bucket(provider_id, capability_id, behavior_id)
        bucket.binary_digests.add(binary_digest)
        bucket.analysis_digests.add(analysis_digest)
        if classification == "false_positive":
            bucket.false_positive_sessions.add(session_id)
        if not verified_success and classification in ("false_positive", "true_negative"):
            bucket.blocked_sessions.add(session_id)
        bucket.most_recent_evidence_at = merge_evidence_timestamp(
            bucket.most_recent_evidence_at, timestamp
        )

    def record_wine_success(
        self,
        *,
        capability_id: str,
        behavior_id: Optional[str],
        binary_digest: str,
        session_id: str,
        timestamp: Optional[str] = None,
    ) -> None:
        bucket = self._bucket("wine", capability_id, behavior_id)
        bucket.verified_wine_sessions.add(session_id)
        bucket.binary_digests.add(binary_digest)
        bucket.most_recent_evidence_at = merge_evidence_timestamp(
            bucket.most_recent_evidence_at, timestamp
        )

    def record_native_verified(
        self,
        *,
        capability_id: str,
        behavior_id: Optional[str],
        session_id: str,
        timestamp: Optional[str] = None,
    ) -> None:
        bucket = self._bucket("native_alma", capability_id, behavior_id)
        bucket.verified_native_sessions.add(session_id)
        bucket.most_recent_evidence_at = merge_evidence_timestamp(
            bucket.most_recent_evidence_at, timestamp
        )

    def get_evidence(
        self, provider_id: str, capability_id: str, behavior_id: Optional[str]
    ) -> DemandEvidence:
        return self._evidence.get(
            candidate_demand_key(provider_id, capability_id, behavior_id),
            DemandEvidence(),
        )

    def all_keys(self) -> List[tuple[str, str, Optional[str]]]:
        results: List[tuple[str, str, Optional[str]]] = []
        for key in sorted(self._evidence.keys()):
            provider_id, capability_id, behavior = key.split("|", 2)
            behavior_id = None if behavior == "*" else behavior
            results.append((provider_id, capability_id, behavior_id))
        return results
