from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional

from alma_bridge.session.services.verification import (
    DEFAULT_POLICY_ID,
    DEFAULT_POLICY_VERSION,
    WINE_GUI_POLICY_ID,
    WINE_GUI_POLICY_VERSION,
)


@dataclass(frozen=True)
class ExpectedVerificationContract:
    """Deterministic verification contract inferred before planning."""

    policy_id: str
    policy_version: str
    phase: str
    program_kind: str
    required_checks: List[str]
    optional_checks: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "policy_version": self.policy_version,
            "phase": self.phase,
            "program_kind": self.program_kind,
            "required_checks": list(self.required_checks),
            "optional_checks": list(self.optional_checks),
        }


def expected_verification_contract_for_kind(kind: Mapping[str, Any]) -> ExpectedVerificationContract:
    """
    Build the expected verification contract from program inspection only.
    Used by shadow pre-plan eligibility (pattern C) without calling the planner.
    """
    program_kind = str(kind.get("program_kind") or "unknown")
    if program_kind == "pe_windows_gui":
        return ExpectedVerificationContract(
            policy_id=WINE_GUI_POLICY_ID,
            policy_version=WINE_GUI_POLICY_VERSION,
            phase="wine_gui",
            program_kind=program_kind,
            required_checks=["process_survives"],
            optional_checks=["target_process_identity"],
        )
    if program_kind == "native_script":
        return ExpectedVerificationContract(
            policy_id=DEFAULT_POLICY_ID,
            policy_version=DEFAULT_POLICY_VERSION,
            phase="native",
            program_kind=program_kind,
            required_checks=["exit_code_zero"],
            optional_checks=[],
        )
    if bool(kind.get("is_installer")):
        return ExpectedVerificationContract(
            policy_id=DEFAULT_POLICY_ID,
            policy_version=DEFAULT_POLICY_VERSION,
            phase="install",
            program_kind=program_kind,
            required_checks=["installer_not_false_success", "prefix_has_launcher"],
            optional_checks=[],
        )
    if bool(kind.get("is_electron")) or bool(kind.get("needs_gui")):
        return ExpectedVerificationContract(
            policy_id=DEFAULT_POLICY_ID,
            policy_version=DEFAULT_POLICY_VERSION,
            phase="launcher",
            program_kind=program_kind,
            required_checks=["process_survives"],
            optional_checks=["log_excludes_signature"],
        )
    return ExpectedVerificationContract(
        policy_id=DEFAULT_POLICY_ID,
        policy_version=DEFAULT_POLICY_VERSION,
        phase="native",
        program_kind=program_kind,
        required_checks=["exit_code_zero"],
        optional_checks=[],
    )


def expected_verification_contract_for_path(
    file_path: str,
    *,
    host_arch: str = "x86_64",
) -> ExpectedVerificationContract:
    from alma_bridge.compatibility.program_kind import classify_program_kind

    kind = classify_program_kind(file_path, host_arch=host_arch)
    return expected_verification_contract_for_kind(kind)
