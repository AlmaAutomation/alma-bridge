"""Read-only HTTP routes for Alma Research Platform."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from alma_bridge.research.service import ResearchService

router = APIRouter()


def _service() -> ResearchService:
    return ResearchService.shared()


@router.get("/bridge/research/reports", tags=["Research"])
def list_research_reports():
    """List available deterministic research report types."""
    return {
        "schema_version": "alma_research_v1",
        "report_types": _service().list_report_types(),
    }


@router.get("/bridge/research/reports/{report_type}", tags=["Research"])
def get_research_report(
    report_type: str,
    time_start: Optional[str] = Query(None, alias="time_window_start"),
    time_end: Optional[str] = Query(None, alias="time_window_end"),
    provider_id: Optional[str] = Query(None),
    use_cache: bool = Query(False),
):
    """Generate or fetch a deterministic research report (read-only GET)."""
    try:
        rt = ResearchService.parse_report_type(report_type)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    report = _service().generate_report(
        rt,
        time_start=time_start,
        time_end=time_end,
        provider_id=provider_id,
        use_cache=use_cache,
    )
    return report.model_dump(mode="json")


@router.get("/bridge/research/dashboard", tags=["Research"])
def research_dashboard(
    time_start: Optional[str] = Query(None, alias="time_window_start"),
    time_end: Optional[str] = Query(None, alias="time_window_end"),
    provider_id: Optional[str] = Query(None),
):
    """Aggregated research dashboard for Explorer (read-only)."""
    dashboard = _service().generate_dashboard(
        time_start=time_start,
        time_end=time_end,
        provider_id=provider_id,
    )
    return dashboard.model_dump(mode="json")
