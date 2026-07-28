"""Tests for CompatibilityRunEnvironment capture and serialization."""

from __future__ import annotations

from alma_bridge.compatibility.run_environment import (
    RUN_ENVIRONMENT_SCHEMA_VERSION,
    CompatibilityRunEnvironment,
    capture_run_environment,
    environment_from_dict,
    environment_to_dict,
)
from alma_bridge.schemas.models import AttemptRecord, ExecutionMode


def _sample_record(**overrides) -> AttemptRecord:
    base = dict(
        attempt_number=1,
        strategy_id="wine_gui",
        remediation_id=None,
        runtime="wine",
        command=["wine", "/opt/app.exe"],
        env={"WINEPREFIX": "/tmp/prefix-a"},
        mode=ExecutionMode.HOST,
        success=True,
        exit_code=0,
        error_signature=None,
        detected_error=None,
        stdout="",
        stderr="",
        duration_ms=1000,
        phase="wine_gui",
    )
    base.update(overrides)
    return AttemptRecord(**base)


class TestCompatibilityRunEnvironment:
    def test_deterministic_serialization(self):
        env = CompatibilityRunEnvironment(
            alma_bridge_version="0.1.0",
            host_os="Linux (Ubuntu)",
            host_architecture="x86_64",
            wine_version="wine-9.0",
            relevant_runtime_identities=["runtime:wine", "phase:wine_gui"],
        )
        first = environment_to_dict(env)
        second = environment_to_dict(env)
        assert first == second
        assert first["schema_version"] == RUN_ENVIRONMENT_SCHEMA_VERSION
        assert env.identity_fingerprint() == env.identity_fingerprint()

    def test_missing_fields_not_fabricated(self):
        env = CompatibilityRunEnvironment(alma_bridge_version="0.1.0")
        payload = environment_to_dict(env)
        assert "wine_version" not in payload
        assert "host_os" not in payload
        assert payload["alma_bridge_version"] == "0.1.0"

    def test_capture_from_hardware_and_record(self):
        hardware = {
            "os": "Linux",
            "distribution": "Ubuntu",
            "architecture": "x86_64",
            "os_version": "6.8.0-generic",
            "paths": {"wine": "/usr/bin/wine"},
        }
        snapshot = capture_run_environment(
            hardware_profile=hardware,
            record=_sample_record(),
            wine_version="wine-9.0 (Ubuntu)",
        )
        assert snapshot is not None
        assert snapshot.host_os == "Linux (Ubuntu)"
        assert snapshot.host_architecture == "x86_64"
        assert snapshot.wine_version == "wine-9.0 (Ubuntu)"
        assert snapshot.prefix_id is not None
        assert "runtime:wine" in snapshot.relevant_runtime_identities

    def test_environment_from_dict_roundtrip(self):
        original = CompatibilityRunEnvironment(
            host_os="Linux",
            wine_version="wine-8.0",
        )
        restored = environment_from_dict(environment_to_dict(original))
        assert restored is not None
        assert restored.wine_version == "wine-8.0"
        assert restored.identity_fingerprint() == original.identity_fingerprint()
