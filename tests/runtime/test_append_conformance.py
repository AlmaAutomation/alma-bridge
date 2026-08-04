"""Append conformance, verification evidence, and calibration linkage."""

from __future__ import annotations

from pathlib import Path

import pytest

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.compatibility_intelligence.behavior_requirements import get_behavior_profile
from alma_bridge.compatibility_intelligence.coverage_validation import compute_coverage_validation
from alma_bridge.compatibility_intelligence.service import CompatibilityIntelligenceService
from alma_bridge.native_engineering.benchmarks import run_benchmark
from alma_bridge.native_engineering.specifications import get_specification
from alma_bridge.native_runtime.loader.entrypoint import shim_available
from alma_bridge.native_runtime.runtime import run_pe_in_workspace

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "native_runtime" / "bin"
WORK_ITEM_ID = "wi_native_alma_filesystem_basic_io_append_existing_file_v1"


class TestAppendConformance:
    def test_createfilew_spec_supports_append(self):
        spec = get_specification("CreateFileW")
        assert "append_existing_file" in spec.supported_behaviors
        assert "overlapped_io" in spec.unsupported_behaviors

    def test_writefile_spec_supports_append(self):
        spec = get_specification("WriteFile")
        assert "append_existing_file" in spec.supported_behaviors

    def test_behavior_profile_updated(self):
        profile = get_behavior_profile("filesystem.basic_io", "native_alma")
        assert profile is not None
        assert "append_existing_file" in profile.supported_behaviors
        assert "overlapped_io" in profile.unsupported_behaviors
        assert profile.implementation_version == "0.2.1-m2"

    def test_native_vs_workspace_content(self, tmp_path):
        path = FIXTURES / "append_existing_success.exe"
        if not path.is_file() or not shim_available():
            pytest.skip("native shim/fixtures required")
        (tmp_path / "seed.txt").write_text("prior\n", encoding="utf-8")
        result = run_pe_in_workspace(path, workspace=tmp_path)
        assert result.exit_code == 0
        content = (tmp_path / "seed.txt").read_text(encoding="utf-8")
        assert content == "prior\nappended by fixture\n"

    def test_verification_contract_fields(self, tmp_path):
        path = FIXTURES / "append_existing_success.exe"
        if not path.is_file() or not shim_available():
            pytest.skip("native shim/fixtures required")
        (tmp_path / "seed.txt").write_text("base\n", encoding="utf-8")
        result = run_pe_in_workspace(path, workspace=tmp_path)
        contract = {
            "work_item_id": WORK_ITEM_ID,
            "file_existed": True,
            "content_preserved": (tmp_path / "seed.txt").read_text().startswith("base\n"),
            "payload_appended": "appended by fixture" in (tmp_path / "seed.txt").read_text(),
            "workspace_confined": True,
            "simulation_used": result.simulation_used,
            "exit_code": result.exit_code,
        }
        assert contract["content_preserved"]
        assert contract["payload_appended"]
        assert contract["simulation_used"] is False
        digest = sha256_v1(contract)
        assert len(digest) == 64

    def test_benchmark_append_success(self):
        path = FIXTURES / "append_existing_success.exe"
        if not path.is_file() or not shim_available():
            pytest.skip("native shim/fixtures required")
        result = run_benchmark("append_existing_success.exe", allow_execution=True)
        assert result.output_verified
        assert result.metrics[0].value > 0

    def test_calibration_gap_resolved(self, file_append_unsupported_path):
        svc = CompatibilityIntelligenceService()
        analysis = svc.analyze(str(file_append_unsupported_path), persist=False)
        profile = get_behavior_profile("filesystem.basic_io", "native_alma")
        assert profile is not None
        assert "append_existing_file" in profile.supported_behaviors
        validation = compute_coverage_validation(
            analysis.coverage,
            analysis.required_capabilities,
            analysis.imports,
            analysis.api_classifications,
            analysis.metadata,
            provider_id="native_alma",
            fixture_name="file_append_unsupported.exe",
        )
        assert "append_existing_file" in validation.supported_behaviors


@pytest.fixture
def file_append_unsupported_path():
    path = FIXTURES / "file_append_unsupported.exe"
    if not path.is_file():
        pytest.skip("file_append_unsupported fixture not built")
    return path
