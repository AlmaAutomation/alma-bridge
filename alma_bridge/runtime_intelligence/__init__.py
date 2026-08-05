"""Read-only Runtime Intelligence foundations."""

from alma_bridge.runtime_intelligence.corpus import (
    CorpusEnrollmentResolver,
    CorpusResolutionError,
    load_corpus_manifest,
    require_corpus,
)
from alma_bridge.runtime_intelligence.family import (
    family_for_behavior,
    family_for_capability,
    list_families,
)
from alma_bridge.runtime_intelligence.models import (
    BehaviorFamilyId,
    BehaviorFamilyMapping,
    CanonicalFamily,
    CorpusEnrollmentEntry,
    CorpusKind,
    CorpusManifest,
)

__all__ = [
    "BehaviorFamilyId",
    "BehaviorFamilyMapping",
    "CanonicalFamily",
    "CorpusEnrollmentEntry",
    "CorpusEnrollmentResolver",
    "CorpusKind",
    "CorpusManifest",
    "CorpusResolutionError",
    "family_for_behavior",
    "family_for_capability",
    "list_families",
    "load_corpus_manifest",
    "require_corpus",
]
