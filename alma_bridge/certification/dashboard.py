"""Aggregated certification dashboard data."""

from __future__ import annotations

from typing import TYPE_CHECKING

from alma_bridge.certification.compliance import build_compliance_matrix
from alma_bridge.certification.models import (
    CertificationDashboard,
    CertificationLevel,
    ComplianceStatus,
    CERTIFICATION_SCHEMA_VERSION,
    CERTIFICATION_PROVIDER_ID,
    CERTIFICATION_IMPLEMENTATION_VERSION,
    utc_now_iso,
)
from alma_bridge.certification.versioning import detect_stale_items

if TYPE_CHECKING:
    from alma_bridge.certification.queries import CertificationQueries


def build_certification_dashboard(queries: CertificationQueries) -> CertificationDashboard:
    certs = queries.list_behavior_certifications()
    matrix = build_compliance_matrix(certs)
    stale = detect_stale_items(certs)

    certified_count = sum(
        1
        for c in certs
        if c.compliance_status == ComplianceStatus.CERTIFIED
    )
    unsupported_count = sum(1 for c in certs if not c.supported)
    stale_count = len(stale)

    summary = [
        {
            "capability_id": c.capability_id,
            "behavior_id": c.behavior_id,
            "api_symbols": c.api_symbols,
            "supported": c.supported,
            "certification_level": c.certification_level.value,
            "compliance_status": c.compliance_status.value,
            "fixture_coverage_pct": c.fixture_coverage_pct,
            "verification_pct": c.verification_pct,
            "evidence_count": c.evidence_count,
            "certification_digest": c.certification_digest,
        }
        for c in certs
    ]

    limitations = [
        "Certification computed from evidence — no auto-promotion of governance",
        "Unsupported behaviors show documented gaps, not symbol presence",
        "History is append-only; stale items retain prior certification records",
        "append_existing_file and overlapped_io are not certified",
    ]

    return CertificationDashboard(
        generated_at=utc_now_iso(),
        schema_version=CERTIFICATION_SCHEMA_VERSION,
        provider_id=CERTIFICATION_PROVIDER_ID,
        implementation_version=CERTIFICATION_IMPLEMENTATION_VERSION,
        behavior_count=len(certs),
        certified_count=certified_count,
        stale_count=stale_count,
        unsupported_count=unsupported_count,
        compliance_matrix=matrix,
        stale_items=stale,
        certifications_summary=summary,
        limitations=limitations,
    )
