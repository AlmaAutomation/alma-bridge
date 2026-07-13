from __future__ import annotations

import os

import pytest

from alma_bridge.execution.privileges import (
    clear_stored_sudo_password,
    prepare_sudo,
    remember_sudo_password,
    store_sudo_password,
    sudo_ticket_valid,
    wrap_with_sudo,
)

_IS_ROOT = hasattr(os, "geteuid") and os.geteuid() == 0
from alma_bridge.learning.remediation import remediations_for_signature


@pytest.mark.skipif(_IS_ROOT, reason="root bypasses sudo wrapping")
def test_wrap_with_sudo():
    wrapped = wrap_with_sudo(["docker", "run"], use_sudo=True)
    assert wrapped[:2] == ["sudo", "-n"]
    assert wrap_with_sudo(["wine", "game.exe"], use_sudo=False) == ["wine", "game.exe"]


def test_prepare_sudo_without_password_when_not_requested():
    ok, err = prepare_sudo(requested=False)
    assert ok is True
    assert err == ""


@pytest.mark.skipif(_IS_ROOT, reason="root does not need sudo credentials")
def test_prepare_sudo_fails_without_credentials(monkeypatch):
    monkeypatch.setattr(
        "alma_bridge.execution.privileges.passwordless_sudo_works",
        lambda: False,
    )
    monkeypatch.setattr(
        "alma_bridge.execution.privileges.sudo_ticket_valid",
        lambda: False,
    )
    monkeypatch.setattr(
        "alma_bridge.execution.privileges.get_stored_sudo_password",
        lambda: None,
    )
    ok, err = prepare_sudo(requested=True)
    assert ok is False
    assert "sudo password" in err.lower() or "sudo -v" in err.lower()


def test_prepare_sudo_uses_warmed_ticket(monkeypatch):
    monkeypatch.setattr(
        "alma_bridge.execution.privileges.passwordless_sudo_works",
        lambda: False,
    )
    monkeypatch.setattr(
        "alma_bridge.execution.privileges.sudo_ticket_valid",
        lambda: True,
    )
    ok, err = prepare_sudo(requested=True)
    assert ok is True
    assert err == ""


def test_remember_sudo_password_stores_for_later(monkeypatch):
    clear_stored_sudo_password()
    monkeypatch.setattr(
        "alma_bridge.execution.privileges.warm_sudo_cache",
        lambda password: (True, ""),
    )
    ok, err = remember_sudo_password("secret")
    assert ok is True
    assert err == ""
    from alma_bridge.execution.privileges import get_stored_sudo_password

    assert get_stored_sudo_password() == "secret"
    clear_stored_sudo_password()


def test_container_remediation_skipped_when_disabled():
    actions = remediations_for_signature("unknown_error", allow_container=False)
    ids = {action["id"] for action in actions}
    assert "container_isolation" not in ids
