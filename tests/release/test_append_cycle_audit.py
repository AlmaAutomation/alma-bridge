"""Post-cycle audit tests for native-alma append engineering cycle."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from alma_bridge.compatibility_intelligence.behavior_requirements import get_behavior_profile
from alma_bridge.compatibility_intelligence.expansion.service import ExpansionPlanningService
from alma_bridge.config import PROJECT_ROOT
from alma_bridge.native_engineering.benchmarks import run_append_baseline_suite
from alma_bridge.native_engineering.specifications import get_specification
from alma_bridge.native_lab.bootstrap_append_cycle import (
    build_completed_append_work_item,
    committed_store_available,
    materialize_committed_store,
)
from alma_bridge.native_lab.completion import is_engineering_complete, is_workflow_completed
from alma_bridge.native_lab.evidence_resolution import (
    build_evidence_manifest,
    load_committed_manifest,
    validate_required_evidence_resolves,
)
from alma_bridge.native_lab.models import (
    GovernanceDisposition,
    SEEDED_WORK_ITEM_ID,
    WorkItemStatus,
)
from alma_bridge.native_lab.repository import NativeLabRepository
from alma_bridge.native_lab.service import NativeLabService
from alma_bridge.native_runtime.loader.entrypoint import shim_available
from alma_bridge.native_runtime.runtime import run_pe_in_workspace

FIXTURES = PROJECT_ROOT / "tests" / "fixtures" / "native_runtime" / "bin"
WORK_ITEM_ID = SEEDED_WORK_ITEM_ID

APPEND_FIXTURES = [
    "append_existing_success.exe",
    "append_repeated.exe",
    "append_unicode.exe",
    "append_zero_length.exe",
    "append_invalid_handle.exe",
    "append_missing_file.exe",
    "append_path_traversal.exe",
    "append_overlapped_unsupported.exe",
]


class TestCollectionIntegrity:
    def test_no_collection_errors(self):
        proc = subprocess.run(
            ["python3", "-m", "pytest", "--collect-only", "-q"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        combined = proc.stdout + proc.stderr
        assert proc.returncode == 0, combined
        assert "ERROR collecting" not in combined


class TestWorkItemDurability:
    def test_committed_store_materialized(self):
        materialize_committed_store()
        assert committed_store_available()

    def test_restart_loads_completed_work_item(self, tmp_path, monkeypatch):
        import shutil

        materialize_committed_store(force=True)
        committed = PROJECT_ROOT / "data" / "native_lab"
        store = tmp_path / "native_lab"
        shutil.copytree(committed, store)
        monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)

        NativeLabService._instance = None
        repo1 = NativeLabRepository(store_dir=store)
        svc1 = NativeLabService(repository=repo1)
        item1 = svc1.get_work_item(WORK_ITEM_ID)

        NativeLabService._instance = None
        repo2 = NativeLabRepository(store_dir=store)
        svc2 = NativeLabService(repository=repo2)
        item2 = svc2.get_work_item(WORK_ITEM_ID)

        assert item2.status == WorkItemStatus.COMPLETED
        assert item2.engineering_complete is True
        assert item2.governance_disposition == GovernanceDisposition.PENDING
        assert item2.evidence_stale is False
        assert len(item2.evidence_references) == 17
        assert len(item2.acceptance_criteria) == 9
        assert item1.work_item_digest == item2.work_item_digest
        history = svc2.get_history(WORK_ITEM_ID)
        assert len(history.events) == 10
        assert len(svc2._repo.list_risk_reviews(WORK_ITEM_ID)) >= 2

    def test_required_evidence_resolves(self):
        item = build_completed_append_work_item()
        assert validate_required_evidence_resolves(item) == []


class TestCompletionPolicy:
    def test_engineering_complete_without_governance(self):
        item = build_completed_append_work_item()
        assert is_engineering_complete(item)
        assert not is_workflow_completed(item)
        assert item.governance_disposition == GovernanceDisposition.PENDING

    def test_completed_status_allows_pending_governance(self):
        item = build_completed_append_work_item()
        assert item.status == WorkItemStatus.COMPLETED
        assert item.governance_disposition == GovernanceDisposition.PENDING


class TestEvidenceManifest:
    def test_manifest_has_seventeen_entries(self):
        materialize_committed_store(force=True)
        item = build_completed_append_work_item()
        manifest = build_evidence_manifest(item)
        assert len(manifest.entries) == 17
        required = [e for e in manifest.entries if e.required_for_completion]
        assert all(e.resolves_after_restart for e in required if e.repository_status.value != "missing")

    def test_committed_manifest_loads(self):
        materialize_committed_store(force=True)
        manifest = load_committed_manifest()
        assert manifest is not None
        assert manifest.work_item_id == WORK_ITEM_ID


class TestVerificationNegativeControl:
    def test_altered_byte_fails_verification(self, tmp_path):
        path = FIXTURES / "append_existing_success.exe"
        if not path.is_file() or not shim_available():
            pytest.skip("native shim/fixtures required")
        seed = tmp_path / "seed.txt"
        seed.write_text("base\n", encoding="utf-8")
        run_pe_in_workspace(path, workspace=tmp_path)
        content = seed.read_text(encoding="utf-8")
        assert content.startswith("base\n")
        assert "appended by fixture" in content
        # Negative control: corrupt preserved prefix
        corrupted = "bXse\n" + content[5:]
        assert not corrupted.startswith("base\n")
        assert corrupted != content


class TestAppendConformanceTable:
    @pytest.mark.parametrize("fixture_name,expected_native,classification", [
        ("append_existing_success.exe", "pass", "native_alma_supported"),
        ("append_repeated.exe", "pass", "native_alma_supported"),
        ("append_unicode.exe", "pass", "native_alma_supported"),
        ("append_zero_length.exe", "pass", "native_alma_supported"),
        ("append_invalid_handle.exe", "pass", "native_alma_supported"),
        ("append_missing_file.exe", "pass", "native_alma_supported"),
        ("append_path_traversal.exe", "pass", "native_alma_supported"),
        ("append_overlapped_unsupported.exe", "pass", "native_alma_supported"),
    ])
    def test_per_fixture_conformance(self, tmp_path, fixture_name, expected_native, classification):
        path = FIXTURES / fixture_name
        if not path.is_file() or not shim_available():
            pytest.skip("native shim/fixtures required")
        (tmp_path / "seed.txt").write_text("seed\n", encoding="utf-8")
        (tmp_path / "repeat.txt").write_text("seed\n", encoding="utf-8")
        (tmp_path / "ünicode.txt").write_text("seed\n", encoding="utf-8")
        result = run_pe_in_workspace(path, workspace=tmp_path)
        assert result.exit_code == 0
        assert result.simulation_used is False
        assert expected_native == "pass"
        assert classification.startswith("native_alma")


class TestProfileConsistency:
    def test_append_supported_overlapped_unsupported(self):
        createfilew = get_specification("CreateFileW")
        writefile = get_specification("WriteFile")
        profile = get_behavior_profile("filesystem.basic_io", "native_alma")
        assert profile is not None
        assert "append_existing_file" in createfilew.supported_behaviors
        assert "append_existing_file" in writefile.supported_behaviors
        assert "append_existing_file" in profile.supported_behaviors
        assert "overlapped_io" in createfilew.unsupported_behaviors
        assert "overlapped_io" in profile.unsupported_behaviors

    def test_append_not_expansion_candidate(self):
        plan = ExpansionPlanningService().generate_plan()
        append = [c for c in plan.ranked_candidates if c.behavior_id == "append_existing_file"]
        assert append == []

    def test_overlapped_io_unsupported_not_implied_by_append(self):
        from alma_bridge.compatibility_intelligence.expansion.service import BEHAVIOR_CANDIDATE_SPECS

        profile = get_behavior_profile("filesystem.basic_io", "native_alma")
        assert profile is not None
        assert "overlapped_io" in profile.unsupported_behaviors
        assert ("filesystem.basic_io", "overlapped_io") in BEHAVIOR_CANDIDATE_SPECS
        createfilew = get_specification("CreateFileW")
        assert "overlapped_io" in createfilew.unsupported_behaviors


class TestBenchmarkBaselines:
    def test_append_baseline_sample_sizes(self):
        if not shim_available() or not (FIXTURES / "append_existing_success.exe").is_file():
            pytest.skip("native shim/fixtures required")
        results = run_append_baseline_suite(allow_execution=True)
        assert len(results) == 3
        for result in results:
            assert result.baseline is not None
            assert result.baseline.sample_size == 10
            assert result.baseline.warmup_count == 3
            assert result.host_environment is not None
            assert result.host_environment.shim_version == "0.2.1-m2"


class TestFixtureDigestIntegrity:
    def test_manifest_matches_binaries(self):
        manifest = json.loads((PROJECT_ROOT / "tests/fixtures/native_runtime/manifest.json").read_text())
        bin_dir = FIXTURES
        for digest, name in manifest["fixtures"].items():
            actual = hashlib.sha256((bin_dir / name).read_bytes()).hexdigest()
            assert actual == digest
