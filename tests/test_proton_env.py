from __future__ import annotations

from pathlib import Path

from alma_bridge.hardware.proton_env import build_proton_env, resolve_steam_root
from alma_bridge.learning.installer import fresh_prefix_path


def test_fresh_prefix_under_home():
    path = fresh_prefix_path("session-abc-123")
    assert path.startswith(str(Path.home()))
    assert "alma-bridge/prefixes" in path


def test_build_proton_env_sets_compat_paths():
    proton = "/home/joshua/.local/share/Steam/compatibilitytools.d/GE-Proton10-34/proton"
    env = build_proton_env(proton, "test-session-id")
    assert env["STEAM_COMPAT_DATA_PATH"]
    assert env["STEAM_COMPAT_CLIENT_INSTALL_PATH"]
    assert env["WINEPREFIX"].endswith("/pfx")
    assert "Steam" in resolve_steam_root(proton)
