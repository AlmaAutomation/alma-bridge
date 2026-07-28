"""End-to-end: Bridge persisted session → recent listing → Compatibility Graph v1."""

from __future__ import annotations

from fastapi.testclient import TestClient

from alma_bridge.graph.models import GraphEdgeType, GraphNodeType
from alma_bridge.main import create_app
from alma_bridge.storage import outcomes
from tests.intelligence.conftest import (
    CODEBLOCKS_FINGERPRINT,
    CODEBLOCKS_SESSION_ID,
    seed_codeblocks_session,
)


def _client(tmp_path, monkeypatch) -> TestClient:
    db = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db)
    outcomes.init_outcome_store()
    return TestClient(create_app())


def test_codeblock_session_persists_required_evidence_fields(tmp_path, monkeypatch):
    _client(tmp_path, monkeypatch)
    seed_codeblocks_session()
    session = outcomes.get_session(CODEBLOCKS_SESSION_ID)
    assert session is not None
    assert session["session_id"] == CODEBLOCKS_SESSION_ID
    assert session["file_hash"] == CODEBLOCKS_FINGERPRINT
    assert session["file_path"] == "/opt/CodeBlocks/codeblocks.exe"
    assert session["attempts"]
    attempt = session["attempts"][0]
    assert attempt["strategy_id"] == "wine_gui"
    assert attempt.get("verification", {}).get("passed") is True
    assert "wxwidgets" in (attempt.get("stderr") or "").lower()


def test_bridge_recent_lists_codeblock_with_graph_metadata(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    seed_codeblocks_session()
    body = client.get("/bridge/sessions/recent", params={"limit": 5}).json()
    match = next(s for s in body["sessions"] if s["session_id"] == CODEBLOCKS_SESSION_ID)
    assert match["application_fingerprint"] == CODEBLOCKS_FINGERPRINT
    assert match["application_name"] == "codeblocks.exe"
    assert match["graph_compatible"] is True
    assert match["verified"] is True
    assert match["state"] in {"SUCCEEDED", "RUNNING"}


def test_bridge_to_graph_e2e_codeblock_workflow(tmp_path, monkeypatch):
    """Acceptance: persisted Bridge session ingests into Graph v1 with full provenance."""
    client = _client(tmp_path, monkeypatch)
    seed_codeblocks_session()

    recent = client.get("/bridge/sessions/recent").json()
    listed = next(s for s in recent["sessions"] if s["session_id"] == CODEBLOCKS_SESSION_ID)
    assert listed["graph_compatible"] is True
    assert listed["verified"] is True

    graph = client.get(f"/bridge/graph/sessions/{CODEBLOCKS_SESSION_ID}").json()
    assert graph["session_id"] == CODEBLOCKS_SESSION_ID
    assert graph["application_fingerprint"] == CODEBLOCKS_FINGERPRINT

    nodes_by_type = {node["node_type"] for node in graph["nodes"]}
    assert GraphNodeType.APPLICATION.value in nodes_by_type
    assert GraphNodeType.EXECUTION_SESSION.value in nodes_by_type
    assert GraphNodeType.LAUNCH_STRATEGY.value in nodes_by_type
    assert GraphNodeType.FRAMEWORK.value in nodes_by_type
    assert GraphNodeType.VERIFICATION_CONTRACT.value in nodes_by_type

    edges_by_type = {edge["edge_type"] for edge in graph["edges"]}
    assert GraphEdgeType.SESSION_FOR_APPLICATION.value in edges_by_type
    assert GraphEdgeType.LAUNCHED_VIA.value in edges_by_type
    assert GraphEdgeType.DETECTED_FRAMEWORK.value in edges_by_type
    assert GraphEdgeType.VERIFIED_BY.value in edges_by_type
    assert GraphEdgeType.PRODUCED_EVIDENCE.value in edges_by_type

    for edge in graph["edges"]:
        assert edge["evidence_references"], f"edge {edge['edge_id']} missing provenance"

    nodes_by_id = {node["node_id"]: node for node in graph["nodes"]}
    framework_edges = [
        edge for edge in graph["edges"] if edge["edge_type"] == GraphEdgeType.DETECTED_FRAMEWORK.value
    ]
    framework_names = {
        nodes_by_id[edge["target_node_id"]]["attributes"].get("framework")
        for edge in framework_edges
    }
    assert "wxwidgets" in framework_names

    launch_edges = [
        edge for edge in graph["edges"] if edge["edge_type"] == GraphEdgeType.LAUNCHED_VIA.value
    ]
    strategy_names = {
        nodes_by_id[edge["target_node_id"]]["attributes"].get("strategy_id")
        for edge in launch_edges
    }
    assert "wine_gui" in strategy_names

    verified_edges = [
        edge for edge in graph["edges"] if edge["edge_type"] == GraphEdgeType.VERIFIED_BY.value
    ]
    assert verified_edges
    contract_nodes = [nodes_by_id[edge["target_node_id"]] for edge in verified_edges]
    assert any(node["attributes"].get("policy_id") == "wine_gui_process_v1" for node in contract_nodes)

    app_node = next(
        node for node in graph["nodes"] if node["node_type"] == GraphNodeType.APPLICATION.value
    )
    assert app_node["identity_key"] == CODEBLOCKS_FINGERPRINT
    assert "codeblocks" in app_node["attributes"].get("file_path", "").lower()
