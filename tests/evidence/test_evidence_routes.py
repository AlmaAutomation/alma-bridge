"""API route tests for evidence endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from alma_bridge.main import app


client = TestClient(app)


class TestEvidenceRoutes:
    def test_platform_health(self):
        res = client.get("/bridge/evidence/platform/health")
        assert res.status_code == 200
        data = res.json()
        assert "metrics" in data
        assert "generated_at" in data

    def test_assemble_requires_params(self):
        res = client.post("/bridge/evidence/assemble")
        assert res.status_code == 400

    def test_timeline_not_found_returns_empty(self):
        res = client.get("/bridge/evidence/bundles/nonexistent-bundle-id/timeline")
        assert res.status_code == 200
        assert res.json()["event_count"] == 0
