"""Driver / device compliance.

Inventories PCI and USB devices straight from sysfs (no third-party deps), maps
each to a human-readable class, reports whether a kernel driver is bound, and
classifies devices against a small built-in catalog plus an optional SQLite
catalog inherited from the legacy ``automatic driver detection`` prototype.

The sysfs root is injectable so the logic can be unit-tested against a fake
tree without touching the host.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

# High byte of the PCI class code -> friendly name.
_PCI_CLASS_NAMES = {
    0x00: "unclassified",
    0x01: "storage",
    0x02: "network",
    0x03: "display",
    0x04: "multimedia",
    0x05: "memory",
    0x06: "bridge",
    0x07: "communication",
    0x08: "system",
    0x09: "input",
    0x0A: "docking",
    0x0B: "processor",
    0x0C: "serial_bus",
    0x0D: "wireless",
    0x0E: "intelligent",
    0x0F: "satellite",
    0x10: "encryption",
    0x11: "signal_processing",
}

# Device classes where an unbound driver is a real compliance problem.
_CRITICAL_CLASSES = {"storage", "network", "display", "wireless"}

# Cache of the parsed SQLite catalog, keyed by (path, mtime). Avoids re-opening
# the DB on every inventory call.
_CATALOG_CACHE: Dict[tuple, Dict[str, Dict[str, str]]] = {}

# Minimal built-in catalog: VENDOR:DEVICE (lowercase hex, no 0x) -> module hint.
# Catalogs can be extended via the legacy driver_compatibility.db.
_BUILTIN_CATALOG: Dict[str, Dict[str, str]] = {
    "8086:*": {"vendor": "Intel", "module_hint": "e1000e/i915/iwlwifi"},
    "10de:*": {"vendor": "NVIDIA", "module_hint": "nvidia/nouveau"},
    "1002:*": {"vendor": "AMD/ATI", "module_hint": "amdgpu/radeon"},
    "14e4:*": {"vendor": "Broadcom", "module_hint": "tg3/b43/wl"},
    "10ec:*": {"vendor": "Realtek", "module_hint": "r8169/rtl8xxxu"},
}


def _read(path: Path) -> Optional[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None


def _hex_no_prefix(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip().lower()
    return value[2:] if value.startswith("0x") else value


def _driver_for(device_dir: Path) -> Optional[str]:
    """Return the bound kernel module name, or ``None`` if unbound."""
    link = device_dir / "driver"
    if link.is_symlink() or link.exists():
        try:
            return os.path.basename(os.path.realpath(link))
        except OSError:
            return None
    return None


def read_pci_devices(sys_root: str = "/sys") -> List[Dict[str, Any]]:
    base = Path(sys_root) / "bus" / "pci" / "devices"
    devices: List[Dict[str, Any]] = []
    if not base.exists():
        return devices
    for entry in sorted(base.iterdir()):
        vendor = _hex_no_prefix(_read(entry / "vendor"))
        device = _hex_no_prefix(_read(entry / "device"))
        if not vendor or not device:
            continue
        class_raw = _hex_no_prefix(_read(entry / "class")) or ""
        class_hi = int(class_raw[:2], 16) if len(class_raw) >= 2 else -1
        driver = _driver_for(entry)
        devices.append(
            {
                "bus": "pci",
                "slot": entry.name,
                "vendor_id": vendor,
                "device_id": device,
                "class_code": class_raw,
                "class_name": _PCI_CLASS_NAMES.get(class_hi, "unknown"),
                "driver": driver,
                "bound": driver is not None,
            }
        )
    return devices


def read_usb_devices(sys_root: str = "/sys") -> List[Dict[str, Any]]:
    base = Path(sys_root) / "bus" / "usb" / "devices"
    devices: List[Dict[str, Any]] = []
    if not base.exists():
        return devices
    for entry in sorted(base.iterdir()):
        vendor = _hex_no_prefix(_read(entry / "idVendor"))
        product = _hex_no_prefix(_read(entry / "idProduct"))
        if not vendor or not product:
            continue
        driver = _driver_for(entry)
        devices.append(
            {
                "bus": "usb",
                "slot": entry.name,
                "vendor_id": vendor,
                "device_id": product,
                "class_name": (_read(entry / "product") or "usb_device"),
                "driver": driver,
                "bound": driver is not None,
            }
        )
    return devices


class DriverCatalog:
    """Built-in catalog, optionally enriched from the legacy SQLite DB."""

    def __init__(self, entries: Optional[Dict[str, Dict[str, str]]] = None) -> None:
        self.entries: Dict[str, Dict[str, str]] = dict(_BUILTIN_CATALOG)
        if entries:
            self.entries.update(entries)

    @classmethod
    def load(cls, db_path: Optional[Path] = None) -> "DriverCatalog":
        catalog = cls()
        if db_path and Path(db_path).exists():
            path = Path(db_path)
            try:
                mtime = path.stat().st_mtime
            except OSError:
                mtime = 0.0
            cache_key = (str(path), mtime)
            cached = _CATALOG_CACHE.get(cache_key)
            if cached is not None:
                catalog.entries = dict(cached)
            else:
                catalog._load_sqlite(path)
                _CATALOG_CACHE.clear()
                _CATALOG_CACHE[cache_key] = dict(catalog.entries)
        return catalog

    def _load_sqlite(self, db_path: Path) -> None:
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        except sqlite3.Error:
            return
        try:
            cur = conn.cursor()
            tables = {
                row[0]
                for row in cur.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            if "drivers" not in tables:
                return
            cols = {row[1] for row in cur.execute("PRAGMA table_info(drivers)")}
            if not {"vendor_id", "device_id"} <= cols:
                return
            for row in cur.execute(
                "SELECT vendor_id, device_id FROM drivers"
            ):
                vendor = _hex_no_prefix(str(row[0]))
                device = _hex_no_prefix(str(row[1]))
                if vendor and device:
                    self.entries[f"{vendor}:{device}"] = {
                        "vendor": "catalog",
                        "module_hint": "see driver catalog",
                    }
        except sqlite3.Error:
            pass
        finally:
            conn.close()

    def lookup(self, vendor_id: str, device_id: str) -> Optional[Dict[str, str]]:
        exact = self.entries.get(f"{vendor_id}:{device_id}")
        if exact:
            return exact
        return self.entries.get(f"{vendor_id}:*")


def classify_device(device: Dict[str, Any], catalog: DriverCatalog) -> Dict[str, Any]:
    """Annotate a device with a compliance status."""
    catalog_hit = catalog.lookup(device["vendor_id"], device["device_id"])
    critical = device.get("class_name") in _CRITICAL_CLASSES

    if device.get("bound"):
        status = "ok"
        detail = f"bound to {device.get('driver')}"
    elif critical:
        status = "missing_driver"
        detail = f"{device.get('class_name')} device has no kernel driver bound"
    else:
        status = "no_driver"
        detail = "no kernel driver bound (non-critical class)"

    result = dict(device)
    result["status"] = status
    result["detail"] = detail
    result["catalog_vendor"] = catalog_hit.get("vendor") if catalog_hit else None
    result["module_hint"] = catalog_hit.get("module_hint") if catalog_hit else None
    result["critical"] = critical
    return result


def inventory_devices(
    sys_root: str = "/sys",
    *,
    catalog_db: Optional[Path] = None,
    include_usb: bool = True,
) -> Dict[str, Any]:
    """Full device inventory with per-device compliance classification."""
    catalog = DriverCatalog.load(catalog_db)
    raw = read_pci_devices(sys_root)
    if include_usb:
        raw += read_usb_devices(sys_root)

    classified = [classify_device(dev, catalog) for dev in raw]
    missing = [d for d in classified if d["status"] == "missing_driver"]

    return {
        "device_count": len(classified),
        "bound_count": sum(1 for d in classified if d["bound"]),
        "missing_driver_count": len(missing),
        "devices": classified,
        "missing_drivers": missing,
        "compliant": not missing,
    }
