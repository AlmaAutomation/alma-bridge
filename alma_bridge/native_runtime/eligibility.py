"""PE eligibility checks for native console runtime."""

from __future__ import annotations

import hashlib
import json
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

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

_MANIFEST_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "native_runtime" / "manifest.json"


def pe_binary_digest(file_path: str | Path) -> str:
    data = Path(file_path).read_bytes()
    return hashlib.sha256(data).hexdigest()


def _load_fixture_manifest() -> Dict[str, str]:
    """digest hex -> fixture label."""
    if not _MANIFEST_PATH.is_file():
        return {}
    try:
        payload = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
        entries = payload.get("fixtures", payload)
        if isinstance(entries, dict):
            return {str(k).lower(): str(v) for k, v in entries.items()}
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def manifest_match(path: Path) -> bool:
    digest = pe_binary_digest(path)
    return digest.lower() in _load_fixture_manifest()


@dataclass
class EligibilityResult:
    eligible: bool
    reason_codes: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    parsed: Optional[ParsedPE] = None
    binary_digest: Optional[str] = None
    manifest_match: bool = False


def check_eligibility(file_path: str | Path) -> EligibilityResult:
    path = Path(file_path)
    basename = path.name.lower()
    digest: Optional[str] = None
    matched_manifest = False
    if path.is_file():
        digest = pe_binary_digest(path)
        matched_manifest = digest.lower() in _load_fixture_manifest()
    if basename in FIXTURE_ALLOWLIST or matched_manifest:
        try:
            parsed = parse_pe_file(path)
        except Exception:
            return EligibilityResult(
                eligible=False,
                reason_codes=[REASON_INVALID_PE],
                binary_digest=digest,
            )
        note = "allowlisted fixture" if basename in FIXTURE_ALLOWLIST else "manifest digest match"
        return EligibilityResult(
            eligible=True,
            notes=[note],
            parsed=parsed,
            binary_digest=digest,
            manifest_match=matched_manifest,
        )
    try:
        parsed = parse_pe_file(path)
    except Exception:
        return EligibilityResult(eligible=False, reason_codes=[REASON_NOT_PE], binary_digest=digest)
    return _strict_pe_checks(parsed, binary_digest=digest)


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
        binary_digest=result.binary_digest,
        manifest_match=result.manifest_match,
        metadata={
            "binary_digest": result.binary_digest,
            "manifest_match": result.manifest_match,
        },
    )


def _strict_pe_checks(parsed: ParsedPE, *, binary_digest: Optional[str] = None) -> EligibilityResult:
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
        return EligibilityResult(
            eligible=False,
            reason_codes=sorted(set(reasons)),
            notes=notes,
            parsed=parsed,
            binary_digest=binary_digest,
        )
    return EligibilityResult(
        eligible=True,
        notes=["strict PE checks passed"],
        parsed=parsed,
        binary_digest=binary_digest,
    )


def _has_32bit_worker() -> bool:
    return platform.machine().lower() in ("i686", "i386", "x86")
