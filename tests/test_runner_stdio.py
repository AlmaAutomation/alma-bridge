from __future__ import annotations

from alma_bridge.execution import runner


def test_is_wine_runtime():
    assert runner._is_wine_runtime(["/usr/bin/wine", "game.exe"])
    assert runner._is_wine_runtime(["/usr/bin/wine64", "game.exe"])
    assert runner._is_wine_runtime(["/opt/GE-Proton/proton", "run", "game.exe"])
    assert not runner._is_wine_runtime(["/bin/sh", "script.sh"])
    assert not runner._is_wine_runtime([])


def test_gui_run_gives_valid_stdin_and_captures_output(tmp_path):
    # `cat` reads stdin to EOF: if stdin were a closed/invalid fd it would error.
    # A valid NUL/devnull stdin yields immediate EOF, proving the child got a
    # usable stdin handle (the fix for the Electron EBADF crash).
    code, out, err = runner._run_gui_to_file(
        ["sh", "-c", "cat; echo marker-out; echo marker-err 1>&2; exit 7"],
        {"WINEPREFIX": str(tmp_path)},
        timeout_sec=10,
    )
    assert code == 7
    # Output is funneled into stderr (combined), stdout stays empty.
    assert out == ""
    assert "marker-out" in err
    assert "marker-err" in err


def test_gui_run_does_not_use_pipe_stdin(tmp_path):
    # Reading from stdin should succeed (return nothing) rather than raise, and
    # the run should complete with the child's exit code.
    code, out, err = runner._run_gui_to_file(
        ["sh", "-c", "read line; echo \"[$line]\"; exit 0"],
        {"WINEPREFIX": str(tmp_path)},
        timeout_sec=10,
    )
    assert code == 0
    assert "[]" in err
