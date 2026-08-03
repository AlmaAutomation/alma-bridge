"""Query helpers for decision plan validation history."""

from __future__ import annotations

from typing import List, Optional

from alma_bridge.decision_validation.models import DecisionPlanDryRunReport
from alma_bridge.decision_validation.repository import (
    latest_validation_for_plan,
    list_validations_for_plan,
)


def validation_history(plan_id: str) -> List[DecisionPlanDryRunReport]:
    return list_validations_for_plan(plan_id)


def latest_validation(plan_id: str) -> Optional[DecisionPlanDryRunReport]:
    return latest_validation_for_plan(plan_id)
