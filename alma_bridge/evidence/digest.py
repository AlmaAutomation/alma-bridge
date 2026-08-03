"""Deterministic bundle and section digests."""

from __future__ import annotations

from typing import Any, Mapping

from alma_bridge.compatibility.profile_fingerprints import sha256_v1

from alma_bridge.evidence.models import CompatibilityEvidenceBundle, SectionReference, TimelineEvent


def section_digest(section: SectionReference) -> str:
    return sha256_v1(
        {
            "section": section.section,
            "artifact_id": section.artifact_id,
            "digest": section.digest,
            "schema_version": section.schema_version,
        }
    )


def bundle_digest_payload(bundle: CompatibilityEvidenceBundle) -> dict[str, Any]:
    sections: dict[str, str] = {}
    for name in (
        "executable",
        "static_analysis",
        "capability_graph",
        "coverage",
        "prediction",
        "prediction_snapshot",
        "execution",
        "runtime_provider",
        "verification",
        "knowledge",
        "regression",
        "advisor",
        "decision",
        "review",
        "validation",
        "governance",
        "expansion",
    ):
        ref = getattr(bundle, name, None)
        if ref is not None:
            sections[name] = section_digest(ref)
    return {
        "schema_version": bundle.schema_version,
        "binary_digest": bundle.binary_digest,
        "application_fingerprint": bundle.application_fingerprint,
        "version": bundle.version,
        "sections": sections,
        "limitations": sorted(bundle.limitations),
    }


def compute_bundle_digest(bundle: CompatibilityEvidenceBundle) -> str:
    return sha256_v1(bundle_digest_payload(bundle))


def compute_timeline_digest(events: list[TimelineEvent]) -> str:
    payload = [
        {
            "event_id": event.event_id,
            "event_type": event.event_type.value,
            "timestamp": event.timestamp,
            "version": event.version,
            "evidence_digest": event.evidence_digest,
            "source": event.source,
            "references": sorted(event.references),
        }
        for event in sorted(events, key=lambda e: (e.timestamp, e.event_id))
    ]
    return sha256_v1({"events": payload})


def compute_event_id(payload: Mapping[str, Any]) -> str:
    return sha256_v1(payload)
