"""Map Bridge execution signatures → host + Wine remediation pathways."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from alma_bridge.learning.remediation import remediations_for_signature


def build_bridge_signature_pathways(
    bridge_signature: str,
    *,
    error_text: str = "",
    file_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Turn a Bridge error signature into ranked autopilot-style pathways."""
    sig = (bridge_signature or "unknown_error").strip()
    pathways: List[Dict[str, Any]] = []
    text = (error_text or "").lower()
    is_pe = (file_path or "").lower().endswith((".exe", ".msi", ".bat", ".cmd"))

    def add(pid: str, title: str, commands: List[str], *, score: float = 0.94) -> None:
        pathways.append({
            "id": f"bridge:{pid}",
            "title": title,
            "signature": sig,
            "category": "bridge",
            "score": score,
            "synthesized": True,
            "steps": [
                {
                    "description": title,
                    "command": cmd,
                    "kind": "remediation",
                    "requires_root": "sudo" in cmd,
                }
                for cmd in commands
            ],
        })

    if sig in {"electron_gpu_crash", "gpu_crash", "display_crash"}:
        add(
            "disable_gpu",
            "Disable GPU for Electron/Chromium under Wine",
            [
                'export WINEDEBUG="-all"',
                "winetricks -q settings gl=disabled 2>/dev/null || true",
            ],
            score=0.97,
        )

    if sig in {"missing_dll", "missing_visual_c_runtime", "dotnet_missing"}:
        prefix_cmd = ""
        if file_path:
            from alma_bridge.hardware.prefixes import find_best_prefix

            prefix = find_best_prefix(file_path)
            if prefix:
                prefix_cmd = f'WINEPREFIX="{prefix}" BROWSER=/bin/true '
        add(
            "winetricks_runtimes",
            "Install VC++ / .NET runtimes via winetricks",
            [
                f"{prefix_cmd}winetricks -q vcrun2019 vcrun2022 dotnet48 2>/dev/null || true",
            ],
            score=0.96,
        )

    if sig in {"permission_denied", "prefix_not_writable"}:
        add(
            "fresh_wineprefix",
            "Create fresh WINEPREFIX (permission_denied)",
            [
                'rm -rf ~/.wine-alma-fresh && WINEARCH=win64 WINEPREFIX=~/.wine-alma-fresh wineboot -i',
            ],
            score=0.98,
        )
        add(
            "fix_prefix_perms",
            "Repair Wine prefix ownership",
            [
                'sudo chown -R "$USER:$USER" ~/.wine 2>/dev/null || true',
                "chmod -R u+rwx ~/.wine 2>/dev/null || true",
            ],
            score=0.93,
        )

    if sig in {"client_services_stalled", "sidecar_silent_crash", "electron_crashpad_failure", "wine_int3_crash"}:
        add(
            "electron_sidecar_bootstrap",
            "Bootstrap Electron sidecar runtimes",
            [
                'export ALMA_RUN_WINETRICKS="vcrun2019,vcrun2022,dotnet48"',
                'export ELECTRON_DISABLE_CRASH_REPORTER=1',
                'export WINEDEBUG="-all"',
            ],
            score=0.95,
        )
        add(
            "mingw_electron_wrappers",
            "Install mingw cross-compiler for Electron-on-Wine wrappers",
            [
                "sudo apt-get install -y gcc-mingw-w64-x86-64",
            ],
            score=0.97,
        )

    if sig == "architecture_mismatch" or "elfclass32" in text or "wrong elf class" in text:
        add(
            "enable_multiarch",
            "Enable 32-bit multiarch support",
            [
                "sudo dpkg --add-architecture i386 2>/dev/null || true",
                "sudo apt-get update && sudo apt-get install -y libc6:i386 libstdc++6:i386",
            ],
            score=0.92,
        )

    if sig in {"file_not_found", "missing_dependency"} or "cannot open shared object" in text:
        add(
            "host_ldd_probe",
            "Probe missing host libraries",
            [
                f'ldd "{file_path}" 2>&1 | grep "not found" || true' if file_path else "ldconfig -p | head",
            ],
            score=0.88,
        )

    if sig == "sudo_password_required":
        add(
            "sudo_warmup",
            "Warm sudo credentials for host remediation",
            ["sudo -v"],
            score=0.99,
        )

    if sig == "windows_version_required":
        add(
            "wine_version_win10",
            "Set Wine Windows version to Windows 10",
            ['winetricks -q win10 2>/dev/null || winecfg'],
            score=0.91,
        )

    # Surface top learned Bridge remediations as informational pathway steps.
    for rem in remediations_for_signature(sig, electron=is_pe)[:3]:
        rem_id = rem.get("id")
        if not rem_id or rem_id == "baseline_retry":
            continue
        desc = rem.get("description") or rem_id
        env_hints = []
        for key, val in (rem.get("env") or {}).items():
            env_hints.append(f'export {key}="{val}"')
        args = rem.get("args") or []
        if args:
            env_hints.append(f"# retry args: {' '.join(args)}")
        if env_hints:
            add(
                f"remediation_{rem_id}",
                f"Bridge remediation — {desc}",
                env_hints,
                score=0.9 - rem.get("priority", 10) * 0.01,
            )

    return pathways
