"""Distro / package-manager detection shared across compliance modules."""

from __future__ import annotations

import shutil
from typing import Dict, Optional

PACKAGE_MANAGERS: Dict[str, Dict[str, str]] = {
    "apt": {"install": "sudo apt-get install -y {pkgs}", "refresh": "sudo apt-get update"},
    "dnf": {"install": "sudo dnf install -y {pkgs}", "refresh": "sudo dnf makecache"},
    "yum": {"install": "sudo yum install -y {pkgs}", "refresh": "sudo yum makecache"},
    "pacman": {"install": "sudo pacman -S --noconfirm {pkgs}", "refresh": "sudo pacman -Sy"},
    "zypper": {"install": "sudo zypper install -y {pkgs}", "refresh": "sudo zypper refresh"},
    "apk": {"install": "sudo apk add {pkgs}", "refresh": "sudo apk update"},
}


def detect_package_manager(os_release_text: Optional[str] = None) -> str:
    """Best-effort package-manager id (apt/dnf/pacman/...) from os-release/PATH."""
    text = os_release_text
    if text is None:
        try:
            with open("/etc/os-release", "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            text = ""
    ids = set()
    for line in (text or "").splitlines():
        if line.startswith("ID=") or line.startswith("ID_LIKE="):
            value = line.split("=", 1)[1].strip().strip('"')
            ids.update(value.replace(",", " ").split())
    family = {
        "debian": "apt", "ubuntu": "apt", "linuxmint": "apt", "pop": "apt", "raspbian": "apt",
        "fedora": "dnf", "rhel": "dnf", "centos": "dnf", "rocky": "dnf", "almalinux": "dnf",
        "arch": "pacman", "manjaro": "pacman", "endeavouros": "pacman",
        "opensuse": "zypper", "suse": "zypper", "sles": "zypper",
        "alpine": "apk",
    }
    for ident in ids:
        if ident in family:
            return family[ident]
    for mgr in ("apt-get", "dnf", "yum", "pacman", "zypper", "apk"):
        if shutil.which(mgr):
            return "apt" if mgr == "apt-get" else mgr
    return "apt"


def install_cmd(pkgs: list[str], pm: str) -> str:
    tmpl = PACKAGE_MANAGERS.get(pm, PACKAGE_MANAGERS["apt"])["install"]
    return tmpl.format(pkgs=" ".join(pkgs))
