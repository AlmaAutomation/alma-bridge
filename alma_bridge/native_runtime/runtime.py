"""Native runtime orchestration."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from alma_bridge.native_runtime.api.kernel32 import simulate_fixture_from_pe
from alma_bridge.native_runtime.eligibility import check_eligibility, pe_binary_digest
from alma_bridge.native_runtime.errors import (
    NativeRuntimeError,
    REASON_EXEC_FAILED,
    REASON_SHIM_MISSING,
)
from alma_bridge.native_runtime.loader.entrypoint import (
    capture_shim_output,
    invoke_native_load_and_run,
    shim_available,
)
from alma_bridge.native_runtime.models import NativeRunResult, PEInspection
from alma_bridge.native_runtime.tracing import trace


def _simulation_forced() -> bool:
    return os.environ.get("ALMA_NATIVE_SIMULATION", "") == "1"


def inspect_file(file_path: str | Path) -> PEInspection:
    from alma_bridge.native_runtime.eligibility import inspect_pe

    return inspect_pe(file_path)


def run_pe_in_workspace(
    file_path: str | Path,
    *,
    argv: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    workspace: Optional[Path] = None,
    use_simulation: bool = False,
    load_base_override: Optional[int] = None,
) -> NativeRunResult:
    path = Path(file_path)
    eligibility = check_eligibility(path)
    digest = pe_binary_digest(path) if path.is_file() else None
    if not eligibility.eligible:
        return NativeRunResult(
            success=False,
            error="PE not eligible for native runtime",
            reason_codes=eligibility.reason_codes,
            binary_digest=digest,
        )
    owns_workspace = workspace is None
    ws = workspace or Path(tempfile.mkdtemp(prefix="alma-native-"))
    try:
        target = ws / path.name
        if not target.exists() or path.resolve() != target.resolve():
            shutil.copy2(path, target)
        force_sim = use_simulation or _simulation_forced()
        if force_sim or not shim_available():
            if not force_sim and not shim_available():
                trace("shim missing; simulation unavailable in production path")
                return NativeRunResult(
                    success=False,
                    error="native shim library not built",
                    reason_codes=[REASON_SHIM_MISSING],
                    binary_digest=digest,
                )
            trace("using explicit fixture simulation (ALMA_NATIVE_SIMULATION=1 or use_simulation=True)")
            code, stdout, stderr = simulate_fixture_from_pe(
                path.name.lower(),
                workspace=ws,
                argv=argv or [path.name],
                env=env,
            )
            return NativeRunResult(
                exit_code=code,
                stdout=stdout,
                stderr=stderr,
                success=True,
                simulation_used=True,
                entrypoint_invoked=False,
                native_execution_mode="python_fixture_simulation",
                binary_digest=digest,
                metadata={"mode": "simulation"},
            )
        pe_bytes = path.read_bytes()
        override = load_base_override or 0
        exit_code, invoked, simulation, mode = invoke_native_load_and_run(
            pe_bytes,
            workspace=ws,
            argv=argv or [path.name],
            env=env,
            load_base_override=override,
        )
        stdout, stderr = capture_shim_output()
        return NativeRunResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            success=True,
            simulation_used=simulation,
            entrypoint_invoked=invoked,
            native_execution_mode=mode,
            load_base=override or None,
            binary_digest=digest,
            metadata={"mode": mode},
        )
    except NativeRuntimeError as exc:
        return NativeRunResult(
            success=False,
            error=str(exc),
            reason_codes=getattr(exc, "reason_codes", [REASON_EXEC_FAILED]),
            binary_digest=digest,
        )
    except Exception as exc:
        return NativeRunResult(
            success=False,
            error=str(exc),
            reason_codes=[REASON_EXEC_FAILED],
            binary_digest=digest,
        )
    finally:
        if owns_workspace:
            shutil.rmtree(ws, ignore_errors=True)
