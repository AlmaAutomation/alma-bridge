"""Architecture boundary tests for Runtime Intelligence service layer."""

from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from tests._boundaries import FORBIDDEN_IMPORT_FRAGMENTS, ROOT, forbidden_imports, py_files

RUNTIME_INTELLIGENCE = ROOT / "alma_bridge" / "runtime_intelligence"
API_ROUTES = ROOT / "alma_bridge" / "api" / "runtime_intelligence_routes.py"


class TestRuntimeIntelligenceServiceBoundaries:
    def test_service_package_has_no_forbidden_imports(self):
        offenders: list[str] = []
        for path in py_files(RUNTIME_INTELLIGENCE):
            offenders.extend(forbidden_imports(path))
        assert offenders == []

    def test_queries_has_no_outcomes_store_import(self):
        source = (RUNTIME_INTELLIGENCE / "queries.py").read_text(encoding="utf-8")
        assert "storage.outcomes" not in source
        assert "OutcomesStore" not in source

    def test_service_has_no_orchestrator_import(self):
        source = (RUNTIME_INTELLIGENCE / "service.py").read_text(encoding="utf-8")
        assert "orchestrator" not in source

    def test_service_has_no_verification_gateway_import(self):
        source = (RUNTIME_INTELLIGENCE / "service.py").read_text(encoding="utf-8")
        assert "verification_gateway" not in source

    def test_service_has_no_session_mutation_import(self):
        source = (RUNTIME_INTELLIGENCE / "service.py").read_text(encoding="utf-8")
        assert "session.mutations" not in source

    def test_service_has_no_subprocess(self):
        for name in ("queries.py", "service.py", "history.py"):
            source = (RUNTIME_INTELLIGENCE / name).read_text(encoding="utf-8")
            assert "import subprocess" not in source

    def test_service_has_no_work_item_creation(self):
        source = (RUNTIME_INTELLIGENCE / "service.py").read_text(encoding="utf-8")
        assert "create_work_item" not in source
        assert "NativeLabService" not in source

    def test_service_has_no_governance_apply(self):
        source = (RUNTIME_INTELLIGENCE / "service.py").read_text(encoding="utf-8")
        assert "apply_governance" not in source

    def test_service_has_no_certification_issue(self):
        source = (RUNTIME_INTELLIGENCE / "service.py").read_text(encoding="utf-8")
        assert "issue_certification" not in source

    def test_service_has_no_provider_registry_mutation(self):
        source = (RUNTIME_INTELLIGENCE / "service.py").read_text(encoding="utf-8")
        assert "save_version" not in source
        assert "apply_playbook" not in source

    def test_queries_never_infer_corpus_from_outcomes(self):
        source = (RUNTIME_INTELLIGENCE / "queries.py").read_text(encoding="utf-8")
        assert "storage.outcomes" not in source
        assert "outcomes." not in source

    def test_api_routes_are_get_only(self):
        tree = ast.parse(API_ROUTES.read_text(encoding="utf-8"))
        methods: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        methods.append(dec.func.attr.upper())
                    elif isinstance(dec, ast.Attribute):
                        methods.append(dec.attr.upper())
        assert methods
        assert all(method == "GET" for method in methods)

    def test_import_api_routes_does_not_load_orchestrator(self):
        modules = (
            "alma_bridge.api.runtime_intelligence_routes",
            "alma_bridge.learning.orchestrator",
        )
        saved = {mod: sys.modules.get(mod) for mod in modules}
        try:
            for mod in modules:
                sys.modules.pop(mod, None)
            importlib.import_module("alma_bridge.api.runtime_intelligence_routes")
            assert "alma_bridge.learning.orchestrator" not in sys.modules
        finally:
            for mod, previous in saved.items():
                if previous is None:
                    sys.modules.pop(mod, None)
                else:
                    sys.modules[mod] = previous

    def test_no_global_merged_corpus_report(self):
        source = (RUNTIME_INTELLIGENCE / "service.py").read_text(encoding="utf-8")
        assert "combined" not in source.lower()

    def test_forbidden_fragments_absent_from_new_modules(self):
        offenders: list[str] = []
        for name in ("queries.py", "service.py", "history.py"):
            path = RUNTIME_INTELLIGENCE / name
            for fragment in FORBIDDEN_IMPORT_FRAGMENTS:
                if fragment in path.read_text(encoding="utf-8"):
                    offenders.append(f"{name}:{fragment}")
        assert offenders == []

    def test_get_report_does_not_append_timeline(self, corpus_resolver):
        from alma_bridge.runtime_intelligence.service import RuntimeIntelligenceService
        from alma_bridge.runtime_intelligence.queries import RuntimeIntelligenceQueries

        queries = RuntimeIntelligenceQueries(
            corpus_resolver=corpus_resolver,
            evidence_queries=MagicMock(list_bundle_ids=MagicMock(return_value=[])),
            analysis_repo=MagicMock(list_recent=MagicMock(return_value=[])),
            calibration_repo=MagicMock(list_records=MagicMock(return_value=[])),
            governance_repo=MagicMock(get_current_version=MagicMock(side_effect=RuntimeError("no gov"))),
        )
        repo = MagicMock()
        service = RuntimeIntelligenceService(queries=queries, evidence_repo=repo)
        from alma_bridge.runtime_intelligence.models import CorpusKind

        service.get_report(CorpusKind.ENGINEERING)
        repo.append_timeline_event.assert_not_called()

    def test_record_hypothesis_only_appends_timeline(self, corpus_resolver):
        from alma_bridge.runtime_intelligence.hypotheses import create_hypothesis_snapshot
        from alma_bridge.runtime_intelligence.models import BehaviorFamilyId, CorpusKind
        from alma_bridge.runtime_intelligence.service import RuntimeIntelligenceService
        from alma_bridge.runtime_intelligence.queries import RuntimeIntelligenceQueries

        queries = RuntimeIntelligenceQueries(corpus_resolver=corpus_resolver)
        repo = MagicMock()
        service = RuntimeIntelligenceService(queries=queries, evidence_repo=repo)
        service._evidence = MagicMock(timeline=MagicMock(return_value=[]))
        service._queries._corpus.is_enrolled = MagicMock(return_value=True)
        service._evidence.by_application_fingerprint = MagicMock(
            return_value=MagicMock(bundle_id="bundle-test")
        )
        snap = create_hypothesis_snapshot(
            created_at="2026-08-01T00:00:00+00:00",
            corpus=CorpusKind.ENGINEERING,
            provider_id="native_alma",
            provider_version_scope="0.2.1-m2",
            family_id=BehaviorFamilyId.FILESYSTEM,
            capability_id="filesystem.basic_io",
            behavior_id="append_existing_file",
            bounded_scope="append within workspace",
            evidence_snapshot_digest="snap-001",
            evidence_references=["evidence-001"],
            predicted_application_fingerprints=[
                "d87ac1f8a7c5bd11ffa5ccb00cf18d77edd5ce075a5b37835770e32feca15aaf"
            ],
        )
        with patch("alma_bridge.storage.outcomes.record_attempt") as record_attempt:
            service.record_hypothesis_created(snap)
            record_attempt.assert_not_called()
        repo.append_timeline_event.assert_called_once()
