"""Built-in modernization playbook recipes (exportable JSON templates)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from alma_bridge.compliance.modernization.playbook import build_modernization_playbook
from alma_bridge.flagship import is_flagship_recipe

BUILTIN_PLAYBOOKS: Dict[str, Dict[str, Any]] = {
    "school-lab": {
        "title": "School lab — classroom web readiness",
        "description": (
            "For cash-strapped lab PCs: NTP, CA trust, RAM-tier browser, classroom launcher, "
            "student desktop shortcut, low-memory tuning. Skips 32-bit/multiarch — web learning only."
        ),
        "include_browser": True,
        "include_potato_tuning": True,
        "skip_multiarch": True,
        "school_lab": True,
        "target_audience": "school_lab",
    },
    "potato-browser-only": {
        "title": "Low-RAM browser + connectivity",
        "description": "Clock, CA bundle, lightweight browser, low-RAM launcher — no multiarch.",
        "include_browser": True,
        "include_potato_tuning": True,
        "skip_multiarch": True,
    },
    "full-legacy-x86": {
        "title": "Full x86 legacy enablement",
        "description": "Multiarch, i386 runtime, browser, CA, NTP, swappiness tuning.",
        "include_browser": True,
        "include_potato_tuning": True,
        "skip_multiarch": False,
    },
    "connectivity-only": {
        "title": "Modern web connectivity",
        "description": "NTP + CA bundle + TLS bridge instructions only (no packages).",
        "include_browser": False,
        "include_potato_tuning": False,
        "connectivity_only": True,
    },
    "container-lab": {
        "title": "Container shim lab — VM-like isolation",
        "description": (
            "Run legacy binaries inside Alma sandbox with Wine/QEMU + full shim pack. "
            "Modern glibc/userland without upgrading the host — ideal for frozen school lab PCs."
        ),
        "include_browser": False,
        "include_potato_tuning": False,
        "skip_multiarch": True,
        "container_lab": True,
    },
    "school-lab-windows": {
        "title": "School lab — Windows classroom web readiness",
        "description": (
            "PowerShell plan: NTP, root certs, winget browser, Classroom shortcut, "
            "low-RAM tuning. Export .ps1 for GPO/PDQ when Alma runs on Linux server."
        ),
        "windows_playbook": True,
        "recipe_id": "school-lab-windows",
    },
}


def list_playbooks() -> List[Dict[str, Any]]:
    return [
        {
            "id": pid,
            **{
                k: v
                for k, v in meta.items()
                if k not in {"connectivity_only", "school_lab", "container_lab", "windows_playbook"}
            },
            "flagship": is_flagship_recipe(pid),
            "program_id": "alma-lab-modernization" if is_flagship_recipe(pid) else None,
        }
        for pid, meta in BUILTIN_PLAYBOOKS.items()
    ]


def _classroom_notes(
    ram_mb: Optional[int],
    assessment: Dict[str, Any],
) -> str:
    tier = (assessment.get("browser_recommendation") or {}).get("tier", "light")
    if ram_mb is not None and ram_mb < 768:
        return (
            "Very low RAM for a full classroom browser — use one shared station per row "
            "or retire this PC from daily web use."
        )
    if ram_mb is not None and ram_mb < 2048:
        return (
            f"Lightweight {tier}-tier browser profile applied. "
            "Teachers: launch Classroom Browser from the applications menu."
        )
    return (
        "Standard classroom browser profile. "
        "Teachers: launch Classroom Browser from the applications menu."
    )


def _inject_school_lab_steps(playbook: Dict[str, Any]) -> None:
    """Add school-lab steps: forced swappiness, desktop shortcut, IT checklist."""
    assessment = playbook.get("assessment") or {}
    ram_mb = assessment.get("hardware", {}).get("ram_total_mb")
    steps: List[Dict[str, Any]] = playbook["steps"]

    bridge_idx = next(
        (i for i, s in enumerate(steps) if s.get("id") == "tls_bridge_advisory"),
        len(steps),
    )

    if ram_mb is not None and ram_mb < 2048 and not any(
        s.get("id") == "tune_swappiness" for s in steps
    ):
        steps.insert(
            bridge_idx,
            {
                "id": "tune_swappiness",
                "description": "Lower swappiness so low-RAM lab PCs stay responsive",
                "command": None,
                "kind": "remediation",
                "requires_root": True,
                "swappiness": 10,
            },
        )
        bridge_idx += 1

    if any(s.get("id") == "write_browser_launcher" for s in steps):
        steps.insert(
            bridge_idx,
            {
                "id": "school_desktop_shortcut",
                "description": "Add Classroom Browser shortcut to the student applications menu",
                "command": None,
                "kind": "remediation",
                "requires_root": False,
            },
        )

    steps.append(
        {
            "id": "school_classroom_checklist",
            "description": (
                "After apply: open Classroom Browser and verify district portal, "
                "Google Classroom, and one video lesson load"
            ),
            "command": (
                "test -x \"$HOME/.local/bin/alma-browser\" "
                "&& echo 'Launcher ready — open Classroom Browser from the menu' "
                "|| echo 'Run apply first to install the classroom browser'"
            ),
            "kind": "diagnostic",
            "requires_root": False,
        }
    )
    steps.append(
        {
            "id": "school_lab_policy",
            "description": (
                "Lab policy: students use Classroom Browser only; no admin installs; "
                "cert/time errors → IT; blocked sites may need Alma TLS bridge on one lab server"
            ),
            "command": None,
            "kind": "diagnostic",
            "requires_root": False,
        }
    )

    playbook["apply_step_ids"] = [
        s["id"]
        for s in steps
        if s.get("kind") == "remediation" and s["id"] != "zram_advisory"
    ]
    playbook["school_lab"] = True
    playbook["target_audience"] = "school_lab"
    playbook["classroom_notes"] = _classroom_notes(ram_mb, assessment)


def build_recipe_playbook(
    recipe_id: str,
    assessment: Optional[Dict[str, Any]] = None,
    *,
    os_release: Optional[str] = None,
) -> Dict[str, Any]:
    meta = BUILTIN_PLAYBOOKS.get(recipe_id)
    if not meta:
        raise KeyError(f"unknown playbook: {recipe_id}")

    if meta.get("windows_playbook"):
        from alma_bridge.compliance.modernization.windows import (
            assess_windows_host,
            build_windows_playbook,
            export_playbook_script,
        )

        assessment = assessment or assess_windows_host()
        win = build_windows_playbook(
            assessment,
            recipe_id=meta.get("recipe_id", recipe_id),
        )
        win["recipe_description"] = meta["description"]
        win["export_script"] = export_playbook_script(win)
        return win

    playbook = build_modernization_playbook(
        assessment,
        os_release=os_release,
        include_browser=meta.get("include_browser", True),
        include_potato_tuning=meta.get("include_potato_tuning", True),
    )
    playbook["recipe_id"] = recipe_id
    playbook["recipe_title"] = meta["title"]
    playbook["recipe_description"] = meta["description"]

    if meta.get("connectivity_only"):
        playbook["steps"] = [
            s for s in playbook["steps"]
            if s.get("id") in {"clock_sync", "install_ca_bundle", "tls_bridge_advisory"}
        ]
        playbook["apply_step_ids"] = [
            s["id"] for s in playbook["steps"] if s.get("kind") == "remediation"
        ]

    if meta.get("skip_multiarch"):
        skip = {"enable_multiarch", "install_i386_runtime", "pkg_refresh", "ldconfig_refresh"}
        playbook["steps"] = [s for s in playbook["steps"] if s.get("id") not in skip]
        playbook["apply_step_ids"] = [
            sid for sid in playbook.get("apply_step_ids", []) if sid not in skip
        ]

    if meta.get("school_lab"):
        _inject_school_lab_steps(playbook)

    if meta.get("container_lab"):
        playbook["steps"] = [
            {
                "id": "container_shim_intro",
                "kind": "diagnostic",
                "description": (
                    "Provide file_path to build a shim pack — Alma wraps the binary with "
                    "Wine/QEMU inside the sandbox container and applies GPU/memory/network shims."
                ),
                "command": (
                    "curl -s -X POST http://127.0.0.1:9010/container/shim-pack "
                    "-H 'content-type: application/json' "
                    "-d '{\"file_path\":\"/path/to/binary\"}'"
                ),
            },
            {
                "id": "container_run_intro",
                "kind": "diagnostic",
                "description": "Execute the shim pack (requires Docker/Podman + sandbox image built).",
                "command": (
                    "curl -s -X POST http://127.0.0.1:9010/container/run "
                    "-H 'content-type: application/json' "
                    "-d '{\"file_path\":\"/path/to/binary\"}'"
                ),
            },
            {
                "id": "tls_bridge_advisory",
                "kind": "diagnostic",
                "description": "Pair with Alma TLS bridge on the host for sites the container browser cannot reach.",
                "command": (
                    "curl -s -X POST http://127.0.0.1:9010/compliance/tls/bridge "
                    "-H 'content-type: application/json' "
                    "-d '{\"upstream_host\":\"example.com\",\"upstream_port\":443}'"
                ),
            },
        ]
        playbook["apply_step_ids"] = []
        playbook["container_lab"] = True
        playbook["notes"] = (
            "No host mutations — isolation happens inside the Alma sandbox container. "
            "Build image: docker build -t alma-bridge-sandbox:latest ."
        )

    return playbook
