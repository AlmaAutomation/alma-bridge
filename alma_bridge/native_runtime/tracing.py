"""Lightweight tracing for native runtime (stderr of worker)."""

from __future__ import annotations

import os
from typing import Optional

_ENABLED = os.environ.get("ALMA_NATIVE_RUNTIME_TRACE", "").lower() in ("1", "true", "yes")


def trace(message: str, *, enabled: Optional[bool] = None) -> None:
    if enabled if enabled is not None else _ENABLED:
        import sys

        print(f"[native_runtime] {message}", file=sys.stderr, flush=True)
