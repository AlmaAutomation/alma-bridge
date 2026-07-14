from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, Iterable, List, Optional, Set, Tuple


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


WINE_INFRA_EXECUTABLES = frozenset(
    {
        "wineserver",
        "wineboot",
        "wine",
        "wine64",
        "wine64-preloader",
        "winedevice",
        "winedbg",
        "explorer.exe",
        "start.exe",
        "services.exe",
        "svchost.exe",
        "rpcss.exe",
    }
)


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


def _is_wine_infra_cmdline(cmdline: str, *, target_exe_name: str) -> bool:
    lower = cmdline.lower()
    if _is_decoy_or_sidecar_cmdline(cmdline):
        return True
    tokens = [token.strip("\"'") for token in lower.split() if token.strip("\"'")]
    for token in tokens:
        base = Path(token.replace("\\", "/")).name.lower()
        if not base:
            continue
        if base in WINE_INFRA_EXECUTABLES and base != target_exe_name.lower():
            return True
        if base.endswith(".exe") and base not in {target_exe_name.lower()}:
            if base in WINE_INFRA_EXECUTABLES:
                return True
    if "wineserver" in lower and target_exe_name.lower() not in lower:
        return True
    return False


def _target_path_markers(target_path: str) -> Tuple[str, str, str]:
    launcher = Path(target_path).expanduser().resolve()
    exe_name = launcher.name.lower()
    install_dir = launcher.parent.name.lower()
    marker = f"{install_dir}\\{exe_name}"
    marker_slash = f"{install_dir}/{exe_name}"
    return exe_name, marker, marker_slash


def _cmdline_matches_target(cmdline: str, target_path: str) -> bool:
    exe_name, marker, marker_slash = _target_path_markers(target_path)
    if _is_wine_infra_cmdline(cmdline, target_exe_name=exe_name):
        return False
    lower = cmdline.lower()
    if exe_name not in lower:
        return False
    normalized = lower.replace("/", "\\")
    if marker in normalized or marker_slash in lower:
        return True
    install_dir = Path(target_path).expanduser().resolve().parent.name.lower()
    if install_dir in lower and exe_name in lower and "resources" not in normalized:
        return True
    resolved = str(Path(target_path).expanduser().resolve()).lower()
    if resolved in lower.replace("\\", "/"):
        return True
    return False


@dataclass(frozen=True)
class TargetProcessMatch:
    pid: int
    cmdline: str
    observed_at_monotonic: float

    def to_evidence_line(self) -> str:
        return f"target_pid={self.pid} cmdline={self.cmdline[:240]}"


@dataclass
class TargetGuiObservation:
    target_path: str
    appeared: bool = False
    survived: bool = False
    startup_elapsed_sec: float = 0.0
    survival_observed_sec: float = 0.0
    matches: List[TargetProcessMatch] = field(default_factory=list)
    fatal_signature: Optional[str] = None

    def to_evidence_lines(self) -> List[str]:
        lines = [
            f"target_path={self.target_path}",
            f"appeared={self.appeared}",
            f"survived={self.survived}",
            f"startup_elapsed_sec={round(self.startup_elapsed_sec, 3)}",
            f"survival_observed_sec={round(self.survival_observed_sec, 3)}",
        ]
        for match in self.matches[:3]:
            lines.append(match.to_evidence_line())
        if self.fatal_signature:
            lines.append(f"fatal_signature={self.fatal_signature}")
        return lines

    def to_dict(self) -> Dict[str, object]:
        return {
            "target_path": self.target_path,
            "appeared": self.appeared,
            "survived": self.survived,
            "startup_elapsed_sec": self.startup_elapsed_sec,
            "survival_observed_sec": self.survival_observed_sec,
            "matches": [
                {"pid": m.pid, "cmdline": m.cmdline}
                for m in self.matches
            ],
            "fatal_signature": self.fatal_signature,
        }


def find_target_gui_processes(
    wine_prefix: str,
    target_path: str,
    *,
    exclude_pids: Optional[Set[int]] = None,
) -> List[TargetProcessMatch]:
    skip = exclude_pids or set()
    now = time.monotonic()
    matches: List[TargetProcessMatch] = []
    for pid, cmdline in _iter_wine_cmdlines(wine_prefix):
        if pid in skip:
            continue
        if _cmdline_matches_target(cmdline, target_path):
            matches.append(
                TargetProcessMatch(pid=pid, cmdline=cmdline, observed_at_monotonic=now)
            )
    return matches


def wine_has_target_gui_process(
    wine_prefix: str,
    target_path: str,
    *,
    exclude_pids: Optional[Set[int]] = None,
) -> bool:
    return bool(find_target_gui_processes(wine_prefix, target_path, exclude_pids=exclude_pids))


def wine_has_main_launcher_process(
    wine_prefix: str,
    launcher_path: str,
    *,
    exclude_pids: Optional[Set[int]] = None,
) -> bool:
    """True when the installed launcher exe is running — not Alma's decoy copy."""
    return wine_has_target_gui_process(
        wine_prefix, launcher_path, exclude_pids=exclude_pids
    )


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


def wait_for_target_gui_process(
    wine_prefix: str,
    target_path: str,
    *,
    timeout_sec: float = 15.0,
    poll_sec: float = 0.5,
    exclude_pids: Optional[Set[int]] = None,
) -> List[TargetProcessMatch]:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        matches = find_target_gui_processes(
            wine_prefix, target_path, exclude_pids=exclude_pids
        )
        if matches:
            return matches
        time.sleep(poll_sec)
    return []


def wait_for_main_launcher_process(
    wine_prefix: str,
    launcher_path: str,
    *,
    timeout_sec: float = 15.0,
    poll_sec: float = 0.5,
    exclude_pids: Optional[Set[int]] = None,
) -> bool:
    """Poll until the real installed launcher binary is running."""
    return bool(
        wait_for_target_gui_process(
            wine_prefix,
            launcher_path,
            timeout_sec=timeout_sec,
            poll_sec=poll_sec,
            exclude_pids=exclude_pids,
        )
    )


def observe_target_gui_process(
    wine_prefix: str,
    target_path: str,
    *,
    exclude_pids: Optional[Set[int]] = None,
    startup_timeout_sec: float = 15.0,
    survival_sec: float = 3.0,
    poll_sec: float = 0.5,
) -> TargetGuiObservation:
    """Wait for target appearance, then verify it survives the observation window."""
    observation = TargetGuiObservation(target_path=target_path)
    started = time.monotonic()
    matches = wait_for_target_gui_process(
        wine_prefix,
        target_path,
        timeout_sec=startup_timeout_sec,
        poll_sec=poll_sec,
        exclude_pids=exclude_pids,
    )
    observation.startup_elapsed_sec = time.monotonic() - started
    if not matches:
        return observation

    observation.appeared = True
    observation.matches = matches
    survival_started = time.monotonic()
    time.sleep(survival_sec)
    observation.survival_observed_sec = time.monotonic() - survival_started
    still_alive = find_target_gui_processes(
        wine_prefix, target_path, exclude_pids=exclude_pids
    )
    observation.survived = bool(still_alive)
    if still_alive:
        observation.matches = still_alive
    return observation


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


def terminate_owned_target_processes(
    wine_prefix: str,
    target_path: str,
    *,
    exclude_pids: Optional[Set[int]] = None,
) -> List[int]:
    """Terminate campaign-owned target processes in a prefix (best effort)."""
    terminated: List[int] = []
    for match in find_target_gui_processes(
        wine_prefix, target_path, exclude_pids=exclude_pids
    ):
        try:
            import os
            import signal

            os.kill(match.pid, signal.SIGTERM)
            terminated.append(match.pid)
        except OSError:
            continue
    return terminated
