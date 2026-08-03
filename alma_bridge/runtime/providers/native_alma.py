"""Experimental native Alma runtime provider (Milestone 1)."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from alma_bridge.config import settings
from alma_bridge.native_runtime.eligibility import inspect_pe
from alma_bridge.native_runtime.runtime import run_pe_in_workspace
from alma_bridge.runtime.capabilities import CapabilityState, PE_CONSOLE, RuntimeCapabilities
from alma_bridge.runtime.errors import RuntimeNotSupportedError
from alma_bridge.runtime.models import (
    LaunchHandle,
    PrepareResult,
    RuntimeInspection,
    RuntimeObservation,
    TerminationResult,
)

_PROVIDER_VERSION = "0.1.0-m1"

# In-memory handle store for observe/terminate (worker subprocess jobs)
_HANDLES: Dict[str, Dict[str, object]] = {}


def _runtime_enabled() -> bool:
    return bool(settings.native_runtime_enabled and settings.allow_experimental_runtimes)


class NativeAlmaRuntime:
    """Experimental native console PE provider — isolated worker subprocess."""

    @property
    def provider_id(self) -> str:
        return "native_alma"

    @property
    def provider_version(self) -> str:
        return _PROVIDER_VERSION

    def capabilities(self) -> RuntimeCapabilities:
        state = CapabilityState.SUPPORTED if _runtime_enabled() else CapabilityState.PARTIAL
        if not settings.native_runtime_enabled:
            state = CapabilityState.UNKNOWN
        return RuntimeCapabilities.from_states(**{PE_CONSOLE: state})

    def inspect(
        self,
        file_path: str,
        *,
        env: Optional[Dict[str, str]] = None,
    ) -> RuntimeInspection:
        inspection = inspect_pe(file_path)
        notes = list(inspection.notes)
        if inspection.reason_codes:
            notes.extend(f"reason:{code}" for code in inspection.reason_codes)
        if not _runtime_enabled():
            notes.append("native runtime flags disabled (inspect-only)")
        return RuntimeInspection(
            provider_id=self.provider_id,
            file_path=file_path,
            binary_format="pe" if inspection.machine else None,
            ready=inspection.eligible and _runtime_enabled(),
            notes=notes,
            metadata={
                "machine": inspection.machine,
                "subsystem": inspection.subsystem,
                "import_dlls": inspection.import_dlls,
                "reason_codes": inspection.reason_codes,
                "eligible": inspection.eligible,
            },
        )

    def prepare(
        self,
        file_path: str,
        *,
        command: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> PrepareResult:
        inspection = self.inspect(file_path, env=env)
        if not inspection.ready:
            raise RuntimeNotSupportedError(
                "Native Alma runtime not ready: "
                + "; ".join(inspection.notes) or "eligibility or flags failed"
            )
        argv = command or [str(Path(file_path).name)]
        worker_cmd = [
            sys.executable,
            "-m",
            "alma_bridge.native_runtime.worker",
            "{job_file}",
        ]
        return PrepareResult(
            provider_id=self.provider_id,
            command=worker_cmd,
            env=dict(env or {}),
            ready=True,
            notes=["launch via isolated worker subprocess"],
            metadata={"argv": argv, "file_path": file_path},
        )

    def launch(
        self,
        file_path: str,
        *,
        command: Optional[List[str]] = None,
        env: Optional[Dict[str, str]] = None,
    ) -> LaunchHandle:
        prepared = self.prepare(file_path, command=command, env=env)
        handle_id = str(uuid.uuid4())
        workspace = tempfile.mkdtemp(prefix="alma-native-ws-")
        job = {
            "file_path": str(Path(file_path).resolve()),
            "argv": command or [Path(file_path).name],
            "env": dict(env or {}),
            "workspace": workspace,
            "use_simulation": True,
        }
        job_file = Path(workspace) / "job.json"
        job_file.write_text(json.dumps(job), encoding="utf-8")
        proc = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "alma_bridge.native_runtime.worker",
                str(job_file),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        _HANDLES[handle_id] = {
            "proc": proc,
            "workspace": workspace,
            "job_file": str(job_file),
        }
        return LaunchHandle(
            provider_id=self.provider_id,
            command=prepared.command,
            env=prepared.env,
            pid=proc.pid,
            launched=True,
            file_path=str(Path(file_path).resolve()),
            handle_token=handle_id,
        )

    def observe(self, handle: LaunchHandle) -> RuntimeObservation:
        handle_id = handle.handle_token
        if not handle_id or handle_id not in _HANDLES:
            if handle.file_path:
                result = run_pe_in_workspace(handle.file_path, use_simulation=True)
                return RuntimeObservation(
                    provider_id=self.provider_id,
                    running=False,
                    exit_code=result.exit_code,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    notes=["direct observation (no handle)"],
                )
            raise RuntimeNotSupportedError("no active native runtime handle")
        entry = _HANDLES[handle_id]
        proc = entry["proc"]
        stdout, stderr = proc.communicate(timeout=120)
        try:
            payload = json.loads(stdout or "{}")
        except json.JSONDecodeError:
            payload = {"success": False, "error": stderr or "worker failed"}
        return RuntimeObservation(
            provider_id=self.provider_id,
            running=proc.poll() is None,
            exit_code=payload.get("exit_code"),
            stdout=str(payload.get("stdout") or ""),
            stderr=str(payload.get("stderr") or ""),
            notes=["worker subprocess completed"],
        )

    def terminate(self, handle: LaunchHandle) -> TerminationResult:
        handle_id = handle.handle_token
        if handle_id and handle_id in _HANDLES:
            proc = _HANDLES[handle_id]["proc"]
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
            return TerminationResult(
                provider_id=self.provider_id,
                terminated=True,
                exit_code=proc.returncode,
            )
        return TerminationResult(
            provider_id=self.provider_id,
            terminated=False,
            notes=["no active handle"],
        )

    def teardown(self, handle: LaunchHandle) -> None:
        handle_id = handle.handle_token
        if handle_id and handle_id in _HANDLES:
            entry = _HANDLES.pop(handle_id)
            import shutil

            shutil.rmtree(str(entry.get("workspace", "")), ignore_errors=True)
