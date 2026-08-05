"""Shared fixtures for Runtime Intelligence tests."""

from __future__ import annotations

import pytest

from alma_bridge.runtime_intelligence.corpus import CorpusEnrollmentResolver
from alma_bridge.runtime_intelligence.models import CorpusKind


@pytest.fixture
def corpus_resolver() -> CorpusEnrollmentResolver:
    return CorpusEnrollmentResolver.from_manifest_files()


@pytest.fixture
def engineering_hello64_digest() -> str:
    return "1cf6ffffdd39d9dd4db69711e43aca370455c1e007bcb970e60b966128f3835b"


@pytest.fixture
def engineering_hello64_fingerprint() -> str:
    return "d87ac1f8a7c5bd11ffa5ccb00cf18d77edd5ce075a5b37835770e32feca15aaf"


@pytest.fixture
def engineering_corpus() -> CorpusKind:
    return CorpusKind.ENGINEERING


@pytest.fixture
def real_world_corpus() -> CorpusKind:
    return CorpusKind.REAL_WORLD
