from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alma_bridge.compatibility.program_kind import classify_program_kind, detect_installer
from alma_bridge.execution.program_preflight import check_program_readiness
from alma_bridge.main import create_app
from alma_bridge.storage.outcomes import init_outcome_store


def test_classify_native_elf(tmp_path):
    binary = tmp_path / "hello32"
    binary.write_bytes(b"\x7fELF")
    binary.chmod(0o755)
    kind = classify_program_kind(str(binary))
    assert kind["program_kind"] == "native_elf"
    assert kind["needs_native"] is True
    assert kind["needs_wine"] is False


def test_classify_pe_installer_by_name(tmp_path):
    installer = tmp_path / "game-setup.exe"
    installer.write_bytes(b"MZ")
    assert detect_installer(installer) is True
    kind = classify_program_kind(str(installer))
    assert kind["program_kind"] == "pe_installer"
    assert kind["recommended_args"] == ["/NCRC"]


def test_classify_electron_launcher(tmp_path, monkeypatch):
    app_dir = tmp_path / "MyApp"
    app_dir.mkdir()
    (app_dir / "MyApp.exe").write_bytes(b"MZ")
    (app_dir / "resources.pak").write_bytes(b"x")
    (app_dir / "snapshot_blob.bin").write_bytes(b"x")
    (app_dir / "v8_context_snapshot.bin").write_bytes(b"x")
    kind = classify_program_kind(str(app_dir / "MyApp.exe"))
    assert kind["program_kind"] == "pe_electron_launcher"
    assert kind["is_launcher"] is True
    assert "--disable-gpu" in kind["recommended_args"]


def test_program_preflight_native_ready(tmp_path):
    binary = tmp_path / "hello32"
    binary.write_bytes(b"\x7fELF")
    binary.chmod(0o755)
    result = check_program_readiness(str(binary))
    assert result["ready"] is True
    assert result["recommended_runtime"] == "native"


def test_program_preflight_api(client, tmp_path):
    binary = tmp_path / "hello32"
    binary.write_bytes(b"\x7fELF")
    binary.chmod(0o755)
    response = client.get("/bridge/program/preflight", params={"path": str(binary)})
    assert response.status_code == 200
    body = response.json()
    assert body["program_kind"] == "native_elf"
    assert body["ready"] is True


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    init_outcome_store()
    return TestClient(create_app())
