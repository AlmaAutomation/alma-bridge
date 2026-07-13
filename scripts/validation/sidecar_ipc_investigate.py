#!/usr/bin/env python3
"""DIAGNOSTIC ONLY — Sidecar IPC/handoff investigation.

Not imported by production code. Bounded timeouts. Requires campaign env vars
(see scripts/validation/README-DIAGNOSTICS.md).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import struct
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts.validation.ascension_baseline_investigate import (  # noqa: E402
    EVIDENCE_ROOT,
    _clone_prefix,
    _configure_campaign_guard,
    pe_metadata,
    prefix_aggregate_hash,
    resolve_launcher_in_prefix,
    sha256_file,
)

# Paths from environment (no machine-specific hardcoding in this diagnostic entrypoint).
_HOME = Path.home()
BASELINE_ROOT = Path(
    os.environ.get(
        "ALMA_BRIDGE_VALIDATION_CAMPAIGN_DISPOSABLE_ROOT",
        _HOME / ".local/share/alma-bridge/prefixes/validation/ascension-baseline",
    )
).expanduser()
PRIMARY_PREFIX = Path(
    os.environ.get(
        "ALMA_BRIDGE_VALIDATION_CAMPAIGN_PRIMARY_PREFIX",
        _HOME / ".local/share/alma-bridge/prefixes/803984cf-660",
    )
).expanduser()
SOURCE_SNAPSHOT = Path(
    os.environ.get(
        "ALMA_BRIDGE_VALIDATION_CAMPAIGN_SOURCE_SNAPSHOT",
        _HOME / ".local/share/alma-bridge/prefixes/validation/pilot-001/source-prefix-snapshot",
    )
).expanduser()

IPC_EVIDENCE = EVIDENCE_ROOT / "sidecar-ipc"
SIDECAR_SILENT_CRASH_SEC = 10.0
TRACE_POLL_SEC = 0.25
MAX_BRIDGE_SEC = 420


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mono() -> float:
    return time.monotonic()


# ---------------------------------------------------------------------------
# Wine cleanup
# ---------------------------------------------------------------------------


def cleanup_wine_prefix(prefix: Path, *, kill_tree: bool = True) -> Dict[str, Any]:
    """Kill wineserver and wine processes for one disposable prefix."""
    prefix = prefix.expanduser().resolve()
    killed: List[str] = []
    self_pid = os.getpid()
    if kill_tree:
        prefix_real = str(prefix)
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            if pid == self_pid:
                continue
            try:
                env = (entry / "environ").read_bytes().replace(b"\0", b"\n").decode(
                    "utf-8", errors="replace"
                )
            except OSError:
                continue
            if f"WINEPREFIX={prefix_real}" not in env and prefix_real not in env:
                continue
            try:
                os.kill(pid, 15)
                killed.append(str(pid))
            except OSError:
                pass
    env = {**os.environ, "WINEPREFIX": str(prefix)}
    subprocess.run(["wineserver", "-k"], env=env, capture_output=True, timeout=15)
    time.sleep(0.5)
    return {"prefix": str(prefix), "killed_linux_pids": killed, "wineserver_killed": True}


def cleanup_all_validation_wine() -> None:
    """Clean every disposable baseline prefix and stray wine from prior diagnostics."""
    if BASELINE_ROOT.is_dir():
        for child in sorted(BASELINE_ROOT.iterdir()):
            if child.is_dir():
                cleanup_wine_prefix(child)
    cleanup_wine_prefix(PRIMARY_PREFIX, kill_tree=False)


# ---------------------------------------------------------------------------
# Process / network snapshots
# ---------------------------------------------------------------------------


def _proc_field(pid: int, name: str) -> Optional[str]:
    try:
        return (Path(f"/proc/{pid}") / name).read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _linux_process_snapshot(wine_prefix: str) -> List[Dict[str, Any]]:
    prefix_real = str(Path(wine_prefix).expanduser().resolve())
    rows: List[Dict[str, Any]] = []
    proc_root = Path("/proc")
    if not proc_root.is_dir():
        return rows
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
        cmdline = (entry / "cmdline").read_bytes().replace(b"\0", b" ").decode(
            "utf-8", errors="replace"
        )
        if not cmdline.strip():
            continue
        status = _proc_field(pid, "status") or ""
        ppid = None
        start = None
        for line in status.splitlines():
            if line.startswith("PPid:"):
                ppid = int(line.split()[1])
            if line.startswith("Starttime:"):
                start = int(line.split()[1])
        exe = None
        try:
            exe = os.readlink(entry / "exe")
        except OSError:
            exe = None
        role = _classify_cmdline(cmdline)
        rows.append(
            {
                "linux_pid": pid,
                "ppid": ppid,
                "role": role,
                "cmdline": cmdline,
                "exe": exe,
                "starttime_ticks": start,
            }
        )
    return sorted(rows, key=lambda r: r["linux_pid"])


def _classify_cmdline(cmdline: str) -> str:
    lower = cmdline.lower()
    if "--alma-decoy" in lower or "alma-guard" in lower:
        return "decoy"
    if "clientservices.real.exe" in lower:
        return "sidecar_real"
    if "clientservices.exe" in lower:
        return "sidecar_wrapper"
    if "ascension launcher.exe" in lower and "alma-guard" not in lower:
        return "launcher"
    if "elevate.exe" in lower:
        return "elevate"
    if "wineserver" in lower:
        return "wineserver"
    return "other"


def wine_tasklist_snapshot(wine_prefix: str) -> List[Dict[str, str]]:
    """Windows-visible PIDs via wine tasklist (best-effort)."""
    env = {**os.environ, "WINEPREFIX": str(Path(wine_prefix).expanduser().resolve()), "WINEDEBUG": "-all"}
    try:
        proc = subprocess.run(
            ["wine", "cmd", "/c", "tasklist"],
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    rows: List[Dict[str, str]] = []
    for line in proc.stdout.splitlines():
        if ".exe" not in line.lower():
            continue
        parts = line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            rows.append({"image": parts[0], "windows_pid": parts[1], "raw": line.strip()})
    return rows


def loopback_listeners_snapshot() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    try:
        proc = subprocess.run(["ss", "-ltn"], capture_output=True, text=True, timeout=5)
        for line in proc.stdout.splitlines():
            if "127.0.0.1:" not in line and "::1:" not in line:
                continue
            rows.append({"raw": line.strip()})
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return rows


def _parse_invoke_tail(text: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    decoy = re.search(r"decoy_pid=(\d+)", text)
    if decoy:
        out["decoy_pid_windows"] = int(decoy.group(1))
    cmd = re.search(r"cmdline=(\".+?\")(?:\s|$)", text)
    if cmd:
        out["sidecar_cmdline"] = cmd.group(1)
    passthrough = re.search(r"passthrough_cmdline=(\".+?\")(?:\s|$)", text)
    if passthrough:
        out["passthrough_cmdline"] = passthrough.group(1)
    exit_m = re.search(r"sidecar exited code=(\d+)", text)
    if exit_m:
        out["wrapper_exit_code"] = int(exit_m.group(1))
    return out


def _read_invoke_log(prefix: Path) -> str:
    path = prefix / "drive_c/alma-cs-invoke.log"
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _output_log_size(prefix: Path) -> int:
    path = prefix / "drive_c/alma-cs-output.log"
    try:
        return path.stat().st_size if path.is_file() else 0
    except OSError:
        return 0


def pe_version_strings(path: Path) -> Dict[str, str]:
    """Best-effort PE version metadata via strings."""
    meta: Dict[str, str] = {}
    if not path.is_file():
        return meta
    try:
        proc = subprocess.run(["strings", str(path)], capture_output=True, text=True, timeout=30)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return meta
    for key, pattern in (
        ("original_filename", r"OriginalFilename"),
        ("file_description", r"FileDescription"),
        ("product_name", r"ProductName"),
        ("internal_name", r"InternalName"),
    ):
        for line in proc.stdout.splitlines():
            if pattern in line and len(line) < 200:
                meta[key] = line.strip()
                break
    return meta


def extract_sidecar_guard_strings(real_exe: Path) -> List[str]:
    if not real_exe.is_file():
        return []
    try:
        proc = subprocess.run(["strings", str(real_exe)], capture_output=True, text=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    needles = (
        "launcher guard",
        "launcher_pid",
        "launcher_name",
        "launcher PID",
        "Process32",
        "OpenProcess",
        "api_base",
        "url_file",
        "ascension launcher",
        "belong to the launcher",
        "process existence checked",
    )
    hits = []
    for line in proc.stdout.splitlines():
        low = line.lower()
        if any(n.lower() in low for n in needles):
            hits.append(line.strip())
    return sorted(set(hits))[:80]


# ---------------------------------------------------------------------------
# Traced Bridge run (ground truth)
# ---------------------------------------------------------------------------


@dataclass
class TraceState:
    prefix: Path
    launcher: Path
    started_mono: float = field(default_factory=_mono)
    milestones: List[Dict[str, Any]] = field(default_factory=list)
    seen_roles: Set[str] = field(default_factory=set)
    launcher_linux_pids: Set[int] = field(default_factory=set)
    wrapper_linux_pids: Set[int] = field(default_factory=set)
    real_linux_pids: Set[int] = field(default_factory=set)
    decoy_linux_pids: Set[int] = field(default_factory=set)
    launcher_exit_mono: Optional[float] = None
    real_start_mono: Optional[float] = None
    invoke_mark: int = 0

    def snapshot(self, label: str, extra: Optional[Dict[str, Any]] = None) -> None:
        invoke_text = _read_invoke_log(self.prefix)
        invoke_delta = invoke_text[self.invoke_mark :] if self.invoke_mark else invoke_text
        if len(invoke_text) != self.invoke_mark:
            self.invoke_mark = len(invoke_text)
        entry: Dict[str, Any] = {
            "label": label,
            "at_utc": _utc(),
            "elapsed_sec": round(_mono() - self.started_mono, 3),
            "linux_processes": _linux_process_snapshot(str(self.prefix)),
            "wine_tasklist": wine_tasklist_snapshot(str(self.prefix)),
            "loopback_listeners": loopback_listeners_snapshot(),
            "invoke_parsed": _parse_invoke_tail(invoke_delta),
            "invoke_tail": invoke_text[-1500:],
            "output_bytes": _output_log_size(self.prefix),
        }
        if extra:
            entry.update(extra)
        self.milestones.append(entry)
        self._update_role_tracking(entry["linux_processes"])

    def _update_role_tracking(self, procs: List[Dict[str, Any]]) -> None:
        current_launcher = {p["linux_pid"] for p in procs if p["role"] == "launcher"}
        current_wrapper = {p["linux_pid"] for p in procs if p["role"] == "sidecar_wrapper"}
        current_real = {p["linux_pid"] for p in procs if p["role"] == "sidecar_real"}
        current_decoy = {p["linux_pid"] for p in procs if p["role"] == "decoy"}
        if current_launcher and "launcher" not in self.seen_roles:
            self.seen_roles.add("launcher")
        if current_wrapper and "wrapper" not in self.seen_roles:
            self.seen_roles.add("wrapper")
        if current_real and "real" not in self.seen_roles:
            self.seen_roles.add("real")
            if self.real_start_mono is None:
                self.real_start_mono = _mono()
        if current_decoy:
            self.decoy_linux_pids = current_decoy
        if self.launcher_linux_pids and not current_launcher and self.launcher_exit_mono is None:
            self.launcher_exit_mono = _mono()
        self.launcher_linux_pids = current_launcher or self.launcher_linux_pids
        self.wrapper_linux_pids = current_wrapper or self.wrapper_linux_pids
        self.real_linux_pids = current_real or self.real_linux_pids


def run_traced_bridge_c7(experiment_id: str = "TRACE_C7_process_ground_truth") -> Dict[str, Any]:
    from alma_bridge.learning.orchestrator import BridgeOrchestrator
    from alma_bridge.schemas.models import BridgeRequest

    cleanup_all_validation_wine()
    dest = BASELINE_ROOT / experiment_id
    _clone_prefix(SOURCE_SNAPSHOT, dest)
    subprocess.run(["chmod", "-R", "u+w", str(dest)], check=False)
    cleanup_wine_prefix(dest)

    launcher = resolve_launcher_in_prefix(dest)
    if not launcher:
        raise FileNotFoundError(f"No launcher in {dest}")

    _configure_campaign_guard()
    trace = TraceState(prefix=dest, launcher=launcher)
    trace.snapshot("pre_launch")

    bridge_result: Dict[str, Any] = {}
    bridge_error: List[str] = []

    def _run_bridge() -> None:
        try:
            request = BridgeRequest(
                file_path=str(launcher),
                wine_prefix=str(dest),
                max_attempts=2,
            )
            result = BridgeOrchestrator().run(request)
            bridge_result["payload"] = {
                "session_id": result.session_id,
                "success": result.success,
                "summary": result.summary,
                "attempt_count": len(result.attempts),
                "last_signature": result.attempts[-1].error_signature if result.attempts else None,
            }
        except Exception as exc:  # noqa: BLE001
            bridge_error.append(str(exc))

    thread = threading.Thread(target=_run_bridge, daemon=True)
    thread.start()
    deadline = _mono() + MAX_BRIDGE_SEC
    labels_emitted: Set[str] = set()

    while thread.is_alive() and _mono() < deadline:
        procs = _linux_process_snapshot(str(dest))
        roles = {p["role"] for p in procs}
        if "launcher" in roles and "launcher_start" not in labels_emitted:
            trace.snapshot("launcher_start")
            labels_emitted.add("launcher_start")
        if "sidecar_wrapper" in roles and "wrapper_start" not in labels_emitted:
            trace.snapshot("wrapper_start")
            labels_emitted.add("wrapper_start")
        if "sidecar_real" in roles and "real_start" not in labels_emitted:
            trace.snapshot("real_start")
            labels_emitted.add("real_start")
        if trace.launcher_linux_pids and "launcher" not in roles and "launcher_death" not in labels_emitted:
            trace.snapshot("launcher_death")
            labels_emitted.add("launcher_death")
        if trace.real_start_mono and "silent_crash_threshold" not in labels_emitted:
            if _mono() - trace.real_start_mono >= SIDECAR_SILENT_CRASH_SEC:
                trace.snapshot("silent_crash_threshold")
                labels_emitted.add("silent_crash_threshold")
        time.sleep(TRACE_POLL_SEC)

    thread.join(timeout=5)
    trace.snapshot("verification_time", extra={"bridge_done": not thread.is_alive()})

    # url-file survey (most recent)
    temp_dir = dest / "drive_c/users/joshua/Temp"
    url_files = sorted(temp_dir.glob("ascension-services-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]

    resources = launcher.parent / "resources"
    real_exe = resources / "AscensionClientServices.real.exe"
    decoy = resources / "alma-guard" / launcher.name

    record: Dict[str, Any] = {
        "experiment_id": experiment_id,
        "started_at_utc": _utc(),
        "prefix": str(dest),
        "launcher": str(launcher),
        "bridge": bridge_result.get("payload"),
        "bridge_error": bridge_error,
        "milestones": trace.milestones,
        "survival_summary": {
            "launcher_linux_pids_at_death": sorted(trace.launcher_linux_pids),
            "wrapper_linux_pids_last_seen": sorted(trace.wrapper_linux_pids),
            "real_linux_pids_last_seen": sorted(trace.real_linux_pids),
            "decoy_linux_pids_last_seen": sorted(trace.decoy_linux_pids),
            "launcher_exit_elapsed_sec": (
                round(trace.launcher_exit_mono - trace.started_mono, 3)
                if trace.launcher_exit_mono
                else None
            ),
            "real_start_elapsed_sec": (
                round(trace.real_start_mono - trace.started_mono, 3) if trace.real_start_mono else None
            ),
        },
        "guard_contract_strings": extract_sidecar_guard_strings(real_exe),
        "decoy_identity": {
            "decoy_path": str(decoy),
            "decoy_pe": pe_metadata(decoy),
            "decoy_version_strings": pe_version_strings(decoy),
            "launcher_pe": pe_metadata(launcher),
            "launcher_version_strings": pe_version_strings(launcher),
        },
        "url_files_recent": [
            {
                "path": str(p),
                "mtime_utc": datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc).isoformat(),
                "contents": p.read_text(encoding="utf-8", errors="replace"),
            }
            for p in url_files
            if p.is_file()
        ],
        "primary_hash": prefix_aggregate_hash(PRIMARY_PREFIX),
        "source_hash": prefix_aggregate_hash(SOURCE_SNAPSHOT),
        "completed_at_utc": _utc(),
    }
    return record


# ---------------------------------------------------------------------------
# Control experiments
# ---------------------------------------------------------------------------


def _resources_for(prefix: Path) -> Path:
    launcher = resolve_launcher_in_prefix(prefix)
    if not launcher:
        raise FileNotFoundError(prefix)
    return launcher.parent / "resources"


def restore_vendor_sidecar(prefix: Path) -> Dict[str, Any]:
    """Control P: remove Alma wrapper; restore vendor AscensionClientServices.exe."""
    resources = _resources_for(prefix)
    wrapper = resources / "AscensionClientServices.exe"
    real = resources / "AscensionClientServices.real.exe"
    actions: Dict[str, Any] = {"resources": str(resources)}
    if not real.is_file():
        actions["status"] = "skipped"
        actions["reason"] = "no .real.exe"
        return actions
    # Remove Alma wrapper overlay; vendor binary becomes the sidecar entrypoint.
    if wrapper.is_file():
        wrapper.unlink()
    shutil.copy2(real, wrapper)
    actions["status"] = "restored_vendor_sidecar"
    actions["sidecar_sha256"] = sha256_file(wrapper)
    return actions


def install_diag_wrapper(prefix: Path) -> Dict[str, Any]:
    """Control D: install cs_wrapper_diag (passthrough launcher PID)."""
    cc = shutil.which("x86_64-w64-mingw32-gcc")
    src = REPO / "tools/diagnostics/cs_wrapper_diag.c"
    resources = _resources_for(prefix)
    if not cc or not src.is_file():
        return {"status": "unavailable", "reason": "mingw or source missing"}
    out = Path.home() / ".local/share/alma-bridge/tools/cs_wrapper_diag.exe"
    out.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        [cc, "-municode", "-O2", "-s", "-o", str(out), str(src)],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if proc.returncode != 0 or not out.is_file():
        return {"status": "build_failed", "stderr": proc.stderr[-500:]}
    sidecar = resources / "AscensionClientServices.exe"
    real = resources / "AscensionClientServices.real.exe"
    if not real.is_file() and sidecar.is_file():
        shutil.move(str(sidecar), str(real))
    shutil.copy2(out, sidecar)
    from alma_bridge.compatibility.electron_wine import install_launcher_decoy

    decoy = install_launcher_decoy(resources, "Ascension Launcher.exe")
    return {"status": "installed", "wrapper": str(sidecar), "decoy": decoy}


def _run_launcher_with_trace(
    prefix: Path,
    *,
    label: str,
    prep: Callable[[Path], Dict[str, Any]],
    max_sec: float = 90,
) -> Dict[str, Any]:
    cleanup_wine_prefix(prefix)
    subprocess.run(["chmod", "-R", "u+w", str(prefix)], check=False)
    launcher = resolve_launcher_in_prefix(prefix)
    if not launcher:
        raise FileNotFoundError(prefix)
    prep_report = prep(prefix)
    for name in ("alma-cs-invoke.log", "alma-cs-output.log"):
        p = prefix / "drive_c" / name
        if p.exists():
            p.unlink()
    trace = TraceState(prefix=prefix, launcher=launcher)
    trace.snapshot("pre_launch")
    env = {
        **os.environ,
        "WINEPREFIX": str(prefix),
        "WINEDEBUG": "-all",
        "ELECTRON_DISABLE_CRASH_REPORTER": "1",
        "ALMA_LAUNCHER_EXE_NAME": "Ascension Launcher.exe",
        "DISPLAY": os.environ.get("DISPLAY", ":0"),
    }
    cmd = ["wine", str(launcher)]
    proc = subprocess.Popen(cmd, cwd=str(launcher.parent), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    deadline = _mono() + max_sec
    labels: Set[str] = set()
    exit_code: Optional[int] = None
    while _mono() < deadline:
        if proc.poll() is not None:
            exit_code = proc.returncode
            break
        procs = _linux_process_snapshot(str(prefix))
        roles = {p["role"] for p in procs}
        for role, lbl in (
            ("launcher", "launcher_start"),
            ("sidecar_wrapper", "wrapper_start"),
            ("sidecar_real", "real_start"),
        ):
            if role in roles and lbl not in labels:
                trace.snapshot(lbl)
                labels.add(lbl)
        if trace.launcher_linux_pids and "launcher" not in roles and "launcher_death" not in labels:
            trace.snapshot("launcher_death")
            labels.add("launcher_death")
        if trace.real_start_mono and "silent_crash_threshold" not in labels:
            if _mono() - trace.real_start_mono >= SIDECAR_SILENT_CRASH_SEC:
                trace.snapshot("silent_crash_threshold")
                labels.add("silent_crash_threshold")
        time.sleep(TRACE_POLL_SEC)
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        exit_code = proc.returncode
    trace.snapshot("verification_time")
    cleanup_wine_prefix(prefix)
    return {
        "label": label,
        "prep": prep_report,
        "launcher_exit_code": exit_code,
        "milestones": trace.milestones,
        "invoke_parsed": _parse_invoke_tail(_read_invoke_log(prefix)),
        "output_bytes": _output_log_size(prefix),
        "survival_summary": {
            "wrapper_linux_pids_last_seen": sorted(trace.wrapper_linux_pids),
            "real_linux_pids_last_seen": sorted(trace.real_linux_pids),
            "decoy_linux_pids_last_seen": sorted(trace.decoy_linux_pids),
        },
    }


def run_control_p(experiment_id: str = "CTRL_P_vendor_sidecar") -> Dict[str, Any]:
    dest = BASELINE_ROOT / experiment_id
    if dest.exists():
        shutil.rmtree(dest)
    _clone_prefix(SOURCE_SNAPSHOT, dest)
    subprocess.run(["chmod", "-R", "u+w", str(dest)], check=False)
    from alma_bridge.compatibility.ascension_layout import quarantine_stale_ascension_flat_layout
    from alma_bridge.compatibility.electron_wine import install_elevate_passthrough

    launcher = resolve_launcher_in_prefix(dest)
    resources = launcher.parent / "resources"  # type: ignore[union-attr]

    def prep(prefix: Path) -> Dict[str, Any]:
        q = quarantine_stale_ascension_flat_layout(str(prefix), str(launcher))
        elev = install_elevate_passthrough(resources)
        vendor = restore_vendor_sidecar(prefix)
        return {"quarantine": q, "elevate": elev, "vendor_sidecar": vendor}

    return _run_launcher_with_trace(dest, label="control_p", prep=prep)


def run_control_d(experiment_id: str = "CTRL_D_passthrough_launcher_pid") -> Dict[str, Any]:
    dest = BASELINE_ROOT / experiment_id
    if dest.exists():
        shutil.rmtree(dest)
    _clone_prefix(SOURCE_SNAPSHOT, dest)
    subprocess.run(["chmod", "-R", "u+w", str(dest)], check=False)
    from alma_bridge.compatibility.ascension_layout import quarantine_stale_ascension_flat_layout
    from alma_bridge.compatibility.electron_wine import install_elevate_passthrough

    launcher = resolve_launcher_in_prefix(dest)

    def prep(prefix: Path) -> Dict[str, Any]:
        q = quarantine_stale_ascension_flat_layout(str(prefix), str(launcher))
        elev = install_elevate_passthrough(_resources_for(prefix))
        diag = install_diag_wrapper(prefix)
        return {"quarantine": q, "elevate": elev, "diag_wrapper": diag}

    return _run_launcher_with_trace(dest, label="control_d", prep=prep)


class _ConnRecorder(BaseHTTPRequestHandler):
    server_version = "SidecarIPCProbe/1.0"
    recorded: List[Dict[str, Any]] = []

    def log_message(self, fmt: str, *args: Any) -> None:
        return

    def _record(self, method: str) -> None:
        self.__class__.recorded.append(
            {
                "at_utc": _utc(),
                "method": method,
                "path": self.path,
                "headers": {k: v for k, v in self.headers.items()},
            }
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def do_GET(self) -> None:
        self._record("GET")

    def do_POST(self) -> None:
        self._record("POST")


def run_control_i(experiment_id: str = "CTRL_I_loopback_listener", hold_sec: float = 20) -> Dict[str, Any]:
    """Observe whether .real.exe connects to a live loopback api_base_url."""
    dest = BASELINE_ROOT / experiment_id
    if dest.exists():
        shutil.rmtree(dest)
    _clone_prefix(SOURCE_SNAPSHOT, dest)
    subprocess.run(["chmod", "-R", "u+w", str(dest)], check=False)
    cleanup_wine_prefix(dest)

    launcher = resolve_launcher_in_prefix(dest)
    resources = launcher.parent / "resources"  # type: ignore[union-attr]
    real = resources / "AscensionClientServices.real.exe"
    decoy = resources / "alma-guard" / launcher.name  # type: ignore[union-attr]

    from alma_bridge.compatibility.electron_wine import install_launcher_decoy

    install_launcher_decoy(resources, launcher.name)  # type: ignore[union-attr]

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()

    _ConnRecorder.recorded = []
    httpd = HTTPServer(("127.0.0.1", port), _ConnRecorder)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    temp = dest / "drive_c/users/joshua/Temp"
    temp.mkdir(parents=True, exist_ok=True)
    url_name = "ascension-services-ctrl-i.json"
    url_win = f"C:\\users\\joshua\\Temp\\{url_name}"
    url_path = temp / url_name
    url_path.write_text(json.dumps({"api_base_url": f"http://127.0.0.1:{port}"}), encoding="utf-8")

    env = {
        **os.environ,
        "WINEPREFIX": str(dest),
        "WINEDEBUG": "-all",
        "DISPLAY": os.environ.get("DISPLAY", ":0"),
    }
    # Start decoy to satisfy guard if PID-based check passes
    decoy_proc = subprocess.Popen(
        ["wine", str(decoy), "--alma-decoy"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(1)
    decoy_pid = None
    for p in _linux_process_snapshot(str(dest)):
        if p["role"] == "decoy":
            decoy_pid = p["linux_pid"]
            break

    listeners_before = loopback_listeners_snapshot()
    start = _mono()
    proc = subprocess.run(
        [
            "timeout",
            str(int(hold_sec)),
            "wine",
            str(real),
            "--launcher-pid",
            str(decoy_pid or 0),
            "--token",
            "ctrl-i-probe-token",
            "--url-file",
            url_win,
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    elapsed = _mono() - start
    listeners_after = loopback_listeners_snapshot()
    httpd.shutdown()
    decoy_proc.terminate()
    cleanup_wine_prefix(dest)

    return {
        "experiment_id": experiment_id,
        "probe_port": port,
        "url_file": {"path": str(url_path), "contents": url_path.read_text()},
        "decoy_linux_pid": decoy_pid,
        "sidecar_exit_code": proc.returncode,
        "sidecar_timed_out": proc.returncode == 124,
        "elapsed_sec": round(elapsed, 3),
        "connection_attempts": list(_ConnRecorder.recorded),
        "output_bytes": _output_log_size(dest),
        "listeners_before": listeners_before,
        "listeners_after": listeners_after,
        "stderr_tail": proc.stderr[-2000:],
        "completed_at_utc": _utc(),
    }


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def classify_first_divergence(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Choose exactly one primary classification from collected evidence."""
    trace = evidence.get("trace_c7", {})
    ctrl_p = evidence.get("control_p", {})
    ctrl_d = evidence.get("control_d", {})
    ctrl_i = evidence.get("control_i", {})

    classification = "UNKNOWN"
    rationale: List[str] = []

    conn_attempts = ctrl_i.get("connection_attempts") or []
    output_zero = (trace.get("bridge") or {}).get("last_signature") == "sidecar_silent_crash"
    invoke = ""
    for ms in trace.get("milestones", []):
        invoke += ms.get("invoke_tail", "")
    decoy_windows = re.search(r"decoy_pid=(\d+)", invoke)
    guard_strings = trace.get("guard_contract_strings", [])
    has_name_check = any("belong to the launcher" in s.lower() for s in guard_strings)

    if conn_attempts:
        classification = "SIDECAR_BLOCKS_ON_OTHER_IPC"
        rationale.append("Control I recorded loopback connection attempts; IPC is reachable.")
    elif output_zero and has_name_check:
        # Decoy is launcher_decoy.c — different PE entirely from Ascension Launcher
        decoy_meta = (trace.get("decoy_identity") or {}).get("decoy_pe", {})
        launcher_meta = (trace.get("decoy_identity") or {}).get("launcher_pe", {})
        if decoy_meta.get("sha256") != launcher_meta.get("sha256"):
            classification = "DECOY_IDENTITY_MISMATCH"
            rationale.append("Sidecar strings require launcher identity validation.")
            rationale.append("Decoy SHA differs from canonical launcher PE.")
    elif decoy_windows and output_zero:
        classification = "WINDOWS_LINUX_PID_SEMANTICS"
        rationale.append("Invoke log reports Windows decoy_pid but /proc uses Linux PIDs.")
    elif trace.get("survival_summary", {}).get("launcher_exit_elapsed_sec", 99) < 8 and output_zero:
        classification = "LAUNCHER_LOCAL_API_DISAPPEARS"
        rationale.append("Launcher exits ~4s; url-files reference 127.0.0.1 listener ports.")
        rationale.append("Sidecar produced zero output before silent-crash threshold.")

    # Control P/D comparative refinement
    if ctrl_p.get("output_bytes", 0) > 0 and classification == "ALMA_WRAPPER_CHANGES_RUNTIME_BEHAVIOR":
        pass
    elif ctrl_p.get("launcher_exit_code") == 0 and ctrl_p.get("output_bytes", 0) == 0:
        if classification == "UNKNOWN":
            classification = "NESTED_BUILD_WINE_INCOMPATIBILITY"
            rationale.append("Control P (vendor sidecar, no Alma wrapper) also produced zero sidecar output.")

    return {
        "classification": classification,
        "rationale": rationale,
        "control_p_output_bytes": ctrl_p.get("output_bytes"),
        "control_d_output_bytes": ctrl_d.get("output_bytes"),
        "control_i_connections": len(conn_attempts),
    }


def run_full_investigation() -> Dict[str, Any]:
    IPC_EVIDENCE.mkdir(parents=True, exist_ok=True)
    cleanup_all_validation_wine()

    report: Dict[str, Any] = {
        "started_at_utc": _utc(),
        "phases": {},
    }

    report["phases"]["trace_c7"] = run_traced_bridge_c7()
    (IPC_EVIDENCE / "TRACE_C7_process_ground_truth.json").write_text(
        json.dumps(report["phases"]["trace_c7"], indent=2), encoding="utf-8"
    )
    cleanup_all_validation_wine()

    report["phases"]["control_p"] = run_control_p()
    (IPC_EVIDENCE / "CTRL_P_vendor_sidecar.json").write_text(
        json.dumps(report["phases"]["control_p"], indent=2), encoding="utf-8"
    )
    cleanup_all_validation_wine()

    report["phases"]["control_d"] = run_control_d()
    (IPC_EVIDENCE / "CTRL_D_passthrough_launcher_pid.json").write_text(
        json.dumps(report["phases"]["control_d"], indent=2), encoding="utf-8"
    )
    cleanup_all_validation_wine()

    report["phases"]["control_i"] = run_control_i()
    (IPC_EVIDENCE / "CTRL_I_loopback_listener.json").write_text(
        json.dumps(report["phases"]["control_i"], indent=2), encoding="utf-8"
    )
    cleanup_all_validation_wine()

    report["trace_c7"] = report["phases"]["trace_c7"]
    report["control_p"] = report["phases"]["control_p"]
    report["control_d"] = report["phases"]["control_d"]
    report["control_i"] = report["phases"]["control_i"]
    report["classification"] = classify_first_divergence(report)
    report["completed_at_utc"] = _utc()

    (IPC_EVIDENCE / "sidecar_ipc_investigation.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    return report


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Ascension sidecar IPC investigation")
    parser.add_argument("--cleanup-only", action="store_true")
    parser.add_argument("--trace-c7", action="store_true")
    parser.add_argument("--control-p", action="store_true")
    parser.add_argument("--control-d", action="store_true")
    parser.add_argument("--control-i", action="store_true")
    parser.add_argument("--full", action="store_true", help="Run all phases sequentially")
    args = parser.parse_args()

    if args.cleanup_only:
        cleanup_all_validation_wine()
        print(json.dumps({"status": "cleaned"}, indent=2))
        return

    if args.full:
        print(json.dumps(run_full_investigation(), indent=2))
        return
    if args.trace_c7:
        cleanup_all_validation_wine()
        out = run_traced_bridge_c7()
        IPC_EVIDENCE.mkdir(parents=True, exist_ok=True)
        (IPC_EVIDENCE / "TRACE_C7_process_ground_truth.json").write_text(json.dumps(out, indent=2))
        cleanup_all_validation_wine()
        print(json.dumps(out, indent=2))
        return
    if args.control_p:
        out = run_control_p()
        cleanup_all_validation_wine()
        print(json.dumps(out, indent=2))
        return
    if args.control_d:
        out = run_control_d()
        cleanup_all_validation_wine()
        print(json.dumps(out, indent=2))
        return
    if args.control_i:
        out = run_control_i()
        cleanup_all_validation_wine()
        print(json.dumps(out, indent=2))
        return
    parser.print_help()


if __name__ == "__main__":
    main()
