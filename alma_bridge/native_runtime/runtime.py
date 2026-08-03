"""Native runtime orchestration."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from alma_bridge.native_runtime.api.kernel32 import simulate_fixture_from_pe
from alma_bridge.native_runtime.eligibility import FIXTURE_ALLOWLIST, check_eligibility
from alma_bridge.native_runtime.errors import (
    EligibilityError,
    ExecutionError,
    NativeRuntimeError,
    REASON_DISABLED,
    REASON_EXEC_FAILED,
    REASON_SHIM_MISSING,
)
from alma_bridge.native_runtime.loader.entrypoint import (
    capture_shim_output,
    invoke_entry,
    shim_available,
)
from alma_bridge.native_runtime.loader.image import map_pe_image
from alma_bridge.native_runtime.models import NativeRunResult, PEInspection
from alma_bridge.native_runtime.tracing import trace


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
) -> NativeRunResult:
    path = Path(file_path)
    eligibility = check_eligibility(path)
    if not eligibility.eligible:
        return NativeRunResult(
            success=False,
            error="PE not eligible for native runtime",
            reason_codes=eligibility.reason_codes,
        )
    owns_workspace = workspace is None
    ws = workspace or Path(tempfile.mkdtemp(prefix="alma-native-"))
    try:
        if path.name.lower() not in FIXTURE_ALLOWLIST:
            shutil.copy2(path, ws / path.name)
        target = ws / path.name if path.name.lower() in FIXTURE_ALLOWLIST else ws / path.name
        if not target.exists():
            shutil.copy2(path, target)
        basename = path.name.lower()
        if use_simulation or not shim_available():
            trace("using fixture simulation fallback")
            code, stdout, stderr = simulate_fixture_from_pe(
                basename,
                workspace=ws,
                argv=argv or [path.name],
                env=env,
            )
            return NativeRunResult(
                exit_code=code,
                stdout=stdout,
                stderr=stderr,
                success=True,
                metadata={"mode": "simulation"},
            )
        loaded = map_pe_image(eligibility.parsed)  # type: ignore[arg-type]
        exit_code = invoke_entry(loaded, workspace=ws)
        stdout, stderr = capture_shim_output()
        return NativeRunResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            success=True,
            metadata={"mode": "native_shim"},
        )
    except NativeRuntimeError as exc:
        return NativeRunResult(
            success=False,
            error=str(exc),
            reason_codes=getattr(exc, "reason_codes", [REASON_EXEC_FAILED]),
        )
    except Exception as exc:
        return NativeRunResult(
            success=False,
            error=str(exc),
            reason_codes=[REASON_EXEC_FAILED],
        )
    finally:
        if owns_workspace:
            shutil.rmtree(ws, ignore_errors=True)
