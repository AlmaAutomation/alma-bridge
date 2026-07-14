from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Protocol

from alma_bridge.schemas.models import AttemptRecord
from alma_bridge.session.lifecycle import InvalidSessionTransition, SessionLifecycleManager
from alma_bridge.session.services.verification import (
    DefaultVerificationEngine,
    ExecutionEvidence,
    verification_result_from_exception,
)
from alma_bridge.session.state import SessionState
from alma_bridge.storage import outcomes


class TransitionFn(Protocol):
    def __call__(
        self,
        lifecycle: SessionLifecycleManager,
        state: SessionState,
        *,
        reason: str,
        attempt_number: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None: ...


@dataclass
class VerificationBoundaryResult:
    policy_passed: bool
    verification: Dict[str, Any]
    error_signature: Optional[str] = None
    recommended_actions: Optional[list[str]] = None


class VerificationGateway:
    """Runs OBSERVING → VERIFYING/CLASSIFYING and invokes VerificationEngine."""

    def __init__(
        self,
        verifier: DefaultVerificationEngine,
        *,
        transition: TransitionFn,
    ) -> None:
        self._verifier = verifier
        self._transition = transition

    def run(
        self,
        *,
        lifecycle: SessionLifecycleManager,
        evidence: ExecutionEvidence,
        record: AttemptRecord,
    ) -> VerificationBoundaryResult:
        record.success = False
        try:
            self._transition(
                lifecycle,
                SessionState.OBSERVING,
                reason="execution_complete",
                attempt_number=record.attempt_number,
            )
        except InvalidSessionTransition:
            pass

        if not _eligible_for_verification(evidence):
            try:
                self._transition(
                    lifecycle,
                    SessionState.CLASSIFYING,
                    reason="execution_failed",
                    attempt_number=record.attempt_number,
                )
            except InvalidSessionTransition:
                pass
            return VerificationBoundaryResult(
                policy_passed=False,
                verification={},
                error_signature=str(evidence.result.get("error_signature") or "execution_failed"),
            )

        try:
            self._transition(
                lifecycle,
                SessionState.VERIFYING,
                reason="verification_start",
                attempt_number=record.attempt_number,
            )
        except InvalidSessionTransition:
            return VerificationBoundaryResult(
                policy_passed=False,
                verification={},
                error_signature="lifecycle_error",
            )

        try:
            verification_result = self._verifier.verify_execution(evidence)
        except Exception as exc:  # noqa: BLE001
            verification_result = verification_result_from_exception(exc)

        verification_dict = verification_result.to_dict()
        if not verification_result.passed:
            try:
                self._transition(
                    lifecycle,
                    SessionState.CLASSIFYING,
                    reason=verification_result.failure_reason or "verification_failed",
                    attempt_number=record.attempt_number,
                )
            except InvalidSessionTransition:
                pass
            recommended = None
            if verification_result.recommended_next_action:
                recommended = [verification_result.recommended_next_action]
            return VerificationBoundaryResult(
                policy_passed=False,
                verification=verification_dict,
                error_signature=verification_result.error_signature
                or verification_result.failure_reason,
                recommended_actions=recommended,
            )

        return VerificationBoundaryResult(
            policy_passed=True,
            verification=verification_dict,
        )


def declare_verified_session_success(
    *,
    lifecycle: SessionLifecycleManager,
    session_id: str,
    transition: TransitionFn,
    summary: str,
    rerank_events: Optional[list] = None,
) -> None:
    """Single authority for SUCCEEDED — must originate from VERIFYING."""
    if lifecycle.state != SessionState.VERIFYING:
        raise InvalidSessionTransition(
            f"Cannot declare success from {lifecycle.state.value}; "
            "SUCCEEDED requires VERIFYING origin"
        )
    transition(
        lifecycle,
        SessionState.SUCCEEDED,
        reason="verification_passed",
    )
    outcomes.finalize_session(
        session_id,
        success=True,
        summary=summary,
        rerank_events=rerank_events,
    )


def _eligible_for_verification(evidence: ExecutionEvidence) -> bool:
    raw = evidence.result
    if (
        evidence.installer
        or evidence.gui_launcher
        or evidence.wine_gui
        or evidence.phase in {"launcher", "wine_gui"}
    ):
        return True
    return bool(raw.get("success"))
