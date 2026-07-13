"""Insecure-service detection.

Legacy hosts frequently still expose plaintext or obsolete network services
(telnet, FTP, bare HTTP, SMBv1, SNMPv1/2c, the r-services, plaintext mail).
This module probes a host for those ports and recommends a modern, encrypted
replacement for each — so a legacy box can be brought up to today's baseline.

The registry + recommendation logic is pure; only ``probe_port`` touches the
network.
"""

from __future__ import annotations

import socket
from typing import Any, Dict, List, Optional

from alma_bridge.compliance._perf import map_concurrent, network_slot

# port -> metadata about why it's insecure and what to use instead.
INSECURE_SERVICE_REGISTRY: Dict[int, Dict[str, str]] = {
    21: {"name": "FTP", "risk": "credentials and data sent in plaintext", "replacement": "SFTP (SSH) or FTPS"},
    23: {"name": "Telnet", "risk": "fully unencrypted remote shell", "replacement": "SSH (port 22)"},
    25: {"name": "SMTP (plaintext)", "risk": "mail/credentials may be unencrypted", "replacement": "SMTP+STARTTLS or SMTPS (465)"},
    69: {"name": "TFTP", "risk": "no authentication or encryption", "replacement": "SFTP/HTTPS"},
    80: {"name": "HTTP", "risk": "unencrypted web traffic", "replacement": "HTTPS — front with an Alma TLS-modernizing bridge"},
    110: {"name": "POP3 (plaintext)", "risk": "mail credentials in plaintext", "replacement": "POP3S (995)"},
    111: {"name": "RPCbind", "risk": "exposes RPC services, common attack surface", "replacement": "firewall / disable if unused"},
    143: {"name": "IMAP (plaintext)", "risk": "mail credentials in plaintext", "replacement": "IMAPS (993)"},
    161: {"name": "SNMP v1/v2c", "risk": "community strings sent in plaintext", "replacement": "SNMPv3 with auth+priv"},
    389: {"name": "LDAP (plaintext)", "risk": "directory credentials in plaintext", "replacement": "LDAPS (636) or StartTLS"},
    445: {"name": "SMB", "risk": "SMBv1 is vulnerable (EternalBlue family)", "replacement": "SMBv3 with signing; disable SMBv1"},
    512: {"name": "rexec", "risk": "plaintext remote execution", "replacement": "SSH"},
    513: {"name": "rlogin", "risk": "plaintext remote login", "replacement": "SSH"},
    514: {"name": "rsh/syslog", "risk": "plaintext remote shell / logs", "replacement": "SSH / syslog over TLS"},
    1433: {"name": "MSSQL (unencrypted)", "risk": "DB traffic may be unencrypted", "replacement": "Force TLS on SQL connections"},
    3306: {"name": "MySQL (unencrypted)", "risk": "DB traffic may be unencrypted", "replacement": "Require TLS for MySQL"},
    5432: {"name": "PostgreSQL (unencrypted)", "risk": "DB traffic may be unencrypted", "replacement": "Require SSL (sslmode=require)"},
    5900: {"name": "VNC", "risk": "weak/plaintext remote desktop", "replacement": "VNC over SSH tunnel or modern RDP/TLS"},
}

DEFAULT_SCAN_PORTS = sorted(INSECURE_SERVICE_REGISTRY.keys())


def recommend_for_port(port: int) -> Optional[Dict[str, Any]]:
    """Return the insecure-service metadata for a port, if known."""
    entry = INSECURE_SERVICE_REGISTRY.get(port)
    if not entry:
        return None
    return {"port": port, **entry}


def probe_port(host: str, port: int, *, timeout: float = 2.0) -> bool:
    """True if a TCP connection to ``host:port`` succeeds (service is listening)."""
    try:
        with network_slot(), socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def scan_insecure_services(
    host: str,
    *,
    ports: Optional[List[int]] = None,
    timeout: float = 2.0,
) -> Dict[str, Any]:
    """Probe a host for known insecure services and recommend replacements."""
    ports = ports if ports is not None else DEFAULT_SCAN_PORTS
    # Probe all ports concurrently: a down host costs ~one timeout, not N.
    open_flags = map_concurrent(
        lambda p: probe_port(host, p, timeout=timeout), list(ports)
    )
    findings: List[Dict[str, Any]] = []
    for port, is_open in zip(ports, open_flags):
        meta = recommend_for_port(port)
        if meta is None or not is_open:
            continue
        findings.append({**meta, "open": True})
    findings.sort(key=lambda f: f["port"])

    return {
        "host": host,
        "scanned_ports": len(ports),
        "insecure_count": len(findings),
        "findings": findings,
        "compliant": not findings,
    }
