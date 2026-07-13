from __future__ import annotations

from unittest.mock import patch

from alma_bridge.execution.preflight import ascension_wine_preflight


def test_ascension_preflight_cache_hit_skips_heavy_work():
    calls: list[str] = []
    launcher = "/tmp/prefix/drive_c/Program Files/Ascension Launcher/Ascension Launcher/Ascension Launcher.exe"

    with (
        patch("alma_bridge.bridge.prefix_profile.load_prefix_profile") as load_profile,
        patch("alma_bridge.bridge.prefix_profile.profile_allows_fast_launch", return_value=True),
        patch("alma_bridge.compatibility.ascension_config.disable_ascension_auto_updater", return_value={"ok": True, "actions": []}),
        patch("alma_bridge.compatibility.ascension_config.write_ascension_launch_wrapper", return_value="/tmp/launch-ascension.sh"),
        patch("alma_bridge.execution.preflight.require_wine_windows_version") as win_ver,
        patch("alma_bridge.execution.preflight.refresh_dotnet_registration") as refresh,
        patch("alma_bridge.execution.installer_verify.ascension_main_launcher_path", return_value=launcher),
    ):
        load_profile.return_value.verified_at = "2026-07-10T00:00:00+00:00"
        result = ascension_wine_preflight(
            "/tmp/prefix",
            "/home/joshua/Documents/ascension-setup-1.0.97.exe",
            progress_callback=calls.append,
        )

    win_ver.assert_not_called()
    refresh.assert_not_called()
    assert any("cache hit" in msg.lower() for msg in calls)
    assert any(a.get("kind") == "profile_cache_hit" for a in result["actions"])


def test_ascension_preflight_skips_dotnet_refresh_when_functional():
    calls: list[str] = []
    launcher = "/tmp/prefix/drive_c/Program Files/Ascension Launcher/Ascension Launcher.exe"

    with (
        patch("alma_bridge.bridge.prefix_profile.load_prefix_profile", return_value=None),
        patch("alma_bridge.bridge.prefix_profile.profile_allows_fast_launch", return_value=False),
        patch("alma_bridge.execution.preflight.require_wine_windows_version", return_value=(True, "confirmed win10")),
        patch("alma_bridge.execution.preflight.prefix_runtimes_functional", return_value=True),
        patch("alma_bridge.execution.preflight.prefix_runtimes_ready", return_value=True),
        patch("alma_bridge.execution.preflight.refresh_dotnet_registration") as refresh,
        patch("alma_bridge.execution.preflight.bootstrap_wine_runtimes") as bootstrap,
        patch("alma_bridge.execution.preflight.repair_wine_runtimes") as repair,
        patch("alma_bridge.execution.preflight.repair_ascension_launcher_install", return_value={"ok": True, "skipped": True}),
        patch("alma_bridge.execution.installer_verify.ascension_launcher_install_broken", return_value=False),
        patch("alma_bridge.execution.installer_verify.ascension_main_launcher_path", return_value=launcher),
        patch("alma_bridge.execution.installer_verify.ascension_wrappers_present", return_value=True),
        patch("alma_bridge.execution.installer_verify.discover_installed_launcher", return_value=launcher),
        patch("alma_bridge.compatibility.ascension_config.disable_ascension_auto_updater", return_value={"ok": True, "actions": []}),
        patch("alma_bridge.compatibility.ascension_config.write_ascension_launch_wrapper", return_value="/tmp/launch-ascension.sh"),
        patch("alma_bridge.bridge.prefix_profile.save_prefix_profile"),
        patch("alma_bridge.execution.preflight.wineboot_update", return_value=(True, "")),
        patch(
            "alma_bridge.compatibility.electron_wine.apply_electron_remediation_shims",
            return_value={"status": "ok"},
        ),
        patch("alma_bridge.compatibility.electron_wine.mingw_compiler", return_value="/usr/bin/x86_64-w64-mingw32-gcc"),
    ):
        result = ascension_wine_preflight(
            "/tmp/prefix",
            "/home/joshua/Documents/ascension-setup-1.0.97.exe",
            progress_callback=calls.append,
        )

    refresh.assert_not_called()
    bootstrap.assert_not_called()
    repair.assert_not_called()
    assert any("functional" in msg.lower() for msg in calls)
    assert any(
        a.get("kind") == "runtime_refresh" and a.get("skipped_dotnet_refresh")
        for a in result["actions"]
    )
