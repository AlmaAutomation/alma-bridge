from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Strategy:
    id: str
    runtime: str
    mode: str  # host | container
    description: str
    priority: int
    binary_formats: tuple[str, ...]
    required_capabilities: tuple[str, ...] = ()
    base_env: Dict[str, str] | None = None


PE_SUFFIXES = {".exe", ".msi", ".dll", ".scr", ".cpl"}
SCRIPT_SUFFIXES = {".sh", ".py", ".pl", ".rb"}


def is_pe_path(file_path: str) -> bool:
    return Path(file_path).suffix.lower() in PE_SUFFIXES


STRATEGIES: List[Strategy] = [
    Strategy(
        id="native_host",
        runtime="native",
        mode="host",
        description="Run native ELF directly on the host.",
        priority=10,
        binary_formats=("elf", "script"),
        required_capabilities=(),
    ),
    Strategy(
        id="native_multiarch",
        runtime="native",
        mode="host",
        description="Run 32-bit ELF using multiarch libraries.",
        priority=20,
        binary_formats=("elf32",),
        required_capabilities=("multiarch",),
        base_env={"LD_LIBRARY_PATH": "/usr/lib/i386-linux-gnu:/lib/i386-linux-gnu"},
    ),
    Strategy(
        id="wine_host",
        runtime="wine",
        mode="host",
        description="Run PE binaries with system Wine.",
        priority=30,
        binary_formats=("pe",),
        required_capabilities=("wine",),
    ),
    Strategy(
        id="proton_host",
        runtime="proton",
        mode="host",
        description="Run PE binaries with latest Proton.",
        priority=25,
        binary_formats=("pe",),
        required_capabilities=("proton",),
    ),
    Strategy(
        id="qemu_user",
        runtime="qemu",
        mode="host",
        description="Run foreign-architecture ELF with qemu-user.",
        priority=40,
        binary_formats=("elf_foreign",),
        required_capabilities=("qemu_user",),
    ),
    Strategy(
        id="container_compat",
        runtime="container",
        mode="container",
        description="Run inside Alma sandbox container with broad compatibility tooling.",
        priority=50,
        binary_formats=("elf", "elf32", "pe", "script", "unknown"),
        required_capabilities=("docker",),
    ),
    Strategy(
        id="container_podman",
        runtime="container",
        mode="container",
        description="Run inside Podman sandbox when Docker is unavailable.",
        priority=55,
        binary_formats=("elf", "elf32", "pe", "script", "unknown"),
        required_capabilities=("podman",),
    ),
]


def _read_magic(path: Path) -> str:
    try:
        import subprocess

        output = subprocess.run(
            ["file", "-b", str(path)],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        ).stdout.lower()
        return output
    except (OSError, subprocess.SubprocessError):
        return ""


def classify_binary(file_path: str, host_arch: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()
    name = path.name.lower()

    # Extension wins over file(1) and executable-bit heuristics — PE exes are
    # often +x on Linux and were misclassified as "script" → native_host.
    if suffix in PE_SUFFIXES:
        return "pe"

    if not path.exists():
        if suffix == ".appimage" or "appimage" in name:
            return "elf"
        if suffix in SCRIPT_SUFFIXES:
            return "script"
        return "missing"

    description = _read_magic(path)
    if "pe32+" in description or "pe32" in description or "ms-dos" in description:
        return "pe"
    if "elf" in description:
        if "32-bit" in description:
            if host_arch == "x86_64":
                return "elf32"
            return "elf"
        if "64-bit" in description:
            if host_arch != "x86_64":
                return "elf_foreign"
            return "elf"
        return "elf"
    if suffix in SCRIPT_SUFFIXES or (
        os.access(path, os.X_OK) and suffix not in PE_SUFFIXES
    ):
        return "script"
    return "unknown"


def available_strategies(
    file_path: str,
    capabilities: Dict[str, bool],
    host_arch: str,
    runtime_hint: Optional[str] = None,
) -> List[Strategy]:
    binary_format = classify_binary(file_path, host_arch)
    if binary_format == "missing":
        return []

    candidates = [
        strategy
        for strategy in STRATEGIES
        if binary_format in strategy.binary_formats
        and all(capabilities.get(cap, False) for cap in strategy.required_capabilities)
    ]

    # PE must never run native — scanner/runtime hints can be wrong for Windows binaries.
    if binary_format == "pe":
        candidates = [
            s for s in candidates if s.runtime in {"wine", "proton", "container"}
        ]
        if runtime_hint in {None, "native", "multiarch", "qemu_user"}:
            runtime_hint = "wine"
    elif binary_format in {"elf", "elf32", "script"}:
        candidates = [s for s in candidates if s.runtime not in {"wine", "proton"}]

    if runtime_hint == "wine":
        candidates = [s for s in candidates if s.runtime in {"wine", "container"}]
    elif runtime_hint == "proton":
        candidates = [s for s in candidates if s.runtime in {"proton", "container"}]
    elif runtime_hint in {"native", "multiarch"}:
        candidates = [s for s in candidates if s.runtime == "native"]
    elif runtime_hint == "qemu_user":
        candidates = [s for s in candidates if s.runtime in {"qemu", "container"}]

    return sorted(candidates, key=lambda item: item.priority)
