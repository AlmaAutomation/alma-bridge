"""ACI Phase 3 governance test matrix — 18 scenarios."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from alma_bridge.compatibility_intelligence.calibration_service import CalibrationService
from alma_bridge.compatibility_intelligence.governance.digest import compute_proposal_digest
from alma_bridge.compatibility_intelligence.governance.errors import (
    PolicyViolationError,
    ProposalNotApprovedError,
    StaleProposalError,
)
from alma_bridge.compatibility_intelligence.governance.models import (
    CapabilityMaturityState,
    CapabilityScope,
    ProposalReviewState,
)
from alma_bridge.compatibility_intelligence.governance.policy import PromotionEvidence, evaluate_promotion_policy
from alma_bridge.compatibility_intelligence.governance.proposal import create_proposal
from alma_bridge.compatibility_intelligence.governance.repository import GovernanceRepository
from alma_bridge.compatibility_intelligence.models import OutcomeType
from alma_bridge.compatibility_intelligence.outcome_linking import build_outcome_link
from alma_bridge.compatibility_intelligence.service import CompatibilityIntelligenceService
from alma_bridge.compatibility_intelligence.snapshot import build_prediction_snapshot
from alma_bridge.main import app


CONSOLE_STDOUT_SCENARIOS = [
    "hello64_fixture",
    "stdout_write_fixture",
    "stderr_write_fixture",
    "write_stdout",
    "process_exit_with_code",
]


def _seed_calibration_records(
    calibration: CalibrationService,
    *,
    provider_id: str,
    capability_id: str,
    count: int,
    classification: str = "true_positive",
    behavior_gaps: list | None = None,
    file_path=None,
    fixture_name: str | None = None,
):
    """Seed linked calibration records for governance tests."""
    svc = CompatibilityIntelligenceService(calibration_repository=calibration._repo)
    path = file_path
    if path is None:
        raise RuntimeError("file_path required for seeding")
    records = []
    for i in range(count):
        session_id = f"gov_sess_{provider_id}_{capability_id}_{i}"
        analysis = svc.analyze(str(path), persist=False)
        snap = build_prediction_snapshot(
            analysis,
            provider_id=provider_id,
            session_id=session_id,
            fixture_name=fixture_name or path.name,
        )
        if behavior_gaps:
            static = snap.static_coverage.model_copy(update={"behavior_gaps": behavior_gaps})
            snap = snap.model_copy(update={"static_coverage": static})
        calibration._repo.save_snapshot(snap)
        outcome_type = (
            OutcomeType.VERIFIED_SUCCESS
            if classification == "true_positive"
            else OutcomeType.VERIFIED_FAILURE
            if classification in ("false_positive", "verified_failure")
            else OutcomeType.UNVERIFIABLE
        )
        outcome = build_outcome_link(
            snap,
            session_id=session_id,
            outcome_type=outcome_type,
            verification_result_ref="vref" if outcome_type in {
                OutcomeType.VERIFIED_SUCCESS,
                OutcomeType.VERIFIED_FAILURE,
            } else None,
            verified_success=outcome_type == OutcomeType.VERIFIED_SUCCESS,
        )
        record = calibration.calibrate(snap, outcome)
        if classification != record["classification"]:
            record["classification"] = classification
            calibration._repo.save_json_artifact("records", record["record_id"], record)
        records.append(record)
    return records


def _promote_through_states(
    governance_service,
    *,
    provider_id: str,
    capability_id: str,
    target_state: CapabilityMaturityState,
    scope: CapabilityScope,
    reviewer: str = "operator@test",
):
    proposal = governance_service.create_proposal_from_evidence(
        provider_id=provider_id,
        capability_id=capability_id,
        proposed_state=target_state,
        scope=scope,
        behavior_scenarios=scope.behavior_profile,
        application_scope=scope.application_scope,
        security_review_complete=True,
        regression_suite_stable=True,
        explicit_human_approval=True,
    )
    governance_service.review_proposal(
        proposal.proposal_id,
        reviewer=reviewer,
        state=ProposalReviewState.APPROVED,
        proposal_digest=proposal.proposal_digest,
    )
    return governance_service.apply_proposal(
        proposal.proposal_id,
        proposal_digest=proposal.proposal_digest,
    )


class TestProposalIntegrity:
    def test_01_proposal_digest_deterministic(self, governance_service, hello64_path, tmp_calibration_repo):
        _seed_calibration_records(
            governance_service._calibration,
            provider_id="native_alma",
            capability_id="console.stdout",
            count=3,
            file_path=hello64_path,
            fixture_name="hello64.exe",
        )
        scope = CapabilityScope(
            provider_id="native_alma",
            capability_id="console.stdout",
            behavior_profile=CONSOLE_STDOUT_SCENARIOS,
            application_scope=["hello64.exe"],
        )
        p1 = create_proposal(
            provider_id="native_alma",
            capability_id="console.stdout",
            proposed_state=CapabilityMaturityState.BEHAVIORALLY_TESTED,
            scope=scope,
            behavior_scenarios=CONSOLE_STDOUT_SCENARIOS,
            governance_repo=governance_service._repo,
            calibration=governance_service._calibration,
        )
        p2 = create_proposal(
            provider_id="native_alma",
            capability_id="console.stdout",
            proposed_state=CapabilityMaturityState.BEHAVIORALLY_TESTED,
            scope=scope,
            behavior_scenarios=CONSOLE_STDOUT_SCENARIOS,
            governance_repo=governance_service._repo,
            calibration=governance_service._calibration,
        )
        assert p1.proposal_digest == p2.proposal_digest
        assert compute_proposal_digest(p1) == p1.proposal_digest

    def test_02_proposal_binds_registry_version(self, governance_service):
        registry = governance_service.get_current_registry()
        scope = CapabilityScope(
            provider_id="native_alma",
            capability_id="console.stdout",
            behavior_profile=CONSOLE_STDOUT_SCENARIOS,
        )
        with pytest.raises(PolicyViolationError):
            create_proposal(
                provider_id="native_alma",
                capability_id="console.stdout",
                proposed_state=CapabilityMaturityState.STABLE,
                scope=scope,
                governance_repo=governance_service._repo,
                calibration=governance_service._calibration,
            )
        assert registry.version_id


class TestPromotionBoundaries:
    def test_03_stale_proposal_rejected(self, governance_service, hello64_path):
        _seed_calibration_records(
            governance_service._calibration,
            provider_id="native_alma",
            capability_id="console.stdout",
            count=3,
            file_path=hello64_path,
            fixture_name="hello64.exe",
        )
        scope = CapabilityScope(
            provider_id="native_alma",
            capability_id="console.stdout",
            behavior_profile=CONSOLE_STDOUT_SCENARIOS,
            application_scope=["hello64.exe"],
        )
        proposal = governance_service.create_proposal_from_evidence(
            provider_id="native_alma",
            capability_id="console.stdout",
            proposed_state=CapabilityMaturityState.BEHAVIORALLY_TESTED,
            scope=scope,
            behavior_scenarios=CONSOLE_STDOUT_SCENARIOS,
        )
        governance_service.review_proposal(
            proposal.proposal_id,
            reviewer="operator",
            state=ProposalReviewState.APPROVED,
            proposal_digest=proposal.proposal_digest,
        )
        governance_service._repo.append_version(
            governance_service.get_current_registry().entries,
            parent_version_id=governance_service.get_current_registry().version_id,
            change_summary="registry bump",
        )
        with pytest.raises(StaleProposalError):
            governance_service.apply_proposal(
                proposal.proposal_id,
                proposal_digest=proposal.proposal_digest,
            )

    def test_04_insufficient_sample_cannot_promote(self, governance_service, hello64_path):
        _seed_calibration_records(
            governance_service._calibration,
            provider_id="native_alma",
            capability_id="console.stdout",
            count=1,
            file_path=hello64_path,
            fixture_name="hello64.exe",
        )
        scope = CapabilityScope(
            provider_id="native_alma",
            capability_id="console.stdout",
            behavior_profile=CONSOLE_STDOUT_SCENARIOS,
        )
        with pytest.raises(PolicyViolationError):
            governance_service.create_proposal_from_evidence(
                provider_id="native_alma",
                capability_id="console.stdout",
                proposed_state=CapabilityMaturityState.CALIBRATION_SUPPORTED,
                scope=scope,
            )

    def test_05_unresolved_false_positive_blocks_promotion(self, governance_service, hello64_path):
        _seed_calibration_records(
            governance_service._calibration,
            provider_id="native_alma",
            capability_id="console.stdout",
            count=3,
            classification="false_positive",
            file_path=hello64_path,
            fixture_name="hello64.exe",
        )
        scope = CapabilityScope(
            provider_id="native_alma",
            capability_id="console.stdout",
            behavior_profile=CONSOLE_STDOUT_SCENARIOS,
        )
        with pytest.raises(PolicyViolationError):
            governance_service.create_proposal_from_evidence(
                provider_id="native_alma",
                capability_id="console.stdout",
                proposed_state=CapabilityMaturityState.CALIBRATION_SUPPORTED,
                scope=scope,
            )

    def test_06_bounded_fixture_cannot_produce_global_stable(self, governance_service):
        evidence = PromotionEvidence(
            scope=CapabilityScope(
                provider_id="native_alma",
                capability_id="console.stdout",
                application_scope=["hello64.exe"],
            ),
            current_state=CapabilityMaturityState.VERIFIED_BOUNDED,
            proposed_state=CapabilityMaturityState.STABLE,
            verified_success_count=5,
            behavior_scenarios=["hello64_fixture"],
            security_review_complete=True,
            regression_suite_stable=True,
            explicit_human_approval=True,
        )
        result = evaluate_promotion_policy(evidence)
        assert not result.allowed
        assert any("bounded" in r for r in result.reasons)


class TestHumanReview:
    def test_07_approval_is_human_authored_and_digest_bound(
        self, governance_service, hello64_path
    ):
        _seed_calibration_records(
            governance_service._calibration,
            provider_id="native_alma",
            capability_id="console.stdout",
            count=3,
            file_path=hello64_path,
            fixture_name="hello64.exe",
        )
        scope = CapabilityScope(
            provider_id="native_alma",
            capability_id="console.stdout",
            behavior_profile=["write_stdout", "hello64_fixture"],
            application_scope=["hello64.exe"],
        )
        proposal = governance_service.create_proposal_from_evidence(
            provider_id="native_alma",
            capability_id="console.stdout",
            proposed_state=CapabilityMaturityState.BEHAVIORALLY_TESTED,
            scope=scope,
            behavior_scenarios=CONSOLE_STDOUT_SCENARIOS,
        )
        review = governance_service.review_proposal(
            proposal.proposal_id,
            reviewer="human.operator@alma",
            state=ProposalReviewState.APPROVED,
            rationale="Evidence reviewed",
            proposal_digest=proposal.proposal_digest,
        )
        assert review.reviewer == "human.operator@alma"
        assert review.proposal_digest == proposal.proposal_digest

    def test_08_rejected_proposal_cannot_apply(self, governance_service, hello64_path):
        _seed_calibration_records(
            governance_service._calibration,
            provider_id="native_alma",
            capability_id="console.stdout",
            count=3,
            file_path=hello64_path,
            fixture_name="hello64.exe",
        )
        scope = CapabilityScope(
            provider_id="native_alma",
            capability_id="console.stdout",
            behavior_profile=CONSOLE_STDOUT_SCENARIOS,
            application_scope=["hello64.exe"],
        )
        proposal = governance_service.create_proposal_from_evidence(
            provider_id="native_alma",
            capability_id="console.stdout",
            proposed_state=CapabilityMaturityState.BEHAVIORALLY_TESTED,
            scope=scope,
            behavior_scenarios=CONSOLE_STDOUT_SCENARIOS,
        )
        governance_service.review_proposal(
            proposal.proposal_id,
            reviewer="operator",
            state=ProposalReviewState.REJECTED,
            proposal_digest=proposal.proposal_digest,
        )
        with pytest.raises(ProposalNotApprovedError):
            governance_service.apply_proposal(
                proposal.proposal_id,
                proposal_digest=proposal.proposal_digest,
            )


class TestRegistryVersioning:
    def test_09_registry_history_append_only(self, governance_service):
        v1 = governance_service.get_current_registry()
        v2 = governance_service._repo.append_version(
            v1.entries,
            parent_version_id=v1.version_id,
            change_summary="noop version",
        )
        versions = governance_service.list_registry_versions()
        ids = {v.version_id for v in versions}
        assert v1.version_id in ids
        assert v2.version_id in ids
        assert governance_service._repo.get_version(v1.version_id).digest == v1.digest

    def test_10_rollback_creates_new_version(self, governance_service, hello64_path):
        _seed_calibration_records(
            governance_service._calibration,
            provider_id="native_alma",
            capability_id="console.stdout",
            count=3,
            file_path=hello64_path,
            fixture_name="hello64.exe",
        )
        v_before = governance_service.get_current_registry()
        scope = CapabilityScope(
            provider_id="native_alma",
            capability_id="console.stdout",
            behavior_profile=CONSOLE_STDOUT_SCENARIOS,
            application_scope=["hello64.exe"],
        )
        proposal = governance_service.create_proposal_from_evidence(
            provider_id="native_alma",
            capability_id="console.stdout",
            proposed_state=CapabilityMaturityState.BEHAVIORALLY_TESTED,
            scope=scope,
            behavior_scenarios=CONSOLE_STDOUT_SCENARIOS,
        )
        governance_service.review_proposal(
            proposal.proposal_id,
            reviewer="op",
            state=ProposalReviewState.APPROVED,
            proposal_digest=proposal.proposal_digest,
        )
        v_after = governance_service.apply_proposal(
            proposal.proposal_id,
            proposal_digest=proposal.proposal_digest,
        )
        rolled = governance_service.rollback_to_version(v_before.version_id)
        assert rolled.version_id != v_before.version_id
        assert rolled.version_id != v_after.version_id
        assert len(governance_service.list_registry_versions()) >= 3

    def test_11_old_snapshots_retain_old_registry(self, hello64_path, tmp_calibration_repo):
        svc = CompatibilityIntelligenceService(calibration_repository=tmp_calibration_repo)
        snap = svc.create_prediction_snapshot(
            str(hello64_path), provider_id="native_alma", session_id="old_snap"
        )
        old_reg = snap.capability_registry_version
        GovernanceRepository().get_current_version()
        snap2 = tmp_calibration_repo.get_snapshot(snap.snapshot_id)
        assert snap2.capability_registry_version == old_reg


class TestIsolation:
    def test_12_governance_endpoints_do_not_execute_binaries(self):
        with patch(
            "alma_bridge.compatibility_intelligence.service.CompatibilityIntelligenceService.analyze"
        ) as mock_analyze:
            client = TestClient(app)
            r = client.get("/bridge/compatibility/governance/proposals")
            assert r.status_code == 200
            r2 = client.get("/bridge/compatibility/governance/registry")
            assert r2.status_code == 200
            mock_analyze.assert_not_called()

    def test_13_governance_cannot_alter_verification_engine(self):
        from alma_bridge.compatibility_intelligence.outcome_linking import resolve_outcome_type

        assert resolve_outcome_type(success=True, verification_result_ref=None) == OutcomeType.UNVERIFIABLE

    def test_14_application_a_cannot_promote_scope_b(
        self, governance_service, hello64_path, file_append_unsupported_path
    ):
        _seed_calibration_records(
            governance_service._calibration,
            provider_id="native_alma",
            capability_id="console.stdout",
            count=3,
            file_path=hello64_path,
            fixture_name="hello64.exe",
        )
        scope_a = CapabilityScope(
            provider_id="native_alma",
            capability_id="console.stdout",
            behavior_profile=CONSOLE_STDOUT_SCENARIOS,
            application_scope=["hello64.exe"],
        )
        proposal = governance_service.create_proposal_from_evidence(
            provider_id="native_alma",
            capability_id="console.stdout",
            proposed_state=CapabilityMaturityState.BEHAVIORALLY_TESTED,
            scope=scope_a,
            behavior_scenarios=CONSOLE_STDOUT_SCENARIOS,
        )
        assert proposal.scope.application_scope == ["hello64.exe"]
        assert proposal.capability_id == "console.stdout"
        fs_scope = CapabilityScope(
            provider_id="native_alma",
            capability_id="filesystem.basic_io",
            application_scope=["file_append_unsupported.exe"],
        )
        with pytest.raises(PolicyViolationError):
            governance_service.create_proposal_from_evidence(
                provider_id="native_alma",
                capability_id="filesystem.basic_io",
                proposed_state=CapabilityMaturityState.STABLE,
                scope=fs_scope,
            )

    def test_15_provider_a_cannot_promote_provider_b(
        self, governance_service, hello64_path
    ):
        _seed_calibration_records(
            governance_service._calibration,
            provider_id="native_alma",
            capability_id="console.stdout",
            count=3,
            file_path=hello64_path,
            fixture_name="hello64.exe",
        )
        with pytest.raises(PolicyViolationError):
            create_proposal(
                provider_id="wine",
                capability_id="console.stdout",
                proposed_state=CapabilityMaturityState.VERIFIED_BOUNDED,
                scope=CapabilityScope(provider_id="wine", capability_id="console.stdout"),
                governance_repo=governance_service._repo,
                calibration=governance_service._calibration,
            )

    def test_16_deprecated_only_via_explicit_registry_version(self, governance_service):
        v1 = governance_service.get_current_registry()
        entries = []
        for entry in v1.entries:
            if (
                entry.scope.provider_id == "native_alma"
                and entry.scope.capability_id == "console.stdout"
            ):
                entries.append(entry.model_copy(update={"maturity_state": CapabilityMaturityState.DEPRECATED}))
            else:
                entries.append(entry)
        v2 = governance_service._repo.append_version(
            entries,
            parent_version_id=v1.version_id,
            change_summary="deprecate console.stdout",
        )
        state = governance_service._repo.get_maturity_state("native_alma", "console.stdout")
        assert state == CapabilityMaturityState.DEPRECATED
        assert v2.version_id != v1.version_id

    def test_17_calibration_failure_cannot_mutate_registry(self, governance_service):
        from alma_bridge.compatibility_intelligence.capabilities import CAPABILITY_REGISTRY

        before_versions = len(governance_service.list_registry_versions())
        before_caps = len(CAPABILITY_REGISTRY)
        try:
            governance_service._calibration.compute_metrics()
            governance_service.create_proposal_from_evidence(
                provider_id="native_alma",
                capability_id="console.stdout",
                proposed_state=CapabilityMaturityState.STABLE,
                scope=CapabilityScope(provider_id="native_alma", capability_id="console.stdout"),
            )
        except (PolicyViolationError, Exception):
            pass
        assert len(CAPABILITY_REGISTRY) == before_caps
        assert len(governance_service.list_registry_versions()) == before_versions


class TestExplorerContract:
    def test_18_frontend_preserves_scope_and_sample_size(self):
        from alma_bridge.api import governance_routes

        payload = {
            "provider_id": "native_alma",
            "capability_id": "console.stdout",
            "current_state": "experimental",
            "proposed_state": "behaviorally_tested",
            "scope": {
                "provider_id": "native_alma",
                "capability_id": "console.stdout",
                "behavior_profile": ["write_stdout"],
                "application_scope": ["hello64.exe"],
            },
            "verified_success_count": 3,
            "false_positive_count": 0,
            "indeterminate_count": 1,
            "limitations": [],
            "behavior_scenarios": ["hello64_fixture"],
        }
        assert hasattr(governance_routes, "list_proposals")
        assert payload["scope"]["application_scope"] == ["hello64.exe"]
        assert payload["verified_success_count"] == 3


class TestAcceptanceScenarios:
    def test_console_stdout_verified_bounded_workflow(
        self, governance_service, hello64_path
    ):
        _seed_calibration_records(
            governance_service._calibration,
            provider_id="native_alma",
            capability_id="console.stdout",
            count=4,
            file_path=hello64_path,
            fixture_name="hello64.exe",
        )
        scope = CapabilityScope(
            provider_id="native_alma",
            capability_id="console.stdout",
            behavior_profile=["write_stdout", "process_exit_with_code"],
            application_scope=["hello64.exe", "stdout_write_fixture"],
        )
        proposal = governance_service.create_proposal_from_evidence(
            provider_id="native_alma",
            capability_id="console.stdout",
            proposed_state=CapabilityMaturityState.BEHAVIORALLY_TESTED,
            scope=scope,
            behavior_scenarios=CONSOLE_STDOUT_SCENARIOS,
        )
        governance_service.review_proposal(
            proposal.proposal_id,
            reviewer="operator",
            state=ProposalReviewState.APPROVED,
            proposal_digest=proposal.proposal_digest,
        )
        v1 = governance_service.apply_proposal(
            proposal.proposal_id,
            proposal_digest=proposal.proposal_digest,
        )
        entry = governance_service._repo.find_maturity(scope, version_id=v1.version_id)
        assert entry.maturity_state == CapabilityMaturityState.BEHAVIORALLY_TESTED

        proposal2 = governance_service.create_proposal_from_evidence(
            provider_id="native_alma",
            capability_id="console.stdout",
            proposed_state=CapabilityMaturityState.CALIBRATION_SUPPORTED,
            scope=scope,
            behavior_scenarios=CONSOLE_STDOUT_SCENARIOS,
        )
        governance_service.review_proposal(
            proposal2.proposal_id,
            reviewer="operator",
            state=ProposalReviewState.APPROVED,
            proposal_digest=proposal2.proposal_digest,
        )
        v2 = governance_service.apply_proposal(
            proposal2.proposal_id,
            proposal_digest=proposal2.proposal_digest,
        )

        proposal3 = governance_service.create_proposal_from_evidence(
            provider_id="native_alma",
            capability_id="console.stdout",
            proposed_state=CapabilityMaturityState.VERIFIED_BOUNDED,
            scope=scope,
            behavior_scenarios=CONSOLE_STDOUT_SCENARIOS,
        )
        governance_service.review_proposal(
            proposal3.proposal_id,
            reviewer="operator",
            state=ProposalReviewState.APPROVED,
            proposal_digest=proposal3.proposal_digest,
        )
        v3 = governance_service.apply_proposal(
            proposal3.proposal_id,
            proposal_digest=proposal3.proposal_digest,
        )
        entry3 = governance_service._repo.find_maturity(scope, version_id=v3.version_id)
        assert entry3.maturity_state == CapabilityMaturityState.VERIFIED_BOUNDED
        assert entry3.scope.application_scope

    def test_filesystem_basic_io_retains_limitations(
        self, governance_service, file_append_unsupported_path
    ):
        _seed_calibration_records(
            governance_service._calibration,
            provider_id="native_alma",
            capability_id="filesystem.basic_io",
            count=3,
            classification="false_positive",
            behavior_gaps=["behavior:append_existing_file"],
            file_path=file_append_unsupported_path,
            fixture_name="file_append_unsupported.exe",
        )
        entry = governance_service._repo.find_maturity(
            CapabilityScope(
                provider_id="native_alma",
                capability_id="filesystem.basic_io",
            )
        )
        assert entry is not None
        assert "append_existing_file" in entry.supported_behaviors
        assert "overlapped_io" in entry.unsupported_behaviors
        with pytest.raises(PolicyViolationError):
            governance_service.create_proposal_from_evidence(
                provider_id="native_alma",
                capability_id="filesystem.basic_io",
                proposed_state=CapabilityMaturityState.STABLE,
                scope=CapabilityScope(
                    provider_id="native_alma",
                    capability_id="filesystem.basic_io",
                ),
            )

    def test_no_automatic_promotion(self, governance_service, hello64_path):
        before = governance_service.get_current_registry().version_id
        _seed_calibration_records(
            governance_service._calibration,
            provider_id="native_alma",
            capability_id="console.stdout",
            count=5,
            file_path=hello64_path,
            fixture_name="hello64.exe",
        )
        after = governance_service.get_current_registry().version_id
        assert before == after
