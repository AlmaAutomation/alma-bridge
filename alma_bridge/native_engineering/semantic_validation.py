"""API semantic validation results."""

from __future__ import annotations

from typing import List

from alma_bridge.native_engineering.models import TestScenarioStatus, ValidationCategory, ValidationResult
from alma_bridge.native_engineering.specifications import get_all_specifications


def validate_api_semantics() -> List[ValidationResult]:
    results: List[ValidationResult] = []
    for sym, spec in get_all_specifications().items():
        status = TestScenarioStatus.PASS if spec.success_semantics else TestScenarioStatus.PENDING
        results.append(
            ValidationResult(
                category=ValidationCategory.API_SEMANTIC,
                api_symbol=sym,
                check_id=f"semantic_{sym.lower()}",
                status=status,
                message=f"{len(spec.supported_behaviors)} supported, {len(spec.unsupported_behaviors)} unsupported",
            )
        )
        for err in spec.error_modes:
            results.append(
                ValidationResult(
                    category=ValidationCategory.API_SEMANTIC,
                    api_symbol=sym,
                    check_id=f"error_mode_{sym.lower()}_{err.error_name or err.condition[:20]}",
                    status=TestScenarioStatus.PASS,
                    message=err.condition,
                )
            )
    return results
