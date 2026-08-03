"""Multi-thread behavior validation — deferred for M2 single-threaded worker."""

from __future__ import annotations

from typing import List

from alma_bridge.native_engineering.models import TestScenarioStatus, ValidationCategory, ValidationResult


def validate_threading() -> List[ValidationResult]:
    return [
        ValidationResult(
            category=ValidationCategory.THREADING,
            api_symbol="*",
            check_id="threading_single_worker",
            status=TestScenarioStatus.NOT_APPLICABLE,
            message="M2 worker is single-threaded; no CreateThread shims",
        ),
        ValidationResult(
            category=ValidationCategory.THREADING,
            api_symbol="GetLastError",
            check_id="threading_tls_deferred",
            status=TestScenarioStatus.DEFERRED,
            message="g_last_error is process-global in shim, not per-thread TLS",
        ),
    ]
