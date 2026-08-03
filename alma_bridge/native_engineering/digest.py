"""Deterministic digests for native engineering artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_json_dumps(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def digest_of(data: Any) -> str:
    payload = stable_json_dumps(data)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
