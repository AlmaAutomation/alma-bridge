from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol, Tuple

VERIFIER_VERSION = "1.1.0"

DEFAULT_POLICY_ID = "bridge_aggregate_v1"
DEFAULT_POLICY_VERSION = "1.0.0"
WINE_GUI_POLICY_ID = "wine_gui_process_v1"
WINE_GUI_POLICY_VERSION = "1.0.0"


@dataclass
class VerificationCheckResult:
    verifier_id: str
    verifier_version: str
    check_kind: str
    passed: bool
    confidence: float
    evidence: List[str] = field(default_factory=list)
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class AggregateSuccessPolicy:
    policy_id: str
    policy_version: str
    required_checks: Dict[str, List[str]]
    optional_checks: Dict[str, List[str]] = field(default_factory=dict)
    minimum_confidence: float = 0.5
    contradictory_evidence_behavior: str = "fail_closed"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "required_checks": self.required_checks,
            "optional_checks": self.optional_checks,
            "minimum_confidence": self.minimum_confidence,
            "contradictory_evidence_behavior": self.contradictory_evidence_behavior,
        }


DEFAULT_AGGREGATE_POLICY = AggregateSuccessPolicy(
    policy_id=DEFAULT_POLICY_ID,
    policy_version=DEFAULT_POLICY_VERSION,
    required_checks={
        "native": ["exit_code_zero"],
        "install": ["installer_not_false_success", "prefix_has_launcher"],
        "launcher": ["process_survives"],
        "wine_gui": ["process_survives"],
    },
    optional_checks={
        "launcher": ["log_excludes_signature"],
        "wine_gui": ["target_process_identity"],
        "install": [],
        "native": [],
    },
    minimum_confidence=0.5,
    contradictory_evidence_behavior="fail_closed",
)


WINE_GUI_AGGREGATE_POLICY = AggregateSuccessPolicy(
    policy_id=WINE_GUI_POLICY_ID,
    policy_version=WINE_GUI_POLICY_VERSION,
    required_checks={
        "wine_gui": ["process_survives"],
    },
    optional_checks={
        "wine_gui": ["target_process_identity"],
    },
    minimum_confidence=0.5,
    contradictory_evidence_behavior="fail_closed",
)


@dataclass
class ExecutionEvidence:
    """Typed execution output consumed by VerificationEngine."""

    session_id: str
    attempt_number: int
    phase: str
    result: Dict[str, Any]
    file_path: str
    installer: bool = False
    electron: bool = False
    gui_launcher: bool = False
    wine_gui: bool = False
    wine_prefix: Optional[str] = None
    launcher_path: Optional[str] = None
    before_snapshot: Any = None
    baseline_pids: Optional[set[int]] = None


@dataclass
class VerificationResult:
    passed: bool
    confidence: float
    checks: List[VerificationCheckResult] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    failure_reason: Optional[str] = None
    retryable: bool = True
    recommended_next_action: Optional[str] = None
    success_policy: AggregateSuccessPolicy = field(default_factory=lambda: DEFAULT_AGGREGATE_POLICY)
    error_signature: Optional[str] = None
    verifier_exception: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "passed": self.passed,
            "confidence": self.confidence,
            "checks": [
                {
                    "verifier_id": c.verifier_id,
                    "verifier_version": c.verifier_version,
                    "check_kind": c.check_kind,
                    "passed": c.passed,
                    "confidence": c.confidence,
                    "evidence": c.evidence,
                    "timestamp": c.timestamp,
                }
                for c in self.checks
            ],
            "evidence": self.evidence,
            "failure_reason": self.failure_reason,
            "retryable": self.retryable,
            "recommended_next_action": self.recommended_next_action,
            "success_policy": self.success_policy.to_dict(),
            "error_signature": self.error_signature,
            "verifier_exception": self.verifier_exception,
        }


# Backward-compatible alias
VerificationOutcome = VerificationResult


def evaluate_aggregate_policy(
    checks: List[VerificationCheckResult],
    policy: AggregateSuccessPolicy,
    phase: str,
) -> Tuple[bool, float]:
    """Apply versioned aggregate success policy for a session phase."""
    required = policy.required_checks.get(phase, [])
    if not required and phase == "install":
        required = policy.required_checks.get("install", [])
    if not required and not policy.required_checks.get(phase):
        required = policy.required_checks.get("native", [])

    confidences: List[float] = []
    for check_kind in required:
        matching = [c for c in checks if c.check_kind == check_kind]
        if not matching:
            return False, 0.0
        if not all(c.passed for c in matching):
            if policy.contradictory_evidence_behavior == "fail_closed":
                return False, min(c.confidence for c in matching)
            return False, min(c.confidence for c in matching)
        confidences.extend(c.confidence for c in matching)

    aggregate_confidence = (
        sum(confidences) / len(confidences) if confidences else 0.0
    )
    if aggregate_confidence < policy.minimum_confidence:
        return False, aggregate_confidence
    return True, aggregate_confidence


def verification_result_from_exception(exc: Exception) -> VerificationResult:
    return VerificationResult(
        passed=False,
        confidence=0.0,
        checks=[
            VerificationCheckResult(
                verifier_id="verification_engine",
                verifier_version=VERIFIER_VERSION,
                check_kind="engine_runtime",
                passed=False,
                confidence=0.0,
                evidence=[str(exc)],
            )
        ],
        evidence=[str(exc)],
        failure_reason="verification_engine_exception",
        retryable=True,
        recommended_next_action="retry_with_remediation",
        error_signature="verification_engine_exception",
        verifier_exception=str(exc),
    )


class VerificationEngine(Protocol):
    def verify_execution(self, evidence: ExecutionEvidence) -> VerificationResult: ...

    def verify_installer(
        self,
        *,
        wine_prefix: str,
        before_snapshot: Any,
        stdout: str,
        stderr: str,
        installer_path: str,
        duration_ms: int,
        exit_code: int,
    ) -> VerificationResult: ...

    def verify_launcher(
        self,
        *,
        result: Dict[str, object],
        wine_prefix: str,
        launcher_path: str,
        exclude_pids: Optional[set[int]] = None,
    ) -> VerificationResult: ...

    def verify_wine_gui(
        self,
        *,
        result: Dict[str, object],
        wine_prefix: str,
        target_path: str,
        exclude_pids: Optional[set[int]] = None,
    ) -> VerificationResult: ...

    def verify_process_result(
        self,
        *,
        result: Dict[str, object],
        gui_launcher: bool,
    ) -> VerificationResult: ...


class DefaultVerificationEngine:
    def verify_execution(self, evidence: ExecutionEvidence) -> VerificationResult:
        if evidence.phase == "wine_gui":
            raw = dict(evidence.result)
            outcome = self.verify_wine_gui(
                result=raw,
                wine_prefix=evidence.wine_prefix or "",
                target_path=evidence.launcher_path or evidence.file_path,
                exclude_pids=evidence.baseline_pids,
            )
            policy = WINE_GUI_AGGREGATE_POLICY
        elif evidence.phase == "launcher" or (
            evidence.gui_launcher and not evidence.installer
        ):
            raw = dict(evidence.result)
            outcome = self.verify_launcher(
                result=raw,
                wine_prefix=evidence.wine_prefix or "",
                launcher_path=evidence.launcher_path or evidence.file_path,
                exclude_pids=evidence.baseline_pids,
            )
            policy = DEFAULT_AGGREGATE_POLICY
        elif evidence.installer:
            raw = evidence.result
            outcome = self.verify_installer(
                wine_prefix=evidence.wine_prefix or "",
                before_snapshot=evidence.before_snapshot,
                stdout=str(raw.get("stdout", "")),
                stderr=str(raw.get("stderr", "")),
                installer_path=evidence.file_path,
                duration_ms=int(raw.get("duration_ms", 0)),
                exit_code=int(raw.get("exit_code", 0) or 0),
            )
            policy = DEFAULT_AGGREGATE_POLICY
        else:
            outcome = self.verify_process_result(
                result=evidence.result,
                gui_launcher=evidence.gui_launcher,
            )
            policy = DEFAULT_AGGREGATE_POLICY
        passed, confidence = evaluate_aggregate_policy(
            outcome.checks,
            policy,
            evidence.phase,
        )
        return VerificationResult(
            passed=passed,
            confidence=confidence,
            checks=outcome.checks,
            evidence=outcome.evidence,
            failure_reason=None if passed else outcome.failure_reason,
            retryable=outcome.retryable,
            recommended_next_action=outcome.recommended_next_action,
            success_policy=policy,
            error_signature=outcome.error_signature,
        )

    def verify_installer(
        self,
        *,
        wine_prefix: str,
        before_snapshot: Any,
        stdout: str,
        stderr: str,
        installer_path: str,
        duration_ms: int,
        exit_code: int,
    ) -> VerificationResult:
        from alma_bridge.execution.errors import detect_installer_false_success
        from alma_bridge.execution.installer_verify import verify_installer_outcome
        from alma_bridge.execution.preflight import read_wine_windows_version

        checks: List[VerificationCheckResult] = []
        false_success = detect_installer_false_success(
            stderr,
            stdout,
            duration_ms=duration_ms,
            exit_code=exit_code,
            wine_windows_version=read_wine_windows_version(wine_prefix),
        )
        checks.append(
            VerificationCheckResult(
                verifier_id="installer_false_success",
                verifier_version=VERIFIER_VERSION,
                check_kind="installer_not_false_success",
                passed=false_success is None,
                confidence=0.95 if false_success is None else 0.1,
                evidence=[false_success] if false_success else ["no_false_success_signature"],
            )
        )
        if false_success:
            return VerificationResult(
                passed=False,
                confidence=0.1,
                checks=checks,
                evidence=[false_success],
                failure_reason=false_success,
                retryable=True,
                recommended_next_action="retry_with_remediation",
                success_policy=DEFAULT_AGGREGATE_POLICY,
                error_signature=false_success,
            )

        verified, install_evidence = verify_installer_outcome(
            wine_prefix=wine_prefix,
            before=before_snapshot,
            stdout=stdout,
            stderr=stderr,
            installer_path=installer_path,
            duration_ms=duration_ms,
        )
        checks.append(
            VerificationCheckResult(
                verifier_id="installer_verify",
                verifier_version=VERIFIER_VERSION,
                check_kind="prefix_has_launcher",
                passed=verified,
                confidence=0.9 if verified else 0.2,
                evidence=list(install_evidence),
            )
        )
        return VerificationResult(
            passed=verified,
            confidence=0.9 if verified else 0.2,
            checks=checks,
            evidence=list(install_evidence),
            failure_reason=None if verified else "installer_not_verified",
            retryable=True,
            recommended_next_action=None if verified else "bootstrap_runtimes_and_retry",
            success_policy=DEFAULT_AGGREGATE_POLICY,
            error_signature=None if verified else "installer_not_verified",
        )

    def verify_launcher(
        self,
        *,
        result: Dict[str, object],
        wine_prefix: str,
        launcher_path: str,
        exclude_pids: Optional[set[int]] = None,
    ) -> VerificationResult:
        from alma_bridge.execution.electron_handoff import evaluate_electron_launch_result

        updated, signature, recommended = evaluate_electron_launch_result(
            result,
            wine_prefix=wine_prefix,
            launcher_path=launcher_path,
            exclude_pids=exclude_pids,
        )
        launch_verification = list(updated.get("launch_verification") or [])
        process_passed = bool(updated.get("success")) and bool(launch_verification)
        checks = [
            VerificationCheckResult(
                verifier_id="electron_handoff",
                verifier_version=VERIFIER_VERSION,
                check_kind="process_survives",
                passed=process_passed,
                confidence=0.92 if process_passed else 0.25,
                evidence=launch_verification or ([signature] if signature else []),
            )
        ]
        if signature:
            checks.append(
                VerificationCheckResult(
                    verifier_id="electron_handoff",
                    verifier_version=VERIFIER_VERSION,
                    check_kind="log_excludes_signature",
                    passed=False,
                    confidence=0.8,
                    evidence=[signature],
                )
            )
        return VerificationResult(
            passed=process_passed,
            confidence=0.92 if process_passed else 0.25,
            checks=checks,
            evidence=launch_verification,
            failure_reason=signature,
            retryable=signature not in {"permission_denied"},
            recommended_next_action=recommended[0] if recommended else None,
            success_policy=DEFAULT_AGGREGATE_POLICY,
            error_signature=signature,
        )

    def verify_wine_gui(
        self,
        *,
        result: Dict[str, object],
        wine_prefix: str,
        target_path: str,
        exclude_pids: Optional[set[int]] = None,
    ) -> VerificationResult:
        from pathlib import Path

        from alma_bridge.execution.wine_gui_handoff import evaluate_wine_gui_launch_result

        updated, signature, verification = evaluate_wine_gui_launch_result(
            result,
            wine_prefix=wine_prefix,
            target_path=target_path,
            exclude_pids=exclude_pids,
        )
        process_passed = bool(updated.get("success")) and bool(verification)
        target_name = Path(target_path).name
        identity_passed = any(target_name in line for line in verification)
        checks = [
            VerificationCheckResult(
                verifier_id="wine_gui_handoff",
                verifier_version=VERIFIER_VERSION,
                check_kind="process_survives",
                passed=process_passed,
                confidence=0.9 if process_passed else 0.2,
                evidence=verification or ([signature] if signature else []),
            )
        ]
        if verification:
            checks.append(
                VerificationCheckResult(
                    verifier_id="wine_gui_handoff",
                    verifier_version=VERIFIER_VERSION,
                    check_kind="target_process_identity",
                    passed=identity_passed,
                    confidence=0.85 if identity_passed else 0.2,
                    evidence=verification,
                )
            )
        return VerificationResult(
            passed=process_passed,
            confidence=0.9 if process_passed else 0.2,
            checks=checks,
            evidence=verification,
            failure_reason=signature,
            retryable=signature not in {"permission_denied"},
            recommended_next_action=None,
            success_policy=WINE_GUI_AGGREGATE_POLICY,
            error_signature=signature,
        )

    def verify_process_result(
        self,
        *,
        result: Dict[str, object],
        gui_launcher: bool,
    ) -> VerificationResult:
        if gui_launcher:
            pending = "[alma] launcher detached" in str(result.get("stderr", "")).lower()
            passed = bool(result.get("success")) and not pending
            return VerificationResult(
                passed=passed,
                confidence=0.5 if pending else (0.85 if passed else 0.2),
                checks=[
                    VerificationCheckResult(
                        verifier_id="runner",
                        verifier_version=VERIFIER_VERSION,
                        check_kind="process_starts",
                        passed=passed,
                        confidence=0.5 if pending else (0.85 if passed else 0.2),
                        evidence=[str(result.get("error_signature") or "ok")],
                    )
                ],
                failure_reason=str(result.get("error_signature") or "") or None,
                retryable=True,
                success_policy=DEFAULT_AGGREGATE_POLICY,
                error_signature=str(result.get("error_signature") or "") or None,
            )
        passed = bool(result.get("success"))
        return VerificationResult(
            passed=passed,
            confidence=0.9 if passed else 0.3,
            checks=[
                VerificationCheckResult(
                    verifier_id="runner",
                    verifier_version=VERIFIER_VERSION,
                    check_kind="exit_code_zero",
                    passed=passed,
                    confidence=0.9 if passed else 0.3,
                    evidence=[f"exit_code={result.get('exit_code')}"],
                )
            ],
            failure_reason=str(result.get("error_signature") or "") or None,
            retryable=True,
            success_policy=DEFAULT_AGGREGATE_POLICY,
            error_signature=str(result.get("error_signature") or "") or None,
        )
