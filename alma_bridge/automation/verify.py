"""Post-apply verification — prove the host actually improved."""

from __future__ import annotations

import socket
import ssl
from typing import Any, Dict, List, Optional

from alma_bridge.compliance.modernization.assess import assess_host


def _probe_https(host: str = "example.com", port: int = 443, timeout: float = 6.0) -> Dict[str, Any]:
    ctx = ssl.create_default_context()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert()
                return {
                    "ok": True,
                    "host": host,
                    "protocol": tls.version(),
                    "cipher": tls.cipher(),
                    "cert_subject": cert.get("subject") if cert else None,
                }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "host": host, "error": str(exc)}


def verify_modernization(
    *,
    before: Dict[str, Any],
    after: Optional[Dict[str, Any]] = None,
    apply_results: Optional[List[Dict[str, Any]]] = None,
    https_probe_host: str = "example.com",
) -> Dict[str, Any]:
    """Re-assess the host and compare gaps; probe HTTPS and browser readiness."""
    after = after or assess_host()
    before_gaps = set(before.get("gaps") or [])
    after_gaps = set(after.get("gaps") or [])
    closed = sorted(before_gaps - after_gaps)
    opened = sorted(after_gaps - before_gaps)
    https = _probe_https(https_probe_host)

    apply_ok = True
    if apply_results:
        apply_ok = all(r.get("ok") for r in apply_results)

    browser_ready = after.get("browsers", {}).get("has_modern_browser", False)
    verdict_improved = (
        after.get("verdict") in {"ready", "mostly_ready"}
        and after.get("potato_score", 0) >= before.get("potato_score", 0)
    )

    overall = apply_ok and https.get("ok") and (verdict_improved or len(closed) > 0)

    return {
        "verified": overall,
        "before_verdict": before.get("verdict"),
        "after_verdict": after.get("verdict"),
        "before_potato_score": before.get("potato_score"),
        "after_potato_score": after.get("potato_score"),
        "gaps_closed": closed,
        "gaps_opened": opened,
        "https_probe": https,
        "browser_ready": browser_ready,
        "apply_steps_ok": apply_ok,
        "after_assessment": after,
    }
