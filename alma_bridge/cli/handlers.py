"""Thin CLI handlers — delegate to existing Bridge services only."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from alma_bridge.compatibility_intelligence.planner_integration import select_provider_from_capabilities
from alma_bridge.compatibility_intelligence.service import CompatibilityIntelligenceService
from alma_bridge.config import settings
from alma_bridge.learning.orchestrator import BridgeOrchestrator
from alma_bridge.runtime.registry import RuntimeRegistry, build_default_registry
from alma_bridge.runtime.selection import provider_id_for_strategy
from alma_bridge.runtime_intelligence.corpus import CorpusEnrollmentResolver
from alma_bridge.runtime_intelligence.family import BehaviorFamilyId
from alma_bridge.runtime_intelligence.models import CorpusKind
from alma_bridge.runtime_intelligence.service import RuntimeIntelligenceService
from alma_bridge.schemas.models import BridgeRequest, BridgeSessionResult
from alma_bridge.storage import outcomes


class AlmaCliError(Exception):
    """User-facing CLI error."""


class SessionNotFoundError(AlmaCliError):
    pass


class FileNotFoundCliError(AlmaCliError):
    pass


class UnsupportedFileCliError(AlmaCliError):
    pass


def resolve_executable_path(file_path: str) -> str:
    path = Path(file_path).expanduser()
    if not path.is_file():
        raise FileNotFoundCliError(f"File not found: {file_path}")
    return str(path.resolve())


def _aci_service() -> CompatibilityIntelligenceService:
    return CompatibilityIntelligenceService()


def _runtime_registry() -> RuntimeRegistry:
    return build_default_registry()


def _runtime_intel_service() -> RuntimeIntelligenceService:
    return RuntimeIntelligenceService.shared()


def _orchestrator() -> BridgeOrchestrator:
    return BridgeOrchestrator()


def _corpus_resolver() -> CorpusEnrollmentResolver:
    return CorpusEnrollmentResolver.from_manifest_files()


def analyze_executable(file_path: str, *, persist: bool = False) -> Any:
    resolved = resolve_executable_path(file_path)
    try:
        return _aci_service().analyze(resolved, persist=persist)
    except FileNotFoundError as exc:
        raise FileNotFoundCliError(str(exc)) from exc
    except Exception as exc:
        message = str(exc).lower()
        if "pe" in message or "invalid" in message or "unsupported" in message:
            raise UnsupportedFileCliError(str(exc)) from exc
        raise


def serialize_analysis(result: Any) -> Dict[str, Any]:
    return {
        "analysis_id": result.analysis_id,
        "file_path": result.file_path,
        "binary_digest": result.binary_digest,
        "metadata": result.metadata.model_dump(mode="json"),
        "import_count": len(result.imports),
        "coverage": result.coverage.model_dump(mode="json"),
        "prediction": result.prediction.model_dump(mode="json"),
        "read_only": True,
    }


def predict_executable(file_path: str, *, provider_id: Optional[str] = None, persist: bool = False) -> Dict[str, Any]:
    """Pre-execution prediction (Compatibility Intelligence → Runtime Intelligence calibration)."""
    resolved = resolve_executable_path(file_path)
    result = analyze_executable(resolved, persist=False)
    registry = _runtime_registry()
    recommended = select_provider_from_capabilities(result, registry=registry)
    chosen_provider = provider_id or recommended or result.prediction.recommended_provider_id or "native_alma"
    payload: Dict[str, Any] = {
        "authority": "non_authoritative_prediction",
        "disclaimer": "Pre-execution prediction only; not verified compatibility.",
        "analysis_id": result.analysis_id,
        "binary_digest": result.binary_digest,
        "file_path": result.file_path,
        "recommended_provider_id": recommended,
        "selected_provider_id": chosen_provider,
        "prediction": result.prediction.model_dump(mode="json"),
        "coverage": {
            pid: breakdown.model_dump(mode="json") for pid, breakdown in result.coverage.providers.items()
        },
        "snapshot_persisted": False,
    }
    if persist:
        snapshot = _aci_service().create_prediction_snapshot(
            resolved,
            provider_id=chosen_provider,
            persist=True,
        )
        payload["snapshot_id"] = snapshot.snapshot_id
        payload["snapshot_persisted"] = True
    return payload


def inspect_executable(file_path: str) -> Dict[str, Any]:
    resolved = resolve_executable_path(file_path)
    result = analyze_executable(resolved, persist=False)
    registry = _runtime_registry()
    recommended = select_provider_from_capabilities(result, registry=registry)
    imports = [
        {"dll": item.dll, "function": item.name, "ordinal": item.is_ordinal}
        for item in result.imports
    ]
    capabilities = [
        {
            "capability_id": req.capability_id,
            "description": req.description,
            "required_by_apis": req.required_by_apis,
            "complexity": req.complexity.value,
        }
        for req in result.required_capabilities
    ]
    provider_coverage = [
        {
            "provider_id": pid,
            "coverage_percent": breakdown.coverage_percent,
            "supported": breakdown.supported,
            "partial": breakdown.partial,
            "unsupported": breakdown.unsupported,
            "unknown": breakdown.unknown,
            "blockers": breakdown.blockers,
        }
        for pid, breakdown in sorted(result.coverage.providers.items())
    ]
    return {
        "read_only": True,
        "file_path": result.file_path,
        "binary_digest": result.binary_digest,
        "architecture": result.metadata.architecture,
        "subsystem": result.metadata.subsystem,
        "imports": imports,
        "import_count": len(imports),
        "capabilities": capabilities,
        "provider_coverage": provider_coverage,
        "recommended_provider_id": recommended,
        "confidence": result.prediction.confidence.model_dump(mode="json"),
        "prediction_summary": result.prediction.evidence_summary,
        "native_compatible": result.prediction.native_compatible,
        "wine_compatible": result.prediction.wine_compatible,
    }


def run_executable(
    file_path: str,
    *,
    args: Optional[List[str]] = None,
    preferred_strategy_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> BridgeSessionResult:
    resolved = resolve_executable_path(file_path)
    request = BridgeRequest(
        file_path=resolved,
        args=list(args or []),
        preferred_strategy_id=preferred_strategy_id,
    )
    return _orchestrator().run(request, session_id=session_id)


def serialize_run_result(result: BridgeSessionResult) -> Dict[str, Any]:
    return {
        "session_id": result.session_id,
        "file_path": result.file_path,
        "file_hash": result.file_hash,
        "success": result.success,
        "summary": result.summary,
        "attempts": [attempt.model_dump(mode="json") for attempt in result.attempts],
        "runtime_flags": {
            "native_runtime_enabled": bool(settings.native_runtime_enabled),
            "allow_experimental_runtimes": bool(settings.allow_experimental_runtimes),
        },
        "delegated_to": "BridgeOrchestrator",
    }


def verify_session(session_id: str) -> Dict[str, Any]:
    session = outcomes.get_session(session_id)
    if session is None:
        raise SessionNotFoundError(f"Session not found: {session_id}")
    attempts = session.get("attempts") or []
    verification_attempts = []
    for attempt in attempts:
        verification = attempt.get("verification") or {}
        if not verification:
            continue
        verification_attempts.append(
            {
                "attempt_number": attempt.get("attempt_number"),
                "strategy_id": attempt.get("strategy_id"),
                "phase": attempt.get("phase"),
                "passed": verification.get("passed"),
                "confidence": verification.get("confidence"),
                "failure_reason": verification.get("failure_reason"),
                "checks": verification.get("checks") or [],
                "evidence": verification.get("evidence") or [],
            }
        )
    latest = verification_attempts[-1] if verification_attempts else None
    if latest is None:
        verification_status = "unverifiable"
    elif latest.get("passed"):
        verification_status = "verified"
    else:
        verification_status = "failed"
    return {
        "session_id": session_id,
        "file_path": session.get("file_path"),
        "success": session.get("success"),
        "session_state": session.get("session_state"),
        "summary": session.get("summary"),
        "attempt_count": len(attempts),
        "verification_status": verification_status,
        "reads_stored_evidence_only": True,
        "verification_attempts": verification_attempts,
        "latest_verification": latest,
    }


def _insufficient_metric_report(*, reason: str) -> Dict[str, Any]:
    return {
        "status": "insufficient_evidence",
        "index_value": None,
        "knowledge_coverage_value": None,
        "report_digest": None,
        "limitations": [reason],
    }


def report_session(
    session_id: str,
    *,
    corpus: CorpusKind = CorpusKind.ENGINEERING,
    family_id: BehaviorFamilyId = BehaviorFamilyId.FILESYSTEM,
) -> Dict[str, Any]:
    session = outcomes.get_session(session_id)
    if session is None:
        raise SessionNotFoundError(f"Session not found: {session_id}")
    provider_id = "native_alma"
    winning = session.get("winning_attempt")
    if winning and winning.get("strategy_id"):
        provider_id = provider_id_for_strategy(str(winning["strategy_id"])) or provider_id
    binary_digest = session.get("file_hash") or ""
    resolver = _corpus_resolver()
    enrolled = bool(binary_digest) and resolver.is_enrolled(corpus, binary_digest=binary_digest)
    snapshot = _aci_service().get_prediction_snapshot_by_session(session_id)

    if not enrolled:
        insufficient = _insufficient_metric_report(reason="session_binary_not_enrolled_in_selected_corpus")
        return {
            "session_id": session_id,
            "file_path": session.get("file_path"),
            "binary_digest": binary_digest,
            "success": session.get("success"),
            "summary": session.get("summary"),
            "provider_id": provider_id,
            "corpus": corpus.value,
            "family_id": family_id.value,
            "corpus_enrollment_status": "not_enrolled",
            "limitations": ["session_binary_not_enrolled_in_selected_corpus"],
            "prediction_snapshot": snapshot.model_dump(mode="json") if snapshot else None,
            "compatibility_index": {
                "status": insufficient["status"],
                "index_value": None,
                "report_digest": None,
                "limitations": insufficient["limitations"],
            },
            "knowledge_coverage": {
                "status": insufficient["status"],
                "knowledge_coverage_value": None,
                "report_digest": None,
                "limitations": insufficient["limitations"],
            },
        }

    ri = _runtime_intel_service()
    index_report = ri.get_index(corpus, family_id, provider_id)
    knowledge_report = ri.get_knowledge(corpus, family_id, provider_id)
    return {
        "session_id": session_id,
        "file_path": session.get("file_path"),
        "binary_digest": binary_digest,
        "success": session.get("success"),
        "summary": session.get("summary"),
        "provider_id": provider_id,
        "corpus": corpus.value,
        "family_id": family_id.value,
        "corpus_enrollment_status": "enrolled",
        "limitations": [],
        "prediction_snapshot": snapshot.model_dump(mode="json") if snapshot else None,
        "compatibility_index": {
            "status": index_report.status.value,
            "index_value": index_report.index_value,
            "report_digest": index_report.report_digest,
            "limitations": index_report.limitations,
        },
        "knowledge_coverage": {
            "status": knowledge_report.status.value,
            "knowledge_coverage_value": knowledge_report.knowledge_coverage_value,
            "report_digest": knowledge_report.report_digest,
            "limitations": knowledge_report.limitations,
        },
    }


def list_providers() -> List[Dict[str, Any]]:
    return [entry.model_dump() for entry in _runtime_registry().inventory()]
