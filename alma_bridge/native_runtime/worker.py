"""Isolated worker subprocess entrypoint for native runtime."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional


def run_job(job: Dict[str, Any]) -> Dict[str, Any]:
    from alma_bridge.native_runtime.runtime import run_pe_in_workspace

    file_path = job["file_path"]
    argv: Optional[List[str]] = job.get("argv")
    env: Optional[Dict[str, str]] = job.get("env")
    workspace = job.get("workspace")
    ws_path = Path(workspace) if workspace else None
    use_simulation = bool(job.get("use_simulation", False))
    result = run_pe_in_workspace(
        file_path,
        argv=argv,
        env=env,
        workspace=ws_path,
        use_simulation=use_simulation,
    )
    return result.model_dump()


def main(argv: Optional[List[str]] = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print(json.dumps({"error": "usage: worker <job.json>"}), file=sys.stderr)
        return 2
    job_path = Path(args[0])
    job = json.loads(job_path.read_text(encoding="utf-8"))
    result = run_job(job)
    print(json.dumps(result))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
