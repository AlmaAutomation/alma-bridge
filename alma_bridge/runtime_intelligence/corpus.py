"""Manifest-backed corpus enrollment for Runtime Intelligence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

from alma_bridge.runtime_intelligence.models import (
    CorpusEnrollmentEntry,
    CorpusKind,
    CorpusManifest,
    compute_manifest_digest,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CORPUS_DATA_ROOT = _REPO_ROOT / "data" / "runtime_intelligence" / "corpora"


class CorpusResolutionError(ValueError):
    """Raised when corpus resolution preconditions are not met."""


def corpus_manifest_path(corpus: CorpusKind) -> Path:
    return _CORPUS_DATA_ROOT / corpus.value / "manifest.json"


def require_corpus(corpus: Optional[CorpusKind]) -> CorpusKind:
    """Reject queries that do not specify an explicit corpus track."""
    if corpus is None:
        raise CorpusResolutionError("explicit corpus is required; corpora are never merged")
    return corpus


def load_corpus_manifest(corpus: CorpusKind) -> CorpusManifest:
    path = corpus_manifest_path(corpus)
    raw = json.loads(path.read_text(encoding="utf-8"))
    manifest = CorpusManifest.model_validate(raw)
    if manifest.corpus != corpus:
        raise CorpusResolutionError(
            f"manifest corpus mismatch: expected {corpus.value}, found {manifest.corpus.value}"
        )
    expected_digest = compute_manifest_digest(manifest.entries)
    if manifest.digest != expected_digest:
        raise CorpusResolutionError(
            f"manifest digest mismatch for {corpus.value}: expected {expected_digest}, found {manifest.digest}"
        )
    return manifest


def _index_by_digest(entries: List[CorpusEnrollmentEntry]) -> Dict[str, CorpusEnrollmentEntry]:
    return {entry.binary_digest: entry for entry in entries}


def _index_by_fingerprint(entries: List[CorpusEnrollmentEntry]) -> Dict[str, CorpusEnrollmentEntry]:
    return {entry.application_fingerprint: entry for entry in entries}


class CorpusEnrollmentResolver:
    """Resolve enrollment within a single explicit corpus track."""

    def __init__(self, *, engineering: CorpusManifest, real_world: CorpusManifest) -> None:
        self._manifests: Dict[CorpusKind, CorpusManifest] = {
            CorpusKind.ENGINEERING: engineering,
            CorpusKind.REAL_WORLD: real_world,
        }
        self._by_digest: Dict[CorpusKind, Dict[str, CorpusEnrollmentEntry]] = {
            corpus: _index_by_digest(manifest.entries) for corpus, manifest in self._manifests.items()
        }
        self._by_fingerprint: Dict[CorpusKind, Dict[str, CorpusEnrollmentEntry]] = {
            corpus: _index_by_fingerprint(manifest.entries)
            for corpus, manifest in self._manifests.items()
        }

    @classmethod
    def from_manifest_files(cls) -> "CorpusEnrollmentResolver":
        return cls(
            engineering=load_corpus_manifest(CorpusKind.ENGINEERING),
            real_world=load_corpus_manifest(CorpusKind.REAL_WORLD),
        )

    def manifest_for(self, corpus: CorpusKind) -> CorpusManifest:
        require_corpus(corpus)
        return self._manifests[corpus]

    def resolve_by_digest(self, corpus: CorpusKind, binary_digest: str) -> Optional[CorpusEnrollmentEntry]:
        require_corpus(corpus)
        return self._by_digest[corpus].get(binary_digest)

    def resolve_by_fingerprint(
        self,
        corpus: CorpusKind,
        application_fingerprint: str,
    ) -> Optional[CorpusEnrollmentEntry]:
        require_corpus(corpus)
        return self._by_fingerprint[corpus].get(application_fingerprint)

    def resolve(
        self,
        corpus: CorpusKind,
        *,
        binary_digest: Optional[str] = None,
        application_fingerprint: Optional[str] = None,
    ) -> Optional[CorpusEnrollmentEntry]:
        require_corpus(corpus)
        if binary_digest is None and application_fingerprint is None:
            raise CorpusResolutionError("binary_digest or application_fingerprint is required")
        if binary_digest is not None:
            entry = self.resolve_by_digest(corpus, binary_digest)
            if entry is not None:
                return entry
        if application_fingerprint is not None:
            return self.resolve_by_fingerprint(corpus, application_fingerprint)
        return None

    def enrolled_digests(self, corpus: CorpusKind) -> frozenset[str]:
        require_corpus(corpus)
        return frozenset(self._by_digest[corpus])

    def is_enrolled(
        self,
        corpus: CorpusKind,
        *,
        binary_digest: Optional[str] = None,
        application_fingerprint: Optional[str] = None,
    ) -> bool:
        return self.resolve(
            corpus,
            binary_digest=binary_digest,
            application_fingerprint=application_fingerprint,
        ) is not None
