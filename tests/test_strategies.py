from __future__ import annotations

import os
import stat

from alma_bridge.compatibility.strategies import (
    available_strategies,
    classify_binary,
)


def test_classify_pe_by_suffix_even_when_executable(tmp_path):
    exe = tmp_path / "game.exe"
    exe.write_bytes(b"not a real pe but has .exe suffix")
    exe.chmod(exe.stat().st_mode | stat.S_IXUSR)

    assert classify_binary(str(exe), "x86_64") == "pe"


def test_classify_script_does_not_steal_exe(tmp_path):
    sh = tmp_path / "run.sh"
    sh.write_text("#!/bin/sh\necho hi\n")
    sh.chmod(0o755)
    assert classify_binary(str(sh), "x86_64") == "script"


def test_available_strategies_pe_never_native():
    caps = {"wine": True, "proton": True, "docker": True}
    strategies = available_strategies(
        "/home/joshua/Documents/WoW.exe",
        caps,
        "x86_64",
        runtime_hint="native",
    )
    ids = [s.id for s in strategies]
    assert "native_host" not in ids
    assert "wine_host" in ids
    assert ids[0] in {"wine_host", "proton_host"}


def test_available_strategies_elf_never_wine(tmp_path):
    sh = tmp_path / "hello.sh"
    sh.write_text("#!/bin/sh\necho hi\n")
    sh.chmod(0o755)
    caps = {"wine": True, "docker": False, "multiarch": False}
    strategies = available_strategies(str(sh), caps, "x86_64", runtime_hint=None)
    ids = [s.id for s in strategies]
    assert "wine_host" not in ids
    assert "proton_host" not in ids
    assert "native_host" in ids
