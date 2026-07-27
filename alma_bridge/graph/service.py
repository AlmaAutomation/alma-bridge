"""Compatibility Graph service facade — read-only query and idempotent ingestion."""

from __future__ import annotations

from alma_bridge.graph.ingestion import GraphIngestionEngine
from alma_bridge.graph.models import (
    GraphEdge,
    GraphNode,
    GraphNotFoundError,
    GraphSubgraph,
    MalformedGraphEvidenceError,
)
from alma_bridge.graph.repository import GraphStore, ReadOnlyGraphEvidenceAdapter
from alma_bridge.intelligence.models import IntelligenceNotFoundError


class CompatibilityGraphService:
    """Read-only graph queries backed by idempotent evidence ingestion."""

    def __init__(
        self,
        repository: ReadOnlyGraphEvidenceAdapter | None = None,
        store: GraphStore | None = None,
        ingestion: GraphIngestionEngine | None = None,
    ) -> None:
        self._repository = repository or ReadOnlyGraphEvidenceAdapter()
        self._store = store or GraphStore()
        self._ingestion = ingestion or GraphIngestionEngine(self._repository, self._store)

    def graph_for_session(self, session_id: str) -> GraphSubgraph:
        try:
            return self._ingestion.ingest_session(session_id)
        except IntelligenceNotFoundError as exc:
            raise GraphNotFoundError(str(exc)) from exc
        except MalformedGraphEvidenceError:
            raise

    def graph_for_application(self, fingerprint: str) -> GraphSubgraph:
        try:
            return self._ingestion.ingest_application(fingerprint)
        except IntelligenceNotFoundError as exc:
            raise GraphNotFoundError(str(exc)) from exc
        except MalformedGraphEvidenceError:
            raise

    def get_node(self, node_id: str) -> GraphNode:
        node = self._store.get_node(node_id)
        if not node:
            raise GraphNotFoundError(f"graph node not found: {node_id}")
        return node

    def get_edge(self, edge_id: str) -> GraphEdge:
        edge = self._store.get_edge(edge_id)
        if not edge:
            raise GraphNotFoundError(f"graph edge not found: {edge_id}")
        return edge
