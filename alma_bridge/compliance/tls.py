"""TLS posture assessment for legacy hosts.

The module is split into:

* :func:`evaluate_tls_posture` — pure, network-free verdict logic. Given a set
  of observations (negotiated protocol, cipher, cert info, which legacy
  protocol versions a server still accepts) it returns a compliance verdict.
* :func:`probe_endpoint` — the live network probe that gathers those
  observations from a real ``host:port``.
* :func:`assess_tls` — convenience wrapper: probe then evaluate.

Keeping the verdict logic pure makes it unit-testable without a network or a
certificate authority, while the probe stays a thin, well-isolated I/O layer.
"""

from __future__ import annotations

import socket
import ssl
import warnings
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import certifi

from alma_bridge.compliance._perf import TTLCache, map_concurrent, network_slot

_TLS_CACHE = TTLCache()

# Today's minimum acceptable handshake.
MIN_COMPLIANT_PROTOCOL = "TLSv1.2"
CERT_EXPIRY_WARN_DAYS = 30
# Cipher substrings that are considered weak/deprecated regardless of protocol.
WEAK_CIPHER_MARKERS = ("RC4", "3DES", "DES", "NULL", "EXPORT", "MD5", "ANON", "RC2")

# Rank protocols so we can compare "is this at least TLS 1.2".
_PROTOCOL_RANK: Dict[str, int] = {
    "SSLv2": 0,
    "SSLv3": 1,
    "TLSv1": 2,
    "TLSv1.0": 2,
    "TLSv1.1": 3,
    "TLSv1.2": 4,
    "TLSv1.3": 5,
}

# Legacy protocol versions we actively probe for (and want servers to reject).
_LEGACY_VERSIONS: List[Tuple[str, "ssl.TLSVersion"]] = [
    ("SSLv3", getattr(ssl.TLSVersion, "SSLv3", None)),
    ("TLSv1", ssl.TLSVersion.TLSv1),
    ("TLSv1.1", ssl.TLSVersion.TLSv1_1),
]


def _set_min_version(ctx: ssl.SSLContext, version: "ssl.TLSVersion") -> bool:
    """Set ``minimum_version`` while silencing the intentional legacy-protocol
    DeprecationWarnings (we *want* to probe TLSv1/1.1). Returns False if the
    local OpenSSL build refuses the version outright.
    """
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            ctx.minimum_version = version
        return True
    except (ValueError, OSError):
        return False


def _protocol_rank(protocol: Optional[str]) -> int:
    if not protocol:
        return -1
    return _PROTOCOL_RANK.get(protocol.replace("TLSv1.0", "TLSv1"), -1)


def _days_until(not_after: Optional[str]) -> Optional[int]:
    """Parse an OpenSSL ``notAfter`` string into days-from-now."""
    if not not_after:
        return None
    for fmt in ("%b %d %H:%M:%S %Y %Z", "%b %d %H:%M:%S %Y"):
        try:
            expiry = datetime.strptime(not_after, fmt).replace(tzinfo=timezone.utc)
            break
        except ValueError:
            continue
    else:
        return None
    delta = expiry - datetime.now(timezone.utc)
    return delta.days


def evaluate_tls_posture(observation: Dict[str, Any]) -> Dict[str, Any]:
    """Turn raw TLS observations into a compliance verdict.

    ``observation`` keys (all optional, missing == unknown):
        verified: bool            — chain validated against modern CA roots
        verify_error: str | None
        negotiated_protocol: str  — e.g. "TLSv1.3"
        cipher_name: str
        cipher_bits: int
        cert_not_after: str       — OpenSSL date string
        cert_subject: str
        cert_issuer: str
        legacy_protocols: dict     — {"TLSv1": "supported"|"rejected"|...}
        reachable: bool
        error: str | None          — connection-level failure
    """
    blockers: List[str] = []
    warnings: List[str] = []

    if observation.get("reachable") is False:
        return {
            "compliant": False,
            "reachable": False,
            "grade": "unreachable",
            "blockers": [observation.get("error") or "host unreachable"],
            "warnings": [],
            "observation": observation,
            "recommendation": "Confirm the host is online and the port is correct.",
        }

    negotiated = observation.get("negotiated_protocol")
    if _protocol_rank(negotiated) < _PROTOCOL_RANK[MIN_COMPLIANT_PROTOCOL]:
        blockers.append(
            f"negotiates {negotiated or 'no TLS'} (below {MIN_COMPLIANT_PROTOCOL})"
        )

    # Only a genuine verification failure (not a handshake that never completed)
    # should be reported as a certificate-trust problem.
    if observation.get("verified") is False and not observation.get("tls_handshake_failed"):
        reason = observation.get("verify_error") or "unknown reason"
        blockers.append(f"certificate chain not trusted by modern roots: {reason}")

    if observation.get("tls_handshake_failed") and not negotiated:
        blockers.append(
            "TLS handshake failed: server only offers protocols modern clients "
            f"reject ({observation.get('tls_error') or 'unsupported protocol'})"
        )

    legacy = observation.get("legacy_protocols") or {}
    for proto, state in legacy.items():
        if state == "supported":
            blockers.append(f"still accepts legacy {proto}")

    cipher_name = (observation.get("cipher_name") or "").upper()
    for marker in WEAK_CIPHER_MARKERS:
        if marker in cipher_name:
            blockers.append(f"weak cipher negotiated: {observation.get('cipher_name')}")
            break
    cipher_bits = observation.get("cipher_bits")
    if isinstance(cipher_bits, int) and 0 < cipher_bits < 128:
        warnings.append(f"low cipher strength: {cipher_bits}-bit")

    days = _days_until(observation.get("cert_not_after"))
    if days is not None:
        if days < 0:
            blockers.append(f"certificate expired {abs(days)} day(s) ago")
        elif days <= CERT_EXPIRY_WARN_DAYS:
            warnings.append(f"certificate expires in {days} day(s)")

    compliant = not blockers
    if compliant and not warnings:
        grade = "modern"
    elif compliant:
        grade = "acceptable"
    elif negotiated and _protocol_rank(negotiated) >= _PROTOCOL_RANK["TLSv1"]:
        grade = "legacy"
    elif observation.get("tls_handshake_failed"):
        # Reachable, but only offers obsolete protocols modern clients refuse.
        grade = "legacy"
    else:
        grade = "insecure"

    recommendation = None
    if not compliant:
        recommendation = (
            "If the endpoint cannot be upgraded in place, front it with an Alma "
            "TLS-modernizing bridge so legacy clients reach it over modern TLS."
        )

    return {
        "compliant": compliant,
        "reachable": True,
        "grade": grade,
        "blockers": blockers,
        "warnings": warnings,
        "observation": observation,
        "recommendation": recommendation,
    }


def _probe_legacy_version(
    host: str, port: int, label: str, version: Optional["ssl.TLSVersion"], timeout: float
) -> str:
    """Return whether ``host:port`` will still complete a handshake at ``version``."""
    if version is None:
        return "unavailable"
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    if not _set_min_version(ctx, version):
        # The local OpenSSL build refuses to even offer this version.
        return "unavailable"
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            ctx.maximum_version = version
    except (ValueError, OSError):
        return "unavailable"
    try:
        with network_slot(), socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host):
                return "supported"
    except ssl.SSLError:
        return "rejected"
    except (OSError, socket.timeout):
        return "error"


def _cert_summary(cert: Dict[str, Any]) -> Dict[str, Any]:
    def _join(field: Any) -> str:
        parts = []
        for rdn in field or ():
            for key, value in rdn:
                parts.append(f"{key}={value}")
        return ", ".join(parts)

    return {
        "cert_subject": _join(cert.get("subject")),
        "cert_issuer": _join(cert.get("issuer")),
        "cert_not_after": cert.get("notAfter"),
        "cert_not_before": cert.get("notBefore"),
    }


def probe_endpoint(
    host: str,
    port: int = 443,
    *,
    timeout: float = 6.0,
    ca_file: Optional[str] = None,
    probe_legacy: bool = True,
) -> Dict[str, Any]:
    """Gather live TLS observations from ``host:port``.

    Tries a verified handshake against modern CA roots first (which also yields
    full certificate metadata). On verification failure it retries unverified so
    we can still report the negotiated protocol/cipher and the failure reason.
    """
    observation: Dict[str, Any] = {
        "host": host,
        "port": port,
        "reachable": None,
        "verified": None,
        "verify_error": None,
        "negotiated_protocol": None,
        "cipher_name": None,
        "cipher_bits": None,
        "error": None,
    }
    ca_file = ca_file or certifi.where()

    verified_ctx = ssl.create_default_context(cafile=ca_file)
    _set_min_version(verified_ctx, ssl.TLSVersion.TLSv1)  # allow probing legacy hosts
    try:
        with network_slot(), socket.create_connection((host, port), timeout=timeout) as sock:
            with verified_ctx.wrap_socket(sock, server_hostname=host) as tls:
                observation["reachable"] = True
                observation["verified"] = True
                observation["negotiated_protocol"] = tls.version()
                cipher = tls.cipher()
                if cipher:
                    observation["cipher_name"] = cipher[0]
                    observation["cipher_bits"] = cipher[2]
                observation.update(_cert_summary(tls.getpeercert() or {}))
    except ssl.SSLCertVerificationError as exc:
        observation["verified"] = False
        observation["verify_error"] = getattr(exc, "verify_message", None) or str(exc)
        _probe_unverified(host, port, timeout, observation)
    except ssl.SSLError as exc:
        observation["verified"] = False
        observation["verify_error"] = str(exc)
        _probe_unverified(host, port, timeout, observation)
        if observation.get("reachable") is not True:
            # Handshake failed but the host may still be up and merely offering
            # obsolete protocols our modern client rejects. A TCP probe tells the
            # difference between "down" and "legacy TLS only".
            if _tcp_reachable(host, port, timeout):
                observation["reachable"] = True
                observation["tls_handshake_failed"] = True
                observation["tls_error"] = str(exc)
            else:
                observation["reachable"] = False
                observation["error"] = str(exc)
                return observation
    except (OSError, socket.timeout) as exc:
        observation["reachable"] = False
        observation["error"] = str(exc)
        return observation

    if probe_legacy and observation.get("reachable"):
        # These are independent extra handshakes; run them concurrently so the
        # cost is one round-trip instead of three (matters on slow links).
        labels = [label for label, _ in _LEGACY_VERSIONS]
        states = map_concurrent(
            lambda lv: _probe_legacy_version(host, port, lv[0], lv[1], timeout),
            _LEGACY_VERSIONS,
        )
        observation["legacy_protocols"] = dict(zip(labels, states))
    return observation


def _tcp_reachable(host: str, port: int, timeout: float) -> bool:
    """True if a plain TCP connection to ``host:port`` succeeds."""
    try:
        with network_slot(), socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def _probe_unverified(host: str, port: int, timeout: float, observation: Dict[str, Any]) -> None:
    """Second-chance handshake without verification to capture protocol/cipher.

    Only records positive results; reachability decisions are left to the caller
    so a failed handshake can still be distinguished from an unreachable host.
    """
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    _set_min_version(ctx, ssl.TLSVersion.TLSv1)
    try:
        with network_slot(), socket.create_connection((host, port), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as tls:
                observation["reachable"] = True
                observation["negotiated_protocol"] = tls.version()
                cipher = tls.cipher()
                if cipher:
                    observation["cipher_name"] = cipher[0]
                    observation["cipher_bits"] = cipher[2]
    except (OSError, ssl.SSLError, socket.timeout):
        pass


def assess_tls(
    host: str,
    port: int = 443,
    *,
    timeout: float = 6.0,
    ca_file: Optional[str] = None,
    probe_legacy: bool = True,
    cache_ttl: float = 0.0,
) -> Dict[str, Any]:
    """Probe ``host:port`` and return a full compliance verdict.

    ``cache_ttl`` > 0 memoizes the verdict for repeated/overlapping probes
    (e.g. the same host scanned as a TLS target and a web3 RPC host).
    """
    key = ("tls", host, port, probe_legacy, ca_file or "")

    def _compute() -> Dict[str, Any]:
        observation = probe_endpoint(
            host, port, timeout=timeout, ca_file=ca_file, probe_legacy=probe_legacy
        )
        verdict = evaluate_tls_posture(observation)
        verdict["host"] = host
        verdict["port"] = port
        return verdict

    return _TLS_CACHE.get_or_compute(key, cache_ttl, _compute)
