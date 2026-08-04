"""Aggregated engineering dashboard data."""

from __future__ import annotations

from typing import TYPE_CHECKING

from alma_bridge.native_engineering.models import EngineeringDashboard, utc_now_iso

if TYPE_CHECKING:
    from alma_bridge.native_engineering.queries import NativeEngineeringQueries


def build_engineering_dashboard(queries: NativeEngineeringQueries) -> EngineeringDashboard:
    profiles = queries.list_profiles()
    behavior = queries.behavior_coverage_dashboard()
    conformance = queries.conformance_report()
    history = queries.benchmark_history()

    summary = [
        {
            "api_symbol": p.api_symbol,
            "capability_id": p.capability_id,
            "behavior_ids": p.behavior_ids,
            "spec_digest": p.specification.spec_digest,
            "suite_cases": len(p.behavior_suite.cases),
            "calibration_links": len(p.calibration_links),
            "governance_links": len(p.governance_links),
            "profile_digest": p.profile_digest,
        }
        for p in profiles
    ]

    limitations = [
        "Benchmark execution requires explicit pytest/CLI — not HTTP GET",
        "M2 worker is single-threaded — threading validation not_applicable",
        "append_existing_file implemented in 0.2.1-m2 — see append_existing_file_design.md",
    ]

    return EngineeringDashboard(
        generated_at=utc_now_iso(),
        provider_id="native_alma",
        api_count=len(profiles),
        behavior_coverage=behavior,
        conformance_report=conformance,
        benchmark_history=history,
        profiles_summary=summary,
        limitations=limitations,
    )
