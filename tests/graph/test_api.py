"""Compatibility Graph read-only API tests."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alma_bridge.graph.models import GraphEdgeType
from alma_bridge.main import create_app
from tests.graph.conftest import CODEBLOCKS_FINGERPRINT, CODEBLOCKS_SESSION_ID, seed_codeblocks_session

pytestmark = pytest.mark.usefixtures("isolated_graph_store")


def test_graph_session_endpoint_returns_subgraph():
    seed_codeblocks_session()
    client = TestClient(create_app())
    response = client.get(f"/bridge/graph/sessions/{CODEBLOCKS_SESSION_ID}")
    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == CODEBLOCKS_SESSION_ID
    assert body["nodes"]
    assert body["edges"]
    assert any(edge["edge_type"] == GraphEdgeType.VERIFIED_BY.value for edge in body["edges"])


def test_graph_application_endpoint_returns_subgraph():
    seed_codeblocks_session()
    client = TestClient(create_app())
    response = client.get(f"/bridge/graph/applications/{CODEBLOCKS_FINGERPRINT}")
    assert response.status_code == 200
    body = response.json()
    assert body["application_fingerprint"] == CODEBLOCKS_FINGERPRINT
    assert body["nodes"]


def test_graph_node_and_edge_lookup():
    seed_codeblocks_session()
    client = TestClient(create_app())
    graph = client.get(f"/bridge/graph/sessions/{CODEBLOCKS_SESSION_ID}").json()
    node_id = graph["nodes"][0]["node_id"]
    edge_id = graph["edges"][0]["edge_id"]
    assert client.get(f"/bridge/graph/nodes/{node_id}").status_code == 200
    assert client.get(f"/bridge/graph/edges/{edge_id}").status_code == 200


def test_graph_missing_session_returns_404():
    client = TestClient(create_app())
    response = client.get("/bridge/graph/sessions/missing-session")
    assert response.status_code == 404
