from __future__ import annotations

from pathlib import Path

from alma_bridge.hardware.prefixes import find_best_prefix


def test_find_prefix_for_ascension_installer_name(tmp_path, monkeypatch):
    prefix = tmp_path / "803984cf-660"
    launcher = (
        prefix
        / "drive_c/Program Files/Ascension Launcher/Ascension Launcher.exe"
    )
    launcher.parent.mkdir(parents=True)
    launcher.write_bytes(b"MZ")

    monkeypatch.setattr("alma_bridge.hardware.prefixes.PREFIXES_ROOT", tmp_path)

    found = find_best_prefix("/home/joshua/Documents/ascension-setup-1.0.97.exe")
    assert found == str(prefix)


def test_find_prefix_when_exe_inside_bottle(tmp_path, monkeypatch):
    prefix = tmp_path / "abc123"
    exe = prefix / "drive_c/Program Files/Foo/app.exe"
    exe.parent.mkdir(parents=True)
    exe.write_bytes(b"MZ")

    monkeypatch.setattr("alma_bridge.hardware.prefixes.PREFIXES_ROOT", tmp_path)

    assert find_best_prefix(str(exe)) == str(prefix)
