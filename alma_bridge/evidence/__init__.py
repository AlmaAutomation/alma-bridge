"""Unified compatibility evidence lifecycle — Alma v2.0 integration layer."""

from alma_bridge.evidence.models import (
    EVIDENCE_SCHEMA_VERSION,
    CompatibilityEvidenceBundle,
    TimelineEventType,
)
from alma_bridge.evidence.service import EvidenceService

__all__ = [
    "EVIDENCE_SCHEMA_VERSION",
    "CompatibilityEvidenceBundle",
    "EvidenceService",
    "TimelineEventType",
]
