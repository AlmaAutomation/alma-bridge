"""Tests for Ascension flat vs nested layout canonicalization."""

from __future__ import annotations

from alma_bridge.compatibility.ascension_layout import (
    ascension_launcher_layout,
    ascension_resources_for_launcher,
    ascension_stale_flat_resources_dir,
    quarantine_stale_ascension_flat_layout,
)
from alma_bridge.compatibility.electron_wine import prepare_electron_wine


def _nested_install(prefix):
    nested = prefix / "drive_c/Program Files/Ascension Launcher/Ascension Launcher"
    resources = nested / "resources"
    resources.mkdir(parents=True)
    launcher = nested / "Ascension Launcher.exe"
    launcher.write_bytes(b"MZ" + b"\0" * 600_000)
    (resources / "app.asar").write_bytes(b"x" * 100)
    (resources / "elevate.exe").write_bytes(b"MZ" + b"\0" * 100)
    (resources / "AscensionClientServices.real.exe").write_bytes(b"MZ" + b"\0" * 1000)
    return launcher


def test_nested_launcher_layout_detection(tmp_path):
    launcher = _nested_install(tmp_path)
    assert ascension_launcher_layout(str(launcher)) == "nested"
    assert ascension_resources_for_launcher(str(launcher)) == launcher.parent / "resources"


def test_stale_flat_resources_detected_when_nested_canonical(tmp_path):
    launcher = _nested_install(tmp_path)
    stale = tmp_path / "drive_c/Program Files/Ascension Launcher/resources"
    stale.mkdir(parents=True)
    (stale / "AscensionClientServices.real.exe").write_bytes(b"stale")

    found = ascension_stale_flat_resources_dir(str(tmp_path), str(launcher))
    assert found == stale


def test_quarantine_removes_stale_flat_resources(tmp_path):
    launcher = _nested_install(tmp_path)
    stale = tmp_path / "drive_c/Program Files/Ascension Launcher/resources"
    stale.mkdir(parents=True)
    (stale / "AscensionClientServices.real.exe").write_bytes(b"stale")

    result = quarantine_stale_ascension_flat_layout(str(tmp_path), str(launcher))
    assert result["status"] == "quarantined"
    assert not stale.exists()
    assert (tmp_path / "drive_c/Program Files/Ascension Launcher/.alma-quarantine-flat-layout/resources").is_dir()
    assert (launcher.parent / "resources").is_dir()


def test_prepare_electron_wine_quarantines_stale_flat_before_wrapper(tmp_path):
    launcher = _nested_install(tmp_path)
    stale = tmp_path / "drive_c/Program Files/Ascension Launcher/resources"
    stale.mkdir(parents=True)
    (stale / "AscensionClientServices.real.exe").write_bytes(b"stale")

    report = prepare_electron_wine(str(launcher))
    assert not stale.exists()
    assert any(
        a.get("action") == "quarantine_stale_flat_resources" and a.get("status") == "quarantined"
        for a in report["actions"]
        if isinstance(a, dict)
    )


def test_ascension_main_launcher_prefers_nested(tmp_path):
    from alma_bridge.execution.installer_verify import ascension_main_launcher_path

    flat_dir = tmp_path / "drive_c/Program Files/Ascension Launcher"
    nested = flat_dir / "Ascension Launcher"
    nested.mkdir(parents=True)
    flat_exe = flat_dir / "Ascension Launcher.exe"
    flat_exe.write_bytes(b"MZ" + b"\0" * 600_000)
    nested_exe = nested / "Ascension Launcher.exe"
    nested_exe.write_bytes(b"MZ" + b"\0" * 700_000)

    found = ascension_main_launcher_path(str(tmp_path))
    assert found == str(nested_exe)
