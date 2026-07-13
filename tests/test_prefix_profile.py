from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from alma_bridge.bridge.prefix_profile import (
    PrefixReadinessProfile,
    profile_allows_fast_launch,
    profile_is_fresh,
    profile_store_path,
    save_prefix_profile,
)


def test_profile_is_fresh_within_ttl():
    profile = PrefixReadinessProfile(
        wine_prefix="/tmp/prefix",
        verified_at=datetime.now(timezone.utc).isoformat(),
        ttl_hours=24,
    )
    assert profile_is_fresh(profile)


def test_profile_is_stale_after_ttl():
    old = datetime.now(timezone.utc) - timedelta(hours=48)
    profile = PrefixReadinessProfile(
        wine_prefix="/tmp/prefix",
        verified_at=old.isoformat(),
        ttl_hours=24,
    )
    assert not profile_is_fresh(profile)


def test_profile_allows_fast_launch_when_complete(tmp_path):
    launcher = tmp_path / "Ascension Launcher.exe"
    launcher.write_bytes(b"MZ" + b"\0" * 600_000)
    profile = PrefixReadinessProfile(
        wine_prefix=str(tmp_path),
        launcher_path=str(launcher),
        windows_version="win10",
        dotnet_functional=True,
        vcrun_ready=True,
        wrappers_applied=True,
        updater_disabled=True,
        verified_at=datetime.now(timezone.utc).isoformat(),
    )
    assert profile_allows_fast_launch(profile, str(tmp_path), launcher_path=str(launcher))


def test_save_and_load_roundtrip(tmp_path):
    prefix = tmp_path / "wine-prefix"
    prefix.mkdir()
    profile = PrefixReadinessProfile(
        wine_prefix=str(prefix),
        launcher_path="/tmp/launcher.exe",
        windows_version="win10",
        dotnet_functional=True,
        vcrun_ready=True,
        wrappers_applied=True,
        updater_disabled=True,
    )
    with patch("alma_bridge.bridge.prefix_profile.profile_store_path") as store_path:
        store_path.return_value = tmp_path / "profile.json"
        save_prefix_profile(profile)
        from alma_bridge.bridge.prefix_profile import load_prefix_profile

        loaded = load_prefix_profile(str(prefix))
    assert loaded is not None
    assert loaded.launcher_path == "/tmp/launcher.exe"
    assert loaded.windows_version == "win10"
