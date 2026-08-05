"""Read-only evidence queries for Runtime Intelligence — no mutation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from alma_bridge.certification.models import CertificationLevel
from alma_bridge.certification.service import CertificationService
from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.compatibility_intelligence.behavior_requirements import (
    BEHAVIOR_REGISTRY_VERSION,
    get_behavior_profile,
    list_behavior_profiles,
)
from alma_bridge.compatibility_intelligence.calibration_repository import CalibrationRepository
from alma_bridge.compatibility_intelligence.calibration_service import CalibrationService
from alma_bridge.compatibility_intelligence.expansion.repository import ExpansionPlanRepository
from alma_bridge.compatibility_intelligence.governance.models import CapabilityMaturityState
from alma_bridge.compatibility_intelligence.governance.repository import GovernanceRepository
from alma_bridge.compatibility_intelligence.models import CAPABILITY_REGISTRY_VERSION
from alma_bridge.compatibility_intelligence.repository import AnalysisRepository
from alma_bridge.evidence.models import TimelineEventType
from alma_bridge.evidence.queries import EvidenceQueries
from alma_bridge.runtime_intelligence.corpus import CorpusEnrollmentResolver, require_corpus
from alma_bridge.runtime_intelligence.family import (
    CANONICAL_FAMILIES,
    family_for_behavior,
    family_for_capability,
)
from alma_bridge.runtime_intelligence.hypotheses import (
    HYPOTHESIS_EVENT_TYPE_CREATED,
    HYPOTHESIS_EVENT_TYPE_OUTCOME_LINKED,
)
from alma_bridge.runtime_intelligence.index import (
    evidence_ratio_from_certification,
    evidence_ratio_from_maturity,
)
from alma_bridge.runtime_intelligence.knowledge import (
    qualifies_as_attributed_failure,
    qualifies_as_documented_limitation,
    qualifies_as_explained_blocker,
)
from alma_bridge.runtime_intelligence.models import (
    BehaviorFamilyId,
    CompatibilityDebtKind,
    CompatibilityDebtSignal,
    CompatibilityIndexInput,
    CompatibilityKnowledgeInput,
    CorpusEnrollmentEntry,
    CorpusKind,
    EngineeringHypothesisOutcomeLink,
    EngineeringHypothesisSnapshot,
    EvidenceRatio,
    QueryMetadata,
)


@dataclass(frozen=True)
class EnrolledArtifact:
    entry: CorpusEnrollmentEntry
    binary_digest: str
    application_fingerprint: str


def _dedupe_sorted(values: Sequence[str]) -> List[str]:
    return sorted(set(values))


def _bucket_key(timestamp: str) -> str:
    return timestamp[:10] if timestamp else "unknown"


class RuntimeIntelligenceQueries:
    """Aggregate read-only queries across evidence subsystems for Runtime Intelligence."""

    def __init__(
        self,
        *,
        corpus_resolver: Optional[CorpusEnrollmentResolver] = None,
        evidence_queries: Optional[EvidenceQueries] = None,
        analysis_repo: Optional[AnalysisRepository] = None,
        calibration_repo: Optional[CalibrationRepository] = None,
        calibration_service: Optional[CalibrationService] = None,
        governance_repo: Optional[GovernanceRepository] = None,
        certification_service: Optional[CertificationService] = None,
        expansion_repo: Optional[ExpansionPlanRepository] = None,
    ) -> None:
        self._corpus = corpus_resolver or CorpusEnrollmentResolver.from_manifest_files()
        self._evidence = evidence_queries or EvidenceQueries()
        self._analysis = analysis_repo or AnalysisRepository()
        self._calibration_repo = calibration_repo or CalibrationRepository()
        self._calibration = calibration_service or CalibrationService(self._calibration_repo)
        self._governance = governance_repo or GovernanceRepository()
        self._certification = certification_service or CertificationService.shared()
        self._expansion = expansion_repo or ExpansionPlanRepository()

    def enrolled_entries(self, corpus: CorpusKind) -> List[CorpusEnrollmentEntry]:
        require_corpus(corpus)
        return list(self._corpus.manifest_for(corpus).entries)

    def filter_enrolled_artifacts(
        self,
        corpus: CorpusKind,
        *,
        binary_digests: Sequence[str] = (),
        application_fingerprints: Sequence[str] = (),
    ) -> Tuple[List[EnrolledArtifact], int]:
        """Return manifest-enrolled artifacts; count excluded unenrolled references."""
        require_corpus(corpus)
        enrolled: List[EnrolledArtifact] = []
        seen: set[str] = set()
        excluded = 0

        for digest in binary_digests:
            entry = self._corpus.resolve_by_digest(corpus, digest)
            if entry is None:
                excluded += 1
                continue
            key = entry.entry_id
            if key not in seen:
                seen.add(key)
                enrolled.append(
                    EnrolledArtifact(
                        entry=entry,
                        binary_digest=entry.binary_digest,
                        application_fingerprint=entry.application_fingerprint,
                    )
                )

        for fingerprint in application_fingerprints:
            entry = self._corpus.resolve_by_fingerprint(corpus, fingerprint)
            if entry is None:
                excluded += 1
                continue
            key = entry.entry_id
            if key not in seen:
                seen.add(key)
                enrolled.append(
                    EnrolledArtifact(
                        entry=entry,
                        binary_digest=entry.binary_digest,
                        application_fingerprint=entry.application_fingerprint,
                    )
                )

        return enrolled, excluded

    def compute_evidence_snapshot_digest(
        self,
        corpus: CorpusKind,
        *,
        family_id: BehaviorFamilyId,
        provider_id: str,
    ) -> str:
        entries = self.enrolled_entries(corpus)
        payload: Mapping[str, object] = {
            "corpus": corpus.value,
            "family_id": family_id.value,
            "provider_id": provider_id,
            "enrolled_entry_ids": sorted(entry.entry_id for entry in entries),
        }
        return sha256_v1(payload)

    def _capabilities_for_family(self, family_id: BehaviorFamilyId) -> List[str]:
        from alma_bridge.runtime_intelligence.family import FAMILY_REGISTRY

        return sorted(
            capability_id
            for capability_id, mapped in FAMILY_REGISTRY.items()
            if mapped == family_id
        )

    def _behaviors_for_family(self, family_id: BehaviorFamilyId) -> List[str]:
        from alma_bridge.runtime_intelligence.family import BEHAVIOR_FAMILY_REGISTRY

        return sorted(
            behavior_id
            for behavior_id, mapped in BEHAVIOR_FAMILY_REGISTRY.items()
            if mapped == family_id
        )

    def _provider_version(self, provider_id: str) -> Optional[str]:
        versions: Dict[str, str] = {}
        for profile in list_behavior_profiles():
            if profile.provider_id not in versions or profile.implementation_version > versions[profile.provider_id]:
                versions[profile.provider_id] = profile.implementation_version
        return versions.get(provider_id)

    def _registry_version(self) -> str:
        try:
            return self._governance.get_current_version().version_id
        except Exception:
            return CAPABILITY_REGISTRY_VERSION

    def _verification_stats(
        self,
        corpus: CorpusKind,
        *,
        family_id: BehaviorFamilyId,
        provider_id: str,
    ) -> Tuple[int, int, List[str], int]:
        verified = 0
        total = 0
        refs: List[str] = []
        excluded = 0
        seen_sessions: set[str] = set()

        for artifact in self.enrolled_entries(corpus):
            bundle = self._evidence.by_binary_digest(artifact.binary_digest)
            if bundle is None:
                continue
            for event in self._evidence.timeline(bundle.bundle_id):
                if event.event_type != TimelineEventType.VERIFICATION_COMPLETED:
                    continue
                session_key = ":".join(sorted(event.references)) or event.event_id
                if session_key in seen_sessions:
                    continue
                seen_sessions.add(session_key)
                total += 1
                if event.metadata.get("verified"):
                    verified += 1
                refs.extend(event.references or [event.event_id])

        return verified, total, _dedupe_sorted(refs), excluded

    def _behavior_coverage_ratio(
        self,
        *,
        family_id: BehaviorFamilyId,
        provider_id: str,
        evidence_snapshot_digest: str,
    ) -> EvidenceRatio:
        behaviors = self._behaviors_for_family(family_id)
        if not behaviors:
            return EvidenceRatio(
                numerator=0,
                denominator=0,
                available=False,
                insufficient_reason="no_behaviors_mapped_for_family",
            )

        supported = 0
        total = 0
        refs: List[str] = []
        for capability_id in self._capabilities_for_family(family_id):
            profile = get_behavior_profile(capability_id, provider_id)
            if profile is None:
                continue
            for behavior_id in behaviors:
                if behavior_id not in profile.supported_behaviors and behavior_id not in profile.unsupported_behaviors:
                    continue
                total += 1
                if behavior_id in profile.supported_behaviors:
                    supported += 1
                refs.append(f"{capability_id}:{behavior_id}")

        if total == 0:
            return EvidenceRatio(
                numerator=0,
                denominator=0,
                available=False,
                insufficient_reason="provider_family_behavior_profile_unavailable",
                evidence_references=refs,
                snapshot_digest=evidence_snapshot_digest,
            )

        return EvidenceRatio(
            numerator=supported,
            denominator=total,
            evidence_references=refs,
            snapshot_digest=evidence_snapshot_digest,
        )

    def _calibration_accuracy_ratio(
        self,
        corpus: CorpusKind,
        *,
        family_id: BehaviorFamilyId,
        provider_id: str,
        evidence_snapshot_digest: str,
    ) -> EvidenceRatio:
        records = self._calibration.list_records(limit=500)
        correct = 0
        total = 0
        refs: List[str] = []
        excluded = 0

        for record in records:
            if record.get("provider_id") != provider_id:
                continue
            cap = record.get("capability_id", "")
            if family_for_capability(cap) != family_id:
                continue
            fp = record.get("application_fingerprint") or record.get("binary_digest", "")
            if fp and not self._corpus.is_enrolled(
                corpus,
                binary_digest=record.get("binary_digest"),
                application_fingerprint=record.get("application_fingerprint"),
            ):
                excluded += 1
                continue
            classification = record.get("classification", "")
            if classification in ("indeterminate", ""):
                continue
            total += 1
            if classification in ("true_positive", "true_negative"):
                correct += 1
            refs.append(record.get("record_id", record.get("calibration_id", "")))

        if total == 0:
            return EvidenceRatio(
                numerator=0,
                denominator=0,
                available=False,
                insufficient_reason="no_scoped_calibration_records",
                evidence_references=_dedupe_sorted(refs),
                snapshot_digest=evidence_snapshot_digest,
            )

        return EvidenceRatio(
            numerator=correct,
            denominator=total,
            evidence_references=_dedupe_sorted(refs),
            snapshot_digest=evidence_snapshot_digest,
        )

    def _governance_maturity_ratio(
        self,
        *,
        family_id: BehaviorFamilyId,
        provider_id: str,
        evidence_snapshot_digest: str,
    ) -> EvidenceRatio:
        try:
            version = self._governance.get_current_version()
        except Exception:
            return EvidenceRatio(
                numerator=0,
                denominator=0,
                available=False,
                insufficient_reason="governance_registry_unavailable",
                snapshot_digest=evidence_snapshot_digest,
            )

        states: List[CapabilityMaturityState] = []
        refs: List[str] = []
        for capability_id in self._capabilities_for_family(family_id):
            entry = next(
                (e for e in version.entries if e.scope.capability_id == capability_id),
                None,
            )
            if entry is None:
                continue
            if entry.scope.provider_id != provider_id:
                continue
            states.append(entry.maturity_state)
            refs.append(entry.scope.capability_id)

        if not states:
            return EvidenceRatio(
                numerator=0,
                denominator=0,
                available=False,
                insufficient_reason="no_governance_entries_for_scope",
                evidence_references=refs,
                snapshot_digest=evidence_snapshot_digest,
            )

        normalized = [evidence_ratio_from_maturity(state) for state in states]
        avg = sum(r.value or 0.0 for r in normalized) / len(normalized)
        return EvidenceRatio(
            numerator=int(round(avg * len(normalized))),
            denominator=len(normalized),
            value=round(avg, 4),
            evidence_references=refs,
            snapshot_digest=evidence_snapshot_digest,
        )

    def _certification_level_ratio(
        self,
        *,
        family_id: BehaviorFamilyId,
        provider_id: str,
        evidence_snapshot_digest: str,
    ) -> EvidenceRatio:
        behaviors = self._behaviors_for_family(family_id)
        if not behaviors:
            return EvidenceRatio(
                numerator=0,
                denominator=0,
                available=False,
                insufficient_reason="no_behaviors_for_certification_scope",
                snapshot_digest=evidence_snapshot_digest,
            )

        levels: List[CertificationLevel] = []
        refs: List[str] = []
        for capability_id in self._capabilities_for_family(family_id):
            for behavior_id in behaviors:
                try:
                    cert = self._certification.get_behavior_certification(capability_id, behavior_id)
                except Exception:
                    continue
                if cert.provider_id and cert.provider_id != provider_id:
                    continue
                levels.append(cert.certification_level)
                refs.append(f"{capability_id}:{behavior_id}")

        if not levels:
            return EvidenceRatio(
                numerator=0,
                denominator=0,
                available=False,
                insufficient_reason="no_certification_records_for_scope",
                evidence_references=refs,
                snapshot_digest=evidence_snapshot_digest,
            )

        available_levels = [level for level in levels if level != CertificationLevel.REQUIRES_REVALIDATION]
        if not available_levels:
            return evidence_ratio_from_certification(
                CertificationLevel.REQUIRES_REVALIDATION,
                evidence_references=refs,
                snapshot_digest=evidence_snapshot_digest,
            )

        ratios = [
            evidence_ratio_from_certification(level, evidence_references=refs, snapshot_digest=evidence_snapshot_digest)
            for level in available_levels
        ]
        usable = [r for r in ratios if r.available and r.value is not None]
        if not usable:
            return EvidenceRatio(
                numerator=0,
                denominator=0,
                available=False,
                insufficient_reason="certification_unavailable_for_scope",
                evidence_references=refs,
                snapshot_digest=evidence_snapshot_digest,
            )
        avg = sum(r.value or 0.0 for r in usable) / len(usable)
        return EvidenceRatio(
            numerator=int(round(avg * len(usable))),
            denominator=len(usable),
            value=round(avg, 4),
            evidence_references=refs,
            snapshot_digest=evidence_snapshot_digest,
        )

    def build_index_input(
        self,
        corpus: CorpusKind,
        family_id: BehaviorFamilyId,
        provider_id: str,
        evidence_snapshot_digest: str,
    ) -> Tuple[CompatibilityIndexInput, QueryMetadata]:
        require_corpus(corpus)
        limitations: List[str] = []
        excluded = 0

        verified, total, ver_refs, ver_excluded = self._verification_stats(
            corpus, family_id=family_id, provider_id=provider_id
        )
        excluded += ver_excluded
        if total == 0:
            auth_ratio = EvidenceRatio(
                numerator=0,
                denominator=0,
                available=False,
                insufficient_reason="no_authoritative_verification_outcomes",
                snapshot_digest=evidence_snapshot_digest,
            )
            limitations.append("authoritative_verification_unavailable")
        else:
            auth_ratio = EvidenceRatio(
                numerator=verified,
                denominator=total,
                evidence_references=ver_refs,
                snapshot_digest=evidence_snapshot_digest,
            )

        behavior_ratio = self._behavior_coverage_ratio(
            family_id=family_id,
            provider_id=provider_id,
            evidence_snapshot_digest=evidence_snapshot_digest,
        )
        if not behavior_ratio.available:
            limitations.append(behavior_ratio.insufficient_reason or "behavior_coverage_unavailable")

        calibration_ratio = self._calibration_accuracy_ratio(
            corpus,
            family_id=family_id,
            provider_id=provider_id,
            evidence_snapshot_digest=evidence_snapshot_digest,
        )
        if not calibration_ratio.available:
            limitations.append(calibration_ratio.insufficient_reason or "calibration_unavailable")

        governance_ratio = self._governance_maturity_ratio(
            family_id=family_id,
            provider_id=provider_id,
            evidence_snapshot_digest=evidence_snapshot_digest,
        )
        if not governance_ratio.available:
            limitations.append(governance_ratio.insufficient_reason or "governance_unavailable")

        certification_ratio = self._certification_level_ratio(
            family_id=family_id,
            provider_id=provider_id,
            evidence_snapshot_digest=evidence_snapshot_digest,
        )
        if not certification_ratio.available:
            limitations.append(certification_ratio.insufficient_reason or "certification_unavailable")

        input_data = CompatibilityIndexInput(
            corpus=corpus,
            family_id=family_id,
            provider_id=provider_id,
            behavior_coverage=behavior_ratio,
            authoritative_verification_rate=auth_ratio,
            calibration_accuracy=calibration_ratio,
            governance_maturity=governance_ratio,
            certification_level=certification_ratio,
            registry_version=self._registry_version(),
            provider_version=self._provider_version(provider_id),
            evidence_snapshot_digest=evidence_snapshot_digest,
            generated_from="runtime_intelligence_queries",
            limitations=sorted(set(limitations)),
        )
        return input_data, QueryMetadata(
            excluded_unenrolled_artifact_count=excluded,
            limitations=sorted(set(limitations)),
        )

    def build_knowledge_input(
        self,
        corpus: CorpusKind,
        family_id: BehaviorFamilyId,
        provider_id: str,
        evidence_snapshot_digest: str,
    ) -> Tuple[CompatibilityKnowledgeInput, QueryMetadata]:
        require_corpus(corpus)
        behaviors = self._behaviors_for_family(family_id)
        observed = len(behaviors)
        classified = 0
        explained_blockers = 0
        attributed_failures = 0
        unattributed_failures = 0
        linkage_num = 0
        linkage_den = 0
        documented_limitations = 0
        contradictory = 0
        unknown_behaviors: List[str] = []
        unknown_apis: List[str] = []
        evidence_refs: List[str] = []
        limitations_docs: List[str] = []
        excluded = 0

        for capability_id in self._capabilities_for_family(family_id):
            profile = get_behavior_profile(capability_id, provider_id)
            if profile is None:
                continue
            for behavior_id in behaviors:
                if behavior_id in profile.supported_behaviors or behavior_id in profile.unsupported_behaviors:
                    classified += 1
                else:
                    unknown_behaviors.append(behavior_id)
                if qualifies_as_explained_blocker(
                    has_bounded_classification=behavior_id in profile.unsupported_behaviors,
                    has_evidence_references=True,
                    stderr_only=False,
                ):
                    explained_blockers += 1

        for record in self._calibration.list_records(limit=500):
            if record.get("provider_id") != provider_id:
                continue
            if family_for_capability(record.get("capability_id", "")) != family_id:
                continue
            if not self._corpus.is_enrolled(
                corpus,
                binary_digest=record.get("binary_digest"),
                application_fingerprint=record.get("application_fingerprint"),
            ):
                excluded += 1
                continue
            linkage_den += 1
            if record.get("outcome_link_id"):
                linkage_num += 1
            if qualifies_as_attributed_failure(
                authoritative=record.get("classification") in ("true_positive", "false_positive", "true_negative", "false_negative"),
                attribution_category=record.get("failure_attribution"),
                has_evidence_references=bool(record.get("record_id")),
            ):
                attributed_failures += 1
            elif record.get("classification") not in ("indeterminate", ""):
                unattributed_failures += 1
            evidence_refs.append(record.get("record_id", ""))

        for analysis in self._analysis.list_recent(limit=200):
            enrolled, exc = self.filter_enrolled_artifacts(
                corpus, binary_digests=[analysis.binary_digest]
            )
            excluded += exc
            if not enrolled:
                continue
            for classification in analysis.api_classifications:
                if classification.resolution == "unknown":
                    unknown_apis.append(classification.api_name)
            if qualifies_as_documented_limitation(
                has_bounded_scope=True,
                has_unsupported_semantics=bool(analysis.prediction.limitations),
                has_profile_or_evidence_ref=True,
            ):
                documented_limitations += 1
                limitations_docs.extend(analysis.prediction.limitations)

        def _ratio(num: int, den: int, *, reason: str) -> EvidenceRatio:
            if den == 0:
                return EvidenceRatio(
                    numerator=0,
                    denominator=0,
                    available=False,
                    insufficient_reason=reason,
                    snapshot_digest=evidence_snapshot_digest,
                )
            return EvidenceRatio(
                numerator=num,
                denominator=den,
                evidence_references=_dedupe_sorted(evidence_refs),
                snapshot_digest=evidence_snapshot_digest,
            )

        input_data = CompatibilityKnowledgeInput(
            corpus=corpus,
            family_id=family_id,
            provider_id=provider_id,
            behavior_classification_coverage=_ratio(classified, observed, reason="no_observed_behaviors"),
            blocker_explanation_coverage=_ratio(explained_blockers, max(classified, 1), reason="no_classified_behaviors"),
            failure_attribution_coverage=_ratio(
                attributed_failures,
                attributed_failures + unattributed_failures,
                reason="no_attributable_failures",
            ),
            prediction_outcome_linkage_coverage=_ratio(linkage_num, linkage_den, reason="no_calibration_records"),
            limitation_documentation_coverage=_ratio(
                documented_limitations,
                max(documented_limitations, 1),
                reason="no_documented_limitations",
            ),
            contradiction_quality=EvidenceRatio(
                numerator=max(0, contradictory),
                denominator=max(contradictory, 0),
                available=contradictory > 0,
                insufficient_reason="no_contradictory_evidence_observed",
                snapshot_digest=evidence_snapshot_digest,
            ),
            observed_behavior_count=observed,
            classified_behavior_count=classified,
            explained_blocker_count=explained_blockers,
            unknown_behavior_ids=_dedupe_sorted(unknown_behaviors),
            unknown_api_names=_dedupe_sorted(unknown_apis),
            attributed_failure_count=attributed_failures,
            unattributed_failure_count=unattributed_failures,
            contradictory_evidence_count=contradictory,
            evidence_backed_limitations=_dedupe_sorted(limitations_docs),
            evidence_snapshot_digest=evidence_snapshot_digest,
            registry_version=self._registry_version(),
            provider_version=self._provider_version(provider_id),
            evidence_references=_dedupe_sorted(evidence_refs),
            limitations=["read_only_knowledge_aggregation"],
        )
        return input_data, QueryMetadata(
            excluded_unenrolled_artifact_count=excluded,
            limitations=["unenrolled_artifacts_excluded"] if excluded else [],
        )

    def build_debt_signals(
        self,
        corpus: CorpusKind,
        family_id: BehaviorFamilyId,
        provider_id: str,
        evidence_snapshot_digest: str,
    ) -> Tuple[List[CompatibilityDebtSignal], QueryMetadata]:
        require_corpus(corpus)
        signals: List[CompatibilityDebtSignal] = []
        excluded = 0
        limitations: List[str] = []

        for capability_id in self._capabilities_for_family(family_id):
            profile = get_behavior_profile(capability_id, provider_id)
            if profile is None:
                continue
            for behavior_id in profile.unsupported_behaviors:
                if family_for_behavior(behavior_id) != family_id:
                    continue
                artifacts, exc = self.filter_enrolled_artifacts(corpus, application_fingerprints=[])
                excluded += exc
                enrolled_digests = [entry.binary_digest for entry in self.enrolled_entries(corpus)]
                enrolled_fps = [entry.application_fingerprint for entry in self.enrolled_entries(corpus)]
                signals.append(
                    CompatibilityDebtSignal(
                        kind=CompatibilityDebtKind.UNSUPPORTED_BEHAVIOR,
                        corpus=corpus,
                        family_id=family_id,
                        capability_id=capability_id,
                        behavior_id=behavior_id,
                        provider_id=provider_id,
                        evidence_snapshot_digest=evidence_snapshot_digest,
                        evidence_references=[f"{capability_id}:{behavior_id}"],
                        affected_binary_digests=enrolled_digests[:1],
                        affected_application_fingerprints=enrolled_fps[:1],
                        distinct_binary_count=min(1, len(enrolled_digests)),
                        distinct_application_count=min(1, len(enrolled_fps)),
                    )
                )

        for record in self._calibration.list_records(limit=500):
            if record.get("provider_id") != provider_id:
                continue
            cap = record.get("capability_id", "")
            if family_for_capability(cap) != family_id:
                continue
            if not self._corpus.is_enrolled(
                corpus,
                binary_digest=record.get("binary_digest"),
                application_fingerprint=record.get("application_fingerprint"),
            ):
                excluded += 1
                continue
            classification = record.get("classification", "")
            kind = None
            if classification == "false_positive":
                kind = CompatibilityDebtKind.CALIBRATION_FALSE_POSITIVE
            elif classification == "false_negative":
                kind = CompatibilityDebtKind.CALIBRATION_FALSE_NEGATIVE
            if kind is None:
                continue
            fp = record.get("application_fingerprint", "")
            digest = record.get("binary_digest", "")
            signals.append(
                CompatibilityDebtSignal(
                    kind=kind,
                    corpus=corpus,
                    family_id=family_id,
                    capability_id=cap,
                    provider_id=provider_id,
                    evidence_snapshot_digest=evidence_snapshot_digest,
                    evidence_references=[record.get("record_id", "")],
                    calibration_gap_count=1,
                    affected_application_fingerprints=[fp] if fp else [],
                    affected_binary_digests=[digest] if digest else [],
                    distinct_application_count=1 if fp else 0,
                    distinct_binary_count=1 if digest else 0,
                )
            )

        for analysis in self._analysis.list_recent(limit=200):
            _, exc = self.filter_enrolled_artifacts(corpus, binary_digests=[analysis.binary_digest])
            excluded += exc
            if exc:
                continue
            for classification in analysis.api_classifications:
                if classification.resolution != "unknown":
                    continue
                cap_family = family_for_capability(classification.capability_id or "api.unknown")
                if cap_family != family_id:
                    continue
                signals.append(
                    CompatibilityDebtSignal(
                        kind=CompatibilityDebtKind.UNKNOWN_API,
                        corpus=corpus,
                        family_id=family_id,
                        capability_id=classification.capability_id or "api.unknown",
                        provider_id=provider_id,
                        evidence_snapshot_digest=evidence_snapshot_digest,
                        evidence_references=[analysis.analysis_id],
                        affected_binary_digests=[analysis.binary_digest],
                        distinct_binary_count=1,
                        distinct_application_count=1,
                    )
                )

        try:
            plan = self._expansion.get_latest_plan()
            if plan:
                for candidate in plan.excluded_candidates:
                    if candidate.exclusion_reason:
                        cap = candidate.capability_id
                        if family_for_capability(cap) != family_id:
                            continue
                        signals.append(
                            CompatibilityDebtSignal(
                                kind=CompatibilityDebtKind.ACKNOWLEDGED_OUT_OF_SCOPE,
                                corpus=corpus,
                                family_id=family_id,
                                capability_id=cap,
                                provider_id=provider_id,
                                evidence_snapshot_digest=evidence_snapshot_digest,
                                evidence_references=[candidate.candidate_id],
                                explicitly_out_of_scope=True,
                                expansion_candidate_id=candidate.candidate_id,
                            )
                        )
        except Exception:
            limitations.append("expansion_plan_unavailable")

        return signals, QueryMetadata(
            excluded_unenrolled_artifact_count=excluded,
            limitations=limitations,
        )

    def list_hypothesis_timeline_events(
        self,
        corpus: CorpusKind,
    ) -> Tuple[List[EngineeringHypothesisSnapshot], List[EngineeringHypothesisOutcomeLink]]:
        require_corpus(corpus)
        snapshots: Dict[str, EngineeringHypothesisSnapshot] = {}
        links: List[EngineeringHypothesisOutcomeLink] = []

        for bundle_id in self._evidence.list_bundle_ids():
            for event in self._evidence.timeline(bundle_id):
                metadata = event.metadata or {}
                if event.event_type in (
                    TimelineEventType.ENGINEERING_HYPOTHESIS_CREATED,
                ) or event.event_type.value == HYPOTHESIS_EVENT_TYPE_CREATED:
                    if metadata.get("corpus") != corpus.value:
                        continue
                    snapshot = self._snapshot_from_event_metadata(metadata)
                    if snapshot:
                        snapshots[snapshot.hypothesis_id] = snapshot
                elif event.event_type in (
                    TimelineEventType.ENGINEERING_HYPOTHESIS_OUTCOME_LINKED,
                ) or event.event_type.value == HYPOTHESIS_EVENT_TYPE_OUTCOME_LINKED:
                    link = self._link_from_event_metadata(metadata)
                    if link:
                        links.append(link)

        return list(snapshots.values()), links

    @staticmethod
    def _snapshot_from_event_metadata(metadata: Mapping[str, object]) -> Optional[EngineeringHypothesisSnapshot]:
        hypothesis_id = metadata.get("hypothesis_id")
        if not hypothesis_id:
            return None
        try:
            return EngineeringHypothesisSnapshot(
                hypothesis_id=str(hypothesis_id),
                created_at=str(metadata.get("created_at", "")),
                corpus=CorpusKind(str(metadata.get("corpus", CorpusKind.ENGINEERING.value))),
                provider_id=str(metadata.get("provider_id", "")),
                provider_version_scope=str(metadata.get("provider_version_scope", "")),
                family_id=BehaviorFamilyId(str(metadata.get("family_id", BehaviorFamilyId.FILESYSTEM.value))),
                capability_id=str(metadata.get("capability_id", "")),
                bounded_scope=str(metadata.get("bounded_scope", "")),
                evidence_snapshot_digest=str(metadata.get("evidence_snapshot_digest", "")),
                snapshot_digest=str(metadata.get("snapshot_digest", "")),
                schema_version=str(metadata.get("schema_version", "")),
                formula_version=str(metadata.get("formula_version", "")),
                behavior_id=str(metadata.get("behavior_id")) if metadata.get("behavior_id") else None,
                evidence_references=tuple(metadata.get("evidence_references") or ()),
            )
        except Exception:
            return None

    @staticmethod
    def _link_from_event_metadata(metadata: Mapping[str, object]) -> Optional[EngineeringHypothesisOutcomeLink]:
        outcome_link_id = metadata.get("outcome_link_id")
        hypothesis_id = metadata.get("hypothesis_id")
        if not outcome_link_id or not hypothesis_id:
            return None
        try:
            return EngineeringHypothesisOutcomeLink(
                outcome_link_id=str(outcome_link_id),
                hypothesis_id=str(hypothesis_id),
                linked_at=str(metadata.get("linked_at", "")),
                evidence_snapshot_digest=str(metadata.get("evidence_snapshot_digest", "")),
                link_digest=str(metadata.get("link_digest", "")),
                schema_version=str(metadata.get("schema_version", "")),
                observed_verified_successes=int(metadata.get("observed_verified_successes", 0)),
                observed_verified_failures=int(metadata.get("observed_verified_failures", 0)),
                authoritative_outcome_references=tuple(metadata.get("authoritative_outcome_references") or ()),
                evidence_references=tuple(metadata.get("evidence_references") or ()),
            )
        except Exception:
            return None

    def build_hypothesis_snapshot_inputs(
        self,
        corpus: CorpusKind,
        *,
        family_id: Optional[BehaviorFamilyId] = None,
    ) -> Tuple[List[EngineeringHypothesisSnapshot], QueryMetadata]:
        snapshots, _ = self.list_hypothesis_timeline_events(corpus)
        if family_id is not None:
            snapshots = [snap for snap in snapshots if snap.family_id == family_id]
        return snapshots, QueryMetadata()

    def build_hypothesis_outcome_links(
        self,
        corpus: CorpusKind,
        *,
        hypothesis_id: Optional[str] = None,
    ) -> Tuple[List[EngineeringHypothesisOutcomeLink], QueryMetadata]:
        snapshots, links = self.list_hypothesis_timeline_events(corpus)
        snapshot_ids = {snap.hypothesis_id for snap in snapshots}
        scoped = [link for link in links if link.hypothesis_id in snapshot_ids]
        if hypothesis_id is not None:
            scoped = [link for link in scoped if link.hypothesis_id == hypothesis_id]
        return scoped, QueryMetadata()
