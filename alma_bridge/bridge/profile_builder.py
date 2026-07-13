from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from alma_bridge.compatibility.program_kind import classify_program_kind
from alma_bridge.compatibility.strategies import classify_binary
from alma_bridge.config import settings
from alma_bridge.execution.runner import file_hash
from alma_bridge.hardware.profiler import profile_hardware
from alma_bridge.schemas.bridge_domain import (
    CompatibilityInspection,
    GraphicsRequirement,
    HostCapabilityProfile,
    LibraryRef,
    ProgramIdentity,
    ProgramProfile,
    RuntimeRequirement,
)

_GENERIC_NAME_TOKENS = frozenset(
    {"setup", "install", "installer", "update", "bootstrap", "exe", "x64", "x86", "app"}
)


def _normalize_name_tokens(filename: str) -> List[str]:
    stem = Path(filename).stem.lower()
    tokens = re.split(r"[-_.\s]+", stem)
    return [
        token
        for token in tokens
        if len(token) >= 3 and token not in _GENERIC_NAME_TOKENS
    ]


def compute_program_fingerprint(
    *,
    program_format: str,
    architecture: str,
    program_kind: str,
    filename: str,
) -> str:
    """Stable fingerprint for profile reuse (similar programs, not exact bytes)."""
    payload = {
        "format": program_format,
        "architecture": architecture,
        "program_kind": program_kind,
        "name_tokens": sorted(_normalize_name_tokens(filename)),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


def compute_host_fingerprint(hardware: Dict[str, Any]) -> str:
    """Hash stable host fields used for compatibility profile reuse."""
    payload = {
        "architecture": hardware.get("architecture"),
        "os_bitness": hardware.get("os_bitness"),
        "distribution": hardware.get("distribution"),
        "capabilities": sorted(
            key for key, enabled in (hardware.get("capabilities") or {}).items() if enabled
        ),
        "legacy_indicators": sorted(hardware.get("legacy_indicators") or []),
        "gpu_vendor": (hardware.get("gpu") or {}).get("vendor"),
        "gpu_driver": (hardware.get("gpu") or {}).get("driver"),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


def _display_available() -> bool:
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _probe_elf_libraries(file_path: str) -> List[LibraryRef]:
    """Best-effort ldd probe for native ELF binaries."""
    path = Path(file_path)
    if not path.is_file():
        return []
    try:
        proc = subprocess.run(
            ["ldd", str(path)],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []

    libraries: List[LibraryRef] = []
    for line in (proc.stdout or "").splitlines():
        lower = line.lower().strip()
        if "not found" in lower:
            name = line.split()[0]
            libraries.append(LibraryRef(name=name, required=True, resolved=False))
        elif "=>" in line:
            name = line.split()[0]
            resolved_path = line.split("=>", 1)[1].strip().split()[0]
            libraries.append(
                LibraryRef(
                    name=name,
                    path=resolved_path,
                    required=True,
                    resolved=resolved_path != "not",
                )
            )
    return libraries


def _runtime_requirements_for_kind(kind: Dict[str, Any]) -> List[RuntimeRequirement]:
    requirements: List[RuntimeRequirement] = []
    if kind.get("needs_wine"):
        requirements.append(
            RuntimeRequirement(
                runtime="wine",
                required=True,
                reason="Windows PE binary requires Wine or Proton.",
            )
        )
        if kind.get("is_installer"):
            requirements.extend(
                [
                    RuntimeRequirement(
                        runtime="winetricks.vcrun",
                        version_hint="2019+",
                        required=True,
                        reason="Windows installers often need VC++ runtimes in the prefix.",
                    ),
                    RuntimeRequirement(
                        runtime="winetricks.dotnet48",
                        required=True,
                        reason="Windows installers/launchers often need .NET Framework 4.x.",
                    ),
                ]
            )
        if kind.get("is_electron"):
            requirements.append(
                RuntimeRequirement(
                    runtime="electron_wine_wrappers",
                    required=True,
                    reason="Electron launchers need Alma sidecar/elevate wrappers on Wine.",
                )
            )
    if kind.get("needs_native") and kind.get("binary_format") in {"elf32", "elf"}:
        requirements.append(
            RuntimeRequirement(
                runtime="native",
                required=True,
                reason="ELF binary runs on the Linux host.",
            )
        )
    return requirements


def _graphics_requirements_for_kind(kind: Dict[str, Any]) -> Optional[GraphicsRequirement]:
    if not kind.get("needs_gui"):
        return None
    electron = kind.get("is_electron")
    return GraphicsRequirement(
        api="opengl" if electron else "gdi",
        software_fallback_ok=True,
        gpu_required=False,
    )


def build_program_profile(
    file_path: str,
    *,
    host_arch: Optional[str] = None,
    scanner_data: Optional[Dict[str, Any]] = None,
) -> ProgramProfile:
    """Build a ProgramProfile from Bridge classification and optional scanner data."""
    path = Path(file_path).expanduser()
    hardware = profile_hardware()
    arch = host_arch or hardware.get("architecture", "x86_64")
    kind = classify_program_kind(str(path), host_arch=arch)

    binary_format = kind.get("binary_format", "unknown")
    if scanner_data:
        scanner_format = (scanner_data.get("format") or "").upper()
        if scanner_format == "ELF" and scanner_data.get("bitness") == "32-bit":
            binary_format = "elf32"
        elif scanner_format == "ELF":
            binary_format = "elf"
        elif scanner_format == "PE":
            binary_format = "pe"

    program_format = binary_format
    if program_format == "unknown" and path.exists():
        program_format = classify_binary(str(path), arch)

    architecture = arch
    if scanner_data and scanner_data.get("arch"):
        architecture = str(scanner_data["arch"])
    elif program_format == "elf32":
        architecture = "i386"
    elif program_format == "elf":
        architecture = "x86_64"
    elif program_format == "pe":
        architecture = "pe32+"

    sha = file_hash(str(path)) if path.is_file() else None
    stat = path.stat() if path.is_file() else None
    fingerprint = compute_program_fingerprint(
        program_format=program_format,
        architecture=architecture,
        program_kind=kind.get("program_kind", "unknown"),
        filename=path.name,
    )

    required_libraries: List[LibraryRef] = []
    if kind.get("needs_native") and path.is_file():
        required_libraries = _probe_elf_libraries(str(path))

    source = "scanner" if scanner_data else "bridge"
    return ProgramProfile(
        identity=ProgramIdentity(
            path=str(path),
            filename=path.name,
            sha256=sha,
            size_bytes=stat.st_size if stat else None,
            fingerprint=fingerprint,
            exists=path.is_file(),
        ),
        format=program_format,  # type: ignore[arg-type]
        architecture=architecture,
        program_kind=kind.get("program_kind", "unknown"),
        profile=kind.get("profile", "generic"),
        is_installer=bool(kind.get("is_installer")),
        is_electron=bool(kind.get("is_electron")),
        is_launcher=bool(kind.get("is_launcher")),
        needs_wine=bool(kind.get("needs_wine")),
        needs_gui=bool(kind.get("needs_gui")),
        needs_native=bool(kind.get("needs_native")),
        required_libraries=required_libraries,
        runtime_requirements=_runtime_requirements_for_kind(kind),
        environment_hints={},
        graphics_requirements=_graphics_requirements_for_kind(kind),
        source=source,
    )


def build_host_capability_profile(
    *,
    hardware: Optional[Dict[str, Any]] = None,
) -> HostCapabilityProfile:
    """Build a HostCapabilityProfile from the existing hardware profiler."""
    import socket

    hw = hardware or profile_hardware()
    caps = dict(hw.get("capabilities") or {})
    installed_runtimes = [name for name, enabled in caps.items() if enabled]

    return HostCapabilityProfile(
        host_fingerprint=compute_host_fingerprint(hw),
        hostname=socket.gethostname(),
        os=str(hw.get("os") or ""),
        os_version=str(hw.get("os_version") or ""),
        distribution=hw.get("distribution"),
        architecture=str(hw.get("architecture") or "unknown"),
        os_bitness=str(hw.get("os_bitness") or "unknown"),
        capabilities=caps,
        paths=dict(hw.get("paths") or {}),
        installed_runtimes=installed_runtimes,
        gpu=dict(hw.get("gpu") or {}),
        legacy_indicators=list(hw.get("legacy_indicators") or []),
        security_policies={
            "operator_autonomy": settings.operator_autonomy,
            "operator_allow_mutations": settings.operator_allow_mutations,
            "api_key_configured": bool(settings.api_key),
        },
        resources={
            "cpu_cores": hw.get("cpu_cores"),
            "ram_total_mb": hw.get("ram_total_mb"),
            "ram_gb": hw.get("ram_gb"),
            "storage_type": hw.get("storage_type"),
        },
        display_available=_display_available(),
    )


def _recommended_strategy_id(
    program: ProgramProfile,
    gaps: List[Any],
) -> Optional[str]:
    if not program.identity.exists:
        return None
    protocol_ids = {
        protocol
        for gap in gaps
        for protocol in gap.suggested_protocol_ids
    }
    if program.format == "elf32" or "linux.multiarch_i386" in protocol_ids:
        return "native_multiarch"
    if program.needs_wine:
        return "wine_host"
    if program.needs_native:
        return "native_host"
    return None


def build_compatibility_inspection(
    file_path: str,
    *,
    scanner_data: Optional[Dict[str, Any]] = None,
    wine_prefix: Optional[str] = None,
) -> CompatibilityInspection:
    """Full read-only inspection: program + host + gaps."""
    from alma_bridge.bridge.gap_analyzer import analyze_compatibility_gaps, build_wine_environment_profile

    hardware = profile_hardware()
    program = build_program_profile(
        file_path,
        host_arch=hardware.get("architecture"),
        scanner_data=scanner_data,
    )
    host = build_host_capability_profile(hardware=hardware)
    wine_env = build_wine_environment_profile(program, wine_prefix=wine_prefix)
    gaps = analyze_compatibility_gaps(program, host, wine_env=wine_env)
    blockers = [gap for gap in gaps if gap.severity == "blocker"]
    majors = [gap for gap in gaps if gap.severity == "major"]
    notes: List[str] = []
    if blockers:
        notes.append(
            f"{len(blockers)} blocker(s) must be bridged before the program can run."
        )
    elif wine_env and wine_env.runtimes_ready and program.needs_wine:
        notes.append(
            f"Wine prefix runtimes ready ({wine_env.wine_prefix}) — "
            "Bridge will still verify at launch."
        )
    elif not gaps:
        notes.append("No compatibility gaps detected — host appears ready.")
    if wine_env and wine_env.installed_launcher_path:
        notes.append(f"Installed launcher found: {wine_env.installed_launcher_path}")
    return CompatibilityInspection(
        program=program,
        host=host,
        wine_environment=wine_env,
        gaps=gaps,
        blocker_count=len(blockers),
        major_count=len(majors),
        ready_for_bridge=program.identity.exists and not blockers,
        recommended_strategy_id=_recommended_strategy_id(program, gaps),
        notes=notes,
    )
