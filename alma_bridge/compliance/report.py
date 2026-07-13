"""Unified legacy-compliance report.

Rolls the three signals Bridge can gather — TLS posture of the endpoints a
legacy box must reach, the host's driver inventory, and recommended hardware
shims — into one verdict with a prioritized remediation list.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from alma_bridge.compliance._perf import run_jobs
from alma_bridge.compliance.drivers import inventory_devices
from alma_bridge.compliance.services import scan_insecure_services
from alma_bridge.compliance.timecheck import assess_clock
from alma_bridge.compliance.tls import assess_tls
from alma_bridge.compliance.web3 import assess_web3_endpoint
from alma_bridge.hardware.profiler import profile_hardware
from alma_bridge.hardware.shims import recommended_shims_from_profile


def parse_target(target: Any) -> Tuple[str, int]:
    """Accept ``"host:port"``, ``"host"``, ``(host, port)`` or ``{host, port}``."""
    if isinstance(target, dict):
        return str(target.get("host")), int(target.get("port", 443))
    if isinstance(target, (list, tuple)):
        host = str(target[0])
        port = int(target[1]) if len(target) > 1 else 443
        return host, port
    text = str(target).strip()
    if text.startswith("http://"):
        text = text[len("http://"):]
        default_port = 80
    elif text.startswith("https://"):
        text = text[len("https://"):]
        default_port = 443
    else:
        default_port = 443
    text = text.split("/", 1)[0]
    # IPv6 literal, optionally with a port: "[::1]" or "[::1]:8443".
    if text.startswith("["):
        host, sep, rest = text[1:].partition("]")
        if sep and rest.startswith(":") and rest[1:]:
            return host, int(rest[1:])
        return host, default_port
    if ":" in text:
        host, _, port = text.rpartition(":")
        return host, int(port)
    return text, default_port


def build_compliance_report(
    targets: Optional[List[Any]] = None,
    *,
    include_drivers: bool = True,
    include_shims: bool = True,
    sys_root: str = "/sys",
    catalog_db: Optional[Path] = None,
    tls_timeout: float = 6.0,
    probe_legacy: bool = True,
    web3_rpc: Optional[List[str]] = None,
    check_time: bool = True,
    ntp_server: str = "pool.ntp.org",
    scan_services: bool = False,
    service_timeout: float = 2.0,
    max_workers: int = 0,
    cache_ttl: float = 0.0,
) -> Dict[str, Any]:
    targets = targets or []
    web3_rpc = web3_rpc or []

    tls_targets = [parse_target(t) for t in targets]
    service_hosts: List[str] = []
    if scan_services:
        for host, _ in tls_targets:
            if host not in service_hosts:
                service_hosts.append(host)

    # Build every independent probe as a deferred job, then run them all in a
    # single bounded thread pool. Compliance work is network-bound, so this
    # collapses the wall-clock cost from "sum of round-trips" to "slowest one",
    # even on a single-core box, while the worker cap keeps memory tiny.
    jobs: List[Tuple[Tuple[str, int], Callable[[], Any]]] = []
    jobs.append((("profile", 0), profile_hardware))
    for i, (host, port) in enumerate(tls_targets):
        jobs.append(
            (("tls", i), lambda h=host, p=port: assess_tls(
                h, p, timeout=tls_timeout, probe_legacy=probe_legacy, cache_ttl=cache_ttl
            ))
        )
    for i, url in enumerate(web3_rpc):
        jobs.append(
            (("web3", i), lambda u=url: assess_web3_endpoint(
                u, timeout=tls_timeout, check_tls=True, cache_ttl=cache_ttl
            ))
        )
    for i, host in enumerate(service_hosts):
        jobs.append(
            (("svc", i), lambda h=host: scan_insecure_services(h, timeout=service_timeout))
        )
    if check_time:
        jobs.append((("clock", 0), lambda: assess_clock(ntp_server, timeout=tls_timeout)))
    if include_drivers:
        jobs.append(
            (("drivers", 0), lambda: inventory_devices(sys_root, catalog_db=catalog_db))
        )

    results = run_jobs(jobs, configured_workers=max_workers)

    profile = results[("profile", 0)]
    tls_results = [results[("tls", i)] for i in range(len(tls_targets))]
    web3_results = [results[("web3", i)] for i in range(len(web3_rpc))]
    service_results = [results[("svc", i)] for i in range(len(service_hosts))]
    clock = results.get(("clock", 0)) if check_time else None
    drivers = results.get(("drivers", 0)) if include_drivers else None
    shims = recommended_shims_from_profile(profile) if include_shims else []

    tls_compliant = all(r.get("compliant") for r in tls_results) if tls_results else True
    drivers_compliant = drivers["compliant"] if drivers else True
    web3_compliant = all(r.get("web3_ready") for r in web3_results) if web3_results else True
    # `None` (couldn't measure) does not fail the overall verdict.
    clock_compliant = clock.get("compliant") is not False if clock else True
    services_compliant = all(s.get("compliant") for s in service_results) if service_results else True
    overall_compliant = (
        tls_compliant
        and drivers_compliant
        and web3_compliant
        and clock_compliant
        and services_compliant
    )

    remediations: List[Dict[str, Any]] = []
    for result in tls_results:
        if not result.get("compliant"):
            remediations.append(
                {
                    "area": "tls",
                    "target": f"{result.get('host')}:{result.get('port')}",
                    "severity": "high" if result.get("grade") == "insecure" else "medium",
                    "issue": "; ".join(result.get("blockers", [])) or "non-compliant TLS",
                    "action": "Front this endpoint with an Alma TLS-modernizing bridge "
                    "(POST /compliance/tls/bridge) or upgrade its TLS stack.",
                }
            )
    if drivers:
        for dev in drivers.get("missing_drivers", []):
            remediations.append(
                {
                    "area": "drivers",
                    "target": f"{dev['vendor_id']}:{dev['device_id']} ({dev.get('class_name')})",
                    "severity": "high" if dev.get("critical") else "low",
                    "issue": dev.get("detail"),
                    "action": f"Install/bind a driver (hint: {dev.get('module_hint') or 'unknown'}).",
                }
            )
    for result in web3_results:
        if not result.get("web3_ready"):
            remediations.append(
                {
                    "area": "web3",
                    "target": result.get("url"),
                    "severity": "medium",
                    "issue": "; ".join(result.get("blockers", [])) or "endpoint not web3-ready",
                    "action": result.get("recommendation")
                    or "Verify the RPC endpoint and its TLS posture.",
                }
            )
    if clock and clock.get("compliant") is False:
        remediations.append(
            {
                "area": "time",
                "target": clock.get("ntp_server"),
                "severity": "high",
                "issue": clock.get("impact"),
                "action": "Enable NTP time sync (e.g. systemd-timesyncd/chrony) so "
                "TLS certificate validation works.",
            }
        )
    for svc in service_results:
        for finding in svc.get("findings", []):
            remediations.append(
                {
                    "area": "services",
                    "target": f"{svc['host']}:{finding['port']} ({finding['name']})",
                    "severity": "high",
                    "issue": finding["risk"],
                    "action": f"Replace with {finding['replacement']}.",
                }
            )
    for shim in shims:
        remediations.append(
            {
                "area": "shims",
                "target": shim.get("category"),
                "severity": "info",
                "issue": shim.get("description"),
                "action": f"Apply shim '{shim.get('id')}' via Bridge env overrides.",
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_compliant": overall_compliant,
        "summary": {
            "tls_compliant": tls_compliant,
            "drivers_compliant": drivers_compliant,
            "web3_compliant": web3_compliant,
            "clock_compliant": clock_compliant,
            "services_compliant": services_compliant,
            "tls_targets": len(tls_results),
            "web3_targets": len(web3_results),
            "missing_drivers": drivers["missing_driver_count"] if drivers else 0,
            "insecure_services": sum(s.get("insecure_count", 0) for s in service_results),
            "recommended_shims": len(shims),
            "remediation_count": len(remediations),
        },
        "host": {
            "os": profile.get("os"),
            "distribution": profile.get("distribution"),
            "architecture": profile.get("architecture"),
            "os_bitness": profile.get("os_bitness"),
            "legacy_indicators": profile.get("legacy_indicators", []),
        },
        "tls": tls_results,
        "web3": web3_results,
        "clock": clock,
        "services": service_results,
        "drivers": drivers,
        "recommended_shims": shims,
        "remediations": remediations,
    }
