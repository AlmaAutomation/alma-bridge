"""Evidence reference resolution and manifest generation."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from alma_bridge.config import PROJECT_ROOT
from alma_bridge.native_lab.models import (
    EvidenceLinkKind,
    EvidenceReference,
    NativeRuntimeEngineeringWorkItem,
    SEEDED_WORK_ITEM_ID,
)

MANIFEST_PATH = PROJECT_ROOT / "data" / "native_lab" / "evidence_manifest.json"
FIXTURE_MANIFEST = PROJECT_ROOT / "tests" / "fixtures" / "native_runtime" / "manifest.json"


class RepositoryStatus(str, Enum):
    COMMITTED_IMMUTABLE = "committed_immutable"
    PERSISTED_GENERATED = "persisted_generated"
    EXTERNAL = "external"
    MISSING = "missing"
    MUTABLE_LOCAL = "mutable_local"


class EvidenceManifestEntry(BaseModel):
    work_item_id: str
    evidence_reference_id: str
    artifact_type: str
    path_or_store_id: str
    digest: str = ""
    repository_status: RepositoryStatus
    resolves_after_restart: bool = True
    required_for_completion: bool = True


class EvidenceManifest(BaseModel):
    work_item_id: str
    schema_version: str = "evidence_manifest_v1"
    entries: List[EvidenceManifestEntry] = Field(default_factory=list)
    manifest_digest: str = ""


def _fixture_digest(name: str) -> str:
    if FIXTURE_MANIFEST.is_file():
        data = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
        for digest, fixture_name in data.get("fixtures", {}).items():
            if fixture_name == name:
                return digest
    path = PROJECT_ROOT / "tests" / "fixtures" / "native_runtime" / "bin" / name
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    return ""


def _file_digest(path: Path) -> str:
    if path.is_file():
        return hashlib.sha256(path.read_bytes()).hexdigest()
    return ""


def _classify_path(path: Path) -> RepositoryStatus:
    if not path.is_file():
        return RepositoryStatus.MISSING
    try:
        rel = path.resolve().relative_to(PROJECT_ROOT.resolve())
    except ValueError:
        return RepositoryStatus.MUTABLE_LOCAL
    if str(rel).startswith("data/native_lab/"):
        return RepositoryStatus.PERSISTED_GENERATED
    if str(rel).startswith("docs/") or str(rel).startswith("tests/"):
        return RepositoryStatus.COMMITTED_IMMUTABLE
    return RepositoryStatus.COMMITTED_IMMUTABLE


APPEND_CYCLE_EVIDENCE_SPECS: List[dict] = [
    {
        "reference_id": "ev_file_append_unsupported",
        "kind": EvidenceLinkKind.FIXTURE,
        "artifact_id": "file_append_unsupported.exe",
        "path": "tests/fixtures/native_runtime/bin/file_append_unsupported.exe",
        "required": True,
    },
    {
        "reference_id": "ev_append_existing_success",
        "kind": EvidenceLinkKind.FIXTURE,
        "artifact_id": "append_existing_success.exe",
        "path": "tests/fixtures/native_runtime/bin/append_existing_success.exe",
        "required": True,
    },
    {
        "reference_id": "ev_append_repeated",
        "kind": EvidenceLinkKind.FIXTURE,
        "artifact_id": "append_repeated.exe",
        "path": "tests/fixtures/native_runtime/bin/append_repeated.exe",
        "required": True,
    },
    {
        "reference_id": "ev_append_unicode",
        "kind": EvidenceLinkKind.FIXTURE,
        "artifact_id": "append_unicode.exe",
        "path": "tests/fixtures/native_runtime/bin/append_unicode.exe",
        "required": True,
    },
    {
        "reference_id": "ev_append_zero_length",
        "kind": EvidenceLinkKind.FIXTURE,
        "artifact_id": "append_zero_length.exe",
        "path": "tests/fixtures/native_runtime/bin/append_zero_length.exe",
        "required": False,
    },
    {
        "reference_id": "ev_append_invalid_handle",
        "kind": EvidenceLinkKind.FIXTURE,
        "artifact_id": "append_invalid_handle.exe",
        "path": "tests/fixtures/native_runtime/bin/append_invalid_handle.exe",
        "required": False,
    },
    {
        "reference_id": "ev_append_missing_file",
        "kind": EvidenceLinkKind.FIXTURE,
        "artifact_id": "append_missing_file.exe",
        "path": "tests/fixtures/native_runtime/bin/append_missing_file.exe",
        "required": False,
    },
    {
        "reference_id": "ev_append_path_traversal",
        "kind": EvidenceLinkKind.FIXTURE,
        "artifact_id": "append_path_traversal.exe",
        "path": "tests/fixtures/native_runtime/bin/append_path_traversal.exe",
        "required": True,
    },
    {
        "reference_id": "ev_append_overlapped_unsupported",
        "kind": EvidenceLinkKind.FIXTURE,
        "artifact_id": "append_overlapped_unsupported.exe",
        "path": "tests/fixtures/native_runtime/bin/append_overlapped_unsupported.exe",
        "required": True,
    },
    {
        "reference_id": "ev_design_doc",
        "kind": EvidenceLinkKind.SPECIFICATION,
        "artifact_id": "append_existing_file_design.md",
        "path": "docs/native-runtime/append_existing_file_design.md",
        "required": True,
    },
    {
        "reference_id": "ev_certification_evidence",
        "kind": EvidenceLinkKind.CERTIFICATION,
        "artifact_id": "append_existing_file_certification_evidence.md",
        "path": "docs/certification/append_existing_file_evidence.md",
        "required": True,
    },
    {
        "reference_id": "ev_governance_proposal",
        "kind": EvidenceLinkKind.EXPANSION,
        "artifact_id": "gov_proposal_append_existing_file_v1",
        "path": "tests/seed/governance_append_existing_file_proposal.json",
        "required": False,
    },
    {
        "reference_id": "ev_behavior_tests",
        "kind": EvidenceLinkKind.BEHAVIOR_TEST,
        "artifact_id": "test_append_behavior.py",
        "path": "tests/native_runtime/test_append_behavior.py",
        "required": True,
    },
    {
        "reference_id": "ev_security_tests",
        "kind": EvidenceLinkKind.BEHAVIOR_TEST,
        "artifact_id": "test_append_security.py",
        "path": "tests/native_runtime/test_append_security.py",
        "required": True,
    },
    {
        "reference_id": "ev_conformance_tests",
        "kind": EvidenceLinkKind.BEHAVIOR_TEST,
        "artifact_id": "test_append_conformance.py",
        "path": "tests/runtime/test_append_conformance.py",
        "required": True,
    },
    {
        "reference_id": "ev_verification_record",
        "kind": EvidenceLinkKind.VERIFICATION,
        "artifact_id": "append_verification_contract_v1",
        "path": "data/native_lab/generated/append_verification_contract_v1.json",
        "required": True,
    },
    {
        "reference_id": "ev_benchmark_baseline",
        "kind": EvidenceLinkKind.BENCHMARK,
        "artifact_id": "append_benchmark_baseline_v1",
        "path": "data/native_lab/generated/append_benchmark_baseline_v1.json",
        "required": True,
    },
]


def resolve_evidence_reference(reference: EvidenceReference) -> Optional[Path]:
    """Resolve an evidence reference to a local path when possible."""
    if reference.fixture_path:
        path = PROJECT_ROOT / reference.fixture_path
        if path.is_file():
            return path
    for spec in APPEND_CYCLE_EVIDENCE_SPECS:
        if spec["reference_id"] == reference.reference_id:
            path = PROJECT_ROOT / spec["path"]
            if path.is_file():
                return path
    candidate = PROJECT_ROOT / reference.artifact_id
    if candidate.is_file():
        return candidate
    return None


def validate_required_evidence_resolves(work_item: NativeRuntimeEngineeringWorkItem) -> List[str]:
    """Return reference_ids of required evidence that fail to resolve."""
    if work_item.work_item_id != SEEDED_WORK_ITEM_ID:
        return []
    ref_ids = {r.reference_id for r in work_item.evidence_references}
    missing: List[str] = []
    for spec in APPEND_CYCLE_EVIDENCE_SPECS:
        if not spec.get("required", True):
            continue
        ref_id = spec["reference_id"]
        if ref_id not in ref_ids:
            missing.append(ref_id)
            continue
        ref = next(r for r in work_item.evidence_references if r.reference_id == ref_id)
        path = resolve_evidence_reference(ref)
        if path is None:
            missing.append(ref_id)
    return missing


def build_evidence_manifest(work_item: NativeRuntimeEngineeringWorkItem) -> EvidenceManifest:
    """Build manifest for all evidence references on a work item."""
    entries: List[EvidenceManifestEntry] = []
    spec_by_id = {s["reference_id"]: s for s in APPEND_CYCLE_EVIDENCE_SPECS}
    for ref in work_item.evidence_references:
        spec = spec_by_id.get(ref.reference_id, {})
        path_str = spec.get("path", ref.fixture_path or ref.artifact_id)
        path = PROJECT_ROOT / path_str if path_str else None
        digest = ref.digest
        status = RepositoryStatus.MISSING
        if path is not None:
            status = _classify_path(path)
            if not digest and path.is_file():
                digest = _file_digest(path)
        entries.append(
            EvidenceManifestEntry(
                work_item_id=work_item.work_item_id,
                evidence_reference_id=ref.reference_id,
                artifact_type=ref.kind.value,
                path_or_store_id=path_str,
                digest=digest,
                repository_status=status,
                resolves_after_restart=status != RepositoryStatus.MISSING,
                required_for_completion=spec.get("required", False),
            )
        )
    from alma_bridge.native_lab.digest import digest_of

    body = {"work_item_id": work_item.work_item_id, "entry_count": len(entries)}
    return EvidenceManifest(
        work_item_id=work_item.work_item_id,
        entries=entries,
        manifest_digest=digest_of(body),
    )


def load_committed_manifest() -> Optional[EvidenceManifest]:
    if MANIFEST_PATH.is_file():
        return EvidenceManifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    return None
