"""Immutable lifecycle timeline — append-only event stream."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from alma_bridge.evidence.digest import compute_event_id, compute_timeline_digest
from alma_bridge.evidence.models import (
    Provenance,
    TimelineEvent,
    TimelineEventType,
    utc_now_iso,
)


class EvidenceTimeline:
    """Build and validate immutable timeline events."""

    def __init__(self, events: Optional[List[TimelineEvent]] = None) -> None:
        self._events: List[TimelineEvent] = list(events or [])

    @property
    def events(self) -> List[TimelineEvent]:
        return list(self._events)

    @property
    def digest(self) -> str:
        return compute_timeline_digest(self._events)

    @property
    def version(self) -> int:
        return len(self._events)

    def append(
        self,
        event_type: TimelineEventType,
        *,
        source: str,
        evidence_digest: str,
        references: Optional[List[str]] = None,
        provenance: Optional[Provenance] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TimelineEvent:
        timestamp = utc_now_iso()
        version = self.version + 1
        event_id = compute_event_id(
            {
                "event_type": event_type.value,
                "timestamp": timestamp,
                "source": source,
                "evidence_digest": evidence_digest,
                "version": version,
            }
        )
        event = TimelineEvent(
            event_id=event_id,
            event_type=event_type,
            timestamp=timestamp,
            version=version,
            evidence_digest=evidence_digest,
            source=source,
            references=sorted(references or []),
            provenance=provenance
            or Provenance(source=source, artifact_id=event_id, digest=evidence_digest),
            metadata=metadata or {},
        )
        self._events.append(event)
        return event

    def verify_immutability(self, prior_events: List[TimelineEvent]) -> bool:
        """Return True if prior events are a prefix of current events unchanged."""
        if len(prior_events) > len(self._events):
            return False
        for prior, current in zip(prior_events, self._events):
            if prior.model_dump() != current.model_dump():
                return False
        return True

    @classmethod
    def from_events(cls, events: List[TimelineEvent]) -> EvidenceTimeline:
        sorted_events = sorted(events, key=lambda e: (e.timestamp, e.event_id))
        return cls(sorted_events)
