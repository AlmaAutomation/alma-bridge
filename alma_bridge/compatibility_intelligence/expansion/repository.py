"""Plan persistence — read-only generation, optional cache."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from alma_bridge.compatibility_intelligence.expansion.models import RuntimeExpansionPlan
from alma_bridge.config import settings


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ExpansionPlanRepository:
    """Optional file-backed cache for generated plans — does not mutate registry."""

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        self._store_dir = store_dir or (
            settings.data_dir / "compatibility_intelligence" / "expansion"
        )
        self._last_plan: Optional[RuntimeExpansionPlan] = None

    def save_plan(self, plan: RuntimeExpansionPlan) -> RuntimeExpansionPlan:
        self._store_dir.mkdir(parents=True, exist_ok=True)
        path = self._store_dir / f"{plan.plan_id}.json"
        path.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        latest = self._store_dir / "latest.json"
        latest.write_text(json.dumps({"plan_id": plan.plan_id}), encoding="utf-8")
        self._last_plan = plan
        return plan

    def get_plan(self, plan_id: str) -> Optional[RuntimeExpansionPlan]:
        if self._last_plan and self._last_plan.plan_id == plan_id:
            return self._last_plan
        path = self._store_dir / f"{plan_id}.json"
        if path.is_file():
            plan = RuntimeExpansionPlan.model_validate_json(path.read_text(encoding="utf-8"))
            self._last_plan = plan
            return plan
        return None

    def get_latest_plan(self) -> Optional[RuntimeExpansionPlan]:
        latest = self._store_dir / "latest.json"
        if latest.is_file():
            data = json.loads(latest.read_text(encoding="utf-8"))
            return self.get_plan(str(data["plan_id"]))
        if self._last_plan:
            return self._last_plan
        if self._store_dir.is_dir():
            files = sorted(
                self._store_dir.glob("*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            for path in files:
                if path.name == "latest.json":
                    continue
                try:
                    return RuntimeExpansionPlan.model_validate_json(
                        path.read_text(encoding="utf-8")
                    )
                except (json.JSONDecodeError, ValueError):
                    continue
        return None
