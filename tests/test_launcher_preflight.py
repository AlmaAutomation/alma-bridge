from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alma_bridge.execution.launcher_preflight import check_launcher_readiness
from alma_bridge.main import create_app
from alma_bridge.storage.outcomes import init_outcome_store


def _electron_app_dir(tmp_path, exe_name: str):
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / exe_name).write_bytes(b"MZ")
    (app_dir / "resources.pak").write_bytes(b"x")
    (app_dir / "snapshot_blob.bin").write_bytes(b"x")
    (app_dir / "v8_context_snapshot.bin").write_bytes(b"x")
    return app_dir / exe_name


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    init_outcome_store()
    return TestClient(create_app())


def test_launcher_preflight_electron_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    launcher = _electron_app_dir(tmp_path, "Game Launcher.exe")
    monkeypatch.setattr(
        "alma_bridge.execution.program_preflight.profile_hardware",
        lambda: {"paths": {"wine": "/usr/bin/wine"}, "capabilities": {"wine": True}},
    )
    monkeypatch.setattr(
        "alma_bridge.execution.program_preflight.shutil.which",
        lambda name: "/usr/bin/wine" if name == "wine" else None,
    )

    result = check_launcher_readiness(str(launcher))
    assert result["is_launcher"] is True
    assert result["program_kind"] == "pe_electron_launcher"
    assert result["recommended_remediation_id"] == "electron_disable_gpu"
    assert "--disable-gpu" in result["recommended_args"]
    assert result["is_installer"] is False


def test_launcher_preflight_api(client, tmp_path, monkeypatch):
    monkeypatch.setenv("DISPLAY", ":0")
    launcher = _electron_app_dir(tmp_path, "game.exe")
    monkeypatch.setattr(
        "alma_bridge.execution.program_preflight.profile_hardware",
        lambda: {"paths": {"wine": "/usr/bin/wine"}, "capabilities": {"wine": True}},
    )
    monkeypatch.setattr(
        "alma_bridge.execution.program_preflight.shutil.which",
        lambda name: "/usr/bin/wine" if name == "wine" else None,
    )

    response = client.get(
        "/bridge/launcher/preflight",
        params={"path": str(launcher)},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_launcher"] is True
    assert body["ready"] is True
