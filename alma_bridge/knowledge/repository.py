"""Repository protocol and read-only evidence adapter for knowledge aggregation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from alma_bridge.intelligence.repository import OutcomesStoreAdapter


@runtime_checkable
class KnowledgeEvidenceRepository(Protocol):
    def get_session_record(self, session_id: str) -> Optional[Dict[str, Any]]: ...

    def list_sessions_for_fingerprint(self, fingerprint: str) -> List[Dict[str, Any]]: ...

    def get_profile_candidate_for_attempt(
        self,
        session_id: str,
        attempt_number: int,
    ) -> Optional[Any]: ...


class ReadOnlyKnowledgeEvidenceAdapter(OutcomesStoreAdapter):
    """Read-only adapter over persisted bridge session evidence."""
