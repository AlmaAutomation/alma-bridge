"""Full host assessment for legacy modernization (beyond compliance scanning)."""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from alma_bridge.compliance.pm import detect_package_manager
from alma_bridge.compliance.legacy32 import assess_32bit_support
from alma_bridge.compliance.modernization.browser import assess_browsers, recommend_browser
from alma_bridge.hardware.profiler import profile_hardware


def _glibc_version() -> Optional[str]:
    try:
        proc = subprocess.run(["ldd", "--version"], capture_output=True, text=True, timeout=5)
        line = (proc.stdout or proc.stderr or "").splitlines()[0]
        match = re.search(r"(\d+\.\d+)", line)
        return match.group(1) if match else line.strip()[:40]
    except (OSError, subprocess.SubprocessError):
        return None


def _disk_free_gb(path: str = "/") -> Optional[float]:
    try:
        stat = os.statvfs(path)
        return round((stat.f_bavail * stat.f_frsize) / (1024 ** 3), 2)
    except OSError:
        return None


def _swappiness() -> Optional[int]:
    try:
        with open("/proc/sys/vm/swappiness", encoding="utf-8") as handle:
            return int(handle.read().strip())
    except (OSError, ValueError):
        return None


def _zram_present() -> bool:
    return os.path.exists("/sys/block/zram0") or bool(shutil.which("zramctl"))


def _ca_store_freshness() -> Dict[str, Any]:
    paths = [
        "/etc/ssl/certs/ca-certificates.crt",
        "/etc/pki/tls/certs/ca-bundle.crt",
        "/etc/ssl/ca-bundle.pem",
    ]
    found = next((p for p in paths if os.path.exists(p)), None)
    age_days: Optional[int] = None
    if found:
        try:
            import time

            mtime = os.path.getmtime(found)
            age_days = int((time.time() - mtime) / 86400)
        except OSError:
            pass
    return {"bundle_path": found, "approx_age_days": age_days}


def assess_host(*, os_release: Optional[str] = None) -> Dict[str, Any]:
    """Assess whether this host can run modern browsers and reach the modern web."""
    hw = profile_hardware()
    legacy32 = assess_32bit_support()
    browsers = assess_browsers()
    ram_mb = hw.get("ram_total_mb")
    browser_rec = recommend_browser(ram_mb=ram_mb, os_release=os_release)
    pm = detect_package_manager(os_release)

    gaps: List[str] = []
    if not legacy32.get("ready"):
        gaps.extend(legacy32.get("gaps", []))
    if not browsers.get("has_modern_browser"):
        gaps.append("no_modern_browser")
    if ram_mb is not None and ram_mb < 2048:
        gaps.append("low_memory")
    if hw.get("capabilities", {}).get("multiarch") is False and hw.get("architecture") == "x86_64":
        if "multiarch_disabled" not in gaps:
            gaps.append("multiarch_disabled")
    swappiness = _swappiness()
    if ram_mb is not None and ram_mb < 2048 and swappiness is not None and swappiness > 60:
        gaps.append("swappiness_high")
    if not _zram_present() and ram_mb is not None and ram_mb < 2048:
        gaps.append("no_zram")

    potato_score = _potato_score(ram_mb, hw.get("cpu_cores", 1), hw.get("storage_type"))

    if not gaps:
        verdict = "ready"
    elif len(gaps) <= 2 and browsers.get("has_modern_browser"):
        verdict = "mostly_ready"
    else:
        verdict = "needs_modernization"

    return {
        "verdict": verdict,
        "potato_score": potato_score,
        "package_manager": pm,
        "hardware": {
            "architecture": hw.get("architecture"),
            "os_bitness": hw.get("os_bitness"),
            "distribution": hw.get("distribution"),
            "cpu": hw.get("cpu"),
            "cpu_cores": hw.get("cpu_cores"),
            "ram_total_mb": ram_mb,
            "storage_type": hw.get("storage_type"),
            "gpu": hw.get("gpu"),
            "legacy_indicators": hw.get("legacy_indicators", []),
        },
        "glibc_version": _glibc_version(),
        "disk_free_gb": _disk_free_gb(),
        "swappiness": swappiness,
        "zram_available": _zram_present(),
        "ca_store": _ca_store_freshness(),
        "legacy32": legacy32,
        "browsers": browsers,
        "browser_recommendation": browser_rec,
        "gaps": gaps,
        "summary": _build_summary(verdict, gaps, browsers, ram_mb),
    }


def _potato_score(ram_mb: Optional[int], cores: int, storage: Optional[str]) -> int:
    """0 = potato, 100 = comfortable modern desktop."""
    score = 70
    if ram_mb is not None:
        if ram_mb < 512:
            score -= 35
        elif ram_mb < 1024:
            score -= 25
        elif ram_mb < 2048:
            score -= 15
        elif ram_mb >= 8192:
            score += 10
    if cores <= 1:
        score -= 10
    elif cores >= 4:
        score += 5
    if storage and "ssd" not in str(storage).lower():
        score -= 5
    return max(0, min(100, score))


def _build_summary(
    verdict: str,
    gaps: List[str],
    browsers: Dict[str, Any],
    ram_mb: Optional[int],
) -> str:
    parts = [f"Host verdict: {verdict}."]
    if browsers.get("has_modern_browser"):
        parts.append("A modern browser is installed.")
    else:
        parts.append("No modern browser detected — install + potato profile recommended.")
    if ram_mb is not None:
        parts.append(f"RAM: {ram_mb} MB.")
    if gaps:
        parts.append(f"Gaps: {', '.join(gaps)}.")
    return " ".join(parts)
