"""Runtime Certification Platform orchestration."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.certification.dashboard import build_certification_dashboard
from alma_bridge.certification.models import (
    BehaviorCertification,
    CertificationDashboard,
    CertificationHistory,
    ComplianceMatrix,
    StaleCertificationItem,
)
from alma_bridge.certification.queries import CertificationQueries
from alma_bridge.certification.repository import CertificationRepository


class CertificationService:
    """Orchestrate read-only certification queries."""

    _instance: Optional[CertificationService] = None

    def __init__(
        self,
        *,
        queries: Optional[CertificationQueries] = None,
        repository: Optional[CertificationRepository] = None,
    ) -> None:
        self._repo = repository or CertificationRepository()
        self._queries = queries or CertificationQueries(certification_repo=self._repo)

    @classmethod
    def shared(cls) -> CertificationService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def list_behavior_certifications(self) -> List[BehaviorCertification]:
        return self._queries.list_behavior_certifications()

    def get_behavior_certification(
        self, capability_id: str, behavior_id: str
    ) -> BehaviorCertification:
        return self._queries.get_behavior_certification(capability_id, behavior_id)

    def get_certification_history(
        self, capability_id: str, behavior_id: str
    ) -> CertificationHistory:
        return self._queries.get_certification_history(capability_id, behavior_id)

    def compliance_matrix(self) -> ComplianceMatrix:
        return self._queries.compliance_matrix()

    def stale_certifications(self) -> list[StaleCertificationItem]:
        return self._queries.stale_certifications()

    def certification_dashboard(self) -> CertificationDashboard:
        return build_certification_dashboard(self._queries)
