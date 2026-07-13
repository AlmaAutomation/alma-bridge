from __future__ import annotations

from pathlib import Path

from alma_bridge.compatibility import electron_wine
from alma_bridge.execution.errors import detect_error_signature
from alma_bridge.learning.installer import (
    electron_resources_dir,
    is_electron_builder_elevate,
)


def _make_electron_app(tmp_path: Path) -> Path:
    app = tmp_path / "Ascension Launcher.exe"
    app.write_bytes(b"MZ")
    for marker in ("resources.pak", "snapshot_blob.bin", "libEGL.dll"):
        (tmp_path / marker).write_bytes(b"x")
    res = tmp_path / "resources"
    res.mkdir()
    (res / "app.asar").write_bytes(b"asar")
    (res / "elevate.exe").write_bytes(b"MZ-elevate")
    (res / "AscensionClientServices.exe").write_bytes(b"MZ-sidecar")
    return app


def test_detects_electron_builder_elevate(tmp_path):
    app = _make_electron_app(tmp_path)
    assert is_electron_builder_elevate(str(app))
    assert electron_resources_dir(str(app)) == tmp_path / "resources"


def test_finds_sidecars(tmp_path):
    _make_electron_app(tmp_path)
    res = tmp_path / "resources"
    sidecars = {p.name for p in electron_wine.find_sidecars(res)}
    assert "AscensionClientServices.exe" in sidecars
    # elevate.exe must NOT be treated as a guard sidecar.
    assert "elevate.exe" not in sidecars


def test_launcher_exe_name(tmp_path):
    app = _make_electron_app(tmp_path)
    res = tmp_path / "resources"
    assert electron_wine.launcher_exe_name(str(app), res) == "Ascension Launcher.exe"


def test_prepare_electron_wine_degrades_without_mingw(tmp_path, monkeypatch):
    app = _make_electron_app(tmp_path)
    monkeypatch.setattr(electron_wine, "mingw_compiler", lambda: None)
    report = electron_wine.prepare_electron_wine(str(app))
    assert report["resources"] == str(tmp_path / "resources")
    statuses = {a.get("status") for a in report["actions"]}
    # Without a compiler it reports "unavailable" rather than raising or installing.
    assert "unavailable" in statuses
    # The real sidecar must NOT have been renamed when we cannot build the wrapper.
    assert (tmp_path / "resources" / "AscensionClientServices.exe").exists()
    assert not (tmp_path / "resources" / "AscensionClientServices.real.exe").exists()


def test_install_launcher_decoy_path(tmp_path, monkeypatch):
    app = _make_electron_app(tmp_path)
    res = tmp_path / "resources"
    monkeypatch.setattr(electron_wine, "mingw_compiler", lambda: None)
    result = electron_wine.install_launcher_decoy(res, "Ascension Launcher.exe")
    assert result["status"] == "unavailable"


def test_signature_electron_gpu_beats_generic_gpu():
    # An Electron GPU crash log also contains generic GPU words, but the specific
    # electron_gpu_crash signature must win (ordering in SIGNATURE_PATTERNS).
    log = (
        "ContextResult::kFatalFailure: Failed to create shared context for "
        "virtualization. gpu_channel_manager.cc d3d render"
    )
    assert detect_error_signature(log, "") == "electron_gpu_crash"


def test_signature_launcher_guard_shutdown():
    log = "INFO client_services::launcher_guard: launcher exited, shutting down launcher_pid=260"
    assert detect_error_signature(log, "") == "launcher_guard_shutdown"


def test_signature_electron_crashpad_beats_file_not_found():
    log = (
        "registration_protocol_win.cc:108] CreateFile: File not found. (0x2)\n"
        "crashpad_client_win.cc:142] crash server failed to launch, self-terminating"
    )
    assert detect_error_signature(log, "") == "electron_crashpad_failure"


def test_signature_elevation_failed():
    log = "isAdminRightsRequired is set to true, run installer using elevate.exe"
    assert detect_error_signature(log, "") == "elevation_failed"
