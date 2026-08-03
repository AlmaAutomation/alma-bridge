"""Deterministic promotion policy rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from alma_bridge.compatibility_intelligence.governance.models import (
    CapabilityMaturityState,
    CapabilityScope,
    MATURITY_ORDER,
)
from alma_bridge.compatibility_intelligence.governance.errors import PolicyViolationError

# Deterministic thresholds — never infer stability from aggregate success rate alone.
MIN_CALIBRATION_SAMPLES = 3
MIN_VERIFIED_SUCCESS_FOR_BOUNDED = 2
MAX_UNEXPLAINED_FALSE_POSITIVES = 0
REQUIRED_STABLE_SECURITY_REVIEW = True


@dataclass
class PromotionEvidence:
    """Evidence bundle evaluated by promotion policy."""

    scope: CapabilityScope
    current_state: CapabilityMaturityState
    proposed_state: CapabilityMaturityState
    verified_success_count: int = 0
    verified_failure_count: int = 0
    false_positive_count: int = 0
    false_negative_count: int = 0
    indeterminate_count: int = 0
    behavior_scenarios: List[str] = field(default_factory=list)
    required_behavior_scenarios: List[str] = field(default_factory=list)
    behavior_gaps: List[str] = field(default_factory=list)
    unresolved_false_positives: int = 0
    supporting_record_count: int = 0
    security_review_complete: bool = False
    regression_suite_stable: bool = False
    explicit_human_approval: bool = False
    limitations: List[str] = field(default_factory=list)


@dataclass
class PolicyResult:
    allowed: bool
    reasons: List[str] = field(default_factory=list)


def _is_promotion(current: CapabilityMaturityState, proposed: CapabilityMaturityState) -> bool:
    if proposed in (CapabilityMaturityState.DEPRECATED, CapabilityMaturityState.REVOKED):
        return False
    cur_order = MATURITY_ORDER.get(current, 0)
    prop_order = MATURITY_ORDER.get(proposed, 0)
    return prop_order > cur_order


def evaluate_promotion_policy(evidence: PromotionEvidence) -> PolicyResult:
    """Evaluate deterministic promotion policy for a state transition."""
    reasons: List[str] = []
    current = evidence.current_state
    proposed = evidence.proposed_state

    if current == proposed:
        return PolicyResult(allowed=False, reasons=["current and proposed state are identical"])

    if not _is_promotion(current, proposed):
        if proposed in (CapabilityMaturityState.DEPRECATED, CapabilityMaturityState.REVOKED):
            return PolicyResult(allowed=True, reasons=["demotion via explicit registry version"])
        return PolicyResult(allowed=False, reasons=["only forward promotion or explicit demotion allowed"])

    transition = (current, proposed)

    if transition == (
        CapabilityMaturityState.EXPERIMENTAL,
        CapabilityMaturityState.BEHAVIORALLY_TESTED,
    ):
        if evidence.required_behavior_scenarios:
            missing = set(evidence.required_behavior_scenarios) - set(evidence.behavior_scenarios)
            if missing:
                reasons.append(f"required behavior scenarios not executed: {sorted(missing)}")
        if evidence.behavior_gaps:
            reasons.append(f"hidden unsupported behavior gaps: {evidence.behavior_gaps}")

    elif transition == (
        CapabilityMaturityState.BEHAVIORALLY_TESTED,
        CapabilityMaturityState.CALIBRATION_SUPPORTED,
    ):
        resolved = (
            evidence.verified_success_count
            + evidence.verified_failure_count
            + evidence.false_positive_count
            + evidence.false_negative_count
        )
        if resolved < MIN_CALIBRATION_SAMPLES:
            reasons.append(
                f"insufficient resolved calibration samples: {resolved} < {MIN_CALIBRATION_SAMPLES}"
            )
        if evidence.unresolved_false_positives > MAX_UNEXPLAINED_FALSE_POSITIVES:
            reasons.append(
                f"unexplained false positives above threshold: {evidence.unresolved_false_positives}"
            )
        if evidence.supporting_record_count < MIN_CALIBRATION_SAMPLES:
            reasons.append(
                f"insufficient linked calibration records: {evidence.supporting_record_count}"
            )

    elif transition == (
        CapabilityMaturityState.CALIBRATION_SUPPORTED,
        CapabilityMaturityState.VERIFIED_BOUNDED,
    ):
        if evidence.verified_success_count < MIN_VERIFIED_SUCCESS_FOR_BOUNDED:
            reasons.append(
                f"insufficient verified successes for bounded scope: "
                f"{evidence.verified_success_count} < {MIN_VERIFIED_SUCCESS_FOR_BOUNDED}"
            )
        if evidence.behavior_gaps:
            reasons.append(f"blocking behavior gaps remain: {evidence.behavior_gaps}")
        if evidence.unresolved_false_positives > 0:
            reasons.append("unresolved false positives block verified_bounded promotion")
        if proposed == CapabilityMaturityState.STABLE and not evidence.scope.application_scope:
            reasons.append("bounded fixture evidence cannot produce global stable state")

    elif transition == (
        CapabilityMaturityState.VERIFIED_BOUNDED,
        CapabilityMaturityState.STABLE,
    ):
        if evidence.scope.application_scope and len(evidence.behavior_scenarios) < 3:
            reasons.append("broader scenario coverage required for stable promotion")
        if REQUIRED_STABLE_SECURITY_REVIEW and not evidence.security_review_complete:
            reasons.append("security review required for stable promotion")
        if not evidence.regression_suite_stable:
            reasons.append("regression suite must be stable for stable promotion")
        if not evidence.explicit_human_approval:
            reasons.append("explicit human approval required for stable promotion")

    else:
        allowed_direct = {
            (CapabilityMaturityState.DECLARED, CapabilityMaturityState.EXPERIMENTAL),
        }
        if transition not in allowed_direct:
            reasons.append(f"unsupported promotion transition: {current.value} -> {proposed.value}")

    if proposed == CapabilityMaturityState.STABLE:
        if evidence.scope.application_scope and len(evidence.scope.application_scope) <= 2:
            reasons.append("bounded fixture evidence cannot produce global stable state")

    return PolicyResult(allowed=len(reasons) == 0, reasons=reasons)


def assert_promotion_allowed(evidence: PromotionEvidence) -> None:
    result = evaluate_promotion_policy(evidence)
    if not result.allowed:
        raise PolicyViolationError("; ".join(result.reasons))
