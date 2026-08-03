"""HTTP routes for Native Runtime Development Laboratory."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from alma_bridge.native_lab.errors import (
    CandidateNotFoundError,
    DependencyCycleError,
    EvidenceGateError,
    HistoryMutationError,
    InvalidStatusTransitionError,
    NativeLabError,
    WaiverNotAllowedError,
    WorkItemAlreadyExistsError,
    WorkItemNotFoundError,
)
from alma_bridge.native_lab.models import (
    AcceptanceCriterionStatus,
    NATIVE_LAB_SCHEMA_VERSION,
    RiskCategory,
    RiskSeverity,
    WorkItemStatus,
)
from alma_bridge.native_lab.service import NativeLabService

router = APIRouter()


def _service() -> NativeLabService:
    return NativeLabService.shared()


class CreateWorkItemRequest(BaseModel):
    source_expansion_candidate_id: str
    title: Optional[str] = None


class StatusTransitionRequest(BaseModel):
    to_status: WorkItemStatus
    actor: str = ""
    rationale: str = ""


class AttachEvidenceRequest(BaseModel):
    artifact: str
    source: str = "human_engineer"
    attached_by: str = ""


class RiskReviewRequest(BaseModel):
    category: RiskCategory
    severity: RiskSeverity
    description: str
    likelihood: str = "medium"
    mitigation: str = ""
    residual_risk: str = ""
    reviewer: str = ""


class AcceptanceUpdateRequest(BaseModel):
    criterion_id: str
    status: AcceptanceCriterionStatus
    waiver_reviewer: Optional[str] = None
    waiver_reason: Optional[str] = None
    waiver_expires_at: Optional[str] = None


class SupersedeRequest(BaseModel):
    successor_id: str
    rationale: str = ""


@router.get("/bridge/native-lab/work-items", tags=["NativeLab"])
def list_work_items(status: Optional[WorkItemStatus] = None):
    items = _service().list_work_items(status=status)
    return {
        "schema_version": NATIVE_LAB_SCHEMA_VERSION,
        "count": len(items),
        "work_items": [i.model_dump(mode="json") for i in items],
    }


@router.get("/bridge/native-lab/work-items/{work_item_id}", tags=["NativeLab"])
def get_work_item(work_item_id: str):
    try:
        item = _service().get_work_item(work_item_id)
        card = _service().get_engineering_card(work_item_id)
    except WorkItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "work_item": item.model_dump(mode="json"),
        "engineering_card": card.model_dump(mode="json"),
    }


@router.get("/bridge/native-lab/work-items/{work_item_id}/history", tags=["NativeLab"])
def work_item_history(work_item_id: str):
    try:
        history = _service().get_history(work_item_id)
    except WorkItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return history.model_dump(mode="json")


@router.get("/bridge/native-lab/work-items/{work_item_id}/checklist", tags=["NativeLab"])
def work_item_checklist(work_item_id: str):
    try:
        checklist = _service().get_checklist(work_item_id)
    except WorkItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return checklist.model_dump(mode="json")


@router.get("/bridge/native-lab/work-items/{work_item_id}/dependencies", tags=["NativeLab"])
def work_item_dependencies(work_item_id: str):
    try:
        graph = _service().get_dependencies(work_item_id)
    except WorkItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DependencyCycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return graph.model_dump(mode="json")


@router.get("/bridge/native-lab/work-items/{work_item_id}/evidence", tags=["NativeLab"])
def work_item_evidence(work_item_id: str):
    try:
        evidence = _service().get_evidence(work_item_id)
    except WorkItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        "work_item_id": work_item_id,
        "count": len(evidence),
        "evidence": [e.model_dump(mode="json") for e in evidence],
    }


@router.get("/bridge/native-lab/dashboard", tags=["NativeLab"])
def native_lab_dashboard():
    dashboard = _service().dashboard()
    return dashboard.model_dump(mode="json")


@router.post("/bridge/native-lab/work-items", tags=["NativeLab"])
def create_work_item(body: CreateWorkItemRequest):
    try:
        item = _service().create_from_candidate(
            body.source_expansion_candidate_id,
            title=body.title,
        )
    except CandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WorkItemAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except NativeLabError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return item.model_dump(mode="json")


@router.post("/bridge/native-lab/work-items/{work_item_id}/status", tags=["NativeLab"])
def transition_status(work_item_id: str, body: StatusTransitionRequest):
    try:
        event = _service().transition_status(
            work_item_id,
            body.to_status,
            actor=body.actor,
            rationale=body.rationale,
        )
    except WorkItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except InvalidStatusTransitionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except EvidenceGateError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return event.model_dump(mode="json")


@router.post("/bridge/native-lab/work-items/{work_item_id}/evidence", tags=["NativeLab"])
def attach_evidence(work_item_id: str, body: AttachEvidenceRequest):
    try:
        reference = _service().attach_evidence(
            work_item_id,
            body.artifact,
            source=body.source,
            attached_by=body.attached_by,
        )
    except WorkItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except HistoryMutationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return reference.model_dump(mode="json")


@router.post("/bridge/native-lab/work-items/{work_item_id}/risk-reviews", tags=["NativeLab"])
def submit_risk_review(work_item_id: str, body: RiskReviewRequest):
    try:
        review = _service().submit_risk_review(
            work_item_id,
            category=body.category,
            severity=body.severity,
            description=body.description,
            likelihood=body.likelihood,
            mitigation=body.mitigation,
            residual_risk=body.residual_risk,
            reviewer=body.reviewer,
        )
    except WorkItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return review.model_dump(mode="json")


@router.post("/bridge/native-lab/work-items/{work_item_id}/acceptance", tags=["NativeLab"])
def update_acceptance(work_item_id: str, body: AcceptanceUpdateRequest):
    try:
        criterion = _service().update_acceptance(
            work_item_id,
            body.criterion_id,
            body.status,
            waiver_reviewer=body.waiver_reviewer,
            waiver_reason=body.waiver_reason,
            waiver_expires_at=body.waiver_expires_at,
        )
    except WorkItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except WaiverNotAllowedError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return criterion.model_dump(mode="json")


@router.post("/bridge/native-lab/work-items/{work_item_id}/supersede", tags=["NativeLab"])
def supersede_work_item(work_item_id: str, body: SupersedeRequest):
    try:
        event = _service().supersede(
            work_item_id,
            body.successor_id,
            rationale=body.rationale,
        )
    except WorkItemNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return event.model_dump(mode="json")
