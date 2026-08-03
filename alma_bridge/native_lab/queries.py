"""Read-only queries for native lab data."""

from __future__ import annotations

from typing import Dict, List, Optional

from alma_bridge.native_lab.checklists import generate_checklist
from alma_bridge.native_lab.dependencies import build_dependency_graph
from alma_bridge.native_lab.models import (
    ChecklistEvaluation,
    DependencyGraph,
    EngineeringCard,
    NativeRuntimeEngineeringWorkItem,
    WorkItemHistory,
    WorkItemStatus,
)
from alma_bridge.native_lab.repository import NativeLabRepository
from alma_bridge.native_lab.work_items import build_engineering_card


class NativeLabQueries:
    """Aggregate read-only native lab data."""

    def __init__(
        self,
        *,
        repository: Optional[NativeLabRepository] = None,
    ) -> None:
        self._repo = repository or NativeLabRepository()

    def list_work_items(
        self,
        *,
        status: Optional[WorkItemStatus] = None,
    ) -> List[NativeRuntimeEngineeringWorkItem]:
        items = self._repo.list_work_items()
        if status:
            items = [i for i in items if i.status == status]
        return items

    def get_work_item(self, work_item_id: str) -> Optional[NativeRuntimeEngineeringWorkItem]:
        return self._repo.get_work_item(work_item_id)

    def get_engineering_card(self, work_item_id: str) -> Optional[EngineeringCard]:
        item = self._repo.get_work_item(work_item_id)
        if not item:
            return None
        maturity, cert_level = self._maturity_and_certification(item)
        blockers = self._blockers_for(item)
        return build_engineering_card(
            item,
            current_maturity=maturity,
            current_certification_level=cert_level,
            blockers=blockers,
        )

    def get_history(self, work_item_id: str) -> WorkItemHistory:
        return self._repo.get_history(work_item_id)

    def get_checklist(self, work_item_id: str) -> Optional[ChecklistEvaluation]:
        item = self._repo.get_work_item(work_item_id)
        if not item:
            return None
        return generate_checklist(item)

    def get_dependencies(self, work_item_id: str) -> Optional[DependencyGraph]:
        item = self._repo.get_work_item(work_item_id)
        if not item:
            return None
        all_items = {i.work_item_id: i for i in self._repo.list_work_items()}
        return build_dependency_graph(item, all_items)

    def get_evidence(self, work_item_id: str) -> List:
        item = self._repo.get_work_item(work_item_id)
        if not item:
            return []
        return item.evidence_references

    def get_risk_reviews(self, work_item_id: str):
        return self._repo.list_risk_reviews(work_item_id)

    def _all_items_map(self) -> Dict[str, NativeRuntimeEngineeringWorkItem]:
        return {i.work_item_id: i for i in self._repo.list_work_items()}

    def _blockers_for(self, item: NativeRuntimeEngineeringWorkItem) -> List[str]:
        try:
            graph = build_dependency_graph(item, self._all_items_map())
            return graph.blocked_by
        except Exception:
            return []

    def _maturity_and_certification(
        self, item: NativeRuntimeEngineeringWorkItem
    ) -> tuple[str, str]:
        try:
            from alma_bridge.certification.service import CertificationService

            cert = CertificationService.shared().get_behavior_certification(
                item.capability_id, item.behavior_id
            )
            return "governed" if cert.governance_history else "specified", cert.certification_level.value
        except Exception:
            return "unknown", "unverified"
