from __future__ import annotations

from alma_bridge.learning.installer import (
    apply_electron_launch_overrides,
    electron_disable_gpu_args,
    electron_software_gl_args,
    is_electron_app,
    is_windows_installer,
)
from alma_bridge.learning.remediation import remediations_for_signature


def test_detects_setup_installer():
    assert is_windows_installer("/home/joshua/Documents/ascension-setup-1.0.94.exe")


def test_detects_electron_app(tmp_path):
    app = tmp_path / "Ascension Launcher.exe"
    app.write_bytes(b"MZ")
    for marker in ("resources.pak", "snapshot_blob.bin", "libEGL.dll"):
        (tmp_path / marker).write_bytes(b"x")
    assert is_electron_app(str(app))


def test_non_electron_exe_not_detected(tmp_path):
    app = tmp_path / "setup.exe"
    app.write_bytes(b"MZ")
    assert not is_electron_app(str(app))


def test_apply_electron_launch_overrides_adds_skip_update_args():
    env = {"ALMA_SKIP_ELECTRON_UPDATE": "1"}
    args: list[str] = ["--disable-gpu"]
    apply_electron_launch_overrides(env, args)
    assert "--no-update" in args
    assert "--skip-update" in args
    assert "ALMA_SKIP_ELECTRON_UPDATE" not in env


def test_electron_software_gl_args():
    # Under Wine the ONLY stable option is to disable the GPU process. No
    # --use-gl/--use-angle flags (all of them crash-loop on Wine).
    args = electron_software_gl_args()
    assert "--disable-gpu" in args
    assert "--no-sandbox" in args
    assert "--disable-crash-reporter" in args
    assert not any(a.startswith("--use-gl") or a.startswith("--use-angle") for a in args)


def test_electron_disable_gpu_args():
    args = electron_disable_gpu_args()
    assert "--disable-gpu" in args
    assert not any("angle" in a or "use-gl" in a for a in args)


def test_electron_gpu_remediation_is_disable_gpu():
    rems = remediations_for_signature("electron_gpu_crash", electron=True)
    ids = {a["id"] for a in rems}
    assert "electron_disable_gpu" in ids
    # The wrong ANGLE remediation must be gone.
    assert "electron_angle_gl" not in ids
    disable = next(a for a in rems if a["id"] == "electron_disable_gpu")
    assert "--disable-gpu" in disable["args"]
    assert not any("angle" in a for a in disable["args"])


def test_electron_only_remediations_gated():
    generic = {a["id"] for a in remediations_for_signature("elevation_failed")}
    electron = {a["id"] for a in remediations_for_signature("elevation_failed", electron=True)}
    assert "electron_elevate_passthrough" in electron
    assert "electron_elevate_passthrough" not in generic


def test_launcher_guard_remediation_exists():
    ids = {a["id"] for a in remediations_for_signature("launcher_guard_shutdown", electron=True)}
    assert "electron_launcher_guard_workaround" in ids


def test_installer_remediations_only_when_requested():
    generic = {action["id"] for action in remediations_for_signature("unknown_error")}
    installer = {
        action["id"]
        for action in remediations_for_signature("unknown_error", installer=True)
    }
    assert "nsis_ncrc" in installer
    assert "nsis_ncrc" not in generic
