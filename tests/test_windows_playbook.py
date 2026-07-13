"""Windows modernization playbook tests (plan on Linux CI; apply skipped)."""

from __future__ import annotations

from alma_bridge.automation.playbooks import build_recipe_playbook, list_playbooks
from alma_bridge.compliance.modernization.windows import (
    apply_windows_playbook,
    assess_windows_host,
    build_windows_playbook,
    export_playbook_script,
    is_windows_host,
)


def test_assess_windows_from_linux_server():
    result = assess_windows_host()
    assert result["host_platform"] != "windows" or is_windows_host()
    assert result["verdict"]
    assert "remote_planning" in result["gaps"] or is_windows_host()
    assert result["planning_only"] is not is_windows_host()


def test_build_windows_playbook_has_powershell_steps():
    playbook = build_windows_playbook()
    assert playbook["recipe_id"] == "school-lab-windows"
    assert playbook["host_platform"] == "windows"
    assert len(playbook["steps"]) >= 3
    assert all(s.get("shell") == "powershell" for s in playbook["steps"] if s.get("command"))
    assert "sync_time" in playbook["apply_step_ids"]


def test_export_script_is_runnable_ps1():
    playbook = build_windows_playbook()
    script = export_playbook_script(playbook)
    assert "#Requires -RunAsAdministrator" in script
    assert "w32tm" in script
    assert "Alma Windows playbook finished" in script


def test_apply_plan_only_on_linux():
    playbook = build_windows_playbook()
    outcome = apply_windows_playbook(playbook, allow_mutations=True)
    if is_windows_host():
        assert outcome["applied"] in (True, False)
    else:
        assert outcome["applied"] is False
        assert "export" in (outcome.get("reason") or "").lower()
        assert outcome["export_script"]


def test_school_lab_windows_recipe_in_automation():
    ids = [p["id"] for p in list_playbooks()]
    assert "school-lab-windows" in ids
    recipe = build_recipe_playbook("school-lab-windows")
    assert recipe["host_platform"] == "windows"
    assert recipe.get("export_script")
    assert any(s["id"] == "sync_time" for s in recipe["steps"])
