"""Read-only Compatibility Graph HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from alma_bridge.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNotFoundError,
    GraphSubgraph,
    MalformedGraphEvidenceError,
)
from alma_bridge.graph.service import CompatibilityGraphService

router = APIRouter()
_service = CompatibilityGraphService()


@router.get(
    "/bridge/graph/applications/{fingerprint}",
    response_model=GraphSubgraph,
    tags=["Graph"],
)
def graph_for_application(fingerprint: str) -> GraphSubgraph:
    try:
        return _service.graph_for_application(fingerprint)
    except GraphNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MalformedGraphEvidenceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.details},
        ) from exc


@router.get(
    "/bridge/graph/sessions/{session_id}",
    response_model=GraphSubgraph,
    tags=["Graph"],
)
def graph_for_session(session_id: str) -> GraphSubgraph:
    try:
        return _service.graph_for_session(session_id)
    except GraphNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MalformedGraphEvidenceError as exc:
        raise HTTPException(
            status_code=422,
            detail={"message": str(exc), "errors": exc.details},
        ) from exc


@router.get(
    "/bridge/graph/nodes/{node_id}",
    response_model=GraphNode,
    tags=["Graph"],
)
def graph_node(node_id: str) -> GraphNode:
    try:
        return _service.get_node(node_id)
    except GraphNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/bridge/graph/edges/{edge_id}",
    response_model=GraphEdge,
    tags=["Graph"],
)
def graph_edge(edge_id: str) -> GraphEdge:
    try:
        return _service.get_edge(edge_id)
    except GraphNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
