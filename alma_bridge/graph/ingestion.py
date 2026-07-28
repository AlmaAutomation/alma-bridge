"""Idempotent ingestion of persisted evidence into the Compatibility Graph."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from alma_bridge.graph.models import (
    INGESTION_ENGINE_VERSION,
    GraphEdge,
    GraphEdgeType,
    GraphNode,
    GraphNodeType,
    GraphProvenance,
    GraphSubgraph,
    MalformedGraphEvidenceError,
)
from alma_bridge.graph.queries import (
    build_edge_id,
    build_node_id,
    environment_identity,
    manifest_runtime_identity,
    provenance_fingerprint,
)
from alma_bridge.graph.repository import GraphEvidenceRepository, GraphStore
from alma_bridge.intelligence.evidence import EvidenceBundleBuilder
from alma_bridge.intelligence.models import EvidenceBundle


class GraphIngestionEngine:
    """Derive versioned graph nodes and edges from persisted evidence only."""

    engine_version = INGESTION_ENGINE_VERSION

    def __init__(
        self,
        repository: GraphEvidenceRepository,
        store: Optional[GraphStore] = None,
    ) -> None:
        self._repository = repository
        self._builder = EvidenceBundleBuilder(repository)
        self._store = store or GraphStore()

    def ingest_session(self, session_id: str) -> GraphSubgraph:
        bundle = self._builder.for_session(session_id)
        nodes, edges = self._derive_from_bundle(bundle, primary_session_id=session_id)
        self._persist(nodes, edges)
        return GraphSubgraph(
            session_id=session_id,
            application_fingerprint=bundle.application_fingerprint,
            nodes=nodes,
            edges=edges,
        )

    def ingest_application(self, fingerprint: str) -> GraphSubgraph:
        bundle = self._builder.for_application(fingerprint)
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []
        seen_node_ids: set[str] = set()
        seen_edge_ids: set[str] = set()

        for session in bundle.artifacts.get("sessions") or []:
            session_id = str(session["session_id"])
            session_bundle = self._builder.for_session(session_id)
            session_nodes, session_edges = self._derive_from_bundle(
                session_bundle,
                primary_session_id=session_id,
            )
            for node in session_nodes:
                if node.node_id not in seen_node_ids:
                    nodes.append(node)
                    seen_node_ids.add(node.node_id)
            for edge in session_edges:
                if edge.edge_id not in seen_edge_ids:
                    edges.append(edge)
                    seen_edge_ids.add(edge.edge_id)

        self._persist(nodes, edges)
        return GraphSubgraph(
            application_fingerprint=fingerprint,
            nodes=nodes,
            edges=edges,
        )

    def _derive_from_bundle(
        self,
        bundle: EvidenceBundle,
        *,
        primary_session_id: str,
    ) -> Tuple[List[GraphNode], List[GraphEdge]]:
        nodes: List[GraphNode] = []
        edges: List[GraphEdge] = []
        node_index: Dict[str, GraphNode] = {}

        fingerprint = bundle.application_fingerprint
        if not fingerprint:
            raise MalformedGraphEvidenceError(
                f"session {primary_session_id} missing application fingerprint"
            )

        session_node = self._make_node(
            node_index,
            GraphNodeType.EXECUTION_SESSION,
            primary_session_id,
            {
                "file_path": bundle.file_path,
                "application_fingerprint": fingerprint,
            },
        )
        app_node = self._make_node(
            node_index,
            GraphNodeType.APPLICATION,
            fingerprint,
            {"file_hash": fingerprint, "file_path": bundle.file_path},
        )

        session_provenance = [
            GraphProvenance(
                source_type="session",
                source_id=primary_session_id,
                session_id=primary_session_id,
                captured_at=self._session_captured_at(bundle, primary_session_id),
            )
        ]
        edges.append(
            self._make_edge(
                GraphEdgeType.SESSION_FOR_APPLICATION,
                session_node.node_id,
                app_node.node_id,
                scope=primary_session_id,
                confidence=1.0,
                provenance=session_provenance,
            )
        )

        for key, artifact in sorted(bundle.artifacts.items()):
            if not key.startswith("attempt:"):
                continue
            parts = key.split(":")
            if len(parts) != 3:
                raise MalformedGraphEvidenceError(
                    f"malformed attempt artifact key: {key}",
                    details=[key],
                )
            session_id, attempt_number_str = parts[1], parts[2]
            attempt_number = int(attempt_number_str)
            attempt_scope = f"{session_id}:{attempt_number}"

            strategy_id = artifact.get("strategy_id")
            if strategy_id:
                strategy_node = self._make_node(
                    node_index,
                    GraphNodeType.LAUNCH_STRATEGY,
                    str(strategy_id),
                    {"strategy_id": strategy_id},
                )
                attempt_provenance = [
                    GraphProvenance(
                        source_type="attempt",
                        source_id=attempt_scope,
                        session_id=session_id,
                        attempt_id=attempt_number,
                    )
                ]
                edges.append(
                    self._make_edge(
                        GraphEdgeType.LAUNCHED_VIA,
                        session_node.node_id,
                        strategy_node.node_id,
                        scope=attempt_scope,
                        confidence=0.9,
                        provenance=attempt_provenance,
                    )
                )

            verification_key = f"verification:{session_id}:{attempt_number}"
            verification = bundle.artifacts.get(verification_key) or {}
            if verification:
                self._ingest_verification_edges(
                    edges=edges,
                    node_index=node_index,
                    session_node=session_node,
                    session_id=session_id,
                    attempt_number=attempt_number,
                    attempt_scope=attempt_scope,
                    verification=verification,
                )

            framework_key = f"framework_detection:{session_id}:{attempt_number}"
            framework = bundle.artifacts.get(framework_key)
            if framework:
                self._ingest_framework_edge(
                    edges=edges,
                    node_index=node_index,
                    session_node=session_node,
                    session_id=session_id,
                    attempt_number=attempt_number,
                    attempt_scope=attempt_scope,
                    framework=framework,
                )

            manifest_key = f"manifest_capture:{session_id}:{attempt_number}"
            manifest = bundle.artifacts.get(manifest_key)
            if manifest:
                self._ingest_manifest_edges(
                    edges=edges,
                    node_index=node_index,
                    session_node=session_node,
                    session_id=session_id,
                    attempt_number=attempt_number,
                    attempt_scope=attempt_scope,
                    manifest=manifest,
                )

            evidence_node = self._make_node(
                node_index,
                GraphNodeType.EVIDENCE_RECORD,
                attempt_scope,
                {
                    "artifact_key": key,
                    "strategy_id": strategy_id,
                    "phase": artifact.get("phase"),
                },
            )
            edges.append(
                self._make_edge(
                    GraphEdgeType.PRODUCED_EVIDENCE,
                    session_node.node_id,
                    evidence_node.node_id,
                    scope=attempt_scope,
                    confidence=0.8,
                    provenance=[
                        GraphProvenance(
                            source_type="attempt",
                            source_id=attempt_scope,
                            session_id=session_id,
                            attempt_id=attempt_number,
                        )
                    ],
                )
            )

        environment_key = f"run_environment:{primary_session_id}"
        environment = bundle.artifacts.get(environment_key)
        if environment:
            self._ingest_environment_edge(
                edges=edges,
                node_index=node_index,
                session_node=session_node,
                session_id=primary_session_id,
                environment=environment,
            )

        nodes = list(node_index.values())
        return nodes, edges

    def _ingest_verification_edges(
        self,
        *,
        edges: List[GraphEdge],
        node_index: Dict[str, GraphNode],
        session_node: GraphNode,
        session_id: str,
        attempt_number: int,
        attempt_scope: str,
        verification: Dict[str, Any],
    ) -> None:
        if verification.get("passed") is not True:
            return

        policy = verification.get("success_policy") or {}
        policy_id = str(policy.get("policy_id") or "unknown")
        policy_version = str(policy.get("policy_version") or "unknown")
        required_checks = policy.get("required_checks") or {}
        flat_checks: List[str] = []
        if isinstance(required_checks, dict):
            for check_kind, values in sorted(required_checks.items()):
                for value in values or []:
                    flat_checks.append(f"{check_kind}:{value}")
        elif isinstance(required_checks, list):
            flat_checks = [str(item) for item in required_checks]

        contract_identity = f"{policy_id}:{policy_version}:{','.join(sorted(flat_checks))}"
        contract_node = self._make_node(
            node_index,
            GraphNodeType.VERIFICATION_CONTRACT,
            contract_identity,
            {
                "policy_id": policy_id,
                "policy_version": policy_version,
                "required_checks": required_checks,
            },
        )
        provenance = [
            GraphProvenance(
                source_type="verification",
                source_id=attempt_scope,
                session_id=session_id,
                attempt_id=attempt_number,
            )
        ]
        edges.append(
            self._make_edge(
                GraphEdgeType.VERIFIED_BY,
                session_node.node_id,
                contract_node.node_id,
                scope=attempt_scope,
                confidence=float(verification.get("confidence") or 0.9),
                provenance=provenance,
            )
        )

    def _ingest_framework_edge(
        self,
        *,
        edges: List[GraphEdge],
        node_index: Dict[str, GraphNode],
        session_node: GraphNode,
        session_id: str,
        attempt_number: int,
        attempt_scope: str,
        framework: Dict[str, Any],
    ) -> None:
        framework_name = str(framework.get("framework") or "unknown")
        framework_node = self._make_node(
            node_index,
            GraphNodeType.FRAMEWORK,
            framework_name,
            {
                "framework": framework_name,
                "source": framework.get("source"),
                "detection_confidence": framework.get("confidence"),
            },
        )
        provenance = [
            GraphProvenance(
                source_type="framework_detection",
                source_id=attempt_scope,
                session_id=session_id,
                attempt_id=attempt_number,
            )
        ]
        edges.append(
            self._make_edge(
                GraphEdgeType.DETECTED_FRAMEWORK,
                session_node.node_id,
                framework_node.node_id,
                scope=attempt_scope,
                confidence=float(framework.get("confidence") or 0.75),
                provenance=provenance,
            )
        )

    def _ingest_manifest_edges(
        self,
        *,
        edges: List[GraphEdge],
        node_index: Dict[str, GraphNode],
        session_node: GraphNode,
        session_id: str,
        attempt_number: int,
        attempt_scope: str,
        manifest: Dict[str, Any],
    ) -> None:
        from alma_bridge.compatibility.profile_fingerprints import build_bridge_manifest_hash

        manifest_hash = build_bridge_manifest_hash(manifest)
        manifest_node = self._make_node(
            node_index,
            GraphNodeType.PREFIX_MANIFEST,
            manifest_hash,
            {
                "manifest_hash": manifest_hash,
                "schema": manifest.get("schema"),
            },
        )
        provenance = [
            GraphProvenance(
                source_type="manifest_capture",
                source_id=attempt_scope,
                session_id=session_id,
                attempt_id=attempt_number,
            )
        ]
        edges.append(
            self._make_edge(
                GraphEdgeType.USED_PREFIX_MANIFEST,
                session_node.node_id,
                manifest_node.node_id,
                scope=attempt_scope,
                confidence=0.85,
                provenance=provenance,
            )
        )

        base_runtime = manifest.get("base_runtime") or {}
        runtime_kind = str(base_runtime.get("kind") or "unknown")
        if runtime_kind != "unknown":
            runtime_identity = manifest_runtime_identity(manifest)
            runtime_node = self._make_node(
                node_index,
                GraphNodeType.RUNTIME,
                runtime_identity,
                {
                    "kind": runtime_kind,
                    "version_family": base_runtime.get("version_family"),
                    "observation": "manifest_capture",
                },
            )
            edges.append(
                self._make_edge(
                    GraphEdgeType.RUNTIME_OBSERVED,
                    manifest_node.node_id,
                    runtime_node.node_id,
                    scope=attempt_scope,
                    confidence=0.8,
                    provenance=provenance,
                )
            )

    def _ingest_environment_edge(
        self,
        *,
        edges: List[GraphEdge],
        node_index: Dict[str, GraphNode],
        session_node: GraphNode,
        session_id: str,
        environment: Dict[str, Any],
    ) -> None:
        identity = environment_identity(environment)
        environment_node = self._make_node(
            node_index,
            GraphNodeType.ENVIRONMENT,
            identity,
            {
                "environment_identity": identity,
                "summary": self._environment_summary(environment),
                **{
                    key: environment.get(key)
                    for key in (
                        "alma_bridge_version",
                        "host_os",
                        "kernel_version",
                        "host_architecture",
                        "wine_version",
                        "wine_architecture",
                        "prefix_id",
                    )
                    if environment.get(key) is not None
                },
            },
        )
        provenance = [
            GraphProvenance(
                source_type="run_environment",
                source_id=session_id,
                session_id=session_id,
            )
        ]
        edges.append(
            self._make_edge(
                GraphEdgeType.SESSION_USED_ENVIRONMENT,
                session_node.node_id,
                environment_node.node_id,
                scope=session_id,
                confidence=1.0,
                provenance=provenance,
            )
        )

    @staticmethod
    def _environment_summary(environment: Dict[str, Any]) -> str:
        parts: List[str] = []
        wine_version = environment.get("wine_version")
        if wine_version:
            parts.append(str(wine_version))
        host_os = environment.get("host_os")
        host_arch = environment.get("host_architecture")
        if host_os and host_arch:
            parts.append(f"{host_os}/{host_arch}")
        elif host_os:
            parts.append(str(host_os))
        prefix_id = environment.get("prefix_id")
        if prefix_id:
            parts.append(f"prefix:{str(prefix_id)[:12]}")
        return " | ".join(parts) if parts else "environment observed"

    def _make_node(
        self,
        node_index: Dict[str, GraphNode],
        node_type: GraphNodeType,
        identity_key: str,
        attributes: Dict[str, Any],
    ) -> GraphNode:
        node_id = build_node_id(node_type=node_type, identity_key=identity_key)
        existing = node_index.get(node_id)
        if existing:
            return existing
        node = GraphNode(
            node_id=node_id,
            node_type=node_type,
            identity_key=identity_key,
            attributes=attributes,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        node_index[node_id] = node
        return node

    def _make_edge(
        self,
        edge_type: GraphEdgeType,
        source_node_id: str,
        target_node_id: str,
        *,
        scope: str,
        confidence: float,
        provenance: List[GraphProvenance],
    ) -> GraphEdge:
        evidence_fp = provenance_fingerprint(provenance)
        edge_id = build_edge_id(
            edge_type=edge_type,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            scope=scope,
            evidence_fingerprint=evidence_fp,
        )
        return GraphEdge(
            edge_id=edge_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            edge_type=edge_type,
            scope=scope,
            confidence=confidence,
            evidence_references=provenance,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def _persist(self, nodes: List[GraphNode], edges: List[GraphEdge]) -> None:
        for node in nodes:
            self._store.upsert_node(node)
        for edge in edges:
            self._store.upsert_edge(edge)

    @staticmethod
    def _session_captured_at(bundle: EvidenceBundle, session_id: str) -> Optional[str]:
        for session in bundle.artifacts.get("sessions") or []:
            if str(session.get("session_id")) == session_id:
                return session.get("finished_at") or session.get("started_at")
        return None