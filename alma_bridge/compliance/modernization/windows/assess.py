"""Assess a Windows host for classroom web readiness."""

from __future__ import annotations

import json
import platform
import subprocess
from typing import Any, Dict, List


def _is_windows() -> bool:
    return platform.system().lower() == "windows"


def _run_ps(script: str, *, timeout: float = 30.0) -> tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = (proc.stdout or proc.stderr or "").strip()
        return proc.returncode == 0, out
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)


def _assess_live() -> Dict[str, Any]:
    script = r"""
$os = Get-CimInstance Win32_OperatingSystem
$cs = Get-CimInstance Win32_ComputerSystem
$ramMb = [math]::Round($cs.TotalPhysicalMemory / 1MB)
$disk = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
$freeGb = if ($disk) { [math]::Round($disk.FreeSpace / 1GB, 2) } else { $null }
$browsers = @()
foreach ($p in @(
  "${env:ProgramFiles}\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
  "${env:ProgramFiles}\Mozilla Firefox\firefox.exe",
  "${env:ProgramFiles(x86)}\Mozilla Firefox\firefox.exe"
)) { if (Test-Path $p) { $browsers += (Split-Path (Split-Path $p -Parent) -Leaf) } }
$timeOk = $false
try { w32tm /query /status | Out-Null; $timeOk = $true } catch {}
@{
  os_caption = $os.Caption
  os_version = $os.Version
  build_number = $os.BuildNumber
  ram_mb = $ramMb
  disk_free_gb = $freeGb
  browsers = ($browsers | Select-Object -Unique)
  has_modern_browser = ($browsers.Count -gt 0)
  time_service_ok = $timeOk
} | ConvertTo-Json -Compress
"""
    ok, out = _run_ps(script)
    if not ok or not out:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {}


def _planning_template() -> Dict[str, Any]:
    """Generic assessment when Alma runs on Linux (lab server plans for Windows clients)."""
    return {
        "os_caption": "Windows (planning template)",
        "os_version": "",
        "build_number": "",
        "ram_mb": None,
        "disk_free_gb": None,
        "browsers": [],
        "has_modern_browser": False,
        "time_service_ok": None,
        "planning_only": True,
    }


def assess_windows_host() -> Dict[str, Any]:
    """Assess Windows readiness. Full probe on Windows; template on Linux server."""
    live = _assess_live() if _is_windows() else _planning_template()
    on_windows = _is_windows()

    gaps: List[str] = []
    if not live.get("has_modern_browser"):
        gaps.append("no_modern_browser")
    if live.get("time_service_ok") is False:
        gaps.append("clock_sync")
    if not on_windows:
        gaps.append("remote_planning")

    build = str(live.get("build_number") or live.get("os_version") or "")
    if build.isdigit() and int(build) < 10240:
        gaps.append("os_end_of_life")
    elif "Windows 7" in str(live.get("os_caption", "")):
        gaps.append("os_end_of_life")

    ram = live.get("ram_mb")
    potato = 70
    if ram is not None:
        if ram < 2048:
            potato = 35
        elif ram < 4096:
            potato = 55

    if gaps:
        verdict = "needs_modernization" if "os_end_of_life" not in gaps else "critical_legacy_os"
    elif live.get("has_modern_browser"):
        verdict = "mostly_ready"
    else:
        verdict = "needs_modernization"

    return {
        "host_platform": "windows" if on_windows else platform.system().lower(),
        "can_apply_locally": on_windows,
        "verdict": verdict,
        "potato_score": potato,
        "gaps": gaps,
        "summary": _summary(live, gaps, on_windows),
        "hardware": {
            "ram_total_mb": live.get("ram_mb"),
            "disk_free_gb": live.get("disk_free_gb"),
        },
        "os": {
            "caption": live.get("os_caption"),
            "version": live.get("os_version"),
            "build": live.get("build_number"),
        },
        "browsers": {
            "installed": live.get("browsers") or [],
            "has_modern_browser": bool(live.get("has_modern_browser")),
        },
        "time_service_ok": live.get("time_service_ok"),
        "planning_only": bool(live.get("planning_only")),
    }


def _summary(live: Dict[str, Any], gaps: List[str], on_windows: bool) -> str:
    if not on_windows:
        return (
            "Planning playbook for Windows lab PCs from Alma server — "
            "export the PowerShell script and run via GPO/PDQ on each machine (or run assess on a Windows PC)."
        )
    caption = live.get("os_caption") or "Windows"
    if "os_end_of_life" in gaps:
        return f"{caption} is past supported life — use Alma TLS bridge + browser tuning; plan OS upgrade when budget allows."
    if gaps:
        return f"{caption} needs classroom web tuning: {', '.join(gaps)}."
    return f"{caption} looks ready for classroom web with minor tuning."
