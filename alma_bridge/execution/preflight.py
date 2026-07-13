from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def winetricks_available() -> bool:
    return shutil.which("winetricks") is not None


_OLD_WINE_VERSIONS = frozenset({
    "win98",
    "winme",
    "winxp",
    "win2003",
    "winvista",
    "win2008",
    "win7",
    "win2008r2",
})

_WINE_VERSION_RANK = {
    None: 0,
    "win98": 1,
    "winme": 2,
    "winxp": 3,
    "win2003": 4,
    "winvista": 5,
    "win2008": 6,
    "win7": 7,
    "win2008r2": 8,
    "win8": 9,
    "win2012": 10,
    "win81": 11,
    "win2012r2": 12,
    "win10": 13,
    "win2016": 13,
    "win2019": 14,
    "win11": 15,
}


def wine_windows_version_insufficient(
    current: Optional[str],
    minimum: str = "win10",
) -> bool:
    """True when Wine would report an older Windows version than required."""
    return _WINE_VERSION_RANK.get(current, 0) < _WINE_VERSION_RANK.get(minimum, 13)


def read_wine_windows_version(wine_prefix: str) -> Optional[str]:
    """Read Wine's reported Windows version from user.reg (e.g. win10)."""
    if not wine_prefix:
        return None
    user_reg = Path(wine_prefix).expanduser() / "user.reg"
    if not user_reg.is_file():
        return None
    try:
        text = user_reg.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    match = re.search(r'"Version"\s*=\s*"(win[^"]+)"', text)
    if match:
        return match.group(1)

    system_reg = Path(wine_prefix).expanduser() / "system.reg"
    if system_reg.is_file():
        try:
            text = system_reg.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
        match = re.search(r'"Version"\s*=\s*"(win[^"]+)"', text)
        if match:
            return match.group(1)
    return None


def _patch_user_reg_windows_version(wine_prefix: str, version: str) -> tuple[bool, str]:
    """Write HKCU\\Software\\Wine\\Version directly into user.reg (fast, reliable)."""
    user_reg = Path(wine_prefix).expanduser() / "user.reg"
    if not user_reg.is_file():
        return False, "user.reg missing"
    try:
        text = user_reg.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return False, str(exc)

    version_line = f'"Version"="{version}"'
    if re.search(r'"Version"\s*=', text):
        new_text = re.sub(
            r'"Version"\s*=\s*"(win[^"]*)"',
            version_line,
            text,
            count=1,
        )
    elif re.search(r"\[Software\\\\Wine\]", text):
        new_text = re.sub(
            r"(\[Software\\\\Wine\][^\n]*\n)",
            rf"\1{version_line}\n",
            text,
            count=1,
        )
    else:
        stamp = int(time.time())
        new_text = (
            text.rstrip()
            + f"\n\n[Software\\\\Wine] {stamp}\n#time {stamp:016x}\n{version_line}\n"
        )

    try:
        user_reg.write_text(new_text, encoding="utf-8")
    except OSError as exc:
        return False, str(exc)
    return True, "patched user.reg"


def _wine_prefix_env(wine_prefix: str) -> Dict[str, str]:
    env = os.environ.copy()
    env["WINEPREFIX"] = str(Path(wine_prefix).expanduser())
    env.setdefault("WINEDEBUG", "-all")
    return env


def _kill_wineserver(wine_prefix: str) -> None:
    wineserver = shutil.which("wineserver")
    if not wineserver:
        return
    try:
        subprocess.run(
            [wineserver, "-k"],
            capture_output=True,
            text=True,
            env=_wine_prefix_env(wine_prefix),
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def query_wine_windows_version_live(
    wine_prefix: str,
    *,
    timeout_sec: int = 30,
) -> Optional[str]:
    """Read Version from the live Wine registry (what running processes actually see)."""
    wine = shutil.which("wine") or shutil.which("wine64")
    if not wine or not wine_prefix:
        return None
    try:
        proc = subprocess.run(
            [wine, "reg", "query", r"HKCU\Software\Wine", "/v", "Version"],
            capture_output=True,
            text=True,
            env=_wine_prefix_env(wine_prefix),
            timeout=timeout_sec,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    output = (proc.stdout or "") + (proc.stderr or "")
    match = re.search(r"Version\s+REG_SZ\s+(win\S+)", output)
    if match:
        return match.group(1).strip()
    return None


def _wine_reg_set_version(
    wine_prefix: str,
    version: str,
    *,
    timeout_sec: int = 180,
) -> tuple[bool, str]:
    wine = shutil.which("wine") or shutil.which("wine64")
    if not wine:
        return False, "wine not found"
    try:
        proc = subprocess.run(
            [
                wine,
                "reg",
                "add",
                r"HKCU\Software\Wine",
                "/v",
                "Version",
                "/t",
                "REG_SZ",
                "/d",
                version,
                "/f",
            ],
            capture_output=True,
            text=True,
            env=_wine_prefix_env(wine_prefix),
            timeout=timeout_sec,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return False, "wine reg add timed out"
    except OSError as exc:
        return False, str(exc)
    output = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, output[-1000:]


def _restart_wine_prefix(wine_prefix: str, *, timeout_sec: int = 120) -> tuple[bool, str]:
    """Restart wineserver so registry changes (e.g. Version) take effect."""
    wine = shutil.which("wine") or shutil.which("wine64")
    if not wine:
        return False, "wine not found"
    _kill_wineserver(wine_prefix)
    return wineboot_update(wine_prefix, timeout_sec=timeout_sec)


def set_wine_windows_version(
    wine_prefix: str,
    version: str = "win10",
    *,
    timeout_sec: int = 180,
) -> tuple[bool, str]:
    """Set Wine's reported Windows version for a prefix (installer compatibility)."""
    if not wine_prefix:
        return False, "no WINEPREFIX"

    messages: List[str] = []

    # Live registry first — wineserver -k saves in-memory state to user.reg.
    # Never patch user.reg then kill: that overwrites the patch with XP memory.
    reg_ok, reg_msg = _wine_reg_set_version(wine_prefix, version, timeout_sec=timeout_sec)
    messages.append(reg_msg)
    live = query_wine_windows_version_live(wine_prefix)
    if live == version:
        _kill_wineserver(wine_prefix)
        if read_wine_windows_version(wine_prefix) == version:
            return True, f"live registry set to {version}"
        boot_ok, boot_msg = wineboot_update(wine_prefix, timeout_sec=timeout_sec)
        messages.append(boot_msg)
        if read_wine_windows_version(wine_prefix) == version:
            return True, "; ".join(messages)[-2000:]

    # Fallback: stop wineserver, patch user.reg on disk, boot fresh.
    _kill_wineserver(wine_prefix)
    patch_ok, patch_msg = _patch_user_reg_windows_version(wine_prefix, version)
    messages.append(patch_msg)
    boot_ok, boot_msg = wineboot_update(wine_prefix, timeout_sec=timeout_sec)
    messages.append(boot_msg)

    live = query_wine_windows_version_live(wine_prefix)
    on_disk = read_wine_windows_version(wine_prefix)
    if live == version or on_disk == version:
        return True, f"confirmed {live or on_disk}"
    return False, f"version still live={live!r} disk={on_disk!r}; " + "; ".join(messages)[-1500:]


def ensure_wine_windows_version(
    wine_prefix: str,
    *,
    minimum: str = "win10",
) -> tuple[bool, str]:
    """Bump an old prefix to at least `minimum` before running Windows installers."""
    current = read_wine_windows_version(wine_prefix)
    if current == minimum:
        return True, f"already {minimum}"
    if current and not wine_windows_version_insufficient(current, minimum):
        return True, f"keeping {current}"
    # Unset Version defaults to Windows XP in Wine — always bump.
    return set_wine_windows_version(wine_prefix, minimum)


def require_wine_windows_version(
    wine_prefix: str,
    *,
    minimum: str = "win10",
) -> tuple[bool, str]:
    """Ensure and verify Wine reports at least `minimum` before launch."""
    ok, msg = ensure_wine_windows_version(wine_prefix, minimum=minimum)
    if not ok:
        return False, msg
    live = query_wine_windows_version_live(wine_prefix)
    on_disk = read_wine_windows_version(wine_prefix)
    current = live or on_disk
    if wine_windows_version_insufficient(current, minimum):
        return False, f"prefix still reports {current or 'unset'} (needs {minimum})"
    return True, f"confirmed {current} (live={live}, disk={on_disk})"


def _wine_prefix_from_environ(environ_text: str) -> Optional[str]:
    for line in environ_text.split("\0"):
        if line.startswith("WINEPREFIX="):
            return line.split("=", 1)[1]
    return None


def prefix_vcrun_installed(wine_prefix: str) -> bool:
    """True when common VC++ 2015+ runtime DLLs exist in the prefix."""
    if not wine_prefix:
        return False
    root = Path(wine_prefix).expanduser()
    for rel in (
        "drive_c/windows/system32/msvcp140.dll",
        "drive_c/windows/system32/vcruntime140.dll",
    ):
        if not (root / rel).is_file():
            return False
    return True


def prefix_dotnet_installed(wine_prefix: str) -> bool:
    """True when .NET Framework 4.x appears installed in a Wine prefix."""
    if not wine_prefix:
        return False
    root = Path(wine_prefix).expanduser()
    for rel in (
        "drive_c/windows/Microsoft.NET",
        "drive_c/windows/Microsoft.NET Framework",
    ):
        dotnet_dir = root / rel
        if dotnet_dir.is_dir() and any(dotnet_dir.iterdir()):
            return True

    for reg_name in ("user.reg", "system.reg"):
        reg_path = root / reg_name
        if not reg_path.is_file():
            continue
        try:
            text = reg_path.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        if "dotnetframework" in text and re.search(r"v4\.[0-9]", text):
            return True
        if "net framework setup\\ndp\\v4" in text:
            return True
    return False


def prefix_dotnet_functional(wine_prefix: str) -> bool:
    """Stricter .NET check — files + CLR shim present (rundll32-safe)."""
    if not prefix_dotnet_installed(wine_prefix):
        return False
    root = Path(wine_prefix).expanduser()
    for rel in (
        "drive_c/windows/system32/mscoree.dll",
        "drive_c/windows/Microsoft.NET/Framework/v4.0.30319/clr.dll",
    ):
        if not (root / rel).is_file():
            return False

    for reg_name in ("system.reg", "user.reg"):
        reg_path = root / reg_name
        if not reg_path.is_file():
            continue
        try:
            text = reg_path.read_text(encoding="utf-8", errors="replace").lower()
        except OSError:
            continue
        if "net framework setup\\ndp\\v4\\full" in text and "install" in text:
            return True
        if "dotnetframework\\v4.0.30319" in text:
            return True
    return True


def prefix_runtimes_ready(wine_prefix: str) -> bool:
    return prefix_vcrun_installed(wine_prefix) and prefix_dotnet_installed(wine_prefix)


def prefix_runtimes_functional(wine_prefix: str) -> bool:
    return prefix_vcrun_installed(wine_prefix) and prefix_dotnet_functional(wine_prefix)


def wineboot_update(wine_prefix: str, *, timeout_sec: int = 120) -> tuple[bool, str]:
    """Refresh a Wine prefix after runtime installs."""
    if not wine_prefix:
        return False, "no WINEPREFIX"
    wine = shutil.which("wine") or shutil.which("wine64")
    if not wine:
        return False, "wine not found"
    env = os.environ.copy()
    env["WINEPREFIX"] = str(Path(wine_prefix).expanduser())
    env.setdefault("WINEDEBUG", "-all")
    try:
        proc = subprocess.run(
            [wine, "wineboot", "-u"],
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout_sec,
            check=False,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode == 0, output[-2000:]
    except subprocess.TimeoutExpired:
        return False, "wineboot timed out"
    except OSError as exc:
        return False, str(exc)


def repair_wine_runtimes(
    wine_prefix: str,
    *,
    progress_callback: Optional[Callable[[str], None]] = None,
    force_dotnet: bool = False,
) -> Dict[str, Any]:
    """Repair VC++ / .NET when missing or after a classified rundll32/dotnet failure."""
    steps: List[Dict[str, Any]] = []
    ok = True

    def _progress(message: str) -> None:
        if progress_callback:
            progress_callback(message)

    ensure_wine_windows_version(wine_prefix)
    terminate_stale_winetricks_for_prefix(wine_prefix)

    vcrun_ready = prefix_vcrun_installed(wine_prefix)
    dotnet_ready = prefix_dotnet_installed(wine_prefix)

    if not vcrun_ready or (force_dotnet and not vcrun_ready):
        _progress("Repairing Visual C++ runtimes in Wine prefix…")
        v_ok, _ = run_winetricks(wine_prefix, ["vcrun2019", "vcrun2022"], timeout_sec=900)
        vcrun_ready = prefix_vcrun_installed(wine_prefix)
        steps.append({"step": "vcrun_repair", "ok": v_ok, "ready": vcrun_ready})
        ok = ok and (v_ok or vcrun_ready)
    else:
        steps.append({"step": "vcrun_repair", "ok": True, "ready": True, "skipped": True})

    if dotnet_ready and not force_dotnet:
        steps.append({"step": "dotnet48_force", "ok": True, "ready": True, "skipped": True})
    elif not dotnet_ready or force_dotnet:
        _progress(
            "Installing/repairing .NET Framework 4.8 — ignore any Microsoft Learn browser tab; "
            "Bridge is handling it…"
        )
        if force_dotnet and dotnet_ready:
            _progress("Force-repair requested — refreshing .NET registration…")
        elif not dotnet_ready:
            mono_ok, _ = run_winetricks(wine_prefix, ["remove_mono"], timeout_sec=300)
            steps.append({"step": "remove_mono", "ok": mono_ok})
        d_ok, _ = run_winetricks(
            wine_prefix,
            ["dotnet48"],
            timeout_sec=1200,
            force=force_dotnet,
        )
        dotnet_ready = prefix_dotnet_installed(wine_prefix)
        steps.append({"step": "dotnet48", "ok": d_ok, "ready": dotnet_ready})
        if not dotnet_ready:
            _progress("dotnet48 incomplete — trying dotnet472…")
            d2_ok, _ = run_winetricks(wine_prefix, ["dotnet472"], timeout_sec=1200, force=force_dotnet)
            dotnet_ready = prefix_dotnet_installed(wine_prefix)
            steps.append({"step": "dotnet472", "ok": d2_ok, "ready": dotnet_ready})
            ok = ok and (d_ok or d2_ok or dotnet_ready)
        else:
            ok = ok and (d_ok or dotnet_ready)

    boot_ok, _ = wineboot_update(wine_prefix)
    steps.append({"step": "wineboot", "ok": boot_ok})

    return {
        "ok": ok and boot_ok,
        "vcrun_ready": prefix_vcrun_installed(wine_prefix),
        "dotnet_ready": prefix_dotnet_installed(wine_prefix),
        "steps": steps,
        "repaired": True,
    }


def ascension_wine_preflight(
    wine_prefix: str,
    file_path: str,
    *,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Ascension-specific preflight — cache-aware, skips slow work when prefix is ready."""
    from alma_bridge.bridge.prefix_profile import (
        PrefixReadinessProfile,
        load_prefix_profile,
        profile_allows_fast_launch,
        save_prefix_profile,
    )
    from alma_bridge.compatibility.ascension_config import (
        disable_ascension_auto_updater,
        write_ascension_launch_wrapper,
    )
    from alma_bridge.compatibility.electron_wine import apply_electron_remediation_shims, mingw_compiler
    from alma_bridge.execution.installer_verify import (
        ascension_launcher_install_broken,
        ascension_main_launcher_path,
        ascension_wrappers_present,
        discover_installed_launcher,
    )

    def _progress(message: str) -> None:
        if progress_callback:
            progress_callback(message)

    result: Dict[str, Any] = {"actions": []}
    launcher_path = ascension_main_launcher_path(wine_prefix)
    cached = load_prefix_profile(wine_prefix)

    if launcher_path and profile_allows_fast_launch(cached, wine_prefix, launcher_path=launcher_path):
        _progress("Prefix profile cache hit — skipping dotnet refresh and wrapper rebuild…")
        disable_ascension_auto_updater(wine_prefix, launcher_path)
        wrapper = write_ascension_launch_wrapper(wine_prefix, launcher_path)
        result["actions"].append({
            "kind": "profile_cache_hit",
            "launcher_path": launcher_path,
            "wrapper_script": wrapper,
            "verified_at": cached.verified_at if cached else None,
        })
        return result

    _progress("Ascension preflight: setting Wine Windows version to win10…")
    win_ok, win_msg = require_wine_windows_version(wine_prefix)
    result["actions"].append({
        "kind": "wine_windows_version",
        "ok": win_ok,
        "message": win_msg,
        "version": read_wine_windows_version(wine_prefix),
    })
    if not win_ok:
        _progress(f"Wine Windows version not confirmed: {win_msg}")

    if ascension_launcher_install_broken(wine_prefix):
        _progress("Ascension main launcher missing — repairing install from updater cache…")
        repair = repair_ascension_launcher_install(
            wine_prefix,
            file_path,
            progress_callback=progress_callback,
        )
        result["actions"].append({"kind": "launcher_repair", **repair})
        launcher_path = ascension_main_launcher_path(wine_prefix)

    shim_target = launcher_path or file_path
    if Path(file_path).name.lower().find("setup") >= 0 or "installer" in file_path.lower():
        discovered = discover_installed_launcher(wine_prefix, file_path)
        if discovered:
            shim_target = discovered
            launcher_path = discovered
            _progress(f"Applying Electron wrappers to installed launcher: {Path(discovered).name}")

    wrappers_needed = not (launcher_path and ascension_wrappers_present(launcher_path))
    if wrappers_needed:
        if not mingw_compiler():
            _progress("Installing mingw cross-compiler for Ascension sidecar wrappers…")
            try:
                subprocess.run(
                    ["sudo", "-n", "apt-get", "install", "-y", "gcc-mingw-w64-x86-64"],
                    capture_output=True,
                    text=True,
                    timeout=300,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass

        env: Dict[str, str] = {"WINEPREFIX": wine_prefix, "WINEDEBUG": "-all"}
        shim = apply_electron_remediation_shims(
            {
                "id": "ascension_int3_full_repair",
                "shims": [
                    "electron_launcher_guard_workaround",
                    "electron_elevate_passthrough",
                    "disable_dxvk",
                ],
            },
            env,
            app_file=shim_target,
        )
        result["actions"].append({"kind": "electron_shims", "result": shim})
    else:
        _progress("Electron wrappers already installed — skipping rebuild.")
        result["actions"].append({"kind": "electron_shims", "status": "skipped"})

    if launcher_path:
        updater = disable_ascension_auto_updater(wine_prefix, launcher_path)
        wrapper = write_ascension_launch_wrapper(wine_prefix, launcher_path)
        result["actions"].append({"kind": "updater_disabled", **updater, "wrapper_script": wrapper})

    if prefix_runtimes_functional(wine_prefix):
        _progress("Wine runtimes functional — skipping winetricks dotnet refresh.")
        boot_ok, _ = wineboot_update(wine_prefix)
        result["actions"].append({
            "kind": "runtime_refresh",
            "skipped_full_reinstall": True,
            "skipped_dotnet_refresh": True,
            "wineboot": boot_ok,
            "dotnet_functional": True,
        })
    elif prefix_runtimes_ready(wine_prefix):
        _progress(
            "Wine prefix has VC++ and .NET files but CLR probe failed — "
            "refreshing .NET registration…"
        )
        refresh = refresh_dotnet_registration(
            wine_prefix,
            progress_callback=progress_callback,
        )
        boot_ok, _ = wineboot_update(wine_prefix)
        result["actions"].append({
            "kind": "runtime_refresh",
            "skipped_full_reinstall": True,
            "wineboot": boot_ok,
            **refresh,
        })
    else:
        _progress("Wine runtimes missing in prefix — bootstrapping VC++ and .NET…")
        bootstrap = bootstrap_wine_runtimes(wine_prefix, progress_callback=progress_callback)
        result["actions"].append({"kind": "bootstrap_runtimes", **bootstrap})

    if launcher_path:
        save_prefix_profile(
            PrefixReadinessProfile(
                wine_prefix=str(Path(wine_prefix).expanduser().resolve()),
                launcher_path=launcher_path,
                windows_version=read_wine_windows_version(wine_prefix),
                dotnet_functional=prefix_dotnet_functional(wine_prefix),
                vcrun_ready=prefix_vcrun_installed(wine_prefix),
                wrappers_applied=ascension_wrappers_present(launcher_path),
                updater_disabled=True,
            )
        )
    return result


def repair_ascension_launcher_install(
    wine_prefix: str,
    installer_path: str,
    *,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Reinstall Ascension when the main launcher exe was removed (e.g. failed auto-update)."""
    from alma_bridge.execution.installer_verify import ascension_main_launcher_path

    def _progress(message: str) -> None:
        if progress_callback:
            progress_callback(message)

    if ascension_main_launcher_path(wine_prefix):
        return {"ok": True, "skipped": True}

    wine = shutil.which("wine") or shutil.which("wine64")
    if not wine:
        return {"ok": False, "reason": "wine not found"}

    require_wine_windows_version(wine_prefix)
    candidates: List[Path] = []
    pending = (
        Path(wine_prefix).expanduser()
        / "drive_c/users/joshua/AppData/Local/projectascension-updater/pending"
    )
    if pending.is_dir():
        candidates.extend(sorted(pending.glob("ascension-setup-*.exe"), reverse=True))
    installer = Path(installer_path).expanduser()
    if installer.is_file() and installer not in candidates:
        candidates.append(installer)

    env = _wine_prefix_env(wine_prefix)
    for setup in candidates:
        _progress(f"Reinstalling Ascension from {setup.name}…")
        try:
            proc = subprocess.run(
                [wine, str(setup), "/NCRC"],
                capture_output=True,
                text=True,
                env=env,
                timeout=900,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "reason": str(exc), "setup": str(setup)}
        restored = ascension_main_launcher_path(wine_prefix)
        if restored:
            _progress("Ascension launcher restored.")
            return {
                "ok": True,
                "reinstalled_from": str(setup),
                "launcher_path": restored,
                "exit_code": proc.returncode,
            }

    return {"ok": False, "reason": "launcher still missing after reinstall attempts"}


def apply_ml_wine_fix(
    signature: str,
    wine_prefix: str,
    file_path: str,
    *,
    progress_callback: Optional[Callable[[str], None]] = None,
    session_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    auto_remediate: Optional[bool] = None,
) -> Dict[str, Any]:
    """Apply the ML-ranked Wine fix for a classified Bridge failure signature."""
    result: Dict[str, Any] = {"signature": signature, "actions": []}

    def _progress(message: str) -> None:
        if progress_callback:
            progress_callback(message)

    def _mutate() -> Dict[str, Any]:
        local = {"signature": signature, "actions": []}
        if signature in {"dotnet_missing", "missing_dll", "missing_visual_c_runtime", "client_services_stalled"}:
            _progress(f"AI/ML auto-fix: repairing Wine runtimes for {signature}…")
            repair = repair_wine_runtimes(
                wine_prefix,
                progress_callback=progress_callback,
                force_dotnet=signature == "dotnet_missing",
            )
            local["actions"].append({"kind": "repair_runtimes", **repair})
            return local

        if signature == "wine_int3_crash" or "ascension" in file_path.lower():
            preflight = ascension_wine_preflight(
                wine_prefix,
                file_path,
                progress_callback=progress_callback,
            )
            local["actions"].extend(preflight.get("actions", []))
            return local
        return local

    if session_id:
        from alma_bridge.session.mutations import build_preflight_intent, run_prefix_mutation
        from alma_bridge.session.policy import PolicyGate

        intent = build_preflight_intent(
            action_id=f"ml_wine_fix:{signature}",
            session_id=session_id,
            correlation_id=correlation_id or session_id,
            wine_prefix=wine_prefix,
            auto_remediate=auto_remediate,
        )
        decision, payload, error = run_prefix_mutation(intent, PolicyGate(), _mutate)
        result["policy"] = {
            "allowed": decision.allowed if decision else False,
            "reason": (decision.reason if decision else error) or "",
        }
        if error and not payload:
            return result
        if payload:
            result.update(payload)
        return result

    return _mutate()


def bootstrap_wine_runtimes(
    wine_prefix: str,
    *,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Install VC++ and .NET into a prefix before launching Windows installers/apps."""
    steps: List[Dict[str, Any]] = []
    ok = True

    def _progress(message: str) -> None:
        if progress_callback:
            progress_callback(message)

    if not prefix_vcrun_installed(wine_prefix):
        _progress("Installing Visual C++ runtimes (vcrun2019, vcrun2022)…")
        v_ok, _ = run_winetricks(wine_prefix, ["vcrun2019", "vcrun2022"], timeout_sec=900)
        vcrun_ready = prefix_vcrun_installed(wine_prefix)
        steps.append({"step": "vcrun", "ok": v_ok, "ready": vcrun_ready})
        ok = ok and (v_ok or vcrun_ready)

    dotnet_ready = prefix_dotnet_installed(wine_prefix)
    if not dotnet_ready:
        _progress(
            "Installing .NET Framework 4.8 (dotnet48) — a browser tab about .NET is normal Wine noise; "
            "Bridge blocks it and continues…"
        )
        d_ok, _ = run_winetricks(wine_prefix, ["dotnet48"], timeout_sec=1200)
        dotnet_ready = prefix_dotnet_installed(wine_prefix)
        steps.append({"step": "dotnet48", "ok": d_ok, "ready": dotnet_ready})
        if not dotnet_ready:
            _progress("dotnet48 incomplete — trying dotnet472 fallback…")
            d2_ok, _ = run_winetricks(wine_prefix, ["dotnet472"], timeout_sec=1200)
            dotnet_ready = prefix_dotnet_installed(wine_prefix)
            steps.append({"step": "dotnet472", "ok": d2_ok, "ready": dotnet_ready})
            ok = ok and (d_ok or d2_ok or dotnet_ready)
        else:
            ok = ok and (d_ok or dotnet_ready)

    return {
        "ok": ok,
        "vcrun_ready": prefix_vcrun_installed(wine_prefix),
        "dotnet_ready": prefix_dotnet_installed(wine_prefix),
        "steps": steps,
    }


def refresh_dotnet_registration(
    wine_prefix: str,
    *,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Dict[str, Any]:
    """Re-register .NET when files exist but rundll32 bootstrap still fails."""
    def _progress(message: str) -> None:
        if progress_callback:
            progress_callback(message)

    if prefix_dotnet_functional(wine_prefix):
        return {"ok": True, "skipped": True, "reason": "dotnet already functional"}

    if not prefix_dotnet_installed(wine_prefix):
        return {"ok": False, "skipped": True, "reason": "dotnet not installed"}

    _progress(
        "Refreshing .NET 4.8 registration in Wine prefix "
        "(fixes rundll32 'Unable to find runtime' when files already exist)…"
    )
    require_wine_windows_version(wine_prefix)
    terminate_stale_winetricks_for_prefix(wine_prefix)
    d_ok, _ = run_winetricks(wine_prefix, ["dotnet48"], timeout_sec=1200, force=True)
    boot_ok, _ = wineboot_update(wine_prefix)
    return {
        "ok": d_ok and boot_ok,
        "refreshed": True,
        "dotnet_ready": prefix_dotnet_installed(wine_prefix),
        "wineboot": boot_ok,
    }


def terminate_stale_winetricks_for_prefix(wine_prefix: str) -> List[int]:
    """Kill orphaned winetricks shells still holding the same WINEPREFIX."""
    target = str(Path(wine_prefix).expanduser().resolve())
    killed: List[int] = []
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return killed

    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            environ = (entry / "environ").read_bytes().decode("utf-8", errors="replace")
            cmdline = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", errors="replace"
            )
        except OSError:
            continue
        if "winetricks" not in cmdline.lower():
            continue
        prefix = _wine_prefix_from_environ(environ)
        if not prefix:
            continue
        if str(Path(prefix).expanduser().resolve()) != target:
            continue
        try:
            os.kill(pid, 15)
            killed.append(pid)
        except OSError:
            continue
    return killed


def run_winetricks(
    wine_prefix: str,
    packages: List[str],
    *,
    timeout_sec: int = 600,
    force: bool = False,
) -> tuple[bool, str]:
    if not winetricks_available() or not wine_prefix or not packages:
        return False, "winetricks not available or no packages requested"

    stale = terminate_stale_winetricks_for_prefix(wine_prefix)
    if stale:
        time.sleep(1)

    env = os.environ.copy()
    env["WINEPREFIX"] = wine_prefix
    env.setdefault("WINEDEBUG", "-all")
    env["BROWSER"] = shutil.which("true") or "/bin/true"

    ordered: List[str] = []
    dotnet_pkgs: List[str] = []
    for pkg in packages:
        name = pkg.strip()
        if not name:
            continue
        if name.startswith("dotnet"):
            dotnet_pkgs.append(name)
        else:
            ordered.append(name)
    ordered.extend(dotnet_pkgs)
    if not ordered:
        return False, "no packages requested"

    outputs: List[str] = []
    all_ok = True
    for pkg in ordered:
        pkg_timeout = 1200 if pkg.startswith("dotnet") else timeout_sec
        try:
            cmd = ["winetricks", "-q"]
            if force:
                cmd.append("-f")
            cmd.append(pkg)
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=pkg_timeout,
                check=False,
            )
            chunk = (proc.stdout or "") + (proc.stderr or "")
            outputs.append(chunk)
            if proc.returncode != 0:
                all_ok = False
                if pkg == "dotnet48":
                    try:
                        fallback_cmd = ["winetricks", "-q"]
                        if force:
                            fallback_cmd.append("-f")
                        fallback_cmd.append("dotnet472")
                        fallback = subprocess.run(
                            fallback_cmd,
                            capture_output=True,
                            text=True,
                            env=env,
                            timeout=pkg_timeout,
                            check=False,
                        )
                        outputs.append((fallback.stdout or "") + (fallback.stderr or ""))
                        if fallback.returncode == 0:
                            all_ok = True
                    except (subprocess.TimeoutExpired, OSError):
                        pass
        except subprocess.TimeoutExpired:
            all_ok = False
            outputs.append(f"{pkg} timed out")
        except OSError as exc:
            all_ok = False
            outputs.append(str(exc))

    return all_ok, "\n".join(outputs)[-4000:]
