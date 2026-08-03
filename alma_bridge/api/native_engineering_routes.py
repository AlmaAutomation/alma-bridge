"""Read-only HTTP routes for Native Runtime Engineering Platform."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from alma_bridge.native_engineering.errors import SpecificationNotFoundError
from alma_bridge.native_engineering.models import NATIVE_ENGINEERING_SCHEMA_VERSION
from alma_bridge.native_engineering.service import NativeEngineeringService

router = APIRouter()


def _service() -> NativeEngineeringService:
    return NativeEngineeringService.shared()


@router.get("/bridge/native-engineering/apis", tags=["NativeEngineering"])
def list_api_engineering_profiles():
    """List API engineering profiles (read-only)."""
    profiles = _service().list_api_profiles()
    return {
        "schema_version": NATIVE_ENGINEERING_SCHEMA_VERSION,
        "count": len(profiles),
        "apis": [p.model_dump(mode="json") for p in profiles],
    }


@router.get("/bridge/native-engineering/apis/{api_symbol}", tags=["NativeEngineering"])
def get_api_engineering_profile(api_symbol: str):
    """Full engineering profile for one Win32 API (read-only)."""
    try:
        profile = _service().get_api_profile(api_symbol)
    except SpecificationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return profile.model_dump(mode="json")


@router.get("/bridge/native-engineering/behaviors", tags=["NativeEngineering"])
def behavior_coverage_dashboard():
    """Behavior coverage dashboard data (read-only)."""
    dashboard = _service().behavior_coverage()
    return dashboard.model_dump(mode="json")


@router.get("/bridge/native-engineering/benchmarks", tags=["NativeEngineering"])
def benchmark_results():
    """Benchmark results and longitudinal history (read-only)."""
    data = _service().benchmark_results_and_history()
    return {
        "schema_version": NATIVE_ENGINEERING_SCHEMA_VERSION,
        "results": [r.model_dump(mode="json") for r in data["results"]],
        "history": [h.model_dump(mode="json") for h in data["history"]],
        "catalog": data["catalog"],
    }


@router.get("/bridge/native-engineering/conformance", tags=["NativeEngineering"])
def conformance_report():
    """ABI conformance report (read-only)."""
    report = _service().conformance_report()
    return report.model_dump(mode="json")


@router.get("/bridge/native-engineering/dashboard", tags=["NativeEngineering"])
def engineering_dashboard():
    """Aggregated native runtime engineering dashboard (read-only)."""
    dashboard = _service().engineering_dashboard()
    return dashboard.model_dump(mode="json")
