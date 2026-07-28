"""Stable deterministic helpers for advisor observations."""

from __future__ import annotations

from typing import Iterable, List

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.advisor.models import ADVISOR_SCHEMA_VERSION, ObservationCategory
from alma_bridge.knowledge.models import KnowledgeEvidenceReference


def build_observation_id(
    *,
    application_fingerprint: str,
    category: ObservationCategory,
    subject: str,
) -> str:
    return sha256_v1(
        {
            "schema": ADVISOR_SCHEMA_VERSION,
            "application_fingerprint": application_fingerprint,
            "category": category.value,
            "subject": subject,
        }
    )


def union_evidence_references(
    *groups: Iterable[KnowledgeEvidenceReference],
) -> List[KnowledgeEvidenceReference]:
    seen: set[tuple[str, str, str]] = set()
    merged: List[KnowledgeEvidenceReference] = []
    for group in groups:
        for ref in group:
            key = (ref.source_type, ref.source_id, ref.artifact_key)
            if key in seen:
                continue
            seen.add(key)
            merged.append(ref)
    return sorted(
        merged,
        key=lambda ref: (ref.source_type, ref.source_id, ref.artifact_key),
    )
