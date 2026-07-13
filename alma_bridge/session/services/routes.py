from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from alma_bridge.automation.bridge_pathways import build_bridge_signature_pathways
from alma_bridge.compatibility.planner import build_execution_plan
from alma_bridge.compliance.autopilot import plan_pathways
from alma_bridge.execution.errors import detect_error_signature
from alma_bridge.hardware.prefixes import find_best_prefix
from alma_bridge.learning.remediation import remediations_for_signature


def _first_file_path(failures: Optional[List[Dict[str, Any]]]) -> Optional[str]:
    for failure in failures or []:
        for key in ("file_path", "bridge_target", "scan_path"):
            val = failure.get(key)
            if val and Path(str(val)).exists():
                return str(val)
    return None


def _bridge_signature_from_context(
    error_text: str,
    failures: Optional[List[Dict[str, Any]]],
) -> str:
    for failure in failures or []:
        sig = failure.get("error_signature")
        if sig:
            return str(sig)
    if error_text:
        return detect_error_signature(error_text, error_text)
    return "unknown_error"


def _top_remediation_id(signature: str, *, file_path: Optional[str]) -> Optional[str]:
    is_pe = (file_path or "").lower().endswith((".exe", ".msi", ".bat", ".cmd"))
    rems = remediations_for_signature(signature, electron=is_pe, installer=False)
    for rem in rems:
        rid = rem.get("id")
        if rid and rid != "baseline_retry":
            return rid
    return None


def _pathway_route(pathway: Dict[str, Any], *, fp: Optional[str], error_text: str, sig: str) -> Dict[str, Any]:
    return {
        "id": f"pathway:{pathway.get('id', 'unknown')}",
        "kind": "pathway",
        "title": pathway.get("title", pathway.get("id", "pathway")),
        "score": float(pathway.get("score", 0.5)) + (0.08 if pathway.get("synthesized") else 0),
        "pathway": pathway,
        "pathway_id": pathway.get("id"),
        "signature": sig,
        "error_text": error_text,
        "file_path": fp,
        "synthesized": bool(pathway.get("synthesized")),
        "verify_bridge": bool(fp),
    }


class RouteDiscoveryService:
    def discover(
        self,
        error_text: str,
        *,
        file_path: Optional[str] = None,
        failures: Optional[List[Dict[str, Any]]] = None,
        os_release: Optional[str] = None,
    ) -> Dict[str, Any]:
        error_text = (error_text or "").strip()
        fp = file_path or _first_file_path(failures)
        bridge_sig = _bridge_signature_from_context(error_text, failures)
        routes: List[Dict[str, Any]] = []

        healing: Optional[Dict[str, Any]] = None
        host_sig = "unknown_error"

        if error_text:
            healing = plan_pathways(error_text, os_release=os_release)
            host_sig = healing.get("primary_signature") or "unknown_error"

            for pathway in build_bridge_signature_pathways(
                bridge_sig, error_text=error_text, file_path=fp
            ):
                routes.append(_pathway_route(pathway, fp=fp, error_text=error_text, sig=bridge_sig))

            for pathway in healing.get("pathways") or []:
                routes.append(_pathway_route(pathway, fp=fp, error_text=error_text, sig=host_sig))

        primary_sig = bridge_sig if bridge_sig != "unknown_error" else host_sig
        preferred_remediation = _top_remediation_id(primary_sig, file_path=fp)

        if fp and (
            bridge_sig in {"dotnet_missing", "missing_dll", "missing_visual_c_runtime"}
            or "rundll32" in error_text.lower()
            or "ascension" in fp.lower()
        ):
            routes.append({
                "id": f"route:wine_prefix_bootstrap:{Path(fp).name}",
                "kind": "wine_prefix_bootstrap",
                "title": "AI/ML — repair VC++ / .NET in Bridge Wine prefix",
                "score": 0.995,
                "file_path": fp,
                "error_text": error_text or None,
                "bridge_signature": bridge_sig,
                "preferred_remediation_id": preferred_remediation,
                "verify_bridge": True,
            })

        if fp and Path(fp).exists():
            try:
                plans = build_execution_plan(fp, error_signature=primary_sig)
                for i, plan in enumerate(plans[:8]):
                    base = float(plan.get("rank_score") or plan.get("success_probability") or 0.5)
                    routes.append({
                        "id": f"bridge:{plan.get('strategy_id', i)}:{Path(fp).name}",
                        "kind": "bridge",
                        "title": f"Bridge — {plan.get('description', plan.get('strategy_id'))}",
                        "score": base + 0.04,
                        "file_path": fp,
                        "strategy_id": plan.get("strategy_id"),
                        "bridge_plan": plan,
                        "error_text": error_text or None,
                        "bridge_signature": primary_sig,
                        "preferred_remediation_id": preferred_remediation,
                    })
            except Exception:  # noqa: BLE001
                pass

            if not any(r["kind"] == "bridge" for r in routes):
                routes.append({
                    "id": f"bridge:adaptive:{Path(fp).name}",
                    "kind": "bridge",
                    "title": f"Bridge adaptive run — {Path(fp).name}",
                    "score": 0.9,
                    "file_path": fp,
                    "error_text": error_text or None,
                    "bridge_signature": primary_sig,
                    "preferred_remediation_id": preferred_remediation,
                })

        if fp and error_text:
            top_pathway = None
            for route in routes:
                if route.get("kind") == "pathway":
                    top_pathway = route.get("pathway")
                    break
            routes.append({
                "id": f"route:heal_then_bridge:{Path(fp).name}",
                "kind": "heal_then_bridge",
                "title": "Apply top fix, then verify Bridge launch",
                "score": 0.93,
                "file_path": fp,
                "error_text": error_text,
                "pathway": top_pathway,
                "bridge_signature": primary_sig,
                "preferred_remediation_id": preferred_remediation,
                "verify_bridge": True,
            })

        routes.sort(key=lambda r: r.get("score", 0), reverse=True)
        deduped: List[Dict[str, Any]] = []
        seen: set[str] = set()
        for route in routes:
            if route["id"] in seen:
                continue
            seen.add(route["id"])
            deduped.append(route)

        return {
            "error_text": error_text or None,
            "file_path": fp,
            "route_count": len(deduped),
            "routes": deduped,
            "primary_signature": primary_sig,
            "bridge_signature": bridge_sig,
            "host_signature": host_sig if error_text else None,
            "preferred_remediation_id": preferred_remediation,
        }


class RouteSelectionService:
    def select(self, discovery: Dict[str, Any], *, budget: int) -> List[Dict[str, Any]]:
        routes = discovery.get("routes") or []
        return routes[: max(1, budget)]


@dataclass
class RouteExecutionContext:
    session_id: str
    correlation_id: str
    file_path: str
    wine_prefix: Optional[str]
    error_text: str
    bridge_signature: Optional[str]
    preferred_remediation_id: Optional[str]
    sudo_password: Optional[str] = None
    auto_remediate: Optional[bool] = None


@dataclass
class RouteExecutionResult:
    route_id: str
    kind: str
    success: bool
    summary: str = ""
    error: Optional[str] = None
    prefix_fix: Optional[Dict[str, Any]] = None
    heal: Optional[Dict[str, Any]] = None
    execution_payload: Dict[str, Any] = field(default_factory=dict)
    requires_bridge_retry: bool = False
    preferred_strategy_id: Optional[str] = None
    preferred_remediation_id: Optional[str] = None


class RouteExecutionService(Protocol):
    def execute_route(
        self,
        route: Dict[str, Any],
        discovery: Dict[str, Any],
        context: RouteExecutionContext,
        *,
        apply: bool,
        allow_host_mutations: bool,
    ) -> RouteExecutionResult: ...


class DefaultRouteExecutionService:
    """Executes one route without owning session lifecycle or BridgeOrchestrator."""

    def execute_route(
        self,
        route: Dict[str, Any],
        discovery: Dict[str, Any],
        context: RouteExecutionContext,
        *,
        apply: bool,
        allow_host_mutations: bool,
    ) -> RouteExecutionResult:
        if not apply:
            return RouteExecutionResult(
                route_id=route["id"],
                kind=route.get("kind", "unknown"),
                success=False,
                summary="dry-run",
            )

        kind = route.get("kind")
        try:
            if kind == "wine_prefix_bootstrap":
                return self._wine_prefix_bootstrap(route, discovery, context)
            if kind == "pathway":
                return self._pathway(route, discovery, context, allow_host_mutations=allow_host_mutations)
            if kind == "bridge":
                return RouteExecutionResult(
                    route_id=route["id"],
                    kind=kind,
                    success=False,
                    summary="bridge_retry_required",
                    requires_bridge_retry=True,
                    preferred_strategy_id=route.get("strategy_id"),
                    preferred_remediation_id=(
                        route.get("preferred_remediation_id")
                        or discovery.get("preferred_remediation_id")
                    ),
                )
            if kind == "heal_then_bridge":
                heal = self._pathway(
                    {
                        **route,
                        "kind": "pathway",
                        "pathway": route.get("pathway"),
                        "pathway_id": (route.get("pathway") or {}).get("id"),
                    },
                    discovery,
                    context,
                    allow_host_mutations=allow_host_mutations,
                )
                return RouteExecutionResult(
                    route_id=route["id"],
                    kind=kind,
                    success=False,
                    summary="heal_then_bridge_retry_required",
                    heal=heal.heal,
                    requires_bridge_retry=True,
                    preferred_remediation_id=discovery.get("preferred_remediation_id"),
                )
            return RouteExecutionResult(
                route_id=route["id"],
                kind=str(kind),
                success=False,
                summary=f"unknown route kind {kind}",
            )
        except Exception as exc:  # noqa: BLE001
            return RouteExecutionResult(
                route_id=route["id"],
                kind=str(kind),
                success=False,
                summary="route_execution_failed",
                error=str(exc),
            )

    def _wine_prefix_bootstrap(
        self,
        route: Dict[str, Any],
        discovery: Dict[str, Any],
        context: RouteExecutionContext,
    ) -> RouteExecutionResult:
        from alma_bridge.execution.preflight import apply_ml_wine_fix

        fp = route.get("file_path") or discovery.get("file_path") or context.file_path
        prefix = context.wine_prefix or (find_best_prefix(fp) if fp else None)
        sig = (
            route.get("bridge_signature")
            or discovery.get("bridge_signature")
            or "dotnet_missing"
        )
        if not prefix:
            return RouteExecutionResult(
                route_id=route["id"],
                kind="wine_prefix_bootstrap",
                success=False,
                summary="no Wine prefix found for file",
            )
        fix = apply_ml_wine_fix(
            sig,
            prefix,
            fp or "",
            session_id=context.session_id,
            correlation_id=context.correlation_id,
            auto_remediate=context.auto_remediate,
        )
        return RouteExecutionResult(
            route_id=route["id"],
            kind="wine_prefix_bootstrap",
            success=bool(fix.get("actions")),
            summary="prefix_bootstrap_complete" if fix.get("actions") else "prefix_bootstrap_noop",
            prefix_fix=fix,
            requires_bridge_retry=bool(route.get("verify_bridge")),
            preferred_remediation_id=discovery.get("preferred_remediation_id"),
        )

    def _pathway(
        self,
        route: Dict[str, Any],
        discovery: Dict[str, Any],
        context: RouteExecutionContext,
        *,
        allow_host_mutations: bool,
    ) -> RouteExecutionResult:
        from alma_bridge.compliance.autopilot import run_autopilot

        err = route.get("error_text") or discovery.get("error_text") or context.error_text or ""
        heal = run_autopilot(
            err,
            execute=True,
            allow_mutations=allow_host_mutations,
            pathway_id=route.get("pathway_id"),
            try_all_pathways=False,
            max_pathway_attempts=1,
        )
        success = bool(heal.get("success")) if discovery.get("file_path") is None else False
        return RouteExecutionResult(
            route_id=route["id"],
            kind="pathway",
            success=success,
            summary=str(heal.get("summary") or "pathway_executed"),
            heal=heal,
            requires_bridge_retry=bool(route.get("verify_bridge") and discovery.get("file_path")),
            preferred_remediation_id=discovery.get("preferred_remediation_id"),
        )
