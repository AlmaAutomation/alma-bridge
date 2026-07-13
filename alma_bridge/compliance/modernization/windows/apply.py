"""Apply Windows playbook steps via PowerShell (admin-gated, allowlisted)."""

from __future__ import annotations

import platform
import subprocess
from typing import Any, Dict, List, Optional

HANDLED_STEP_IDS = frozenset(
    {
        "sync_time",
        "update_root_certs",
        "install_browser",
        "classroom_shortcut",
        "tune_power",
    }
)


def is_windows_host() -> bool:
    return platform.system().lower() == "windows"


def _run_ps(command: str, *, timeout: float = 600.0) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "command": command[:500],
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[-3000:],
            "stderr": (proc.stderr or "")[-1500:],
            "ok": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"command": command[:500], "exit_code": None, "stdout": "", "stderr": "timeout", "ok": False}
    except OSError as exc:
        return {"command": command[:500], "exit_code": None, "stdout": "", "stderr": str(exc), "ok": False}


def export_playbook_script(playbook: Dict[str, Any]) -> str:
    """Render remediation steps as a single elevated PowerShell script for GPO/PDQ."""
    lines = [
        "# Alma school-lab-windows playbook — run elevated on lab PCs",
        "#Requires -RunAsAdministrator",
        "$ErrorActionPreference = 'Stop'",
        f"# Recipe: {playbook.get('recipe_id', 'school-lab-windows')}",
        "",
    ]
    for step in playbook.get("steps") or []:
        if step.get("kind") != "remediation":
            continue
        cmd = step.get("command")
        if not cmd:
            continue
        lines.append(f"# --- {step.get('id')}: {step.get('description')} ---")
        lines.append(cmd)
        lines.append("")
    lines.append("Write-Host 'Alma Windows playbook finished.'")
    return "\n".join(lines)


def apply_windows_playbook(
    playbook: Dict[str, Any],
    *,
    step_ids: Optional[List[str]] = None,
    allow_mutations: bool = False,
    stop_on_error: bool = True,
) -> Dict[str, Any]:
    if not allow_mutations:
        return {
            "applied": False,
            "success": False,
            "reason": "allow_mutations is false — plan only",
            "results": [],
            "export_script": export_playbook_script(playbook),
        }

    if not is_windows_host():
        return {
            "applied": False,
            "success": False,
            "reason": (
                "Alma is not running on Windows — export export_script and run via GPO, "
                "PDQ Deploy, or Intune on lab PCs"
            ),
            "results": [],
            "export_script": export_playbook_script(playbook),
        }

    wanted = set(step_ids) if step_ids else None
    results: List[Dict[str, Any]] = []
    applied_any = False

    for step in playbook.get("steps") or []:
        sid = step.get("id")
        if step.get("kind") == "diagnostic":
            continue
        if wanted is not None and sid not in wanted:
            continue
        if sid not in HANDLED_STEP_IDS:
            continue
        cmd = step.get("command")
        if not cmd:
            continue
        result = _run_ps(cmd)
        result["step_id"] = sid
        results.append(result)
        applied_any = True
        if stop_on_error and not result["ok"]:
            break

    return {
        "applied": applied_any,
        "success": all(r.get("ok") for r in results) if results else False,
        "results": results,
        "export_script": export_playbook_script(playbook),
    }
