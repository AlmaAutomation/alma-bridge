from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

INSTALLER_LOG_SUCCESS_MARKERS = (
    "installation complete",
    "successfully installed",
    "setup was successfully completed",
    "installer finished",
    "completed successfully",
    "install success",
    "installation succeeded",
    "finish success",
)

UNINSTALL_KEY_RE = re.compile(
    r'^\[Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\([^\]]+)\]',
    re.MULTILINE,
)

GENERIC_NAME_TOKENS = frozenset(
    {"setup", "install", "installer", "update", "bootstrap", "exe", "x64", "x86"}
)

SKIP_LAUNCHER_NAMES = frozenset(
    {
        "uninstall",
        "setup",
        "install",
        "installer",
        "update",
        "elevate",
        "helper",
        "crash",
        "service",
    }
)


@dataclass(frozen=True)
class PrefixSnapshot:
    uninstall_keys: frozenset[str]
    program_dirs: frozenset[str]
    file_count: int


def snapshot_wine_prefix(wine_prefix: str, *, max_files: int = 8000) -> PrefixSnapshot:
    """Capture prefix state before an installer run for post-run verification."""
    root = Path(wine_prefix).expanduser()
    if not root.is_dir():
        return PrefixSnapshot(frozenset(), frozenset(), 0)

    uninstall_keys: set[str] = set()
    for reg_name in ("user.reg", "system.reg"):
        reg_path = root / reg_name
        if reg_path.is_file():
            try:
                text = reg_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            uninstall_keys.update(UNINSTALL_KEY_RE.findall(text))

    program_dirs: set[str] = set()
    drive_c = root / "drive_c"
    for sub in ("Program Files", "Program Files (x86)", "users/Public"):
        base = drive_c / sub
        if base.is_dir():
            for child in base.iterdir():
                if child.is_dir():
                    program_dirs.add(str(child.relative_to(drive_c)).replace("\\", "/"))

    file_count = 0
    for path in root.rglob("*"):
        if path.is_file():
            file_count += 1
            if file_count >= max_files:
                break

    return PrefixSnapshot(
        uninstall_keys=frozenset(uninstall_keys),
        program_dirs=frozenset(program_dirs),
        file_count=file_count,
    )


def _installer_name_tokens(installer_path: str) -> List[str]:
    stem = Path(installer_path).stem.lower()
    tokens = re.split(r"[-_.\s]+", stem)
    return [
        token
        for token in tokens
        if len(token) >= 4 and token not in GENERIC_NAME_TOKENS
    ]


def _launcher_score(exe: Path, tokens: List[str]) -> int:
    lower = exe.name.lower()
    parent = exe.parent.name.lower()
    path_lower = str(exe).replace("\\", "/").lower()
    if "alma-guard" in path_lower:
        return 0
    if ".real.exe" in path_lower:
        return 0
    if any(skip in lower for skip in SKIP_LAUNCHER_NAMES):
        return 0
    if lower.startswith("uninstall"):
        return 0

    try:
        if exe.stat().st_size < 500_000:
            return 0
    except OSError:
        return 0

    score = 0
    if tokens and any(token in parent or token in lower for token in tokens):
        score += 10
    if "launcher" in lower or "launcher" in parent:
        score += 8
    if "client" in lower and "service" not in lower:
        score += 4

    try:
        from alma_bridge.learning.installer import is_electron_app

        if is_electron_app(str(exe)):
            score += 6
    except ImportError:
        pass

    return score


def ascension_main_launcher_path(wine_prefix: str) -> Optional[str]:
    """Canonical Ascension Electron launcher (not Alma's decoy copy)."""
    base = (
        Path(wine_prefix).expanduser()
        / "drive_c/Program Files/Ascension Launcher"
    )
    candidates = [
        base / "Ascension Launcher.exe",
        base / "Ascension Launcher/Ascension Launcher.exe",
    ]
    for launcher in candidates:
        if launcher.is_file() and launcher.stat().st_size > 500_000:
            return str(launcher)

    ranked: List[tuple[int, Path]] = []
    if base.is_dir():
        for exe in base.rglob("Ascension Launcher.exe"):
            path_lower = str(exe).replace("\\", "/").lower()
            if "alma-guard" in path_lower:
                continue
            try:
                size = exe.stat().st_size
            except OSError:
                continue
            if size > 500_000:
                ranked.append((size, exe))
    if ranked:
        return str(max(ranked, key=lambda item: item[0])[1])
    return None


def ascension_launcher_install_broken(wine_prefix: str) -> bool:
    return ascension_main_launcher_path(wine_prefix) is None


def ascension_wrappers_present(launcher_path: str) -> bool:
    """True when Alma's elevate passthrough + sidecar wrapper are installed."""
    launcher = Path(launcher_path).expanduser()
    resources = launcher.parent / "resources"
    if not resources.is_dir():
        return False
    elevate = resources / "elevate.exe"
    sidecar = resources / "AscensionClientServices.exe"
    sidecar_real = resources / "AscensionClientServices.real.exe"
    if not sidecar_real.is_file():
        return False
    if not sidecar.is_file():
        return False
    if not elevate.is_file():
        return False
    try:
        return elevate.stat().st_size < 300_000
    except OSError:
        return False


def launcher_ready_for_handoff(
    wine_prefix: str,
    installer_path: str,
    *,
    require_wrappers: bool = True,
) -> Optional[str]:
    """Fast-path gate: launcher exists, runtimes functional, win10, wrappers ready."""
    from alma_bridge.execution.preflight import (
        prefix_runtimes_functional,
        query_wine_windows_version_live,
        read_wine_windows_version,
        wine_windows_version_insufficient,
    )

    launcher = discover_installed_launcher(wine_prefix, installer_path)
    if not launcher:
        return None
    if not prefix_runtimes_functional(wine_prefix):
        return None
    version = query_wine_windows_version_live(wine_prefix) or read_wine_windows_version(wine_prefix)
    if wine_windows_version_insufficient(version):
        return None
    if require_wrappers and "ascension" in installer_path.lower():
        if not ascension_wrappers_present(launcher):
            return None
    return launcher


def discover_installed_launcher(wine_prefix: str, installer_path: str) -> Optional[str]:
    """Find the main installed app launcher exe inside a Wine prefix."""
    main = ascension_main_launcher_path(wine_prefix)
    if main:
        return main
    root = Path(wine_prefix).expanduser()
    drive_c = root / "drive_c"
    if not drive_c.is_dir():
        return None

    tokens = _installer_name_tokens(installer_path)
    ranked: List[tuple[int, Path]] = []
    for sub in ("Program Files", "Program Files (x86)"):
        base = drive_c / sub
        if not base.is_dir():
            continue
        for exe in base.rglob("*.exe"):
            score = _launcher_score(exe, tokens)
            if score > 0:
                ranked.append((score, exe))

    if not ranked:
        return None

    best = max(ranked, key=lambda item: (item[0], item[1].stat().st_mtime))[1]
    return str(best)


def launcher_verified_in_prefix(wine_prefix: str, launcher_path: str) -> bool:
    """True when a prior Bridge session verified this launcher actually runs."""
    from alma_bridge.storage import outcomes

    try:
        outcomes.init_outcome_store()
        launcher_name = Path(launcher_path).name.lower()
        for row in outcomes.list_recent_sessions(limit=40):
            if not row.get("success"):
                continue
            full = outcomes.get_session(row["session_id"])
            if not full:
                continue
            summary = (full.get("summary") or "").lower()
            if "is running from the install directory" in summary:
                if wine_prefix in str(full.get("file_path") or ""):
                    return True
                if full.get("installed_launcher_path") and launcher_name in (
                    full.get("installed_launcher_path") or ""
                ).lower():
                    return True
            for attempt in full.get("attempts") or []:
                if not attempt.get("success") or attempt.get("phase") != "launcher":
                    continue
                env = attempt.get("env") or {}
                if wine_prefix not in str(env.get("WINEPREFIX", "")):
                    continue
                attempt_stderr = (attempt.get("stderr") or "").lower()
                if "is running from the install directory" in attempt_stderr:
                    return True
                if attempt.get("launch_verification"):
                    return True
    except Exception:  # noqa: BLE001
        return False
    return False


def _log_indicates_success(stdout: str, stderr: str) -> bool:
    combined = f"{stdout or ''}\n{stderr or ''}".lower()
    return any(marker in combined for marker in INSTALLER_LOG_SUCCESS_MARKERS)


def verify_installer_outcome(
    *,
    wine_prefix: str,
    before: Optional[PrefixSnapshot],
    stdout: str,
    stderr: str,
    installer_path: str,
    duration_ms: int,
) -> Tuple[bool, List[str]]:
    """Return (verified, human-readable evidence lines)."""
    reasons: List[str] = []

    if _log_indicates_success(stdout, stderr):
        reasons.append("installer log contains a success marker")
        return True, reasons

    after = snapshot_wine_prefix(wine_prefix)
    baseline = before or PrefixSnapshot(frozenset(), frozenset(), 0)

    launcher = discover_installed_launcher(wine_prefix, installer_path)
    if launcher:
        launcher_path = Path(launcher)
        drive_c = Path(wine_prefix).expanduser() / "drive_c"
        try:
            launcher_dir = str(launcher_path.parent.relative_to(drive_c)).replace("\\", "/")
        except ValueError:
            launcher_dir = launcher_path.parent.name
        if launcher_dir in after.program_dirs and launcher_dir not in baseline.program_dirs:
            reasons.append(f"installed launcher: {launcher_path.name}")
            return True, reasons
        if launcher_path.is_file() and duration_ms >= 20_000:
            reasons.append(f"launcher present in prefix: {launcher_path.name}")
            return True, reasons

    new_uninstall = after.uninstall_keys - baseline.uninstall_keys
    if new_uninstall:
        sample = ", ".join(sorted(new_uninstall)[:3])
        reasons.append(f"new uninstall registry entries ({sample})")
        return True, reasons

    new_program_dirs = after.program_dirs - baseline.program_dirs
    if new_program_dirs:
        tokens = _installer_name_tokens(installer_path)
        matched = [
            directory
            for directory in new_program_dirs
            if not tokens or any(token in directory.lower() for token in tokens)
        ]
        if matched:
            reasons.append(f"new program directory: {matched[0]}")
            return True, reasons
        if len(new_program_dirs) >= 1 and duration_ms >= 30_000:
            reasons.append(f"new program directory: {sorted(new_program_dirs)[0]}")
            return True, reasons

    file_delta = after.file_count - baseline.file_count
    if file_delta >= 25 and duration_ms >= 45_000:
        reasons.append(f"prefix gained ~{file_delta} files during install")
        return True, reasons

    if not reasons:
        reasons.append("no uninstall entry, program directory, or success log marker found")
    return False, reasons
