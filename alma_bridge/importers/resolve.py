from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from alma_bridge.execution.errors import detect_error_signature
from alma_bridge.execution.runner import file_hash
from alma_bridge.hardware.profiler import profile_hardware
from alma_bridge.importers.mappings import RESOLVE_ACTION_TO_REMEDIATION
from alma_bridge.storage import outcomes


def import_resolve_audits(
    audit_dir: Path,
    *,
    runtime_data_dir: Optional[Path] = None,
    skip_existing: bool = True,
) -> Dict[str, Any]:
    if not audit_dir.exists():
        return {
            "source": "alma_resolve",
            "imported_sessions": 0,
            "imported_attempts": 0,
            "skipped": 0,
            "errors": [f"Audit directory not found: {audit_dir}"],
        }

    runtime_root = runtime_data_dir or audit_dir.parent
    hardware = profile_hardware()
    hardware["import_source"] = "alma_resolve"

    imported_sessions = 0
    imported_attempts = 0
    skipped = 0
    errors: List[str] = []

    for audit_file in sorted(audit_dir.glob("*.json")):
        action = audit_file.stem
        source_key = f"resolve:{action}"
        if skip_existing and outcomes.is_imported("alma_resolve", source_key):
            skipped += 1
            continue

        try:
            payload = json.loads(audit_file.read_text(encoding="utf-8"))
            target_path = payload.get("target_path") or payload.get("prefix_path") or str(audit_file)
            digest = file_hash(target_path) if Path(target_path).exists() else None
            mtime = datetime_from_path(audit_file)

            stderr, stdout = _read_companion_logs(runtime_root, action)
            signature = detect_error_signature(stderr, stdout)
            remediation_id = RESOLVE_ACTION_TO_REMEDIATION.get(action)
            success = _infer_success(action, stderr, stdout)

            session_id = outcomes.import_session(
                file_path=target_path,
                file_hash=digest,
                started_at=mtime,
                finished_at=mtime,
                success=success,
                hardware_profile={
                    **hardware,
                    "resolve": {
                        "action": action,
                        "prefix_path": payload.get("prefix_path"),
                        "script_path": payload.get("script_path"),
                    },
                },
                summary=f"Imported from alma_resolve audit action={action}",
                source="alma_resolve",
            )

            command = [payload.get("script_path", action)]
            outcomes.import_attempt(
                session_id=session_id,
                attempt_number=1,
                strategy_id="wine_host",
                remediation_id=remediation_id,
                runtime="wine",
                command=[str(part) for part in command if part],
                env=_env_from_action(action),
                mode="host",
                success=success,
                exit_code=0 if success else 1,
                error_signature=signature,
                detected_error=signature,
                stdout=stdout,
                stderr=stderr,
                duration_ms=0,
                created_at=mtime,
            )
            outcomes.mark_imported("alma_resolve", source_key, session_id)
            imported_sessions += 1
            imported_attempts += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"resolve {audit_file.name}: {exc}")

    return {
        "source": "alma_resolve",
        "audit_dir": str(audit_dir),
        "imported_sessions": imported_sessions,
        "imported_attempts": imported_attempts,
        "skipped": skipped,
        "errors": errors,
    }


def _read_companion_logs(runtime_root: Path, action: str) -> tuple[str, str]:
    candidates = [
        runtime_root / "launcher_stderr.log",
        runtime_root / "launcher_stdout.log",
        runtime_root / f"{action}.stderr.log",
        runtime_root / f"{action}.stdout.log",
    ]
    stderr = ""
    stdout = ""
    stderr_path = candidates[0]
    stdout_path = candidates[1]
    if stderr_path.exists():
        stderr = stderr_path.read_text(encoding="utf-8", errors="replace")[:8000]
    if stdout_path.exists():
        stdout = stdout_path.read_text(encoding="utf-8", errors="replace")[:8000]
    return stderr, stdout


def _infer_success(action: str, stderr: str, stdout: str) -> bool:
    if action.startswith("capture_"):
        return True
    if action == "reset_launcher_local_state":
        return True
    combined = f"{stderr}\n{stdout}".lower()
    failure_markers = ("error", "failed", "fatal", "segfault", "c0000")
    return not any(marker in combined for marker in failure_markers)


def _env_from_action(action: str) -> Dict[str, str]:
    if action == "test_launcher_with_software_rendering":
        return {"LIBGL_ALWAYS_SOFTWARE": "1", "DXVK_DISABLE": "1"}
    if action == "test_launcher_with_wined3d_fallback":
        return {"DXVK_DISABLE": "1"}
    if action == "test_launcher_with_virtual_desktop":
        return {"ALMA_WINE_VIRTUAL_DESKTOP": "1024x768"}
    if action == "run_launcher_with_wine_debug_logs":
        return {"WINEDEBUG": "+timestamp,+pid,+tid,+seh,+module"}
    return {}


def datetime_from_path(path: Path) -> str:
    from datetime import datetime, timezone

    stamp = path.stat().st_mtime
    return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()
