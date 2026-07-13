"""32-bit legacy readiness: can this host run 32-bit binaries, and how to get there.

Two halves:

  * ``assess_32bit_support`` — read-only inspection of the host: CPU/OS bitness,
    presence of the 32-bit ELF loader, multiarch state, core i386 runtime libs,
    and emulation/translation fallbacks (qemu-user, box86/box64, 32-bit Wine).
  * ``plan_32bit_enablement`` — distro-aware, ordered steps to close whatever
    gaps were found, so even the most legacy 32-bit software runs on a modern
    host (or a legacy 32-bit host reaches modern services via Alma's bridges).

All probes are filesystem/PATH lookups plus optionally a couple of read-only
commands; nothing here mutates the system.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Any, Dict, List, Optional

from alma_bridge.compliance.pm import PACKAGE_MANAGERS, detect_package_manager

# 32-bit ELF program interpreters by arch.
_LOADERS_32 = ["/lib/ld-linux.so.2", "/lib32/ld-linux.so.2", "/usr/lib/ld-linux.so.2"]
# Representative core i386 runtime libs (Debian/RPM multilib paths).
_CORE_I386_LIBS = [
    "/lib/i386-linux-gnu/libc.so.6",
    "/usr/lib/i386-linux-gnu/libc.so.6",
    "/lib32/libc.so.6",
    "/usr/lib32/libc.so.6",
    "/usr/lib/libc.so.6",  # native on a genuinely 32-bit host
]


def _first_existing(paths: List[str], root: str = "") -> Optional[str]:
    for path in paths:
        candidate = os.path.join(root, path.lstrip("/")) if root else path
        if os.path.exists(candidate):
            return candidate
    return None


def _foreign_architectures() -> List[str]:
    """dpkg foreign architectures (i386 => multiarch enabled). Empty if unknown."""
    if not shutil.which("dpkg"):
        return []
    try:
        proc = subprocess.run(
            ["dpkg", "--print-foreign-architectures"],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode == 0:
            return [a for a in proc.stdout.split() if a]
    except (OSError, subprocess.SubprocessError):
        return []
    return []


def assess_32bit_support(*, root: str = "") -> Dict[str, Any]:
    machine = platform.machine().lower()
    is_64 = machine in {"x86_64", "amd64", "aarch64", "arm64", "ppc64le", "s390x"}
    # Only x86-class 64-bit hosts can run x86 32-bit binaries via multiarch; other
    # 64-bit hosts (arm64, ppc64le, ...) need qemu/box86 translation.
    is_x86_64 = machine in {"x86_64", "amd64"}
    native_32 = machine in {"i386", "i486", "i586", "i686", "x86", "armv6l", "armv7l"}

    loader = _first_existing(_LOADERS_32, root)
    core_lib = _first_existing(_CORE_I386_LIBS, root)
    foreign = _foreign_architectures() if not root else []
    multiarch_enabled = "i386" in foreign or bool(
        _first_existing(["/lib/i386-linux-gnu", "/usr/lib/i386-linux-gnu", "/usr/lib32"], root)
    )

    qemu = shutil.which("qemu-i386") or shutil.which("qemu-i386-static")
    box86 = shutil.which("box86")
    wine = shutil.which("wine")

    capabilities = {
        "cpu_machine": machine,
        "os_is_64bit": is_64,
        "os_is_native_32bit": native_32,
        "elf32_loader": loader,
        "core_i386_lib": core_lib,
        "multiarch_enabled": multiarch_enabled,
        "foreign_architectures": foreign,
        "qemu_i386": qemu,
        "box86": box86,
        "wine": wine,
    }

    gaps: List[str] = []
    if native_32:
        # Genuinely 32-bit host: it already runs 32-bit code natively. The real
        # job is modern connectivity, handled by the TLS/DNS/CA pathways.
        ready = True
        notes = ("Native 32-bit host: runs 32-bit binaries directly. Use Alma's "
                 "TLS bridge, modern CA bundle and DoH for modern connectivity.")
    elif is_x86_64:
        if not loader:
            gaps.append("missing_elf32_loader")
        if not core_lib:
            gaps.append("missing_core_i386_libs")
        if not multiarch_enabled:
            gaps.append("multiarch_disabled")
        ready = not gaps
        notes = ("64-bit host can run 32-bit binaries once multiarch + the i386 "
                 "runtime are installed." if not ready
                 else "64-bit host is already 32-bit ready.")
    else:
        # Non-x86 64-bit (e.g. arm64): need translation for x86-32 binaries.
        if not (qemu or box86):
            gaps.append("missing_x86_translation")
        ready = not gaps
        notes = ("Non-x86 host: x86 32-bit binaries need qemu-user or box86 "
                 "translation." if not ready else "Translation layer present.")

    return {
        "ready": ready,
        "verdict": "ready" if ready else "needs_enablement",
        "capabilities": capabilities,
        "gaps": gaps,
        "notes": notes,
    }


def plan_32bit_enablement(
    assessment: Optional[Dict[str, Any]] = None,
    *,
    os_release: Optional[str] = None,
    root: str = "",
) -> Dict[str, Any]:
    """Ordered, distro-aware steps to make the host run 32-bit binaries."""
    assessment = assessment or assess_32bit_support(root=root)
    pm = detect_package_manager(os_release)
    refresh = PACKAGE_MANAGERS.get(pm, PACKAGE_MANAGERS["apt"])["refresh"]
    gaps = set(assessment.get("gaps", []))
    steps: List[Dict[str, Any]] = []

    def add(desc: str, command: Optional[str] = None, *, root_required: bool = False,
            kind: str = "remediation") -> None:
        steps.append({"description": desc, "command": command,
                      "requires_root": root_required, "kind": kind})

    if assessment.get("ready"):
        add("Host is already 32-bit ready — verify by running a 32-bit binary.",
            "file /path/to/binary && /path/to/binary --version", kind="diagnostic")
    elif "missing_x86_translation" in gaps:
        if pm == "apt":
            add("Install qemu user-mode emulation for x86.",
                "sudo apt-get install -y qemu-user-static binfmt-support", root_required=True)
        else:
            add("Install qemu user-mode emulation for x86.",
                PACKAGE_MANAGERS.get(pm, PACKAGE_MANAGERS["apt"])["install"].format(
                    pkgs="qemu-user-static"), root_required=True)
        add("Alternatively install box86/box64 for faster ARM->x86 translation.",
            "# see https://github.com/ptitSeb/box86")
    else:
        if pm == "apt":
            if "multiarch_disabled" in gaps:
                add("Enable the i386 architecture.",
                    "sudo dpkg --add-architecture i386", root_required=True)
            add("Refresh package metadata.", refresh, root_required=True)
            if "missing_core_i386_libs" in gaps or "missing_elf32_loader" in gaps:
                add("Install the 32-bit runtime, loader and common libraries.",
                    "sudo apt-get install -y libc6:i386 libstdc++6:i386 zlib1g:i386 "
                    "libncurses6:i386 libgcc-s1:i386", root_required=True)
        elif pm in ("dnf", "yum"):
            add("Install 32-bit glibc and common libraries (multilib).",
                f"sudo {pm} install -y glibc.i686 libstdc++.i686 zlib.i686 ncurses-libs.i686",
                root_required=True)
        elif pm == "pacman":
            add("Enable the [multilib] repo in /etc/pacman.conf, then sync.",
                "sudo sed -i '/\\[multilib\\]/,/Include/s/^#//' /etc/pacman.conf && "
                "sudo pacman -Sy", root_required=True)
            add("Install the 32-bit runtime.",
                "sudo pacman -S --noconfirm lib32-glibc lib32-gcc-libs lib32-zlib",
                root_required=True)
        elif pm == "zypper":
            add("Install 32-bit glibc and libraries.",
                "sudo zypper install -y glibc-32bit libstdc++6-32bit libz1-32bit",
                root_required=True)
        else:
            add("Install your distro's 32-bit C runtime (glibc/libstdc++/zlib).")
        add("Rebuild the dynamic linker cache.", "sudo ldconfig", root_required=True)
        add("Confirm the 32-bit loader now exists.",
            "test -e /lib/ld-linux.so.2 && echo '32-bit ready'", kind="diagnostic")

    # Connectivity modernization always applies to legacy boxes.
    add("Modernize HTTPS for the legacy app via Alma's TLS bridge if it can't do TLS 1.2+.",
        "curl -s -X POST localhost:8800/compliance/tls/bridge "
        "-H 'content-type: application/json' "
        "-d '{\"upstream_host\":\"HOST\",\"upstream_port\":443}'")
    add("Install Alma's current CA bundle so modern certs validate.",
        "curl -s localhost:8800/compliance/tls/ca-bundle -o alma-ca.pem")

    return {
        "package_manager": pm,
        "gaps": sorted(gaps),
        "ready": assessment.get("ready", False),
        "steps": steps,
    }
