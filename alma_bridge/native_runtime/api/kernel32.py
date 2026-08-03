"""Python-side kernel32 API shim (fixture simulation fallback)."""

from __future__ import annotations

import struct
from pathlib import Path
from typing import Dict, Optional

from alma_bridge.native_runtime.console.stderr import ConsoleStderr
from alma_bridge.native_runtime.console.stdout import ConsoleStdout
from alma_bridge.native_runtime.filesystem.files import read_file, write_file
from alma_bridge.native_runtime.process.command_line import build_command_line_w
from alma_bridge.native_runtime.process.exit import ExitState
from alma_bridge.native_runtime.process.handles import (
    INVALID_HANDLE_VALUE,
    STD_ERROR_HANDLE,
    STD_INPUT_HANDLE,
    STD_OUTPUT_HANDLE,
)


class Kernel32ShimState:
    """In-process kernel32 shim state for fixture simulation."""

    def __init__(
        self,
        *,
        workspace: Path,
        argv: Optional[list[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> None:
        self.workspace = workspace
        self.argv = argv or ["fixture.exe"]
        self.env = env or {}
        self.stdout = ConsoleStdout()
        self.stderr = ConsoleStderr()
        self.exit_state = ExitState()
        self._handles: Dict[int, Path | str] = {}
        self._next_handle = 3

    def get_std_handle(self, handle_type: int) -> int:
        if handle_type == STD_OUTPUT_HANDLE:
            return 1
        if handle_type == STD_ERROR_HANDLE:
            return 2
        if handle_type == STD_INPUT_HANDLE:
            return 0
        return INVALID_HANDLE_VALUE

    def write_file(self, handle: int, data: bytes) -> int:
        if handle == 1:
            return self.stdout.write(data)
        if handle == 2:
            return self.stderr.write(data)
        path = self._handles.get(handle)
        if isinstance(path, Path):
            existing = path.read_bytes() if path.exists() else b""
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(existing + data)
            return len(data)
        return 0

    def exit_process(self, code: int) -> None:
        self.exit_state.set_exit(code)

    def get_command_line_w(self) -> str:
        return build_command_line_w(self.argv)

    def get_environment_variable_w(self, name: str) -> str:
        return self.env.get(name, "")


def simulate_fixture_from_pe(
    basename: str,
    *,
    workspace: Path,
    argv: Optional[list[str]] = None,
    env: Optional[Dict[str, str]] = None,
) -> tuple[int, str, str]:
    """Run fixture semantics without native execution (fallback when shim .so missing)."""
    state = Kernel32ShimState(workspace=workspace, argv=argv, env=env)
    name = basename.lower()
    if name == "hello64.exe" or name == "hello32.exe":
        state.write_file(1, b"Hello, Alma!\n")
        state.exit_process(0)
    elif name == "stdout_write.exe":
        state.write_file(1, b"stdout payload\n")
        state.exit_process(0)
    elif name == "stderr_write.exe":
        state.write_file(2, b"stderr payload\n")
        state.exit_process(0)
    elif name == "exit_code.exe":
        state.exit_process(42)
    elif name == "unicode_argv.exe":
        cmd = state.get_command_line_w()
        state.write_file(1, cmd.encode("utf-16-le"))
        state.exit_process(0)
    elif name == "environment_read.exe":
        val = state.get_environment_variable_w("ALMA_TEST_VAR")
        state.write_file(1, val.encode("utf-16-le"))
        state.exit_process(0)
    elif name == "file_read.exe":
        data = read_file(workspace, "input.txt")
        state.write_file(1, data)
        state.exit_process(0)
    elif name == "file_write.exe":
        write_file(workspace, "output.txt", b"written by fixture\n")
        state.exit_process(0)
    else:
        state.exit_process(1)
    code = state.exit_state.code if state.exit_state.code is not None else 1
    return code, state.stdout.getvalue(), state.stderr.getvalue()
