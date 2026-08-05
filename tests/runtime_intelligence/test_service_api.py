"""Tests for RuntimeIntelligenceService and HTTP API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from alma_bridge.evidence.models import Provenance, TimelineEvent, TimelineEventType
from alma_bridge.main import create_app
from alma_bridge.runtime_intelligence.hypotheses import create_hypothesis_snapshot, create_outcome_link
from alma_bridge.runtime_intelligence.models import (
    BehaviorFamilyId,
    CompatibilityIndexStatus,
    CorpusKind,
    HypothesisTimelineConflictError,
    TimelineAppendStatus,
)
from alma_bridge.runtime_intelligence.service import RuntimeIntelligenceService


CREATED = "2026-08-01T00:00:00+00:00"
LINKED = "2026-08-15T00:00:00+00:00"


def _service(corpus_resolver) -> RuntimeIntelligenceService:
    from alma_bridge.runtime_intelligence.queries import RuntimeIntelligenceQueries

    queries = RuntimeIntelligenceQueries(
        corpus_resolver=corpus_resolver,
        evidence_queries=MagicMock(list_bundle_ids=MagicMock(return_value=[]), timeline=MagicMock(return_value=[])),
        analysis_repo=MagicMock(list_recent=MagicMock(return_value=[])),
        calibration_service=MagicMock(list_records=MagicMock(return_value=[])),
        governance_repo=MagicMock(get_current_version=MagicMock(side_effect=RuntimeError("no gov"))),
        certification_service=MagicMock(
            get_behavior_certification=MagicMock(side_effect=RuntimeError("no cert"))
        ),
        expansion_repo=MagicMock(get_latest_plan=MagicMock(side_effect=RuntimeError("no plan"))),
    )
    return RuntimeIntelligenceService(queries=queries, evidence_repo=MagicMock())


def _snapshot(**overrides):
    defaults = {
        "created_at": CREATED,
        "corpus": CorpusKind.ENGINEERING,
        "provider_id": "native_alma",
        "provider_version_scope": "0.2.1-m2",
        "family_id": BehaviorFamilyId.FILESYSTEM,
        "capability_id": "filesystem.basic_io",
        "behavior_id": "append_existing_file",
        "bounded_scope": "append_existing_file within workspace-confined PE64",
        "evidence_snapshot_digest": "snap-hyp",
        "evidence_references": ["evidence-pre-001"],
        "predicted_application_fingerprints": ["d87ac1f8a7c5bd11ffa5ccb00cf18d77edd5ce075a5b37835770e32feca15aaf"],
    }
    defaults.update(overrides)
    return create_hypothesis_snapshot(**defaults)


@pytest.fixture
def service(corpus_resolver):
    return _service(corpus_resolver)


@pytest.fixture
def client():
    return TestClient(create_app())


class TestRuntimeIntelligenceService:
    def test_get_index(self, service, engineering_corpus):
        report = service.get_index(
            engineering_corpus,
            BehaviorFamilyId.FILESYSTEM,
            "native_alma",
        )
        assert report.corpus == engineering_corpus

    def test_get_knowledge(self, service, engineering_corpus):
        report = service.get_knowledge(
            engineering_corpus,
            BehaviorFamilyId.FILESYSTEM,
            "native_alma",
        )
        assert report.corpus == engineering_corpus

    def test_get_debt(self, service, engineering_corpus):
        report = service.get_debt(
            engineering_corpus,
            BehaviorFamilyId.FILESYSTEM,
            "native_alma",
        )
        assert report.corpus == engineering_corpus

    def test_list_hypotheses(self, service, engineering_corpus):
        assert service.list_hypotheses(engineering_corpus) == []

    def test_get_hypothesis_not_found(self, service, engineering_corpus):
        from alma_bridge.runtime_intelligence.models import HypothesisNotFoundError

        with pytest.raises(HypothesisNotFoundError):
            service.get_hypothesis(engineering_corpus, "missing-hypothesis")

    def test_get_report(self, service, engineering_corpus):
        report = service.get_report(engineering_corpus)
        assert report.corpus == engineering_corpus
        assert report.report_digest

    def test_report_has_no_global_score(self, service, engineering_corpus):
        report = service.get_report(engineering_corpus)
        payload = report.model_dump()
        assert "global_score" not in payload

    def test_report_keeps_families_separate(self, service, engineering_corpus):
        report = service.get_report(engineering_corpus)
        family_ids = {item.family_id for item in report.compatibility_indexes}
        assert len(family_ids) >= 2

    def test_report_digest_deterministic(self, service, engineering_corpus):
        with patch("alma_bridge.runtime_intelligence.service.utc_now_iso", return_value="2026-08-01T00:00:00+00:00"):
            r1 = service.get_report(engineering_corpus)
            r2 = service.get_report(engineering_corpus)
        assert r1.report_digest == r2.report_digest

    def test_generated_at_excluded_from_digest(self, service, engineering_corpus):
        with patch("alma_bridge.runtime_intelligence.service.utc_now_iso", return_value="2026-08-01T00:00:00+00:00"):
            r1 = service.get_report(engineering_corpus)
        with patch("alma_bridge.runtime_intelligence.service.utc_now_iso", return_value="2026-08-02T00:00:00+00:00"):
            r2 = service.get_report(engineering_corpus)
        assert r1.report_digest == r2.report_digest
        assert r1.generated_at != r2.generated_at

    def test_limitations_preserved(self, service, engineering_corpus):
        report = service.get_report(engineering_corpus)
        assert isinstance(report.limitations, list)

    def test_evidence_refs_preserved(self, service, engineering_corpus):
        report = service.get_report(engineering_corpus)
        assert isinstance(report.evidence_references, list)

    def test_created_event_appended(self, service):
        snap = _snapshot()
        repo = MagicMock()
        repo.list_timeline_events.return_value = []
        service._repo = repo
        service._evidence = MagicMock(timeline=MagicMock(return_value=[]))
        service._queries._corpus.is_enrolled = MagicMock(return_value=True)
        service._evidence.by_application_fingerprint = MagicMock(return_value=MagicMock(bundle_id="bundle-1"))
        result = service.record_hypothesis_created(snap)
        assert result.status == TimelineAppendStatus.APPENDED
        repo.append_timeline_event.assert_called_once()

    def test_outcome_linked_event_appended(self, service):
        snap = _snapshot()
        link = create_outcome_link(
            snapshot=snap,
            linked_at=LINKED,
            evidence_snapshot_digest="snap-out",
            evidence_references=["evidence-post-001"],
        )
        repo = MagicMock()
        repo.list_timeline_events.return_value = []
        service._repo = repo
        service._evidence = MagicMock(
            timeline=MagicMock(return_value=[]),
            list_bundle_ids=MagicMock(return_value=[]),
            by_application_fingerprint=MagicMock(return_value=None),
        )
        result = service.record_hypothesis_outcome_linked(link)
        assert result.status == TimelineAppendStatus.APPENDED

    def test_duplicate_append_idempotent(self, service):
        snap = _snapshot()
        existing = TimelineEvent(
            event_id="evt-dup",
            event_type=TimelineEventType.ENGINEERING_HYPOTHESIS_CREATED,
            timestamp=CREATED,
            version=1,
            evidence_digest=snap.snapshot_digest,
            source="runtime_intelligence",
            references=[snap.hypothesis_id],
            provenance=Provenance(
                source="runtime_intelligence",
                artifact_id=snap.hypothesis_id,
                digest=snap.snapshot_digest,
            ),
            metadata={"hypothesis_id": snap.hypothesis_id},
        )
        service._evidence = MagicMock(timeline=MagicMock(return_value=[existing]))
        service._queries._corpus.is_enrolled = MagicMock(return_value=True)
        service._evidence.by_application_fingerprint = MagicMock(return_value=MagicMock(bundle_id="bundle-1"))
        result = service.record_hypothesis_created(snap)
        assert result.status == TimelineAppendStatus.DUPLICATE

    def test_conflicting_immutable_payload_rejected(self, service):
        snap = _snapshot()
        existing = TimelineEvent(
            event_id="evt-conflict",
            event_type=TimelineEventType.ENGINEERING_HYPOTHESIS_CREATED,
            timestamp=CREATED,
            version=1,
            evidence_digest="different-digest",
            source="runtime_intelligence",
            references=[snap.hypothesis_id],
            provenance=Provenance(
                source="runtime_intelligence",
                artifact_id=snap.hypothesis_id,
                digest="different-digest",
            ),
            metadata={"hypothesis_id": snap.hypothesis_id},
        )
        service._evidence = MagicMock(timeline=MagicMock(return_value=[existing]))
        service._queries._corpus.is_enrolled = MagicMock(return_value=True)
        service._evidence.by_application_fingerprint = MagicMock(return_value=MagicMock(bundle_id="bundle-1"))
        with pytest.raises(HypothesisTimelineConflictError):
            service.record_hypothesis_created(snap)

    def test_snapshot_not_mutated_on_record(self, service):
        snap = _snapshot()
        digest_before = snap.snapshot_digest
        service._evidence = MagicMock(timeline=MagicMock(return_value=[]))
        service._queries._corpus.is_enrolled = MagicMock(return_value=True)
        service._evidence.by_application_fingerprint = MagicMock(return_value=MagicMock(bundle_id="bundle-1"))
        service._repo = MagicMock()
        service.record_hypothesis_created(snap)
        assert snap.snapshot_digest == digest_before

    def test_get_methods_do_not_append_events(self, service, engineering_corpus):
        service._repo = MagicMock()
        service.get_index(engineering_corpus, BehaviorFamilyId.FILESYSTEM, "native_alma")
        service.get_report(engineering_corpus)
        service._repo.append_timeline_event.assert_not_called()

    def test_timeline_failure_isolated(self, service):
        snap = _snapshot()
        service._evidence = MagicMock(timeline=MagicMock(return_value=[]))
        service._queries._corpus.is_enrolled = MagicMock(return_value=True)
        service._evidence.by_application_fingerprint = MagicMock(return_value=MagicMock(bundle_id="bundle-1"))
        service._repo = MagicMock(append_timeline_event=MagicMock(side_effect=RuntimeError("timeline down")))
        with pytest.raises(RuntimeError):
            service.record_hypothesis_created(snap)


class TestRuntimeIntelligenceAPI:
    def test_families_route_ok(self, client):
        response = client.get("/bridge/runtime-intelligence/families?corpus=engineering")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_family_detail_route_ok(self, client):
        response = client.get(
            "/bridge/runtime-intelligence/families/filesystem?corpus=engineering"
        )
        assert response.status_code == 200

    def test_index_route_ok(self, client):
        response = client.get(
            "/bridge/runtime-intelligence/index"
            "?corpus=engineering&family_id=filesystem&provider_id=native_alma"
        )
        assert response.status_code == 200

    def test_knowledge_route_ok(self, client):
        response = client.get(
            "/bridge/runtime-intelligence/knowledge"
            "?corpus=engineering&family_id=filesystem&provider_id=native_alma"
        )
        assert response.status_code == 200

    def test_debt_route_ok(self, client):
        response = client.get(
            "/bridge/runtime-intelligence/debt"
            "?corpus=engineering&family_id=filesystem&provider_id=native_alma"
        )
        assert response.status_code == 200

    def test_hypotheses_route_ok(self, client):
        response = client.get("/bridge/runtime-intelligence/hypotheses?corpus=engineering")
        assert response.status_code == 200

    def test_history_route_ok(self, client):
        response = client.get(
            "/bridge/runtime-intelligence/history"
            "?corpus=engineering&metric_id=compatibility_index&family_id=filesystem&provider_id=native_alma"
        )
        assert response.status_code == 200

    def test_report_route_ok(self, client):
        response = client.get("/bridge/runtime-intelligence/report?corpus=engineering")
        assert response.status_code == 200

    def test_missing_corpus_returns_400(self, client):
        response = client.get("/bridge/runtime-intelligence/families")
        assert response.status_code == 400

    def test_invalid_corpus_rejected(self, client):
        response = client.get("/bridge/runtime-intelligence/families?corpus=combined")
        assert response.status_code == 400

    def test_invalid_family_rejected(self, client):
        response = client.get(
            "/bridge/runtime-intelligence/index"
            "?corpus=engineering&family_id=invalid&provider_id=native_alma"
        )
        assert response.status_code == 400

    def test_hypothesis_not_found_returns_404(self, client):
        response = client.get(
            "/bridge/runtime-intelligence/hypotheses/missing-id?corpus=engineering"
        )
        assert response.status_code == 404

    def test_post_returns_405(self, client):
        response = client.post("/bridge/runtime-intelligence/report?corpus=engineering")
        assert response.status_code == 405

    def test_put_returns_405(self, client):
        response = client.put("/bridge/runtime-intelligence/report?corpus=engineering")
        assert response.status_code == 405

    def test_patch_returns_405(self, client):
        response = client.patch("/bridge/runtime-intelligence/report?corpus=engineering")
        assert response.status_code == 405

    def test_delete_returns_405(self, client):
        response = client.delete("/bridge/runtime-intelligence/report?corpus=engineering")
        assert response.status_code == 405

    def test_missing_optional_evidence_returns_insufficient_not_500(self, client):
        response = client.get(
            "/bridge/runtime-intelligence/index"
            "?corpus=engineering&family_id=filesystem&provider_id=native_alma"
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] in (
            CompatibilityIndexStatus.COMPUTED.value,
            CompatibilityIndexStatus.INSUFFICIENT_EVIDENCE.value,
        )

    def test_real_world_corpus_ok(self, client):
        response = client.get("/bridge/runtime-intelligence/report?corpus=real_world")
        assert response.status_code == 200
