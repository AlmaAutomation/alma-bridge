"""Tests for remediation outcome learning."""

from __future__ import annotations

from alma_bridge.learning.remediation import remediations_for_signature
from alma_bridge.learning.remediation_learning import (
    record_remediation_outcome,
    remediation_scores,
)


def test_remediation_learning_updates_scores(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "test.db")

    record_remediation_outcome("missing_dll", "missing_dll_winetricks", True)
    record_remediation_outcome("missing_dll", "missing_dll_winetricks", True)
    record_remediation_outcome("missing_dll", "baseline_retry", False)

    scores = remediation_scores("missing_dll")
    assert scores["missing_dll_winetricks"]["attempts"] == 2
    assert scores["missing_dll_winetricks"]["successes"] == 2
    assert scores["missing_dll_winetricks"]["rate"] > scores["baseline_retry"]["rate"]


def test_remediations_sorted_by_learned_rate(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "test.db")

    record_remediation_outcome("permission_denied", "fresh_wineprefix", True)
    record_remediation_outcome("permission_denied", "fresh_wineprefix", True)

    rems = remediations_for_signature("permission_denied")
    assert rems
    assert rems[0].get("id") in {r.get("id") for r in rems}
