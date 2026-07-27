from __future__ import annotations

from unittest.mock import patch

import pytest

from alma_bridge.execution.installer_verify import (
    ascension_main_launcher_path,
    discover_installed_launcher,
    snapshot_wine_prefix,
    verify_installer_outcome,
)
from alma_bridge.execution.preflight import read_wine_windows_version
from alma_bridge.learning.remediation import remediations_for_signature
from alma_bridge.learning.remediation_learning import (
    init_remediation_store,
    record_remediation_outcome,
    remediation_scores,
)
from alma_bridge.storage.outcomes import init_outcome_store


@pytest.fixture()
def isolated_remediation_store(tmp_path, monkeypatch):
    db_path = tmp_path / "outcomes.db"
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    monkeypatch.setattr("alma_bridge.config.settings.db_path", db_path)
    init_outcome_store()
    init_remediation_store()
    return tmp_path


def test_installer_not_verified_default_remediation_order(isolated_remediation_store):
    chain = remediations_for_signature("installer_not_verified", installer=True)
    ids = [action["id"] for action in chain]
    assert ids[0] == "installer_bootstrap_win10_vcrun_ncrc"
    assert "installer_silent_nsis_bootstrap" in ids
    assert "installer_fresh_prefix_silent" in ids


def test_installer_not_verified_learned_remediation_order(isolated_remediation_store):
    record_remediation_outcome("installer_not_verified", "installer_fresh_prefix_silent", True)
    record_remediation_outcome("installer_not_verified", "installer_fresh_prefix_silent", True)
    record_remediation_outcome("installer_not_verified", "installer_bootstrap_win10_vcrun_ncrc", False)

    chain = remediations_for_signature("installer_not_verified", installer=True)
    ids = [action["id"] for action in chain]
    assert ids[0] == "installer_fresh_prefix_silent"


def test_installer_not_verified_tie_breaks_by_priority(isolated_remediation_store):
    record_remediation_outcome("installer_not_verified", "installer_bootstrap_win10_vcrun_ncrc", True)
    record_remediation_outcome("installer_not_verified", "installer_bootstrap_full_ncrc", True)

    chain = remediations_for_signature("installer_not_verified", installer=True)
    ids = [action["id"] for action in chain]
    bootstrap_idx = ids.index("installer_bootstrap_win10_vcrun_ncrc")
    full_idx = ids.index("installer_bootstrap_full_ncrc")
    assert bootstrap_idx < full_idx


def test_remediation_scores_use_isolated_store_not_user_home(isolated_remediation_store, monkeypatch):
    from alma_bridge.config import settings

    assert str(settings.db_path).startswith(str(isolated_remediation_store))
    assert ".local/share/alma-bridge" not in str(settings.db_path)
    assert remediation_scores("installer_not_verified") == {}


def test_installer_not_verified_remediation_chain_order(isolated_remediation_store):
    chain = remediations_for_signature("installer_not_verified", installer=True)
    ids = [action["id"] for action in chain]
    assert ids[0] == "installer_bootstrap_win10_vcrun_ncrc"
    assert "installer_silent_nsis_bootstrap" in ids
    assert "installer_fresh_prefix_silent" in ids


def test_snapshot_detects_uninstall_keys(tmp_path):
    prefix = tmp_path / "prefix"
    drive_c = prefix / "drive_c" / "Program Files" / "Ascension"
    drive_c.mkdir(parents=True)
    user_reg = prefix / "user.reg"
    user_reg.write_text(
        '[Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Ascension]\n'
        '"DisplayName"="Ascension"\n',
        encoding="utf-8",
    )

    before = snapshot_wine_prefix(str(prefix))
    assert before.uninstall_keys == frozenset({"Ascension"})
    assert "Program Files/Ascension" in before.program_dirs


def test_verify_accepts_log_success_marker():
    verified, reasons = verify_installer_outcome(
        wine_prefix="/nonexistent",
        before=None,
        stdout="",
        stderr="Installation complete.",
        installer_path="/tmp/setup.exe",
        duration_ms=5_000,
    )
    assert verified is True
    assert "success marker" in reasons[0]


def test_verify_accepts_new_uninstall_entry(tmp_path):
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    (prefix / "user.reg").write_text("", encoding="utf-8")
    before = snapshot_wine_prefix(str(prefix))

    user_reg = prefix / "user.reg"
    user_reg.write_text(
        '[Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\Ascension]\n'
        '"DisplayName"="Ascension"\n',
        encoding="utf-8",
    )

    verified, reasons = verify_installer_outcome(
        wine_prefix=str(prefix),
        before=before,
        stdout="",
        stderr="wine noise only",
        installer_path="/tmp/ascension-setup-1.0.97.exe",
        duration_ms=10_000,
    )
    assert verified is True
    assert "uninstall registry" in reasons[0]


def test_verify_rejects_clean_exit_without_artifacts(tmp_path):
    prefix = tmp_path / "prefix"
    prefix.mkdir()
    before = snapshot_wine_prefix(str(prefix))

    verified, reasons = verify_installer_outcome(
        wine_prefix=str(prefix),
        before=before,
        stdout="",
        stderr="err:ole: rpc",
        installer_path="/tmp/ascension-setup-1.0.97.exe",
        duration_ms=4_000,
    )
    assert verified is False
    assert "no uninstall entry" in reasons[0]


def test_read_wine_windows_version_from_user_reg(tmp_path):
    user_reg = tmp_path / "user.reg"
    user_reg.write_text(
        '[Software\\Wine] 1234567890\n#time=1\n"Version"="win10"\n',
        encoding="utf-8",
    )
    assert read_wine_windows_version(str(tmp_path)) == "win10"


def test_discover_ascension_launcher(tmp_path):
    prefix = tmp_path / "prefix"
    launcher_dir = prefix / "drive_c/Program Files/Ascension Launcher"
    launcher_dir.mkdir(parents=True)
    launcher = launcher_dir / "Ascension Launcher.exe"
    launcher.write_bytes(b"MZ" + b"\0" * 600_000)
    for marker in ("resources.pak", "snapshot_blob.bin", "libEGL.dll"):
        (launcher_dir / marker).write_bytes(b"x")

    found = discover_installed_launcher(
        str(prefix),
        "/home/joshua/Documents/ascension-setup-1.0.97.exe",
    )
    assert found == str(launcher)


def test_discover_launcher_ignores_alma_guard_decoy(tmp_path):
    prefix = tmp_path / "prefix"
    install_dir = prefix / "drive_c/Program Files/Ascension Launcher"
    guard_dir = install_dir / "resources/alma-guard"
    guard_dir.mkdir(parents=True)
    decoy = guard_dir / "Ascension Launcher.exe"
    decoy.write_bytes(b"MZ" + b"\0" * 600_000)
    real = install_dir / "Ascension Launcher.exe"
    real.write_bytes(b"MZ" + b"\0" * 600_000)
    for marker in ("resources.pak", "snapshot_blob.bin", "libEGL.dll"):
        (install_dir / marker).write_bytes(b"x")

    found = discover_installed_launcher(str(prefix), "/home/joshua/Documents/ascension-setup.exe")
    assert found == str(real)


def test_ascension_nested_squirrel_launcher_path(tmp_path):
    prefix = tmp_path / "prefix"
    nested = prefix / "drive_c/Program Files/Ascension Launcher/Ascension Launcher"
    nested.mkdir(parents=True)
    launcher = nested / "Ascension Launcher.exe"
    launcher.write_bytes(b"MZ" + b"\0" * 600_000)
    for marker in ("resources.pak", "snapshot_blob.bin", "libEGL.dll"):
        (nested / marker).write_bytes(b"x")

    found = ascension_main_launcher_path(str(prefix))
    assert found == str(launcher)


def test_ascension_wrappers_present_detects_sidecar_and_elevate(tmp_path):
    from alma_bridge.execution.installer_verify import ascension_wrappers_present

    install = tmp_path / "Ascension Launcher"
    resources = install / "resources"
    resources.mkdir(parents=True)
    (install / "Ascension Launcher.exe").write_bytes(b"MZ" + b"\0" * 600_000)
    (resources / "AscensionClientServices.real.exe").write_bytes(b"MZ" + b"\0" * 1000)
    (resources / "AscensionClientServices.exe").write_bytes(b"MZ" + b"\0" * 100)
    (resources / "elevate.exe").write_bytes(b"MZ" + b"\0" * 100)
    assert ascension_wrappers_present(str(install / "Ascension Launcher.exe"))


def test_launcher_ready_for_handoff_nested_launcher(tmp_path):
    from alma_bridge.execution.installer_verify import launcher_ready_for_handoff

    prefix = tmp_path / "prefix"
    nested = prefix / "drive_c/Program Files/Ascension Launcher/Ascension Launcher"
    resources = nested / "resources"
    resources.mkdir(parents=True)
    launcher = nested / "Ascension Launcher.exe"
    launcher.write_bytes(b"MZ" + b"\0" * 600_000)
    for marker in ("resources.pak", "snapshot_blob.bin", "libEGL.dll"):
        (nested / marker).write_bytes(b"x")
    sys32 = prefix / "drive_c/windows/system32"
    sys32.mkdir(parents=True)
    (sys32 / "msvcp140.dll").write_bytes(b"x")
    (sys32 / "vcruntime140.dll").write_bytes(b"x")
    (sys32 / "mscoree.dll").write_bytes(b"x")
    framework = prefix / "drive_c/windows/Microsoft.NET/Framework/v4.0.30319"
    framework.mkdir(parents=True)
    (framework / "clr.dll").write_bytes(b"x")
    dotnet = prefix / "drive_c/windows/Microsoft.NET/Framework64/v4.0.30319"
    dotnet.mkdir(parents=True)
    (dotnet / "mscorlib.dll").write_bytes(b"x")
    (resources / "AscensionClientServices.real.exe").write_bytes(b"MZ" + b"\0" * 1000)
    (resources / "AscensionClientServices.exe").write_bytes(b"MZ" + b"\0" * 100)
    (resources / "elevate.exe").write_bytes(b"MZ" + b"\0" * 100)

    with (
        patch("alma_bridge.execution.preflight.query_wine_windows_version_live", return_value="win10"),
        patch("alma_bridge.execution.preflight.read_wine_windows_version", return_value="win10"),
    ):
        found = launcher_ready_for_handoff(
            str(prefix),
            "/home/joshua/Documents/ascension-setup-1.0.97.exe",
        )
    assert found == str(launcher)
