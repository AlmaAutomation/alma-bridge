"""Certification version history and stale detection."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.certification.digest import digest_of
from alma_bridge.certification.models import (
    BehaviorCertification,
    CertificationLevel,
    CertificationRecord,
    StaleCertificationItem,
    EvidenceReferenceLink,
    utc_now_iso,
)
from alma_bridge.certification.repository import CertificationRepository


def record_level_transition(
    cert: BehaviorCertification,
    repo: CertificationRepository,
    *,
    previous_level: Optional[CertificationLevel] = None,
    reason: str = "",
) -> Optional[CertificationRecord]:
    """Append certification record when level changes (append-only)."""
    history = repo.get_history(cert.capability_id, cert.behavior_id)
    prev = previous_level
    if prev is None and history.records:
        prev = history.records[-1].new_level
    if prev == cert.certification_level:
        return None

    body = {
        "capability_id": cert.capability_id,
        "behavior_id": cert.behavior_id,
        "previous_level": prev.value if prev else None,
        "new_level": cert.certification_level.value,
        "spec_digest": cert.specification.spec_digest if cert.specification else "",
    }
    record_id = digest_of(body)[:16]
    record = CertificationRecord(
        record_id=record_id,
        capability_id=cert.capability_id,
        behavior_id=cert.behavior_id,
        previous_level=prev,
        new_level=cert.certification_level,
        transition_reason=reason or f"Level transition to {cert.certification_level.value}",
        evidence_references=[
            EvidenceReferenceLink(
                source=e.source,
                artifact_id=e.artifact_id,
                digest=e.digest,
                fixture_path=e.fixture_path,
            )
            for e in cert.evidence_references[:10]
        ],
        spec_digest=cert.specification.spec_digest if cert.specification else "",
        record_digest=digest_of(body),
    )
    repo.append_record(record)
    return record


def detect_stale_items(
    certifications: List[BehaviorCertification],
) -> List[StaleCertificationItem]:
    """Collect behaviors requiring revalidation."""
    stale: List[StaleCertificationItem] = []
    for cert in certifications:
        if cert.certification_level != CertificationLevel.REQUIRES_REVALIDATION:
            continue
        if not cert.stale_reasons:
            continue
        prev = CertificationLevel.VERIFIED
        stale.append(
            StaleCertificationItem(
                capability_id=cert.capability_id,
                behavior_id=cert.behavior_id,
                previous_level=prev,
                stale_reasons=list(cert.stale_reasons),
                detail=cert.stale_detail,
                detected_at=utc_now_iso(),
            )
        )
    return stale


def seed_initial_history(
    certifications: List[BehaviorCertification],
    repo: CertificationRepository,
) -> List[CertificationRecord]:
    """Record initial certification levels for behaviors without history."""
    recorded: List[CertificationRecord] = []
    for cert in certifications:
        history = repo.get_history(cert.capability_id, cert.behavior_id)
        if history.records:
            continue
        rec = record_level_transition(
            cert,
            repo,
            previous_level=CertificationLevel.UNVERIFIED,
            reason="Initial certification assessment",
        )
        if rec:
            recorded.append(rec)
    return recorded
