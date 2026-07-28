"""Read-only evidence bundle construction from persisted bridge artifacts."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from alma_bridge.intelligence.models import (
    EvidenceBundle,
    EvidenceReference,
    EvidenceSourceType,
    IntelligenceNotFoundError,
    MalformedEvidenceError,
)
from alma_bridge.intelligence.repository import CompatibilityEvidenceRepository


class EvidenceBundleBuilder:
    """Assemble versioned evidence bundles without writes or subprocess side effects."""

    def __init__(self, repository: CompatibilityEvidenceRepository) -> None:
        self._repository = repository

    def for_session(self, session_id: str) -> EvidenceBundle:
        session = self._repository.get_session_record(session_id)
        if not session:
            raise IntelligenceNotFoundError(f"no session evidence for {session_id}")
        return self._build_from_sessions([session], primary_session_id=session_id)

    def for_application(self, fingerprint: str) -> EvidenceBundle:
        sessions = self._repository.list_sessions_for_fingerprint(fingerprint)
        if not sessions:
            raise IntelligenceNotFoundError(f"no application evidence for fingerprint {fingerprint}")
        return self._build_from_sessions(sessions, application_fingerprint=fingerprint)

    def _build_from_sessions(
        self,
        sessions: List[Dict[str, Any]],
        *,
        primary_session_id: Optional[str] = None,
        application_fingerprint: Optional[str] = None,
    ) -> EvidenceBundle:
        references: List[EvidenceReference] = []
        artifacts: Dict[str, Any] = {"sessions": []}
        limitations: List[str] = []
        file_path: Optional[str] = None
        fingerprint = application_fingerprint

        for session in sorted(sessions, key=lambda item: str(item.get("started_at") or "")):
            session_id = str(session["session_id"])
            file_path = file_path or session.get("file_path")
            fingerprint = fingerprint or session.get("file_hash")
            session_artifact = {
                "session_id": session_id,
                "file_path": session.get("file_path"),
                "file_hash": session.get("file_hash"),
                "success": bool(session.get("success")),
                "started_at": session.get("started_at"),
                "finished_at": session.get("finished_at"),
                "summary": session.get("summary"),
                "attempts": [],
            }
            references.append(
                EvidenceReference(
                    source_type=EvidenceSourceType.SESSION,
                    source_id=session_id,
                    artifact_key="session_record",
                    captured_at=session.get("finished_at") or session.get("started_at"),
                )
            )

            inspection = self._load_json_field(session, "inspection_json", session_id)
            if inspection:
                key = f"inspection:{session_id}"
                artifacts[key] = inspection
                references.append(
                    EvidenceReference(
                        source_type=EvidenceSourceType.INSPECTION,
                        source_id=session_id,
                        artifact_key=key,
                        captured_at=session.get("started_at"),
                    )
                )

            for attempt in session.get("attempts") or []:
                attempt_number = int(attempt["attempt_number"])
                attempt_key = f"attempt:{session_id}:{attempt_number}"
                session_artifact["attempts"].append(
                    {
                        "attempt_number": attempt_number,
                        "strategy_id": attempt.get("strategy_id"),
                        "phase": attempt.get("phase"),
                        "success": bool(attempt.get("success")),
                        "exit_code": attempt.get("exit_code"),
                    }
                )
                references.append(
                    EvidenceReference(
                        source_type=EvidenceSourceType.ATTEMPT,
                        source_id=f"{session_id}:{attempt_number}",
                        artifact_key=attempt_key,
                        captured_at=attempt.get("created_at"),
                    )
                )
                artifacts[attempt_key] = {
                    "strategy_id": attempt.get("strategy_id"),
                    "phase": attempt.get("phase"),
                    "runtime": attempt.get("runtime"),
                    "success": bool(attempt.get("success")),
                    "exit_code": attempt.get("exit_code"),
                    "stderr_excerpt": (attempt.get("stderr") or "")[:500],
                    "stdout_excerpt": (attempt.get("stdout") or "")[:500],
                }

                verification = attempt.get("verification") or {}
                if verification:
                    vkey = f"verification:{session_id}:{attempt_number}"
                    artifacts[vkey] = verification
                    references.append(
                        EvidenceReference(
                            source_type=EvidenceSourceType.VERIFICATION,
                            source_id=f"{session_id}:{attempt_number}",
                            artifact_key=vkey,
                            captured_at=attempt.get("created_at"),
                        )
                    )

                framework = self._framework_from_attempt(attempt, session_id, attempt_number)
                if framework:
                    fkey = f"framework_detection:{session_id}:{attempt_number}"
                    artifacts[fkey] = framework
                    references.append(
                        EvidenceReference(
                            source_type=EvidenceSourceType.FRAMEWORK_DETECTION,
                            source_id=f"{session_id}:{attempt_number}",
                            artifact_key=fkey,
                            captured_at=attempt.get("created_at"),
                            excerpt=str(framework.get("framework")),
                        )
                    )

                candidate = self._repository.get_profile_candidate_for_attempt(
                    session_id,
                    attempt_number,
                )
                if candidate is not None:
                    manifest = getattr(candidate, "bridge_manifest", None) or {}
                    if manifest:
                        mkey = f"manifest_capture:{session_id}:{attempt_number}"
                        artifacts[mkey] = manifest
                        references.append(
                            EvidenceReference(
                                source_type=EvidenceSourceType.MANIFEST_CAPTURE,
                                source_id=f"{session_id}:{attempt_number}",
                                artifact_key=mkey,
                                captured_at=attempt.get("created_at"),
                            )
                        )

            shadow_prediction = self._repository.get_shadow_prediction(session_id)
            if shadow_prediction:
                pkey = f"shadow_prediction:{session_id}"
                artifacts[pkey] = shadow_prediction
                references.append(
                    EvidenceReference(
                        source_type=EvidenceSourceType.SHADOW_COMPARISON,
                        source_id=session_id,
                        artifact_key=pkey,
                        captured_at=shadow_prediction.get("created_at"),
                        excerpt="shadow_prediction",
                    )
                )
                shadow_event_id = shadow_prediction.get("shadow_event_id")
                if shadow_event_id:
                    candidates = self._repository.get_shadow_candidates(str(shadow_event_id))
                    if candidates:
                        artifacts[f"shadow_candidates:{session_id}"] = candidates

            comparison = self._repository.get_shadow_comparison(session_id)
            if comparison:
                ckey = f"shadow_comparison:{session_id}"
                artifacts[ckey] = comparison
                references.append(
                    EvidenceReference(
                        source_type=EvidenceSourceType.SHADOW_COMPARISON,
                        source_id=session_id,
                        artifact_key=ckey,
                        captured_at=comparison.get("created_at"),
                        excerpt="shadow_comparison",
                    )
                )

            artifacts["sessions"].append(session_artifact)

        if not references:
            raise IntelligenceNotFoundError("evidence bundle contains no references")

        return EvidenceBundle(
            session_id=primary_session_id,
            application_fingerprint=fingerprint,
            file_path=file_path,
            references=references,
            artifacts=artifacts,
            limitations=limitations,
        )

    def _load_json_field(
        self,
        session: Dict[str, Any],
        field: str,
        session_id: str,
    ) -> Optional[Dict[str, Any]]:
        raw = session.get(field)
        if raw is None:
            return None
        if isinstance(raw, dict):
            return raw
        if isinstance(raw, str):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise MalformedEvidenceError(
                    f"malformed {field} for session {session_id}",
                    details=[str(exc)],
                ) from exc
            if not isinstance(parsed, dict):
                raise MalformedEvidenceError(
                    f"expected object in {field} for session {session_id}",
                )
            return parsed
        raise MalformedEvidenceError(
            f"unexpected type for {field} on session {session_id}: {type(raw).__name__}",
        )

    def _framework_from_attempt(
        self,
        attempt: Dict[str, Any],
        session_id: str,
        attempt_number: int,
    ) -> Optional[Dict[str, Any]]:
        inspection_hint = attempt.get("framework")
        if inspection_hint:
            return {
                "framework": str(inspection_hint),
                "confidence": 0.8,
                "source": "attempt_metadata",
                "session_id": session_id,
                "attempt_number": attempt_number,
            }

        stderr = (attempt.get("stderr") or "").lower()
        stdout = (attempt.get("stdout") or "").lower()
        log_text = f"{stderr}\n{stdout}"
        framework_patterns = (
            ("wxwidgets", "wxwidgets"),
            ("qt", "qt"),
        )
        for pattern, framework_name in framework_patterns:
            if pattern in log_text:
                return {
                    "framework": framework_name,
                    "confidence": 0.75,
                    "source": "runtime_log",
                    "session_id": session_id,
                    "attempt_number": attempt_number,
                    "evidence": [f"runtime_log:{framework_name}"],
                }

        verification = attempt.get("verification") or {}
        for item in verification.get("evidence") or []:
            text = str(item).lower()
            if "wxwidgets" in text or "framework=" in text:
                framework = "wxwidgets" if "wxwidgets" in text else text.split("=", 1)[-1]
                return {
                    "framework": framework,
                    "confidence": 0.7,
                    "source": "verification_evidence",
                    "session_id": session_id,
                    "attempt_number": attempt_number,
                    "evidence": [str(item)],
                }
        return None
