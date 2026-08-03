"""Architecture boundary tests for decision plan validation."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

from tests._boundaries import forbidden_imports, py_files

ROOT = Path(__file__).resolve().parents[2]
DECISION_VALIDATION = ROOT / "alma_bridge" / "decision_validation"


class TestDecisionValidationArchitectureBoundaries:
    def test_decision_validation_package_has_no_forbidden_imports(self):
        offenders: list[str] = []
        for path in py_files(DECISION_VALIDATION):
            offenders.extend(forbidden_imports(path))
        assert offenders == []

    def test_decision_validation_cannot_emit_action_intent(self):
        for path in py_files(DECISION_VALIDATION):
            assert "ActionIntent" not in path.read_text(encoding="utf-8")

    def test_import_decision_validation_routes_does_not_load_orchestrator(self):
        modules = (
            "alma_bridge.api.decision_validation_routes",
            "alma_bridge.learning.orchestrator",
        )
        saved = {mod: sys.modules.get(mod) for mod in modules}
        try:
            for mod in modules:
                sys.modules.pop(mod, None)
            importlib.import_module("alma_bridge.api.decision_validation_routes")
            assert "alma_bridge.learning.orchestrator" not in sys.modules
        finally:
            for mod, value in saved.items():
                if value is None:
                    sys.modules.pop(mod, None)
                else:
                    sys.modules[mod] = value

    def test_dry_run_disclaimer_present(self):
        from alma_bridge.decision_validation.models import DRY_RUN_DISCLAIMER

        assert "No application was launched" in DRY_RUN_DISCLAIMER
