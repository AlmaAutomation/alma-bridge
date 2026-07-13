from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from alma_bridge.execution.runner import file_hash
from alma_bridge.hardware.profiler import profile_hardware
from alma_bridge.importers.mappings import (
    SYSDET_RUNTIME_TO_STRATEGY,
    normalize_error_signature,
)
from alma_bridge.learning.training import normalize_strategy_id
from alma_bridge.storage import outcomes


def import_sysdet_history(
    db_path: Path,
    *,
    limit: Optional[int] = None,
    skip_existing: bool = True,
) -> Dict[str, Any]:
    if not db_path.exists():
        return {
            "source": "almasysdet",
            "imported_sessions": 0,
            "imported_attempts": 0,
            "skipped": 0,
            "errors": [f"Database not found: {db_path}"],
        }

    hardware = profile_hardware()
    rows = _fetch_rows(db_path, limit)
    imported_sessions = 0
    imported_attempts = 0
    skipped = 0
    errors: List[str] = []

    for row in rows:
        source_key = f"sysdet:{row['id']}"
        if skip_existing and outcomes.is_imported("almasysdet", source_key):
            skipped += 1
            continue

        try:
            metadata = _parse_json(row.get("metadata"), {})
            telemetry = _parse_json(row.get("telemetry_snapshot"), {})
            command = _parse_json(row.get("command"), [])

            file_path = row.get("file_path") or "unknown"
            digest = row.get("file_hash") or file_hash(file_path)
            started_at = metadata.get("started_at") or row.get("timestamp")
            finished_at = metadata.get("finished_at") or row.get("timestamp")
            duration_ms = _duration_ms(started_at, finished_at)

            session_id = outcomes.import_session(
                file_path=file_path,
                file_hash=digest,
                started_at=started_at,
                finished_at=finished_at,
                success=bool(row.get("success")),
                hardware_profile=_merge_hardware(hardware, telemetry),
                summary=f"Imported from almasysdet execution_history id={row['id']}",
                source="almasysdet",
            )

            runtime = row.get("runtime") or "unknown"
            raw_strategy = metadata.get("strategy_id") or SYSDET_RUNTIME_TO_STRATEGY.get(
                runtime, f"sysdet_{runtime}"
            )
            strategy_id = normalize_strategy_id(raw_strategy, runtime, file_path)
            signature = normalize_error_signature(
                metadata.get("error_signature"),
                row.get("detected_error"),
            )

            outcomes.import_attempt(
                session_id=session_id,
                attempt_number=1,
                strategy_id=strategy_id,
                remediation_id=row.get("remediation_applied"),
                runtime=runtime,
                command=command if isinstance(command, list) else [str(command)],
                env={},
                mode="host",
                success=bool(row.get("success")),
                exit_code=row.get("exit_code"),
                error_signature=signature,
                detected_error=row.get("detected_error"),
                stdout=row.get("stdout") or "",
                stderr=row.get("stderr") or "",
                duration_ms=duration_ms,
                created_at=row.get("timestamp"),
            )
            outcomes.mark_imported("almasysdet", source_key, session_id)
            imported_sessions += 1
            imported_attempts += 1
        except Exception as exc:  # noqa: BLE001
            errors.append(f"sysdet id={row.get('id')}: {exc}")

    return {
        "source": "almasysdet",
        "db_path": str(db_path),
        "imported_sessions": imported_sessions,
        "imported_attempts": imported_attempts,
        "skipped": skipped,
        "errors": errors,
    }


def _fetch_rows(db_path: Path, limit: Optional[int]) -> List[Dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM execution_history ORDER BY id ASC"
    if limit:
        query += f" LIMIT {int(limit)}"
    rows = conn.execute(query).fetchall()
    conn.close()
    return [dict(row) for row in rows]


def _parse_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _duration_ms(started_at: Optional[str], finished_at: Optional[str]) -> int:
    if not started_at or not finished_at:
        return 0
    try:
        start = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(finished_at).replace("Z", "+00:00"))
        return max(int((end - start).total_seconds() * 1000), 0)
    except ValueError:
        return 0


def _merge_hardware(base: Dict[str, Any], telemetry: Dict[str, Any]) -> Dict[str, Any]:
    profile = dict(base)
    if telemetry:
        profile["telemetry"] = telemetry
    profile["import_source"] = "almasysdet"
    return profile
