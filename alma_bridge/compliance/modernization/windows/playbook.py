"""Windows modernization playbooks — PowerShell steps for school labs."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from alma_bridge.compliance.modernization.windows.assess import assess_windows_host


def _step(
    step_id: str,
    description: str,
    *,
    command: Optional[str] = None,
    kind: str = "remediation",
    requires_admin: bool = False,
    **extra: Any,
) -> Dict[str, Any]:
    return {
        "id": step_id,
        "description": description,
        "command": command,
        "shell": "powershell",
        "kind": kind,
        "requires_admin": requires_admin,
        **extra,
    }


def _recommend_browser(ram_mb: Optional[int]) -> Dict[str, Any]:
    if ram_mb is not None and ram_mb < 2048:
        return {
            "tier": "light",
            "label": "Firefox ESR",
            "winget_id": "Mozilla.Firefox.ESR",
            "launch_args": "-no-remote -profile \"$env:LOCALAPPDATA\\Alma\\ClassroomBrowser\"",
        }
    return {
        "tier": "standard",
        "label": "Microsoft Edge",
        "winget_id": "Microsoft.Edge",
        "launch_args": "",
    }


def build_windows_playbook(
    assessment: Optional[Dict[str, Any]] = None,
    *,
    recipe_id: Optional[str] = None,
    include_browser: bool = True,
    include_performance_tuning: bool = True,
) -> Dict[str, Any]:
    assessment = assessment or assess_windows_host()
    gaps = set(assessment.get("gaps") or [])
    ram = assessment.get("hardware", {}).get("ram_total_mb")
    browser_rec = _recommend_browser(ram)
    steps: List[Dict[str, Any]] = []

    steps.append(
        _step(
            "sync_time",
            "Sync system clock with domain controller or NTP (required for TLS)",
            command=(
                "w32tm /resync /force; "
                "if ($LASTEXITCODE -ne 0) { "
                "w32tm /config /manualpeerlist:'time.windows.com,0x9' /syncfromflags:manual /update; "
                "Restart-Service w32time -ErrorAction SilentlyContinue; w32tm /resync /force }"
            ),
            requires_admin=True,
        )
    )

    steps.append(
        _step(
            "update_root_certs",
            "Update Windows root certificate store from Windows Update",
            command="certutil -generateSSTFromWU roots.sst; certutil -addstore -f root roots.sst; Remove-Item roots.sst -ErrorAction SilentlyContinue",
            requires_admin=True,
        )
    )

    if include_browser and ("no_modern_browser" in gaps or not assessment.get("browsers", {}).get("has_modern_browser")):
        winget = browser_rec["winget_id"]
        steps.append(
            _step(
                "install_browser",
                f"Install {browser_rec['label']} via winget ({browser_rec['tier']} tier)",
                command=f"winget install --accept-package-agreements --accept-source-agreements -e --id {winget}",
                requires_admin=True,
            )
        )
        steps.append(
            _step(
                "classroom_shortcut",
                "Create Classroom Browser desktop shortcut for students",
                command=_shortcut_script(browser_rec),
                requires_admin=False,
            )
        )

    if include_performance_tuning and ram is not None and ram < 4096:
        steps.append(
            _step(
                "tune_power",
                "Use balanced power plan and disable visual effects on low-RAM lab PCs",
                command=(
                    "powercfg /setactive SCHEME_BALANCED; "
                    "Set-ItemProperty -Path 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects' "
                    "-Name VisualFXSetting -Value 2 -ErrorAction SilentlyContinue"
                ),
                requires_admin=False,
            )
        )

    if "os_end_of_life" in gaps:
        steps.append(
            _step(
                "tls_bridge_advisory",
                "Legacy OS cannot get modern TLS — point browsers at Alma TLS bridge on lab server",
                kind="diagnostic",
                command="# Set proxy/PAC to http://<alma-server>:8443 or use Alma Container lab for legacy apps",
            )
        )

    steps.append(
        _step(
            "school_classroom_checklist",
            "Verify: district portal, Google Classroom, and one video lesson load in Classroom Browser",
            kind="diagnostic",
            command="Write-Host 'Open the Classroom Browser shortcut and test your district sites'",
        )
    )

    apply_ids = [s["id"] for s in steps if s.get("kind") == "remediation"]

    playbook = {
        "verdict": assessment.get("verdict"),
        "potato_score": assessment.get("potato_score"),
        "gaps": sorted(gaps),
        "summary": assessment.get("summary"),
        "host_platform": "windows",
        "can_apply_locally": assessment.get("can_apply_locally", False),
        "planning_only": assessment.get("planning_only", False),
        "browser_recommendation": browser_rec,
        "recipe_id": recipe_id or "school-lab-windows",
        "recipe_title": "School lab — Windows classroom web readiness",
        "steps": steps,
        "apply_step_ids": apply_ids,
        "assessment": assessment,
    }

    if recipe_id == "connectivity-only-windows":
        keep = {"sync_time", "update_root_certs", "tls_bridge_advisory", "school_classroom_checklist"}
        playbook["steps"] = [s for s in steps if s["id"] in keep]
        playbook["apply_step_ids"] = [s["id"] for s in playbook["steps"] if s.get("kind") == "remediation"]

    return playbook


def _shortcut_script(browser_rec: Dict[str, Any]) -> str:
    label = browser_rec["label"]
    if "Firefox" in label:
        exe = "${env:ProgramFiles}\\Mozilla Firefox\\firefox.exe"
        if "ESR" in label:
            exe = "${env:ProgramFiles}\\Mozilla Firefox\\firefox.exe"
        args = browser_rec.get("launch_args", "")
        return f"""
$exe = "{exe.replace('"', '`"')}"
if (-not (Test-Path $exe)) {{ $exe = "${{env:ProgramFiles(x86)}}\\Mozilla Firefox\\firefox.exe" }}
$wd = "$env:LOCALAPPDATA\\Alma\\ClassroomBrowser"
New-Item -ItemType Directory -Force -Path $wd | Out-Null
$shell = New-Object -ComObject WScript.Shell
$lnk = "$env:PUBLIC\\Desktop\\Classroom Browser.lnk"
$sc = $shell.CreateShortcut($lnk)
$sc.TargetPath = $exe
$sc.Arguments = "{args}"
$sc.WorkingDirectory = $wd
$sc.Save()
Write-Host "Shortcut: $lnk"
""".strip()
    return r"""
$exe = "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe"
if (-not (Test-Path $exe)) { $exe = "${env:ProgramFiles}\Microsoft\Edge\Application\msedge.exe" }
$shell = New-Object -ComObject WScript.Shell
$lnk = "$env:PUBLIC\Desktop\Classroom Browser.lnk"
$sc = $shell.CreateShortcut($lnk)
$sc.TargetPath = $exe
$sc.Arguments = "--disable-features=TranslateUI"
$sc.Save()
Write-Host "Shortcut: $lnk"
""".strip()
