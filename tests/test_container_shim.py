"""Tests for Container Shim Pack — VM-like sandbox execution."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alma_bridge.main import create_app
from alma_bridge.execution.container_command import build_container_command
from alma_bridge.execution.container_spec import build_container_run_spec
from alma_bridge.execution.shim_pack import build_shim_pack, sandbox_status
from alma_bridge.automation.playbooks import build_recipe_playbook, list_playbooks


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def test_build_container_command_pe():
    cmd = build_container_command("/tmp/app.exe", binary_format="pe")
    assert cmd == ["wine", "/workspace/app.exe"]


def test_build_container_command_elf_foreign():
    cmd = build_container_command("/tmp/app", binary_format="elf_foreign")
    assert cmd[0] == "qemu-x86_64-static"


def test_container_spec_includes_shim_flags():
    spec = build_container_run_spec(
        file_path="/tmp/demo.sh",
        command=["bash", "/workspace/demo.sh"],
        env={"ALMA_CONTAINER_NETWORK": "host", "ALMA_CONTAINER_MEMORY": "512m"},
        runtime="docker",
        image="alma-bridge-sandbox:latest",
    )
    preview = spec["preview"]
    assert "--network host" in preview
    assert "--memory 512m" in preview
    assert "alma-bridge-sandbox:latest" in preview


def test_build_shim_pack_missing_file():
    result = build_shim_pack("/nonexistent/alma-test-binary")
    assert result["ok"] is False
    assert "not found" in result["error"]


def test_build_shim_pack_native_elf(tmp_path):
    binary = tmp_path / "hello.sh"
    binary.write_text("#!/bin/bash\necho hi\n", encoding="utf-8")
    binary.chmod(0o755)
    result = build_shim_pack(str(binary))
    assert result["ok"] is True
    assert result["binary_format"] == "script"
    assert result["command"]
    assert isinstance(result["shims"], list)
    assert result["container_spec"]["preview"]


def test_container_lab_recipe():
    playbooks = list_playbooks()
    assert any(p["id"] == "container-lab" for p in playbooks)
    recipe = build_recipe_playbook("container-lab", os_release="ID=ubuntu")
    assert recipe["container_lab"] is True
    assert recipe["apply_step_ids"] == []
    ids = [s["id"] for s in recipe["steps"]]
    assert "container_shim_intro" in ids


def test_sandbox_status_structure():
    status = sandbox_status()
    assert "ready" in status
    assert "image" in status
    assert status["shim_count"] >= 14


def test_sandbox_status_api(client):
    resp = client.get("/execution/sandbox/status")
    assert resp.status_code == 200
    assert "ready" in resp.json()


def test_container_shims_api(client):
    resp = client.get("/container/shims")
    assert resp.status_code == 200
    body = resp.json()
    assert "catalog" in body
    assert "recommended" in body
    assert len(body["catalog"]) >= 14


def test_container_shim_pack_api(client, tmp_path):
    script = tmp_path / "run.sh"
    script.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    script.chmod(0o755)
    resp = client.post("/container/shim-pack", json={"file_path": str(script)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["shims"] is not None


@patch("alma_bridge.execution.shim_pack.run_in_container")
def test_container_run_api(mock_run, client, tmp_path):
    script = tmp_path / "run.sh"
    script.write_text("#!/bin/sh\necho ok\n", encoding="utf-8")
    script.chmod(0o755)
    mock_run.return_value = (0, "ok\n", "")
    with patch("alma_bridge.execution.shim_pack.sandbox_ready", return_value=(True, "docker")):
        resp = client.post("/container/run", json={"file_path": str(script)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["executed"] is True
    assert body["success"] is True
