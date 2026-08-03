"""API × behavior verification status matrix."""

from __future__ import annotations

from typing import Any, Dict, List

from alma_bridge.certification.models import BehaviorCertification


def build_verification_matrix(
    certifications: List[BehaviorCertification],
) -> List[Dict[str, Any]]:
    """Build API × behavior verification status matrix."""
    rows: List[Dict[str, Any]] = []
    for cert in certifications:
        api_sym = cert.api_symbols[0] if cert.api_symbols else ""
        rows.append(
            {
                "api_symbol": api_sym,
                "behavior_id": cert.behavior_id,
                "capability_id": cert.capability_id,
                "supported": cert.supported,
                "verification_pct": cert.verification_pct,
                "fixture_coverage_pct": cert.fixture_coverage_pct,
                "certification_level": cert.certification_level.value,
                "compliance_status": cert.compliance_status.value,
                "verification_contracts": [
                    c.model_dump(mode="json") for c in cert.verification_contracts
                ],
                "regression_status": cert.regression_status,
            }
        )
    return sorted(rows, key=lambda r: (r["api_symbol"], r["behavior_id"]))
