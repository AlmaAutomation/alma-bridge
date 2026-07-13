from __future__ import annotations

import json
import sqlite3

import pytest

from alma_bridge.learning.ranker import rank_strategies, ranker_status
from alma_bridge.learning.training import (
    build_feature_row,
    load_ranker_artifact,
    normalize_strategy_id,
    train_strategy_ranker,
)
from alma_bridge.compatibility.strategies import STRATEGIES
from alma_bridge.storage.outcomes import init_outcome_store


def _seed_training_db(db_path, rows: int = 20):
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE bridge_sessions (
            session_id TEXT PRIMARY KEY,
            file_path TEXT,
            file_hash TEXT,
            started_at TEXT,
            finished_at TEXT,
            success INTEGER,
            hardware_profile TEXT,
            summary TEXT
        );
        CREATE TABLE bridge_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            attempt_number INTEGER,
            strategy_id TEXT,
            remediation_id TEXT,
            runtime TEXT,
            command TEXT,
            env TEXT,
            mode TEXT,
            success INTEGER,
            exit_code INTEGER,
            error_signature TEXT,
            detected_error TEXT,
            stdout TEXT,
            stderr TEXT,
            duration_ms INTEGER,
            created_at TEXT
        );
        """
    )
    hardware = json.dumps(
        {
            "architecture": "x86_64",
            "capabilities": {"wine": True, "docker": True, "multiarch": True, "proton": False},
            "gpu": {"vendor": "intel"},
            "storage_type": "ssd",
            "ram_gb": 16,
            "legacy_indicators": [],
        }
    )
    for index in range(rows):
        success = 1 if index % 3 != 0 else 0
        strategy = "native_host" if index % 2 == 0 else "wine_host"
        runtime = "native" if strategy == "native_host" else "wine"
        file_path = "/tmp/app.AppImage" if strategy == "native_host" else "/tmp/game.exe"
        session_id = f"sess-{index}"
        conn.execute(
            """
            INSERT INTO bridge_sessions (
                session_id, file_path, started_at, success, hardware_profile, summary
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, file_path, "2026-06-07T00:00:00", success, hardware, "test"),
        )
        conn.execute(
            """
            INSERT INTO bridge_attempts (
                session_id, attempt_number, strategy_id, remediation_id, runtime,
                command, env, mode, success, exit_code, error_signature, detected_error,
                stdout, stderr, duration_ms, created_at
            ) VALUES (?, 1, ?, NULL, ?, '[]', '{}', 'host', ?, 0, 'unknown_error', 'unknown_error', '', '', 0, '2026-06-07T00:00:00')
            """,
            (session_id, strategy, runtime, success),
        )
    conn.commit()
    conn.close()


def test_normalize_strategy_id_maps_appimage():
    assert normalize_strategy_id("sysdet_/tmp/foo.AppImage", "native", "/tmp/foo.AppImage") == "native_host"


def test_build_feature_row():
    row = build_feature_row(
        {
            "strategy_id": "wine_host",
            "runtime": "wine",
            "file_path": "/tmp/test.exe",
            "hardware_profile": {"capabilities": {"wine": True}, "gpu": {"vendor": "nvidia"}},
            "error_signature": "missing_dll",
        }
    )
    assert row["strategy_id"] == "wine_host"
    assert row["binary_format"] == "pe"
    assert row["wine_cap"] == 1


def test_train_strategy_ranker(tmp_path, monkeypatch):
    db_path = tmp_path / "outcomes.db"
    model_path = tmp_path / "model.joblib"
    meta_path = tmp_path / "model.json"

    monkeypatch.setattr("alma_bridge.config.settings.db_path", db_path)
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.ranker_model_path", model_path)
    monkeypatch.setattr("alma_bridge.config.settings.ranker_metadata_path", meta_path)

    _seed_training_db(db_path, rows=24)
    init_outcome_store()

    result = train_strategy_ranker()
    assert result["trained"] is True
    assert result["records"] == 24
    assert model_path.exists()
    assert meta_path.exists()
    assert load_ranker_artifact() is not None


def test_ranker_uses_trained_model(tmp_path, monkeypatch):
    db_path = tmp_path / "outcomes.db"
    model_path = tmp_path / "model.joblib"
    meta_path = tmp_path / "model.json"

    monkeypatch.setattr("alma_bridge.config.settings.db_path", db_path)
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.ranker_model_path", model_path)
    monkeypatch.setattr("alma_bridge.config.settings.ranker_metadata_path", meta_path)

    _seed_training_db(db_path, rows=24)
    init_outcome_store()
    train_strategy_ranker()

    hardware = {
        "architecture": "x86_64",
        "capabilities": {"wine": True, "docker": True, "multiarch": True},
        "gpu": {"vendor": "intel"},
        "storage_type": "ssd",
        "ram_gb": 16,
        "legacy_indicators": [],
    }
    ranked = rank_strategies(
        STRATEGIES,
        file_path="/tmp/test.AppImage",
        hardware_profile=hardware,
    )
    assert ranked
    status = ranker_status()
    assert status["model_loaded"] is True
