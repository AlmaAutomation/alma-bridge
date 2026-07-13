from __future__ import annotations

from alma_bridge.learning.orchestrator import _winetricks_packages_for_attempt


def test_winetricks_only_from_current_remediation():
    env = {"ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022,dotnet48", "WINEDEBUG": "-all"}
    current = {"id": "network_workarounds", "env": {"WINEDEBUG": "-all"}}
    assert _winetricks_packages_for_attempt(current, env) is None
    assert "ALMA_RUN_WINETRICKS" not in env


def test_winetricks_runs_when_current_step_requests_it():
    env = {}
    current = {
        "id": "launcher_sidecar_vcrun",
        "env": {"ALMA_RUN_WINETRICKS": "vcrun2019,vcrun2022,dotnet48"},
    }
    assert (
        _winetricks_packages_for_attempt(current, env)
        == "vcrun2019,vcrun2022,dotnet48"
    )
