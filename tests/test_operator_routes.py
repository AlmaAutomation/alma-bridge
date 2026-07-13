"""Tests for operator route discovery and execution."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from alma_bridge.operator.routes import discover_routes, execute_best_routes


def test_discover_routes_builds_pathways_from_error():
    result = discover_routes(
        "error while loading shared libraries: libssl.so.1.0.0: cannot open shared object file"
    )
    assert result["route_count"] >= 1
    kinds = {r["kind"] for r in result["routes"]}
    assert "pathway" in kinds


def test_discover_routes_synthesizes_permission_denied_pathways():
    result = discover_routes("Last error: permission_denied. Try fresh WINEPREFIX.")
    titles = " ".join(r["title"] for r in result["routes"]).lower()
    assert "wine" in titles or "prefix" in titles or result["route_count"] >= 1


def test_execute_best_routes_dry_run():
    discovery = discover_routes("permission_denied wine prefix bad permissions")
    out = execute_best_routes(discovery, apply=False)
    assert out["success_count"] == 0
    assert all(r.get("skipped") for r in out["results"])


def test_discover_routes_detects_bridge_signature():
    result = discover_routes("err: Failed to create shared context for virtualization. GPU process")
    assert result.get("bridge_signature") in {"electron_gpu_crash", "gpu_crash", "unknown_error"}
    assert result.get("route_count", 0) >= 1


def test_discover_routes_includes_bridge_signature_pathways():
    result = discover_routes("permission_denied bad prefix permissions")
    titles = " ".join(r["title"] for r in result["routes"]).lower()
    assert "wine" in titles or "prefix" in titles


from alma_bridge.session.services.routes import RouteExecutionResult


def test_execute_best_routes_requires_bridge_when_file_path_set():
    discovery = {
        "file_path": "/tmp/game.exe",
        "routes": [
            {
                "id": "pathway:test",
                "kind": "pathway",
                "title": "heal only",
                "error_text": "test",
                "pathway_id": "test",
                "verify_bridge": True,
                "file_path": "/tmp/game.exe",
            },
        ],
    }
    fake_result = RouteExecutionResult(
        route_id="pathway:test",
        kind="pathway",
        success=False,
        requires_bridge_retry=True,
        heal={"success": True},
    )

    with patch(
        "alma_bridge.operator.routes._route_executor.execute_route",
        return_value=fake_result,
    ):
        out = execute_best_routes(discovery, apply=True, max_routes=1)

    assert out["success_count"] == 0
    assert out.get("requires_orchestrator_resume") is True


def test_execute_best_routes_stops_on_success():
    discovery = {
        "routes": [
            {"id": "a", "kind": "pathway", "title": "first", "error_text": "test"},
            {"id": "b", "kind": "pathway", "title": "second", "error_text": "test"},
        ]
    }
    fake = RouteExecutionResult(route_id="a", kind="pathway", success=True, heal={"success": True})

    with patch(
        "alma_bridge.operator.routes._route_executor.execute_route",
        return_value=fake,
    ):
        out = execute_best_routes(discovery, apply=True, max_routes=5)

    assert out["success_count"] == 1
    assert out["winning_route"] == "a"
    assert len(out["results"]) == 1


def test_run_autopilot_tries_multiple_pathways_when_enabled(monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.operator_try_all_pathways", True)
    monkeypatch.setattr("alma_bridge.config.settings.operator_max_route_attempts", 6)
    monkeypatch.setattr("alma_bridge.config.settings.operator_allow_mutations", True)

    calls = []

    def fake_apply(pathway, **kwargs):
        calls.append(pathway.get("id"))
        return [{"ok": pathway.get("id") == "second_path"}]

    plan = {
        "primary_signature": "permission_denied",
        "pathways": [
            {
                "id": "first_path",
                "title": "first",
                "steps": [{"kind": "remediation", "command": "echo one"}],
            },
            {
                "id": "second_path",
                "title": "second",
                "steps": [{"kind": "remediation", "command": "echo two"}],
            },
        ],
    }

    with patch("alma_bridge.compliance.autopilot.plan_pathways", return_value=plan):
        with patch(
            "alma_bridge.compliance.modernization.apply.apply_pathway_steps",
            side_effect=fake_apply,
        ):
            with patch("alma_bridge.compliance.autopilot.record_outcome"):
                from alma_bridge.compliance.autopilot import run_autopilot

                result = run_autopilot(
                    "permission_denied",
                    execute=True,
                    allow_mutations=True,
                    try_all_pathways=True,
                    max_pathway_attempts=3,
                )

    assert len(calls) >= 2
    assert result.get("success") is True
