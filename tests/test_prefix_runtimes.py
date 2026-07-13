from __future__ import annotations

from pathlib import Path

from alma_bridge.execution.errors import detect_error_signature, launch_failure_in_log
from alma_bridge.execution.preflight import (
    prefix_dotnet_functional,
    prefix_dotnet_installed,
    prefix_runtimes_ready,
    prefix_vcrun_installed,
)


def test_prefix_vcrun_detects_system32_dlls(tmp_path: Path):
    root = tmp_path / "prefix"
    (root / "drive_c/windows/system32").mkdir(parents=True)
    (root / "drive_c/windows/system32/msvcp140.dll").write_bytes(b"x")
    (root / "drive_c/windows/system32/vcruntime140.dll").write_bytes(b"x")
    assert prefix_vcrun_installed(str(root)) is True


def test_prefix_dotnet_detects_framework_directory(tmp_path: Path):
    root = tmp_path / "prefix"
    dotnet = root / "drive_c/windows/Microsoft.NET/Framework64/v4.0.30319"
    dotnet.mkdir(parents=True)
    (dotnet / "mscorlib.dll").write_bytes(b"x")
    assert prefix_dotnet_installed(str(root)) is True


def test_prefix_dotnet_functional_requires_clr_shim(tmp_path: Path):
    root = tmp_path / "prefix"
    sys32 = root / "drive_c/windows/system32"
    sys32.mkdir(parents=True)
    (sys32 / "mscoree.dll").write_bytes(b"x")
    framework = root / "drive_c/windows/Microsoft.NET/Framework/v4.0.30319"
    framework.mkdir(parents=True)
    (framework / "clr.dll").write_bytes(b"x")
    dotnet = root / "drive_c/windows/Microsoft.NET/Framework64/v4.0.30319"
    dotnet.mkdir(parents=True)
    (dotnet / "mscorlib.dll").write_bytes(b"x")
    assert prefix_dotnet_installed(str(root)) is True
    assert prefix_dotnet_functional(str(root)) is True


def test_prefix_runtimes_ready_requires_both(tmp_path: Path):
    root = tmp_path / "prefix"
    sys32 = root / "drive_c/windows/system32"
    sys32.mkdir(parents=True)
    (sys32 / "msvcp140.dll").write_bytes(b"x")
    (sys32 / "vcruntime140.dll").write_bytes(b"x")
    assert prefix_vcrun_installed(str(root)) is True
    assert prefix_dotnet_installed(str(root)) is False
    assert prefix_runtimes_ready(str(root)) is False


def test_ms_learn_url_maps_to_dotnet_missing():
    sig = detect_error_signature(
        "",
        "https://learn.microsoft.com/en-us/dotnet/framework/install/application-not-started"
        "?processName=rundll32.exe",
    )
    assert sig == "dotnet_missing"


def test_launch_failure_ms_learn_rundll32():
    assert (
        launch_failure_in_log(
            "rundll32.exe opened application-not-started help page",
            "learn.microsoft.com/en-us/dotnet/framework/install/application-not-started",
        )
        == "dotnet_missing"
    )
