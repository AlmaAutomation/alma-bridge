from __future__ import annotations

from enum import Enum
from typing import List, Optional, Tuple


# NOTE: detect_error_signature returns the FIRST matching signature, so the more
# specific Electron / Wine signatures MUST come before the broad ones (gpu_crash,
# file_not_found, missing_dependency), otherwise a generic substring like "d3d"
# would shadow the precise classification.
SIGNATURE_PATTERNS = {
    "sudo_password_required": [
        "sudo: a password is required",
        "a terminal is required to read the password",
        "no tty present",
    ],
    # --- Specific Electron-on-Wine signatures (checked first) ---
    "electron_gpu_crash": [
        "failed to create shared context for virtualization",
        "dcompositioncreatedevice3 failed",
        "contextresult::kfatalfailure",
        "sharedimagemanager",
        "gpu_channel_manager",
        "gl_factory_win.cc",
    ],
    "launcher_guard_shutdown": [
        "launcher exited, shutting down",
        "launcher_guard",
        "launcher pid does not belong to the launcher",
    ],
    "winsock_update_hang": [
        "alma:update_check_timeout",
    ],
    "electron_crashpad_failure": [
        "crash server failed to launch, self-terminating",
        "crashpad_client_win.cc",
        "registration_protocol_win.cc",
        "crash server failed to launch",
    ],
    "wine_int3_crash": [
        ": int3",
        " int3",
        "program error",
        "unhandled exception",
        "wine debugger",
        "dbghelp",
        "ascension launcher+",
    ],
    "sidecar_silent_crash": [
        "sidecar .real.exe was invoked but produced no output",
        "[alma] sidecar watchdog: sidecar .real.exe was invoked",
    ],
    "invalid_launch_args": [
        "bad option:",
        "unknown option",
        "unrecognized option",
    ],
    "execution_timeout": [
        "execution timed out",
    ],
    "elevation_failed": [
        "elevation failed",
        "elevation_declined",
        "isadminrightsrequired",
        "is set to true, run installer using elevate.exe",
    ],
    "windows_version_required": [
        "windows 7 and above is required",
        "windows 7 or later",
        "requires windows 7",
        "requires windows 10",
        "requires windows 11",
        "minimum version of windows",
        "not supported on this version of windows",
        "this program requires windows",
    ],
    "nsis_installer_failure": [
        "nsis error",
        "installer integrity check has failed",
    ],
    "missing_dll": [
        "dll not found",
        "failed to load dll",
        "import_dll",
        "msvcp",
        "vcruntime",
    ],
    "missing_visual_c_runtime": [
        "vcruntime",
        "msvcp140",
        "visual c++",
    ],
    "dotnet_missing": [
        "mscoree",
        ".net framework",
        "dotnet",
        "clr",
        "application could not be started",
        "application-not-started",
        "processname=rundll32.exe",
        "rundll32.exe - this application",
        "learn.microsoft.com/en-us/dotnet/framework/install/application-not-started",
    ],
    "java_missing": [
        "could not find java",
        "java virtual machine",
        "jvm.dll",
        "no jre",
        "no jdk",
        "failed to load jvm",
    ],
    "opengl_legacy": [
        "wglcreatecontext",
        "opengl32",
        "invalid pixel format",
        "glx",
        "mesa",
        "wined3d",
    ],
    "directx_old": [
        "d3d9",
        "d3d11",
        "direct3d",
        "dxgi",
        "dinput",
        "xinput",
    ],
    "wine_shell_error": [
        "shgetfileinfo",
        "pidl is null",
    ],
    "proton_unavailable": [
        "proton: no compat data path",
        "no compat data path",
    ],
    "architecture_mismatch": [
        "bad exe format",
        "wrong elf class",
        "exec format error",
        "cannot execute binary file",
    ],
    "permission_denied": [
        "permission denied",
        "access denied",
    ],
    "wine_prefix_problem": [
        "wineprefix",
        "wine prefix",
        "wine configuration",
    ],
    "file_not_found": [
        "file not found",
        "failed to open",
        "c0000135",
    ],
    # --- Broad fallbacks (checked last) ---
    "gpu_crash": [
        "vulkan",
        "dxvk",
        "opengl",
        "glx",
        "d3d",
        "render",
    ],
    "display_crash": [
        "x11",
        "wayland",
        "fullscreen",
        "virtual desktop",
    ],
    "audio_failure": [
        "alsa",
        "pulseaudio",
        "audio",
        "sound",
    ],
    "missing_dependency": [
        "no such file or directory",
        "cannot open shared object file",
        "error while loading shared libraries",
    ],
}


RECOMMENDED_ACTIONS = {
    "sudo_password_required": [
        "Enter your sudo password in the Bridge UI (Use sudo → password field), or run `sudo -v` in a terminal first.",
        "Wine/Proton do not need sudo — leave 'Use sudo' off unless using container sandbox.",
        "Or configure passwordless sudo (NOPASSWD) for Docker in /etc/sudoers.",
    ],
    "missing_dll": [
        "Install missing DLLs with winetricks in the active WINEPREFIX.",
        "Retry with a clean 32-bit or 64-bit prefix matching the installer.",
    ],
    "missing_visual_c_runtime": [
        "Run: winetricks vcrun2019 vcrun2022",
    ],
    "nsis_installer_failure": [
        "Retry with NSIS /NCRC flag to skip integrity check.",
        "Redownload the installer if the file may be corrupt.",
    ],
    "windows_version_required": [
        "Wine is reporting an old Windows version to the installer — set the prefix to Windows 10.",
        "Bridge will retry with ALMA_WINE_WINDOWS_VERSION=win10 on the active WINEPREFIX.",
    ],
    "installer_aborted": [
        "The installer exited almost immediately with no install progress — often a dismissed error dialog.",
        "Check Wine's reported Windows version (winecfg → Windows version) and retry with win10.",
    ],
    "installer_not_verified": [
        "The installer process exited cleanly but nothing was installed into the Wine prefix.",
        "Bridge will retry with bootstrap (win10 + VC++ + .NET) and silent install flags.",
    ],
    "dotnet_missing": [
        "Bridge installs VC++ and .NET 4.8 in the Wine prefix automatically before launch.",
        "If a browser opened to learn.microsoft.com about .NET during winetricks, that is Wine noise from rundll32 — close the tab and let Bridge continue.",
        "Manual fallback: winetricks -q vcrun2019 vcrun2022 dotnet48 in the active WINEPREFIX.",
    ],
    "java_missing": [
        "Install a Windows JRE/JDK into the WINEPREFIX or use winetricks java8.",
        "Some launchers bundle their own JVM — retry with a fresh prefix.",
    ],
    "opengl_legacy": [
        "Retry with WineD3D/DXVK disabled and software rendering.",
        "Legacy OpenGL titles often need a 32-bit Wine prefix.",
    ],
    "directx_old": [
        "Install d3dx9/d3dcompiler via winetricks for older DirectX titles.",
        "Retry with DXVK disabled if the game predates D3D11.",
    ],
    "wine_prefix_problem": [
        "Create a fresh WINEPREFIX and retry.",
    ],
    "gpu_crash": [
        "Retry with software rendering and DXVK disabled.",
    ],
    "display_crash": [
        "Retry inside a Wine virtual desktop.",
    ],
    "proton_unavailable": [
        "Proton needs STEAM_COMPAT_DATA_PATH — Bridge will configure this automatically on retry.",
        "For NSIS installers, system Wine with /NCRC is usually more reliable than Proton.",
    ],
    "wine_shell_error": [
        "Retry with NSIS /NCRC and a Wine virtual desktop.",
        "Launch via: wine explorer /desktop=Alma,1280x720 setup.exe /NCRC",
    ],
    "permission_denied": [
        "Retry with a fresh WINEPREFIX — the active prefix may have bad permissions.",
        "For installers, try /NCRC or silent flags (/S, /VERYSILENT).",
        "Ensure the binary is not being run with the wrong strategy (PE needs Wine, not native).",
    ],
    "electron_gpu_crash": [
        "Electron GPU process crashed under Wine; the window will stay stuck at 1x1.",
        "Retry with the GPU process disabled: --disable-gpu --no-sandbox (the only stable option under Wine).",
        "Do NOT pass --use-gl/--use-angle: D3D11, ANGLE-GL and SwiftShader all crash-loop under Wine.",
        "Matches official Project Ascension guidance (add --disable-gpu to the launcher).",
    ],
    "launcher_guard_shutdown": [
        "The app's elevated sidecar shut down because its launcher_guard wrongly thinks the launcher exited (Wine misreports the live launcher PID after ~1s).",
        "Bridge wraps the sidecar so the guard watches a correctly-named, reliably-alive decoy process.",
        "Alternatively use a Wine build where the guard works (e.g. wine-ge-proton8-26).",
    ],
    "winsock_update_hang": [
        "Wine's winsock change-notifier (WSALookupServiceBegin failed: 8) stalled the Electron auto-updater at 'Checking for update'.",
        "Bridge retries skipping the in-app update check so the launcher proceeds.",
    ],
    "electron_crashpad_failure": [
        "Electron's Crashpad handler cannot start under Wine (CreateFile / crash server failed) and the app self-terminates.",
        "Bridge retries with --disable-crash-reporter and --disable-breakpad.",
    ],
    "wine_int3_crash": [
        "Wine hit an int3 breakpoint in the Electron launcher — common for Ascension/Chromium under Wine.",
        "Bridge reinstalls Electron-on-Wine wrappers (sidecar guard + elevate passthrough), bootstraps VC++/.NET, and disables GPU via Wine env (not CLI flags).",
        "Requires gcc-mingw-w64-x86-64 for wrapper builds: sudo apt install gcc-mingw-w64-x86-64",
    ],
    "client_services_stalled": [
        "The Electron launcher started its elevated sidecar but exited before the UI came up.",
        "Bridge retries with sidecar guard refresh, update-check skip, VC++/dotnet bootstrap.",
        "If a browser opened to learn.microsoft.com about .NET during winetricks, that is Wine noise from rundll32 — close the tab and let Bridge continue.",
    ],
    "sidecar_silent_crash": [
        "The elevated sidecar binary started under Wine but wrote nothing to alma-cs-output.log — it likely crashed immediately.",
        "Bridge refreshes the sidecar guard wrapper and bootstraps VC++/dotnet, then retries.",
        "If this repeats, try Wine-GE/Proton or run AscensionClientServices.real.exe manually under Wine to capture the crash.",
    ],
    "invalid_launch_args": [
        "The launcher wrapper rejected Chromium-style flags (--disable-gpu, etc.).",
        "Bridge retries with no extra CLI flags — GPU/sidecar fixes apply via Wine env and shims instead.",
    ],
    "execution_timeout": [
        "The launcher was still running when the old watchdog killed it — Bridge now detaches once the process survives bootstrap.",
        "Check your desktop for the Ascension window; if it is open, the run actually succeeded.",
    ],
    "elevation_failed": [
        "App tried to elevate (UAC) which Wine cannot grant. Wine already runs as admin.",
        "Bridge installs a CreateProcess passthrough over elevate.exe so elevated children start.",
    ],
    "unknown_error": [
        "Inspect stderr output below for the real failure.",
        "Try a fresh Wine prefix with winetricks vcrun2019 dotnet48.",
        "For NSIS installers, retry with /NCRC.",
    ],
}


# Signatures that mean failure even when the child process exits 0 (e.g. user
# clicks OK on a version-requirement MessageBox and the installer quits cleanly).
HARD_FAIL_SIGNATURES = frozenset(
    {
        "windows_version_required",
        "electron_crashpad_failure",
        "nsis_installer_failure",
        "elevation_failed",
        "architecture_mismatch",
        "permission_denied",
    }
)

# Retry termination scope per error signature. Signatures omitted from this map
# continue with the next remediation attempt (ATTEMPT scope).
class RetryScope(str, Enum):
    ATTEMPT = "attempt"
    STRATEGY = "strategy"
    SESSION = "session"


ERROR_RETRY_POLICIES: dict[str, RetryScope] = {
    "single_instance_detected": RetryScope.SESSION,
    "architecture_mismatch": RetryScope.SESSION,
    "invalid_launch_args": RetryScope.SESSION,
}


def retry_scope_for_signature(signature: Optional[str]) -> Optional[RetryScope]:
    if not signature:
        return None
    return ERROR_RETRY_POLICIES.get(signature)


NON_RETRYABLE_SIGNATURES = frozenset(
    signature
    for signature, scope in ERROR_RETRY_POLICIES.items()
    if scope == RetryScope.SESSION
)

INSTALLER_PROGRESS_MARKERS = (
    "installing",
    "extracting",
    "copying",
    "creating ",
    "uninst",
    "success",
    "complete",
    "finished",
    "setup was",
)

OLD_WINE_WINDOWS_VERSIONS = frozenset(
    {"win98", "winme", "winxp", "win2003", "winvista", "win2008"}
)


def detect_installer_false_success(
    stderr: str,
    stdout: str,
    *,
    duration_ms: int,
    exit_code: int,
    wine_windows_version: str | None = None,
) -> str | None:
    """Detect GUI installers that exited cleanly but never actually installed."""
    combined = f"{stderr or ''}\n{stdout or ''}".lower()
    signature = detect_error_signature(stderr, stdout)
    if signature in HARD_FAIL_SIGNATURES:
        return signature
    if exit_code != 0:
        return None
    if duration_ms > 180_000:
        return None
    if any(marker in combined for marker in INSTALLER_PROGRESS_MARKERS):
        return None
    if wine_windows_version and wine_windows_version.lower() in OLD_WINE_WINDOWS_VERSIONS:
        return "windows_version_required"
    if duration_ms < 120_000:
        return "installer_aborted"
    return None


def launch_failure_in_log(stderr: str, stdout: str = "") -> Optional[str]:
    """Return a failure signature when launch logs show a hard error dialog."""
    combined = f"{stderr or ''}\n{stdout or ''}"
    lower = combined.lower()
    if "application could not be started" in lower and "rundll32" in lower:
        return "dotnet_missing"
    sig = detect_error_signature(stderr, stdout)
    if sig in {
        "dotnet_missing",
        "missing_dll",
        "missing_visual_c_runtime",
        "invalid_launch_args",
        "electron_crashpad_failure",
        "windows_version_required",
        "wine_int3_crash",
    }:
        return sig
    if ": int3" in lower or " int3" in lower:
        return "wine_int3_crash"
    return None


def detect_error_signature(stderr: str, stdout: str) -> str:
    combined = f"{stderr or ''}\n{stdout or ''}".lower()
    for signature, patterns in SIGNATURE_PATTERNS.items():
        if any(pattern in combined for pattern in patterns):
            return signature
    return "unknown_error"


def classify_execution_error(stderr: str, stdout: str) -> Tuple[str, List[str]]:
    signature = detect_error_signature(stderr, stdout)
    return signature, list(RECOMMENDED_ACTIONS.get(signature, RECOMMENDED_ACTIONS["unknown_error"]))


BENIGN_WINE_INSTALLER_MARKERS = (
    "err:ole:",
    "err:menubuilder:",
    "err:combase:",
    "err:d3d:wined3d",
    "has been updated.",
)


def is_benign_wine_installer_stderr(stderr: str) -> bool:
    """OLE/COM and D3D warnings are common during successful GUI installers under Wine."""
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    if not lines:
        return True
    return all(
        any(marker in line.lower() for marker in BENIGN_WINE_INSTALLER_MARKERS)
        for line in lines
    )


def format_wine_log_for_display(stderr: str, *, success: bool) -> str:
    if not stderr:
        return ""
    if success and is_benign_wine_installer_stderr(stderr):
        line_count = len(stderr.splitlines())
        preview = "\n".join(stderr.splitlines()[:6])
        suffix = "\n..." if line_count > 6 else ""
        return (
            "Installer finished successfully. The messages below are normal Wine noise "
            "(Windows COM/RpcSs, menu icons, D3D) — not a failed install.\n\n"
            f"{preview}{suffix}"
        )
    return stderr


def suggest_fix(signature: str | None, stderr: str = "", stdout: str = "") -> str:
    actions = RECOMMENDED_ACTIONS.get(signature or "unknown_error", RECOMMENDED_ACTIONS["unknown_error"])
    headline = actions[0] if actions else "Review execution logs."
    detail = (stderr or stdout or "").strip().splitlines()
    if detail:
        return f"{headline} Detail: {detail[0][:240]}"
    return headline
