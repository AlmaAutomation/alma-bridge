from __future__ import annotations

from pathlib import Path

from alma_bridge.compliance.drivers import (
    DriverCatalog,
    classify_device,
    inventory_devices,
    read_pci_devices,
)


def _make_pci_device(
    root: Path, slot: str, vendor: str, device: str, class_code: str, driver: str | None
) -> None:
    dev_dir = root / "bus" / "pci" / "devices" / slot
    dev_dir.mkdir(parents=True)
    (dev_dir / "vendor").write_text(f"0x{vendor}\n")
    (dev_dir / "device").write_text(f"0x{device}\n")
    (dev_dir / "class").write_text(f"0x{class_code}\n")
    if driver:
        module_dir = root / "modules" / driver
        module_dir.mkdir(parents=True, exist_ok=True)
        (dev_dir / "driver").symlink_to(module_dir)


def test_read_pci_devices_parses_sysfs(tmp_path):
    _make_pci_device(tmp_path, "0000:00:1f.6", "8086", "15bc", "020000", "e1000e")
    devices = read_pci_devices(str(tmp_path))
    assert len(devices) == 1
    dev = devices[0]
    assert dev["vendor_id"] == "8086"
    assert dev["device_id"] == "15bc"
    assert dev["class_name"] == "network"
    assert dev["driver"] == "e1000e"
    assert dev["bound"] is True


def test_classify_bound_device_is_ok():
    catalog = DriverCatalog()
    dev = {
        "vendor_id": "8086",
        "device_id": "15bc",
        "class_name": "network",
        "driver": "e1000e",
        "bound": True,
    }
    result = classify_device(dev, catalog)
    assert result["status"] == "ok"
    assert result["catalog_vendor"] == "Intel"


def test_classify_unbound_critical_device_is_missing_driver():
    catalog = DriverCatalog()
    dev = {
        "vendor_id": "10de",
        "device_id": "1c82",
        "class_name": "display",
        "driver": None,
        "bound": False,
    }
    result = classify_device(dev, catalog)
    assert result["status"] == "missing_driver"
    assert result["critical"] is True
    assert result["module_hint"]  # NVIDIA hint present


def test_classify_unbound_noncritical_device():
    catalog = DriverCatalog()
    dev = {
        "vendor_id": "1234",
        "device_id": "5678",
        "class_name": "multimedia",
        "driver": None,
        "bound": False,
    }
    result = classify_device(dev, catalog)
    assert result["status"] == "no_driver"
    assert result["critical"] is False


def test_inventory_flags_missing_drivers(tmp_path):
    _make_pci_device(tmp_path, "0000:00:1f.6", "8086", "15bc", "020000", "e1000e")
    _make_pci_device(tmp_path, "0000:01:00.0", "10de", "1c82", "030000", None)
    inv = inventory_devices(str(tmp_path), include_usb=False)
    assert inv["device_count"] == 2
    assert inv["bound_count"] == 1
    assert inv["missing_driver_count"] == 1
    assert inv["compliant"] is False
    assert inv["missing_drivers"][0]["vendor_id"] == "10de"


def test_inventory_compliant_when_all_bound(tmp_path):
    _make_pci_device(tmp_path, "0000:00:1f.6", "8086", "15bc", "020000", "e1000e")
    inv = inventory_devices(str(tmp_path), include_usb=False)
    assert inv["compliant"] is True
    assert inv["missing_driver_count"] == 0
