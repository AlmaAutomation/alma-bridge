"""Orchestration for prediction calibration — compare snapshots to verified outcomes."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from alma_bridge.compatibility_intelligence.calibration import (
    attribute_failure,
    classify_calibration,
)
from alma_bridge.compatibility_intelligence.calibration_repository import (
    CalibrationRepository,
    _utc_now_iso,
)
from alma_bridge.compatibility_intelligence.models import (
    ACI_CALIBRATION_SCHEMA_VERSION,
    CalibrationClassification,
    FailureAttribution,
    OutcomeLink,
    PredictionSnapshot,
)
from alma_bridge.compatibility_intelligence.outcome_linking import OutcomeLinkingService
from alma_bridge.compatibility.profile_fingerprints import sha256_v1


CALIBRATION_ENGINE_VERSION = "aci_calibration_v1"


class CalibrationRecord(dict):
    """Typed dict for calibration records stored as JSON."""

    pass


class CalibrationMetrics:
    """Aggregated calibration metrics with sample sizes."""

    def __init__(
        self,
        *,
        total_records: int = 0,
        indeterminate_count: int = 0,
        true_positive_count: int = 0,
        false_positive_count: int = 0,
        true_negative_count: int = 0,
        false_negative_count: int = 0,
        by_provider: Optional[Dict[str, dict]] = None,
        by_capability: Optional[Dict[str, dict]] = None,
    ) -> None:
        self.total_records = total_records
        self.indeterminate_count = indeterminate_count
        self.true_positive_count = true_positive_count
        self.false_positive_count = false_positive_count
        self.true_negative_count = true_negative_count
        self.false_negative_count = false_negative_count
        self.by_provider = by_provider or {}
        self.by_capability = by_capability or {}

    def to_dict(self) -> dict:
        authoritative = (
            self.true_positive_count
            + self.false_positive_count
            + self.true_negative_count
            + self.false_negative_count
        )
        return {
            "total_records": self.total_records,
            "authoritative_sample_size": authoritative,
            "indeterminate_count": self.indeterminate_count,
            "true_positive": self._rate(self.true_positive_count, authoritative),
            "false_positive": self._rate(self.false_positive_count, authoritative),
            "true_negative": self._rate(self.true_negative_count, authoritative),
            "false_negative": self._rate(self.false_negative_count, authoritative),
            "by_provider": self.by_provider,
            "by_capability": self.by_capability,
            "engine_version": CALIBRATION_ENGINE_VERSION,
        }

    @staticmethod
    def _rate(numerator: int, denominator: int) -> dict:
        rate = round(numerator / denominator, 4) if denominator > 0 else 0.0
        return {"count": numerator, "denominator": denominator, "rate": rate}


class CalibrationService:
    """Compare prediction snapshots to verified outcomes and compute metrics."""

    def __init__(
        self,
        repository: Optional[CalibrationRepository] = None,
        linking: Optional[OutcomeLinkingService] = None,
    ) -> None:
        self._repo = repository or CalibrationRepository()
        self._linking = linking or OutcomeLinkingService(self._repo)

    def calibrate(
        self,
        snapshot: PredictionSnapshot,
        outcome: OutcomeLink,
    ) -> dict:
        classification = classify_calibration(snapshot, outcome)
        failure_attr = attribute_failure(
            snapshot,
            outcome,
            classification=classification,
        )
        ts = _utc_now_iso()
        record = {
            "schema_version": ACI_CALIBRATION_SCHEMA_VERSION,
            "record_id": sha256_v1(
                {
                    "snapshot_id": snapshot.snapshot_id,
                    "outcome_id": outcome.outcome_id,
                    "classification": classification.value,
                }
            ),
            "snapshot_id": snapshot.snapshot_id,
            "outcome_id": outcome.outcome_id,
            "session_id": outcome.session_id,
            "binary_digest": snapshot.binary_digest,
            "analysis_digest": snapshot.analysis_digest,
            "provider_id": snapshot.provider_id,
            "classification": classification.value,
            "failure_attribution": failure_attr.value if failure_attr else None,
            "predicted_eligible": snapshot.predicted_eligible,
            "outcome_type": outcome.outcome_type.value,
            "verified_success": outcome.verified_success,
            "behavior_gaps": snapshot.static_coverage.behavior_gaps,
            "capability_registry_version": snapshot.capability_registry_version,
            "api_registry_version": snapshot.api_registry_version,
            "created_at": ts,
            "engine_version": CALIBRATION_ENGINE_VERSION,
        }
        self._repo.save_json_artifact("records", record["record_id"], record)
        return record

    def calibrate_session(self, session_id: str) -> List[dict]:
        snapshot = self._repo.get_snapshot_by_session(session_id)
        if snapshot is None:
            return []
        outcomes = self._linking.list_outcomes_for_session(session_id)
        return [self.calibrate(snapshot, o) for o in outcomes]

    def list_records(self, limit: int = 500) -> List[dict]:
        return self._repo.list_json_artifacts("records", limit=limit)

    def list_records_for_analysis(self, analysis_digest: str) -> List[dict]:
        return [
            r
            for r in self.list_records()
            if r.get("analysis_digest") == analysis_digest
        ]

    def list_records_for_capability(self, capability_id: str) -> List[dict]:
        results: List[dict] = []
        for record in self.list_records():
            snap = self._repo.get_snapshot(str(record.get("snapshot_id", "")))
            if snap and capability_id in snap.required_capabilities:
                results.append(record)
        return results

    def compute_metrics(
        self,
        *,
        provider_id: Optional[str] = None,
        capability_id: Optional[str] = None,
    ) -> CalibrationMetrics:
        records = self.list_records()
        if capability_id:
            records = [r for r in records if capability_id in self._cap_ids(r)]
        if provider_id:
            records = [r for r in records if r.get("provider_id") == provider_id]

        metrics = CalibrationMetrics(total_records=len(records))
        by_provider: Dict[str, dict] = defaultdict(
            lambda: {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "indeterminate": 0}
        )
        by_capability: Dict[str, dict] = defaultdict(
            lambda: {"tp": 0, "fp": 0, "tn": 0, "fn": 0, "indeterminate": 0}
        )

        for record in records:
            cls = record.get("classification", "")
            pid = str(record.get("provider_id", ""))
            bucket = by_provider[pid]
            self._increment_bucket(bucket, cls, metrics)
            for cap in self._cap_ids(record):
                cap_bucket = by_capability[cap]
                self._increment_bucket(cap_bucket, cls, metrics)

        metrics.by_provider = {
            pid: self._bucket_to_rates(b) for pid, b in sorted(by_provider.items())
        }
        metrics.by_capability = {
            cid: self._bucket_to_rates(b) for cid, b in sorted(by_capability.items())
        }
        return metrics

    def _cap_ids(self, record: dict) -> List[str]:
        snap = self._repo.get_snapshot(str(record.get("snapshot_id", "")))
        if snap:
            return snap.required_capabilities
        return []

    @staticmethod
    def _increment_bucket(bucket: dict, classification: str, metrics: CalibrationMetrics) -> None:
        if classification == CalibrationClassification.TRUE_POSITIVE.value:
            bucket["tp"] += 1
            metrics.true_positive_count += 1
        elif classification == CalibrationClassification.FALSE_POSITIVE.value:
            bucket["fp"] += 1
            metrics.false_positive_count += 1
        elif classification == CalibrationClassification.TRUE_NEGATIVE.value:
            bucket["tn"] += 1
            metrics.true_negative_count += 1
        elif classification == CalibrationClassification.FALSE_NEGATIVE.value:
            bucket["fn"] += 1
            metrics.false_negative_count += 1
        else:
            bucket["indeterminate"] += 1
            metrics.indeterminate_count += 1

    @staticmethod
    def _bucket_to_rates(bucket: dict) -> dict:
        authoritative = bucket["tp"] + bucket["fp"] + bucket["tn"] + bucket["fn"]
        return {
            "true_positive": CalibrationMetrics._rate(bucket["tp"], authoritative),
            "false_positive": CalibrationMetrics._rate(bucket["fp"], authoritative),
            "true_negative": CalibrationMetrics._rate(bucket["tn"], authoritative),
            "false_negative": CalibrationMetrics._rate(bucket["fn"], authoritative),
            "indeterminate": {"count": bucket["indeterminate"]},
            "authoritative_sample_size": authoritative,
        }

    def get_analysis_calibration(self, analysis_digest: str) -> dict:
        records = self.list_records_for_analysis(analysis_digest)
        snapshots = self._repo.list_snapshots_by_analysis_digest(analysis_digest)
        return {
            "analysis_digest": analysis_digest,
            "snapshot_count": len(snapshots),
            "calibration_records": records,
            "metrics": self.compute_metrics().to_dict(),
        }

    def get_capability_calibration(self, capability_id: str) -> dict:
        records = self.list_records_for_capability(capability_id)
        return {
            "capability_id": capability_id,
            "calibration_records": records,
            "metrics": self.compute_metrics(capability_id=capability_id).to_dict(),
        }
