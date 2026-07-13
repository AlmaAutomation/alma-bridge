"""Bounded budget for auto-compatibility escalation loops."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


AUTO_COMPATIBILITY_BUDGET_EXHAUSTED = "AUTO_COMPATIBILITY_BUDGET_EXHAUSTED"


@dataclass
class AutoCompatibilityBudget:
    """Session-scoped limits for execution, escalation, and no-progress detection."""

    max_execution_attempts: int = 64
    max_routes: int = 12
    max_bridge_retries: int = 8
    max_remediations: int = 32
    max_identical_tuple: int = 4
    wall_clock_sec: int = 3600

    execution_attempts: int = 0
    routes_attempted: int = 0
    bridge_retries: int = 0
    remediation_applications: int = 0
    started_monotonic: float = field(default_factory=time.monotonic)
    exhausted: bool = False
    exhaustion_reason: Optional[str] = None
    exhaustion_dimension: Optional[str] = None
    _signature_counts: Dict[str, int] = field(default_factory=dict)
    _tuple_counts: Dict[str, int] = field(default_factory=dict)
    _verification_confidence_peak: float = 0.0

    @classmethod
    def from_settings(cls, settings: Any) -> "AutoCompatibilityBudget":
        return cls(
            max_execution_attempts=int(
                getattr(settings, "auto_compat_max_execution_attempts", 64)
            ),
            max_routes=int(getattr(settings, "auto_compat_max_routes", 12)),
            max_bridge_retries=int(
                getattr(settings, "auto_compat_max_bridge_retries", 8)
            ),
            max_remediations=int(
                getattr(settings, "auto_compat_max_remediations", 32)
            ),
            max_identical_tuple=int(
                getattr(settings, "auto_compat_max_identical_tuple", 4)
            ),
            wall_clock_sec=int(getattr(settings, "auto_compat_wall_clock_sec", 3600)),
        )

    def check(self) -> Optional[str]:
        if self.exhausted:
            return self.exhaustion_reason
        if self.execution_attempts >= self.max_execution_attempts:
            return self._exhaust("execution_attempts", "max_execution_attempts")
        if self.routes_attempted >= self.max_routes:
            return self._exhaust("routes", "max_routes")
        if self.bridge_retries >= self.max_bridge_retries:
            return self._exhaust("bridge_retries", "max_bridge_retries")
        if self.remediation_applications >= self.max_remediations:
            return self._exhaust("remediations", "max_remediations")
        elapsed = time.monotonic() - self.started_monotonic
        if elapsed >= self.wall_clock_sec:
            return self._exhaust("wall_clock", "wall_clock_sec")
        return None

    def record_execution_attempt(self) -> Optional[str]:
        self.execution_attempts += 1
        return self.check()

    def record_route(self) -> Optional[str]:
        self.routes_attempted += 1
        return self.check()

    def record_bridge_retry(self) -> Optional[str]:
        self.bridge_retries += 1
        return self.check()

    def record_remediation(self) -> Optional[str]:
        self.remediation_applications += 1
        return self.check()

    def record_failure_signature(self, signature: Optional[str]) -> Optional[str]:
        sig = signature or "unknown_error"
        self._signature_counts[sig] = self._signature_counts.get(sig, 0) + 1
        return None

    def record_no_progress_tuple(
        self,
        *,
        program_identity: str,
        strategy_id: str,
        remediation_ids: List[Optional[str]],
        failure_signature: Optional[str],
        state_fingerprint: Optional[str],
        verification_confidence: float = 0.0,
    ) -> Optional[str]:
        if verification_confidence > self._verification_confidence_peak:
            self._verification_confidence_peak = verification_confidence
            return None
        key = _tuple_key(
            program_identity,
            strategy_id,
            remediation_ids,
            failure_signature,
            state_fingerprint,
        )
        count = self._tuple_counts.get(key, 0) + 1
        self._tuple_counts[key] = count
        if count >= self.max_identical_tuple:
            return self._exhaust("no_progress_tuple", "max_identical_tuple")
        return self.check()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "execution_attempts": self.execution_attempts,
            "routes_attempted": self.routes_attempted,
            "bridge_retries": self.bridge_retries,
            "remediation_applications": self.remediation_applications,
            "exhausted": self.exhausted,
            "exhaustion_reason": self.exhaustion_reason,
            "exhaustion_dimension": self.exhaustion_dimension,
            "signature_counts": dict(self._signature_counts),
            "tuple_counts": {k: v for k, v in self._tuple_counts.items() if v > 1},
            "verification_confidence_peak": self._verification_confidence_peak,
            "limits": {
                "max_execution_attempts": self.max_execution_attempts,
                "max_routes": self.max_routes,
                "max_bridge_retries": self.max_bridge_retries,
                "max_remediations": self.max_remediations,
                "max_identical_tuple": self.max_identical_tuple,
                "wall_clock_sec": self.wall_clock_sec,
            },
        }

    def _exhaust(self, dimension: str, limit_name: str) -> str:
        self.exhausted = True
        self.exhaustion_dimension = dimension
        self.exhaustion_reason = AUTO_COMPATIBILITY_BUDGET_EXHAUSTED
        return f"{AUTO_COMPATIBILITY_BUDGET_EXHAUSTED}:{dimension}:{limit_name}"


def _tuple_key(
    program_identity: str,
    strategy_id: str,
    remediation_ids: List[Optional[str]],
    failure_signature: Optional[str],
    state_fingerprint: Optional[str],
) -> str:
    remediation_key = ",".join(sorted(r or "" for r in remediation_ids))
    return "|".join(
        [
            program_identity,
            strategy_id,
            remediation_key,
            failure_signature or "unknown_error",
            state_fingerprint or "",
        ]
    )
