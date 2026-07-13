"""Webhook notifications for automation lifecycle events."""

from __future__ import annotations

import json
import urllib.request
from typing import Any, Dict, List, Optional

from alma_bridge.config import settings


def webhook_urls() -> List[str]:
    raw = getattr(settings, "automation_webhook_urls", "") or ""
    return [u.strip() for u in raw.split(",") if u.strip()]


def emit_event(event: str, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """POST ``event`` + payload to configured webhook URLs (best-effort)."""
    urls = webhook_urls()
    if not urls:
        return []
    body = json.dumps({"event": event, "payload": payload}).encode("utf-8")
    results: List[Dict[str, Any]] = []
    for url in urls:
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=8) as resp:  # noqa: S310
                results.append({"url": url, "ok": True, "status": resp.status})
        except Exception as exc:  # noqa: BLE001
            results.append({"url": url, "ok": False, "error": str(exc)})
    return results
