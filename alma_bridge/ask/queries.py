"""Evidence reference helpers for Ask Alma."""

from __future__ import annotations

from typing import Iterable, List, Optional

from alma_bridge.ask.models import AskAlmaEvidenceReference
from alma_bridge.knowledge.models import KnowledgeEvidenceReference


def to_ask_evidence_reference(
    ref: KnowledgeEvidenceReference,
    *,
    source_layer: str,
) -> AskAlmaEvidenceReference:
    return AskAlmaEvidenceReference(
        source_layer=source_layer,
        source_type=ref.source_type,
        source_id=ref.source_id,
        session_id=ref.session_id,
        attempt_id=ref.attempt_id,
        artifact_key=ref.artifact_key or "",
    )


def merge_evidence_references(
    *groups: Iterable[AskAlmaEvidenceReference],
) -> List[AskAlmaEvidenceReference]:
    seen: set[tuple[str, str, str, str]] = set()
    merged: List[AskAlmaEvidenceReference] = []
    for group in groups:
        for ref in group:
            key = (ref.source_layer, ref.source_type, ref.source_id, ref.artifact_key)
            if key in seen:
                continue
            seen.add(key)
            merged.append(ref)
    return sorted(
        merged,
        key=lambda ref: (ref.source_layer, ref.source_type, ref.source_id, ref.artifact_key),
    )


def refs_from_knowledge(profile, *, limit: Optional[int] = None) -> List[AskAlmaEvidenceReference]:
    refs: List[AskAlmaEvidenceReference] = []
    for framework in profile.observed_frameworks:
        refs.extend(
            to_ask_evidence_reference(ref, source_layer="knowledge")
            for ref in framework.evidence_references
        )
    for strategy in profile.observed_launch_strategies:
        refs.extend(
            to_ask_evidence_reference(ref, source_layer="knowledge")
            for ref in strategy.evidence_references
        )
    for runtime in profile.observed_runtimes:
        refs.extend(
            to_ask_evidence_reference(ref, source_layer="knowledge")
            for ref in runtime.evidence_references
        )
    for contract in profile.verification_contracts:
        refs.extend(
            to_ask_evidence_reference(ref, source_layer="knowledge")
            for ref in contract.evidence_references
        )
    for conflict in profile.conflicts:
        for side_refs in conflict.evidence_by_side.values():
            refs.extend(
                to_ask_evidence_reference(ref, source_layer="knowledge")
                for ref in side_refs
            )
    merged = merge_evidence_references(refs)
    if limit is not None:
        return merged[:limit]
    return merged
