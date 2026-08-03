"""Dependency graph with cycle detection."""

from __future__ import annotations

from typing import Dict, List, Set

from alma_bridge.native_lab.digest import digest_of
from alma_bridge.native_lab.errors import DependencyCycleError
from alma_bridge.native_lab.models import (
    DependencyEdge,
    DependencyGraph,
    NativeRuntimeEngineeringWorkItem,
    WorkItemStatus,
)


def _build_adjacency(
    work_item: NativeRuntimeEngineeringWorkItem,
    all_items: Dict[str, NativeRuntimeEngineeringWorkItem],
) -> tuple[List[DependencyEdge], Set[str]]:
    edges: List[DependencyEdge] = []
    nodes: Set[str] = {work_item.work_item_id}
    for pred_id in work_item.prerequisite_work_item_ids:
        edges.append(
            DependencyEdge(
                predecessor_id=pred_id,
                successor_id=work_item.work_item_id,
                relationship="prerequisite",
                description="Required prerequisite work item",
            )
        )
        nodes.add(pred_id)
    for other in all_items.values():
        if work_item.work_item_id in other.prerequisite_work_item_ids:
            edges.append(
                DependencyEdge(
                    predecessor_id=work_item.work_item_id,
                    successor_id=other.work_item_id,
                    relationship="blocks",
                    description="This work item blocks successor",
                )
            )
            nodes.add(other.work_item_id)
    return edges, nodes


def _detect_cycle(nodes: Set[str], edges: List[DependencyEdge]) -> bool:
    adj: Dict[str, List[str]] = {n: [] for n in nodes}
    for edge in edges:
        if edge.relationship in ("prerequisite", "blocks"):
            adj.setdefault(edge.predecessor_id, []).append(edge.successor_id)
    visited: Set[str] = set()
    stack: Set[str] = set()

    def dfs(node: str) -> bool:
        if node in stack:
            return True
        if node in visited:
            return False
        visited.add(node)
        stack.add(node)
        for neighbor in adj.get(node, []):
            if dfs(neighbor):
                return True
        stack.remove(node)
        return False

    return any(dfs(n) for n in nodes)


def _blocked_by(
    work_item: NativeRuntimeEngineeringWorkItem,
    all_items: Dict[str, NativeRuntimeEngineeringWorkItem],
) -> List[str]:
    blockers: List[str] = []
    for pred_id in work_item.prerequisite_work_item_ids:
        pred = all_items.get(pred_id)
        if pred is None:
            blockers.append(f"Missing prerequisite: {pred_id}")
        elif pred.status not in (
            WorkItemStatus.COMPLETED,
            WorkItemStatus.SUPERSEDED,
        ):
            blockers.append(f"Prerequisite not complete: {pred_id} ({pred.status.value})")
    return blockers


def _critical_path(
    work_item_id: str,
    edges: List[DependencyEdge],
    all_items: Dict[str, NativeRuntimeEngineeringWorkItem],
) -> List[str]:
    preds = [
        e.predecessor_id
        for e in edges
        if e.successor_id == work_item_id and e.relationship == "prerequisite"
    ]
    if not preds:
        return [work_item_id]
    longest: List[str] = []
    for pred in preds:
        sub = _critical_path(pred, edges, all_items)
        if len(sub) > len(longest):
            longest = sub
    return longest + [work_item_id]


def build_dependency_graph(
    work_item: NativeRuntimeEngineeringWorkItem,
    all_items: Dict[str, NativeRuntimeEngineeringWorkItem],
) -> DependencyGraph:
    """Build DAG with cycle detection and blocked-by reporting."""
    edges, nodes = _build_adjacency(work_item, all_items)
    has_cycle = _detect_cycle(nodes, edges)
    if has_cycle:
        raise DependencyCycleError(
            f"Dependency cycle detected for work item: {work_item.work_item_id}"
        )
    blocked = _blocked_by(work_item, all_items)
    blocks = [
        e.successor_id
        for e in edges
        if e.predecessor_id == work_item.work_item_id and e.relationship == "blocks"
    ]
    critical = _critical_path(work_item.work_item_id, edges, all_items)
    body = {
        "work_item_id": work_item.work_item_id,
        "edge_count": len(edges),
        "blocked_count": len(blocked),
    }
    return DependencyGraph(
        work_item_id=work_item.work_item_id,
        edges=edges,
        blocked_by=blocked,
        blocks=blocks,
        critical_path=critical,
        has_cycle=False,
        graph_digest=digest_of(body),
    )


def validate_no_cycle_on_add(
    work_item_id: str,
    prerequisite_ids: List[str],
    all_items: Dict[str, NativeRuntimeEngineeringWorkItem],
) -> None:
    """Validate that adding prerequisites would not create a cycle."""
    fake = NativeRuntimeEngineeringWorkItem(
        work_item_id=work_item_id,
        title="validation",
        capability_id="",
        behavior_id="",
        bounded_scope="",
        prerequisite_work_item_ids=prerequisite_ids,
    )
    edges, nodes = _build_adjacency(fake, all_items)
    if _detect_cycle(nodes, edges):
        raise DependencyCycleError(f"Adding prerequisites would create cycle for {work_item_id}")
