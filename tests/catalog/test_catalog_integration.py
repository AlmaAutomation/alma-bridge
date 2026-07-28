"""Integration tests for catalog aggregation and API."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from alma_bridge.catalog.service import CompatibilityCatalogService
from alma_bridge.graph.ingestion import GraphIngestionEngine
from alma_bridge.graph.models import GraphEdgeType, GraphNodeType
from alma_bridge.graph.repository import GraphStore, ReadOnlyGraphEvidenceAdapter
from alma_bridge.intelligence.evidence import EvidenceBundleBuilder
from alma_bridge.knowledge.aggregation import KnowledgeAggregationEngine
from alma_bridge.regression.service import CompatibilityRegressionService
from alma_bridge.storage import outcomes
from tests.catalog.conftest import (
    APP_A_FINGERPRINT,
    APP_B_FINGERPRINT,
    ENV_SESSION_WINE_10,
    ENV_SESSION_WINE_9,
    seed_catalog_acceptance_data,
)
from tests.intelligence.conftest import seed_codeblocks_session


@pytest.fixture
def isolated_catalog_store(tmp_path, monkeypatch):
    db_path = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db_path)
    monkeypatch.setattr("alma_bridge.graph.repository.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.graph.repository.settings.db_path", db_path)
    outcomes.init_outcome_store()
    yield tmp_path


class TestCatalogAggregation:
    def test_catalog_returns_correct_aggregates(self, isolated_catalog_store):
        seed_catalog_acceptance_data()
        service = CompatibilityCatalogService()
        catalog = service.list_applications()
        assert len(catalog.applications) == 2
        app_a = next(item for item in catalog.applications if item.fingerprint == APP_A_FINGERPRINT)
        app_b = next(item for item in catalog.applications if item.fingerprint == APP_B_FINGERPRINT)
        assert app_a.total_sessions >= 6
        assert app_a.verified_successes >= 2
        assert app_a.latest_environment_summary is not None
        assert "wine" in app_a.latest_environment_summary.lower()
        assert app_b.total_sessions == 1
        assert app_b.fingerprint != app_a.fingerprint

    def test_application_a_cannot_leak_to_b(self, isolated_catalog_store):
        seed_catalog_acceptance_data()
        service = CompatibilityCatalogService()
        catalog = service.list_applications()
        app_b = next(item for item in catalog.applications if item.fingerprint == APP_B_FINGERPRINT)
        assert APP_A_FINGERPRINT not in app_b.name
        assert app_b.total_sessions == 1

    def test_legacy_sessions_without_environment_still_work(self, isolated_catalog_store):
        seed_codeblocks_session()
        service = CompatibilityCatalogService()
        catalog = service.list_applications()
        entry = catalog.applications[0]
        assert entry.total_sessions == 1
        assert entry.latest_environment_summary is None


class TestEnvironmentEvidencePipeline:
    def test_environment_persisted_immutable(self, isolated_catalog_store):
        from tests.catalog.conftest import _make_environment, seed_session_with_environment

        seed_session_with_environment(
            session_id=ENV_SESSION_WINE_9,
            fingerprint=APP_A_FINGERPRINT,
            wine_version="wine-9.0",
            prefix_path="/tmp/a",
        )
        session = outcomes.get_session(ENV_SESSION_WINE_9)
        first = session["run_environment"]
        outcomes.set_session_run_environment(
            ENV_SESSION_WINE_9,
            _make_environment(wine_version="wine-99.0", prefix_path="/tmp/b"),
        )
        session_after = outcomes.get_session(ENV_SESSION_WINE_9)
        assert session_after["run_environment"] == first

    def test_graph_has_environment_node_and_edge(self, isolated_catalog_store):
        seed_catalog_acceptance_data()
        adapter = ReadOnlyGraphEvidenceAdapter()
        store = GraphStore()
        engine = GraphIngestionEngine(adapter, store=store)
        subgraph = engine.ingest_session(ENV_SESSION_WINE_10)
        node_types = {node.node_type for node in subgraph.nodes}
        edge_types = {edge.edge_type for edge in subgraph.edges}
        assert GraphNodeType.ENVIRONMENT in node_types
        assert GraphEdgeType.SESSION_USED_ENVIRONMENT in edge_types

    def test_knowledge_includes_observed_environments(self, isolated_catalog_store):
        seed_catalog_acceptance_data()
        builder = EvidenceBundleBuilder(ReadOnlyGraphEvidenceAdapter())
        bundle = builder.for_application(APP_A_FINGERPRINT)
        profile = KnowledgeAggregationEngine().aggregate(bundle)
        assert len(profile.observed_environments) >= 2
        identities = {item.environment_identity for item in profile.observed_environments}
        assert len(identities) >= 2
        assert all(item.evidence_references for item in profile.observed_environments)

    def test_two_wine_versions_compare_with_evidence(self, isolated_catalog_store):
        seed_catalog_acceptance_data()
        service = CompatibilityRegressionService()
        report = service.report_for_application(
            APP_A_FINGERPRINT,
            session_id=ENV_SESSION_WINE_10,
        )
        env_findings = [
            item for item in report.findings if item.regression_type.value == "environment_changed"
        ]
        assert env_findings
        summary = env_findings[0].summary.lower()
        assert "differs" in summary
        assert "because" not in summary
        assert "caused" not in summary
        assert env_findings[0].evidence_references


class TestCatalogApi:
    def test_catalog_endpoint(self, isolated_catalog_store):
        from alma_bridge.main import create_app

        seed_catalog_acceptance_data()
        client = TestClient(create_app())
        response = client.get("/bridge/catalog/applications")
        assert response.status_code == 200
        payload = response.json()
        assert payload["schema_version"] == "compatibility_catalog_v1"
        fingerprints = {item["fingerprint"] for item in payload["applications"]}
        assert APP_A_FINGERPRINT in fingerprints
        assert APP_B_FINGERPRINT in fingerprints
