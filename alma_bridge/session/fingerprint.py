from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional


def remediation_fingerprint(
    *,
    strategy_id: str,
    remediation_id: Optional[str],
    env: Dict[str, str],
    launch_args: List[str],
    phase: str = "run",
) -> str:
    payload = {
        "strategy_id": strategy_id,
        "remediation_id": remediation_id or "",
        "phase": phase,
        "env": sorted((k, env[k]) for k in env if k.startswith(("ALMA_", "WINE", "WINED", "DXVK", "ELECTRON"))),
        "args": launch_args,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


class RetryGuard:
    """Per-session duplicate remediation and budget tracking."""

    def __init__(
        self,
        *,
        max_attempts: int,
        per_remediation_limit: int = 2,
        max_identical_fingerprints: int = 3,
        session_timeout_sec: Optional[int] = None,
        started_monotonic: Optional[float] = None,
    ) -> None:
        import time

        self.max_attempts = max_attempts
        self.per_remediation_limit = per_remediation_limit
        self.max_identical_fingerprints = max_identical_fingerprints
        self.session_timeout_sec = session_timeout_sec
        self._started = started_monotonic or time.monotonic()
        self._fingerprints: List[str] = []
        self._remediation_counts: Dict[str, int] = {}
        self._escalation_signatures: set[str] = set()

    def attempt_allowed(self, attempt_number: int) -> bool:
        return attempt_number < self.max_attempts

    def session_timed_out(self) -> bool:
        if not self.session_timeout_sec:
            return False
        import time

        return (time.monotonic() - self._started) >= self.session_timeout_sec

    def remediation_allowed(self, remediation_id: Optional[str], fingerprint: str) -> tuple[bool, str]:
        key = remediation_id or "__baseline__"
        count = self._remediation_counts.get(key, 0)
        if count >= self.per_remediation_limit:
            return False, f"per_remediation_limit:{key}"
        if fingerprint in self._fingerprints:
            streak = self._consecutive_identical(fingerprint)
            if streak >= self.max_identical_fingerprints:
                return False, f"duplicate_loop:{fingerprint}"
        return True, ""

    def record_attempt(self, remediation_id: Optional[str], fingerprint: str) -> None:
        key = remediation_id or "__baseline__"
        self._remediation_counts[key] = self._remediation_counts.get(key, 0) + 1
        self._fingerprints.append(fingerprint)

    def escalation_allowed(self, signature: Optional[str]) -> bool:
        sig = signature or "unknown_error"
        if sig in self._escalation_signatures:
            return False
        self._escalation_signatures.add(sig)
        return True

    def _consecutive_identical(self, fingerprint: str) -> int:
        streak = 0
        for item in reversed(self._fingerprints):
            if item != fingerprint:
                break
            streak += 1
        return streak
