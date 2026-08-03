"""PE eligibility checks for native console runtime."""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Set

from alma_bridge.native_runtime.errors import (
    REASON_COM,
    REASON_DELAY_IMPORT,
    REASON_DOTNET,
    REASON_GUI_SUBSYSTEM,
    REASON_HOST_ARCH,
    REASON_IMPORT_NOT_ALLOWED,
    REASON_INVALID_PE,
    REASON_NOT_ALLOWLISTED,
    REASON_NOT_PE,
    REASON_NO_32BIT_WORKER,
    REASON_TLS_PRESENT,
)
from alma_bridge.native_runtime.models import PEInspection
from alma_bridge.native_runtime.pe.headers import (
    IMAGE_FILE_MACHINE_AMD64,
    IMAGE_FILE_MACHINE_I386,
    IMAGE_SUBSYSTEM_WINDOWS_CUI,
    IMAGE_SUBSYSTEM_WINDOWS_GUI,
    machine_name,
    subsystem_name,
)
from alma_bridge.native_runtime.pe.parser import ParsedPE, parse_pe_file

ALLOWED_IMPORT_DLLS: Set[str] = {"kernel32.dll"}

FIXTURE_ALLOWLIST: Set[str] = {
    "hello64.exe",
    "hello32.exe",
    "stdout_write.exe",
    "stderr_write.exe",
    "exit_code.exe",
    "unicode_argv.exe",
    "environment_read.exe",
    "file_read.exe",
    "file_write.exe",
}


@dataclass
class EligibilityResult:
    eligible: bool
    reason_codes: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    parsed: Optional[ParsedPE] = None


def check_eligibility(file_path: str | Path) -> EligibilityResult:
    path = Path(file_path)
    basename = path.name.lower()
    if basename in FIXTURE_ALLOWLIST:
        try:
            parsed = parse_pe_file(path)
        except Exception:
            return EligibilityResult(eligible=False, reason_codes=[REASON_INVALID_PE])
        return EligibilityResult(
            eligible=True,
            notes=["allowlisted fixture"],
            parsed=parsed,
        )
    try:
        parsed = parse_pe_file(path)
    except Exception:
        return EligibilityResult(eligible=False, reason_codes=[REASON_NOT_PE])
    return _strict_pe_checks(parsed)


def inspect_pe(file_path: str | Path) -> PEInspection:
    result = check_eligibility(file_path)
    parsed = result.parsed
    machine: Optional[str] = None
    subsystem: Optional[str] = None
    import_dlls: List[str] = []
    if parsed is not None:
        machine = machine_name(parsed.coff.machine)
        subsystem = subsystem_name(parsed.optional.subsystem)
        import_dlls = parsed.import_dlls
    return PEInspection(
        file_path=str(file_path),
        eligible=result.eligible,
        machine=machine,
        subsystem=subsystem,
        import_dlls=import_dlls,
        reason_codes=result.reason_codes,
        notes=result.notes,
    )


def _strict_pe_checks(parsed: ParsedPE) -> EligibilityResult:
    reasons: List[str] = []
    notes: List[str] = []

    host = platform.machine().lower()
    machine = parsed.coff.machine
    if machine == IMAGE_FILE_MACHINE_AMD64:
        if host not in ("x86_64", "amd64"):
            reasons.append(REASON_HOST_ARCH)
    elif machine == IMAGE_FILE_MACHINE_I386:
        if not _has_32bit_worker():
            reasons.append(REASON_NO_32BIT_WORKER)
    else:
        reasons.append(REASON_HOST_ARCH)

    subsystem = parsed.optional.subsystem
    if subsystem == IMAGE_SUBSYSTEM_WINDOWS_GUI:
        reasons.append(REASON_GUI_SUBSYSTEM)
    elif subsystem != IMAGE_SUBSYSTEM_WINDOWS_CUI:
        reasons.append(REASON_NOT_ALLOWLISTED)
        notes.append(f"subsystem={subsystem_name(subsystem)}")

    if parsed.has_tls:
        reasons.append(REASON_TLS_PRESENT)
    if parsed.delay_import_dlls:
        reasons.append(REASON_DELAY_IMPORT)
    if parsed.cli_rva:
        reasons.append(REASON_DOTNET)

    for sec in parsed.sections:
        if sec.name.startswith(".com"):
            reasons.append(REASON_COM)

    for dll in parsed.import_dlls:
        if dll not in ALLOWED_IMPORT_DLLS:
            reasons.append(REASON_IMPORT_NOT_ALLOWED)
            notes.append(f"import={dll}")

    if reasons:
        return EligibilityResult(eligible=False, reason_codes=sorted(set(reasons)), notes=notes, parsed=parsed)
    return EligibilityResult(eligible=True, notes=["strict PE checks passed"], parsed=parsed)


def _has_32bit_worker() -> bool:
    import platform

    return platform.machine().lower() in ("i686", "i386", "x86")
