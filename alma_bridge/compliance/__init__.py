"""Legacy compliance toolkit for Alma Bridge.

Brings legacy machines up to modern standards along two axes:

* **TLS / HTTPS** — assess a host's TLS posture against today's baseline and,
  where the legacy box cannot be upgraded in place, front it with a
  TLS-modernizing bridge (plaintext/legacy port -> modern TLS 1.2+ upstream).
* **Drivers / shims** — inventory PCI/USB devices, flag unbound or unknown
  drivers, and surface the hardware shims Bridge already knows how to apply.
"""

from alma_bridge.compliance.tls import (
    assess_tls,
    evaluate_tls_posture,
)
from alma_bridge.compliance.drivers import inventory_devices
from alma_bridge.compliance.report import build_compliance_report
from alma_bridge.compliance.web3 import (
    assess_web3_endpoint,
    chain_info,
    normalize_ipfs_uri,
)
from alma_bridge.compliance.timecheck import assess_clock, evaluate_clock_skew
from alma_bridge.compliance.services import scan_insecure_services
from alma_bridge.compliance.dns import resolve_doh
from alma_bridge.compliance.autopilot import (
    diagnose,
    plan_pathways,
    run_autopilot,
    record_outcome,
)
from alma_bridge.compliance.legacy32 import (
    assess_32bit_support,
    plan_32bit_enablement,
)
from alma_bridge.compliance.modernization import (
    apply_playbook_steps,
    assess_host,
    build_modernization_playbook,
)

__all__ = [
    "assess_tls",
    "evaluate_tls_posture",
    "inventory_devices",
    "build_compliance_report",
    "assess_web3_endpoint",
    "chain_info",
    "normalize_ipfs_uri",
    "assess_clock",
    "evaluate_clock_skew",
    "scan_insecure_services",
    "resolve_doh",
    "diagnose",
    "plan_pathways",
    "run_autopilot",
    "record_outcome",
    "assess_32bit_support",
    "plan_32bit_enablement",
    "assess_host",
    "build_modernization_playbook",
    "apply_playbook_steps",
]
