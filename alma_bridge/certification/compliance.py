"""Compliance matrix builder."""

from __future__ import annotations

from typing import List

from alma_bridge.certification.digest import digest_of
from alma_bridge.certification.models import (
    BehaviorCertification,
    ComplianceMatrix,
    ComplianceMatrixEntry,
    CERTIFICATION_SCHEMA_VERSION,
    CERTIFICATION_PROVIDER_ID,
    utc_now_iso,
)


def build_compliance_matrix(
    certifications: List[BehaviorCertification],
) -> ComplianceMatrix:
    """Build deterministic API × behavior compliance matrix."""
    entries: List[ComplianceMatrixEntry] = []
    for cert in certifications:
        api_sym = cert.api_symbols[0] if cert.api_symbols else cert.capability_id
        entries.append(
            ComplianceMatrixEntry(
                api_symbol=api_sym,
                behavior_id=cert.behavior_id,
                capability_id=cert.capability_id,
                status=cert.compliance_status,
                coverage_pct=cert.fixture_coverage_pct,
                evidence_count=cert.evidence_count,
                verification_pct=cert.verification_pct,
                regression_status=cert.regression_status,
                governance_level=cert.governance_level,
                certification_level=cert.certification_level,
                supported=cert.supported,
                limitations=list(cert.known_limitations),
            )
        )
    entries.sort(key=lambda e: (e.api_symbol, e.behavior_id))
    body = {
        "provider_id": CERTIFICATION_PROVIDER_ID,
        "entry_count": len(entries),
    }
    return ComplianceMatrix(
        generated_at=utc_now_iso(),
        schema_version=CERTIFICATION_SCHEMA_VERSION,
        provider_id=CERTIFICATION_PROVIDER_ID,
        entries=entries,
        matrix_digest=digest_of(body),
    )
