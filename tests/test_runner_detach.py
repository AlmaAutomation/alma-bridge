"""GUI launcher detach — avoid false execution timeouts."""

from __future__ import annotations

from alma_bridge.execution.errors import detect_error_signature


def test_invalid_launch_args_signature():
    sig = detect_error_signature(
        "Ascension Launcher.exe: bad option: --disable-gpu",
        "",
    )
    assert sig == "invalid_launch_args"


def test_execution_timeout_signature():
    sig = detect_error_signature("", "Execution timed out.")
    assert sig == "execution_timeout"
