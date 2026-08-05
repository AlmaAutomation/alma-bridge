"""Architecture boundary tests for Runtime Intelligence."""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path
from unittest.mock import patch

from tests._boundaries import FORBIDDEN_IMPORT_FRAGMENTS, forbidden_imports, py_files

ROOT = Path(__file__).resolve().parents[2]
RUNTIME_INTELLIGENCE = ROOT / "alma_bridge" / "runtime_intelligence"


class TestRuntimeIntelligenceArchitectureBoundaries:
    def test_runtime_intelligence_package_has_no_forbidden_imports(self):
        offenders: list[str] = []
        for path in py_files(RUNTIME_INTELLIGENCE):
            offenders.extend(forbidden_imports(path))
        assert offenders == []

    def test_corpus_module_has_no_storage_outcomes_import(self):
        source = (RUNTIME_INTELLIGENCE / "corpus.py").read_text(encoding="utf-8")
        assert "storage.outcomes" not in source
        assert "OutcomesStore" not in source

    def test_family_module_has_no_mutation_apis(self):
        source = (RUNTIME_INTELLIGENCE / "family.py").read_text(encoding="utf-8")
        for fragment in ("record_attempt", "finalize_session", "ActionIntent", "GraphIngestionEngine"):
            assert fragment not in source

    def test_import_runtime_intelligence_has_no_db_side_effects(self):
        calls: list[str] = []

        def _track(name: str):
            def _wrapper(*args, **kwargs):
                calls.append(name)

            return _wrapper

        with patch("alma_bridge.storage.outcomes.init_outcome_store", _track("init_outcome_store")):
            with patch(
                "alma_bridge.compatibility.profile_store.ensure_profile_tables",
                _track("ensure_profile_tables"),
            ):
                importlib.import_module("alma_bridge.runtime_intelligence")
        assert calls == []

    def test_corpus_kind_has_no_combined_member(self):
        from alma_bridge.runtime_intelligence.models import CorpusKind

        assert {member.value for member in CorpusKind} == {"engineering", "real_world"}

    def test_package_source_has_no_forbidden_import_fragments(self):
        offenders: list[str] = []
        for path in py_files(RUNTIME_INTELLIGENCE):
            for fragment in FORBIDDEN_IMPORT_FRAGMENTS:
                if fragment in path.read_text(encoding="utf-8"):
                    offenders.append(f"{path.relative_to(ROOT)}:{fragment}")
        assert offenders == []

    def test_import_runtime_intelligence_does_not_load_orchestrator(self):
        modules = (
            "alma_bridge.runtime_intelligence",
            "alma_bridge.learning.orchestrator",
        )
        saved = {mod: sys.modules.get(mod) for mod in modules}
        try:
            for mod in modules:
                sys.modules.pop(mod, None)
            importlib.import_module("alma_bridge.runtime_intelligence")
            assert "alma_bridge.learning.orchestrator" not in sys.modules
        finally:
            for mod, previous in saved.items():
                if previous is None:
                    sys.modules.pop(mod, None)
                else:
                    sys.modules[mod] = previous

    def test_corpus_resolver_never_merges_tracks(self):
        source = (RUNTIME_INTELLIGENCE / "corpus.py").read_text(encoding="utf-8")
        assert "combined" not in source.lower()
        tree = ast.parse(source)
        function_names = {
            node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
        }
        assert "merge" not in function_names
