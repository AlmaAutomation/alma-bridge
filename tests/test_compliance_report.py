from __future__ import annotations

from pathlib import Path

import pytest

from alma_bridge.compliance.report import build_compliance_report, parse_target


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("example.com", ("example.com", 443)),
        ("example.com:8443", ("example.com", 8443)),
        ("https://example.com/path", ("example.com", 443)),
        ("http://example.com", ("example.com", 80)),
        (("host", 9000), ("host", 9000)),
        ({"host": "h", "port": 1234}, ("h", 1234)),
    ],
)
def test_parse_target(raw, expected):
    assert parse_target(raw) == expected


def _make_pci_device(root, slot, vendor, device, class_code, driver):
    dev_dir = root / "bus" / "pci" / "devices" / slot
    dev_dir.mkdir(parents=True)
    (dev_dir / "vendor").write_text(f"0x{vendor}\n")
    (dev_dir / "device").write_text(f"0x{device}\n")
    (dev_dir / "class").write_text(f"0x{class_code}\n")
    if driver:
        mod = root / "modules" / driver
        mod.mkdir(parents=True, exist_ok=True)
        (dev_dir / "driver").symlink_to(mod)


def test_report_with_missing_driver_is_noncompliant(tmp_path):
    _make_pci_device(tmp_path, "0000:01:00.0", "10de", "1c82", "030000", None)
    report = build_compliance_report(
        targets=[],
        include_drivers=True,
        include_shims=False,
        sys_root=str(tmp_path),
    )
    assert report["overall_compliant"] is False
    assert report["summary"]["missing_drivers"] == 1
    driver_remediations = [r for r in report["remediations"] if r["area"] == "drivers"]
    assert driver_remediations
    assert driver_remediations[0]["severity"] == "high"


def test_report_compliant_when_no_targets_and_all_bound(tmp_path):
    _make_pci_device(tmp_path, "0000:00:1f.6", "8086", "15bc", "020000", "e1000e")
    report = build_compliance_report(
        targets=[],
        include_drivers=True,
        include_shims=False,
        sys_root=str(tmp_path),
    )
    assert report["overall_compliant"] is True
    assert report["summary"]["tls_targets"] == 0
    assert "os" in report["host"]
