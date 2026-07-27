"""Domain models for the Compatibility Graph knowledge layer."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


GRAPH_SCHEMA_VERSION = "compatibility_graph_v1"
INGESTION_ENGINE_VERSION = "compatibility_graph_ingestion_v1"


class GraphNodeType(str, Enum):
    APPLICATION = "application"
    FRAMEWORK = "framework"
    RUNTIME = "runtime"
    LAUNCH_STRATEGY = "launch_strategy"
    VERIFICATION_CONTRACT = "verification_contract"
    PREFIX_MANIFEST = "prefix_manifest"
    EXECUTION_SESSION = "execution_session"
    EVIDENCE_RECORD = "evidence_record"


class GraphEdgeType(str, Enum):
    SESSION_FOR_APPLICATION = "session_for_application"
    DETECTED_FRAMEWORK = "detected_framework"
    LAUNCHED_VIA = "launched_via"
    VERIFIED_BY = "verified_by"
    USED_PREFIX_MANIFEST = "used_prefix_manifest"
    PRODUCED_EVIDENCE = "produced_evidence"
    RUNTIME_OBSERVED = "runtime_observed"


VALID_NODE_TYPES = frozenset(item.value for item in GraphNodeType)
VALID_EDGE_TYPES = frozenset(item.value for item in GraphEdgeType)


class GraphProvenance(BaseModel):
    source_type: str
    source_id: str
    session_id: Optional[str] = None
    attempt_id: Optional[int] = None
    captured_at: Optional[str] = None
    engine_version: str = INGESTION_ENGINE_VERSION


class GraphNode(BaseModel):
    node_id: str
    node_type: GraphNodeType
    identity_key: str
    attributes: Dict[str, Any] = Field(default_factory=dict)
    schema_version: str = GRAPH_SCHEMA_VERSION
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator("node_type", mode="before")
    @classmethod
    def _validate_node_type(cls, value: object) -> object:
        if isinstance(value, str) and value not in VALID_NODE_TYPES:
            raise ValueError(f"invalid graph node_type: {value}")
        return value


class GraphEdge(BaseModel):
    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: GraphEdgeType
    scope: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.0)
    evidence_references: List[GraphProvenance] = Field(default_factory=list)
    schema_version: str = GRAPH_SCHEMA_VERSION
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator("edge_type", mode="before")
    @classmethod
    def _validate_edge_type(cls, value: object) -> object:
        if isinstance(value, str) and value not in VALID_EDGE_TYPES:
            raise ValueError(f"invalid graph edge_type: {value}")
        return value

    @field_validator("evidence_references")
    @classmethod
    def _require_provenance(
        cls,
        value: List[GraphProvenance],
    ) -> List[GraphProvenance]:
        if not value:
            raise ValueError("graph edges require at least one provenance reference")
        return sorted(
            value,
            key=lambda ref: (
                ref.source_type,
                ref.source_id,
                ref.session_id or "",
                ref.attempt_id or -1,
            ),
        )


class GraphSubgraph(BaseModel):
    schema_version: str = GRAPH_SCHEMA_VERSION
    engine_version: str = INGESTION_ENGINE_VERSION
    session_id: Optional[str] = None
    application_fingerprint: Optional[str] = None
    nodes: List[GraphNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    ingested_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @field_validator("nodes")
    @classmethod
    def _sort_nodes(cls, value: List[GraphNode]) -> List[GraphNode]:
        return sorted(value, key=lambda node: (node.node_type.value, node.node_id))

    @field_validator("edges")
    @classmethod
    def _sort_edges(cls, value: List[GraphEdge]) -> List[GraphEdge]:
        return sorted(value, key=lambda edge: (edge.edge_type.value, edge.edge_id))


class GraphNotFoundError(Exception):
    """Raised when no graph data exists for the requested scope."""


class MalformedGraphEvidenceError(Exception):
    """Raised when persisted evidence cannot be ingested safely."""

    def __init__(self, message: str, *, details: Optional[List[str]] = None) -> None:
        super().__init__(message)
        self.details = details or []
