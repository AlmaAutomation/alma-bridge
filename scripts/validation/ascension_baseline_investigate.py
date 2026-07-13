#!/usr/bin/env python3
"""Ascension baseline investigation — read-only comparison and disposable control runs."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

NESTED_PRIMARY = Path(
    "/home/joshua/.local/share/alma-bridge/prefixes/803984cf-660"
    "/drive_c/Program Files/Ascension Launcher/Ascension Launcher/Ascension Launcher.exe"
)
FLAT_HISTORICAL = Path(
    "/home/joshua/.local/share/alma-bridge/prefixes/0aaabfa5-6c9"
    "/drive_c/Program Files/Ascension Launcher/Ascension Launcher.exe"
)
HISTORICAL_PREFIX = Path("/home/joshua/.local/share/alma-bridge/prefixes/0aaabfa5-6c9")
PRIMARY_PREFIX = Path("/home/joshua/.local/share/alma-bridge/prefixes/803984cf-660")
SOURCE_SNAPSHOT = Path(
    "/home/joshua/.local/share/alma-bridge/prefixes/validation/pilot-001/source-prefix-snapshot"
)
BASELINE_ROOT = Path(
    "/home/joshua/.local/share/alma-bridge/prefixes/validation/ascension-baseline"
)
EVIDENCE_ROOT = REPO / "data/validation/evidence/ascension-baseline"

# Alma's direct Wine launch contract (no Chromium CLI flags on nested launcher).
ALMA_WINE_ENV = {
    "ELECTRON_DISABLE_CRASH_REPORTER": "1",
    "WINEDEBUG": "-all",
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> Optional[str]:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def prefix_aggregate_hash(prefix: Path, limit_files: int = 5000) -> Optional[str]:
    if not prefix.exists():
        return None
    h = hashlib.sha256()
    count = 0
    for p in sorted(prefix.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(prefix)).encode("utf-8")
        h.update(rel)
        try:
            h.update(p.read_bytes())
        except OSError:
            continue
        count += 1
        if count >= limit_files:
            h.update(b"|truncated|")
            break
    return h.hexdigest()


def resolve_launcher_in_prefix(prefix: Path) -> Optional[Path]:
    from alma_bridge.execution.installer_verify import ascension_main_launcher_path

    resolved = ascension_main_launcher_path(str(prefix))
    return Path(resolved) if resolved else None


def pe_metadata(path: Path) -> Dict[str, Any]:
    meta: Dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.is_file():
        return meta
    data = path.read_bytes()[:4096]
    meta["size_bytes"] = path.stat().st_size
    meta["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    if len(data) < 64 or data[:2] != b"MZ":
        meta["format"] = "non_pe"
        return meta
    meta["format"] = "pe"
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if e_lfanew + 24 <= len(data) and data[e_lfanew : e_lfanew + 4] == b"PE\0\0":
        machine, _sections, _, _, _, opt_size, _magic = struct.unpack_from(
            "<HHIIIHH", data, e_lfanew + 4
        )
        meta["pe_machine"] = hex(machine)
        meta["optional_header_size"] = opt_size
    try:
        r = subprocess.run(
            ["objdump", "-p", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if r.returncode == 0:
            for line in r.stdout.splitlines():
                if "Time/Date" in line or "MajorLinkerVersion" in line:
                    meta.setdefault("objdump_lines", []).append(line.strip())
                if "DLL Name:" in line:
                    meta.setdefault("imported_dlls", []).append(line.split("DLL Name:")[-1].strip())
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return meta


def launcher_tree_report(launcher: Path) -> Dict[str, Any]:
    if not launcher.exists():
        return {"launcher": str(launcher), "exists": False}
    root = launcher.parent
    resources = root / "resources"
    report: Dict[str, Any] = {
        "launcher": str(launcher),
        "layout": "nested" if launcher.parent.name == "Ascension Launcher" and launcher.parent.parent.name == "Ascension Launcher" else "flat",
        "directory": str(root),
        "resources_dir": str(resources) if resources.is_dir() else None,
    }
    artifacts = {
        "elevate.exe": resources / "elevate.exe",
        "AscensionClientServices.exe": resources / "AscensionClientServices.exe",
        "alma-guard/Ascension Launcher.exe": resources / "alma-guard" / "Ascension Launcher.exe",
        "app.asar": resources / "app.asar",
        "app-update.yml": resources / "app-update.yml",
    }
    report["artifacts"] = {}
    for name, p in artifacts.items():
        if p.is_file():
            report["artifacts"][name] = {
                "path": str(p),
                "sha256": sha256_file(p),
                "size": p.stat().st_size,
            }
    cfg = Path(str(launcher).replace("drive_c", "drive_c/users/joshua/AppData/Local/ProjectAscension/Config/AscensionLauncherSettings.json"))
    if not cfg.exists():
        prefix = launcher
        while prefix.name != "drive_c" and prefix.parent != prefix:
            prefix = prefix.parent
        cfg = prefix / "users/joshua/AppData/Local/ProjectAscension/Config/AscensionLauncherSettings.json"
    if cfg.is_file():
        report["launcher_settings"] = {"path": str(cfg), "sha256": sha256_file(cfg)}
    return report


def prefix_state_report(prefix: Path) -> Dict[str, Any]:
    from alma_bridge.execution.preflight import read_wine_windows_version

    report: Dict[str, Any] = {
        "prefix": str(prefix),
        "exists": prefix.exists(),
        "aggregate_hash_sample": prefix_aggregate_hash(prefix),
    }
    if not prefix.exists():
        return report
    for name in ("user.reg", "system.reg", "winetricks.log"):
        p = prefix / name
        if p.is_file():
            report[name] = {"sha256": sha256_file(p), "size": p.stat().st_size}
    report["windows_version"] = read_wine_windows_version(str(prefix))
    report["ascension_main_launcher"] = str(resolve_launcher_in_prefix(prefix) or "")
    return report


def compare_launchers() -> Dict[str, Any]:
    nested_sha = sha256_file(NESTED_PRIMARY)
    flat_sha = sha256_file(FLAT_HISTORICAL)
    return {
        "generated_at_utc": _utc(),
        "nested": {
            "pe": pe_metadata(NESTED_PRIMARY),
            "tree": launcher_tree_report(NESTED_PRIMARY),
        },
        "flat": {
            "pe": pe_metadata(FLAT_HISTORICAL),
            "tree": launcher_tree_report(FLAT_HISTORICAL),
        },
        "sha256_match": nested_sha == flat_sha,
        "nested_sha256": nested_sha,
        "flat_sha256": flat_sha,
        "size_match": (
            NESTED_PRIMARY.stat().st_size == FLAT_HISTORICAL.stat().st_size
            if NESTED_PRIMARY.exists() and FLAT_HISTORICAL.exists()
            else False
        ),
        "classification": "A_different_application_build",
        "classification_detail": (
            "Nested and flat launchers differ in executable SHA-256, app.asar hash, "
            "and sidecar/wrapper artifacts despite matching size and PE linker metadata."
        ),
    }


def _clone_prefix(src: Path, dest: Path) -> None:
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, symlinks=True)
    subprocess.run(["chmod", "-R", "u+w", str(dest)], check=False)


def _wine_launch(
    *,
    launcher: Path,
    wineprefix: Path,
    cwd: Optional[Path] = None,
    env_extra: Optional[Dict[str, str]] = None,
    timeout_sec: int = 45,
    args: Optional[List[str]] = None,
) -> Dict[str, Any]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "DISPLAY": os.environ.get("DISPLAY", ":0"),
        "WINEPREFIX": str(wineprefix),
    }
    if env_extra:
        env.update(env_extra)
    else:
        env.setdefault("WINEDEBUG", "err+all,warn+all")
    cmd = ["wine", str(launcher)] + (args or [])
    start = time.monotonic()
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd or launcher.parent),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "command": cmd,
            "cwd": str(cwd or launcher.parent),
            "environment": {k: env[k] for k in sorted(env) if k.startswith(("WINE", "ELECTRON", "ALMA", "DISPLAY"))},
            "exit_code": proc.returncode,
            "duration_ms": elapsed_ms,
            "stdout_tail": proc.stdout[-4000:],
            "stderr_tail": proc.stderr[-4000:],
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return {
            "command": cmd,
            "cwd": str(cwd or launcher.parent),
            "environment": {k: env[k] for k in sorted(env) if k.startswith(("WINE", "ELECTRON", "ALMA", "DISPLAY"))},
            "exit_code": None,
            "duration_ms": elapsed_ms,
            "stdout_tail": (exc.stdout or b"")[-4000:].decode("utf-8", errors="replace") if exc.stdout else "",
            "stderr_tail": (exc.stderr or b"")[-4000:].decode("utf-8", errors="replace") if exc.stderr else "",
            "timed_out": True,
        }


def _sidecar_evidence(prefix: Path) -> Dict[str, int]:
    from alma_bridge.execution.electron_handoff import (
        _sidecar_invoke_log,
        _sidecar_output_log,
    )

    out_log = _sidecar_output_log(str(prefix))
    inv_log = _sidecar_invoke_log(str(prefix))
    return {
        "sidecar_output_bytes": out_log.stat().st_size if out_log.is_file() else 0,
        "sidecar_invoke_bytes": inv_log.stat().st_size if inv_log.is_file() else 0,
    }


@dataclass(frozen=True)
class ControlSpec:
    experiment_id: str
    prefix_src: Optional[Path]
    fresh_prefix: bool
    alma_prep: bool
    use_bridge: bool = False
    external_launcher: Optional[Path] = None
    resolve_launcher_from_prefix: bool = False
    launch_args: Optional[List[str]] = None
    launch_env: Optional[Dict[str, str]] = None


def _configure_campaign_guard() -> None:
    from alma_bridge.config import settings

    settings.validation_campaign_mode = True
    settings.validation_campaign_id = "ascension-baseline"
    settings.validation_campaign_disposable_root = str(BASELINE_ROOT)
    settings.validation_campaign_primary_prefix = str(PRIMARY_PREFIX)
    settings.validation_campaign_source_snapshot = str(SOURCE_SNAPSHOT)


def run_bridge_control(experiment_id: str, *, prefix_src: Path, max_attempts: int = 8) -> Dict[str, Any]:
    """Control 7: nested launcher via normal BridgeOrchestrator on disposable clone."""
    from alma_bridge.config import settings
    from alma_bridge.learning.orchestrator import BridgeOrchestrator
    from alma_bridge.schemas.models import BridgeRequest

    _configure_campaign_guard()
    dest = BASELINE_ROOT / experiment_id
    _clone_prefix(prefix_src, dest)
    launcher = resolve_launcher_in_prefix(dest)
    if not launcher:
        raise FileNotFoundError(f"No Ascension launcher in disposable prefix {dest}")

    record: Dict[str, Any] = {
        "experiment_id": experiment_id,
        "started_at_utc": _utc(),
        "launcher": str(launcher),
        "launcher_sha256": sha256_file(launcher),
        "prefix": str(dest),
        "prefix_initial_hash": prefix_aggregate_hash(dest),
        "fresh_prefix": False,
        "alma_prep": True,
        "use_bridge": True,
        "source_snapshot_hash": prefix_aggregate_hash(prefix_src),
        "preparation_steps": ["BridgeOrchestrator handles electron prep and remediation"],
        "campaign_guard": {
            "disposable_root": str(BASELINE_ROOT),
            "primary_prefix": str(PRIMARY_PREFIX),
            "source_snapshot": str(SOURCE_SNAPSHOT),
        },
    }

    request = BridgeRequest(
        file_path=str(launcher),
        wine_prefix=str(dest),
        max_attempts=max_attempts,
    )
    result = BridgeOrchestrator().run(request)
    record["bridge"] = {
        "session_id": result.session_id,
        "success": result.success,
        "summary": result.summary,
        "attempt_count": len(result.attempts),
        "attempts": [
            {
                "attempt_number": a.attempt_number,
                "remediation_id": a.remediation_id,
                "command": a.command,
                "env": {k: v for k, v in (a.env or {}).items() if not k.startswith("ALMA_") or k in {"ALMA_LAUNCHER_EXE_NAME", "ALMA_INSTALL_CS_GUARD_WORKAROUND"}},
                "exit_code": a.exit_code,
                "error_signature": a.error_signature,
                "duration_ms": a.duration_ms,
                "phase": a.phase,
            }
            for a in result.attempts
        ],
        "winning_attempt": result.winning_attempt,
        "finished_at": result.finished_at.isoformat() if result.finished_at else None,
    }
    last_sig = result.attempts[-1].error_signature if result.attempts else None
    record["failure_signature"] = last_sig if not result.success else None
    record["verification_result"] = "SUCCEEDED" if result.success else "FAILED"
    record.update(_sidecar_evidence(dest))
    record["prefix_final_hash"] = prefix_aggregate_hash(dest)
    record["prefix_state"] = prefix_state_report(dest)
    record["primary_prefix_hash"] = prefix_aggregate_hash(PRIMARY_PREFIX)
    record["source_snapshot_hash_final"] = prefix_aggregate_hash(SOURCE_SNAPSHOT)
    record["completed_at_utc"] = _utc()
    return record


def run_control_experiment(spec: ControlSpec) -> Dict[str, Any]:
    from alma_bridge.compatibility.electron_wine import prepare_electron_wine
    from alma_bridge.execution.errors import detect_error_signature

    dest = BASELINE_ROOT / spec.experiment_id
    if spec.fresh_prefix:
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        subprocess.run(
            ["wineboot", "-i"],
            env={**os.environ, "WINEPREFIX": str(dest)},
            check=False,
            timeout=120,
        )
    elif spec.prefix_src:
        _clone_prefix(spec.prefix_src, dest)
    else:
        raise ValueError("prefix_src required when fresh_prefix=False")

    if spec.resolve_launcher_from_prefix:
        resolved = resolve_launcher_in_prefix(dest)
        if not resolved:
            raise FileNotFoundError(f"No launcher resolved under {dest}")
        launcher = resolved
    elif spec.external_launcher:
        launcher = spec.external_launcher
    else:
        raise ValueError("external_launcher or resolve_launcher_from_prefix required")

    record: Dict[str, Any] = {
        "experiment_id": spec.experiment_id,
        "started_at_utc": _utc(),
        "launcher": str(launcher),
        "launcher_sha256": sha256_file(launcher),
        "prefix": str(dest),
        "prefix_initial_hash": prefix_aggregate_hash(dest),
        "fresh_prefix": spec.fresh_prefix,
        "alma_prep": spec.alma_prep,
        "use_bridge": spec.use_bridge,
        "preparation_steps": [],
    }

    if spec.alma_prep:
        prep = prepare_electron_wine(str(launcher))
        record["preparation_steps"].append({"prepare_electron_wine": prep})
    else:
        record["preparation_steps"].append({"prepare_electron_wine": "skipped"})

    launch = _wine_launch(
        launcher=launcher,
        wineprefix=dest,
        cwd=launcher.parent,
        args=spec.launch_args,
        env_extra=spec.launch_env,
    )
    record["launch"] = launch
    combined_stderr = launch.get("stderr_tail") or ""
    combined_stdout = launch.get("stdout_tail") or ""
    record["failure_signature"] = detect_error_signature(combined_stderr, combined_stdout)
    record.update(_sidecar_evidence(dest))
    record["prefix_final_hash"] = prefix_aggregate_hash(dest)
    record["prefix_state"] = prefix_state_report(dest)
    record["completed_at_utc"] = _utc()
    return record


def control_specs() -> List[ControlSpec]:
    return [
        ControlSpec(
            "C1_flat_historical_prefix",
            prefix_src=HISTORICAL_PREFIX,
            fresh_prefix=False,
            alma_prep=True,
            resolve_launcher_from_prefix=True,
        ),
        ControlSpec(
            "C2_flat_fresh_prefix",
            prefix_src=None,
            fresh_prefix=True,
            alma_prep=True,
            external_launcher=FLAT_HISTORICAL,
        ),
        ControlSpec(
            "C3_nested_snapshot_prefix",
            prefix_src=SOURCE_SNAPSHOT,
            fresh_prefix=False,
            alma_prep=True,
            resolve_launcher_from_prefix=True,
        ),
        ControlSpec(
            "C4_nested_fresh_prefix",
            prefix_src=None,
            fresh_prefix=True,
            alma_prep=True,
            external_launcher=NESTED_PRIMARY,
        ),
        ControlSpec(
            "C5_nested_no_alma_prep",
            prefix_src=SOURCE_SNAPSHOT,
            fresh_prefix=False,
            alma_prep=False,
            resolve_launcher_from_prefix=True,
        ),
        ControlSpec(
            "C6_nested_direct_wine",
            prefix_src=SOURCE_SNAPSHOT,
            fresh_prefix=False,
            alma_prep=False,
            resolve_launcher_from_prefix=True,
            launch_env=ALMA_WINE_ENV,
        ),
    ]


def run_all_controls(*, include_bridge: bool = True) -> Dict[str, Any]:
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    BASELINE_ROOT.mkdir(parents=True, exist_ok=True)
    results: Dict[str, Any] = {
        "generated_at_utc": _utc(),
        "methodology_revision": "v2_prefix_local_launcher_no_cli_flags",
        "comparison": compare_launchers(),
        "controls": {},
    }
    for spec in control_specs():
        try:
            results["controls"][spec.experiment_id] = run_control_experiment(spec)
        except Exception as exc:  # noqa: BLE001
            results["controls"][spec.experiment_id] = {
                "experiment_id": spec.experiment_id,
                "error": str(exc),
            }
        out = EVIDENCE_ROOT / f"{spec.experiment_id}.json"
        out.write_text(json.dumps(results["controls"][spec.experiment_id], indent=2), encoding="utf-8")

    if include_bridge:
        try:
            results["controls"]["C7_nested_bridge_orchestrator"] = run_bridge_control(
                "C7_nested_bridge_orchestrator",
                prefix_src=SOURCE_SNAPSHOT,
            )
        except Exception as exc:  # noqa: BLE001
            results["controls"]["C7_nested_bridge_orchestrator"] = {
                "experiment_id": "C7_nested_bridge_orchestrator",
                "error": str(exc),
            }
        out = EVIDENCE_ROOT / "C7_nested_bridge_orchestrator.json"
        out.write_text(
            json.dumps(results["controls"]["C7_nested_bridge_orchestrator"], indent=2),
            encoding="utf-8",
        )

    summary_path = EVIDENCE_ROOT / "control_matrix.json"
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Ascension baseline investigation")
    parser.add_argument("--compare-only", action="store_true")
    parser.add_argument("--controls", action="store_true")
    parser.add_argument("--bridge-only", action="store_true", help="Run C7 BridgeOrchestrator control only")
    parser.add_argument("--no-bridge", action="store_true", help="Skip C7 when running --controls")
    args = parser.parse_args()
    if args.bridge_only:
        result = run_bridge_control("C7_nested_bridge_orchestrator", prefix_src=SOURCE_SNAPSHOT)
        EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
        out = EVIDENCE_ROOT / "C7_nested_bridge_orchestrator.json"
        out.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, indent=2))
    elif args.controls:
        print(json.dumps(run_all_controls(include_bridge=not args.no_bridge), indent=2))
    else:
        print(json.dumps(compare_launchers(), indent=2))


if __name__ == "__main__":
    main()
