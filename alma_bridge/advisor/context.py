"""Compose advisor context from existing read-only layer services."""

from __future__ import annotations

from typing import Optional

from alma_bridge.advisor.models import AdvisorContext, GraphSummary, MalformedAdvisorError
from alma_bridge.advisor.queries import union_evidence_references
from alma_bridge.graph.service import CompatibilityGraphService
from alma_bridge.knowledge.models import (
    CompatibilityKnowledgeProfile,
    KnowledgeNotFoundError,
    MalformedKnowledgeEvidenceError,
)
from alma_bridge.knowledge.service import CompatibilityKnowledgeService
from alma_bridge.regression.models import (
    CompatibilityRegressionReport,
    RegressionNotFoundError,
)
from alma_bridge.regression.service import CompatibilityRegressionService


class AdvisorContextBuilder:
    """Compose normalized advisor context without re-aggregating or re-detecting."""

    def __init__(
        self,
        *,
        knowledge_service: CompatibilityKnowledgeService | None = None,
        regression_service: CompatibilityRegressionService | None = None,
        graph_service: CompatibilityGraphService | None = None,
    ) -> None:
        self._knowledge = knowledge_service or CompatibilityKnowledgeService()
        self._regression = regression_service or CompatibilityRegressionService()
        # Phase 1: graph service is accepted for future read-only summaries but not invoked
        # because graph_for_* triggers ingestion side effects (ADR-006).
        self._graph = graph_service

    def build(
        self,
        fingerprint: str,
        *,
        session_id: Optional[str] = None,
    ) -> AdvisorContext:
        try:
            knowledge = self._knowledge.profile_for_application(fingerprint)
        except KnowledgeNotFoundError as exc:
            raise RegressionNotFoundError(str(exc)) from exc
        except MalformedKnowledgeEvidenceError as exc:
            raise MalformedAdvisorError(str(exc), details=exc.details) from exc

        try:
            regression = self._regression.report_for_application(
                fingerprint,
                session_id=session_id,
            )
        except RegressionNotFoundError as exc:
            raise RegressionNotFoundError(str(exc)) from exc
        except MalformedKnowledgeEvidenceError as exc:
            raise MalformedAdvisorError(str(exc), details=exc.details) from exc

        graph_summary = self._graph_summary_from_knowledge(knowledge)
        evidence_refs = self._collect_evidence(knowledge, regression)
        return AdvisorContext(
            application_fingerprint=knowledge.application_fingerprint,
            application_name=knowledge.application_name,
            graph_summary=graph_summary,
            knowledge_profile=knowledge,
            regression_report=regression,
            selected_session_id=session_id or regression.comparison_session_id or None,
            evidence_references=evidence_refs,
        )

    @staticmethod
    def _graph_summary_from_knowledge(
        profile: CompatibilityKnowledgeProfile,
    ) -> GraphSummary:
        return GraphSummary(
            application_fingerprint=profile.application_fingerprint,
            total_sessions=profile.total_sessions,
            frameworks_observed=[item.framework for item in profile.observed_frameworks],
            strategies_observed=[item.strategy for item in profile.observed_launch_strategies],
            runtimes_observed=[item.runtime for item in profile.observed_runtimes],
            conflict_count=len(profile.conflicts),
        )

    @staticmethod
    def _collect_evidence(
        knowledge: CompatibilityKnowledgeProfile,
        regression: CompatibilityRegressionReport,
    ) -> list:
        refs = []
        for framework in knowledge.observed_frameworks:
            refs.extend(framework.evidence_references)
        for strategy in knowledge.observed_launch_strategies:
            refs.extend(strategy.evidence_references)
        for runtime in knowledge.observed_runtimes:
            refs.extend(runtime.evidence_references)
        for contract in knowledge.verification_contracts:
            refs.extend(contract.evidence_references)
        for conflict in knowledge.conflicts:
            for side_refs in conflict.evidence_by_side.values():
                refs.extend(side_refs)
        for finding in regression.findings or regression.regressions:
            refs.extend(finding.evidence_references)
        return union_evidence_references(refs)
