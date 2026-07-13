from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

from alma_bridge.compatibility.electron_wine import mingw_compiler
from alma_bridge.compliance.legacy32 import assess_32bit_support
from alma_bridge.execution.installer_verify import discover_installed_launcher
from alma_bridge.execution.preflight import (
    prefix_dotnet_installed,
    prefix_runtimes_ready,
    prefix_vcrun_installed,
    read_wine_windows_version,
)
from alma_bridge.hardware.prefixes import find_best_prefix
from alma_bridge.schemas.bridge_domain import (
    BridgeComponentKind,
    CompatibilityGap,
    GapCategory,
    HostCapabilityProfile,
    ProgramProfile,
    WineEnvironmentProfile,
)

_GAP_COUNTER = 0


def _next_gap_id(prefix: str) -> str:
    global _GAP_COUNTER  # noqa: PLW0603
    _GAP_COUNTER += 1
    return f"gap:{prefix}:{_GAP_COUNTER}"


def _gap(
    *,
    prefix: str,
    category: GapCategory,
    severity: str,
    description: str,
    evidence: List[str],
    component_kinds: List[BridgeComponentKind],
    confidence: float = 0.9,
    protocol_ids: List[str] | None = None,
) -> CompatibilityGap:
    return CompatibilityGap(
        id=_next_gap_id(prefix),
        category=category,
        severity=severity,  # type: ignore[arg-type]
        description=description,
        evidence=evidence,
        required_component_kinds=component_kinds,
        confidence=confidence,
        suggested_protocol_ids=protocol_ids or [],
    )


def build_wine_environment_profile(
    program: ProgramProfile,
    *,
    wine_prefix: Optional[str] = None,
) -> Optional[WineEnvironmentProfile]:
    """Inspect the Wine prefix Bridge would use for this program."""
    if not program.needs_wine:
        return None

    prefix = wine_prefix or find_best_prefix(program.identity.path)
    if not prefix:
        return WineEnvironmentProfile(
            electron_wrappers_needed=bool(program.is_electron or program.is_launcher),
            mingw_compiler_available=bool(mingw_compiler()),
        )

    prefix_path = Path(prefix).expanduser()
    launcher = None
    if program.is_installer:
        launcher = discover_installed_launcher(prefix, program.identity.path)

    return WineEnvironmentProfile(
        wine_prefix=prefix,
        prefix_exists=prefix_path.is_dir(),
        prefix_writable=os.access(prefix_path, os.W_OK) if prefix_path.is_dir() else False,
        windows_version=read_wine_windows_version(prefix),
        vcrun_ready=prefix_vcrun_installed(prefix),
        dotnet_ready=prefix_dotnet_installed(prefix),
        runtimes_ready=prefix_runtimes_ready(prefix),
        mingw_compiler_available=bool(mingw_compiler()),
        electron_wrappers_needed=bool(program.is_electron or program.is_launcher),
        installed_launcher_path=launcher,
    )


def _wine_environment_gaps(
    program: ProgramProfile,
    wine_env: WineEnvironmentProfile,
) -> List[CompatibilityGap]:
    gaps: List[CompatibilityGap] = []

    if not wine_env.prefix_exists:
        gaps.append(
            _gap(
                prefix="wine_prefix_missing",
                category=GapCategory.MISSING_RUNTIME,
                severity="major",
                description="No Wine prefix exists yet — Bridge will create one and bootstrap runtimes.",
                evidence=["wine_prefix=null"],
                component_kinds=[
                    BridgeComponentKind.ISOLATED_RUNTIME,
                    BridgeComponentKind.DEPENDENCY_LAYER,
                ],
                protocol_ids=["wine.create_prefix", "wine.winetricks_bootstrap"],
            )
        )
        return gaps

    if not wine_env.prefix_writable:
        gaps.append(
            _gap(
                prefix="wine_prefix_readonly",
                category=GapCategory.PERMISSION_MISMATCH,
                severity="blocker",
                description="Wine prefix is not writable.",
                evidence=[f"wine_prefix={wine_env.wine_prefix}"],
                component_kinds=[BridgeComponentKind.FILESYSTEM_ADAPTER],
                protocol_ids=["wine.fix_prefix_permissions"],
            )
        )

    if program.is_installer or program.is_electron:
        if not wine_env.vcrun_ready:
            gaps.append(
                _gap(
                    prefix="wine_vcrun",
                    category=GapCategory.MISSING_RUNTIME,
                    severity="blocker",
                    description="Visual C++ runtimes are not installed in the Wine prefix.",
                    evidence=[f"wine_prefix={wine_env.wine_prefix}", "vcrun_ready=false"],
                    component_kinds=[BridgeComponentKind.DEPENDENCY_LAYER],
                    protocol_ids=["wine.winetricks_vcrun"],
                )
            )
        if not wine_env.dotnet_ready:
            gaps.append(
                _gap(
                    prefix="wine_dotnet",
                    category=GapCategory.MISSING_RUNTIME,
                    severity="blocker",
                    description=".NET Framework 4.x is not installed in the Wine prefix (rundll32 errors at install/launch).",
                    evidence=[f"wine_prefix={wine_env.wine_prefix}", "dotnet_ready=false"],
                    component_kinds=[BridgeComponentKind.DEPENDENCY_LAYER],
                    protocol_ids=["wine.winetricks_dotnet48"],
                )
            )

    if wine_env.windows_version in {None, "win98", "winme", "winxp", "win2003", "winvista", "win7"}:
        severity = "blocker" if (program.is_electron or program.is_installer) else "major"
        gaps.append(
            _gap(
                prefix="wine_windows_version",
                category=GapCategory.ENVIRONMENT_CONFIGURATION_MISMATCH,
                severity=severity,
                description=(
                    "Wine prefix reports Windows XP (unset Version) — Electron/Chromium apps "
                    "crash with int3 until win10 is set and wineserver restarted."
                ),
                evidence=[f"windows_version={wine_env.windows_version or 'unset'}"],
                component_kinds=[BridgeComponentKind.CONFIGURATION_OVERLAY],
                protocol_ids=["wine.set_win10"],
            )
        )

    if wine_env.electron_wrappers_needed and not wine_env.mingw_compiler_available:
        gaps.append(
            _gap(
                prefix="mingw_missing",
                category=GapCategory.MISSING_DEPENDENCY,
                severity="major",
                description="Electron-on-Wine needs gcc-mingw-w64-x86-64 to build sidecar/elevate wrappers.",
                evidence=["mingw_compiler_available=false"],
                component_kinds=[BridgeComponentKind.WRAPPER],
                protocol_ids=["host.apt_mingw_w64"],
            )
        )

    ascension = "ascension" in program.identity.path.lower()
    if ascension and wine_env.prefix_exists and wine_env.runtimes_ready:
        gaps.append(
            _gap(
                prefix="ascension_runtime_verify",
                category=GapCategory.UNKNOWN_RUNTIME_FAILURE,
                severity="minor",
                description=(
                    "Wine prefix runtimes appear installed, but Ascension may still fail at launch "
                    "(int3, rundll32) — Bridge will verify and repair automatically."
                ),
                evidence=[
                    f"wine_prefix={wine_env.wine_prefix}",
                    "runtimes_ready=true",
                    "historical_ascension_failures",
                ],
                component_kinds=[BridgeComponentKind.WRAPPER, BridgeComponentKind.DEPENDENCY_LAYER],
                protocol_ids=["wine.repair_runtimes", "electron.install_wrappers"],
                confidence=0.75,
            )
        )

    return gaps


def analyze_compatibility_gaps(
    program: ProgramProfile,
    host: HostCapabilityProfile,
    *,
    wine_env: Optional[WineEnvironmentProfile] = None,
) -> List[CompatibilityGap]:
    """Deterministic gap analysis between program requirements and host capabilities."""
    global _GAP_COUNTER  # noqa: PLW0603
    _GAP_COUNTER = 0

    gaps: List[CompatibilityGap] = []

    if not program.identity.exists:
        gaps.append(
            _gap(
                prefix="missing_program",
                category=GapCategory.PROGRAM_NOT_FOUND,
                severity="blocker",
                description="Program file does not exist on the host.",
                evidence=[f"path={program.identity.path}"],
                component_kinds=[],
                confidence=1.0,
            )
        )
        return gaps

    caps = host.capabilities

    if program.needs_gui and not host.display_available:
        gaps.append(
            _gap(
                prefix="gui_unavailable",
                category=GapCategory.GUI_UNAVAILABLE,
                severity="blocker",
                description="Program needs a GUI session but DISPLAY/WAYLAND_DISPLAY is unset.",
                evidence=["No active desktop session detected."],
                component_kinds=[BridgeComponentKind.ENVIRONMENT_ADAPTER],
                protocol_ids=["host.display_session"],
            )
        )

    if program.format == "elf32" and host.architecture == "x86_64":
        assessment = assess_32bit_support()
        for gap_code in assessment.get("gaps") or []:
            if gap_code == "missing_elf32_loader":
                gaps.append(
                    _gap(
                        prefix="elf32_loader",
                        category=GapCategory.MISSING_DEPENDENCY,
                        severity="blocker",
                        description="32-bit ELF loader (ld-linux.so.2) is not installed.",
                        evidence=[f"assessment={gap_code}"],
                        component_kinds=[
                            BridgeComponentKind.DEPENDENCY_LAYER,
                            BridgeComponentKind.ARCHITECTURE_TRANSLATION,
                        ],
                        protocol_ids=["linux.multiarch_i386"],
                    )
                )
            elif gap_code == "missing_core_i386_libs":
                gaps.append(
                    _gap(
                        prefix="elf32_libs",
                        category=GapCategory.MISSING_DEPENDENCY,
                        severity="blocker",
                        description="Core i386 runtime libraries are missing.",
                        evidence=[f"assessment={gap_code}"],
                        component_kinds=[BridgeComponentKind.DEPENDENCY_LAYER],
                        protocol_ids=["linux.multiarch_i386"],
                    )
                )
            elif gap_code == "multiarch_disabled":
                gaps.append(
                    _gap(
                        prefix="elf32_multiarch",
                        category=GapCategory.ARCHITECTURE_MISMATCH,
                        severity="blocker",
                        description="64-bit host cannot run 32-bit ELF until multiarch (i386) is enabled.",
                        evidence=[f"assessment={gap_code}"],
                        component_kinds=[
                            BridgeComponentKind.DEPENDENCY_LAYER,
                            BridgeComponentKind.ENVIRONMENT_ADAPTER,
                        ],
                        protocol_ids=["linux.multiarch_i386"],
                    )
                )
            elif gap_code == "missing_x86_translation":
                gaps.append(
                    _gap(
                        prefix="elf32_translation",
                        category=GapCategory.ARCHITECTURE_MISMATCH,
                        severity="blocker",
                        description="Non-x86 host needs qemu-user or box86 to run x86 32-bit binaries.",
                        evidence=[f"assessment={gap_code}"],
                        component_kinds=[BridgeComponentKind.ARCHITECTURE_TRANSLATION],
                        protocol_ids=["linux.qemu_user_i386"],
                    )
                )

        if not caps.get("multiarch") and not assessment.get("ready"):
            if not any(g.id.startswith("gap:elf32") for g in gaps):
                gaps.append(
                    _gap(
                        prefix="elf32_multiarch",
                        category=GapCategory.ARCHITECTURE_MISMATCH,
                        severity="blocker",
                        description="32-bit ELF on 64-bit x86 host requires multiarch support.",
                        evidence=["capabilities.multiarch=false"],
                        component_kinds=[BridgeComponentKind.DEPENDENCY_LAYER],
                        protocol_ids=["linux.multiarch_i386"],
                    )
                )

    if program.format == "elf_foreign":
        gaps.append(
            _gap(
                prefix="foreign_elf",
                category=GapCategory.ARCHITECTURE_MISMATCH,
                severity="blocker",
                description="Binary architecture does not match the host CPU.",
                evidence=[
                    f"program.architecture={program.architecture}",
                    f"host.architecture={host.architecture}",
                ],
                component_kinds=[
                    BridgeComponentKind.ARCHITECTURE_TRANSLATION,
                    BridgeComponentKind.CONTAINER,
                ],
                protocol_ids=["linux.qemu_user", "bridge.container_compat"],
            )
        )

    if program.needs_wine:
        if not caps.get("wine") and not caps.get("proton"):
            gaps.append(
                _gap(
                    prefix="wine_missing",
                    category=GapCategory.MISSING_RUNTIME,
                    severity="blocker",
                    description="Windows PE program requires Wine or Proton, neither is available.",
                    evidence=["capabilities.wine=false", "capabilities.proton=false"],
                    component_kinds=[BridgeComponentKind.ISOLATED_RUNTIME],
                    protocol_ids=["wine.install"],
                )
            )
        elif program.is_installer or program.is_electron:
            if not caps.get("winetricks"):
                gaps.append(
                    _gap(
                        prefix="winetricks_missing",
                        category=GapCategory.MISSING_RUNTIME,
                        severity="major",
                        description="winetricks is recommended to bootstrap VC++/ .NET in Wine prefixes.",
                        evidence=["capabilities.winetricks=false"],
                        component_kinds=[BridgeComponentKind.DEPENDENCY_LAYER],
                        protocol_ids=["wine.winetricks_bootstrap"],
                    )
                )

        if wine_env is None:
            wine_env = build_wine_environment_profile(program)
        if wine_env is not None:
            gaps.extend(_wine_environment_gaps(program, wine_env))

    for library in program.required_libraries:
        if library.resolved is False:
            gaps.append(
                _gap(
                    prefix=f"lib_{library.name.replace('.', '_')}",
                    category=GapCategory.MISSING_DEPENDENCY,
                    severity="blocker",
                    description=f"Required shared library is missing: {library.name}",
                    evidence=[f"ldd: {library.name} => not found"],
                    component_kinds=[BridgeComponentKind.DEPENDENCY_LAYER],
                    protocol_ids=["linux.install_missing_library"],
                )
            )

    if program.needs_native and not os.access(program.identity.path, os.X_OK):
        gaps.append(
            _gap(
                prefix="not_executable",
                category=GapCategory.PERMISSION_MISMATCH,
                severity="major",
                description="Binary is not marked executable.",
                evidence=[f"path={program.identity.path}"],
                component_kinds=[BridgeComponentKind.CONFIGURATION_OVERLAY],
                protocol_ids=["host.chmod_executable"],
            )
        )

    if "no_multiarch_libs" in host.legacy_indicators and program.format == "elf32":
        if not any(g.suggested_protocol_ids == ["linux.multiarch_i386"] for g in gaps):
            gaps.append(
                _gap(
                    prefix="legacy_no_multiarch",
                    category=GapCategory.ARCHITECTURE_MISMATCH,
                    severity="blocker",
                    description="Host legacy indicator: multiarch libraries not present.",
                    evidence=["legacy_indicators.no_multiarch_libs"],
                    component_kinds=[BridgeComponentKind.DEPENDENCY_LAYER],
                    protocol_ids=["linux.multiarch_i386"],
                )
            )

    return gaps
