"""Build runtime-aware commands for execution inside the Alma sandbox container."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from alma_bridge.compatibility.strategies import classify_binary


def container_workspace_path(file_path: str) -> str:
    return f"/workspace/{Path(file_path).name}"


def build_container_command(
    file_path: str,
    *,
    host_arch: str = "x86_64",
    binary_format: Optional[str] = None,
) -> List[str]:
    """Wrap ``file_path`` with wine/qemu/bash inside the sandbox image."""
    fmt = binary_format or classify_binary(file_path, host_arch)
    target = container_workspace_path(file_path)

    if fmt == "pe":
        return ["wine", target]
    if fmt == "elf_foreign":
        return ["qemu-x86_64-static", target]
    if fmt == "script":
        return ["bash", target]
    if fmt == "elf32":
        return [target]
    return [target]
