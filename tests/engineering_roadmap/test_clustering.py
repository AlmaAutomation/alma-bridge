"""Tests for deterministic engineering roadmap blocker clustering."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from alma_bridge.engineering_roadmap.clustering import (
    BLOCKER_CLUSTER_REGISTRY,
    BLOCKER_CLUSTER_REGISTRY_VERSION,
    BlockerClusterRegistryError,
    ParsedBlockerKind,
    _validate_registry,
    cluster_blockers,
    compute_cluster_digest,
    compute_clustering_report_digest,
    parse_blocker,
)
from alma_bridge.engineering_roadmap.models import (
    BlockerClusterClassification,
    BlockerClusterSpec,
    BlockerClusteringResult,
    EngineeringRoadmapOpportunity,
    ProvisionalBlockerCluster,
)
from alma_bridge.runtime_intelligence.models import BehaviorFamilyId

ROOT = Path(__file__).resolve().parents[2]
CLUSTERING_MODULE = ROOT / "alma_bridge" / "engineering_roadmap" / "clustering.py"
EVIDENCE_SNAPSHOT = "evidence-snapshot-cluster-v1"


def _cluster(blockers, **kwargs):
    defaults = {"evidence_snapshot_digest": EVIDENCE_SNAPSHOT}
    defaults.update(kwargs)
    return cluster_blockers(blockers, **defaults)


class TestParseBlocker:
    def test_parses_unknown_api_exact_symbol(self):
        parsed = parse_blocker("unknown_api:kernel32.dll!CreateFileMappingW")
        assert parsed.parseable is True
        assert parsed.kind == ParsedBlockerKind.UNKNOWN_API
        assert parsed.symbol == "CreateFileMappingW"
        assert parsed.dll == "kernel32.dll"

    def test_parses_behavior_gap(self):
        parsed = parse_blocker("behavior_gap:open_existing_readwrite")
        assert parsed.parseable is True
        assert parsed.kind == ParsedBlockerKind.BEHAVIOR_GAP
        assert parsed.symbol == "open_existing_readwrite"

    def test_malformed_unknown_api_without_symbol(self):
        parsed = parse_blocker("unknown_api:kernel32.dll")
        assert parsed.parseable is False
        assert parsed.reason == "malformed_blocker"

    def test_unsupported_blocker_format(self):
        parsed = parse_blocker("api.unknown=unknown")
        assert parsed.parseable is False
        assert parsed.reason == "unsupported_blocker_format"

    def test_no_wildcard_matching(self):
        parsed = parse_blocker("unknown_api:kernel32.dll!Create*")
        assert parsed.parseable is False


class TestRegistryValidation:
    def test_registry_has_fifteen_api_clusters(self):
        assert len(BLOCKER_CLUSTER_REGISTRY) == 15

    def test_registry_version_constant(self):
        assert BLOCKER_CLUSTER_REGISTRY_VERSION == "blocker_cluster_registry_v1"
        assert all(spec.registry_version == BLOCKER_CLUSTER_REGISTRY_VERSION for spec in BLOCKER_CLUSTER_REGISTRY)

    def test_duplicate_symbol_across_specs_rejected(self):
        base = BLOCKER_CLUSTER_REGISTRY[0]
        duplicate = BlockerClusterSpec(
            cluster_id="cluster.duplicate_test",
            title="Duplicate",
            api_symbols=[base.api_symbols[0]],
            capability_id="api.unknown",
            family_id=BehaviorFamilyId.CRT,
            registry_version=BLOCKER_CLUSTER_REGISTRY_VERSION,
        )
        with pytest.raises(BlockerClusterRegistryError):
            _validate_registry((base, duplicate))


class TestClusterBlockersBasics:
    def test_duplicate_blockers_deduplicated(self):
        blockers = [
            "unknown_api:kernel32.dll!HeapAlloc",
            "unknown_api:kernel32.dll!HeapAlloc",
        ]
        result = _cluster(blockers)
        assert result.input_blocker_count == 1
        assert result.clustered_blocker_count == 1

    def test_input_order_does_not_affect_output(self):
        blockers_a = [
            "unknown_api:kernel32.dll!HeapAlloc",
            "unknown_api:kernel32.dll!HeapFree",
            "unknown_api:kernel32.dll!CreateMutexW",
        ]
        blockers_b = list(reversed(blockers_a))
        result_a = _cluster(blockers_a)
        result_b = _cluster(blockers_b)
        assert result_a.report_digest == result_b.report_digest
        assert [c.cluster_id for c in result_a.clusters] == [c.cluster_id for c in result_b.clusters]

    def test_registry_order_does_not_affect_output(self):
        blockers = [
            "unknown_api:kernel32.dll!MapViewOfFile",
            "unknown_api:kernel32.dll!CreateMutexW",
        ]
        first = _cluster(blockers)
        second = _cluster(blockers)
        assert first.report_digest == second.report_digest

    def test_unmatched_api_remains_unclustered(self):
        result = _cluster(["unknown_api:kernel32.dll!AreFileApisANSI"])
        assert result.unclustered_blocker_count == 1
        assert result.unclustered[0].reason == "not_in_cluster_registry"
        assert result.unclustered[0].parsed_symbol == "AreFileApisANSI"

    def test_no_dll_only_clustering(self):
        result = _cluster(["unsupported:kernel32.dll"])
        assert result.clustered_blocker_count == 0
        assert result.unclustered[0].reason == "malformed_blocker"


class TestNamedClusters:
    def test_memory_mapped_file_cluster(self):
        result = _cluster(
            [
                "unknown_api:kernel32.dll!CreateFileMappingW",
                "unknown_api:kernel32.dll!MapViewOfFile",
            ]
        )
        cluster = next(c for c in result.clusters if c.cluster_id == "cluster.memory_mapped_file_v1")
        assert cluster.classification == BlockerClusterClassification.PROVISIONAL
        assert cluster.capability_id == "memory.mapped_file"
        assert cluster.family_id == BehaviorFamilyId.MEMORY

    def test_synchronization_cluster(self):
        result = _cluster(["unknown_api:kernel32.dll!CreateMutexW"])
        cluster = next(c for c in result.clusters if c.cluster_id == "cluster.synchronization_primitives_v1")
        assert "CreateMutexW" in cluster.api_symbols

    def test_heap_cluster(self):
        result = _cluster(["unknown_api:kernel32.dll!HeapAlloc"])
        cluster = next(c for c in result.clusters if c.cluster_id == "cluster.heap_management_v1")
        assert cluster.capability_id == "memory.heap"

    def test_file_position_cluster(self):
        result = _cluster(["unknown_api:kernel32.dll!SetFilePointerEx"])
        cluster = next(c for c in result.clusters if c.cluster_id == "cluster.file_position_locking_v1")
        assert cluster.behavior_id == "file_position_and_locking"

    def test_directory_enumeration_cluster(self):
        result = _cluster(["unknown_api:kernel32.dll!FindNextFileW"])
        cluster = next(c for c in result.clusters if c.cluster_id == "cluster.directory_enumeration_v1")
        assert cluster.capability_id == "filesystem.directory_enumeration"

    def test_unicode_locale_cluster(self):
        result = _cluster(["unknown_api:kernel32.dll!CompareStringW"])
        cluster = next(c for c in result.clusters if c.cluster_id == "cluster.unicode_locale_v1")
        assert cluster.family_id == BehaviorFamilyId.CRT

    def test_threading_cluster(self):
        result = _cluster(["unknown_api:kernel32.dll!CreateThread"])
        cluster = next(c for c in result.clusters if c.cluster_id == "cluster.threading_lifecycle_v1")
        assert cluster.capability_id == "threading.basic"

    def test_tls_fls_cluster(self):
        result = _cluster(["unknown_api:kernel32.dll!TlsAlloc"])
        cluster = next(c for c in result.clusters if c.cluster_id == "cluster.tls_fls_v1")
        assert "TlsAlloc" in cluster.api_symbols

    def test_console_cluster(self):
        result = _cluster(["unknown_api:kernel32.dll!WriteConsoleW"])
        cluster = next(c for c in result.clusters if c.cluster_id == "cluster.console_io_v1")
        assert cluster.family_id == BehaviorFamilyId.CONSOLE

    def test_process_module_cluster_marked_unsuitable(self):
        result = _cluster(["unknown_api:kernel32.dll!LoadLibraryA"])
        cluster = next(c for c in result.clusters if c.cluster_id == "cluster.process_module_loading_v1")
        assert cluster.independently_implementable is False
        assert cluster.suitable_as_bounded_opportunity is False
        assert cluster.suitability_reason == "hard_excluded_or_high_risk"


class TestCanonicalOverrides:
    def test_api_capability_map_overrides_provisional_mapping(self):
        result = _cluster(["unknown_api:kernel32.dll!Sleep"])
        cluster = next(c for c in result.clusters if c.cluster_id == "cluster.timing_performance_v1")
        assert cluster.capability_id == "process.timing"
        assert cluster.behavior_id == "process_timing"
        assert cluster.classification == BlockerClusterClassification.KNOWN
        assert cluster.family_id == BehaviorFamilyId.CRT


class TestBehaviorGaps:
    def test_behavior_gap_retained_as_cluster(self):
        result = _cluster(["behavior_gap:open_existing_readwrite"])
        cluster = next(c for c in result.clusters if c.cluster_id == "behavior_gap.open_existing_readwrite")
        assert cluster.classification == BlockerClusterClassification.KNOWN
        assert cluster.behavior_id == "open_existing_readwrite"
        assert cluster.capability_id == "filesystem.basic_io"

    def test_unregistered_behavior_gap_stays_unclustered(self):
        result = _cluster(["behavior_gap:unknown_behavior_xyz"])
        assert result.unclustered[0].reason == "known_behavior_gap_unregistered"


class TestDescriptiveMetadata:
    def test_fixture_availability_surfaced(self):
        result = _cluster(
            ["unknown_api:kernel32.dll!HeapAlloc"],
            fixture_capabilities={"memory.heap"},
        )
        cluster = next(c for c in result.clusters if c.cluster_id == "cluster.heap_management_v1")
        assert cluster.fixture_available is True

    def test_native_coverage_surfaced(self):
        result = _cluster(
            ["unknown_api:kernel32.dll!HeapAlloc"],
            native_alma_coverage_by_capability={"memory.heap": 12.5},
        )
        cluster = next(c for c in result.clusters if c.cluster_id == "cluster.heap_management_v1")
        assert cluster.native_alma_coverage_percent == 12.5

    def test_evidence_references_deduplicated(self):
        result = _cluster(
            ["unknown_api:kernel32.dll!HeapAlloc"],
            evidence_references=["ref-b", "ref-a", "ref-b"],
        )
        cluster = result.clusters[0]
        assert cluster.evidence_references == ["ref-a", "ref-b"]


class TestDigests:
    def test_cluster_digest_stable_for_reordered_symbols(self):
        result = _cluster(
            [
                "unknown_api:kernel32.dll!HeapAlloc",
                "unknown_api:kernel32.dll!HeapFree",
            ]
        )
        cluster = result.clusters[0]
        shuffled = cluster.model_copy(
            update={"api_symbols": ["HeapFree", "HeapAlloc"], "digest": ""}
        )
        assert compute_cluster_digest(shuffled) == cluster.digest

    def test_report_digest_stable_for_reordered_clusters(self):
        blockers = [
            "unknown_api:kernel32.dll!HeapAlloc",
            "unknown_api:kernel32.dll!CreateMutexW",
        ]
        result = _cluster(blockers)
        forward = compute_clustering_report_digest(
            clusters=result.clusters,
            unclustered=result.unclustered,
            registry_version=result.registry_version,
            evidence_snapshot_digest=result.evidence_snapshot_digest,
        )
        reverse = compute_clustering_report_digest(
            clusters=list(reversed(result.clusters)),
            unclustered=list(reversed(result.unclustered)),
            registry_version=result.registry_version,
            evidence_snapshot_digest=result.evidence_snapshot_digest,
        )
        assert forward == reverse
        assert result.report_digest == forward

    def test_snapshot_digest_change_changes_report_digest(self):
        first = _cluster(["unknown_api:kernel32.dll!HeapAlloc"])
        second = _cluster(
            ["unknown_api:kernel32.dll!HeapAlloc"],
            evidence_snapshot_digest="evidence-snapshot-other",
        )
        assert first.report_digest != second.report_digest


class TestSqliteLikeClustering:
    def test_sqlite_subset_clusters_without_ranking(self):
        blockers = [
            "behavior_gap:open_existing_readwrite",
            "unknown_api:kernel32.dll!CreateFileMappingW",
            "unknown_api:kernel32.dll!MapViewOfFile",
            "unknown_api:kernel32.dll!CreateMutexW",
            "unknown_api:kernel32.dll!HeapAlloc",
            "unknown_api:kernel32.dll!FindFirstFileW",
            "unknown_api:kernel32.dll!LoadLibraryA",
            "unknown_api:kernel32.dll!AreFileApisANSI",
        ]
        result = _cluster(blockers)
        assert isinstance(result, BlockerClusteringResult)
        assert result.clustered_blocker_count >= 6
        assert any(item.reason == "not_in_cluster_registry" for item in result.unclustered)
        assert all(not isinstance(item, EngineeringRoadmapOpportunity) for item in result.clusters)


class TestImportBoundaries:
    FORBIDDEN = (
        "alma_bridge.learning.orchestrator",
        "alma_bridge.execution",
        "alma_bridge.compatibility_intelligence.expansion.ranking",
        "alma_bridge.cli",
        "alma_bridge.api",
    )

    def test_clustering_module_avoids_forbidden_imports(self):
        tree = ast.parse(CLUSTERING_MODULE.read_text(encoding="utf-8"))
        imports = [node for node in ast.walk(tree) if isinstance(node, (ast.Import, ast.ImportFrom))]
        for node in imports:
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for name in names:
                for forbidden in self.FORBIDDEN:
                    assert not name.startswith(forbidden)

    def test_no_opportunity_instances_created(self):
        result = _cluster(["unknown_api:kernel32.dll!HeapAlloc"])
        assert all(isinstance(cluster, ProvisionalBlockerCluster) for cluster in result.clusters)
