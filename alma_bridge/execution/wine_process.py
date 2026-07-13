from __future__ import annotations

import time
from pathlib import Path
from typing import FrozenSet, Iterable, Optional, Set, Tuple


def _iter_wine_cmdlines(wine_prefix: str) -> Iterable[Tuple[int, str]]:
    prefix_real = str(Path(wine_prefix).expanduser().resolve())
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return

    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            environ = (entry / "environ").read_bytes().replace(b"\0", b"\n").decode(
                "utf-8", errors="replace"
            )
        except OSError:
            continue
        if prefix_real not in environ and f"WINEPREFIX={prefix_real}" not in environ:
            continue
        try:
            cmdline = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(
                "utf-8", errors="replace"
            )
        except OSError:
            cmdline = ""
        if cmdline.strip():
            yield pid, cmdline


def snapshot_wine_pids(wine_prefix: str) -> FrozenSet[int]:
    """PIDs already running in this prefix before a new launch attempt."""
    return frozenset(pid for pid, _ in _iter_wine_cmdlines(wine_prefix))


def _is_decoy_or_sidecar_cmdline(cmdline: str) -> bool:
    lower = cmdline.lower()
    if "alma-guard" in lower:
        return True
    if "clientservices" in lower or "client-services" in lower:
        return True
    if "cs_wrapper" in lower:
        return True
    if "--alma-decoy" in lower:
        return True
    return False


def wine_has_main_launcher_process(
    wine_prefix: str,
    launcher_path: str,
    *,
    exclude_pids: Optional[Set[int]] = None,
) -> bool:
    """True when the installed launcher exe is running — not Alma's decoy copy."""
    launcher = Path(launcher_path).expanduser().resolve()
    install_dir = launcher.parent.name.lower()
    exe_name = launcher.name.lower()
    marker = f"{install_dir}\\{exe_name}"
    marker_slash = f"{install_dir}/{exe_name}"
    skip = exclude_pids or set()

    for pid, cmdline in _iter_wine_cmdlines(wine_prefix):
        if pid in skip:
            continue
        if _is_decoy_or_sidecar_cmdline(cmdline):
            continue
        lower = cmdline.lower()
        if exe_name not in lower:
            continue
        normalized = lower.replace("/", "\\")
        if marker in normalized or marker_slash in lower:
            return True
        if install_dir in lower and exe_name in lower and "resources" not in normalized:
            return True
    return False


def wine_has_process_for_prefix(wine_prefix: str, needle: str, *, min_hits: int = 1) -> bool:
    """Return True if a process in `wine_prefix` has `needle` in its cmdline."""
    needle_lower = needle.lower()
    hits = 0
    for _, cmdline in _iter_wine_cmdlines(wine_prefix):
        if needle_lower in cmdline.lower():
            hits += 1
            if hits >= min_hits:
                return True
    return False


def wine_rundll32_active(wine_prefix: str) -> bool:
    """True when rundll32.exe is running in the prefix (often a .NET bootstrap failure)."""
    return wine_has_process_for_prefix(wine_prefix, "rundll32")


def wait_for_main_launcher_process(
    wine_prefix: str,
    launcher_path: str,
    *,
    timeout_sec: float = 15.0,
    poll_sec: float = 0.5,
    exclude_pids: Optional[Set[int]] = None,
) -> bool:
    """Poll until the real installed launcher binary is running."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if wine_has_main_launcher_process(
            wine_prefix, launcher_path, exclude_pids=exclude_pids
        ):
            return True
        time.sleep(poll_sec)
    return False


def wait_for_wine_process(
    wine_prefix: str,
    needle: str,
    *,
    timeout_sec: float = 15.0,
    poll_sec: float = 0.5,
) -> bool:
    """Poll until a matching Wine process appears or timeout."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if wine_has_process_for_prefix(wine_prefix, needle):
            return True
        time.sleep(poll_sec)
    return False
