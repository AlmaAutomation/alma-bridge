"""Sandboxed process environment for native runtime."""

from __future__ import annotations

import os
from typing import Dict, Optional


def build_environment(
    base: Optional[Dict[str, str]] = None,
    *,
    workspace: str,
) -> Dict[str, str]:
    env = dict(base or os.environ)
    env["ALMA_NATIVE_WORKSPACE"] = workspace
    return env
