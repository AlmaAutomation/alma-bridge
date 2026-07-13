from __future__ import annotations

from alma_bridge.execution.installer_preflight import check_installer_readiness


def test_installer_preflight_detects_missing_file(tmp_path, monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    result = check_installer_readiness(str(tmp_path / "missing-setup.exe"))
    assert result["ready"] is False
    assert any("not found" in item.lower() for item in result["blockers"])


def test_installer_preflight_requires_display(tmp_path, monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    installer = tmp_path / "ascension-setup.exe"
    installer.write_bytes(b"MZ")
    result = check_installer_readiness(str(installer))
    assert result["is_installer"] is True
    assert any("GUI session" in item for item in result["blockers"])


def test_installer_preflight_ready_with_display(tmp_path, monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    installer = tmp_path / "game-setup.exe"
    installer.write_bytes(b"MZ")
    monkeypatch.setattr(
        "alma_bridge.execution.program_preflight.profile_hardware",
        lambda: {"paths": {"wine": "/usr/bin/wine"}, "capabilities": {"wine": True}},
    )
    monkeypatch.setattr(
        "alma_bridge.execution.program_preflight.shutil.which",
        lambda name: "/usr/bin/wine" if name == "wine" else None,
    )
    result = check_installer_readiness(str(installer))
    assert result["ready"] is True
    assert result["display"] == ":0"
    assert result["recommended_max_attempts"] == 18
