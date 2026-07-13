"""Clock / time compliance.

A wrong system clock is one of the most common reasons a legacy machine fails
to use modern HTTPS: certificate validation rejects certs that appear
"not yet valid" or "expired" purely because the host's clock is off. This
module measures the host's clock skew against a trusted time source (NTP) and
reports the likely impact.

Pure verdict logic (``evaluate_clock_skew``) is separated from the live NTP
query so it can be unit-tested deterministically.
"""

from __future__ import annotations

import socket
import struct
import time
from typing import Any, Dict, Optional

from alma_bridge.compliance._perf import network_slot

# NTP timestamps count seconds since 1900; Unix epoch is 1970.
_NTP_UNIX_DELTA = 2208988800
_NTP_PACKET = b"\x1b" + 47 * b"\0"  # LI=0, VN=3, Mode=3 (client)

# Skew thresholds (seconds).
SKEW_WARN_SECONDS = 60
SKEW_FAIL_SECONDS = 300  # beyond this, TLS/cert validation commonly breaks


def evaluate_clock_skew(
    local_epoch: float, reference_epoch: Optional[float]
) -> Dict[str, Any]:
    """Pure verdict for a measured clock skew.

    ``skew_seconds`` is ``local - reference`` (positive = host clock ahead).
    """
    if reference_epoch is None:
        return {
            "compliant": None,
            "skew_seconds": None,
            "severity": "unknown",
            "impact": "Could not reach a trusted time source to measure skew.",
            "local_epoch": local_epoch,
            "reference_epoch": None,
        }

    skew = local_epoch - reference_epoch
    magnitude = abs(skew)
    if magnitude >= SKEW_FAIL_SECONDS:
        severity = "high"
        compliant = False
        impact = (
            f"Clock is off by {round(skew)}s — this will cause TLS certificate "
            "validation failures (certs appear not-yet-valid or expired). "
            "Sync the clock (NTP) before relying on HTTPS."
        )
    elif magnitude >= SKEW_WARN_SECONDS:
        severity = "medium"
        compliant = True
        impact = (
            f"Clock is off by {round(skew)}s — borderline; may intermittently "
            "affect time-sensitive auth (tokens, Kerberos). Recommend NTP sync."
        )
    else:
        severity = "ok"
        compliant = True
        impact = f"Clock within {SKEW_WARN_SECONDS}s of reference ({round(skew, 1)}s)."

    return {
        "compliant": compliant,
        "skew_seconds": round(skew, 3),
        "severity": severity,
        "impact": impact,
        "local_epoch": local_epoch,
        "reference_epoch": reference_epoch,
    }


def query_ntp(server: str = "pool.ntp.org", *, timeout: float = 5.0) -> Optional[float]:
    """Return the reference Unix time from an NTP server, or ``None`` on failure."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        with network_slot():
            sock.sendto(_NTP_PACKET, (server, 123))
            data, _ = sock.recvfrom(48)
    except (OSError, socket.timeout):
        return None
    finally:
        sock.close()
    if len(data) < 44:
        return None
    # Transmit timestamp (seconds) is at bytes 40-43, big-endian.
    seconds = struct.unpack("!I", data[40:44])[0]
    if seconds == 0:
        return None
    return seconds - _NTP_UNIX_DELTA


def assess_clock(server: str = "pool.ntp.org", *, timeout: float = 5.0) -> Dict[str, Any]:
    """Measure local clock skew against an NTP server and return a verdict."""
    local = time.time()
    reference = query_ntp(server, timeout=timeout)
    verdict = evaluate_clock_skew(local, reference)
    verdict["ntp_server"] = server
    return verdict
