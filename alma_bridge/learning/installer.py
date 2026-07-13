from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, List


INSTALLER_NAME_RE = re.compile(
    r"(setup|installer|install|bootstrap|update|mediacreationtool)",
    re.IGNORECASE,
)


def is_windows_installer(file_path: str) -> bool:
    path = Path(file_path)
    if path.suffix.lower() != ".exe":
        return False
    name = path.name.lower()
    if INSTALLER_NAME_RE.search(name):
        return True
    return "setup" in name or "installer" in name


def installer_launch_args(remediation_id: str | None) -> list[str]:
    if remediation_id == "nsis_ncrc":
        return ["/NCRC"]
    if remediation_id == "silent_install":
        return ["/S"]
    if remediation_id == "inno_silent":
        return ["/VERYSILENT", "/SUPPRESSMSGBOXES"]
    return []


def default_installer_args() -> list[str]:
    """NSIS installers commonly need /NCRC when run under Wine."""
    return ["/NCRC"]


ELECTRON_MARKERS = (
    "resources.pak",
    "snapshot_blob.bin",
    "v8_context_snapshot.bin",
    "libEGL.dll",
    "vk_swiftshader.dll",
)


def is_electron_app(file_path: str) -> bool:
    """Detect Electron apps by the sibling files an Electron bundle ships."""
    target = Path(file_path)
    if target.suffix.lower() != ".exe":
        return False
    folder = target.parent
    if not folder.exists():
        return False
    present = {entry.name.lower() for entry in folder.iterdir() if entry.is_file()}
    hits = sum(1 for marker in ELECTRON_MARKERS if marker.lower() in present)
    return hits >= 2


def electron_software_gl_args() -> list[str]:
    """GPU + crash-reporter flags for Electron apps under Wine.

    Under Wine every Chromium GPU backend fails to create the "shared context
    for virtualization" and crash-loops, leaving the window stuck at 1x1.
    Crashpad also fails to attach (CreateFile / crash server failed) and Electron
    self-terminates — disable it alongside the GPU process.
    """
    return [
        "--disable-gpu",
        "--no-sandbox",
        "--disable-crash-reporter",
        "--disable-breakpad",
        "--disable-features=CrashReporting",
    ]


# Back-compat alias; both names return the same (correct) disable-gpu flags.
def electron_disable_gpu_args() -> list[str]:
    """Stable Electron-under-Wine launch flags (GPU off + no Crashpad)."""
    return electron_software_gl_args()


def electron_launch_env() -> dict[str, str]:
    """Environment overrides common for Electron-on-Wine launches."""
    return {
        "ELECTRON_DISABLE_CRASH_REPORTER": "1",
        "WINEDEBUG": "-all",
    }


ASCENSION_SKIP_UPDATE_ARGS = ["--no-update", "--skip-update"]


def apply_electron_launch_overrides(
    env: Dict[str, str],
    launch_args: List[str],
) -> None:
    """Apply env-driven Electron launch tweaks (e.g. skip auto-updater under Wine)."""
    if env.pop("ALMA_SKIP_ELECTRON_UPDATE", None):
        for arg in ASCENSION_SKIP_UPDATE_ARGS:
            if arg not in launch_args:
                launch_args.append(arg)


def is_electron_builder_elevate(file_path: str) -> bool:
    """True if the Electron bundle ships electron-builder's elevate.exe.

    That helper elevates child processes with the Windows "runas" UAC verb,
    which Wine cannot grant, so the elevated child dies instantly. Alma replaces
    it with a CreateProcess passthrough (tools/elevate_passthrough.c).
    """
    folder = Path(file_path).parent
    candidates = (
        folder / "resources" / "elevate.exe",
        folder / "elevate.exe",
    )
    return any(c.exists() for c in candidates)


def electron_resources_dir(file_path: str) -> Path | None:
    """Locate the Electron app's resources/ dir (where elevate.exe / sidecars live)."""
    folder = Path(file_path).parent
    for cand in (folder / "resources", folder):
        if (cand / "elevate.exe").exists() or (cand / "app.asar").exists():
            return cand
    return None


def fresh_prefix_path(session_id: str) -> str:
    """Wine refuses some /tmp prefixes — keep prefixes under the user home."""
    base = Path.home() / ".local/share/alma-bridge/prefixes"
    path = base / session_id[:12]
    path.mkdir(parents=True, exist_ok=True)
    return str(path)
