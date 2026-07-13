from __future__ import annotations

from pathlib import Path

from alma_bridge.compatibility.ascension_config import disable_ascension_auto_updater


def test_disable_ascension_auto_updater_neuters_app_update_yml(tmp_path: Path):
    launcher = tmp_path / "Ascension Launcher.exe"
    resources = tmp_path / "resources"
    resources.mkdir()
    launcher.write_bytes(b"MZ")
    update_yml = resources / "app-update.yml"
    update_yml.write_text(
        "provider: generic\nurl: https://cdn.example.com/update\n",
        encoding="utf-8",
    )

    result = disable_ascension_auto_updater(str(tmp_path), str(launcher))

    assert result["ok"] is True
    assert (resources / "app-update.yml.orig").is_file()
    text = update_yml.read_text(encoding="utf-8")
    assert "alma-disabled-update" in text
