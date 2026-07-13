from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional


def _run_cmd(args: List[str], timeout: int = 8) -> str:
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if proc.returncode == 0:
            return proc.stdout
    except (OSError, subprocess.SubprocessError):
        pass
    return ""


def _normalize_spaces(text: str) -> str:
    return " ".join(text.split())


def detect_distro_family() -> str:
    try:
        with open("/etc/os-release", encoding="utf-8") as handle:
            content = handle.read().lower()
        if "ubuntu" in content or "debian" in content:
            return "debian"
        if "fedora" in content:
            return "fedora"
        if "arch" in content:
            return "arch"
    except OSError:
        pass
    return "unknown"


def get_cpu_model() -> str:
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as handle:
            for line in handle:
                if line.lower().startswith("model name"):
                    return _normalize_spaces(line.split(":", 1)[1].strip())
    except OSError:
        pass

    output = _run_cmd(["lscpu"])
    for line in output.splitlines():
        if "Model name:" in line:
            return _normalize_spaces(line.split(":", 1)[1].strip())
    return "Unknown CPU"


def detect_cpu_brand() -> str:
    model = get_cpu_model().lower()
    if "intel" in model:
        return "intel"
    if "amd" in model:
        return "amd"
    if "arm" in model or "aarch64" in model:
        return "arm"
    return "unknown"


def _clean_gpu_name(name: str) -> str:
    name = name.replace("NVIDIA Corporation", "").replace("Corporation", "")
    name = name.replace("VGA compatible controller:", "").replace("3D controller:", "")
    name = re.sub(r"\s*\(rev .*?\)", "", name)
    name = re.sub(r"\s*\[.*?\]", "", name)
    return _normalize_spaces(name.strip(" -"))


def get_gpu_model() -> str:
    output = _run_cmd(["lspci"])
    if output:
        gpu_lines = []
        for line in output.splitlines():
            low = line.lower()
            if any(tag in low for tag in ("vga compatible controller", "3d controller", "display controller")):
                gpu_lines.append(line)
        if gpu_lines:
            first = gpu_lines[0]
            if "NVIDIA" in first:
                return _clean_gpu_name(first)
            cleaned = first.split(":", 2)[-1].strip()
            cleaned = re.sub(r"\s*\(rev .*?\)", "", cleaned)
            cleaned = re.sub(r"\s*\[.*?\]", "", cleaned)
            return _normalize_spaces(cleaned)

    if shutil.which("nvidia-smi"):
        smi = _run_cmd(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
        first = smi.splitlines()[0].strip() if smi else ""
        if first:
            return first
    return "Unknown GPU"


def detect_gpu_vendor() -> str:
    model = get_gpu_model().lower()
    if any(token in model for token in ("nvidia", "geforce", "quadro", "rtx", "gtx")):
        return "nvidia"
    if "amd" in model or "radeon" in model:
        return "amd"
    if any(token in model for token in ("intel", "uhd graphics", "iris", "tigerlake")):
        return "intel"
    return "unknown"


def detect_storage_type() -> str:
    output = _run_cmd(["lsblk", "-dn", "-o", "NAME"])
    if not output:
        return "unknown"

    any_ssd = any_hdd = False
    for name in output.split():
        path = f"/sys/block/{name}/queue/rotational"
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as handle:
                rotational = handle.read().strip()
            if rotational == "0":
                any_ssd = True
            elif rotational == "1":
                any_hdd = True
        except OSError:
            continue

    if any_ssd and not any_hdd:
        return "ssd"
    if any_hdd and not any_ssd:
        return "hdd"
    if any_ssd and any_hdd:
        return "mixed"
    return "unknown"


def get_ram_gb() -> Optional[float]:
    try:
        import psutil

        return round(psutil.virtual_memory().total / (1024**3), 2)
    except Exception:
        pass

    try:
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    return round(kb / 1024 / 1024, 2)
    except (OSError, ValueError):
        return None
    return None


def get_swappiness() -> Optional[int]:
    output = _run_cmd(["sysctl", "-n", "vm.swappiness"])
    try:
        return int(output.strip())
    except (TypeError, ValueError):
        return None


def asod_indicators(summary: Dict[str, Any]) -> List[str]:
    indicators: List[str] = []
    ram_gb = summary.get("ram_gb")
    if ram_gb is not None and ram_gb < 4:
        indicators.append("low_memory")
    if summary.get("gpu") == "unknown":
        indicators.append("unknown_gpu")
    if summary.get("storage") == "hdd":
        indicators.append("rotational_storage")
    swappiness = summary.get("swappiness")
    if swappiness is not None and swappiness > 80:
        indicators.append("high_swappiness")
    if summary.get("distro") == "unknown":
        indicators.append("unknown_distro")
    return indicators


def get_asod_summary() -> Dict[str, Any]:
    """ASOD-style hardware summary for Alma Bridge shim selection."""
    return {
        "distro": detect_distro_family(),
        "cpu": detect_cpu_brand(),
        "cpu_model": get_cpu_model(),
        "gpu": detect_gpu_vendor(),
        "gpu_model": get_gpu_model(),
        "storage": detect_storage_type(),
        "ram_gb": get_ram_gb(),
        "swappiness": get_swappiness(),
        "psutil": _has_psutil(),
        "nmcli": shutil.which("nmcli") is not None,
        "legacy_indicators": [],
    }


def _has_psutil() -> bool:
    try:
        import psutil  # noqa: F401

        return True
    except Exception:
        return False


def enrich_summary(summary: Dict[str, Any]) -> Dict[str, Any]:
    summary = dict(summary)
    summary["legacy_indicators"] = asod_indicators(summary)
    return summary
