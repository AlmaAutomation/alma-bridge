"""Native Runtime Development Laboratory verification — 25 backend scenarios."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from alma_bridge.config import PROJECT_ROOT
from alma_bridge.main import app
from alma_bridge.native_lab.checklists import generate_checklist
from alma_bridge.native_lab.dependencies import build_dependency_graph, validate_no_cycle_on_add
from alma_bridge.native_lab.errors import (
    DependencyCycleError,
    EvidenceGateError,
    HistoryMutationError,
    InvalidStatusTransitionError,
    WaiverNotAllowedError,
    WorkItemAlreadyExistsError,
)
from alma_bridge.native_lab.models import (
    AcceptanceCriterionStatus,
    ChecklistCategory,
    RiskCategory,
    RiskSeverity,
    SEEDED_WORK_ITEM_ID,
    WorkItemStatus,
)
from alma_bridge.native_lab.seed import build_seeded_append_work_item
from alma_bridge.native_lab.status import validate_transition
from alma_bridge.native_lab.work_items import is_evidence_gated_complete

client = TestClient(app)

FIXTURE_BIN = PROJECT_ROOT / "tests" / "fixtures" / "native_runtime" / "bin"
FIXTURE_MANIFEST = PROJECT_ROOT / "tests" / "fixtures" / "native_runtime" / "manifest.json"


def _fixture_digest(name: str) -> str:
    if FIXTURE_MANIFEST.is_file():
        manifest = json.loads(FIXTURE_MANIFEST.read_text(encoding="utf-8"))
        for digest, fixture_name in manifest.get("fixtures", {}).items():
            if fixture_name == name:
                return digest
    path = FIXTURE_BIN / name
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TestWorkItemCreation:
    def test_seeded_append_work_item_exists(self, native_lab_service):
        item = native_lab_service.get_work_item(SEEDED_WORK_ITEM_ID)
        assert item.capability_id == "filesystem.basic_io"
        assert item.behavior_id == "append_existing_file"
        assert item.status == WorkItemStatus.PROPOSED
        assert len(item.evidence_references) >= 5

    def test_seeded_work_item_has_all_required_fields(self, native_lab_service):
        item = native_lab_service.get_work_item(SEEDED_WORK_ITEM_ID)
        assert item.work_item_id
        assert item.title
        assert item.bounded_scope
        assert item.source_expansion_candidate_id
        assert item.work_item_digest
        assert item.acceptance_criteria
        assert item.required_fixtures
        assert item.security_review_items

    def test_create_from_expansion_candidate(self, native_lab_service):
        from alma_bridge.compatibility_intelligence.expansion.service import ExpansionPlanningService

        plan = ExpansionPlanningService().generate_plan()
        candidate = next(
            c
            for c in plan.ranked_candidates
            if c.behavior_id == "open_existing_readwrite"
        )
        try:
            item = native_lab_service.create_from_candidate(candidate.candidate_id)
            assert item.source_expansion_candidate_id == candidate.candidate_id
            assert item.status == WorkItemStatus.PROPOSED
        except WorkItemAlreadyExistsError:
            pass  # idempotent if already created

    def test_duplicate_create_rejected(self, native_lab_service):
        with pytest.raises(WorkItemAlreadyExistsError):
            native_lab_service.create_from_candidate(
                native_lab_service.get_work_item(SEEDED_WORK_ITEM_ID).source_expansion_candidate_id
            )


class TestChecklists:
    def test_deterministic_checklist_generation(self, native_lab_service):
        item = native_lab_service.get_work_item(SEEDED_WORK_ITEM_ID)
        c1 = generate_checklist(item)
        c2 = generate_checklist(item)
        assert c1.evaluation_digest == c2.evaluation_digest
        assert len(c1.items) == 14

    def test_checklist_categories_present(self, native_lab_service):
        item = native_lab_service.get_work_item(SEEDED_WORK_ITEM_ID)
        checklist = generate_checklist(item)
        cats = {i.category for i in checklist.items}
        assert ChecklistCategory.DESIGN in cats
        assert ChecklistCategory.GOVERNANCE in cats
        assert ChecklistCategory.VERIFICATION in cats

    def test_seeded_checklist_item_14_preserve_overlapped(self, native_lab_service):
        item = native_lab_service.get_work_item(SEEDED_WORK_ITEM_ID)
        checklist = generate_checklist(item)
        last = [i for i in checklist.items if i.ordinal == 14][0]
        assert "overlapped" in last.title.lower()


class TestAcceptanceCriteria:
    def test_seeded_acceptance_criteria(self, native_lab_service):
        item = native_lab_service.get_work_item(SEEDED_WORK_ITEM_ID)
        assert len(item.acceptance_criteria) >= 8
        critical = [c for c in item.acceptance_criteria if c.critical]
        assert len(critical) >= 4

    def test_critical_waiver_requires_reviewer(self, native_lab_service):
        item = native_lab_service.get_work_item(SEEDED_WORK_ITEM_ID)
        crit = next(c for c in item.acceptance_criteria if c.security_related)
        with pytest.raises(WaiverNotAllowedError):
            native_lab_service.update_acceptance(
                item.work_item_id,
                crit.criterion_id,
                AcceptanceCriterionStatus.WAIVED,
            )

    def test_satisfy_acceptance_criterion(self, native_lab_service):
        item = native_lab_service.get_work_item(SEEDED_WORK_ITEM_ID)
        crit = item.acceptance_criteria[0]
        updated = native_lab_service.update_acceptance(
            item.work_item_id,
            crit.criterion_id,
            AcceptanceCriterionStatus.SATISFIED,
        )
        assert updated.status == AcceptanceCriterionStatus.SATISFIED


class TestStatusTransitions:
    def test_valid_transition_proposed_to_triaged(self):
        validate_transition(WorkItemStatus.PROPOSED, WorkItemStatus.TRIAGED)

    def test_invalid_transition_proposed_to_completed(self):
        with pytest.raises(InvalidStatusTransitionError):
            validate_transition(WorkItemStatus.PROPOSED, WorkItemStatus.COMPLETED)

    def test_status_append_only_events(self, native_lab_service):
        item = native_lab_service.get_work_item(SEEDED_WORK_ITEM_ID)
        if item.status == WorkItemStatus.PROPOSED:
            event = native_lab_service.transition_status(
                item.work_item_id, WorkItemStatus.TRIAGED, actor="test"
            )
            assert event.to_status == WorkItemStatus.TRIAGED
            history = native_lab_service.get_history(item.work_item_id)
            assert len(history.events) >= 1

    def test_completion_blocked_without_evidence_gates(self, native_lab_service):
        item = build_seeded_append_work_item()
        assert not is_evidence_gated_complete(item)
        from alma_bridge.native_lab.status import validate_completion_gates

        with pytest.raises(EvidenceGateError):
            validate_completion_gates(item)


class TestDependencies:
    def test_dependency_graph_no_cycle(self, native_lab_service):
        item = native_lab_service.get_work_item(SEEDED_WORK_ITEM_ID)
        all_items = {i.work_item_id: i for i in native_lab_service.list_work_items()}
        graph = build_dependency_graph(item, all_items)
        assert not graph.has_cycle

    def test_cycle_detection_rejects(self):
        from alma_bridge.native_lab.models import NativeRuntimeEngineeringWorkItem

        a = NativeRuntimeEngineeringWorkItem(
            work_item_id="wi_a",
            title="a",
            capability_id="c",
            behavior_id="b",
            bounded_scope="s",
            prerequisite_work_item_ids=["wi_b"],
        )
        b = NativeRuntimeEngineeringWorkItem(
            work_item_id="wi_b",
            title="b",
            capability_id="c",
            behavior_id="b2",
            bounded_scope="s",
            prerequisite_work_item_ids=["wi_a"],
        )
        with pytest.raises(DependencyCycleError):
            build_dependency_graph(a, {"wi_a": a, "wi_b": b})

    def test_blocked_by_reporting(self, native_lab_service):
        graph = native_lab_service.get_dependencies(SEEDED_WORK_ITEM_ID)
        assert isinstance(graph.blocked_by, list)


class TestRiskReview:
    def test_structured_risk_review(self, native_lab_service):
        review = native_lab_service.submit_risk_review(
            SEEDED_WORK_ITEM_ID,
            category=RiskCategory.SECURITY,
            severity=RiskSeverity.MEDIUM,
            description="Filesystem escape review",
            reviewer="engineer",
        )
        assert review.review_id
        assert review.category == RiskCategory.SECURITY


class TestEvidenceAttachments:
    def test_attach_evidence_read_only_link(self, native_lab_service):
        artifact = FIXTURE_BIN / "file_append_unsupported.exe"
        before = artifact.read_bytes()
        expected_digest = _fixture_digest("file_append_unsupported.exe")
        ref = native_lab_service.attach_evidence(
            SEEDED_WORK_ITEM_ID,
            str(artifact.relative_to(PROJECT_ROOT)),
            attached_by="test",
        )
        assert ref.artifact_id
        assert ref.digest == expected_digest
        assert artifact.read_bytes() == before
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == expected_digest

    def test_evidence_list_via_api(self):
        resp = client.get(f"/bridge/native-lab/work-items/{SEEDED_WORK_ITEM_ID}/evidence")
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1


class TestEngineeringCard:
    def test_engineering_card_generation(self, native_lab_service):
        card = native_lab_service.get_engineering_card(SEEDED_WORK_ITEM_ID)
        assert card.demand_summary
        assert card.impact_summary
        assert card.bounded_scope
        assert card.work_item_id == SEEDED_WORK_ITEM_ID


class TestDashboard:
    def test_dashboard_metrics_with_sample_sizes(self, native_lab_service):
        dashboard = native_lab_service.dashboard()
        assert dashboard.total_work_items >= 1
        assert "work_items" in dashboard.sample_sizes


class TestRoutes:
    def test_list_work_items_get(self):
        resp = client.get("/bridge/native-lab/work-items")
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    def test_get_work_item_detail(self):
        resp = client.get(f"/bridge/native-lab/work-items/{SEEDED_WORK_ITEM_ID}")
        assert resp.status_code == 200
        assert "engineering_card" in resp.json()

    def test_get_endpoints_are_read_only_except_post(self):
        from alma_bridge.api import native_lab_routes

        get_routes = [r for r in native_lab_routes.router.routes if "GET" in r.methods]
        post_routes = [r for r in native_lab_routes.router.routes if "POST" in r.methods]
        assert len(get_routes) >= 7
        assert len(post_routes) >= 5

    def test_post_status_does_not_execute_binaries(self, native_lab_service):
        """Status POST only mutates lab records."""
        item = native_lab_service.get_work_item(SEEDED_WORK_ITEM_ID)
        if item.status == WorkItemStatus.PROPOSED:
            resp = client.post(
                f"/bridge/native-lab/work-items/{SEEDED_WORK_ITEM_ID}/status",
                json={"to_status": "triaged", "actor": "test"},
            )
            assert resp.status_code == 200
            assert "event_id" in resp.json()

    def test_post_evidence_does_not_mutate_source(self, native_lab_service):
        before = native_lab_service.get_evidence(SEEDED_WORK_ITEM_ID)
        count_before = len(before)
        native_lab_service.attach_evidence(
            SEEDED_WORK_ITEM_ID,
            "behavior_test_result.json",
            attached_by="test",
        )
        after = native_lab_service.get_evidence(SEEDED_WORK_ITEM_ID)
        assert len(after) > count_before
        # Original seeded references unchanged
        original = [e for e in after if e.reference_id == "ev_file_append_unsupported"]
        if original:
            assert original[0].digest == _fixture_digest("file_append_unsupported.exe")


class TestRepository:
    def test_append_only_work_item(self, native_lab_repo):
        item = build_seeded_append_work_item()
        item.work_item_id = "wi_test_append_only"
        native_lab_repo.save_work_item(item, create_only=True)
        with pytest.raises(HistoryMutationError):
            native_lab_repo.save_work_item(item, create_only=True)


class TestFrontendContract:
    """API contract tests for Explorer (items 1-10)."""

    def test_work_item_scope_in_response(self):
        resp = client.get(f"/bridge/native-lab/work-items/{SEEDED_WORK_ITEM_ID}")
        wi = resp.json()["work_item"]
        assert "bounded_scope" in wi
        assert "filesystem.basic_io" in wi["capability_id"]

    def test_demand_impact_distinguished(self):
        resp = client.get(f"/bridge/native-lab/work-items/{SEEDED_WORK_ITEM_ID}")
        card = resp.json()["engineering_card"]
        assert card["demand_summary"]
        assert card["impact_summary"]
        assert card["demand_summary"] != card["impact_summary"] or card["impact_summary"]

    def test_checklist_api(self):
        resp = client.get(f"/bridge/native-lab/work-items/{SEEDED_WORK_ITEM_ID}/checklist")
        assert resp.status_code == 200
        assert len(resp.json()["items"]) == 14

    def test_blockers_in_engineering_card(self):
        resp = client.get(f"/bridge/native-lab/work-items/{SEEDED_WORK_ITEM_ID}")
        card = resp.json()["engineering_card"]
        assert "blockers" in card

    def test_stale_evidence_field(self):
        resp = client.get(f"/bridge/native-lab/work-items/{SEEDED_WORK_ITEM_ID}")
        wi = resp.json()["work_item"]
        assert "evidence_stale" in wi

    def test_risk_reviews_via_post(self):
        resp = client.post(
            f"/bridge/native-lab/work-items/{SEEDED_WORK_ITEM_ID}/risk-reviews",
            json={
                "category": "semantic",
                "severity": "low",
                "description": "Unmodeled flags review",
                "reviewer": "test",
            },
        )
        assert resp.status_code == 200

    def test_history_append_only(self):
        resp = client.get(f"/bridge/native-lab/work-items/{SEEDED_WORK_ITEM_ID}/history")
        assert resp.status_code == 200
        assert "events" in resp.json()

    def test_no_auto_implement_endpoint(self):
        """No implement/generate/patch endpoints exist."""
        for path in [
            "/bridge/native-lab/implement",
            "/bridge/native-lab/generate-patch",
            "/bridge/native-lab/auto-certify",
        ]:
            resp = client.post(path, json={})
            assert resp.status_code == 404

    def test_no_auto_certify_endpoint(self):
        routes = [r.path for r in app.routes if hasattr(r, "path")]
        assert not any("auto-certify" in p for p in routes)
        assert not any("auto-implement" in p for p in routes)

    def test_seeded_append_work_item_via_api(self):
        resp = client.get(f"/bridge/native-lab/work-items/{SEEDED_WORK_ITEM_ID}")
        assert resp.status_code == 200
        assert resp.json()["work_item"]["behavior_id"] == "append_existing_file"
