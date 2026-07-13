"""Self-healing autopilot for legacy modernization.

Given an error (free text from a failed launch, a TLS/driver/web3 finding, or a
compliance report), the autopilot:

  1. **Diagnoses** the failure into a stable *signature* + *category* with
     evidence and a confidence score (transparent regex/keyword matching, not a
     black box).
  2. **Plans pathways** — ordered remediation strategies, each a sequence of
     concrete steps. Static priority is blended with an online success-rate
     learner (see ``learning.py``) so pathways that actually work on this host
     float to the top over time.
  3. **Synthesizes new pathways** when no catalogued pathway matches (e.g. a
     never-seen missing shared library is turned into an install/relink plan).
  4. **Rebuilds dependencies** — emits distro-aware, copy-pasteable commands and
     can auto-run the *read-only diagnostic* steps to confirm what is missing.

Everything that mutates the system is dry-run by default. Execution only ever
runs read-only diagnostic probes unless ``allow_mutations`` is explicitly set,
and destructive commands are never generated.
"""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from alma_bridge.compliance.learning import pathway_scores, record_pathway_outcome
from alma_bridge.compliance.pm import PACKAGE_MANAGERS, detect_package_manager, install_cmd as _install_cmd


# --------------------------------------------------------------------------- #
# Diagnosis
# --------------------------------------------------------------------------- #


@dataclass
class Signature:
    id: str
    category: str
    title: str
    patterns: List[str]
    severity: str = "error"


# Ordered most-specific first; ``diagnose`` keeps all matches but ranks by
# number of distinct pattern hits (a rough confidence proxy).
SIGNATURES: List[Signature] = [
    Signature(
        "missing_shared_library", "dependency",
        "A required shared library is missing",
        [r"error while loading shared libraries",
         r"cannot open shared object file",
         r"lib[\w.+-]+\.so[.\d]*: cannot open"],
    ),
    Signature(
        "glibc_too_old", "dependency",
        "The system glibc is older than the binary requires",
        [r"GLIBC_\d", r"version `GLIBC_", r"`GLIBCXX_"],
    ),
    Signature(
        "arch_32bit", "legacy32",
        "A 32-bit binary cannot run (missing multiarch / loader)",
        [r"ELFCLASS32", r"wrong ELF class",
         r"cannot execute binary file", r"ld-linux\.so\.2",
         r"no such file or directory.*ld-linux"],
    ),
    Signature(
        "tls_obsolete_protocol", "tls",
        "Endpoint or client only speaks obsolete TLS/SSL",
        [r"sslv3", r"tlsv1(\.[01])?\b", r"no protocols available",
         r"unsupported protocol", r"wrong version number",
         r"handshake failure", r"dh key too small", r"unsafe legacy renegotiation"],
    ),
    Signature(
        "tls_cert_expired", "tls",
        "TLS certificate is expired or not yet valid",
        [r"certificate has expired", r"certificate is not yet valid",
         r"notvalidafter", r"cert(ificate)? expired"],
    ),
    Signature(
        "tls_cert_untrusted", "tls",
        "TLS certificate chain is not trusted (stale CA store)",
        [r"unable to get local issuer", r"self.signed certificate",
         r"certificate verify failed", r"unable to verify the first certificate",
         r"ca(_| )?bundle"],
    ),
    Signature(
        "clock_skew", "clock",
        "Host clock is wrong, breaking certificate validation",
        [r"clock", r"not yet valid", r"system time", r"date is incorrect"],
    ),
    Signature(
        "dns_failure", "dns",
        "DNS resolution is failing",
        [r"name or service not known", r"getaddrinfo", r"temporary failure in name resolution",
         r"could not resolve host", r"nxdomain"],
    ),
    Signature(
        "driver_missing", "driver",
        "A kernel driver/firmware for a device is missing",
        [r"no driver", r"unknown symbol", r"modprobe", r"firmware.*failed",
         r"failed to load firmware", r"no such device"],
    ),
    Signature(
        "web3_unreachable", "web3",
        "A Web3 JSON-RPC endpoint is unreachable or insecure",
        [r"json-?rpc", r"eth_chainid", r"web3", r"rpc endpoint"],
    ),
    Signature(
        "permission_denied", "system",
        "Operation failed due to insufficient privileges",
        [r"permission denied", r"operation not permitted", r"eacces", r"must be root"],
    ),
]


def diagnose(error_text: str) -> List[Dict[str, Any]]:
    """Classify free-text error output into ranked diagnoses."""
    text = (error_text or "").lower()
    results: List[Dict[str, Any]] = []
    for sig in SIGNATURES:
        hits = []
        for pat in sig.patterns:
            match = re.search(pat, text, re.IGNORECASE)
            if match:
                hits.append(match.group(0))
        if hits:
            confidence = round(min(1.0, 0.4 + 0.2 * len(hits)), 3)
            results.append(
                {
                    "signature": sig.id,
                    "category": sig.category,
                    "title": sig.title,
                    "severity": sig.severity,
                    "confidence": confidence,
                    "evidence": hits[:5],
                    "missing_library": _extract_missing_library(error_text)
                    if sig.id == "missing_shared_library" else None,
                }
            )
    results.sort(key=lambda d: d["confidence"], reverse=True)
    if not results:
        results.append(
            {
                "signature": "unknown_error",
                "category": "unknown",
                "title": "Unrecognized error",
                "severity": "warning",
                "confidence": 0.2,
                "evidence": [],
                "missing_library": None,
            }
        )
    return results


_LIB_RE = re.compile(r"(lib[\w.+-]+?\.so[.\d]*)", re.IGNORECASE)


def _extract_missing_library(error_text: str) -> Optional[str]:
    match = _LIB_RE.search(error_text or "")
    return match.group(1) if match else None


# --------------------------------------------------------------------------- #
# Pathway knowledge base
# --------------------------------------------------------------------------- #


@dataclass
class Step:
    description: str
    command: Optional[str] = None
    kind: str = "remediation"  # "diagnostic" (read-only) | "remediation" (mutating)
    requires_root: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "description": self.description,
            "command": self.command,
            "kind": self.kind,
            "requires_root": self.requires_root,
        }


@dataclass
class Pathway:
    id: str
    signature: str
    title: str
    category: str
    priority: int
    steps: List[Step]
    rebuild: bool = False
    notes: str = ""
    alma_route: Optional[str] = None  # related Alma API/feature

    def as_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "signature": self.signature,
            "title": self.title,
            "category": self.category,
            "priority": self.priority,
            "rebuild": self.rebuild,
            "notes": self.notes,
            "alma_route": self.alma_route,
            "steps": [s.as_dict() for s in self.steps],
        }


def _pm_token() -> str:
    return "{pm-install}"


PATHWAYS: List[Pathway] = [
    # ---- TLS obsolete protocol ---------------------------------------------
    Pathway(
        "tls_modernizer_bridge", "tls_obsolete_protocol",
        "Front the legacy client with Alma's TLS-modernizing bridge",
        "tls", 1,
        [
            Step("Start a local plaintext->modern-TLS bridge so the legacy app "
                 "connects to 127.0.0.1 while Alma re-originates TLS 1.2+ upstream.",
                 "curl -s -X POST localhost:8800/compliance/tls/bridge "
                 "-H 'content-type: application/json' "
                 "-d '{\"upstream_host\":\"HOST\",\"upstream_port\":443}'",
                 kind="remediation"),
            Step("Point the legacy client at the returned 127.0.0.1:<port>."),
        ],
        notes="Lets a box that can only do SSLv3/TLS1.0 reach modern HTTPS.",
        alma_route="POST /compliance/tls/bridge",
    ),
    Pathway(
        "tls_enable_modern_openssl", "tls_obsolete_protocol",
        "Update the system OpenSSL / TLS library",
        "tls", 5,
        [
            Step("Refresh package metadata.", "{pm-refresh}", requires_root=True),
            Step("Install a current OpenSSL/libssl.", _pm_token(), requires_root=True),
        ],
        rebuild=True,
        notes="Permanent fix when the OS is recent enough to ship modern OpenSSL.",
    ),
    # ---- TLS cert untrusted (stale CA store) -------------------------------
    Pathway(
        "tls_install_modern_ca_bundle", "tls_cert_untrusted",
        "Install Alma's up-to-date CA root bundle",
        "tls", 1,
        [
            Step("Download Alma's current CA bundle.",
                 "curl -s localhost:8800/compliance/tls/ca-bundle -o alma-ca.pem"),
            Step("Install it into the system trust store and rebuild.",
                 "sudo cp alma-ca.pem /usr/local/share/ca-certificates/alma-ca.crt && "
                 "sudo update-ca-certificates", requires_root=True),
        ],
        rebuild=True,
        notes="Fixes 'unable to get local issuer' on boxes with a frozen CA store.",
        alma_route="GET /compliance/tls/ca-bundle",
    ),
    # ---- clock skew ---------------------------------------------------------
    Pathway(
        "clock_ntp_sync", "clock_skew",
        "Sync the system clock so certificate dates validate",
        "clock", 1,
        [
            Step("Check the current skew against NTP.",
                 "curl -s localhost:8800/compliance/time/check", kind="diagnostic"),
            Step("Force a one-shot NTP sync.",
                 "sudo ntpdate pool.ntp.org || sudo chronyc makestep || "
                 "sudo timedatectl set-ntp true", requires_root=True),
        ],
        rebuild=True,
        notes="A wrong clock makes every valid cert look expired/not-yet-valid.",
        alma_route="GET /compliance/time/check",
    ),
    # ---- DNS ----------------------------------------------------------------
    Pathway(
        "dns_over_https", "dns_failure",
        "Resolve names through Alma's DNS-over-HTTPS resolver",
        "dns", 1,
        [
            Step("Resolve the host via DoH to confirm the name exists.",
                 "curl -s 'localhost:8800/compliance/dns/resolve?name=HOST'",
                 kind="diagnostic"),
            Step("Use the returned A/AAAA records (or point the app at a DoH proxy)."),
        ],
        notes="Works even when the legacy resolver/ISP DNS is broken or blocked.",
        alma_route="GET /compliance/dns/resolve",
    ),
    # ---- missing shared library --------------------------------------------
    Pathway(
        "rebuild_missing_library", "missing_shared_library",
        "Locate and (re)install the missing shared library",
        "dependency", 1,
        [
            Step("List what the binary needs and which libs are unresolved.",
                 "ldd BINARY | grep 'not found'", kind="diagnostic"),
            Step("Search the package that provides the library.",
                 "{pm-whatprovides}", kind="diagnostic"),
            Step("Install the providing package.", _pm_token(), requires_root=True),
            Step("Refresh the dynamic linker cache.", "sudo ldconfig", requires_root=True),
        ],
        rebuild=True,
        notes="Auto-extracts the lib name from the error to target the install.",
    ),
    # ---- glibc too old ------------------------------------------------------
    Pathway(
        "glibc_container_shim", "glibc_too_old",
        "Run the binary in a newer-glibc container instead of upgrading the host",
        "dependency", 1,
        [
            Step("Confirm the host glibc version.", "ldd --version | head -1",
                 kind="diagnostic"),
            Step("Run inside Alma sandbox with full shim pack (modern glibc, no host upgrade).",
                 "curl -s -X POST http://127.0.0.1:9010/container/run "
                 "-H 'content-type: application/json' "
                 "-d '{\"file_path\":\"BINARY_PATH\"}'"),
        ],
        notes="Upgrading glibc in place on a legacy distro often breaks the system; "
              "a container gives a modern glibc without touching the host.",
    ),
    # ---- 32-bit legacy ------------------------------------------------------
    Pathway(
        "legacy32_enable_multiarch", "arch_32bit",
        "Enable multiarch and install the 32-bit runtime",
        "legacy32", 1,
        [
            Step("Enable the i386 architecture (Debian/Ubuntu).",
                 "sudo dpkg --add-architecture i386 && sudo apt-get update",
                 requires_root=True),
            Step("Install the core 32-bit runtime + loader.",
                 "sudo apt-get install -y libc6:i386 libstdc++6:i386 zlib1g:i386",
                 requires_root=True),
            Step("Verify the 32-bit loader is present.",
                 "test -e /lib/ld-linux.so.2 && echo OK", kind="diagnostic"),
        ],
        rebuild=True,
        notes="Makes 32-bit ELF binaries runnable on a modern 64-bit host.",
        alma_route="GET /compliance/legacy32",
    ),
    Pathway(
        "legacy32_wine_prefix", "arch_32bit",
        "For Windows binaries, use a 32-bit Wine prefix",
        "legacy32", 6,
        [
            Step("Create/point at a 32-bit WINEPREFIX.",
                 "WINEARCH=win32 WINEPREFIX=~/.wine32 wineboot -i"),
        ],
        notes="Mirrors Alma's win32_prefix shim for 32-bit Windows apps.",
    ),
    # ---- driver -------------------------------------------------------------
    Pathway(
        "driver_inventory_and_install", "driver_missing",
        "Inventory the device and install the matching driver/firmware",
        "driver", 1,
        [
            Step("Inventory PCI/USB devices and flag missing drivers.",
                 "curl -s localhost:8800/compliance/drivers", kind="diagnostic"),
            Step("Install linux-firmware + the recommended module package.",
                 "{pm-install}", requires_root=True),
            Step("Load the module.", "sudo modprobe MODULE", requires_root=True),
        ],
        rebuild=True,
        alma_route="GET /compliance/drivers",
    ),
    # ---- web3 ---------------------------------------------------------------
    Pathway(
        "web3_modern_rpc_via_bridge", "web3_unreachable",
        "Reach the chain through a modern HTTPS RPC + TLS bridge",
        "web3", 1,
        [
            Step("Assess the RPC endpoint (chain id, TLS posture).",
                 "curl -s -X POST localhost:8800/compliance/web3/assess "
                 "-H 'content-type: application/json' -d '{\"url\":\"RPC_URL\"}'",
                 kind="diagnostic"),
            Step("If the legacy client can't do modern TLS, front it with the bridge.",
                 "curl -s -X POST localhost:8800/compliance/tls/bridge "
                 "-H 'content-type: application/json' "
                 "-d '{\"upstream_host\":\"RPC_HOST\",\"upstream_port\":443}'"),
        ],
        alma_route="POST /compliance/web3/assess",
    ),
    # ---- permission ---------------------------------------------------------
    Pathway(
        "permission_rerun_root", "permission_denied",
        "Re-run the failing step with elevated privileges",
        "system", 1,
        [
            Step("Re-run the command under sudo (review it first)."),
        ],
    ),
    # ---- generic fallback ---------------------------------------------------
    Pathway(
        "baseline_retry", "unknown_error",
        "Capture diagnostics and retry with a clean environment",
        "unknown", 100,
        [
            Step("Collect verbose output to refine the diagnosis.",
                 "BINARY 2>&1 | tail -50", kind="diagnostic"),
        ],
    ),
]


def _pathways_for_signature(signature: str) -> List[Pathway]:
    matches = [p for p in PATHWAYS if p.signature == signature]
    if not matches:
        matches = [p for p in PATHWAYS if p.signature == "unknown_error"]
    return matches


# --------------------------------------------------------------------------- #
# Ranking (static priority blended with learned success rate)
# --------------------------------------------------------------------------- #


def rank_pathways(pathways: List[Pathway], signature: str) -> List[Dict[str, Any]]:
    """Order pathways by a blend of static priority and learned success rate."""
    scores = pathway_scores(signature)
    ranked: List[Dict[str, Any]] = []
    for path in pathways:
        # Static score: lower priority number == better -> normalize to 0..1.
        static = 1.0 / (1.0 + path.priority)
        learned = scores.get(path.id)
        if learned:
            rate = learned["rate"]
            attempts = learned["attempts"]
            # Trust learned rate more as evidence accumulates.
            weight = min(0.8, 0.2 + 0.1 * attempts)
            blended = (1 - weight) * static + weight * rate
        else:
            rate = None
            blended = static
        entry = path.as_dict()
        entry["static_score"] = round(static, 4)
        entry["learned_rate"] = rate
        entry["score"] = round(blended, 4)
        ranked.append(entry)
    ranked.sort(key=lambda e: e["score"], reverse=True)
    return ranked


# --------------------------------------------------------------------------- #
# Pathway synthesis (build *new* pathways for unseen problems)
# --------------------------------------------------------------------------- #


def synthesize_pathway(diagnosis: Dict[str, Any], pm: str) -> Optional[Dict[str, Any]]:
    """Generate a bespoke pathway from a diagnosis when the catalog is too generic.

    This is how the autopilot "builds new pathways": e.g. a never-seen missing
    library name is turned into a targeted, package-manager-specific install.
    """
    signature = diagnosis.get("signature")
    if signature == "missing_shared_library":
        lib = diagnosis.get("missing_library")
        if not lib:
            return None
        whatprovides = _whatprovides_cmd(lib, pm)
        path = Pathway(
            id=f"synth_install_{re.sub(r'[^a-z0-9]+', '_', lib.lower())}",
            signature=signature,
            title=f"Resolve and install the package providing {lib}",
            category="dependency",
            priority=0,
            rebuild=True,
            notes=f"Synthesized for the specific missing library '{lib}'.",
            steps=[
                Step(f"Find which package ships {lib}.", whatprovides, kind="diagnostic"),
                Step(f"Install that package, then refresh the linker cache.",
                     "sudo ldconfig", requires_root=True),
            ],
        )
        entry = path.as_dict()
        entry["synthesized"] = True
        return entry

    if signature == "permission_denied":
        path = Pathway(
            id="synth_fresh_wineprefix",
            signature=signature,
            title="Fresh WINEPREFIX — reset bad Wine permissions",
            category="bridge",
            priority=0,
            rebuild=True,
            notes="Synthesized for permission_denied under Wine/Bridge.",
            steps=[
                Step(
                    "Create an isolated Alma Wine prefix.",
                    "WINEARCH=win64 WINEPREFIX=~/.wine-alma-fresh wineboot -i",
                ),
            ],
        )
        entry = path.as_dict()
        entry["synthesized"] = True
        return entry

    return None


def _whatprovides_cmd(lib: str, pm: str) -> str:
    if pm == "apt":
        return f"apt-file search {lib} || dpkg -S {lib}"
    if pm in ("dnf", "yum"):
        return f"{pm} provides '*/{lib}'"
    if pm == "pacman":
        return f"pacman -F {lib}"
    if pm == "zypper":
        return f"zypper what-provides {lib}"
    if pm == "apk":
        return f"apk info --who-owns {lib}"
    return f"# search your package manager for {lib}"


# --------------------------------------------------------------------------- #
# Concrete command materialization
# --------------------------------------------------------------------------- #


def _materialize_steps(steps: List[Dict[str, Any]], pm: str, lib: Optional[str]) -> List[Dict[str, Any]]:
    """Replace package-manager placeholders with concrete commands."""
    refresh = PACKAGE_MANAGERS.get(pm, PACKAGE_MANAGERS["apt"])["refresh"]
    out: List[Dict[str, Any]] = []
    for step in steps:
        cmd = step.get("command")
        if cmd:
            cmd = cmd.replace("{pm-refresh}", refresh)
            if "{pm-install}" in cmd:
                pkgs = [_guess_package(lib, pm)] if lib else ["<package>"]
                cmd = cmd.replace("{pm-install}", _install_cmd(pkgs, pm))
            if "{pm-whatprovides}" in cmd and lib:
                cmd = cmd.replace("{pm-whatprovides}", _whatprovides_cmd(lib, pm))
            elif "{pm-whatprovides}" in cmd:
                cmd = cmd.replace("{pm-whatprovides}", "# identify the providing package")
        step = dict(step)
        step["command"] = cmd
        out.append(step)
    return out


def _guess_package(lib: Optional[str], pm: str) -> str:
    if not lib:
        return "<package>"
    base = lib.split(".so")[0]
    if pm == "apt":
        return f"{base.lower()}"
    return base


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #


def plan_pathways(error_text: str, *, os_release: Optional[str] = None) -> Dict[str, Any]:
    """Diagnose ``error_text`` and return ranked + synthesized pathways."""
    from alma_bridge.automation.pathways import build_novel_pathway_extras

    pm = detect_package_manager(os_release)
    diagnoses = diagnose(error_text)
    top = diagnoses[0]
    lib = top.get("missing_library")
    pathways = rank_pathways(_pathways_for_signature(top["signature"]), top["signature"])
    pathways = [
        {**p, "steps": _materialize_steps(p["steps"], pm, lib)} for p in pathways
    ]
    synth = synthesize_pathway(top, pm)
    if synth:
        synth["steps"] = _materialize_steps(synth["steps"], pm, lib)
        synth["score"] = 1.0  # bespoke pathways lead
        pathways.insert(0, synth)

    seen_ids = {p["id"] for p in pathways}
    for extra in build_novel_pathway_extras(error_text, diagnoses):
        extra["steps"] = _materialize_steps(extra.get("steps") or [], pm, lib)
        if extra["id"] not in seen_ids:
            pathways.insert(0, extra)
            seen_ids.add(extra["id"])

    pathways.sort(key=lambda p: p.get("score", 0), reverse=True)
    return {
        "package_manager": pm,
        "diagnoses": diagnoses,
        "primary_signature": top["signature"],
        "pathways": pathways,
    }


# Mutating command names / shell features that must never auto-run. Matched as
# whole words so e.g. "ldd" is not flagged by "dd".
_UNSAFE_TOKENS = re.compile(
    r"(\bsudo\b|\brm\b|\bmkfs\b|\bdd\b|\binstall\b|\bmodprobe\b|"
    r"\bdpkg\b|\bapt(-get)?\b|\bpacman\b|\bdnf\b|\byum\b|\bzypper\b|\bapk\b|>{1,2})"
)


def _is_safe_diagnostic(command: str) -> bool:
    """Allow only obviously read-only probes to auto-run."""
    if not command:
        return False
    if _UNSAFE_TOKENS.search(command):
        return False
    safe_prefixes = ("ldd", "ldconfig -p", "ldconfig --print", "test -e", "test -f",
                     "curl -s localhost", "curl -s 'localhost", "cat /etc",
                     "uname", "file ", "getconf")
    return command.strip().startswith(safe_prefixes)


def run_autopilot(
    error_text: str,
    *,
    os_release: Optional[str] = None,
    execute: bool = False,
    allow_mutations: bool = False,
    binary: Optional[str] = None,
    timeout: float = 8.0,
    max_pathway_attempts: Optional[int] = None,
    try_all_pathways: Optional[bool] = None,
    pathway_id: Optional[str] = None,
    sudo_password: Optional[str] = None,
) -> Dict[str, Any]:
    """Full self-healing pass: diagnose -> plan -> optionally probe/apply.

    When ``allow_mutations`` is true, tries ranked pathways (up to
    ``max_pathway_attempts``) until one succeeds or the budget is exhausted.
    """
    from alma_bridge.config import settings

    plan = plan_pathways(error_text, os_release=os_release)
    executed: List[Dict[str, Any]] = []
    executed_remediations: List[Dict[str, Any]] = []
    mutations_applied = False
    pathways_tried: List[str] = []

    if try_all_pathways is None:
        try_all_pathways = bool(settings.operator_try_all_pathways)
    budget = max_pathway_attempts
    if budget is None:
        budget = max(3, int(settings.operator_max_route_attempts // 2)) if try_all_pathways else 1

    if execute and allow_mutations and plan.get("pathways"):
        from alma_bridge.compliance.modernization.apply import apply_pathway_steps

        candidates = plan["pathways"]
        if pathway_id:
            picked = [p for p in candidates if p.get("id") == pathway_id]
            candidates = picked or candidates[:1]
        else:
            candidates = candidates[: max(1, int(budget))]

        for pathway in candidates:
            pathways_tried.append(pathway.get("id", "?"))
            executed_remediations = apply_pathway_steps(
                pathway,
                allow_mutations=True,
                stop_on_error=True,
                timeout=timeout,
                sudo_password=sudo_password,
            )
            if executed_remediations and all(r.get("ok") for r in executed_remediations):
                mutations_applied = True
                record_outcome(
                    plan.get("primary_signature") or "unknown_error",
                    pathway.get("id", "unknown"),
                    True,
                )
                break
            if executed_remediations:
                record_outcome(
                    plan.get("primary_signature") or "unknown_error",
                    pathway.get("id", "unknown"),
                    False,
                )
    elif execute:
        for pathway in plan["pathways"]:
            for step in pathway["steps"]:
                cmd = step.get("command")
                if step.get("kind") != "diagnostic" or not cmd:
                    continue
                run_cmd = cmd.replace("BINARY", binary or "BINARY")
                if "BINARY" in cmd and not binary:
                    continue
                if not _is_safe_diagnostic(run_cmd):
                    continue
                executed.append(_run_diagnostic(run_cmd, timeout=timeout))
            if executed:
                break

    plan["executed_diagnostics"] = executed
    plan["executed_remediations"] = executed_remediations
    plan["mutations_applied"] = mutations_applied
    plan["pathways_tried"] = pathways_tried
    plan["success"] = mutations_applied or bool(executed and all(e.get("ok") for e in executed))
    return plan


def _run_diagnostic(command: str, *, timeout: float) -> Dict[str, Any]:
    try:
        proc = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=timeout
        )
        return {
            "command": command,
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[-2000:],
            "stderr": (proc.stderr or "")[-1000:],
            "ok": proc.returncode == 0,
        }
    except subprocess.TimeoutExpired:
        return {"command": command, "exit_code": None, "stdout": "", "stderr": "timeout", "ok": False}
    except Exception as exc:  # noqa: BLE001 - diagnostics must never crash the API
        return {"command": command, "exit_code": None, "stdout": "", "stderr": str(exc), "ok": False}


def record_outcome(signature: str, pathway_id: str, success: bool) -> None:
    """Feed an outcome back into the learner so ranking improves over time."""
    record_pathway_outcome(signature, pathway_id, success)


def host_summary() -> Dict[str, Any]:
    """Light host context the UI can show next to autopilot output."""
    return {
        "machine": platform.machine(),
        "system": platform.system(),
        "package_manager": detect_package_manager(),
        "python": platform.python_version(),
    }
