"""Autonomous operator loop.

Runs :func:`run_cycle` on an interval in the background so the AI operator can
continuously watch the host and keep it modernized/healed. Off by default; a
caller must explicitly start it (and mutations still obey the brain's policy).
"""

from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone
from typing import Any, Deque, Dict, Optional

from alma_bridge.config import settings
from alma_bridge.operator.brain import run_cycle


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summarize(cycle: Dict[str, Any]) -> Dict[str, Any]:
    """Compact record for the status ring buffer (drops heavy nested payloads)."""
    plan = cycle.get("plan", {})
    obs = cycle.get("observation", {})
    remediation = cycle.get("remediation") or {}
    route_discovery = obs.get("route_discovery") or {}
    winning_route = None
    for r in remediation.get("results") or []:
        ex = r.get("execution") or {}
        if ex.get("winning_route"):
            winning_route = ex["winning_route"]
            break
    return {
        "cycle_at": cycle.get("cycle_at"),
        "trigger": cycle.get("trigger"),
        "applied": cycle.get("applied"),
        "applied_step_ids": cycle.get("applied_step_ids", []),
        "verdict": obs.get("verdict"),
        "lab_readiness_score": obs.get("lab_readiness_score"),
        "action_count": len(plan.get("actions", [])),
        "auto_eligible": len(plan.get("auto_apply_step_ids", [])),
        "auto_mitigations": plan.get("auto_mitigation_count", 0),
        "recommendation": plan.get("recommendation"),
        "execution_success": (cycle.get("execution") or {}).get("success"),
        "remediation_applied": remediation.get("applied"),
        "remediation_success_count": remediation.get("success_count", 0),
        "route_count": route_discovery.get("route_count"),
        "winning_route": winning_route,
    }


class OperatorLoop:
    """Singleton-ish controller for the background operator task."""

    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._running = False
        self._apply = False
        self._interval = 900
        self._started_at: Optional[str] = None
        self._last_tick_at: Optional[str] = None
        self._tick_count = 0
        self._cycles: Deque[Dict[str, Any]] = deque(maxlen=20)
        self._last_error: Optional[str] = None

    @property
    def running(self) -> bool:
        return self._running and self._task is not None and not self._task.done()

    async def _loop(self) -> None:
        try:
            while self._running:
                await self._tick(trigger="loop")
                await asyncio.sleep(max(15, self._interval))
        except asyncio.CancelledError:  # graceful stop
            raise
        except Exception as exc:  # noqa: BLE001 - loop must never crash silently
            self._last_error = str(exc)
            self._running = False

    async def _tick(self, *, trigger: str, sudo_password: Optional[str] = None) -> Dict[str, Any]:
        from alma_bridge.execution.privileges import get_stored_sudo_password

        effective_password = sudo_password or get_stored_sudo_password()
        try:
            cycle = await asyncio.to_thread(
                run_cycle,
                apply=self._apply,
                trigger=trigger,
                sudo_password=effective_password,
            )
            self._cycles.append(_summarize(cycle))
            self._tick_count += 1
            self._last_tick_at = _now()
            self._last_error = None
            return cycle
        except Exception as exc:  # noqa: BLE001
            self._last_error = str(exc)
            raise

    def start(self, *, interval_sec: Optional[int] = None, apply: bool = False) -> Dict[str, Any]:
        if not settings.operator_enabled:
            return {"started": False, "reason": "operator_enabled is false"}
        if self.running:
            return {"started": False, "reason": "already running", **self.status()}
        self._interval = int(interval_sec or settings.operator_interval_sec)
        self._apply = bool(apply)
        self._running = True
        self._started_at = _now()
        self._task = asyncio.create_task(self._loop())
        return {"started": True, **self.status()}

    async def stop(self) -> Dict[str, Any]:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        return {"stopped": True, **self.status()}

    async def tick_once(
        self,
        *,
        apply: bool = False,
        sudo_password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run a single cycle on demand (does not require the loop to be running)."""
        prev = self._apply
        self._apply = bool(apply)
        try:
            return await self._tick(trigger="manual", sudo_password=sudo_password)
        finally:
            self._apply = prev

    def status(self) -> Dict[str, Any]:
        return {
            "running": self.running,
            "apply": self._apply,
            "interval_sec": self._interval,
            "started_at": self._started_at,
            "last_tick_at": self._last_tick_at,
            "tick_count": self._tick_count,
            "last_error": self._last_error,
            "recent_cycles": list(self._cycles),
            "config": {
                "enabled": bool(settings.operator_enabled),
                "autonomy": settings.operator_autonomy,
                "allow_mutations": bool(settings.operator_allow_mutations),
                "apply_all": bool(settings.operator_apply_all),
                "interval_sec": settings.operator_interval_sec,
                "max_risk": settings.operator_max_risk,
                "min_confidence": settings.operator_min_confidence,
            },
        }


# Module-level singleton used by the API layer.
operator_loop = OperatorLoop()
