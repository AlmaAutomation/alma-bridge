"""Automatic Electron-on-Wine remediation.

Encodes everything Alma learned about running Electron launchers (e.g. the
Ascension Launcher) under Wine, so the closed loop can apply it without any
manual scripts:

  * GPU: launch with ``--disable-gpu --no-sandbox`` (every Chromium GPU backend
    crash-loops under Wine -- see installer.electron_software_gl_args).
  * Elevation: electron-builder's ``elevate.exe`` uses the Windows "runas" UAC
    verb, which Wine cannot grant, so the elevated child dies. Replace it with a
    CreateProcess passthrough (tools/elevate_passthrough.c).
  * launcher_guard: the elevated sidecar (e.g. AscensionClientServices.exe)
    shuts itself down because, under Wine, its 1s launcher-PID liveness check
    misreports the live launcher as exited. Wrap the sidecar so the guard
    watches a correctly-named, always-alive decoy (tools/cs_wrapper.c).

Everything degrades gracefully: if the mingw cross-compiler is missing, or the
target files are absent, the helpers report what they could not do instead of
raising.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from alma_bridge.learning.installer import electron_resources_dir

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOOLS_SRC = _REPO_ROOT / "tools"
_BUILD_DIR = Path.home() / ".local/share/alma-bridge/tools"

# Sidecars that ship a launcher_guard and need the wrapper. Heuristic on name.
_SIDECAR_RE = re.compile(r"(clientservices|client.?services|agent|sidecar|helper|service)\.exe$", re.I)
_SKIP_EXE_RE = re.compile(r"(elevate|crashpad|setup|uninstall|update)\.exe$", re.I)


def mingw_compiler() -> Optional[str]:
    """Return the mingw-w64 cross-compiler path, or None if unavailable."""
    return shutil.which("x86_64-w64-mingw32-gcc")


def _build_tool(src_name: str, out_name: str) -> Optional[Path]:
    """Compile a tools/*.c source into a Windows .exe. Returns the path or None."""
    cc = mingw_compiler()
    src = _TOOLS_SRC / src_name
    if not cc or not src.exists():
        return None
    _BUILD_DIR.mkdir(parents=True, exist_ok=True)
    out = _BUILD_DIR / out_name
    try:
        proc = subprocess.run(
            [cc, "-municode", "-O2", "-s", "-o", str(out), str(src)],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0 or not out.exists():
        return None
    return out


def install_elevate_passthrough(resources: Path) -> Dict[str, object]:
    """Swap electron-builder's elevate.exe for a CreateProcess passthrough."""
    elevate = resources / "elevate.exe"
    if not elevate.exists():
        return {"action": "elevate_passthrough", "status": "skipped", "reason": "no elevate.exe"}
    built = _build_tool("elevate_passthrough.c", "elevate.exe")
    if not built:
        return {
            "action": "elevate_passthrough",
            "status": "unavailable",
            "reason": "mingw-w64 cross-compiler not installed (apt install gcc-mingw-w64-x86-64)",
        }
    backup = resources / "elevate.exe.orig"
    if not backup.exists():
        shutil.copy2(elevate, backup)
    shutil.copy2(built, elevate)
    return {"action": "elevate_passthrough", "status": "installed", "path": str(elevate)}


def find_sidecars(resources: Path) -> List[Path]:
    """Sidecar .exes that likely run a launcher_guard."""
    out: List[Path] = []
    if not resources.exists():
        return out
    for entry in resources.iterdir():
        if not entry.is_file() or entry.suffix.lower() != ".exe":
            continue
        if _SKIP_EXE_RE.search(entry.name):
            continue
        if _SIDECAR_RE.search(entry.name):
            out.append(entry)
    return out


def install_launcher_decoy(resources: Path, launcher_name: str) -> Dict[str, object]:
    """Install a correctly-named sleeper the guard can watch instead of the launcher."""
    guard_dir = resources / "alma-guard"
    guard_dir.mkdir(parents=True, exist_ok=True)
    decoy_path = guard_dir / launcher_name
    built = _build_tool("launcher_decoy.c", "launcher_decoy.exe")
    if not built:
        return {
            "action": "launcher_decoy",
            "status": "unavailable",
            "reason": "mingw-w64 cross-compiler not installed (apt install gcc-mingw-w64-x86-64)",
        }
    shutil.copy2(built, decoy_path)
    return {
        "action": "launcher_decoy",
        "status": "installed",
        "path": str(decoy_path),
    }


def install_cs_guard_wrapper(resources: Path) -> List[Dict[str, object]]:
    """Wrap launcher-guard sidecars so the guard watches a stable decoy."""
    results: List[Dict[str, object]] = []
    sidecars = find_sidecars(resources)
    if not sidecars:
        return [{"action": "cs_guard_wrapper", "status": "skipped", "reason": "no sidecar found"}]
    built = _build_tool("cs_wrapper.c", "cs_wrapper.exe")
    if not built:
        return [{
            "action": "cs_guard_wrapper",
            "status": "unavailable",
            "reason": "mingw-w64 cross-compiler not installed (apt install gcc-mingw-w64-x86-64)",
        }]
    # Sanity: refuse to install an ancient wrapper missing the decoy logic.
    try:
        blob = built.read_bytes()
    except OSError:
        blob = b""
    if b"alma-cs-wrapper-decoy-v1" not in blob:
        return [{
            "action": "cs_guard_wrapper",
            "status": "failed",
            "reason": "built cs_wrapper.exe is missing decoy support (rebuild failed?)",
        }]
    for sidecar in sidecars:
        real = sidecar.with_name(sidecar.stem + ".real.exe")
        if not real.exists():
            if sidecar.exists():
                shutil.move(str(sidecar), str(real))
        shutil.copy2(built, sidecar)
        results.append({"action": "cs_guard_wrapper", "status": "installed", "sidecar": str(sidecar)})
    return results


def launcher_exe_name(app_file: str, resources: Path) -> str:
    """Best guess at the launcher exe basename (for the guard's name check)."""
    app = Path(app_file)
    if app.suffix.lower() == ".exe" and "setup" not in app.name.lower():
        return app.name
    # The launcher exe is the parent dir's main .exe next to resources/.
    parent = resources.parent
    candidates = [
        e for e in parent.glob("*.exe")
        if e.is_file() and not _SKIP_EXE_RE.search(e.name)
    ]
    if candidates:
        return max(candidates, key=lambda e: e.stat().st_size).name
    return "Ascension Launcher.exe"


def _wine_prefix_from_app_file(app_file: str) -> Optional[str]:
    path = Path(app_file).expanduser()
    for parent in path.parents:
        if parent.name == "drive_c":
            return str(parent.parent)
    return None


def prepare_electron_wine(app_file: str) -> Dict[str, object]:
    """Build+install the Electron-on-Wine workarounds for the given app.

    Idempotent and safe to call on every run: re-installs the passthrough/wrapper
    (the original binaries are preserved as .orig/.real.exe on first install).
    """
    resources = electron_resources_dir(app_file)
    report: Dict[str, object] = {
        "mingw": bool(mingw_compiler()),
        "resources": str(resources) if resources else None,
        "actions": [],
        "launcher_exe_name": None,
    }
    if not resources:
        report["actions"].append({"status": "skipped", "reason": "no Electron resources dir"})
        return report
    if "ascension" in app_file.lower():
        from alma_bridge.compatibility.ascension_layout import quarantine_stale_ascension_flat_layout

        wine_prefix = _wine_prefix_from_app_file(app_file)
        if wine_prefix:
            report["actions"].append(
                quarantine_stale_ascension_flat_layout(wine_prefix, app_file)
            )
    name = launcher_exe_name(app_file, resources)
    report["launcher_exe_name"] = name
    report["actions"].append(install_elevate_passthrough(resources))
    report["actions"].append(install_launcher_decoy(resources, name))
    report["actions"].extend(install_cs_guard_wrapper(resources))
    return report


def apply_electron_remediation_shims(
    remediation: Dict[str, Any],
    env: Dict[str, str],
    *,
    app_file: str,
) -> Dict[str, object]:
    """Install Electron-on-Wine wrappers when a remediation requests compat shims."""
    shims = set(remediation.get("shims") or [])
    if (
        "electron_launcher_guard_workaround" in shims
        or "electron_elevate_passthrough" in shims
        or env.pop("ALMA_INSTALL_CS_GUARD_WORKAROUND", None)
        or env.pop("ALMA_INSTALL_ELEVATE_PASSTHROUGH", None)
    ):
        return prepare_electron_wine(app_file)
    return {}
