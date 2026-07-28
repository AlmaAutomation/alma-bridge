"""Architecture boundary tests for Compatibility Catalog."""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG = ROOT / "alma_bridge" / "catalog"

FORBIDDEN_IMPORT_FRAGMENTS = (
    "orchestrator",
    "verification_gateway",
    "session.mutations",
    "winetricks",
    "ActionIntent",
)


def _py_files(path: Path) -> list[Path]:
    return sorted(p for p in path.rglob("*.py") if p.is_file())


def _forbidden_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for fragment in FORBIDDEN_IMPORT_FRAGMENTS:
                if fragment in node.module:
                    hits.append(f"{path.relative_to(ROOT)}:{fragment}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                for fragment in FORBIDDEN_IMPORT_FRAGMENTS:
                    if fragment in alias.name:
                        hits.append(f"{path.relative_to(ROOT)}:{fragment}")
    return hits


class TestCatalogArchitectureBoundaries:
    def test_catalog_package_has_no_forbidden_imports(self):
        offenders: list[str] = []
        for path in _py_files(CATALOG):
            offenders.extend(_forbidden_imports(path))
        assert offenders == []

    def test_catalog_api_routes_are_get_only(self):
        routes_path = ROOT / "alma_bridge" / "api" / "catalog_routes.py"
        tree = ast.parse(routes_path.read_text(encoding="utf-8"))
        http_methods: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        if dec.func.attr == "get":
                            http_methods.append("GET")
                    if isinstance(dec, ast.Attribute) and dec.attr == "get":
                        http_methods.append("GET")
        assert http_methods
        assert all(method == "GET" for method in http_methods)

    def test_import_catalog_routes_does_not_load_orchestrator(self):
        modules = (
            "alma_bridge.api.catalog_routes",
            "alma_bridge.learning.orchestrator",
        )
        saved = {mod: sys.modules.get(mod) for mod in modules}
        try:
            for mod in modules:
                sys.modules.pop(mod, None)
            importlib.import_module("alma_bridge.api.catalog_routes")
            assert "alma_bridge.learning.orchestrator" not in sys.modules
        finally:
            for mod, previous in saved.items():
                if previous is None:
                    sys.modules.pop(mod, None)
                else:
                    sys.modules[mod] = previous

    def test_catalog_service_source_has_no_action_intent(self):
        offenders: list[str] = []
        for path in _py_files(CATALOG):
            if "ActionIntent" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(ROOT)))
        assert offenders == []

    def test_catalog_aggregation_has_no_subprocess(self):
        source = (CATALOG / "aggregation.py").read_text(encoding="utf-8")
        assert "import subprocess" not in source
        assert "record_attempt" not in source
