"""HTTP routes for runtime expansion planning — read-only GET only."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException

from alma_bridge.compatibility_intelligence.expansion.errors import CandidateNotFoundError
from alma_bridge.compatibility_intelligence.expansion.service import ExpansionPlanningService

router = APIRouter()
_service = ExpansionPlanningService()


@router.get(
    "/bridge/compatibility/expansion/plan",
    tags=["Compatibility Intelligence Expansion"],
)
def get_expansion_plan(
    provider_id: Optional[str] = None,
    architecture: Optional[str] = None,
    subsystem: Optional[str] = None,
    maximum_complexity: Optional[str] = None,
    maximum_security_risk: Optional[float] = None,
):
    """Ranked runtime expansion plan — advisory only, no execution."""
    plan = _service.get_plan(
        provider_id=provider_id,
        architecture=architecture,
        subsystem=subsystem,
        maximum_complexity=maximum_complexity,
        maximum_security_risk=maximum_security_risk,
    )
    return plan.model_dump(mode="json")


@router.get(
    "/bridge/compatibility/expansion/candidates/{candidate_id}",
    tags=["Compatibility Intelligence Expansion"],
)
def get_expansion_candidate(candidate_id: str):
    """Single expansion candidate detail — read-only."""
    try:
        candidate = _service.get_candidate(candidate_id)
    except CandidateNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return candidate.model_dump(mode="json")


@router.get(
    "/bridge/compatibility/expansion/capabilities/{capability_id}",
    tags=["Compatibility Intelligence Expansion"],
)
def get_expansion_candidates_for_capability(capability_id: str):
    """Expansion candidates scoped to a capability — read-only."""
    candidates = _service.get_candidates_for_capability(capability_id)
    return [c.model_dump(mode="json") for c in candidates]
