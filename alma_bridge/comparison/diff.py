"""Pure session comparison diff engine."""

from __future__ import annotations

from typing import Callable, Iterable, List, Optional, Sequence

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.comparison.models import (
    COMPARISON_SCHEMA_VERSION,
    NON_CAUSALITY_NOTICE,
    SessionComparisonValue,
    SessionEnvironmentComparison,
)
from alma_bridge.comparison.queries import SessionEvidenceSnapshot
from alma_bridge.knowledge.models import KnowledgeEvidenceReference
from alma_bridge.regression.queries import union_evidence_references


_ENVIRONMENT_FIELDS = (
    ("alma_bridge_version", "Alma Bridge version"),
    ("host_os", "Host OS"),
    ("kernel_version", "Kernel"),
    ("host_architecture", "Architecture"),
    ("wine_version", "Wine"),
    ("wine_architecture", "Wine architecture"),
    ("prefix_id", "Prefix"),
    ("prefix_schema_version", "Prefix schema"),
)

_EXECUTION_FIELDS = (
    ("launch_strategy", "Strategy"),
    ("strategy_version", "Strategy version"),
)

_VERIFICATION_FIELDS = (
    ("authoritative_outcome", "Outcome"),
    ("verification_contract_identity", "Contract"),
    ("verification_policy_version", "Policy version"),
)


class SessionComparisonDiffEngine:
    """Compare two session snapshots without database access."""

    def compare(
        self,
        before: SessionEvidenceSnapshot,
        after: SessionEvidenceSnapshot,
    ) -> SessionEnvironmentComparison:
        environment_changes = self._compare_scalar_fields(
            before,
            after,
            _ENVIRONMENT_FIELDS,
            category="environment",
        )
        execution_changes = self._compare_scalar_fields(
            before,
            after,
            _EXECUTION_FIELDS,
            category="execution",
        )
        verification_changes = self._compare_scalar_fields(
            before,
            after,
            _VERIFICATION_FIELDS,
            category="verification",
            formatters={
                "authoritative_outcome": _format_outcome,
            },
        )
        framework_changes = self._compare_frameworks(before, after)
        runtime_changes = self._compare_runtimes(before, after)

        all_values = [
            *environment_changes,
            *execution_changes,
            *verification_changes,
            *framework_changes,
            *runtime_changes,
        ]
        unchanged_fields = sorted(
            value.field for value in all_values if not value.changed
        )
        non_causality_notice = self._non_causality_notice(
            environment_changes,
            verification_changes,
        )

        return SessionEnvironmentComparison(
            baseline_session_id=before.session_id,
            comparison_session_id=after.session_id,
            application_fingerprint=before.application_fingerprint,
            application_name=before.application_name,
            environment_changes=environment_changes,
            execution_changes=execution_changes,
            verification_changes=verification_changes,
            framework_changes=framework_changes,
            runtime_changes=runtime_changes,
            unchanged_fields=unchanged_fields,
            non_causality_notice=non_causality_notice,
        )

    def _compare_scalar_fields(
        self,
        before: SessionEvidenceSnapshot,
        after: SessionEvidenceSnapshot,
        fields: Sequence[tuple[str, str]],
        *,
        category: str,
        formatters: Optional[dict[str, Callable[[Optional[object]], Optional[str]]]] = None,
    ) -> List[SessionComparisonValue]:
        formatters = formatters or {}
        values: List[SessionComparisonValue] = []
        for field_name, label in fields:
            raw_before = getattr(before, field_name)
            raw_after = getattr(after, field_name)
            formatter = formatters.get(field_name, _format_scalar)
            before_value = formatter(raw_before)
            after_value = formatter(raw_after)
            changed = before_value != after_value
            refs = union_evidence_references(
                before.evidence_by_field.get(field_name, []),
                after.evidence_by_field.get(field_name, []),
            )
            values.append(
                SessionComparisonValue(
                    field=label,
                    before=before_value,
                    after=after_value,
                    changed=changed,
                    comparison_id=_comparison_id(
                        application_fingerprint=before.application_fingerprint,
                        category=category,
                        field=field_name,
                        baseline_session_id=before.session_id,
                        comparison_session_id=after.session_id,
                    ),
                    evidence_references=refs,
                )
            )
        return values

    def _compare_frameworks(
        self,
        before: SessionEvidenceSnapshot,
        after: SessionEvidenceSnapshot,
    ) -> List[SessionComparisonValue]:
        before_value = _format_frameworks(before.detected_frameworks)
        after_value = _format_frameworks(after.detected_frameworks)
        refs = union_evidence_references(
            before.evidence_by_field.get("detected_frameworks", []),
            after.evidence_by_field.get("detected_frameworks", []),
        )
        return [
            SessionComparisonValue(
                field="Frameworks",
                before=before_value,
                after=after_value,
                changed=before_value != after_value,
                comparison_id=_comparison_id(
                    application_fingerprint=before.application_fingerprint,
                    category="framework",
                    field="detected_frameworks",
                    baseline_session_id=before.session_id,
                    comparison_session_id=after.session_id,
                ),
                evidence_references=refs,
            )
        ]

    def _compare_runtimes(
        self,
        before: SessionEvidenceSnapshot,
        after: SessionEvidenceSnapshot,
    ) -> List[SessionComparisonValue]:
        runtimes = sorted(set(before.runtime_observations) | set(after.runtime_observations))
        values: List[SessionComparisonValue] = []
        for runtime in runtimes:
            before_state = _format_runtime_state(before.runtime_observations.get(runtime))
            after_state = _format_runtime_state(after.runtime_observations.get(runtime))
            refs = union_evidence_references(
                before.evidence_by_field.get(f"runtime:{runtime}", []),
                after.evidence_by_field.get(f"runtime:{runtime}", []),
            )
            values.append(
                SessionComparisonValue(
                    field=runtime,
                    before=before_state,
                    after=after_state,
                    changed=before_state != after_state,
                    comparison_id=_comparison_id(
                        application_fingerprint=before.application_fingerprint,
                        category="runtime",
                        field=runtime,
                        baseline_session_id=before.session_id,
                        comparison_session_id=after.session_id,
                    ),
                    evidence_references=refs,
                )
            )
        return values

    @staticmethod
    def _non_causality_notice(
        environment_changes: Iterable[SessionComparisonValue],
        verification_changes: Iterable[SessionComparisonValue],
    ) -> Optional[str]:
        environment_changed = any(item.changed for item in environment_changes)
        outcome_changed = any(
            item.changed and item.field == "Outcome" for item in verification_changes
        )
        if environment_changed and outcome_changed:
            return NON_CAUSALITY_NOTICE
        return None


def _comparison_id(
    *,
    application_fingerprint: str,
    category: str,
    field: str,
    baseline_session_id: str,
    comparison_session_id: str,
) -> str:
    return sha256_v1(
        {
            "schema": COMPARISON_SCHEMA_VERSION,
            "application_fingerprint": application_fingerprint,
            "category": category,
            "field": field,
            "baseline_session_id": baseline_session_id,
            "comparison_session_id": comparison_session_id,
        }
    )


def _format_scalar(value: Optional[object]) -> Optional[str]:
    if value is None or value == "":
        return None
    return str(value)


def _format_outcome(value: Optional[str]) -> Optional[str]:
    mapping = {
        "verified_success": "verified success",
        "verified_failure": "verified failure",
        "unverifiable": "unverifiable",
    }
    if value is None:
        return None
    return mapping.get(value, str(value))


def _format_frameworks(frameworks: List[str]) -> Optional[str]:
    if not frameworks:
        return None
    return ", ".join(frameworks)


def _format_runtime_state(value: Optional[str]) -> str:
    if value:
        return "observed"
    return "absent"
