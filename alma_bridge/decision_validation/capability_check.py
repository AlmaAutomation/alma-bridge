"""Runtime feasibility checks using read-only inventory."""

from __future__ import annotations

import platform
import shutil
from typing import Callable, List, Optional

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.decision.models import DecisionPlan
from alma_bridge.decision_validation.models import (
    ValidationCheck,
    ValidationCheckCategory,
    ValidationCheckSeverity,
)
from alma_bridge.storage import outcomes


def _normalize_arch(value: Optional[str]) -> str:
    arch = (value or "").lower()
    if any(token in arch for token in ("x86_64", "amd64")):
        return "x86_64"
    if arch in {"x86", "i386", "i686"}:
        return "x86"
    if any(token in arch for token in ("aarch64", "arm64")):
        return "arm64"
    return "unknown"


def _check(
    *,
    code: str,
    message: str,
    passed: bool,
    severity: ValidationCheckSeverity = ValidationCheckSeverity.BLOCKING,
) -> ValidationCheck:
    return ValidationCheck(
        check_id=sha256_v1({"category": "runtime_feasibility", "code": code}),
        category=ValidationCheckCategory.RUNTIME_FEASIBILITY,
        code=code,
        message=message,
        severity=severity,
        passed=passed,
    )


def check_runtime_feasibility(
    plan: DecisionPlan,
    *,
    which: Callable[[str], Optional[str]] = shutil.which,
    host_arch: Optional[str] = None,
) -> List[ValidationCheck]:
    """Evaluate runtime provider availability without launching processes."""
    checks: List[ValidationCheck] = []
    host = _normalize_arch(host_arch or platform.machine())

    wine_available = which("wine") is not None
    try:
        from alma_bridge.hardware.proton import find_proton_installs

        proton_available = bool(find_proton_installs())
    except Exception:
        proton_available = which("proton") is not None
    checks.append(
        _check(
            code="runtime_provider_available",
            message=(
                "Wine runtime is available on the host."
                if wine_available
                else "Wine runtime is not available on the host."
            ),
            passed=wine_available,
        )
    )

    required_runtime = _required_runtime_from_plan(plan)
    if required_runtime == "proton":
        checks.append(
            _check(
                code="proton_runtime_available",
                message=(
                    "Named Proton runtime requirement is satisfied by host inventory."
                    if proton_available
                    else "Named Proton runtime requirement is not satisfied by host inventory."
                ),
                passed=proton_available,
            )
        )

    session_arch = _session_architecture(plan.session_id)
    if session_arch and session_arch != "unknown":
        compatible = session_arch == host or (session_arch == "x86" and host == "x86_64")
        checks.append(
            _check(
                code="architecture_supported",
                message=(
                    f"Session architecture {session_arch} is supported on host {host}."
                    if compatible
                    else f"Session architecture {session_arch} is not supported on host {host}."
                ),
                passed=compatible,
            )
        )

    return checks


def _required_runtime_from_plan(plan: DecisionPlan) -> Optional[str]:
    serialized = plan.model_dump_json().lower()
    if "proton" in serialized:
        return "proton"
    if "wine" in serialized:
        return "wine"
    return None


def _session_architecture(session_id: Optional[str]) -> Optional[str]:
    if not session_id:
        return None
    session = outcomes.get_session(session_id)
    if not session:
        return None
    profile = session.get("hardware_profile") or {}
    return _normalize_arch(str(profile.get("architecture") or profile.get("arch") or ""))
