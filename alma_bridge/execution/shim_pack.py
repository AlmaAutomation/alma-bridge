"""Alma Container Shim Pack — bundle shims + runtime for VM-like isolated execution."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from alma_bridge.compatibility.program_kind import classify_program_kind
from alma_bridge.compatibility.strategies import classify_binary
from alma_bridge.config import settings
from alma_bridge.execution.container_checks import sandbox_ready
from alma_bridge.execution.container_command import build_container_command
from alma_bridge.execution.container_spec import build_container_run_spec
from alma_bridge.execution.sandbox import run_in_container
from alma_bridge.hardware.profiler import profile_hardware
from alma_bridge.hardware.shims import (
    SHIM_CATALOG,
    recommended_shims_from_profile,
    shim_env,
    shims_for_indicators,
)


def sandbox_status(*, use_sudo: bool = False) -> Dict[str, Any]:
    ready, runtime = sandbox_ready(use_sudo=use_sudo)
    return {
        "ready": ready,
        "runtime": runtime,
        "image": settings.sandbox_image,
        "sandbox_enabled": settings.sandbox_enabled,
        "shim_count": len(SHIM_CATALOG),
    }


def _resolve_shims(
    hardware: Dict[str, Any],
    *,
    shim_ids: Optional[List[str]] = None,
    error_signature: Optional[str] = None,
) -> List[Dict[str, Any]]:
    if shim_ids:
        catalog = {item["id"]: item for item in SHIM_CATALOG}
        return [catalog[sid] for sid in shim_ids if sid in catalog]

    indicators = list(hardware.get("legacy_indicators", []))
    asod = hardware.get("asod", {})
    indicators.extend(asod.get("legacy_indicators", []))
    if error_signature:
        matched = shims_for_indicators(indicators, error_signature)
        if matched:
            return matched
    return recommended_shims_from_profile(hardware)


def _container_notes(binary_format: str, hardware: Dict[str, Any]) -> str:
    caps = hardware.get("capabilities", {})
    parts = [
        f"Binary format: {binary_format}.",
        "Runs inside Alma sandbox — modern glibc/userland without upgrading the host.",
    ]
    if binary_format == "pe":
        parts.append("PE wrapped with wine inside the container.")
    elif binary_format == "elf_foreign":
        parts.append("Foreign-arch ELF uses qemu-user-static in the container.")
    if not caps.get("docker") and not caps.get("podman"):
        parts.append("Install Docker or Podman and build the sandbox image.")
    return " ".join(parts)


def build_shim_pack(
    file_path: str,
    *,
    shim_ids: Optional[List[str]] = None,
    error_signature: Optional[str] = None,
    extra_env: Optional[Dict[str, str]] = None,
    sandbox_image: Optional[str] = None,
    use_sudo: bool = False,
) -> Dict[str, Any]:
    """Plan a container run with all applicable Alma shims applied."""
    target = Path(file_path).expanduser()
    if not target.exists():
        return {
            "ok": False,
            "error": f"file not found: {target}",
            "file_path": str(target),
        }

    hardware = profile_hardware()
    host_arch = hardware.get("architecture", "x86_64")
    binary_format = classify_binary(str(target), host_arch)
    program_kind = classify_program_kind(str(target), host_arch=host_arch)
    shims = _resolve_shims(
        hardware,
        shim_ids=shim_ids,
        error_signature=error_signature,
    )

    env = shim_env([s["id"] for s in shims])
    if extra_env:
        env.update(extra_env)

    command = build_container_command(
        str(target),
        host_arch=host_arch,
        binary_format=binary_format,
    )
    ready, runtime = sandbox_ready(use_sudo=use_sudo)
    spec = build_container_run_spec(
        file_path=str(target),
        command=command,
        env=env,
        image=sandbox_image,
        runtime=runtime,
        use_sudo=use_sudo,
    )

    return {
        "ok": True,
        "file_path": str(target.resolve()),
        "binary_format": binary_format,
        "program_kind": program_kind.get("program_kind"),
        "host_architecture": host_arch,
        "sandbox_ready": ready,
        "runtime": runtime,
        "image": sandbox_image or settings.sandbox_image,
        "shims": [{"id": s["id"], "category": s["category"], "description": s["description"]} for s in shims],
        "env": env,
        "command": command,
        "container_spec": {
            "mount": spec["mount"],
            "preview": spec["preview"],
            "argv": spec["argv"],
        },
        "notes": _container_notes(binary_format, hardware),
        "hardware_summary": {
            "ram_mb": hardware.get("ram_total_mb"),
            "gpu": hardware.get("gpu", {}).get("model"),
            "legacy_indicators": hardware.get("legacy_indicators", [])[:8],
        },
    }


def run_shim_pack(
    file_path: str,
    *,
    shim_ids: Optional[List[str]] = None,
    error_signature: Optional[str] = None,
    extra_env: Optional[Dict[str, str]] = None,
    sandbox_image: Optional[str] = None,
    use_sudo: bool = False,
    timeout_sec: Optional[int] = None,
    extra_args: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Execute a shim pack inside the Alma sandbox container."""
    pack = build_shim_pack(
        file_path,
        shim_ids=shim_ids,
        error_signature=error_signature,
        extra_env=extra_env,
        sandbox_image=sandbox_image,
        use_sudo=use_sudo,
    )
    if not pack.get("ok"):
        return pack

    if not pack.get("sandbox_ready"):
        pack["executed"] = False
        pack["error"] = (
            f"Container sandbox unavailable. Build: docker build -t {settings.sandbox_image} ."
        )
        return pack

    timeout = timeout_sec or settings.execution_timeout_sec
    exit_code, stdout, stderr = run_in_container(
        pack["command"],
        env=pack["env"],
        file_path=pack["file_path"],
        timeout_sec=timeout,
        use_sudo=use_sudo,
        extra_run_args=extra_args,
    )

    pack["executed"] = True
    pack["exit_code"] = exit_code
    pack["stdout"] = (stdout or "")[-4000:]
    pack["stderr"] = (stderr or "")[-4000:]
    pack["success"] = exit_code == 0
    return pack
