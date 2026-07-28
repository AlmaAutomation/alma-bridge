"""Read-only Compatibility Regression Intelligence."""

from alma_bridge.regression.models import (
    CompatibilityRegressionReport,
    RegressionFinding,
)
from alma_bridge.regression.service import CompatibilityRegressionService

__all__ = [
    "CompatibilityRegressionReport",
    "CompatibilityRegressionService",
    "RegressionFinding",
]
