"""Validation campaign prefix guard tests."""

from __future__ import annotations

import os

import pytest

from alma_bridge.schemas.models import BridgeRequest
from alma_bridge.validation.campaign_guard import (
    CampaignPrefixRejected,
    validate_campaign_bridge_request,
)


@pytest.fixture
def campaign_env(tmp_path, monkeypatch):
    disposable = tmp_path / "disposable"
    primary = tmp_path / "primary"
    snapshot = tmp_path / "snapshot"
    disposable.mkdir()
    primary.mkdir()
    snapshot.mkdir()
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_mode", True)
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_id", "pilot-002")
    monkeypatch.setattr(
        "alma_bridge.config.settings.validation_campaign_disposable_root",
        str(disposable),
    )
    monkeypatch.setattr(
        "alma_bridge.config.settings.validation_campaign_primary_prefix",
        str(primary),
    )
    monkeypatch.setattr(
        "alma_bridge.config.settings.validation_campaign_source_snapshot",
        str(snapshot),
    )
    return {"disposable": disposable, "primary": primary, "snapshot": snapshot}


def test_primary_prefix_rejected(campaign_env):
    with pytest.raises(CampaignPrefixRejected) as exc:
        validate_campaign_bridge_request(
            BridgeRequest(
                file_path="/tmp/game.exe",
                wine_prefix=str(campaign_env["primary"]),
            )
        )
    assert exc.value.reason_code == "CAMPAIGN_PRIMARY_PREFIX_FORBIDDEN"


def test_source_snapshot_rejected(campaign_env):
    with pytest.raises(CampaignPrefixRejected) as exc:
        validate_campaign_bridge_request(
            BridgeRequest(
                file_path="/tmp/game.exe",
                wine_prefix=str(campaign_env["snapshot"]),
            )
        )
    assert exc.value.reason_code == "CAMPAIGN_SOURCE_SNAPSHOT_FORBIDDEN"


def test_outside_root_rejected(campaign_env, tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(CampaignPrefixRejected) as exc:
        validate_campaign_bridge_request(
            BridgeRequest(
                file_path="/tmp/game.exe",
                wine_prefix=str(outside),
            )
        )
    assert exc.value.reason_code == "CAMPAIGN_PREFIX_OUTSIDE_ROOT"


def test_valid_disposable_clone_accepted(campaign_env):
    clone = campaign_env["disposable"] / "run-01"
    clone.mkdir()
    validate_campaign_bridge_request(
        BridgeRequest(
            file_path="/tmp/game.exe",
            wine_prefix=str(clone),
        )
    )


def test_symlink_escape_rejected(campaign_env, tmp_path):
    escape_target = tmp_path / "escape"
    escape_target.mkdir()
    link = campaign_env["disposable"] / "evil-link"
    link.symlink_to(escape_target)
    with pytest.raises(CampaignPrefixRejected):
        validate_campaign_bridge_request(
            BridgeRequest(
                file_path="/tmp/game.exe",
                wine_prefix=str(link),
            )
        )


def test_native_script_without_prefix_allowed(campaign_env):
    validate_campaign_bridge_request(
        BridgeRequest(file_path="/tmp/probe.sh"),
    )


def test_guard_inactive_without_campaign_mode(monkeypatch, campaign_env):
    monkeypatch.setattr("alma_bridge.config.settings.validation_campaign_mode", False)
    validate_campaign_bridge_request(
        BridgeRequest(
            file_path="/tmp/game.exe",
            wine_prefix=str(campaign_env["primary"]),
        )
    )
