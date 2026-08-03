"""Native Runtime Development Laboratory orchestration."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.native_lab.acceptance import update_acceptance_criterion
from alma_bridge.native_lab.candidates import create_work_item_from_candidate
from alma_bridge.native_lab.dashboard import build_native_lab_dashboard
from alma_bridge.native_lab.errors import (
    EvidenceGateError,
    InvalidStatusTransitionError,
    WorkItemAlreadyExistsError,
    WorkItemNotFoundError,
)
from alma_bridge.native_lab.evidence_links import (
    artifact_digest_from_path,
    create_evidence_reference,
    infer_evidence_kind,
)
from alma_bridge.native_lab import hooks as lab_hooks
from alma_bridge.native_lab.models import (
    AcceptanceCriterionStatus,
    ChecklistEvaluation,
    DependencyGraph,
    EngineeringCard,
    EvidenceLinkKind,
    NativeLabDashboard,
    NativeRuntimeEngineeringWorkItem,
    RiskCategory,
    RiskReviewRecord,
    RiskSeverity,
    StatusEvent,
    WorkItemHistory,
    WorkItemStatus,
    utc_now_iso,
)
from alma_bridge.native_lab.queries import NativeLabQueries
from alma_bridge.native_lab.repository import NativeLabRepository
from alma_bridge.native_lab.risk_review import create_risk_review
from alma_bridge.native_lab.seed import ensure_seeded_work_item
from alma_bridge.native_lab.status import (
    create_status_event,
    validate_completion_gates,
    validate_transition,
)


class NativeLabService:
    """Orchestrate native lab workflow — coordinates human engineering only."""

    _instance: Optional[NativeLabService] = None

    def __init__(
        self,
        *,
        repository: Optional[NativeLabRepository] = None,
        queries: Optional[NativeLabQueries] = None,
    ) -> None:
        self._repo = repository or NativeLabRepository()
        self._queries = queries or NativeLabQueries(repository=self._repo)
        ensure_seeded_work_item(self._repo)

    @classmethod
    def shared(cls) -> NativeLabService:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def list_work_items(
        self, *, status: Optional[WorkItemStatus] = None
    ) -> List[NativeRuntimeEngineeringWorkItem]:
        return self._queries.list_work_items(status=status)

    def get_work_item(self, work_item_id: str) -> NativeRuntimeEngineeringWorkItem:
        item = self._queries.get_work_item(work_item_id)
        if not item:
            raise WorkItemNotFoundError(f"Work item not found: {work_item_id}")
        return item

    def get_engineering_card(self, work_item_id: str) -> EngineeringCard:
        card = self._queries.get_engineering_card(work_item_id)
        if not card:
            raise WorkItemNotFoundError(f"Work item not found: {work_item_id}")
        return card

    def get_history(self, work_item_id: str) -> WorkItemHistory:
        self.get_work_item(work_item_id)
        return self._queries.get_history(work_item_id)

    def get_checklist(self, work_item_id: str) -> ChecklistEvaluation:
        checklist = self._queries.get_checklist(work_item_id)
        if not checklist:
            raise WorkItemNotFoundError(f"Work item not found: {work_item_id}")
        return checklist

    def get_dependencies(self, work_item_id: str) -> DependencyGraph:
        graph = self._queries.get_dependencies(work_item_id)
        if not graph:
            raise WorkItemNotFoundError(f"Work item not found: {work_item_id}")
        return graph

    def get_evidence(self, work_item_id: str) -> List:
        self.get_work_item(work_item_id)
        return self._queries.get_evidence(work_item_id)

    def dashboard(self) -> NativeLabDashboard:
        return build_native_lab_dashboard(self._queries)

    def create_from_candidate(
        self,
        candidate_id: str,
        *,
        title: Optional[str] = None,
    ) -> NativeRuntimeEngineeringWorkItem:
        existing_ids = {i.work_item_id for i in self._repo.list_work_items()}
        item = create_work_item_from_candidate(
            candidate_id, title=title, existing_ids=existing_ids
        )
        self._repo.save_work_item(item, create_only=True)
        lab_hooks.on_engineering_work_item_created(item.work_item_id, item.work_item_digest)
        return item

    def transition_status(
        self,
        work_item_id: str,
        to_status: WorkItemStatus,
        *,
        actor: str = "",
        rationale: str = "",
    ) -> StatusEvent:
        item = self.get_work_item(work_item_id)
        validate_transition(item.status, to_status)
        if to_status == WorkItemStatus.COMPLETED:
            validate_completion_gates(item)
        event = create_status_event(
            work_item_id, item.status, to_status, actor=actor, rationale=rationale
        )
        self._repo.append_status_event(event)
        item.status = to_status
        item.updated_at = utc_now_iso()
        self._repo.save_work_item(item)
        if to_status == WorkItemStatus.ACCEPTED:
            lab_hooks.on_engineering_work_item_accepted(work_item_id, event.event_digest)
        elif to_status == WorkItemStatus.VERIFICATION_PENDING:
            lab_hooks.on_verification_requested(work_item_id, event.event_digest)
        elif to_status == WorkItemStatus.CERTIFICATION_PENDING:
            lab_hooks.on_certification_requested(work_item_id, event.event_digest)
        elif to_status == WorkItemStatus.COMPLETED:
            lab_hooks.on_engineering_work_item_completed(work_item_id, event.event_digest)
        return event

    def attach_evidence(
        self,
        work_item_id: str,
        artifact: str,
        *,
        kind: Optional[EvidenceLinkKind] = None,
        source: str = "human_engineer",
        attached_by: str = "",
    ):
        item = self.get_work_item(work_item_id)
        evidence_kind = kind or infer_evidence_kind(artifact)
        digest = artifact_digest_from_path(artifact)
        reference = create_evidence_reference(
            kind=evidence_kind,
            source=source,
            artifact_id=artifact,
            digest=digest,
            fixture_path=artifact if artifact.endswith(".exe") else None,
            attached_by=attached_by,
        )
        self._repo.append_evidence_attachment(work_item_id, reference)
        item.evidence_references = list(item.evidence_references) + [reference]
        item.updated_at = utc_now_iso()
        self._repo.save_work_item(item)
        lab_hooks.on_implementation_evidence_attached(
            work_item_id, reference.reference_id, artifact
        )
        return reference

    def submit_risk_review(
        self,
        work_item_id: str,
        *,
        category: RiskCategory,
        severity: RiskSeverity,
        description: str,
        likelihood: str = "medium",
        mitigation: str = "",
        residual_risk: str = "",
        reviewer: str = "",
    ) -> RiskReviewRecord:
        self.get_work_item(work_item_id)
        review = create_risk_review(
            work_item_id,
            category=category,
            severity=severity,
            description=description,
            likelihood=likelihood,
            mitigation=mitigation,
            residual_risk=residual_risk,
            reviewer=reviewer,
        )
        self._repo.append_risk_review(review)
        return review

    def update_acceptance(
        self,
        work_item_id: str,
        criterion_id: str,
        status: AcceptanceCriterionStatus,
        *,
        waiver_reviewer: Optional[str] = None,
        waiver_reason: Optional[str] = None,
        waiver_expires_at: Optional[str] = None,
    ):
        item = self.get_work_item(work_item_id)
        criterion = update_acceptance_criterion(
            item,
            criterion_id,
            status=status,
            waiver_reviewer=waiver_reviewer,
            waiver_reason=waiver_reason,
            waiver_expires_at=waiver_expires_at,
        )
        item.updated_at = utc_now_iso()
        self._repo.save_work_item(item)
        if status == AcceptanceCriterionStatus.SATISFIED and criterion.category.value == "testing":
            digest = sha256_v1({"criterion_id": criterion_id, "work_item_id": work_item_id})
            lab_hooks.on_behavior_tests_completed(work_item_id, digest)
        return criterion

    def supersede(
        self,
        work_item_id: str,
        successor_id: str,
        *,
        rationale: str = "",
    ) -> StatusEvent:
        item = self.get_work_item(work_item_id)
        self.get_work_item(successor_id)
        event = create_status_event(
            work_item_id,
            item.status,
            WorkItemStatus.SUPERSEDED,
            rationale=rationale or f"Superseded by {successor_id}",
        )
        self._repo.append_status_event(event)
        item.status = WorkItemStatus.SUPERSEDED
        item.superseded_by = successor_id
        item.updated_at = utc_now_iso()
        self._repo.save_work_item(item)
        digest = sha256_v1({"work_item_id": work_item_id, "successor_id": successor_id})
        lab_hooks.on_engineering_work_item_superseded(work_item_id, successor_id, digest)
        return event

    def request_certification(self, work_item_id: str) -> StatusEvent:
        """Transition toward certification_pending — does NOT issue certification."""
        return self.transition_status(
            work_item_id,
            WorkItemStatus.CERTIFICATION_PENDING,
            actor="human_engineer",
            rationale="Certification review requested",
        )
