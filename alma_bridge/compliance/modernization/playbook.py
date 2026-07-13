"""Ordered modernization playbook — from assessment gaps to concrete steps."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from alma_bridge.compliance.pm import PACKAGE_MANAGERS, detect_package_manager
from alma_bridge.compliance.modernization.assess import assess_host
from alma_bridge.compliance.modernization.browser import recommend_browser


def _step(
    step_id: str,
    description: str,
    *,
    command: Optional[str] = None,
    kind: str = "remediation",
    requires_root: bool = False,
    **extra: Any,
) -> Dict[str, Any]:
    return {
        "id": step_id,
        "description": description,
        "command": command,
        "kind": kind,
        "requires_root": requires_root,
        **extra,
    }


def build_modernization_playbook(
    assessment: Optional[Dict[str, Any]] = None,
    *,
    os_release: Optional[str] = None,
    include_browser: bool = True,
    include_potato_tuning: bool = True,
) -> Dict[str, Any]:
    """Turn a host assessment into an ordered, apply-ready modernization playbook."""
    assessment = assessment or assess_host(os_release=os_release)
    pm = assessment.get("package_manager") or detect_package_manager(os_release)
    refresh = PACKAGE_MANAGERS.get(pm, PACKAGE_MANAGERS["apt"])["refresh"]
    gaps = set(assessment.get("gaps") or [])
    ram_mb = assessment.get("hardware", {}).get("ram_total_mb")
    browser_rec = assessment.get("browser_recommendation") or recommend_browser(
        ram_mb=ram_mb, os_release=os_release
    )
    steps: List[Dict[str, Any]] = []

    # 1 — Time (TLS cert validation depends on this)
    steps.append(
        _step(
            "clock_sync",
            "Sync system clock with NTP so TLS certificates validate",
            command="sudo timedatectl set-ntp true || sudo ntpdate pool.ntp.org",
            requires_root=True,
        )
    )

    # 2 — Trust store
    steps.append(
        _step(
            "install_ca_bundle",
            "Install Alma's up-to-date CA root bundle into the system trust store",
            requires_root=True,
        )
    )

    # 3 — 32-bit runtime (x86-64 hosts running legacy 32-bit apps)
    legacy32 = assessment.get("legacy32") or {}
    if not legacy32.get("ready"):
        if "multiarch_disabled" in gaps and pm == "apt":
            steps.append(
                _step(
                    "enable_multiarch",
                    "Enable i386 multiarch for 32-bit binaries",
                    command="sudo dpkg --add-architecture i386",
                    requires_root=True,
                )
            )
            steps.append(
                _step("pkg_refresh", "Refresh package lists", command=refresh, requires_root=True)
            )
        steps.append(
            _step(
                "install_i386_runtime",
                "Install 32-bit C runtime and common libraries",
                command=(
                    "sudo apt-get install -y libc6:i386 libstdc++6:i386 zlib1g:i386"
                    if pm == "apt"
                    else f"sudo {pm} install -y glibc.i686 libstdc++.i686 zlib.i686"
                    if pm in ("dnf", "yum")
                    else None
                ),
                requires_root=True,
            )
        )
        steps.append(
            _step("ldconfig_refresh", "Refresh dynamic linker cache", command="sudo ldconfig", requires_root=True)
        )

    # 4 — Modern browser
    if include_browser and not (assessment.get("browsers") or {}).get("has_modern_browser"):
        steps.append(
            _step(
                "install_browser",
                f"Install {browser_rec.get('recommended_label', 'browser')} ({browser_rec.get('tier')} tier)",
                command=browser_rec.get("install_command"),
                requires_root=True,
            )
        )
        steps.append(
            _step(
                "write_browser_launcher",
                "Install potato-optimized browser launcher at ~/.local/bin/alma-browser",
                requires_root=False,
                script_content=browser_rec.get("launch_script"),
                launch_script=browser_rec.get("launch_script"),
            )
        )

    # 5 — Potato tuning
    if include_potato_tuning and ram_mb is not None and ram_mb < 2048:
        if "swappiness_high" in gaps or (assessment.get("swappiness") or 0) > 40:
            steps.append(
                _step(
                    "tune_swappiness",
                    "Lower swappiness to reduce thrashing on low RAM",
                    requires_root=True,
                    swappiness=10,
                )
            )
        if "no_zram" in gaps:
            steps.append(
                _step(
                    "zram_advisory",
                    "Enable zram swap for low-memory hosts (manual: install zram-tools / zram-generator)",
                    kind="diagnostic",
                    command="test -e /sys/block/zram0 && echo zram_ok || echo 'consider: sudo apt install zram-tools'",
                )
            )

    # 6 — Connectivity bridge (always document; Alma runs the bridge)
    steps.append(
        _step(
            "tls_bridge_advisory",
            "For apps that cannot speak TLS 1.2+, use Alma's TLS-modernizing bridge",
            kind="diagnostic",
            command=(
                "curl -s -X POST http://127.0.0.1:9010/compliance/tls/bridge "
                "-H 'content-type: application/json' "
                "-d '{\"upstream_host\":\"example.com\",\"upstream_port\":443}'"
            ),
        )
    )

    apply_ids = [s["id"] for s in steps if s.get("kind") == "remediation" and s["id"] != "zram_advisory"]

    return {
        "verdict": assessment.get("verdict"),
        "potato_score": assessment.get("potato_score"),
        "package_manager": pm,
        "gaps": sorted(gaps),
        "summary": assessment.get("summary"),
        "browser_recommendation": browser_rec,
        "steps": steps,
        "apply_step_ids": apply_ids,
        "assessment": assessment,
    }
