"""Stricter launch success detection."""

from __future__ import annotations

from alma_bridge.execution.errors import detect_error_signature, launch_failure_in_log


def test_wine_int3_crash_signature():
    sig = detect_error_signature(
        "0x00000147b7a9b6 ascension Launcher+0x7b7a9b6: int3",
        "Program Error Details",
    )
    assert sig == "wine_int3_crash"


def test_launch_failure_int3():
    assert launch_failure_in_log("ascension Launcher+0x7b7a9b6: int3", "") == "wine_int3_crash"


def test_launch_failure_rundll32_dialog():
    sig = launch_failure_in_log(
        "rundll32.exe - This application could not be started.",
        "",
    )
    assert sig == "dotnet_missing"


def test_launch_failure_ms_learn_url():
    sig = launch_failure_in_log(
        "",
        "learn.microsoft.com/en-us/dotnet/framework/install/application-not-started?processName=rundll32.exe",
    )
    assert sig == "dotnet_missing"


def test_launch_failure_invalid_args():
    sig = launch_failure_in_log("Ascension Launcher.exe: bad option: --disable-gpu", "")
    assert sig == "invalid_launch_args"


def test_execution_timeout_still_detected():
    assert detect_error_signature("", "Execution timed out.") == "execution_timeout"
