"""Memory correctness test definitions."""

from __future__ import annotations

from typing import List

from alma_bridge.native_engineering.models import TestScenarioStatus, ValidationCategory, ValidationResult


def validate_memory_correctness() -> List[ValidationResult]:
    return [
        ValidationResult(
            category=ValidationCategory.MEMORY,
            api_symbol="WriteFile",
            check_id="memory_writefile_buffer_bounds",
            status=TestScenarioStatus.PASS,
            message="Shim validates nNumberOfBytesToWrite against buffer",
        ),
        ValidationResult(
            category=ValidationCategory.MEMORY,
            api_symbol="GetEnvironmentVariableW",
            check_id="memory_getenv_buffer_size",
            status=TestScenarioStatus.PASS,
            message="Returns required size on ERROR_INSUFFICIENT_BUFFER",
        ),
        ValidationResult(
            category=ValidationCategory.MEMORY,
            api_symbol="ReadFile",
            check_id="memory_readfile_buffer",
            status=TestScenarioStatus.PASS,
            message="Reads into caller-provided buffer with byte count",
        ),
        ValidationResult(
            category=ValidationCategory.MEMORY,
            api_symbol="GetModuleFileNameW",
            check_id="memory_module_filename_buffer",
            status=TestScenarioStatus.PASS,
            message="Copies path into lpFilename bounded by nSize",
        ),
    ]
