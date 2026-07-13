from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from alma_bridge.hardware.shims import shim_env

# Remediation actions from almasysdet profiles + alma_resolve recovery scripts.
REMEDIATION_ACTIONS: List[Dict[str, Any]] = [
    {
        "id": "baseline_retry",
        "signature": "*",
        "description": "Retry with clean environment and no extra overrides.",
        "env": {},
        "shims": [],
        "args": [],
        "priority": 100,
    },
    {
        "id": "dotnet_bootstrap_first",
        "signature": "dotnet_missing",
        "description": "Install VC++ and .NET 4.8 in Wine prefix before relaunch.",
        "env": {"ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022,dotnet48", "WINEDEBUG": "-all"},
        "shims": [],
        "args": [],
        "priority": 1,
    },
    {
        "id": "ascension_int3_full_repair",
        "signature": "wine_int3_crash",
        "description": "Ascension/Electron int3 — reinstall Wine wrappers, bootstrap runtimes, GPU-off via env.",
        "env": {
            "WINEDEBUG": "-all",
            "ELECTRON_DISABLE_CRASH_REPORTER": "1",
            "ALMA_SKIP_ELECTRON_UPDATE": "1",
            "ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022,dotnet48",
            "DXVK_DISABLE": "1",
            "WINE_D3D_RENDERER": "gdi",
            "WINEDLLOVERRIDES": "d3d11,d3d10core,dxgi=disabled",
        },
        "shims": [
            "electron_launcher_guard_workaround",
            "electron_elevate_passthrough",
            "disable_dxvk",
            "mesa_glthread_off",
        ],
        "args": [
            "--disable-gpu",
            "--no-sandbox",
            "--disable-crash-reporter",
            "--disable-breakpad",
            "--disable-features=CrashReporting",
        ],
        "replace_args": True,
        "priority": 1,
        "electron_only": True,
    },
    {
        "id": "ascension_int3_guard_refresh",
        "signature": "wine_int3_crash",
        "description": "Refresh sidecar guard + decoy after int3 crash, then relaunch.",
        "env": {"WINEDEBUG": "-all", "ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022"},
        "shims": ["electron_launcher_guard_workaround", "electron_elevate_passthrough"],
        "args": [],
        "replace_args": True,
        "priority": 2,
        "electron_only": True,
    },
    {
        "id": "launcher_no_cli_flags",
        "signature": "invalid_launch_args",
        "description": "Launcher wrapper rejects Chromium flags — relaunch with no extra CLI args.",
        "env": {"WINEDEBUG": "-all"},
        "shims": [],
        "args": [],
        "replace_args": True,
        "priority": 1,
        "electron_only": True,
    },
    {
        "id": "launcher_sidecar_vcrun",
        "signature": "client_services_stalled",
        "description": "Bootstrap VC++ and .NET runtimes for the Electron sidecar, then relaunch.",
        "env": {"ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022,dotnet48", "WINEDEBUG": "-all"},
        "shims": [],
        "args": [],
        "priority": 4,
        "electron_only": True,
    },
    {
        "id": "sidecar_silent_crash_refresh",
        "signature": "sidecar_silent_crash",
        "description": "Refresh sidecar guard wrapper after a silent sidecar crash, then bootstrap VC++/dotnet.",
        "env": {"ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022,dotnet48", "WINEDEBUG": "-all"},
        "shims": ["electron_launcher_guard_workaround"],
        "args": [],
        "priority": 2,
        "electron_only": True,
    },
    {
        "id": "electron_launcher_guard_workaround",
        "signature": "client_services_stalled",
        "description": "Refresh sidecar guard wrapper and decoy before relaunch.",
        "env": {},
        "shims": ["electron_launcher_guard_workaround"],
        "args": [],
        "priority": 5,
        "electron_only": True,
    },
    {
        "id": "electron_update_check_offline",
        "signature": "client_services_stalled",
        "description": "Skip in-app update check and relaunch the sidecar.",
        "env": {"ALMA_SKIP_ELECTRON_UPDATE": "1"},
        "shims": [],
        "args": ["--no-update", "--skip-update"],
        "priority": 6,
        "electron_only": True,
    },
    {
        "id": "electron_disable_crashpad",
        "signature": "electron_crashpad_failure",
        "description": "Disable Electron Crashpad — under Wine it fails to attach and the app self-terminates.",
        "env": {"ELECTRON_DISABLE_CRASH_REPORTER": "1", "WINEDEBUG": "-all"},
        "shims": [],
        "args": ["--disable-crash-reporter", "--disable-breakpad", "--disable-features=CrashReporting"],
        "priority": 3,
        "electron_only": True,
    },
    {
        "id": "electron_disable_gpu",
        "signature": "electron_gpu_crash",
        "description": "Disable Electron's GPU process entirely (--disable-gpu). Under Wine every Chromium GPU backend fails the 'shared context for virtualization' and crash-loops; this is the only stable option (matches official Project Ascension guidance).",
        "env": {"WINEDEBUG": "-all"},
        "shims": ["electron_disable_gpu"],
        "args": ["--disable-gpu", "--no-sandbox"],
        "priority": 3,
    },
    {
        "id": "electron_disable_gpu_generic",
        "signature": "gpu_crash",
        "description": "Electron-under-Wine GPU fallback: --disable-gpu --no-sandbox.",
        "env": {"WINEDEBUG": "-all"},
        "shims": ["electron_disable_gpu"],
        "args": ["--disable-gpu", "--no-sandbox"],
        "priority": 12,
    },
    {
        "id": "electron_elevate_passthrough",
        "signature": "elevation_failed",
        "description": "Replace electron-builder's elevate.exe (Windows 'runas' UAC verb, which Wine cannot grant) with a CreateProcess passthrough so elevated child processes actually start.",
        "env": {},
        "shims": ["electron_elevate_passthrough"],
        "args": [],
        "priority": 4,
        "electron_only": True,
    },
    {
        "id": "electron_launcher_guard_workaround",
        "signature": "launcher_guard_shutdown",
        "description": "Wrap the app's elevated sidecar so its launcher_guard watches a correctly-named, reliably-alive decoy. Wine misreports the live Electron launcher PID as exited after ~1s, which kills the sidecar API and leaves the UI on its loading splash.",
        "env": {},
        "shims": ["electron_launcher_guard_workaround"],
        "args": [],
        "priority": 4,
        "electron_only": True,
    },
    {
        "id": "electron_update_check_offline",
        "signature": "winsock_update_hang",
        "description": "Wine's winsock change-notifier (WSALookupServiceBegin failed: 8) sometimes hangs the Electron auto-updater at 'Checking for update'. Skip the in-app update check so the launcher proceeds.",
        "env": {"ALMA_SKIP_ELECTRON_UPDATE": "1"},
        "shims": [],
        "args": ["--no-update", "--skip-update"],
        "priority": 8,
    },
    {
        "id": "software_rendering",
        "signature": "gpu_crash",
        "description": "Force software rendering (alma_resolve Electron profile).",
        "env": {"WINEDEBUG": "-all"},
        "shims": ["software_opengl", "disable_dxvk"],
        "args": ["--disable-gpu", "--disable-gpu-compositing", "--in-process-gpu"],
        "priority": 10,
    },
    {
        "id": "wined3d_fallback",
        "signature": "gpu_crash",
        "description": "Disable DXVK and use WineD3D (alma_resolve).",
        "env": {
            "WINEDEBUG": "-all",
            "WINEDLLOVERRIDES": "dxgi,d3d11,d3d10core=",
        },
        "shims": ["disable_dxvk"],
        "args": ["--disable-gpu"],
        "priority": 20,
    },
    {
        "id": "gpu_process_disabled",
        "signature": "gpu_crash",
        "description": "Disable GPU process for Electron launchers (alma_resolve).",
        "env": {"WINEDEBUG": "-all"},
        "shims": ["disable_dxvk"],
        "args": ["--disable-gpu", "--in-process-gpu"],
        "priority": 25,
    },
    {
        "id": "wine_windows_version_win10",
        "signature": "windows_version_required",
        "description": "Set Wine's reported Windows version to Windows 10 so installers stop rejecting the prefix.",
        "env": {"ALMA_WINE_WINDOWS_VERSION": "win10", "WINEDEBUG": "-all"},
        "shims": [],
        "args": [],
        "priority": 2,
        "installer_only": True,
    },
    {
        "id": "installer_aborted_win10",
        "signature": "installer_aborted",
        "description": "Installer exited immediately — set Windows 10 and retry with /NCRC.",
        "env": {"ALMA_WINE_WINDOWS_VERSION": "win10", "WINEDEBUG": "-all"},
        "shims": [],
        "args": ["/NCRC"],
        "priority": 3,
        "installer_only": True,
    },
    {
        "id": "installer_bootstrap_win10_vcrun_ncrc",
        "signature": "installer_not_verified",
        "description": "Bootstrap Windows 10 + VC++ runtimes, then retry NSIS with /NCRC.",
        "env": {
            "ALMA_WINE_WINDOWS_VERSION": "win10",
            "ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022",
            "WINEDEBUG": "-all",
        },
        "shims": [],
        "args": ["/NCRC"],
        "priority": 2,
        "installer_only": True,
    },
    {
        "id": "installer_bootstrap_full_ncrc",
        "signature": "installer_not_verified",
        "description": "Full bootstrap: Windows 10 + VC++ + .NET 4.8, then /NCRC.",
        "env": {
            "ALMA_WINE_WINDOWS_VERSION": "win10",
            "ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022,dotnet48",
            "WINEDEBUG": "-all",
        },
        "shims": [],
        "args": ["/NCRC"],
        "priority": 4,
        "installer_only": True,
    },
    {
        "id": "installer_silent_nsis_bootstrap",
        "signature": "installer_not_verified",
        "description": "Bootstrap runtimes and silent NSIS install (/S /NCRC).",
        "env": {
            "ALMA_WINE_WINDOWS_VERSION": "win10",
            "ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022",
            "WINEDEBUG": "-all",
        },
        "shims": [],
        "args": ["/S", "/NCRC"],
        "priority": 6,
        "installer_only": True,
    },
    {
        "id": "installer_silent_inno_bootstrap",
        "signature": "installer_not_verified",
        "description": "Bootstrap + Inno Setup silent flags.",
        "env": {
            "ALMA_WINE_WINDOWS_VERSION": "win10",
            "ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022,dotnet48",
            "WINEDEBUG": "-all",
        },
        "shims": [],
        "args": ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NCRC"],
        "priority": 8,
        "installer_only": True,
    },
    {
        "id": "installer_fresh_prefix_silent",
        "signature": "installer_not_verified",
        "description": "Clean prefix + full bootstrap + silent NSIS (/S /NCRC).",
        "env": {
            "ALMA_FRESH_PREFIX": "1",
            "ALMA_WINE_WINDOWS_VERSION": "win10",
            "ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022,dotnet48",
            "WINEDEBUG": "-all",
        },
        "shims": [],
        "args": ["/S", "/NCRC"],
        "priority": 10,
        "installer_only": True,
    },
    {
        "id": "installer_virtual_desktop_silent",
        "signature": "installer_not_verified",
        "description": "Virtual desktop + bootstrap + silent NSIS.",
        "env": {
            "ALMA_WINE_VIRTUAL_DESKTOP": "1280x720",
            "ALMA_WINE_WINDOWS_VERSION": "win10",
            "ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022",
            "WINEDEBUG": "-all",
        },
        "shims": [],
        "args": ["/S", "/NCRC"],
        "priority": 12,
        "installer_only": True,
    },
    {
        "id": "installer_aborted_bootstrap_win10_vcrun",
        "signature": "installer_aborted",
        "description": "Installer aborted early — bootstrap Windows 10 + VC++ and /NCRC.",
        "env": {
            "ALMA_WINE_WINDOWS_VERSION": "win10",
            "ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022",
            "WINEDEBUG": "-all",
        },
        "shims": [],
        "args": ["/NCRC"],
        "priority": 4,
        "installer_only": True,
    },
    {
        "id": "installer_aborted_silent_nsis",
        "signature": "installer_aborted",
        "description": "Silent NSIS after bootstrap (no GUI dialogs).",
        "env": {
            "ALMA_WINE_WINDOWS_VERSION": "win10",
            "ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022,dotnet48",
            "WINEDEBUG": "-all",
        },
        "shims": [],
        "args": ["/S", "/NCRC"],
        "priority": 6,
        "installer_only": True,
    },
    {
        "id": "installer_aborted_fresh_silent",
        "signature": "installer_aborted",
        "description": "Fresh prefix + full bootstrap + silent NSIS.",
        "env": {
            "ALMA_FRESH_PREFIX": "1",
            "ALMA_WINE_WINDOWS_VERSION": "win10",
            "ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022,dotnet48",
            "WINEDEBUG": "-all",
        },
        "shims": [],
        "args": ["/S", "/NCRC"],
        "priority": 8,
        "installer_only": True,
    },
    {
        "id": "windows_version_bootstrap_full",
        "signature": "windows_version_required",
        "description": "Set Windows 10 + bootstrap VC++/.NET before retry.",
        "env": {
            "ALMA_WINE_WINDOWS_VERSION": "win10",
            "ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022,dotnet48",
            "WINEDEBUG": "-all",
        },
        "shims": [],
        "args": ["/NCRC"],
        "priority": 3,
        "installer_only": True,
    },
    {
        "id": "windows_version_silent_nsis",
        "signature": "windows_version_required",
        "description": "Windows 10 + bootstrap + silent NSIS (/S /NCRC).",
        "env": {
            "ALMA_WINE_WINDOWS_VERSION": "win10",
            "ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022",
            "WINEDEBUG": "-all",
        },
        "shims": [],
        "args": ["/S", "/NCRC"],
        "priority": 5,
        "installer_only": True,
    },
    {
        "id": "installer_virtual_desktop",
        "signature": "wine_shell_error",
        "description": "Run installer inside a Wine virtual desktop with /NCRC.",
        "env": {"ALMA_WINE_VIRTUAL_DESKTOP": "1280x720", "WINEDEBUG": "-all"},
        "shims": [],
        "args": ["/NCRC"],
        "priority": 8,
        "installer_only": True,
    },
    {
        "id": "virtual_desktop",
        "signature": "display_crash",
        "description": "Launch inside a Wine virtual desktop.",
        "env": {},
        "shims": ["virtual_desktop"],
        "args": [],
        "priority": 15,
    },
    {
        "id": "best_known_profile",
        "signature": "gpu_crash",
        "description": "Combined alma_resolve best-known Wine profile.",
        "env": {
            "WINEDEBUG": "-all",
            "WINEDLLOVERRIDES": "dxgi,d3d11,d3d10core=",
        },
        "shims": ["disable_dxvk"],
        "args": ["--disable-gpu"],
        "priority": 18,
    },
    {
        "id": "win32_prefix",
        "signature": "architecture_mismatch",
        "description": "Retry with 32-bit Wine prefix.",
        "env": {},
        "shims": ["win32_prefix"],
        "args": [],
        "priority": 5,
    },
    {
        "id": "multiarch_libs",
        "signature": "missing_dependency",
        "description": "Expose 32-bit native libraries.",
        "env": {},
        "shims": ["ld_library_path_32"],
        "args": [],
        "priority": 10,
    },
    {
        "id": "missing_dll_winetricks",
        "signature": "missing_dll",
        "description": "Hint winetricks install for missing Windows DLLs.",
        "env": {"ALMA_HINT_WINETRICKS": "vcrun2019"},
        "shims": [],
        "args": [],
        "priority": 8,
    },
    {
        "id": "wine_prefix_reset_hint",
        "signature": "wine_prefix_problem",
        "description": "Retry with a clean prefix env (caller supplies WINEPREFIX).",
        "env": {"WINEDEBUG": "-all"},
        "shims": [],
        "args": [],
        "priority": 5,
    },
    {
        "id": "nsis_ncrc",
        "signature": "unknown_error",
        "description": "NSIS installer: skip CRC integrity check.",
        "env": {"WINEDEBUG": "-all"},
        "shims": [],
        "args": ["/NCRC"],
        "priority": 12,
        "installer_only": True,
    },
    {
        "id": "silent_install",
        "signature": "unknown_error",
        "description": "Try silent NSIS install (/S).",
        "env": {"WINEDEBUG": "-all"},
        "shims": [],
        "args": ["/S"],
        "priority": 14,
        "installer_only": True,
    },
    {
        "id": "inno_silent",
        "signature": "unknown_error",
        "description": "Try Inno Setup silent flags.",
        "env": {"WINEDEBUG": "-all"},
        "shims": [],
        "args": ["/VERYSILENT", "/SUPPRESSMSGBOXES"],
        "priority": 16,
        "installer_only": True,
    },
    {
        "id": "installer_vcrun",
        "signature": "unknown_error",
        "description": "Bootstrap VC++ runtimes via winetricks before install.",
        "env": {"ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022", "WINEDEBUG": "-all"},
        "shims": [],
        "args": [],
        "priority": 8,
        "installer_only": True,
    },
    {
        "id": "installer_dotnet",
        "signature": "unknown_error",
        "description": "Bootstrap .NET 4.8 via winetricks before install.",
        "env": {"ALMA_RUN_WINETRICKS": "dotnet48", "WINEDEBUG": "-all"},
        "shims": [],
        "args": [],
        "priority": 9,
        "installer_only": True,
    },
    {
        "id": "fresh_wine_prefix",
        "signature": "wine_prefix_problem",
        "description": "Use a clean session-scoped WINEPREFIX.",
        "env": {"WINEDEBUG": "-all", "ALMA_FRESH_PREFIX": "1"},
        "shims": [],
        "args": [],
        "priority": 4,
    },
    {
        "id": "nsis_ncrc",
        "signature": "nsis_installer_failure",
        "description": "NSIS installer: skip CRC integrity check.",
        "env": {"WINEDEBUG": "-all"},
        "shims": [],
        "args": ["/NCRC"],
        "priority": 5,
    },
    {
        "id": "installer_vcrun",
        "signature": "missing_dll",
        "description": "Install VC++ runtimes via winetricks.",
        "env": {"ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022", "WINEDEBUG": "-all"},
        "shims": [],
        "args": [],
        "priority": 6,
    },
    {
        "id": "installer_dotnet",
        "signature": "dotnet_missing",
        "description": "Install .NET 4.8 via winetricks.",
        "env": {"ALMA_RUN_WINETRICKS": "dotnet48", "WINEDEBUG": "-all"},
        "shims": [],
        "args": [],
        "priority": 5,
    },
    {
        "id": "java_jre_winetricks",
        "signature": "java_missing",
        "description": "Install a Windows Java runtime via winetricks.",
        "env": {"ALMA_RUN_WINETRICKS": "java8", "WINEDEBUG": "-all"},
        "shims": [],
        "args": [],
        "priority": 6,
    },
    {
        "id": "legacy_opengl_wined3d",
        "signature": "opengl_legacy",
        "description": "Legacy OpenGL/D3D title — disable DXVK and use WineD3D.",
        "env": {
            "WINEDEBUG": "-all",
            "WINEDLLOVERRIDES": "dxgi,d3d11,d3d10core,d3d9=",
        },
        "shims": ["disable_dxvk", "software_opengl"],
        "args": [],
        "priority": 8,
    },
    {
        "id": "legacy_directx9",
        "signature": "directx_old",
        "description": "Install legacy DirectX components for older games.",
        "env": {"ALMA_RUN_WINETRICKS": "d3dx9_43,d3dcompiler_47", "WINEDEBUG": "-all"},
        "shims": ["disable_dxvk"],
        "args": [],
        "priority": 9,
    },
    {
        "id": "wine_debug_collect",
        "signature": "unknown_error",
        "description": "Collect verbose Wine diagnostics.",
        "env": {"WINEDEBUG": "+timestamp,+pid,+tid,+seh,+module"},
        "shims": [],
        "args": [],
        "priority": 50,
    },
    {
        "id": "network_workarounds",
        "signature": "unknown_error",
        "description": "Networking workarounds for Electron launchers (alma_resolve).",
        "env": {"WINEDEBUG": "-all"},
        "shims": [],
        "args": ["--disable-http-cache", "--no-proxy-server"],
        "priority": 35,
    },
    {
        "id": "low_resource_mode",
        "signature": "unknown_error",
        "description": "Reduce resource pressure for legacy hardware.",
        "env": {},
        "shims": ["old_cpu_compat"],
        "args": [],
        "priority": 40,
    },
    {
        "id": "audio_compat",
        "signature": "audio_failure",
        "description": "Apply PulseAudio compatibility settings.",
        "env": {},
        "shims": ["pulse_audio_compat"],
        "args": [],
        "priority": 10,
    },
    {
        "id": "container_isolation",
        "signature": "*",
        "description": "Retry inside container sandbox with compatibility tooling.",
        "env": {},
        "shims": [],
        "args": [],
        "force_mode": "container",
        "priority": 30,
    },
    {
        "id": "permission_fresh_prefix",
        "signature": "permission_denied",
        "description": "Permission failure under Wine — retry with a clean session prefix.",
        "env": {"WINEDEBUG": "-all", "ALMA_FRESH_PREFIX": "1"},
        "shims": [],
        "args": [],
        "priority": 5,
    },
    {
        "id": "permission_nsis_ncrc",
        "signature": "permission_denied",
        "description": "NSIS installer permission failure — skip CRC check.",
        "env": {"WINEDEBUG": "-all"},
        "shims": [],
        "args": ["/NCRC"],
        "priority": 8,
        "installer_only": True,
    },
    {
        "id": "arch_wine32",
        "signature": "architecture_mismatch",
        "description": "PE/ELF arch mismatch — retry with 32-bit Wine prefix.",
        "env": {"WINEDEBUG": "-all"},
        "shims": ["win32_prefix"],
        "args": [],
        "priority": 4,
    },
]


def _baseline_remediation() -> Dict[str, Any]:
    return {
        "id": None,
        "signature": "*",
        "description": "Baseline attempt with plan defaults.",
        "env": {},
        "shims": [],
        "args": [],
        "priority": 100,
    }


# Ordered remediation ids for Electron launcher handoff (after baseline).
ELECTRON_LAUNCHER_REMEDIATION_IDS = [
    "ascension_int3_full_repair",
    "ascension_int3_guard_refresh",
    "electron_update_check_offline",
    "electron_disable_crashpad",
    "electron_launcher_guard_workaround",
    "electron_elevate_passthrough",
    "launcher_sidecar_vcrun",
    "network_workarounds",
]


def next_electron_launcher_remediation(
    tried_ids: set[Optional[str]],
    *,
    allow_container: bool = False,
) -> Optional[Dict[str, Any]]:
    for remediation_id in ELECTRON_LAUNCHER_REMEDIATION_IDS:
        if remediation_id in tried_ids:
            continue
        action = get_remediation_by_id(
            remediation_id,
            allow_container=allow_container,
            installer=False,
            electron=True,
        )
        if action:
            return action
    return None


def next_launcher_remediation(
    plan_signature: Optional[str],
    tried_ids: set[Optional[str]],
    *,
    allow_container: bool = False,
) -> Optional[Dict[str, Any]]:
    """Pick the next launcher remediation, preferring signature-specific fixes first."""
    if plan_signature:
        for action in remediations_for_signature(
            plan_signature,
            allow_container=allow_container,
            electron=True,
        ):
            remediation_id = action.get("id")
            if remediation_id in tried_ids:
                continue
            resolved = get_remediation_by_id(
                str(remediation_id),
                allow_container=allow_container,
                installer=False,
                electron=True,
            )
            if resolved:
                return resolved
    return next_electron_launcher_remediation(
        tried_ids,
        allow_container=allow_container,
    )


def get_remediation_by_id(
    remediation_id: str,
    *,
    allow_container: bool = True,
    installer: bool = False,
    electron: bool = False,
) -> Optional[Dict[str, Any]]:
    """Look up a remediation action by id, respecting runtime context filters."""
    for action in REMEDIATION_ACTIONS:
        if action.get("id") != remediation_id:
            continue
        if not allow_container and action.get("force_mode") == "container":
            continue
        if action.get("installer_only") and not installer:
            continue
        if action.get("electron_only") and not electron:
            continue
        return dict(action)
    return None


def remediations_for_signature(
    signature: Optional[str],
    *,
    allow_container: bool = True,
    installer: bool = False,
    electron: bool = False,
) -> List[Dict[str, Any]]:
    from alma_bridge.learning.remediation_learning import remediation_scores

    key = signature or "unknown_error"
    matches = [
        action
        for action in REMEDIATION_ACTIONS
        if action["signature"] in {key, "*"}
        and (allow_container or action.get("force_mode") != "container")
        and (installer or not action.get("installer_only"))
        and (electron or not action.get("electron_only"))
    ]
    specific = [action for action in matches if action["signature"] == key]
    pool = specific if specific else [action for action in matches if action["signature"] == "*"]
    if not pool:
        return [_baseline_remediation()]

    rates = remediation_scores(key)

    def _sort_key(action: Dict[str, Any]) -> tuple:
        learned = rates.get(action.get("id") or "", {}).get("rate", 0.5)
        priority = int(action.get("priority", 100))
        return (-learned, priority)

    return sorted(pool, key=_sort_key)


def apply_remediation(
    base_env: Dict[str, str],
    remediation: Dict[str, Any],
    base_args: Optional[List[str]] = None,
) -> Tuple[Dict[str, str], List[str]]:
    env = dict(base_env)
    env.update(remediation.get("env", {}))
    env.update(shim_env(remediation.get("shims", [])))
    if remediation.get("replace_args"):
        args = list(remediation.get("args", []))
    else:
        args = list(base_args or [])
        args.extend(remediation.get("args", []))
    return env, args
