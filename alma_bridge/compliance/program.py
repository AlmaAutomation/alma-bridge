"""Commercial program compliance — metadata, data practices, retention."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from alma_bridge.config import settings

PROGRAM_ID = "alma-lab-modernization"

# Fields never persisted in audit logs (commercial privacy requirement).
REDACTED_REQUEST_FIELDS = frozenset(
    {
        "sudo_password",
        "approval_token",
        "password",
        "token",
        "api_key",
        "secret",
    }
)


def redact_request_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Remove secrets before writing automation/audit records."""
    clean: Dict[str, Any] = {}
    for key, value in payload.items():
        if key in REDACTED_REQUEST_FIELDS:
            clean[key] = "[REDACTED]"
        elif isinstance(value, dict):
            clean[key] = redact_request_payload(value)
        else:
            clean[key] = value
    return clean


def data_practices() -> Dict[str, Any]:
    return {
        "program_id": PROGRAM_ID,
        "student_pii_collected": False,
        "education_records_ferpa": (
            "Alma does not require student names, grades, or directory information. "
            "Host configuration, automation results, and operator-supplied scan paths "
            "may be stored locally on the district's Alma server."
        ),
        "coppa": (
            "Alma is an IT administration tool for district staff, not a student-facing "
            "application. Districts must not configure scans to target student home "
            "directories or personal files."
        ),
        "data_location": "On-premise / district-controlled server by default (SQLite, local logs)",
        "subprocessors": [],
        "optional_webhooks": (
            "If ALMA_BRIDGE_AUTOMATION_WEBHOOK_URLS is set, automation events are POSTed "
            "to district-configured endpoints only."
        ),
        "retention_days_default": settings.compliance_data_retention_days,
        "secrets_in_logs": "sudo passwords and approval tokens are redacted before persistence",
        "export": "JSON reports downloadable from the flagship console",
        "deletion": "DELETE /compliance/program/data (requires API key when configured)",
    }


def legal_documents() -> List[Dict[str, str]]:
    base = "docs/legal"
    return [
        {"id": "commercial_license", "title": "Commercial License Agreement", "path": f"{base}/COMMERCIAL_LICENSE.md"},
        {"id": "terms", "title": "Terms of Service", "path": f"{base}/TERMS_OF_SERVICE.md"},
        {"id": "privacy", "title": "Privacy Policy", "path": f"{base}/PRIVACY_POLICY.md"},
        {"id": "dpa", "title": "Data Processing Addendum (FERPA)", "path": f"{base}/DATA_PROCESSING_ADDENDUM.md"},
        {"id": "ferpa_coppa", "title": "FERPA & COPPA Statement", "path": f"{base}/FERPA_COPPA_STATEMENT.md"},
        {"id": "acceptable_use", "title": "Acceptable Use Policy", "path": f"{base}/ACCEPTABLE_USE.md"},
        {"id": "sla", "title": "Support & SLA", "path": f"{base}/SLA.md"},
        {"id": "security", "title": "Security Overview", "path": "alma-bridge/SECURITY.md"},
        {"id": "third_party", "title": "Third-Party Notices", "path": f"{base}/THIRD_PARTY_NOTICES.md"},
    ]


def compliance_program() -> Dict[str, Any]:
    return {
        "program_id": PROGRAM_ID,
        "program_name": "Alma Lab Modernization Program",
        "commercial_ready": True,
        "certifications": {
            "soc2_type2": False,
            "fedramp": False,
            "note": "On-prem deployment; district controls infrastructure. SOC 2 roadmap available on request.",
        },
        "data_practices": data_practices(),
        "legal_documents": legal_documents(),
        "vendor_onboarding": {
            "w9_available": True,
            "coi_available_on_request": True,
            "contact": "legal@example.com",
        },
        "standards_addressed": [
            "FERPA (US student education records — DPA)",
            "COPPA (no child-directed collection)",
            "CCPA/CPRA (minimal personal data; on-prem)",
            "NIST CSF aligned security controls (documented)",
        ],
    }


def purge_local_data(*, older_than_days: int | None = None) -> Dict[str, Any]:
    """Delete automation audit rows older than retention window."""
    if older_than_days is not None:
        days = max(0, int(older_than_days))
    else:
        days = max(1, int(settings.compliance_data_retention_days))
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_iso = cutoff.isoformat()

    from alma_bridge.automation.sessions import _connect, init_automation_store

    init_automation_store()
    with _connect() as conn:
        cur = conn.execute(
            "DELETE FROM automation_sessions WHERE started_at < ?",
            (cutoff_iso,),
        )
        approvals = conn.execute(
            "DELETE FROM automation_approvals WHERE expires_at < ?",
            (cutoff_iso,),
        )
        conn.commit()
        return {
            "purged_sessions": cur.rowcount,
            "purged_approvals": approvals.rowcount,
            "cutoff": cutoff_iso,
            "retention_days": days,
        }
