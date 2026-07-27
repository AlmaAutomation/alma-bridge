from __future__ import annotations

import re
import struct
from pathlib import Path
from typing import Any, Dict, List, Optional

from alma_bridge.compatibility.framework_detection import detect_gui_framework
from alma_bridge.compatibility.strategies import classify_binary
from alma_bridge.learning.installer import (
    default_installer_args,
    electron_software_gl_args,
    is_electron_app,
    is_windows_installer,
)

# PE optional-header subsystem values (winnt.h)
IMAGE_SUBSYSTEM_WINDOWS_GUI = 2
IMAGE_SUBSYSTEM_WINDOWS_CUI = 3

INSTALLER_NAME_RE = re.compile(
    r"(setup|installer|install|bootstrap|update|mediacreationtool)",
    re.IGNORECASE,
)
LAUNCHER_NAME_RE = re.compile(
    r"(launcher|client|game|play|run|start)",
    re.IGNORECASE,
)


def read_pe_subsystem(path: Path) -> Optional[int]:
    """Return PE optional-header subsystem (2=GUI, 3=CUI) or None."""
    return _read_pe_subsystem(path)


def _read_pe_subsystem(path: Path) -> Optional[int]:
    """Return PE optional-header subsystem (2=GUI, 3=CUI) or None."""
    try:
        with path.open("rb") as handle:
            header = handle.read(0x1000)
        if len(header) < 64 or header[:2] != b"MZ":
            return None
        pe_offset = struct.unpack_from("<I", header, 0x3C)[0]
        if pe_offset + 24 > len(header) or header[pe_offset : pe_offset + 4] != b"PE\0\0":
            return None
        optional_offset = pe_offset + 24
        magic = struct.unpack_from("<H", header, optional_offset)[0]
        if magic not in {0x10B, 0x20B}:
            return None
        subsystem_offset = optional_offset + 68
        if subsystem_offset + 2 > len(header):
            return None
        return struct.unpack_from("<H", header, subsystem_offset)[0]
    except (OSError, struct.error):
        return None


def _installer_markers_in_file(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:65536].lower()
    except OSError:
        return False
    markers = (
        b"nullsoft",
        b"inno setup",
        b"installshield",
        b"nsis error",
        b"setup.exe",
    )
    return any(marker in sample for marker in markers)


def detect_installer(path: Path) -> bool:
    if path.suffix.lower() == ".msi":
        return True
    if path.suffix.lower() != ".exe":
        return False
    if is_windows_installer(str(path)):
        return True
    name = path.name.lower()
    if INSTALLER_NAME_RE.search(name):
        return True
    subsystem = _read_pe_subsystem(path)
    if subsystem == IMAGE_SUBSYSTEM_WINDOWS_GUI and _installer_markers_in_file(path):
        return True
    if subsystem == IMAGE_SUBSYSTEM_WINDOWS_GUI and re.search(
        r"[-_.](setup|installer|update)[-_.]", name
    ):
        return True
    return False


def classify_program_kind(file_path: str, *, host_arch: str = "x86_64") -> Dict[str, Any]:
    """Classify any program path for Bridge planning and preflight.

    Precedence (highest first):
      installer → Electron launcher → PE GUI → PE console → other PE/native kinds
    """
    path = Path(file_path).expanduser()
    exists = path.is_file()
    binary_format = classify_binary(str(path), host_arch) if exists else "missing"
    suffix = path.suffix.lower()
    name = path.name.lower()
    pe_subsystem = _read_pe_subsystem(path) if exists and suffix == ".exe" else None

    installer = detect_installer(path) if exists else False
    electron = is_electron_app(str(path)) if exists and suffix == ".exe" else False
    is_launcher = bool(electron and not installer)
    is_wine_gui = (
        exists
        and suffix == ".exe"
        and binary_format == "pe"
        and not installer
        and not electron
        and pe_subsystem == IMAGE_SUBSYSTEM_WINDOWS_GUI
    )

    if not exists:
        program_kind = "missing"
    elif suffix == ".appimage" or "appimage" in name:
        program_kind = "appimage"
    elif binary_format in {"elf", "elf32", "elf_foreign"}:
        program_kind = "native_elf"
    elif binary_format == "script":
        program_kind = "native_script"
    elif installer:
        program_kind = "pe_installer"
    elif is_launcher:
        program_kind = "pe_electron_launcher"
    elif is_wine_gui:
        program_kind = "pe_windows_gui"
    elif binary_format == "pe":
        program_kind = "pe_windows"
    else:
        program_kind = "unknown"

    needs_wine = program_kind in {
        "pe_installer",
        "pe_electron_launcher",
        "pe_windows_gui",
        "pe_windows",
    }
    needs_gui = program_kind in {
        "pe_installer",
        "pe_electron_launcher",
        "pe_windows_gui",
    }
    needs_native = program_kind in {"native_elf", "native_script", "appimage"}

    if needs_wine:
        recommended_runtime = "wine"
        recommended_max_attempts = 18 if installer else 10
        if installer:
            recommended_args: List[str] = default_installer_args()
            recommended_remediation_id: Optional[str] = None
        elif program_kind == "pe_windows_gui":
            recommended_args = []
            recommended_remediation_id = None
        else:
            recommended_args = electron_software_gl_args()
            recommended_remediation_id = "electron_disable_gpu"
    elif needs_native:
        recommended_runtime = "native"
        recommended_max_attempts = 8
        recommended_args = []
        recommended_remediation_id = None
    else:
        recommended_runtime = "native"
        recommended_max_attempts = 8
        recommended_args = []
        recommended_remediation_id = None

    profile = program_kind
    if program_kind == "pe_electron_launcher":
        profile = "electron_launcher"
    elif program_kind == "pe_windows_gui" and LAUNCHER_NAME_RE.search(name):
        profile = "windows_launcher"
    elif program_kind == "pe_windows" and LAUNCHER_NAME_RE.search(name):
        profile = "windows_launcher"

    framework_detection = None
    if exists and suffix == ".exe" and program_kind in {
        "pe_windows_gui",
        "pe_electron_launcher",
    }:
        framework_detection = detect_gui_framework(path)

    return {
        "file_path": str(path),
        "exists": exists,
        "binary_format": binary_format,
        "program_kind": program_kind,
        "profile": profile,
        "pe_subsystem": pe_subsystem,
        "is_installer": installer,
        "is_electron": electron,
        "is_launcher": is_launcher,
        "is_wine_gui": is_wine_gui,
        "needs_wine": needs_wine,
        "needs_gui": needs_gui,
        "needs_native": needs_native,
        "recommended_runtime": recommended_runtime,
        "recommended_max_attempts": recommended_max_attempts,
        "recommended_args": recommended_args,
        "recommended_remediation_id": recommended_remediation_id,
        "framework": (
            framework_detection.framework if framework_detection else "unknown"
        ),
        "framework_confidence": (
            framework_detection.confidence if framework_detection else 0.0
        ),
        "framework_version": (
            framework_detection.version if framework_detection else None
        ),
        "framework_linkage": (
            framework_detection.linkage if framework_detection else "unknown"
        ),
        "framework_evidence": (
            list(framework_detection.evidence) if framework_detection else []
        ),
    }
