from __future__ import annotations

"""Atomic campaign run evidence persistence."""

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

EVIDENCE_PERSISTENCE_INCOMPLETE = "EVIDENCE_PERSISTENCE_INCOMPLETE"
DB_RECOVERED = "DB_RECOVERED"


@dataclass(frozen=True)
class RunEvidencePaths:
    run_dir: Path
    response_path: Path
    evidence_path: Path
    export_path: Path
    log_path: Path
    metadata_path: Path


def prepare_run_evidence_paths(
    *,
    evidence_root: Path,
    run_number: int,
    logs_root: Optional[Path] = None,
) -> RunEvidencePaths:
    """Create all evidence directories before run execution."""
    run_dir = evidence_root / f"run-{run_number:02d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    if logs_root is not None:
        logs_root.mkdir(parents=True, exist_ok=True)
    return RunEvidencePaths(
        run_dir=run_dir,
        response_path=run_dir / "response.json",
        evidence_path=run_dir / "evidence.json",
        export_path=run_dir / "export.json",
        log_path=(logs_root or evidence_root.parent / "logs") / f"run-{run_number:02d}.log",
        metadata_path=run_dir / "metadata.json",
    )


def persist_run_evidence(
    *,
    paths: RunEvidencePaths,
    response: Dict[str, Any],
    extra: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    export_command: Optional[list[str]] = None,
    export_env: Optional[Dict[str, str]] = None,
    recovery_mode: str = "fresh",
) -> Dict[str, Any]:
    """Persist run evidence atomically. Raises on failure."""
    paths.run_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "run_dir": str(paths.run_dir),
        "session_id": session_id or response.get("session_id"),
        "recovery_mode": recovery_mode,
        "persisted_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "in_progress",
    }
    paths.metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    try:
        paths.response_path.write_text(json.dumps(response, indent=2, sort_keys=True), encoding="utf-8")
        if extra is not None:
            paths.evidence_path.write_text(json.dumps(extra, indent=2, sort_keys=True), encoding="utf-8")
        if session_id and export_command:
            subprocess.run(
                export_command + ["--session-id", session_id, "--output", str(paths.export_path)],
                check=True,
                env=export_env,
            )
        metadata["status"] = "complete"
        paths.metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    except Exception as exc:
        metadata["status"] = EVIDENCE_PERSISTENCE_INCOMPLETE
        metadata["error"] = str(exc)
        try:
            paths.metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        except Exception:
            pass
        raise
    return metadata


def recover_run_evidence_from_db(
    *,
    paths: RunEvidencePaths,
    response: Dict[str, Any],
    extra: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
    export_command: Optional[list[str]] = None,
    export_env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Recover evidence from existing DB session without re-execution."""
    return persist_run_evidence(
        paths=paths,
        response=response,
        extra=extra,
        session_id=session_id,
        export_command=export_command,
        export_env=export_env,
        recovery_mode=DB_RECOVERED,
    )
