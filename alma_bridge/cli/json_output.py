"""Machine-readable JSON output for Alma CLI."""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional


def emit_json(payload: Dict[str, Any], *, ok: bool = True) -> None:
    """Write JSON-only payload to stdout."""
    envelope = {"ok": ok, **payload}
    sys.stdout.write(json.dumps(envelope, indent=2, sort_keys=True))
    sys.stdout.write("\n")
    sys.stdout.flush()


def emit_error(
    command: str,
    message: str,
    *,
    code: str = "error",
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Write JSON error envelope to stdout; human hint to stderr."""
    payload: Dict[str, Any] = {
        "command": command,
        "error": message,
        "code": code,
    }
    if details:
        payload["details"] = details
    emit_json(payload, ok=False)
    sys.stderr.write(f"{message}\n")
    sys.stderr.flush()
