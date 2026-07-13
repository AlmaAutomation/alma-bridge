from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alma_bridge.hardware.asod import enrich_summary, get_asod_summary
from alma_bridge.hardware.profiler import profile_hardware
from alma_bridge.hardware.shims import recommended_shims_from_profile
from alma_bridge.importers.resolve import import_resolve_audits
from alma_bridge.importers.sysdet import import_sysdet_history
from alma_bridge.main import create_app
from alma_bridge.storage import outcomes
from alma_bridge.storage.outcomes import get_stats, init_outcome_store


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    init_outcome_store()
    return TestClient(create_app())


@pytest.fixture()
def sysdet_db(tmp_path) -> Path:
    db_path = tmp_path / "alma.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE execution_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            file_path TEXT,
            file_name TEXT,
            file_hash TEXT,
            runtime TEXT,
            architecture TEXT,
            installer_type TEXT,
            command TEXT,
            success INTEGER,
            exit_code INTEGER,
            detected_error TEXT,
            remediation_applied TEXT,
            stdout TEXT,
            stderr TEXT,
            telemetry_snapshot TEXT,
            metadata TEXT
        );
        """
    )
    conn.execute(
        """
        INSERT INTO execution_history (
            timestamp, file_path, file_name, runtime, command, success, exit_code,
            detected_error, stdout, stderr, telemetry_snapshot, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-06-07T10:00:00",
            "/tmp/test.exe",
            "test.exe",
            "wine",
            '["wine", "/tmp/test.exe"]',
            0,
            1,
            "missing_dll",
            "",
            "failed to load dll msvcp140.dll",
            '{"cpu": 10.0}',
            json.dumps(
                {
                    "started_at": "2026-06-07T10:00:00",
                    "finished_at": "2026-06-07T10:00:05",
                    "error_signature": "missing_dll",
                }
            ),
        ),
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def resolve_audit_dir(tmp_path) -> Path:
    audit_dir = tmp_path / "audit"
    audit_dir.mkdir()
    (audit_dir / "test_launcher_with_software_rendering.json").write_text(
        json.dumps(
            {
                "prefix_path": "/tmp/prefix",
                "target_path": "/tmp/prefix/app.exe",
                "script_path": "runtime_data/launch_with_software_rendering.sh",
            }
        ),
        encoding="utf-8",
    )
    runtime_dir = tmp_path / "runtime_data"
    runtime_dir.mkdir()
    (runtime_dir / "launcher_stderr.log").write_text("vulkan error", encoding="utf-8")
    return audit_dir


def test_asod_summary_has_legacy_indicators():
    summary = enrich_summary(get_asod_summary())
    assert "legacy_indicators" in summary
    assert "gpu" in summary


def test_profile_hardware_includes_asod():
    profile = profile_hardware()
    assert "asod" in profile
    assert "storage_type" in profile
    assert "recommended_shims" not in profile


def test_recommended_shims_from_profile():
    profile = {
        "legacy_indicators": ["low_memory", "rotational_storage"],
        "asod": {"legacy_indicators": []},
    }
    shims = recommended_shims_from_profile(profile)
    ids = {shim["id"] for shim in shims}
    assert "old_cpu_compat" in ids
    assert "hdd_io_compat" in ids


def test_import_sysdet_normalizes_strategy_id(client, sysdet_db, tmp_path, monkeypatch):
    conn = sqlite3.connect(sysdet_db)
    conn.execute(
        """
        INSERT INTO execution_history (
            timestamp, file_path, file_name, runtime, command, success, exit_code,
            detected_error, stdout, stderr, telemetry_snapshot, metadata
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-06-07T11:00:00",
            "/tmp/ascension.exe",
            "ascension.exe",
            "wine",
            '["wine", "/tmp/ascension.exe"]',
            1,
            0,
            "",
            "",
            "",
            "{}",
            json.dumps({"strategy_id": "sysdet_wine"}),
        ),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    init_outcome_store()

    import_sysdet_history(sysdet_db, skip_existing=False)

    with outcomes._connect() as conn:
        row = conn.execute(
            "SELECT strategy_id FROM bridge_attempts WHERE strategy_id = 'wine_host'"
        ).fetchone()
    assert row is not None


def test_import_sysdet(client, sysdet_db, tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    init_outcome_store()

    result = import_sysdet_history(sysdet_db)
    assert result["imported_sessions"] == 1
    assert result["imported_attempts"] == 1

    stats = get_stats()
    assert stats["total_attempts"] == 1


def test_import_resolve(client, resolve_audit_dir, tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    init_outcome_store()

    result = import_resolve_audits(
        resolve_audit_dir,
        runtime_data_dir=resolve_audit_dir.parent / "runtime_data",
    )
    assert result["imported_sessions"] == 1
    assert result["imported_attempts"] == 1


def test_import_api(client, sysdet_db, resolve_audit_dir):
    response = client.post(
        "/import/all",
        json={
            "sysdet_db": str(sysdet_db),
            "resolve_audit_dir": str(resolve_audit_dir),
            "skip_existing": False,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total_sessions"] >= 2
    assert body["total_attempts"] >= 2
