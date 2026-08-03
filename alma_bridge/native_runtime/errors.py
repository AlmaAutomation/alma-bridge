"""Native runtime error types and reason codes."""

from __future__ import annotations

# Fail-closed reason codes (stable strings for tests and API)
REASON_HOST_ARCH = "host_arch_unsupported"
REASON_NO_32BIT_WORKER = "no_32bit_worker"
REASON_NOT_PE = "not_pe"
REASON_INVALID_PE = "invalid_pe"
REASON_GUI_SUBSYSTEM = "gui_subsystem"
REASON_TLS_PRESENT = "tls_present"
REASON_DELAY_IMPORT = "delay_import"
REASON_DOTNET = "dotnet_indicator"
REASON_COM = "com_indicator"
REASON_IMPORT_NOT_ALLOWED = "import_not_allowed"
REASON_NOT_ALLOWLISTED = "not_allowlisted"
REASON_DISABLED = "native_runtime_disabled"
REASON_SHIM_MISSING = "shim_library_missing"
REASON_LOAD_FAILED = "load_failed"
REASON_EXEC_FAILED = "exec_failed"


class NativeRuntimeError(Exception):
    """Base error for native runtime operations."""

    def __init__(self, message: str, *, reason_codes: list[str] | None = None) -> None:
        super().__init__(message)
        self.reason_codes = list(reason_codes or [])


class PEParseError(NativeRuntimeError):
    """PE structure could not be parsed."""


class EligibilityError(NativeRuntimeError):
    """PE failed eligibility checks."""


class LoadError(NativeRuntimeError):
    """PE image could not be loaded."""


class ExecutionError(NativeRuntimeError):
    """PE entry execution failed."""
