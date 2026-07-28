"""Pure regression diff engine over compatibility knowledge profiles."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from alma_bridge.knowledge.models import (
    CompatibilityKnowledgeProfile,
    KnowledgeConflict,
    KnowledgeEvidenceReference,
    ObservedFramework,
    ObservedLaunchStrategy,
    ObservedRuntime,
    VerificationContractAggregate,
)
from alma_bridge.regression.models import (
    REGRESSION_ENGINE_VERSION,
    RegressionFinding,
    RegressionSeverity,
    RegressionStateSnapshot,
    RegressionType,
    severity_for_regression_type,
)
from alma_bridge.regression.queries import build_regression_id, union_evidence_references

MIN_BASELINE_ATTEMPTS = 3
MIN_RATE_DELTA = 0.25
SUCCESS_RATE_DROP_THRESHOLD = 0.75


class RegressionDiffEngine:
    """Compare baseline and current knowledge profiles for compatibility changes."""

    engine_version = REGRESSION_ENGINE_VERSION

    def compare(
        self,
        before: CompatibilityKnowledgeProfile,
        after: CompatibilityKnowledgeProfile,
    ) -> List[RegressionFinding]:
        findings: List[RegressionFinding] = []
        generated_at = after.generated_at

        findings.extend(self._detect_verified_success_to_failure(before, after, generated_at))
        findings.extend(self._detect_strategy_rate_drops(before, after, generated_at))
        findings.extend(self._detect_framework_changes(before, after, generated_at))
        findings.extend(self._detect_verification_contract_changes(before, after, generated_at))
        findings.extend(self._detect_runtime_changes(before, after, generated_at))
        findings.extend(self._detect_environment_changes(before, after, generated_at))
        findings.extend(self._detect_new_conflicts(before, after, generated_at))

        return sorted(
            findings,
            key=lambda item: (item.regression_type.value, item.subject, item.regression_id),
        )

    def unchanged_summary(
        self,
        before: CompatibilityKnowledgeProfile,
        after: CompatibilityKnowledgeProfile,
        findings: List[RegressionFinding],
    ) -> str:
        if findings:
            return ""
        if before.total_sessions == 0:
            return (
                "Insufficient baseline: no prior sessions to compare against the comparison session."
            )
        return (
            "No compatibility regressions or material evidence changes detected between baseline "
            f"({before.total_sessions} session(s)) and current ({after.total_sessions} session(s))."
        )

    def _detect_verified_success_to_failure(
        self,
        before: CompatibilityKnowledgeProfile,
        after: CompatibilityKnowledgeProfile,
        generated_at: str,
    ) -> List[RegressionFinding]:
        if before.verified_failures > 0:
            return []
        if after.verified_failures <= before.verified_failures:
            return []

        before_refs = self._profile_strategy_refs(before)
        after_refs = self._new_strategy_refs(before, after)
        if not before_refs or not after_refs:
            return []

        regression_type = RegressionType.VERIFIED_SUCCESS_TO_VERIFIED_FAILURE
        subject = "application_verified_outcome"
        return [
            self._build_finding(
                before=before,
                after=after,
                regression_type=regression_type,
                subject=subject,
                generated_at=generated_at,
                previous=RegressionStateSnapshot(
                    dimension="verified_outcome",
                    label="verified failures",
                    value=str(before.verified_failures),
                    evidence_references=before_refs,
                ),
                current=RegressionStateSnapshot(
                    dimension="verified_outcome",
                    label="verified failures",
                    value=str(after.verified_failures),
                    evidence_references=after_refs,
                ),
                summary=(
                    "Compatibility regression: verified failure observed where baseline had "
                    "no verified failures."
                ),
                confidence=0.9,
            )
        ]

    def _detect_strategy_rate_drops(
        self,
        before: CompatibilityKnowledgeProfile,
        after: CompatibilityKnowledgeProfile,
        generated_at: str,
    ) -> List[RegressionFinding]:
        before_by_strategy = {item.strategy: item for item in before.observed_launch_strategies}
        findings: List[RegressionFinding] = []

        for after_strategy in after.observed_launch_strategies:
            before_strategy = before_by_strategy.get(after_strategy.strategy)
            if not before_strategy:
                continue

            baseline_verified = (
                before_strategy.verified_successes + before_strategy.verified_failures
            )
            if baseline_verified < MIN_BASELINE_ATTEMPTS:
                continue

            baseline_rate = before_strategy.success_rate
            current_rate = after_strategy.success_rate
            delta = round(baseline_rate - current_rate, 4)

            if baseline_rate < SUCCESS_RATE_DROP_THRESHOLD:
                continue
            if delta < MIN_RATE_DELTA:
                continue
            if not before_strategy.evidence_references or not after_strategy.evidence_references:
                continue

            regression_type = RegressionType.STRATEGY_SUCCESS_RATE_DROPPED
            findings.append(
                self._build_finding(
                    before=before,
                    after=after,
                    regression_type=regression_type,
                    subject=after_strategy.strategy,
                    generated_at=generated_at,
                    previous=RegressionStateSnapshot(
                        dimension="launch_strategy_success_rate",
                        label=after_strategy.strategy,
                        value=f"{baseline_rate:.4f}",
                        evidence_references=before_strategy.evidence_references,
                    ),
                    current=RegressionStateSnapshot(
                        dimension="launch_strategy_success_rate",
                        label=after_strategy.strategy,
                        value=f"{current_rate:.4f}",
                        evidence_references=after_strategy.evidence_references,
                    ),
                    summary=(
                        f"Observed verified success rate for {after_strategy.strategy} changed "
                        f"from {baseline_rate:.2%} to {current_rate:.2%} (delta {delta:.2%})."
                    ),
                    confidence=min(1.0, baseline_verified / max(baseline_verified + 1, 1)),
                )
            )
        return findings

    def _detect_framework_changes(
        self,
        before: CompatibilityKnowledgeProfile,
        after: CompatibilityKnowledgeProfile,
        generated_at: str,
    ) -> List[RegressionFinding]:
        before_map = {item.framework: item for item in before.observed_frameworks}
        findings: List[RegressionFinding] = []

        for after_fw in after.observed_frameworks:
            before_fw = before_map.get(after_fw.framework)
            if before_fw is None:
                continue

            changed = (
                before_fw.observation_count != after_fw.observation_count
                or before_fw.classification != after_fw.classification
                or before_fw.verified_session_count != after_fw.verified_session_count
            )
            if not changed:
                continue
            if not before_fw.evidence_references or not after_fw.evidence_references:
                continue

            findings.append(
                self._framework_change_finding(
                    before,
                    after,
                    framework=after_fw.framework,
                    generated_at=generated_at,
                    previous_value=(
                        f"observations={before_fw.observation_count}, "
                        f"classification={before_fw.classification.value}"
                    ),
                    current_value=(
                        f"observations={after_fw.observation_count}, "
                        f"classification={after_fw.classification.value}"
                    ),
                    before_refs=before_fw.evidence_references,
                    after_refs=after_fw.evidence_references,
                    confidence=0.7,
                )
            )
        return findings

    def _framework_change_finding(
        self,
        before: CompatibilityKnowledgeProfile,
        after: CompatibilityKnowledgeProfile,
        *,
        framework: str,
        generated_at: str,
        previous_value: str,
        current_value: str,
        before_refs: List[KnowledgeEvidenceReference],
        after_refs: List[KnowledgeEvidenceReference],
        confidence: float,
    ) -> RegressionFinding:
        return self._build_finding(
            before=before,
            after=after,
            regression_type=RegressionType.FRAMEWORK_CHANGED,
            subject=framework,
            generated_at=generated_at,
            previous=RegressionStateSnapshot(
                dimension="framework_evidence",
                label=framework,
                value=previous_value,
                evidence_references=before_refs,
            ),
            current=RegressionStateSnapshot(
                dimension="framework_evidence",
                label=framework,
                value=current_value,
                evidence_references=after_refs,
            ),
            summary=f"Framework evidence changed for {framework}.",
            confidence=confidence,
        )

    def _detect_verification_contract_changes(
        self,
        before: CompatibilityKnowledgeProfile,
        after: CompatibilityKnowledgeProfile,
        generated_at: str,
    ) -> List[RegressionFinding]:
        before_map = {item.contract: item for item in before.verification_contracts}
        findings: List[RegressionFinding] = []

        for after_contract in after.verification_contracts:
            before_contract = before_map.get(after_contract.contract)
            if before_contract is None:
                continue

            changed = (
                before_contract.passed_count != after_contract.passed_count
                or before_contract.failed_count != after_contract.failed_count
            )
            if not changed:
                continue
            if not before_contract.evidence_references or not after_contract.evidence_references:
                continue

            findings.append(
                self._contract_change_finding(
                    before,
                    after,
                    contract=after_contract.contract,
                    generated_at=generated_at,
                    previous_value=(
                        f"passed={before_contract.passed_count}, "
                        f"failed={before_contract.failed_count}"
                    ),
                    current_value=(
                        f"passed={after_contract.passed_count}, "
                        f"failed={after_contract.failed_count}"
                    ),
                    before_refs=before_contract.evidence_references,
                    after_refs=after_contract.evidence_references,
                )
            )
        return findings

    def _contract_change_finding(
        self,
        before: CompatibilityKnowledgeProfile,
        after: CompatibilityKnowledgeProfile,
        *,
        contract: str,
        generated_at: str,
        previous_value: str,
        current_value: str,
        before_refs: List[KnowledgeEvidenceReference],
        after_refs: List[KnowledgeEvidenceReference],
    ) -> RegressionFinding:
        return self._build_finding(
            before=before,
            after=after,
            regression_type=RegressionType.VERIFICATION_CONTRACT_CHANGED,
            subject=contract,
            generated_at=generated_at,
            previous=RegressionStateSnapshot(
                dimension="verification_contract",
                label=contract,
                value=previous_value,
                evidence_references=before_refs,
            ),
            current=RegressionStateSnapshot(
                dimension="verification_contract",
                label=contract,
                value=current_value,
                evidence_references=after_refs,
            ),
            summary=f"Verification contract changed for {contract}.",
            confidence=0.75,
        )

    def _detect_runtime_changes(
        self,
        before: CompatibilityKnowledgeProfile,
        after: CompatibilityKnowledgeProfile,
        generated_at: str,
    ) -> List[RegressionFinding]:
        before_map = {item.runtime: item for item in before.observed_runtimes}
        findings: List[RegressionFinding] = []

        for after_runtime in after.observed_runtimes:
            before_runtime = before_map.get(after_runtime.runtime)
            if before_runtime is None:
                continue

            changed = (
                before_runtime.observation_count != after_runtime.observation_count
                or before_runtime.verified_success_observation_count
                != after_runtime.verified_success_observation_count
            )
            if not changed:
                continue
            if not before_runtime.evidence_references or not after_runtime.evidence_references:
                continue

            findings.append(
                self._runtime_change_finding(
                    before,
                    after,
                    runtime=after_runtime.runtime,
                    generated_at=generated_at,
                    previous_value=(
                        f"observations={before_runtime.observation_count}, "
                        f"verified_success_observations="
                        f"{before_runtime.verified_success_observation_count}"
                    ),
                    current_value=(
                        f"observations={after_runtime.observation_count}, "
                        f"verified_success_observations="
                        f"{after_runtime.verified_success_observation_count}"
                    ),
                    before_refs=before_runtime.evidence_references,
                    after_refs=after_runtime.evidence_references,
                )
            )
        return findings

    def _runtime_change_finding(
        self,
        before: CompatibilityKnowledgeProfile,
        after: CompatibilityKnowledgeProfile,
        *,
        runtime: str,
        generated_at: str,
        previous_value: str,
        current_value: str,
        before_refs: List[KnowledgeEvidenceReference],
        after_refs: List[KnowledgeEvidenceReference],
    ) -> RegressionFinding:
        return self._build_finding(
            before=before,
            after=after,
            regression_type=RegressionType.RUNTIME_OBSERVATION_CHANGED,
            subject=runtime,
            generated_at=generated_at,
            previous=RegressionStateSnapshot(
                dimension="runtime_observation",
                label=runtime,
                value=previous_value,
                evidence_references=before_refs,
            ),
            current=RegressionStateSnapshot(
                dimension="runtime_observation",
                label=runtime,
                value=current_value,
                evidence_references=after_refs,
            ),
            summary=f"Runtime observation changed for {runtime}.",
            confidence=0.7,
        )

    def _detect_environment_changes(
        self,
        before: CompatibilityKnowledgeProfile,
        after: CompatibilityKnowledgeProfile,
        generated_at: str,
    ) -> List[RegressionFinding]:
        before_map = {item.environment_identity: item for item in before.observed_environments}
        findings: List[RegressionFinding] = []

        for after_env in after.observed_environments:
            before_env = before_map.get(after_env.environment_identity)
            if before_env is None:
                if not after_env.evidence_references:
                    continue
                findings.append(
                    self._environment_change_finding(
                        before,
                        after,
                        environment=after_env.summary or after_env.environment_identity,
                        generated_at=generated_at,
                        previous_value="not observed in baseline sessions",
                        current_value=(
                            f"summary={after_env.summary}, "
                            f"observations={after_env.observation_count}"
                        ),
                        before_refs=after_env.evidence_references[:1],
                        after_refs=after_env.evidence_references,
                    )
                )
                continue

            changed = (
                before_env.observation_count != after_env.observation_count
                or before_env.verified_success_count != after_env.verified_success_count
                or before_env.verified_failure_count != after_env.verified_failure_count
            )
            if not changed:
                continue
            if not before_env.evidence_references or not after_env.evidence_references:
                continue

            findings.append(
                self._environment_change_finding(
                    before,
                    after,
                    environment=after_env.summary or after_env.environment_identity,
                    generated_at=generated_at,
                    previous_value=(
                        f"observations={before_env.observation_count}, "
                        f"verified_successes={before_env.verified_success_count}, "
                        f"verified_failures={before_env.verified_failure_count}"
                    ),
                    current_value=(
                        f"observations={after_env.observation_count}, "
                        f"verified_successes={after_env.verified_success_count}, "
                        f"verified_failures={after_env.verified_failure_count}"
                    ),
                    before_refs=before_env.evidence_references,
                    after_refs=after_env.evidence_references,
                )
            )
        return findings

    def _environment_change_finding(
        self,
        before: CompatibilityKnowledgeProfile,
        after: CompatibilityKnowledgeProfile,
        *,
        environment: str,
        generated_at: str,
        previous_value: str,
        current_value: str,
        before_refs: List[KnowledgeEvidenceReference],
        after_refs: List[KnowledgeEvidenceReference],
    ) -> RegressionFinding:
        return self._build_finding(
            before=before,
            after=after,
            regression_type=RegressionType.ENVIRONMENT_CHANGED,
            subject=environment,
            generated_at=generated_at,
            previous=RegressionStateSnapshot(
                dimension="run_environment",
                label=environment,
                value=previous_value,
                evidence_references=before_refs,
            ),
            current=RegressionStateSnapshot(
                dimension="run_environment",
                label=environment,
                value=current_value,
                evidence_references=after_refs,
            ),
            summary=f"Run environment snapshot differs for {environment}.",
            confidence=0.75,
        )

    def _detect_new_conflicts(
        self,
        before: CompatibilityKnowledgeProfile,
        after: CompatibilityKnowledgeProfile,
        generated_at: str,
    ) -> List[RegressionFinding]:
        before_keys = {self._conflict_key(item) for item in before.conflicts}
        findings: List[RegressionFinding] = []

        for conflict in after.conflicts:
            key = self._conflict_key(conflict)
            if key in before_keys:
                continue
            before_refs, after_refs = self._conflict_evidence_pair(before, conflict)
            if not before_refs or not after_refs:
                continue

            regression_type = RegressionType.NEW_CONFLICT
            subject = f"{conflict.relationship}:{conflict.conflict_type}"
            findings.append(
                self._build_finding(
                    before=before,
                    after=after,
                    regression_type=regression_type,
                    subject=subject,
                    generated_at=generated_at,
                    previous=RegressionStateSnapshot(
                        dimension="conflicting_evidence",
                        label=subject,
                        value="no conflict recorded",
                        evidence_references=before_refs,
                    ),
                    current=RegressionStateSnapshot(
                        dimension="conflicting_evidence",
                        label=subject,
                        value=f"sides={','.join(conflict.competing_observations)}",
                        evidence_references=after_refs,
                    ),
                    summary=(
                        "New conflicting evidence: "
                        f"{', '.join(conflict.competing_observations)}."
                    ),
                    confidence=0.8,
                )
            )
        return findings

    @staticmethod
    def _conflict_key(conflict: KnowledgeConflict) -> Tuple[str, str, Tuple[str, ...]]:
        return (
            conflict.relationship,
            conflict.conflict_type,
            tuple(conflict.competing_observations),
        )

    def _conflict_evidence_pair(
        self,
        before: CompatibilityKnowledgeProfile,
        new_conflict: KnowledgeConflict,
    ) -> tuple[List[KnowledgeEvidenceReference], List[KnowledgeEvidenceReference]]:
        after_refs: List[KnowledgeEvidenceReference] = []
        for refs in new_conflict.evidence_by_side.values():
            after_refs.extend(refs)
        after_refs = union_evidence_references(after_refs)

        before_refs: List[KnowledgeEvidenceReference] = []
        for framework in before.observed_frameworks:
            if framework.framework in new_conflict.competing_observations:
                before_refs.extend(framework.evidence_references)
        before_refs = union_evidence_references(before_refs)

        if not before_refs and after_refs:
            before_refs = after_refs[:1]
        return before_refs, after_refs

    @staticmethod
    def _profile_strategy_refs(profile: CompatibilityKnowledgeProfile) -> List[KnowledgeEvidenceReference]:
        refs: List[KnowledgeEvidenceReference] = []
        for strategy in profile.observed_launch_strategies:
            refs.extend(strategy.evidence_references)
        return union_evidence_references(refs)

    @staticmethod
    def _new_strategy_refs(
        before: CompatibilityKnowledgeProfile,
        after: CompatibilityKnowledgeProfile,
    ) -> List[KnowledgeEvidenceReference]:
        before_keys = {
            (ref.source_type, ref.source_id, ref.artifact_key)
            for strategy in before.observed_launch_strategies
            for ref in strategy.evidence_references
        }
        new_refs: List[KnowledgeEvidenceReference] = []
        for strategy in after.observed_launch_strategies:
            for ref in strategy.evidence_references:
                key = (ref.source_type, ref.source_id, ref.artifact_key)
                if key not in before_keys:
                    new_refs.append(ref)
        return union_evidence_references(new_refs)

    def _build_finding(
        self,
        *,
        before: CompatibilityKnowledgeProfile,
        after: CompatibilityKnowledgeProfile,
        regression_type: RegressionType,
        subject: str,
        generated_at: str,
        previous: RegressionStateSnapshot,
        current: RegressionStateSnapshot,
        summary: str,
        confidence: float,
    ) -> RegressionFinding:
        severity = severity_for_regression_type(regression_type)
        evidence = union_evidence_references(
            previous.evidence_references,
            current.evidence_references,
        )
        return RegressionFinding(
            regression_id=build_regression_id(
                application_fingerprint=after.application_fingerprint,
                regression_type=regression_type,
                subject=subject,
            ),
            application_fingerprint=after.application_fingerprint,
            application_name=after.application_name,
            regression_type=regression_type,
            severity=severity,
            subject=subject,
            previous_state=previous,
            current_state=current,
            first_observed_at=generated_at,
            confidence=round(confidence, 4),
            summary=summary,
            evidence_references=evidence,
        )
