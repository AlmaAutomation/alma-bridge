from __future__ import annotations

from alma_bridge.execution.runner import _append_launch_args
from alma_bridge.learning.remediation import (
    apply_remediation,
    get_remediation_by_id,
    remediations_for_signature,
)
from alma_bridge.hardware.proton import find_proton_installs


def test_get_remediation_by_id_respects_context():
    assert get_remediation_by_id("software_rendering") is not None
    assert get_remediation_by_id("installer_virtual_desktop", installer=False) is None
    assert get_remediation_by_id("installer_virtual_desktop", installer=True) is not None


def test_gpu_crash_remediations_include_resolve_profiles():
    actions = remediations_for_signature("gpu_crash")
    ids = {action["id"] for action in actions}
    assert "software_rendering" in ids
    assert "best_known_profile" in ids
    assert "baseline_retry" not in ids


def test_legacy_signatures_have_targeted_remediations():
    assert remediations_for_signature("java_missing")[0]["id"] == "java_jre_winetricks"
    assert remediations_for_signature("opengl_legacy")[0]["id"] == "legacy_opengl_wined3d"
    assert remediations_for_signature("directx_old")[0]["id"] == "legacy_directx9"


def test_apply_remediation_adds_electron_args():
    env, args = apply_remediation(
        {"WINEPREFIX": "/tmp/prefix"},
        {
            "id": "software_rendering",
            "env": {"WINEDEBUG": "-all"},
            "shims": [],
            "args": ["--disable-gpu"],
        },
    )
    assert env["WINEPREFIX"] == "/tmp/prefix"
    assert env["WINEDEBUG"] == "-all"
    assert args == ["--disable-gpu"]


def test_append_launch_args_for_wine():
    command = ["/usr/bin/wine", "/tmp/game.exe"]
    updated = _append_launch_args(command, ["--disable-gpu"])
    assert updated == ["/usr/bin/wine", "/tmp/game.exe", "--disable-gpu"]


def test_append_launch_args_for_proton():
    command = ["/proton/proton", "run", "/tmp/game.exe"]
    updated = _append_launch_args(command, ["--disable-gpu"])
    assert updated == ["/proton/proton", "run", "/tmp/game.exe", "--disable-gpu"]


def test_find_proton_installs_is_list():
    assert isinstance(find_proton_installs(), list)
