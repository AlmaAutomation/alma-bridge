"""API route tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from alma_bridge.main import create_app


class TestApiRoutes:
    def setup_method(self):
        self.client = TestClient(create_app())

    def test_capability_registry_endpoint(self):
        resp = self.client.get("/bridge/compatibility/capabilities")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        ids = {item["capability_id"] for item in data}
        assert "filesystem.basic_io" in ids
        assert "console.stdout" in ids

    def test_api_registry_endpoint(self):
        resp = self.client.get("/bridge/compatibility/apis")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 18
        funcs = {(item["dll"], item["function"]) for item in data}
        assert ("kernel32.dll", "WriteFile") in funcs

    def test_metrics_endpoint(self):
        resp = self.client.get("/bridge/compatibility/metrics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_registry_apis"] >= 18
        assert "kernel32.dll" in data["by_dll"]

    def test_analyze_endpoint(self, hello64_path):
        resp = self.client.post(
            "/bridge/compatibility/analyze",
            json={"file_path": str(hello64_path), "persist": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["prediction"]["native_compatible"] is True
        assert data["coverage"]["total_apis"] >= 1

    def test_analyze_not_found(self):
        resp = self.client.post(
            "/bridge/compatibility/analyze",
            json={"file_path": "/no/such/file.exe"},
        )
        assert resp.status_code == 404

    def test_predict_endpoint(self, hello64_path):
        resp = self.client.get(
            "/bridge/compatibility/predict",
            params={"file_path": str(hello64_path)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "prediction" in data
        assert "coverage" in data
