"""Deterministic catalog aggregation from knowledge and regression evidence."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.catalog.models import (
    CATALOG_ENGINE_VERSION,
    CatalogApplicationEntry,
    CompatibilityCatalogResponse,
)
from alma_bridge.intelligence.evidence import EvidenceBundleBuilder
from alma_bridge.intelligence.models import IntelligenceNotFoundError
from alma_bridge.knowledge.aggregation import KnowledgeAggregationEngine
from alma_bridge.regression.service import CompatibilityRegressionService


class CatalogAggregationEngine:
    """Build application catalog entries from read-only evidence aggregation."""

    engine_version = CATALOG_ENGINE_VERSION

    def __init__(
        self,
        *,
        knowledge_engine: Optional[KnowledgeAggregationEngine] = None,
        regression_service: Optional[CompatibilityRegressionService] = None,
    ) -> None:
        self._knowledge = knowledge_engine or KnowledgeAggregationEngine()
        self._regression = regression_service or CompatibilityRegressionService()

    def build_catalog(
        self,
        fingerprints: List[str],
        builder: EvidenceBundleBuilder,
    ) -> CompatibilityCatalogResponse:
        entries: List[CatalogApplicationEntry] = []
        for fingerprint in sorted(fingerprints):
            try:
                bundle = builder.for_application(fingerprint)
            except IntelligenceNotFoundError:
                continue
            profile = self._knowledge.aggregate(bundle)
            sessions = sorted(
                bundle.artifacts.get("sessions") or [],
                key=lambda item: str(item.get("started_at") or ""),
            )
            latest = sessions[-1] if sessions else {}
            latest_session_id = str(latest.get("session_id") or "")
            latest_status = self._latest_status(profile, latest)
            last_regression = self._last_regression_change(fingerprint)
            latest_environment = self._latest_environment_summary(bundle, latest_session_id)

            entries.append(
                CatalogApplicationEntry(
                    fingerprint=fingerprint,
                    name=profile.application_name,
                    total_sessions=profile.total_sessions,
                    verified_successes=profile.verified_successes,
                    verified_failures=profile.verified_failures,
                    latest_status=latest_status,
                    latest_session=latest_session_id,
                    last_regression_change=last_regression,
                    observed_frameworks=[item.framework for item in profile.observed_frameworks],
                    observed_strategies=[item.strategy for item in profile.observed_launch_strategies],
                    latest_environment_summary=latest_environment,
                )
            )

        return CompatibilityCatalogResponse(applications=entries)

    def _latest_status(self, profile, latest_session: dict) -> str:
        if profile.verified_successes and not profile.verified_failures:
            return "verified_success"
        if profile.verified_failures and not profile.verified_successes:
            return "verified_failure"
        if profile.verified_successes and profile.verified_failures:
            return "mixed_verified"
        if latest_session.get("success"):
            return "unverified_success"
        return "unverified_or_failed"

    def _last_regression_change(self, fingerprint: str) -> Optional[str]:
        try:
            report = self._regression.report_for_application(fingerprint)
        except Exception:  # noqa: BLE001
            return None
        environment_findings = [
            finding
            for finding in report.findings
            if finding.regression_type.value == "environment_changed"
        ]
        if environment_findings:
            return environment_findings[-1].summary
        if report.findings:
            return report.findings[-1].summary
        return None

    @staticmethod
    def _latest_environment_summary(bundle, latest_session_id: str) -> Optional[str]:
        if not latest_session_id:
            return None
        artifact = bundle.artifacts.get(f"run_environment:{latest_session_id}")
        if not isinstance(artifact, dict):
            return None
        parts: List[str] = []
        wine_version = artifact.get("wine_version")
        if wine_version:
            parts.append(str(wine_version))
        host_os = artifact.get("host_os")
        host_arch = artifact.get("host_architecture")
        if host_os and host_arch:
            parts.append(f"{host_os}/{host_arch}")
        elif host_os:
            parts.append(str(host_os))
        prefix_id = artifact.get("prefix_id")
        if prefix_id:
            parts.append(f"prefix:{str(prefix_id)[:12]}")
        return " | ".join(parts) if parts else None
