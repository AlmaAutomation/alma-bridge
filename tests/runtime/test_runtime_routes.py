"""Runtime API route tests."""

from __future__ import annotations

import importlib
import sys

from fastapi.testclient import TestClient

from alma_bridge.main import app


class TestRuntimeRoutes:
    def test_runtime_providers_endpoint(self):
        client = TestClient(app)
        response = client.get("/bridge/runtime/providers")
        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload, list)
        assert len(payload) >= 4
        ids = {item["provider_id"] for item in payload}
        assert "wine" in ids
        assert "native_alma" in ids

    def test_runtime_routes_do_not_load_orchestrator(self):
        modules = (
            "alma_bridge.api.runtime_routes",
            "alma_bridge.learning.orchestrator",
        )
        saved = {mod: sys.modules.get(mod) for mod in modules}
        try:
            for mod in modules:
                sys.modules.pop(mod, None)
            importlib.import_module("alma_bridge.api.runtime_routes")
            assert "alma_bridge.learning.orchestrator" not in sys.modules
        finally:
            for mod, previous in saved.items():
                if previous is None:
                    sys.modules.pop(mod, None)
                else:
                    sys.modules[mod] = previous
