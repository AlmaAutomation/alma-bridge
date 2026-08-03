"""Compatibility graph with provenance."""

from __future__ import annotations

from typing import List

from alma_bridge.compatibility_intelligence.models import (
    ApiClassificationResult,
    CapabilityRequirement,
    CompatibilityGraph,
    GraphEdge,
    GraphNode,
    ImportedFunction,
    ProvenanceEvidence,
)


def build_compatibility_graph(
    file_path: str,
    binary_digest: str,
    imports: List[ImportedFunction],
    classifications: List[ApiClassificationResult],
    required_capabilities: List[CapabilityRequirement],
    *,
    provenance: ProvenanceEvidence,
) -> CompatibilityGraph:
    """Build Application → Imports → APIs → Capabilities → Providers graph."""
    nodes: List[GraphNode] = []
    edges: List[GraphEdge] = []
    app_id = f"app:{binary_digest[:16]}"
    app_name = file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]

    nodes.append(
        GraphNode(
            node_id=app_id,
            node_type="application",
            label=app_name,
            metadata={"digest": binary_digest},
            provenance=provenance,
        )
    )

    cls_by_key = {(c.dll, c.function): c for c in classifications}

    for imp in imports:
        dll_id = f"dll:{imp.dll}"
        if not any(n.node_id == dll_id for n in nodes):
            nodes.append(
                GraphNode(
                    node_id=dll_id,
                    node_type="dll",
                    label=imp.dll,
                    provenance=provenance,
                )
            )
            edges.append(
                GraphEdge(
                    edge_id=f"{app_id}->{dll_id}",
                    source_id=app_id,
                    target_id=dll_id,
                    relation="imports",
                    provenance=provenance,
                )
            )

        api_id = f"api:{imp.dll}:{imp.name}"
        cls = cls_by_key.get((imp.dll, imp.name))
        nodes.append(
            GraphNode(
                node_id=api_id,
                node_type="api",
                label=f"{imp.dll}!{imp.name}",
                metadata={
                    "known": str(cls.is_known if cls else False),
                    "capability_id": cls.capability_id if cls else "api.unknown",
                },
                provenance=provenance,
            )
        )
        edges.append(
            GraphEdge(
                edge_id=f"{dll_id}->{api_id}",
                source_id=dll_id,
                target_id=api_id,
                relation="exports",
                provenance=provenance,
            )
        )

        if cls:
            cap_id = f"cap:{cls.capability_id}"
            if not any(n.node_id == cap_id for n in nodes):
                nodes.append(
                    GraphNode(
                        node_id=cap_id,
                        node_type="capability",
                        label=cls.capability_id,
                        provenance=provenance,
                    )
                )
            edges.append(
                GraphEdge(
                    edge_id=f"{api_id}->{cap_id}",
                    source_id=api_id,
                    target_id=cap_id,
                    relation="requires",
                    provenance=provenance,
                )
            )

    for req in required_capabilities:
        cap_id = f"cap:{req.capability_id}"
        for provider_id in ("native_alma", "wine"):
            prov_node_id = f"provider:{provider_id}"
            if not any(n.node_id == prov_node_id for n in nodes):
                nodes.append(
                    GraphNode(
                        node_id=prov_node_id,
                        node_type="provider",
                        label=provider_id,
                        provenance=provenance,
                    )
                )
            edges.append(
                GraphEdge(
                    edge_id=f"{cap_id}->{prov_node_id}",
                    source_id=cap_id,
                    target_id=prov_node_id,
                    relation="implemented_by",
                    provenance=provenance,
                )
            )

    nodes.sort(key=lambda n: n.node_id)
    edges.sort(key=lambda e: e.edge_id)
    return CompatibilityGraph(nodes=nodes, edges=edges)
