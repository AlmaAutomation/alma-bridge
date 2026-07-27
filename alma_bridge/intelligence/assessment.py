"""Deterministic compatibility assessment from evidence bundles."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from alma_bridge.intelligence.confidence import ConfidencePolicy
from alma_bridge.intelligence.models import (
    CompatibilityAssessment,
    CompatibilityFact,
    CompatibilityHypothesis,
    EvidenceBundle,
    EvidenceReference,
    EvidenceSourceType,
    FactKind,
    FactStatus,
    HypothesisStatus,
)


ENGINE_VERSION = "compatibility_intelligence_v1"


class CompatibilityAssessmentEngine:
    """Conservative, deterministic rules for labeling facts and hypotheses."""

    engine_version = ENGINE_VERSION

    def __init__(self, confidence_policy: Optional[ConfidencePolicy] = None) -> None:
        self._confidence = confidence_policy or ConfidencePolicy()

    def assess(self, bundle: EvidenceBundle) -> CompatibilityAssessment:
        facts: List[CompatibilityFact] = []
        hypotheses: List[CompatibilityHypothesis] = []
        limitations = list(bundle.limitations)

        winning = self._select_winning_attempt(bundle)
        verified_launch, launch_refs = self._verified_launch(bundle, winning)
        if verified_launch:
            facts.append(
                CompatibilityFact(
                    fact_id="fact:verified_successful_launch",
                    kind=FactKind.VERIFIED_SUCCESSFUL_LAUNCH,
                    status=FactStatus.PROVEN,
                    statement="Application launch verified by aggregate verification policy pass.",
                    provenance=launch_refs,
                    confidence=float((winning or {}).get("verification_confidence") or 0.9),
                )
            )
        elif winning and (winning.get("exit_code") == 0 or winning.get("attempt_success")):
            limitations.append(
                "Attempt reported success or exit_code zero without verification aggregate pass; "
                "verified_successful_launch not proven."
            )

        framework, framework_refs = self._observed_framework(bundle)
        if framework:
            facts.append(
                CompatibilityFact(
                    fact_id=f"fact:uses_framework:{framework}",
                    kind=FactKind.USES_FRAMEWORK,
                    status=FactStatus.OBSERVED,
                    statement=f"Framework {framework} observed from persisted detection artifacts.",
                    provenance=framework_refs,
                    confidence=0.75,
                    attributes={"framework": framework},
                )
            )

        if verified_launch and winning and winning.get("strategy_id"):
            facts.append(
                CompatibilityFact(
                    fact_id=f"fact:verified_with_strategy:{winning['strategy_id']}",
                    kind=FactKind.VERIFIED_WITH_STRATEGY,
                    status=FactStatus.PROVEN,
                    statement=(
                        f"Verified launch achieved with strategy {winning['strategy_id']}."
                    ),
                    provenance=launch_refs,
                    confidence=float((winning or {}).get("verification_confidence") or 0.85),
                    attributes={"strategy_id": winning["strategy_id"]},
                )
            )

        runtime_hypothesis = self._runtime_requirement_hypothesis(bundle, verified_launch)
        if runtime_hypothesis:
            hypotheses.append(runtime_hypothesis)

        shadow_refs = [
            ref
            for ref in bundle.references
            if ref.source_type == EvidenceSourceType.SHADOW_COMPARISON
        ]
        if shadow_refs:
            limitations.append(
                "Shadow prediction/comparison artifacts present; shadow outputs are not proven facts."
            )

        conflict = self._conflicting_evidence(bundle, winning, verified_launch)
        if conflict:
            facts.append(conflict)

        confidence = self._confidence.summarize(facts, hypotheses)
        return CompatibilityAssessment(
            engine_version=self.engine_version,
            session_id=bundle.session_id,
            application_fingerprint=bundle.application_fingerprint,
            facts=facts,
            hypotheses=hypotheses,
            confidence=confidence,
            limitations=limitations,
        )

    def _select_winning_attempt(self, bundle: EvidenceBundle) -> Optional[Dict[str, Any]]:
        candidates: List[Dict[str, Any]] = []
        for key, artifact in bundle.artifacts.items():
            if not key.startswith("attempt:"):
                continue
            parts = key.split(":")
            if len(parts) != 3:
                continue
            session_id, attempt_number = parts[1], int(parts[2])
            verification_key = f"verification:{session_id}:{attempt_number}"
            verification = bundle.artifacts.get(verification_key) or {}
            candidates.append(
                {
                    "session_id": session_id,
                    "attempt_number": attempt_number,
                    "strategy_id": artifact.get("strategy_id"),
                    "phase": artifact.get("phase"),
                    "exit_code": artifact.get("exit_code"),
                    "attempt_success": bool(artifact.get("success")),
                    "verification": verification,
                    "verification_confidence": verification.get("confidence"),
                }
            )

        for session in bundle.artifacts.get("sessions") or []:
            if not session.get("success"):
                continue
            for attempt in session.get("attempts") or []:
                if not attempt.get("success"):
                    continue
                session_id = session["session_id"]
                attempt_number = int(attempt["attempt_number"])
                if any(
                    c["session_id"] == session_id and c["attempt_number"] == attempt_number
                    for c in candidates
                ):
                    continue
                verification_key = f"verification:{session_id}:{attempt_number}"
                verification = bundle.artifacts.get(verification_key) or {}
                candidates.append(
                    {
                        "session_id": session_id,
                        "attempt_number": attempt_number,
                        "strategy_id": attempt.get("strategy_id"),
                        "phase": attempt.get("phase"),
                        "exit_code": attempt.get("exit_code"),
                        "attempt_success": True,
                        "verification": verification,
                        "verification_confidence": verification.get("confidence"),
                    }
                )

        if not candidates:
            return None

        def _sort_key(item: Dict[str, Any]) -> Tuple[int, int, str, int]:
            verified = 1 if self._verification_passed(item.get("verification") or {}) else 0
            return (verified, int(item.get("attempt_success") or False), item["session_id"], -item["attempt_number"])

        return sorted(candidates, key=_sort_key, reverse=True)[0]

    def _verification_passed(self, verification: Dict[str, Any]) -> bool:
        return bool(verification.get("passed"))

    def _verified_launch(
        self,
        bundle: EvidenceBundle,
        winning: Optional[Dict[str, Any]],
    ) -> Tuple[bool, List[EvidenceReference]]:
        if not winning:
            return False, []
        verification = winning.get("verification") or {}
        if not self._verification_passed(verification):
            return False, []

        refs = [
            ref
            for ref in bundle.references
            if ref.source_type == EvidenceSourceType.VERIFICATION
            and ref.source_id
            == f"{winning['session_id']}:{winning['attempt_number']}"
        ]
        if not refs:
            return False, []
        return True, refs

    def _observed_framework(
        self,
        bundle: EvidenceBundle,
    ) -> Tuple[Optional[str], List[EvidenceReference]]:
        framework: Optional[str] = None
        refs: List[EvidenceReference] = []
        for ref in bundle.references:
            if ref.source_type != EvidenceSourceType.FRAMEWORK_DETECTION:
                continue
            artifact = bundle.artifacts.get(ref.artifact_key) or {}
            candidate = str(artifact.get("framework") or "").strip().lower()
            if candidate:
                framework = candidate
                refs.append(ref)
        return framework, refs

    def _runtime_requirement_hypothesis(
        self,
        bundle: EvidenceBundle,
        verified_launch: bool,
    ) -> Optional[CompatibilityHypothesis]:
        supporting: List[EvidenceReference] = []
        contradicting: List[EvidenceReference] = []
        notes: List[str] = []

        for key, artifact in bundle.artifacts.items():
            if not key.startswith("attempt:"):
                continue
            stderr = (artifact.get("stderr_excerpt") or "").lower()
            if "visual c++" in stderr or "vcrun" in stderr or "msvcp" in stderr:
                parts = key.split(":")
                ref = EvidenceReference(
                    source_type=EvidenceSourceType.ATTEMPT,
                    source_id=f"{parts[1]}:{parts[2]}",
                    artifact_key=key,
                    excerpt="runtime_signal_in_stderr",
                )
                if verified_launch and (
                    "compiler" in stderr or "added compiler" in stderr
                ):
                    contradicting.append(ref)
                    notes.append(
                        "Visual C++ strings in startup log may reflect compiler inventory, not missing runtime."
                    )
                else:
                    supporting.append(ref)

        if verified_launch:
            return CompatibilityHypothesis(
                hypothesis_id="hypothesis:runtime_requirements",
                question="Which Windows runtime packages are required for reliable launch?",
                status=HypothesisStatus.OPEN,
                supporting_evidence=supporting,
                contradicting_evidence=contradicting,
                notes=notes or [
                    "Verified launch observed; exact runtime dependency set remains unresolved."
                ],
            )

        if not supporting and not contradicting:
            return None

        status = HypothesisStatus.OPEN
        if contradicting and not supporting:
            status = HypothesisStatus.REFUTED
        elif supporting and not contradicting:
            status = HypothesisStatus.SUPPORTED

        return CompatibilityHypothesis(
            hypothesis_id="hypothesis:runtime_requirements",
            question="Does this application require additional Windows runtime packages beyond the verified launch environment?",
            status=status,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            notes=notes,
        )

    def _conflicting_evidence(
        self,
        bundle: EvidenceBundle,
        winning: Optional[Dict[str, Any]],
        verified_launch: bool,
    ) -> Optional[CompatibilityFact]:
        if not winning:
            return None

        session_success = any(bool(s.get("success")) for s in bundle.artifacts.get("sessions") or [])
        attempt_success = bool(winning.get("attempt_success"))
        verification = winning.get("verification") or {}
        verification_passed = self._verification_passed(verification)

        conflicts: List[str] = []
        if attempt_success and not verification_passed:
            conflicts.append("attempt_success_without_verification_pass")
        if session_success and not verification_passed:
            conflicts.append("session_success_without_verification_pass")
        if verification_passed and not session_success:
            conflicts.append("verification_pass_without_session_success")
        if winning.get("exit_code") == 0 and not verification_passed:
            conflicts.append("exit_code_zero_without_verification_pass")

        if not conflicts:
            return None

        refs = [
            ref
            for ref in bundle.references
            if ref.source_type
            in (EvidenceSourceType.VERIFICATION, EvidenceSourceType.SESSION, EvidenceSourceType.ATTEMPT)
        ][:3]
        if not refs:
            return None

        return CompatibilityFact(
            fact_id="fact:conflicting_evidence",
            kind=FactKind.CONFLICTING_EVIDENCE,
            status=FactStatus.OBSERVED,
            statement="Persisted success signals disagree with verification authority.",
            provenance=refs,
            confidence=0.6,
            attributes={"conflicts": sorted(conflicts)},
        )
