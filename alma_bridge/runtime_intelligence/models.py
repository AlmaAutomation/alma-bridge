"""Domain models for Runtime Intelligence."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Mapping, Optional

from pydantic import BaseModel, Field, field_validator

from alma_bridge.compatibility.profile_fingerprints import sha256_v1

RUNTIME_INTELLIGENCE_SCHEMA_VERSION = "runtime_intelligence_corpus_v1"


class CorpusKind(str, Enum):
    ENGINEERING = "engineering"
    REAL_WORLD = "real_world"


class BehaviorFamilyId(str, Enum):
    FILESYSTEM = "filesystem"
    CONSOLE = "console"
    MEMORY = "memory"
    CRT = "crt"
    REGISTRY = "registry"
    NETWORKING = "networking"
    SYNCHRONIZATION = "synchronization"
    GUI = "gui"


class CorpusProvenance(BaseModel):
    source: str
    fixture_path: str = ""


class CorpusEnrollmentEntry(BaseModel):
    entry_id: str
    application_fingerprint: str
    binary_digest: str
    provenance: CorpusProvenance
    enrolled_at: str

    def to_canonical_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "application_fingerprint": self.application_fingerprint,
            "binary_digest": self.binary_digest,
            "provenance": self.provenance.model_dump(mode="json"),
            "enrolled_at": self.enrolled_at,
        }


class CorpusManifest(BaseModel):
    schema_version: str
    corpus: CorpusKind
    entries: List[CorpusEnrollmentEntry] = Field(default_factory=list)
    digest: str

    @field_validator("schema_version")
    @classmethod
    def _require_schema_version(cls, value: str) -> str:
        if value != RUNTIME_INTELLIGENCE_SCHEMA_VERSION:
            raise ValueError(f"unsupported corpus schema: {value}")
        return value

    @field_validator("entries")
    @classmethod
    def _sort_entries(
        cls,
        value: List[CorpusEnrollmentEntry],
    ) -> List[CorpusEnrollmentEntry]:
        return sorted(value, key=lambda entry: entry.entry_id)


class CanonicalFamily(BaseModel):
    family_id: BehaviorFamilyId
    name: str
    description: str


class BehaviorFamilyMapping(BaseModel):
    behavior_id: str
    family_id: BehaviorFamilyId


def compute_manifest_digest(entries: List[CorpusEnrollmentEntry]) -> str:
    """Deterministic digest over canonical serialized enrollment entries."""
    payload: Mapping[str, Any] = {
        "entries": [entry.to_canonical_dict() for entry in sorted(entries, key=lambda e: e.entry_id)],
    }
    return sha256_v1(payload)


def compute_enrollment_entry_id(*, corpus: CorpusKind, binary_digest: str) -> str:
    return sha256_v1({"corpus": corpus.value, "binary_digest": binary_digest})


def compute_application_fingerprint(
    *,
    binary_digest: str,
    fixture_name: str,
    corpus: CorpusKind,
) -> str:
    return sha256_v1(
        {
            "binary_digest": binary_digest,
            "fixture_name": fixture_name,
            "corpus_track": corpus.value,
        }
    )
