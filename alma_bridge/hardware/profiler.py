from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from alma_bridge.hardware.asod import enrich_summary, get_asod_summary


def _normalize_arch(value: Optional[str]) -> str:
    arch = (value or "").lower()
    if any(x in arch for x in ("x86_64", "amd64")):
        return "x86_64"
    if arch in ("x86", "i386", "i686"):
        return "x86"
    if any(x in arch for x in ("aarch64", "arm64")):
        return "arm64"
    if "arm" in arch:
        return "arm"
    return "unknown"


def _os_bitness() -> str:
    bits = platform.architecture()[0]
    if bits in ("32bit", "64bit"):
        return "64-bit" if bits == "64bit" else "32-bit"
    machine = platform.machine().lower()
    if any(x in machine for x in ("x86_64", "amd64", "aarch64", "arm64")):
        return "64-bit"
    if any(x in machine for x in ("i386", "i686", "x86", "armv7")):
        return "32-bit"
    return "unknown"


def _probe_multiarch() -> bool:
    if _os_bitness() != "64-bit" or _normalize_arch(platform.machine()) != "x86_64":
        return False
    markers = (
        "/lib/ld-linux.so.2",
        "/lib32/ld-linux.so.2",
        "/usr/lib/i386-linux-gnu/ld-linux.so.2",
    )
    return any(os.path.exists(path) for path in markers)


def _read_mem_total_mb() -> Optional[int]:
    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        return None
    return None


def _detect_gpu() -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "vendor": "unknown",
        "renderer": "unknown",
        "driver": "unknown",
        "vulkan": shutil.which("vulkaninfo") is not None,
        "opengl": shutil.which("glxinfo") is not None,
    }

    if shutil.which("lspci"):
        try:
            output = subprocess.run(
                ["lspci", "-nn"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            ).stdout.lower()
            if "nvidia" in output:
                info["vendor"] = "nvidia"
            elif "amd" in output or "ati" in output:
                info["vendor"] = "amd"
            elif "intel" in output:
                info["vendor"] = "intel"
        except (OSError, subprocess.SubprocessError):
            pass

    for driver in ("nvidia", "amdgpu", "i915", "nouveau", "radeon"):
        if (Path("/sys/module") / driver).exists():
            info["driver"] = driver
            break

    return info


def _find_proton() -> Optional[str]:
    from alma_bridge.hardware.proton import find_best_proton

    return find_best_proton()


def profile_hardware() -> Dict[str, Any]:
    arch = _normalize_arch(platform.machine())
    asod = enrich_summary(get_asod_summary())
    gpu = _detect_gpu()
    gpu["vendor"] = asod.get("gpu") or gpu["vendor"]
    gpu["renderer"] = asod.get("gpu_model") or gpu["renderer"]

    ram_mb = _read_mem_total_mb()
    if asod.get("ram_gb") is not None:
        ram_mb = int(float(asod["ram_gb"]) * 1024)

    legacy_indicators = list(
        dict.fromkeys(
            _legacy_hardware_indicators(arch, gpu=gpu, ram_mb=ram_mb)
            + asod.get("legacy_indicators", [])
        )
    )

    return {
        "os": platform.system(),
        "os_version": platform.version(),
        "distribution": _read_distribution() or asod.get("distro"),
        "architecture": arch,
        "os_bitness": _os_bitness(),
        "cpu": asod.get("cpu_model") or platform.processor() or "unknown",
        "cpu_brand": asod.get("cpu"),
        "cpu_cores": os.cpu_count() or 1,
        "ram_total_mb": ram_mb,
        "ram_gb": asod.get("ram_gb"),
        "storage_type": asod.get("storage"),
        "swappiness": asod.get("swappiness"),
        "gpu": gpu,
        "asod": asod,
        "capabilities": {
            "wine": shutil.which("wine") is not None,
            "proton": _find_proton() is not None,
            "qemu_user": any(
                shutil.which(binary)
                for binary in ("qemu-x86_64", "qemu-i386", "qemu-aarch64", "qemu-arm")
            ),
            "docker": shutil.which("docker") is not None,
            "podman": shutil.which("podman") is not None,
            "multiarch": _probe_multiarch(),
            "winetricks": shutil.which("winetricks") is not None,
            "firejail": shutil.which("firejail") is not None,
        },
        "paths": {
            "proton": _find_proton(),
            "wine": shutil.which("wine"),
            "docker": shutil.which("docker"),
            "podman": shutil.which("podman"),
        },
        "legacy_indicators": legacy_indicators,
    }


def _read_distribution() -> Optional[str]:
    try:
        import distro

        return distro.name(pretty=True)
    except Exception:
        return None


def _legacy_hardware_indicators(
    arch: str,
    *,
    gpu: Optional[Dict[str, Any]] = None,
    ram_mb: Optional[int] = None,
) -> List[str]:
    indicators: List[str] = []
    ram = ram_mb if ram_mb is not None else _read_mem_total_mb()
    if ram is not None and ram < 4096:
        indicators.append("low_memory")
    if arch == "x86":
        indicators.append("32bit_cpu")
    if _os_bitness() == "32-bit":
        indicators.append("32bit_os")
    if not _probe_multiarch() and arch == "x86_64":
        indicators.append("no_multiarch_libs")
    gpu_info = gpu or _detect_gpu()
    if gpu_info["vendor"] == "unknown":
        indicators.append("unknown_gpu")
    if gpu_info["driver"] in ("unknown", "nouveau", "radeon"):
        indicators.append("legacy_or_generic_gpu_driver")
    return indicators
