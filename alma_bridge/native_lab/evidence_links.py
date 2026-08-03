"""Read-only evidence attachment links."""

from __future__ import annotations

import uuid
from pathlib import Path

from alma_bridge.native_lab.digest import digest_of
from alma_bridge.native_lab.models import EvidenceLinkKind, EvidenceReference


def create_evidence_reference(
    *,
    kind: EvidenceLinkKind,
    source: str,
    artifact_id: str,
    digest: str = "",
    fixture_path: str | None = None,
    attached_by: str = "",
) -> EvidenceReference:
    """Create a read-only evidence reference — does not mutate source evidence."""
    reference_id = f"ev_{uuid.uuid4().hex[:12]}"
    return EvidenceReference(
        reference_id=reference_id,
        kind=kind,
        source=source,
        artifact_id=artifact_id,
        digest=digest,
        fixture_path=fixture_path,
        attached_by=attached_by,
        evidence_stale=False,
    )


def infer_evidence_kind(artifact: str) -> EvidenceLinkKind:
    lower = artifact.lower()
    if lower.endswith(".exe") or "fixture" in lower:
        return EvidenceLinkKind.FIXTURE
    if "benchmark" in lower:
        return EvidenceLinkKind.BENCHMARK
    if "verification" in lower:
        return EvidenceLinkKind.VERIFICATION
    if "certification" in lower:
        return EvidenceLinkKind.CERTIFICATION
    return EvidenceLinkKind.BEHAVIOR_TEST


def check_evidence_staleness(
    reference: EvidenceReference,
    *,
    current_digest: str | None = None,
) -> EvidenceReference:
    """Mark reference stale if source digest changed — never rewrite original attachment."""
    if current_digest and reference.digest and current_digest != reference.digest:
        return reference.model_copy(
            update={
                "evidence_stale": True,
                "stale_reason": "Source evidence digest changed",
            }
        )
    return reference


def artifact_digest_from_path(path: str) -> str:
    """Best-effort digest lookup from fixture manifest."""
    try:
        import json

        manifest_path = Path("tests/fixtures/native_runtime/manifest.json")
        if not manifest_path.is_file():
            return ""
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        name = Path(path).name
        for digest, fixture_name in manifest.get("fixtures", {}).items():
            if fixture_name == name:
                return digest
    except Exception:
        pass
    return ""
