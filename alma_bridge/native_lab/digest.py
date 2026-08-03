"""Deterministic digests for native lab artifacts."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def stable_json_dumps(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def digest_of(data: Any) -> str:
    payload = stable_json_dumps(data)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_work_item_id(
    provider_id: str,
    capability_id: str,
    behavior_id: str,
    *,
    version: str = "v1",
) -> str:
    key = f"{provider_id}__{capability_id}__{behavior_id}__{version}".replace("/", "_")
    return f"wi_{key}"
