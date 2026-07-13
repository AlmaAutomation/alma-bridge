from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Dict, List

from alma_bridge.config import settings
from alma_bridge.storage.outcomes import _connect


def export_training_dataset(output_path: Path) -> Dict[str, Any]:
    """Export attempt outcomes as JSONL for future ML training."""
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                a.*,
                s.file_path,
                s.file_hash,
                s.hardware_profile
            FROM bridge_attempts a
            JOIN bridge_sessions s ON s.session_id = a.session_id
            ORDER BY a.id ASC
            """
        ).fetchall()

    records: List[Dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["command"] = json.loads(item.get("command") or "[]")
        item["env"] = json.loads(item.get("env") or "{}")
        item["hardware_profile"] = json.loads(item.get("hardware_profile") or "{}")
        item["success"] = bool(item.get("success"))
        records.append(item)

    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record) + "\n")

    return {"records": len(records), "output_path": str(output_path)}


def export_csv_summary(output_path: Path) -> Dict[str, Any]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT strategy_id, remediation_id, error_signature, success, COUNT(*) AS count
            FROM bridge_attempts
            GROUP BY strategy_id, remediation_id, error_signature, success
            ORDER BY count DESC
            """
        ).fetchall()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["strategy_id", "remediation_id", "error_signature", "success", "count"],
        )
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "strategy_id": row["strategy_id"],
                    "remediation_id": row["remediation_id"],
                    "error_signature": row["error_signature"],
                    "success": bool(row["success"]),
                    "count": row["count"],
                }
            )

    return {"rows": len(rows), "output_path": str(output_path)}
