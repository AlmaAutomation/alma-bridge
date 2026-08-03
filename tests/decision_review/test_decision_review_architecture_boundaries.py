"""Architecture boundary tests for decision plan review."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from tests._boundaries import forbidden_imports, py_files

ROOT = Path(__file__).resolve().parents[2]
DECISION_REVIEW = ROOT / "alma_bridge" / "decision_review"


class TestDecisionReviewArchitectureBoundaries:
    def test_decision_review_package_has_no_forbidden_imports(self):
        offenders: list[str] = []
        for path in py_files(DECISION_REVIEW):
            offenders.extend(forbidden_imports(path))
        assert offenders == []

    def test_import_decision_review_routes_does_not_load_orchestrator(self):
        modules = (
            "alma_bridge.api.decision_review_routes",
            "alma_bridge.learning.orchestrator",
        )
        saved = {mod: sys.modules.get(mod) for mod in modules}
        try:
            for mod in modules:
                sys.modules.pop(mod, None)
            importlib.import_module("alma_bridge.api.decision_review_routes")
            assert "alma_bridge.learning.orchestrator" not in sys.modules
        finally:
            for mod, value in saved.items():
                if value is None:
                    sys.modules.pop(mod, None)
                else:
                    sys.modules[mod] = value

    def test_execution_status_constant_is_not_executed(self):
        from alma_bridge.decision_review.models import EXECUTION_STATUS_NOT_EXECUTED

        assert EXECUTION_STATUS_NOT_EXECUTED == "not_executed"
