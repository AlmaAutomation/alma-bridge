"""Deterministic explanation engine — template-based, not LLM."""

from __future__ import annotations

from typing import List

from alma_bridge.advisor.models import (
    ADVISOR_ENGINE_VERSION,
    ADVISOR_SCHEMA_VERSION,
    AdvisorContext,
    AdvisorExplanation,
    AdvisorObservation,
    ObservationCategory,
    SourceLayer,
)
from alma_bridge.advisor.policy import validate_explanation
from alma_bridge.advisor.queries import build_observation_id, union_evidence_references
from alma_bridge.knowledge.models import EvidenceClassification
from alma_bridge.regression.models import RegressionType


class DeterministicAdvisorEngine:
    """Produce factual advisor explanations from composed context."""

    engine_version = ADVISOR_ENGINE_VERSION

    def explain(self, context: AdvisorContext) -> AdvisorExplanation:
        observations: List[AdvisorObservation] = []
        limitations: List[str] = []

        profile = context.knowledge_profile
        regression = context.regression_report

        observations.extend(self._verified_outcome_observations(context))
        observations.extend(self._framework_observations(context))
        observations.extend(self._strategy_observations(context))
        observations.extend(self._runtime_observations(context))
        observations.extend(self._verification_contract_observations(context))
        observations.extend(self._conflict_observations(context))
        observations.extend(self._compatibility_change_observations(context))

        if profile.total_sessions <= 1 or profile.unverifiable_sessions == profile.total_sessions:
            obs = self._insufficient_evidence_observation(context)
            if obs:
                observations.append(obs)
            limitations.append(
                "Evidence is insufficient to characterize compatibility reliably."
            )

        if regression.unchanged_summary and not (regression.findings or regression.regressions):
            limitations.append(regression.unchanged_summary)

        limitations.append(
            "Alma does not infer a runtime requirement from these observations."
        )

        summary = self._build_summary(context, observations, limitations)
        explanation = AdvisorExplanation(
            application_fingerprint=context.application_fingerprint,
            application_name=context.application_name,
            observations=observations,
            summary=summary,
            limitations=sorted(set(limitations)),
            schema_version=ADVISOR_SCHEMA_VERSION,
            engine_version=self.engine_version,
        )
        validate_explanation(explanation)
        return explanation

    def _verified_outcome_observations(
        self,
        context: AdvisorContext,
    ) -> List[AdvisorObservation]:
        profile = context.knowledge_profile
        if profile.total_sessions == 0:
            return []

        refs = union_evidence_references(
            *(
                strategy.evidence_references
                for strategy in profile.observed_launch_strategies
            )
        )
        if not refs:
            return []

        parts = []
        if profile.verified_successes:
            parts.append(
                f"{profile.verified_successes} session(s) were authoritatively verified successful"
            )
        if profile.verified_failures:
            parts.append(
                f"{profile.verified_failures} session(s) had authoritative verified failure"
            )
        if profile.unverifiable_sessions:
            parts.append(
                f"{profile.unverifiable_sessions} session(s) were unverifiable"
            )

        statement = (
            f"{context.application_name} has "
            + "; ".join(parts)
            + " across available sessions."
        )
        severity = "critical" if profile.verified_failures else "info"
        return [
            AdvisorObservation(
                observation_id=build_observation_id(
                    application_fingerprint=context.application_fingerprint,
                    category=ObservationCategory.VERIFIED_OUTCOME_HISTORY,
                    subject="session_outcomes",
                ),
                category=ObservationCategory.VERIFIED_OUTCOME_HISTORY,
                title="Verified outcome history",
                statement=statement,
                confidence=min(1.0, 0.5 + 0.1 * profile.total_sessions),
                severity=severity,
                evidence_references=refs[: min(len(refs), 8)],
                source_layer=SourceLayer.KNOWLEDGE,
            )
        ]

    def _framework_observations(self, context: AdvisorContext) -> List[AdvisorObservation]:
        observations: List[AdvisorObservation] = []
        for framework in context.knowledge_profile.observed_frameworks:
            label = framework.framework
            if framework.classification == EvidenceClassification.CONFLICTING:
                title = "Conflicting framework observation"
            elif framework.classification == EvidenceClassification.REPEATED:
                title = "Repeated framework observation"
            else:
                title = "Framework observation"
            statement = (
                f"{label} was observed in {framework.observation_count} session(s)"
                f" ({framework.verified_session_count} with verified sessions)."
            )
            observations.append(
                AdvisorObservation(
                    observation_id=build_observation_id(
                        application_fingerprint=context.application_fingerprint,
                        category=ObservationCategory.FRAMEWORK_OBSERVATION,
                        subject=label,
                    ),
                    category=ObservationCategory.FRAMEWORK_OBSERVATION,
                    title=title,
                    statement=statement,
                    confidence=framework.confidence,
                    severity="warning" if framework.classification == EvidenceClassification.CONFLICTING else "info",
                    evidence_references=list(framework.evidence_references),
                    source_layer=SourceLayer.KNOWLEDGE,
                )
            )
        return observations

    def _strategy_observations(self, context: AdvisorContext) -> List[AdvisorObservation]:
        observations: List[AdvisorObservation] = []
        for strategy in context.knowledge_profile.observed_launch_strategies:
            statement = (
                f"{strategy.strategy} was used in {strategy.attempts} attempt(s) with "
                f"{strategy.verified_successes} authoritative verified success(es) and "
                f"{strategy.verified_failures} authoritative verified failure(s) "
                f"({strategy.success_rate:.0%} verified success rate across observed outcomes)."
            )
            observations.append(
                AdvisorObservation(
                    observation_id=build_observation_id(
                        application_fingerprint=context.application_fingerprint,
                        category=ObservationCategory.STRATEGY_HISTORY,
                        subject=strategy.strategy,
                    ),
                    category=ObservationCategory.STRATEGY_HISTORY,
                    title="Launch strategy history",
                    statement=statement,
                    confidence=min(1.0, strategy.success_rate + 0.1),
                    severity="info",
                    evidence_references=list(strategy.evidence_references),
                    source_layer=SourceLayer.KNOWLEDGE,
                )
            )
        return observations

    def _runtime_observations(self, context: AdvisorContext) -> List[AdvisorObservation]:
        observations: List[AdvisorObservation] = []
        for runtime in context.knowledge_profile.observed_runtimes:
            statement = (
                f"{runtime.runtime} runtime was observed in "
                f"{runtime.observation_count} session(s) "
                f"({runtime.verified_success_observation_count} in verified sessions)."
            )
            observations.append(
                AdvisorObservation(
                    observation_id=build_observation_id(
                        application_fingerprint=context.application_fingerprint,
                        category=ObservationCategory.RUNTIME_OBSERVATION,
                        subject=runtime.runtime,
                    ),
                    category=ObservationCategory.RUNTIME_OBSERVATION,
                    title="Runtime observation",
                    statement=statement,
                    confidence=0.7,
                    severity="info",
                    evidence_references=list(runtime.evidence_references),
                    source_layer=SourceLayer.KNOWLEDGE,
                )
            )
        return observations

    def _verification_contract_observations(
        self,
        context: AdvisorContext,
    ) -> List[AdvisorObservation]:
        observations: List[AdvisorObservation] = []
        for contract in context.knowledge_profile.verification_contracts:
            statement = (
                f"Verification contract {contract.contract} passed in "
                f"{contract.passed_count} session(s) and failed in {contract.failed_count} session(s)."
            )
            observations.append(
                AdvisorObservation(
                    observation_id=build_observation_id(
                        application_fingerprint=context.application_fingerprint,
                        category=ObservationCategory.VERIFICATION_CONTRACT,
                        subject=contract.contract,
                    ),
                    category=ObservationCategory.VERIFICATION_CONTRACT,
                    title="Verification contract history",
                    statement=statement,
                    confidence=0.8,
                    severity="info",
                    evidence_references=list(contract.evidence_references),
                    source_layer=SourceLayer.KNOWLEDGE,
                )
            )
        return observations

    def _conflict_observations(self, context: AdvisorContext) -> List[AdvisorObservation]:
        observations: List[AdvisorObservation] = []
        for conflict in context.knowledge_profile.conflicts:
            sides = " and ".join(conflict.competing_observations)
            statement = (
                f"Framework evidence is conflicting: {sides} have both been observed."
            )
            side_refs = union_evidence_references(*conflict.evidence_by_side.values())
            observations.append(
                AdvisorObservation(
                    observation_id=build_observation_id(
                        application_fingerprint=context.application_fingerprint,
                        category=ObservationCategory.CONFLICTING_EVIDENCE,
                        subject=conflict.relationship,
                    ),
                    category=ObservationCategory.CONFLICTING_EVIDENCE,
                    title="Conflicting framework evidence",
                    statement=statement,
                    confidence=0.85,
                    severity="warning",
                    evidence_references=side_refs,
                    source_layer=SourceLayer.KNOWLEDGE,
                )
            )
        return observations

    def _compatibility_change_observations(
        self,
        context: AdvisorContext,
    ) -> List[AdvisorObservation]:
        observations: List[AdvisorObservation] = []
        findings = context.regression_report.findings or context.regression_report.regressions
        for finding in findings:
            if finding.regression_type == RegressionType.VERIFIED_SUCCESS_TO_VERIFIED_FAILURE:
                title = "Compatibility regression"
                severity = "critical"
            elif finding.regression_type == RegressionType.NEW_CONFLICT:
                title = "New conflicting evidence"
                severity = "warning"
            elif finding.regression_type == RegressionType.STRATEGY_SUCCESS_RATE_DROPPED:
                title = "Strategy outcome change"
                severity = "warning"
            elif finding.regression_type == RegressionType.FRAMEWORK_CHANGED:
                title = "Framework evidence changed"
                severity = "info"
            elif finding.regression_type == RegressionType.VERIFICATION_CONTRACT_CHANGED:
                title = "Verification contract changed"
                severity = "info"
            elif finding.regression_type == RegressionType.RUNTIME_OBSERVATION_CHANGED:
                title = "Runtime observation changed"
                severity = "info"
            else:
                title = "Compatibility change"
                severity = finding.severity.value

            observations.append(
                AdvisorObservation(
                    observation_id=build_observation_id(
                        application_fingerprint=context.application_fingerprint,
                        category=ObservationCategory.COMPATIBILITY_CHANGE,
                        subject=finding.regression_id,
                    ),
                    category=ObservationCategory.COMPATIBILITY_CHANGE,
                    title=title,
                    statement=finding.summary,
                    confidence=finding.confidence,
                    severity=severity,
                    evidence_references=list(finding.evidence_references),
                    source_layer=SourceLayer.REGRESSION,
                )
            )

        if not findings and context.regression_report.baseline_session_count > 0:
            unchanged = context.regression_report.unchanged_summary or (
                "No compatibility regressions were detected relative to the available baseline."
            )
            refs = context.evidence_references[: min(len(context.evidence_references), 4)]
            if refs:
                observations.append(
                    AdvisorObservation(
                        observation_id=build_observation_id(
                            application_fingerprint=context.application_fingerprint,
                            category=ObservationCategory.COMPATIBILITY_CHANGE,
                            subject="no_regression",
                        ),
                        category=ObservationCategory.COMPATIBILITY_CHANGE,
                        title="No compatibility regression detected",
                        statement=unchanged,
                        confidence=0.6,
                        severity="info",
                        evidence_references=refs,
                        source_layer=SourceLayer.REGRESSION,
                    )
                )
        return observations

    def _insufficient_evidence_observation(
        self,
        context: AdvisorContext,
    ) -> AdvisorObservation | None:
        refs = context.evidence_references[: min(len(context.evidence_references), 2)]
        if not refs:
            return None
        return AdvisorObservation(
            observation_id=build_observation_id(
                application_fingerprint=context.application_fingerprint,
                category=ObservationCategory.INSUFFICIENT_EVIDENCE,
                subject="sparse",
            ),
            category=ObservationCategory.INSUFFICIENT_EVIDENCE,
            title="Insufficient evidence",
            statement="Evidence is insufficient to characterize compatibility reliably.",
            confidence=0.3,
            severity="notice",
            evidence_references=refs,
            source_layer=SourceLayer.KNOWLEDGE,
        )

    def _build_summary(
        self,
        context: AdvisorContext,
        observations: List[AdvisorObservation],
        limitations: List[str],
    ) -> str:
        profile = context.knowledge_profile
        sentences: List[str] = []

        if profile.verified_successes:
            strategy_names = ", ".join(
                item.strategy for item in profile.observed_launch_strategies
            )
            if strategy_names:
                sentences.append(
                    f"{context.application_name} has multiple authoritatively verified sessions using {strategy_names}."
                )
            else:
                sentences.append(
                    f"{context.application_name} has {profile.verified_successes} authoritatively verified successful session(s)."
                )

        regression_failures = [
            obs
            for obs in observations
            if obs.category == ObservationCategory.COMPATIBILITY_CHANGE
            and obs.severity == "critical"
        ]
        if regression_failures:
            sentences.append(
                "A later verified failure was observed after prior verified successes."
            )
        elif profile.verified_failures:
            sentences.append(
                "An authoritative verified failure was observed in available session history."
            )

        repeated = [
            fw.framework
            for fw in profile.observed_frameworks
            if fw.classification == EvidenceClassification.REPEATED
        ]
        if repeated:
            sentences.append(
                f"{repeated[0]} has been observed repeatedly across sessions."
            )

        if profile.conflicts:
            sides = profile.conflicts[0].competing_observations
            if len(sides) >= 2:
                sentences.append(
                    f"{sides[0]} and {sides[1]} appear in conflicting framework evidence."
                )

        if profile.observed_runtimes:
            sentences.append("Runtime observations are present in verified sessions.")

        if not sentences:
            sentences.append(
                "Available compatibility evidence is limited; see observations and limitations."
            )

        sentences.append(
            "Alma does not infer a runtime requirement from these observations."
        )
        return " ".join(sentences)
