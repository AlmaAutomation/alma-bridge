"""Graph persistence and read-only evidence repository adapters."""

from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from alma_bridge.config import settings
from alma_bridge.graph.models import GraphEdge, GraphNode, GraphProvenance
from alma_bridge.intelligence.repository import OutcomesStoreAdapter


@runtime_checkable
class GraphEvidenceRepository(Protocol):
    def get_session_record(self, session_id: str) -> Optional[Dict[str, Any]]: ...

    def list_sessions_for_fingerprint(self, fingerprint: str) -> List[Dict[str, Any]]: ...

    def get_profile_candidate_for_attempt(
        self,
        session_id: str,
        attempt_number: int,
    ) -> Optional[Any]: ...


class GraphStore:
    """Append-only graph node/edge store — never mutates execution tables."""

    def __init__(self, db_path: Optional[str] = None) -> None:
        self._db_path = db_path or str(settings.db_path)

    def _connect(self) -> sqlite3.Connection:
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def ensure_tables(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS compatibility_graph_nodes (
                    node_id TEXT PRIMARY KEY,
                    node_type TEXT NOT NULL,
                    identity_key TEXT NOT NULL,
                    attributes_json TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_graph_nodes_type_identity
                    ON compatibility_graph_nodes(node_type, identity_key);

                CREATE TABLE IF NOT EXISTS compatibility_graph_edges (
                    edge_id TEXT PRIMARY KEY,
                    source_node_id TEXT NOT NULL,
                    target_node_id TEXT NOT NULL,
                    edge_type TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    evidence_references_json TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_graph_edges_source
                    ON compatibility_graph_edges(source_node_id);
                CREATE INDEX IF NOT EXISTS idx_graph_edges_target
                    ON compatibility_graph_edges(target_node_id);
                CREATE INDEX IF NOT EXISTS idx_graph_edges_type_scope
                    ON compatibility_graph_edges(edge_type, scope);
                """
            )
            conn.commit()

    def upsert_node(self, node: GraphNode) -> bool:
        """Insert node if absent. Returns True when inserted, False when preserved."""
        self.ensure_tables()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO compatibility_graph_nodes (
                    node_id, node_type, identity_key, attributes_json,
                    schema_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    node.node_id,
                    node.node_type.value,
                    node.identity_key,
                    json.dumps(node.attributes, sort_keys=True),
                    node.schema_version,
                    node.created_at,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def upsert_edge(self, edge: GraphEdge) -> bool:
        """Insert edge if absent. Conflicting evidence is preserved as distinct edges."""
        self.ensure_tables()
        with self._connect() as conn:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO compatibility_graph_edges (
                    edge_id, source_node_id, target_node_id, edge_type, scope,
                    confidence, evidence_references_json, schema_version, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    edge.edge_id,
                    edge.source_node_id,
                    edge.target_node_id,
                    edge.edge_type.value,
                    edge.scope,
                    edge.confidence,
                    json.dumps(
                        [ref.model_dump() for ref in edge.evidence_references],
                        sort_keys=True,
                    ),
                    edge.schema_version,
                    edge.created_at,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_node(self, node_id: str) -> Optional[GraphNode]:
        self.ensure_tables()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM compatibility_graph_nodes WHERE node_id = ?",
                (node_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_node(row)

    def get_edge(self, edge_id: str) -> Optional[GraphEdge]:
        self.ensure_tables()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM compatibility_graph_edges WHERE edge_id = ?",
                (edge_id,),
            ).fetchone()
        if not row:
            return None
        return self._row_to_edge(row)

    def list_nodes_for_sessions(self, session_ids: List[str]) -> List[GraphNode]:
        if not session_ids:
            return []
        self.ensure_tables()
        placeholders = ",".join("?" for _ in session_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT DISTINCT n.*
                FROM compatibility_graph_nodes n
                JOIN compatibility_graph_edges e
                  ON n.node_id = e.source_node_id OR n.node_id = e.target_node_id
                JOIN compatibility_graph_nodes session_node
                  ON session_node.node_type = 'execution_session'
                 AND session_node.identity_key IN ({placeholders})
                 AND (
                    e.source_node_id = session_node.node_id
                    OR e.target_node_id = session_node.node_id
                    OR n.node_id = session_node.node_id
                 )
                """,
                session_ids,
            ).fetchall()
        return [self._row_to_node(row) for row in rows]

    def list_edges_for_sessions(self, session_ids: List[str]) -> List[GraphEdge]:
        if not session_ids:
            return []
        self.ensure_tables()
        session_nodes = [
            f"session:{session_id}" for session_id in session_ids
        ]
        placeholders = ",".join("?" for _ in session_ids)
        with self._connect() as conn:
            session_node_rows = conn.execute(
                f"""
                SELECT node_id FROM compatibility_graph_nodes
                WHERE node_type = 'execution_session'
                  AND identity_key IN ({placeholders})
                """,
                session_ids,
            ).fetchall()
        session_node_ids = {str(row["node_id"]) for row in session_node_rows}
        if not session_node_ids:
            return []

        app_placeholders = ",".join("?" for _ in session_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT e.*
                FROM compatibility_graph_edges e
                WHERE e.scope IN ({app_placeholders})
                   OR e.source_node_id IN ({",".join("?" for _ in session_node_ids)})
                   OR e.target_node_id IN ({",".join("?" for _ in session_node_ids)})
                """,
                [*session_ids, *session_node_ids, *session_node_ids],
            ).fetchall()
        del session_nodes
        return [self._row_to_edge(row) for row in rows]

    def list_nodes_for_fingerprint(self, fingerprint: str) -> List[GraphNode]:
        self.ensure_tables()
        with self._connect() as conn:
            app_row = conn.execute(
                """
                SELECT node_id FROM compatibility_graph_nodes
                WHERE node_type = 'application' AND identity_key = ?
                """,
                (fingerprint,),
            ).fetchone()
        if not app_row:
            return []
        app_node_id = str(app_row["node_id"])
        with self._connect() as conn:
            edge_rows = conn.execute(
                """
                SELECT source_node_id, target_node_id
                FROM compatibility_graph_edges
                WHERE source_node_id = ? OR target_node_id = ?
                """,
                (app_node_id, app_node_id),
            ).fetchall()
        node_ids = {app_node_id}
        for row in edge_rows:
            node_ids.add(str(row["source_node_id"]))
            node_ids.add(str(row["target_node_id"]))
        placeholders = ",".join("?" for _ in node_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM compatibility_graph_nodes WHERE node_id IN ({placeholders})",
                list(node_ids),
            ).fetchall()
        return [self._row_to_node(row) for row in rows]

    def list_edges_for_fingerprint(self, fingerprint: str) -> List[GraphEdge]:
        nodes = self.list_nodes_for_fingerprint(fingerprint)
        if not nodes:
            return []
        node_ids = {node.node_id for node in nodes}
        placeholders = ",".join("?" for _ in node_ids)
        with self._connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM compatibility_graph_edges
                WHERE source_node_id IN ({placeholders})
                   OR target_node_id IN ({placeholders})
                """,
                [*node_ids, *node_ids],
            ).fetchall()
        return [self._row_to_edge(row) for row in rows]

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> GraphNode:
        return GraphNode(
            node_id=str(row["node_id"]),
            node_type=row["node_type"],
            identity_key=str(row["identity_key"]),
            attributes=json.loads(row["attributes_json"] or "{}"),
            schema_version=str(row["schema_version"]),
            created_at=str(row["created_at"]),
        )

    @staticmethod
    def _row_to_edge(row: sqlite3.Row) -> GraphEdge:
        refs_raw = json.loads(row["evidence_references_json"] or "[]")
        return GraphEdge(
            edge_id=str(row["edge_id"]),
            source_node_id=str(row["source_node_id"]),
            target_node_id=str(row["target_node_id"]),
            edge_type=row["edge_type"],
            scope=str(row["scope"]),
            confidence=float(row["confidence"]),
            evidence_references=[GraphProvenance(**item) for item in refs_raw],
            schema_version=str(row["schema_version"]),
            created_at=str(row["created_at"]),
        )


class ReadOnlyGraphEvidenceAdapter(OutcomesStoreAdapter):
    """Read-only adapter for graph ingestion evidence reads."""
