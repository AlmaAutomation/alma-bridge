from __future__ import annotations

from unittest.mock import patch

from alma_bridge.execution.errors import (
    HARD_FAIL_SIGNATURES,
    detect_error_signature,
    detect_installer_false_success,
)
from alma_bridge.execution.preflight import (
    _patch_user_reg_windows_version,
    read_wine_windows_version,
    require_wine_windows_version,
    wine_windows_version_insufficient,
)


def test_windows_version_required_signature():
    assert (
        detect_error_signature("", "Windows 7 and above is required")
        == "windows_version_required"
    )


def test_hard_fail_includes_windows_version():
    assert "windows_version_required" in HARD_FAIL_SIGNATURES


def test_installer_false_success_on_old_wine_version():
    sig = detect_installer_false_success(
        "",
        "",
        duration_ms=5_000,
        exit_code=0,
        wine_windows_version="winxp",
    )
    assert sig == "windows_version_required"


def test_installer_false_success_skips_when_progress_visible():
    sig = detect_installer_false_success(
        "Copying files to destination...",
        "",
        duration_ms=5_000,
        exit_code=0,
        wine_windows_version="winxp",
    )
    assert sig is None


def test_installer_aborted_on_immediate_clean_exit():
    sig = detect_installer_false_success(
        "",
        "",
        duration_ms=3_000,
        exit_code=0,
        wine_windows_version="win10",
    )
    assert sig == "installer_aborted"


def test_read_wine_windows_version_from_user_reg(tmp_path):
    user_reg = tmp_path / "user.reg"
    user_reg.write_text(
        '[Software\\Wine]\n"Version"="win10"\n',
        encoding="utf-8",
    )
    assert read_wine_windows_version(str(tmp_path)) == "win10"


def test_wine_windows_version_insufficient_defaults_to_xp():
    assert wine_windows_version_insufficient(None)
    assert wine_windows_version_insufficient("winxp")
    assert not wine_windows_version_insufficient("win10")


def test_patch_user_reg_adds_version_to_existing_wine_section(tmp_path):
    user_reg = tmp_path / "user.reg"
    user_reg.write_text(
        "WINE REGISTRY Version 2\n\n[Software\\\\Wine] 123\n#time abc\n",
        encoding="utf-8",
    )
    ok, _ = _patch_user_reg_windows_version(str(tmp_path), "win10")
    assert ok
    assert read_wine_windows_version(str(tmp_path)) == "win10"


def test_patch_user_reg_updates_existing_version(tmp_path):
    user_reg = tmp_path / "user.reg"
    user_reg.write_text(
        '[Software\\Wine]\n"Version"="winxp"\n',
        encoding="utf-8",
    )
    ok, _ = _patch_user_reg_windows_version(str(tmp_path), "win10")
    assert ok
    assert read_wine_windows_version(str(tmp_path)) == "win10"


def test_require_wine_windows_version_confirms_after_patch(tmp_path):
    user_reg = tmp_path / "user.reg"
    user_reg.write_text("WINE REGISTRY Version 2\n", encoding="utf-8")
    with (
        patch("alma_bridge.execution.preflight._wine_reg_set_version", return_value=(True, "ok")),
        patch("alma_bridge.execution.preflight.query_wine_windows_version_live", return_value="win10"),
        patch("alma_bridge.execution.preflight._kill_wineserver"),
    ):
        ok, msg = require_wine_windows_version(str(tmp_path))
    assert ok
    assert "confirmed win10" in msg
