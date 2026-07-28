"""Stable deterministic ID helpers for graph nodes and edges."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.graph.models import (
    GRAPH_SCHEMA_VERSION,
    GraphEdgeType,
    GraphNodeType,
    GraphProvenance,
)


def build_node_id(*, node_type: GraphNodeType | str, identity_key: str) -> str:
    node_type_value = node_type.value if isinstance(node_type, GraphNodeType) else str(node_type)
    return sha256_v1(
        {
            "schema": GRAPH_SCHEMA_VERSION,
            "node_type": node_type_value,
            "identity_key": identity_key,
        }
    )


def build_edge_id(
    *,
    edge_type: GraphEdgeType | str,
    source_node_id: str,
    target_node_id: str,
    scope: str,
    evidence_fingerprint: str,
) -> str:
    edge_type_value = edge_type.value if isinstance(edge_type, GraphEdgeType) else str(edge_type)
    return sha256_v1(
        {
            "schema": GRAPH_SCHEMA_VERSION,
            "edge_type": edge_type_value,
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "scope": scope,
            "evidence_fingerprint": evidence_fingerprint,
        }
    )


def provenance_fingerprint(provenance: List[GraphProvenance]) -> str:
    payload = [
        {
            "source_type": ref.source_type,
            "source_id": ref.source_id,
            "session_id": ref.session_id,
            "attempt_id": ref.attempt_id,
        }
        for ref in sorted(
            provenance,
            key=lambda item: (
                item.source_type,
                item.source_id,
                item.session_id or "",
                item.attempt_id or -1,
            ),
        )
    ]
    return sha256_v1({"provenance": payload})


def manifest_runtime_identity(manifest: Mapping[str, Any]) -> str:
    base_runtime = manifest.get("base_runtime") or {}
    return sha256_v1(
        {
            "kind": str(base_runtime.get("kind") or "unknown"),
            "version_family": str(base_runtime.get("version_family") or "unknown"),
        }
    )


def environment_identity(environment: Mapping[str, Any]) -> str:
    return sha256_v1(
        {
            "schema": str(environment.get("schema_version") or "compatibility_run_environment_v1"),
            "payload": dict(sorted(environment.items())),
        }
    )
