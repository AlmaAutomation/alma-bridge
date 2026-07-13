from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from alma_bridge.compatibility.profile_shadow_validation_store import (
    ensure_validation_tables,
    list_labels,
)
from alma_bridge.compatibility.profile_store import _connect, ensure_profile_tables
from alma_bridge.compatibility.profile_shadow_store import ensure_shadow_tables

_SENSITIVE_ENV_KEYS = re.compile(
    r"(password|secret|token|api[_-]?key|auth|credential|sudo)",
    re.IGNORECASE,
)
_PATH_PATTERN = re.compile(r"(/home/[^/\s]+|/Users/[^/\s]+|C:\\Users\\[^\\]+)")


def _redact_string(value: str) -> str:
    redacted = _PATH_PATTERN.sub("<redacted_path>", value)
    if _SENSITIVE_ENV_KEYS.search(redacted):
        return "<redacted_sensitive>"
    return redacted


def _sanitize_obj(value: Any) -> Any:
    if isinstance(value, str):
        return _redact_string(value)
    if isinstance(value, list):
        return [_sanitize_obj(item) for item in value]
    if isinstance(value, dict):
        sanitized: Dict[str, Any] = {}
        for key, item in value.items():
            if key in {"username", "path_raw", "path_normalized", "path_template"}:
                sanitized[key] = "<redacted>"
                continue
            if key in {"environment", "env", "env_json"} and isinstance(item, dict):
                sanitized[key] = {
                    str(k): (
                        "<redacted_sensitive>"
                        if _SENSITIVE_ENV_KEYS.search(str(k))
                        else "<redacted>"
                    )
                    for k in item
                }
                continue
            sanitized[key] = _sanitize_obj(item)
        return sanitized
    return value


def export_shadow_validation_bundle(
    *,
    shadow_event_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    with _connect() as conn:
        ensure_profile_tables(conn)
        ensure_shadow_tables(conn)
        ensure_validation_tables(conn)

        if session_id and not shadow_event_id:
            row = conn.execute(
                """
                SELECT shadow_event_id FROM compatibility_profile_shadow_predictions
                WHERE session_id = ? ORDER BY created_at DESC LIMIT 1
                """,
                (session_id,),
            ).fetchone()
            shadow_event_id = str(row["shadow_event_id"]) if row else None

        if not shadow_event_id:
            return {"schema": "shadow_validation_export_v1", "records": []}

        prediction = conn.execute(
            "SELECT * FROM compatibility_profile_shadow_predictions WHERE shadow_event_id = ?",
            (shadow_event_id,),
        ).fetchone()
        candidates = conn.execute(
            "SELECT * FROM compatibility_profile_shadow_candidates WHERE shadow_event_id = ?",
            (shadow_event_id,),
        ).fetchall()
        actual = conn.execute(
            "SELECT * FROM compatibility_profile_shadow_actual_outcomes WHERE shadow_event_id = ?",
            (shadow_event_id,),
        ).fetchone()
        comparison = conn.execute(
            "SELECT * FROM compatibility_profile_shadow_comparisons WHERE shadow_event_id = ?",
            (shadow_event_id,),
        ).fetchone()
        run = conn.execute(
            "SELECT * FROM compatibility_profile_shadow_validation_runs WHERE shadow_event_id = ?",
            (shadow_event_id,),
        ).fetchone()
        scenario = None
        if run:
            scenario = conn.execute(
                "SELECT * FROM compatibility_profile_shadow_scenarios WHERE scenario_id = ?",
                (run["scenario_id"],),
            ).fetchone()

    labels = [
        label
        for label in list_labels(shadow_event_id)
    ]

    from alma_bridge.compatibility.profile_shadow_validation_store import list_failure_analyses

    failure_rows = list_failure_analyses(shadow_event_id=shadow_event_id)

    bundle = {
        "schema": "shadow_validation_export_v1",
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "shadow_event_id": shadow_event_id,
        "prediction": _sanitize_obj(dict(prediction)) if prediction else None,
        "candidates": [_sanitize_obj(dict(c)) for c in candidates],
        "actual_outcome": _sanitize_obj(dict(actual)) if actual else None,
        "comparison": _sanitize_obj(dict(comparison)) if comparison else None,
        "validation_run": _sanitize_obj(dict(run)) if run else None,
        "scenario": _sanitize_obj(json.loads(scenario["manifest_json"])) if scenario else None,
        "labels": [_sanitize_obj(label) for label in labels],
        "failure_analyses": [_sanitize_obj(row) for row in failure_rows],
    }
    return bundle


def write_export_file(
    path: Path,
    *,
    shadow_event_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Path:
    bundle = export_shadow_validation_bundle(
        shadow_event_id=shadow_event_id,
        session_id=session_id,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(bundle, indent=2, sort_keys=True), encoding="utf-8")
    return path
