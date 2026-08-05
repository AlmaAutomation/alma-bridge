"""Corpus separation tests for Runtime Intelligence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from alma_bridge.runtime_intelligence.corpus import (
    CorpusEnrollmentResolver,
    CorpusResolutionError,
    load_corpus_manifest,
    require_corpus,
)
from alma_bridge.runtime_intelligence.models import (
    CorpusKind,
    compute_manifest_digest,
)

ROOT = Path(__file__).resolve().parents[2]
NATIVE_RUNTIME_MANIFEST = ROOT / "tests" / "fixtures" / "native_runtime" / "manifest.json"


class TestCorpusManifestLoading:
    def test_engineering_manifest_loads_with_valid_digest(self):
        manifest = load_corpus_manifest(CorpusKind.ENGINEERING)
        assert manifest.corpus == CorpusKind.ENGINEERING
        assert len(manifest.entries) == 17
        assert manifest.digest == compute_manifest_digest(manifest.entries)

    def test_real_world_manifest_loads_empty_entries(self):
        manifest = load_corpus_manifest(CorpusKind.REAL_WORLD)
        assert manifest.corpus == CorpusKind.REAL_WORLD
        assert manifest.entries == []
        assert manifest.digest == compute_manifest_digest([])

    def test_engineering_manifest_seeded_from_native_runtime_fixtures(self):
        native = json.loads(NATIVE_RUNTIME_MANIFEST.read_text(encoding="utf-8"))
        manifest = load_corpus_manifest(CorpusKind.ENGINEERING)
        enrolled_digests = {entry.binary_digest for entry in manifest.entries}
        assert enrolled_digests == set(native["fixtures"])

    def test_manifest_rejects_digest_mismatch(self):
        manifest = load_corpus_manifest(CorpusKind.ENGINEERING)
        tampered = manifest.model_copy(update={"digest": "0" * 64})
        with pytest.raises(CorpusResolutionError, match="digest mismatch"):
            expected = compute_manifest_digest(tampered.entries)
            if tampered.digest != expected:
                raise CorpusResolutionError("manifest digest mismatch")


class TestCorpusSeparation:
    def test_require_corpus_rejects_none(self):
        with pytest.raises(CorpusResolutionError, match="explicit corpus is required"):
            require_corpus(None)

    def test_engineering_enrollment_not_visible_in_real_world(
        self,
        corpus_resolver: CorpusEnrollmentResolver,
        engineering_hello64_digest: str,
        engineering_hello64_fingerprint: str,
    ):
        assert corpus_resolver.is_enrolled(
            CorpusKind.ENGINEERING,
            binary_digest=engineering_hello64_digest,
        )
        assert not corpus_resolver.is_enrolled(
            CorpusKind.REAL_WORLD,
            binary_digest=engineering_hello64_digest,
        )
        assert not corpus_resolver.is_enrolled(
            CorpusKind.REAL_WORLD,
            application_fingerprint=engineering_hello64_fingerprint,
        )

    def test_resolve_requires_lookup_key(self, corpus_resolver: CorpusEnrollmentResolver):
        with pytest.raises(CorpusResolutionError, match="binary_digest or application_fingerprint"):
            corpus_resolver.resolve(CorpusKind.ENGINEERING)

    def test_corpora_never_share_enrollment_sets(self, corpus_resolver: CorpusEnrollmentResolver):
        engineering_digests = corpus_resolver.enrolled_digests(CorpusKind.ENGINEERING)
        real_world_digests = corpus_resolver.enrolled_digests(CorpusKind.REAL_WORLD)
        assert engineering_digests.isdisjoint(real_world_digests)
        assert len(engineering_digests) == 17
        assert len(real_world_digests) == 0

    def test_resolve_by_digest_and_fingerprint_agree(
        self,
        corpus_resolver: CorpusEnrollmentResolver,
        engineering_hello64_digest: str,
        engineering_hello64_fingerprint: str,
    ):
        by_digest = corpus_resolver.resolve(
            CorpusKind.ENGINEERING,
            binary_digest=engineering_hello64_digest,
        )
        by_fingerprint = corpus_resolver.resolve(
            CorpusKind.ENGINEERING,
            application_fingerprint=engineering_hello64_fingerprint,
        )
        assert by_digest is not None
        assert by_fingerprint is not None
        assert by_digest.entry_id == by_fingerprint.entry_id

    def test_corpus_kind_has_no_combined_value(self):
        assert {member.value for member in CorpusKind} == {"engineering", "real_world"}
