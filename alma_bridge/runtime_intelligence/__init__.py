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
from alma_bridge.runtime_intelligence.index import (
    CERTIFICATION_LEVEL_NORMALIZATION_V1,
    COMPATIBILITY_INDEX_WEIGHTS_V1,
    GOVERNANCE_MATURITY_NORMALIZATION_V1,
    compute_compatibility_index,
    compute_report_digest,
    evidence_ratio_from_certification,
    evidence_ratio_from_maturity,
    normalize_certification_level,
    normalize_governance_maturity,
)
from alma_bridge.runtime_intelligence.models import (
    BehaviorFamilyId,
    BehaviorFamilyMapping,
    CanonicalFamily,
    CompatibilityIndexComponent,
    CompatibilityIndexInput,
    CompatibilityIndexReport,
    CompatibilityIndexStatus,
    CorpusEnrollmentEntry,
    CorpusKind,
    CorpusManifest,
    EvidenceRatio,
)

__all__ = [
    "BehaviorFamilyId",
    "BehaviorFamilyMapping",
    "CanonicalFamily",
    "CERTIFICATION_LEVEL_NORMALIZATION_V1",
    "COMPATIBILITY_INDEX_WEIGHTS_V1",
    "CompatibilityIndexComponent",
    "CompatibilityIndexInput",
    "CompatibilityIndexReport",
    "CompatibilityIndexStatus",
    "CorpusEnrollmentEntry",
    "CorpusEnrollmentResolver",
    "CorpusKind",
    "CorpusManifest",
    "CorpusResolutionError",
    "EvidenceRatio",
    "GOVERNANCE_MATURITY_NORMALIZATION_V1",
    "compute_compatibility_index",
    "compute_report_digest",
    "evidence_ratio_from_certification",
    "evidence_ratio_from_maturity",
    "family_for_behavior",
    "family_for_capability",
    "list_families",
    "load_corpus_manifest",
    "normalize_certification_level",
    "normalize_governance_maturity",
    "require_corpus",
]
