"""Deterministic report digests."""

from __future__ import annotations

from typing import Any, Mapping

from alma_bridge.compatibility.profile_fingerprints import sha256_v1

from alma_bridge.research.models import ResearchReport


def report_digest_payload(report: ResearchReport) -> dict[str, Any]:
    return {
        "schema_version": report.metadata.schema_version,
        "report_type": report.metadata.report_type.value,
        "time_window": report.metadata.time_window.model_dump(mode="json"),
        "registry_version": report.metadata.registry_version,
        "provider_id": report.metadata.provider_id,
        "sample_size": report.metadata.sample_size.model_dump(mode="json"),
        "summary": report.summary,
        "metrics": [
            {
                "name": m.name,
                "value": m.value,
                "sample_size": m.sample_size.model_dump(mode="json"),
            }
            for m in sorted(report.metrics, key=lambda m: m.name)
        ],
        "rows": [
            {
                "rank": r.rank,
                "label": r.label,
                "count": r.count,
                "value": r.value,
            }
            for r in report.rows
        ],
        "series": [
            {
                "timestamp": p.timestamp,
                "value": p.value,
                "label": p.label,
            }
            for p in report.series
        ],
    }


def compute_report_digest(report: ResearchReport) -> str:
    return sha256_v1(report_digest_payload(report))


def compute_dashboard_digest(payload: Mapping[str, Any]) -> str:
    return sha256_v1(payload)
