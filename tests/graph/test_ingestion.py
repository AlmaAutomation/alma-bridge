"""Graph ingestion behavior and provenance boundary tests."""

from __future__ import annotations

from dataclasses import replace

import pytest

from alma_bridge.compatibility.profile_fingerprints import build_bridge_manifest_hash
from alma_bridge.compatibility.profile_store import persist_candidate_snapshot
from alma_bridge.graph.models import (
    GraphEdge,
    GraphEdgeType,
    GraphNodeType,
    MalformedGraphEvidenceError,
)
from alma_bridge.graph.service import CompatibilityGraphService
from alma_bridge.storage import outcomes
from tests.graph.conftest import (
    CODEBLOCKS_FINGERPRINT,
    CODEBLOCKS_SESSION_ID,
    seed_codeblocks_session,
)
from tests.intelligence.conftest import sample_wine_gui_verification
from tests.profile_test_helpers import build_test_snapshot

pytestmark = pytest.mark.usefixtures("isolated_graph_store")


def _service() -> CompatibilityGraphService:
    return CompatibilityGraphService()


def test_ingestion_is_idempotent():
    seed_codeblocks_session()
    service = _service()
    first = service.graph_for_session(CODEBLOCKS_SESSION_ID)
    second = service.graph_for_session(CODEBLOCKS_SESSION_ID)
    assert {node.node_id for node in first.nodes} == {node.node_id for node in second.nodes}
    assert {edge.edge_id for edge in first.edges} == {edge.edge_id for edge in second.edges}


def test_same_evidence_produces_stable_node_and_edge_ids():
    seed_codeblocks_session()
    service = _service()
    first = service.graph_for_session(CODEBLOCKS_SESSION_ID)
    second = service.graph_for_session(CODEBLOCKS_SESSION_ID)
    assert first.nodes[0].node_id == second.nodes[0].node_id
    assert first.edges[0].edge_id == second.edges[0].edge_id


def test_every_edge_has_provenance():
    seed_codeblocks_session()
    graph = _service().graph_for_session(CODEBLOCKS_SESSION_ID)
    assert graph.edges
    for edge in graph.edges:
        assert edge.evidence_references
        assert all(ref.source_type and ref.source_id for ref in edge.evidence_references)


def test_edges_require_provenance_at_model_level():
    with pytest.raises(ValueError, match="graph edges require at least one provenance"):
        GraphEdge(
            edge_id="edge:test",
            source_node_id="a",
            target_node_id="b",
            edge_type=GraphEdgeType.SESSION_FOR_APPLICATION,
            scope="scope",
            evidence_references=[],
        )


def test_exit_code_success_cannot_create_verified_by():
    session_id = outcomes.new_session("/tmp/app.exe", "exit-only-hash", {})
    outcomes.record_attempt(
        session_id=session_id,
        attempt_number=1,
        strategy_id="wine_gui",
        remediation_id=None,
        runtime="wine",
        command=["wine", "/tmp/app.exe"],
        env={},
        mode="host_prefix",
        success=True,
        exit_code=0,
        error_signature=None,
        detected_error=None,
        stdout="",
        stderr="",
        duration_ms=100,
        phase="wine_gui",
        verification=None,
    )
    outcomes.finalize_session(session_id, success=True, summary="exit only")
    graph = _service().graph_for_session(session_id)
    assert not any(edge.edge_type == GraphEdgeType.VERIFIED_BY for edge in graph.edges)


def test_failed_verification_cannot_create_verified_by():
    session_id = outcomes.new_session("/tmp/app.exe", "failed-verify-hash", {})
    failed = sample_wine_gui_verification()
    failed["passed"] = False
    outcomes.record_attempt(
        session_id=session_id,
        attempt_number=1,
        strategy_id="wine_gui",
        remediation_id=None,
        runtime="wine",
        command=["wine", "/tmp/app.exe"],
        env={},
        mode="host_prefix",
        success=False,
        exit_code=1,
        error_signature=None,
        detected_error=None,
        stdout="",
        stderr="wxwidgets startup",
        duration_ms=100,
        phase="wine_gui",
        verification=failed,
    )
    outcomes.finalize_session(session_id, success=False, summary="verification failed")
    graph = _service().graph_for_session(session_id)
    assert not any(edge.edge_type == GraphEdgeType.VERIFIED_BY for edge in graph.edges)


def test_framework_observations_remain_scoped_to_evidence():
    seed_codeblocks_session()
    graph = _service().graph_for_session(CODEBLOCKS_SESSION_ID)
    framework_edges = [
        edge for edge in graph.edges if edge.edge_type == GraphEdgeType.DETECTED_FRAMEWORK
    ]
    assert framework_edges
    for edge in framework_edges:
        assert edge.scope == f"{CODEBLOCKS_SESSION_ID}:1"
        assert edge.evidence_references[0].source_type == "framework_detection"


def test_runtime_observed_not_runtime_required():
    seed_codeblocks_session()
    snapshot = build_test_snapshot(
        session_id=CODEBLOCKS_SESSION_ID,
        attempt_number=1,
        strategy_id="wine_gui",
        runtime="wine",
        file_path="/opt/CodeBlocks/codeblocks.exe",
        executable_hash=CODEBLOCKS_FINGERPRINT,
        verification_payload=sample_wine_gui_verification(),
        manifest_env={"WINEPREFIX": "/tmp/prefix"},
    )
    manifest = dict(snapshot.bridge_manifest)
    manifest["base_runtime"] = {"kind": "wine", "version_family": "9.x"}
    snapshot = replace(
        snapshot,
        bridge_manifest=manifest,
        bridge_manifest_hash=build_bridge_manifest_hash(manifest),
    )
    persist_candidate_snapshot(snapshot)

    graph = _service().graph_for_session(CODEBLOCKS_SESSION_ID)
    edge_types = {edge.edge_type.value for edge in graph.edges}
    assert GraphEdgeType.RUNTIME_OBSERVED.value in edge_types
    assert "runtime_required" not in edge_types


def test_conflicting_evidence_is_preserved():
    seed_codeblocks_session()
    session_id = CODEBLOCKS_SESSION_ID
    outcomes.record_attempt(
        session_id=session_id,
        attempt_number=2,
        strategy_id="wine_gui",
        remediation_id=None,
        runtime="wine",
        command=["wine", "/opt/CodeBlocks/codeblocks.exe"],
        env={},
        mode="host_prefix",
        success=False,
        exit_code=1,
        error_signature=None,
        detected_error=None,
        stdout="",
        stderr="generic failure",
        duration_ms=900,
        phase="wine_gui",
        verification={
            "passed": False,
            "confidence": 0.2,
            "success_policy": {
                "policy_id": "wine_gui_process_v1",
                "policy_version": "1.1.0",
                "required_checks": {"wine_gui": ["process_survives"]},
            },
            "checks": [],
            "evidence": ["framework=electron"],
        },
    )
    graph = _service().graph_for_session(session_id)
    framework_edges = [
        edge for edge in graph.edges if edge.edge_type == GraphEdgeType.DETECTED_FRAMEWORK
    ]
    scopes = {edge.scope for edge in framework_edges}
    assert f"{session_id}:1" in scopes
    assert f"{session_id}:2" in scopes
    assert len(framework_edges) >= 2


def test_codeblocks_application_subgraph_is_stable():
    seed_codeblocks_session()
    service = _service()
    session_graph = service.graph_for_session(CODEBLOCKS_SESSION_ID)
    app_graph = service.graph_for_application(CODEBLOCKS_FINGERPRINT)

    node_types = {node.node_type for node in session_graph.nodes}
    assert GraphNodeType.APPLICATION in node_types
    assert GraphNodeType.EXECUTION_SESSION in node_types
    assert GraphNodeType.LAUNCH_STRATEGY in node_types
    assert GraphNodeType.FRAMEWORK in node_types
    assert GraphNodeType.VERIFICATION_CONTRACT in node_types

    assert any(edge.edge_type == GraphEdgeType.VERIFIED_BY for edge in session_graph.edges)
    assert {node.node_id for node in session_graph.nodes}.issubset(
        {node.node_id for node in app_graph.nodes}
    )


def test_malformed_evidence_fails_closed():
    session_id = outcomes.new_session("/tmp/app.exe", "", {})
    with pytest.raises(MalformedGraphEvidenceError):
        _service().graph_for_session(session_id)
