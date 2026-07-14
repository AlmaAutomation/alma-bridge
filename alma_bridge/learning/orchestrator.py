from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from alma_bridge.compatibility.electron_wine import apply_electron_remediation_shims, prepare_electron_wine
from alma_bridge.compatibility.planner import build_execution_plan
from alma_bridge.compatibility.program_kind import classify_program_kind
from alma_bridge.compatibility.profile_creation import (
    ProfileCandidateService,
    ProfileCreationService,
    VerifiedAttemptInputs,
)
from alma_bridge.compatibility.profile_shadow import ProfileShadowService
from alma_bridge.compatibility.profile_shadow_models import (
    ShadowActualInputs,
    ShadowPlanningInputs,
)
from alma_bridge.config import settings
from alma_bridge.execution.container_checks import sandbox_ready
from alma_bridge.execution.errors import (
    RECOMMENDED_ACTIONS,
    detect_error_signature,
    format_wine_log_for_display,
)
from alma_bridge.bridge.prefix_profile import (
    PrefixReadinessProfile,
    invalidate_prefix_profile,
    load_prefix_profile,
    profile_allows_fast_launch,
    save_prefix_profile,
)
from alma_bridge.execution.installer_verify import (
    PrefixSnapshot,
    ascension_wrappers_present,
    discover_installed_launcher,
    launcher_ready_for_handoff,
    launcher_verified_in_prefix,
    snapshot_wine_prefix,
)
from alma_bridge.execution.preflight import (
    apply_ml_wine_fix,
    ascension_wine_preflight,
    bootstrap_wine_runtimes,
    ensure_wine_windows_version,
    prefix_dotnet_functional,
    prefix_runtimes_ready,
    read_wine_windows_version,
    repair_wine_runtimes,
    require_wine_windows_version,
    run_winetricks,
    set_wine_windows_version,
)
from alma_bridge.execution.privileges import passwordless_sudo_works, prepare_sudo, resolve_use_sudo
from alma_bridge.execution.runner import execute_attempt, file_hash
from alma_bridge.execution.wine_process import snapshot_wine_pids
from alma_bridge.hardware.prefixes import find_best_prefix
from alma_bridge.hardware.profiler import profile_hardware
from alma_bridge.hardware.shims import shims_for_indicators
from alma_bridge.hardware.proton_env import build_proton_env
from alma_bridge.learning.installer import (
    apply_electron_launch_overrides,
    default_installer_args,
    electron_launch_env,
    electron_software_gl_args,
    fresh_prefix_path,
)
from alma_bridge.learning.ranker import rerank_plans
from alma_bridge.learning.remediation import (
    apply_remediation,
    get_remediation_by_id,
    next_electron_launcher_remediation,
    next_launcher_remediation,
    remediations_for_signature,
)
from alma_bridge.schemas.models import (
    AttemptRecord,
    BridgeRequest,
    BridgeSessionResult,
    ExecutionMode,
    RerankEvent,
)
from alma_bridge.session.auto_compat_budget import (
    AUTO_COMPATIBILITY_BUDGET_EXHAUSTED,
    AutoCompatibilityBudget,
)
from alma_bridge.session.fingerprint import RetryGuard, remediation_fingerprint
from alma_bridge.session.lease import SessionLeaseManager
from alma_bridge.session.lifecycle import InvalidSessionTransition, SessionLifecycleManager
from alma_bridge.session.mutations import (
    build_remediation_intent,
    build_route_intent,
    evaluate_or_block,
    run_prefix_mutation,
)
from alma_bridge.session.policy import ActionIntent, ActionType, ExecutionScope, MutationScope, PolicyGate
from alma_bridge.session.services.inspector import DefaultCompatibilityInspector
from alma_bridge.session.services.planner import (
    DefaultCompatibilityPlanner,
    ExecutionPlan,
    plan_step_to_dict,
)
from alma_bridge.session.services.routes import (
    DefaultRouteExecutionService,
    RouteDiscoveryService,
    RouteExecutionContext,
    RouteSelectionService,
)
from alma_bridge.session.services.verification import (
    DefaultVerificationEngine,
    ExecutionEvidence,
    VerificationResult,
)
from alma_bridge.session.state import SessionState
from alma_bridge.session.verification_gateway import (
    VerificationBoundaryResult,
    VerificationGateway,
    declare_verified_session_success,
)
from alma_bridge.storage import outcomes


class BridgeOrchestrator:
    """Closed-loop executor: plan → run → classify → remediate → retry → learn."""

    def __init__(
        self,
        *,
        inspector: DefaultCompatibilityInspector | None = None,
        planner: DefaultCompatibilityPlanner | None = None,
        verifier: DefaultVerificationEngine | None = None,
        policy: PolicyGate | None = None,
        route_discovery: RouteDiscoveryService | None = None,
        route_selection: RouteSelectionService | None = None,
        route_executor: DefaultRouteExecutionService | None = None,
        lease_manager: SessionLeaseManager | None = None,
    ) -> None:
        self._inspector = inspector or DefaultCompatibilityInspector()
        self._planner = planner or DefaultCompatibilityPlanner()
        self._verifier = verifier or DefaultVerificationEngine()
        self._policy = policy or PolicyGate()
        self._route_discovery = route_discovery or RouteDiscoveryService()
        self._route_selection = route_selection or RouteSelectionService()
        self._route_executor = route_executor or DefaultRouteExecutionService()
        self._lease_manager = lease_manager or SessionLeaseManager()
        self._verification_gateway = VerificationGateway(
            self._verifier,
            transition=self._transition,
        )

    def run(
        self,
        request: BridgeRequest,
        *,
        session_id: Optional[str] = None,
        cancel_check: Optional[callable] = None,
    ) -> BridgeSessionResult:
        started_at = datetime.now(timezone.utc)
        hardware = profile_hardware()
        digest = file_hash(request.file_path)
        if session_id is None:
            timeout_at = None
            if settings.session_timeout_sec:
                from datetime import timedelta

                timeout_at = (
                    started_at + timedelta(seconds=settings.session_timeout_sec)
                ).isoformat()
            session_id = outcomes.new_session(
                request.file_path,
                digest,
                hardware,
                session_timeout_at=timeout_at,
            )

        lifecycle = SessionLifecycleManager(session_id)
        lease = self._lease_manager.acquire(session_id)
        if not lease.acquired:
            summary = "Another worker holds the session lease for this Bridge run."
            outcomes.finalize_session(session_id, success=False, summary=summary)
            return BridgeSessionResult(
                session_id=session_id,
                file_path=request.file_path,
                file_hash=digest,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                success=False,
                attempts=[],
                hardware_profile=hardware,
                summary=summary,
            )

        retry_guard = RetryGuard(
            max_attempts=settings.max_attempts,
            per_remediation_limit=settings.per_remediation_retry_limit,
            session_timeout_sec=settings.session_timeout_sec,
        )
        budget = AutoCompatibilityBudget.from_settings(settings)
        result: Optional[BridgeSessionResult] = None

        try:
            self._transition(lifecycle, SessionState.INSPECTING, reason="session_start")
            inspection = self._inspector.inspect(
                request.file_path,
                wine_prefix=request.wine_prefix,
            )
            outcomes.update_session_inspection(
                session_id, inspection.model_dump(mode="json")
            )
            self._transition(lifecycle, SessionState.PLANNING, reason="inspect_complete")

            result = self._run_session(
                request=request,
                session_id=session_id,
                lifecycle=lifecycle,
                retry_guard=retry_guard,
                budget=budget,
                hardware=hardware,
                started_at=started_at,
                digest=digest,
                inspection=inspection,
                cancel_check=cancel_check,
            )
        except InvalidSessionTransition as exc:
            result = self._lifecycle_error_result(
                request=request,
                session_id=session_id,
                lifecycle=lifecycle,
                started_at=started_at,
                digest=digest,
                hardware=hardware,
                exc=exc,
            )
        except Exception as exc:  # noqa: BLE001
            result = self._internal_error_result(
                request=request,
                session_id=session_id,
                lifecycle=lifecycle,
                started_at=started_at,
                digest=digest,
                hardware=hardware,
                exc=exc,
            )
        finally:
            if result is not None:
                self._finalize_bridge_session(
                    lifecycle=lifecycle,
                    result=result,
                    budget=budget,
                )
            self._lease_manager.release(session_id)

        return result  # type: ignore[return-value]

    def _run_session(
        self,
        *,
        request: BridgeRequest,
        session_id: str,
        lifecycle: SessionLifecycleManager,
        retry_guard: RetryGuard,
        hardware: Dict[str, Any],
        started_at: datetime,
        digest: Optional[str],
        inspection: Any,
        cancel_check: Optional[callable],
        resume_after_escalation: bool = False,
        budget: Optional[AutoCompatibilityBudget] = None,
    ) -> BridgeSessionResult:
        session_budget = budget or AutoCompatibilityBudget.from_settings(settings)
        if exhausted := session_budget.check():
            return self._budget_exhausted_result(
                request=request,
                session_id=session_id,
                lifecycle=lifecycle,
                started_at=started_at,
                digest=digest,
                hardware=hardware,
                attempts=[],
                budget=session_budget,
                detail=exhausted,
            )
        if self._check_cancelled(lifecycle, retry_guard, cancel_check):
            return self._cancelled_result(
                request, session_id, started_at, digest, hardware, []
            )
        if retry_guard.session_timed_out():
            return self._timeout_result(
                request, session_id, started_at, digest, hardware, []
            )

        if not resume_after_escalation:
            _report_progress(session_id, "Bridge adaptive run started…")
        kind = classify_program_kind(
            request.file_path,
            host_arch=hardware.get("architecture", "x86_64"),
        )
        installer = kind["is_installer"]
        electron = kind["is_electron"]
        wine_gui = bool(kind.get("is_wine_gui"))
        if kind.get("needs_gui") and (request.sandbox or request.use_sudo):
            request.sandbox = False
            request.use_sudo = False
        max_attempts = request.max_attempts or (
            18 if installer else settings.max_attempts
        )
        retry_guard.max_attempts = max_attempts
        execution_timeout = 300 if installer else settings.execution_timeout_sec

        # For an installed Electron launcher, proactively install the Wine
        # workarounds Alma learned: elevate.exe passthrough + sidecar guard
        # wrapper. (--disable-gpu is applied via electron_software_gl_args below.)
        electron_prep: Optional[Dict[str, Any]] = None
        if electron and not installer:
            electron_prep = prepare_electron_wine(request.file_path)

        wine_prefix = request.wine_prefix or find_best_prefix(request.file_path)
        if not wine_prefix:
            wine_prefix = fresh_prefix_path(session_id)

        if kind.get("needs_wine") and wine_prefix:
            win_ok, win_msg = require_wine_windows_version(wine_prefix)
            if not win_ok:
                _report_progress(session_id, f"Wine Windows version not set: {win_msg}")
            _ensure_prefix_runtimes(session_id, wine_prefix, request.file_path, kind)

        if installer and request.launch_after_install:
            cached = load_prefix_profile(wine_prefix)
            existing_launcher: Optional[str] = None
            if profile_allows_fast_launch(cached, wine_prefix):
                existing_launcher = cached.launcher_path if cached else None
                _report_progress(
                    session_id,
                    "Fast-path: prefix profile cache hit — launching installed Ascension…",
                )
            else:
                existing_launcher = launcher_ready_for_handoff(wine_prefix, request.file_path)
                if existing_launcher:
                    _report_progress(
                        session_id,
                        "Fast-path: installed launcher ready — skipping installer…",
                    )
                elif (
                    discover_installed_launcher(wine_prefix, request.file_path)
                    and launcher_verified_in_prefix(
                        wine_prefix,
                        discover_installed_launcher(wine_prefix, request.file_path) or "",
                    )
                    and prefix_runtimes_ready(wine_prefix)
                ):
                    existing_launcher = discover_installed_launcher(wine_prefix, request.file_path)

            if existing_launcher:
                try:
                    self._transition(
                        lifecycle,
                        SessionState.POLICY_CHECK,
                        reason="fast_path_launcher",
                    )
                except InvalidSessionTransition:
                    pass
                return self._run_launcher_handoff(
                    request=request,
                    session_id=session_id,
                    lifecycle=lifecycle,
                    launcher_path=existing_launcher,
                    wine_prefix=wine_prefix,
                    hardware=hardware,
                    started_at=started_at,
                    digest=digest,
                    prior_attempts=[],
                    skipped_installer=True,
                    install_summary="Installed launcher ready — skipped re-running the installer.",
                )
            discovered = discover_installed_launcher(wine_prefix, request.file_path)
            if discovered and not prefix_runtimes_ready(wine_prefix):
                _report_progress(
                    session_id,
                    "Launcher found but .NET/VC++ runtimes are missing in the prefix — "
                    "bootstrapping before install/launch…",
                )
                _ensure_prefix_runtimes(session_id, wine_prefix, request.file_path, kind)

        self._create_shadow_prediction_before_plan(
            session_id=session_id,
            correlation_id=lifecycle.correlation_id,
            file_path=request.file_path,
            executable_hash=digest or "",
            hardware=hardware,
            wine_prefix=wine_prefix,
            runtime_hint=request.runtime_hint,
            preferred_strategy_id=(
                request.preferred_strategy_id
                or getattr(inspection, "recommended_strategy_id", None)
            ),
        )
        execution_plan = self._planner.plan(
            request.file_path,
            runtime_hint=request.runtime_hint,
            preferred_strategy_id=(
                request.preferred_strategy_id
                or getattr(inspection, "recommended_strategy_id", None)
            ),
            wine_prefix=wine_prefix,
            proton_path=request.proton_path,
            base_env=request.env,
        )
        if not resume_after_escalation:
            self._transition(lifecycle, SessionState.POLICY_CHECK, reason="plan_ready")
        plans = [plan_step_to_dict(step) for step in execution_plan.steps]

        signature_fixes_applied: set[str] = set()
        early_compat_attempted = False

        if not plans:
            summary = "No compatible execution strategies available for this binary and host."
            outcomes.finalize_session(session_id, success=False, summary=summary)
            return BridgeSessionResult(
                session_id=session_id,
                file_path=request.file_path,
                file_hash=digest,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                success=False,
                attempts=[],
                hardware_profile=hardware,
                summary=summary,
            )

        attempt_records: List[AttemptRecord] = []
        attempt_number = 0
        last_signature: Optional[str] = None
        last_recommended: List[str] = []

        sudo_ready, sudo_error = prepare_sudo(
            requested=request.use_sudo,
            password=request.sudo_password,
        )
        if request.use_sudo and not sudo_ready:
            summary = f"Sudo required but not available: {sudo_error}"
            outcomes.finalize_session(session_id, success=False, summary=summary)
            return BridgeSessionResult(
                session_id=session_id,
                file_path=request.file_path,
                file_hash=digest,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                success=False,
                attempts=[],
                hardware_profile=hardware,
                summary=summary,
                recommended_actions=list(RECOMMENDED_ACTIONS["sudo_password_required"]),
            )

        use_sudo = resolve_use_sudo(request.use_sudo)
        sudo_disabled = False
        container_viable = request.sandbox and sandbox_ready(use_sudo=use_sudo)[0]

        remaining_plans = list(plans)
        rerank_count = 0
        rerank_events: List[RerankEvent] = []
        prefix_snapshots: Dict[str, PrefixSnapshot] = {}

        while remaining_plans and attempt_number < max_attempts:
            plan = remaining_plans.pop(0)
            if plan.get("mode") == "container" and not container_viable:
                continue

            plan_args = _plan_launch_args(plan)
            if installer and plan["runtime"] == "wine":
                plan_args = default_installer_args() + plan_args
            # Chromium CLI flags break some launcher wrappers (e.g. Ascension); remediations add them when needed.

            plan_signature: Optional[str] = None
            tried_remediation_ids: set[Optional[str]] = set()

            while attempt_number < max_attempts:
                self._prepare_retry_attempt(lifecycle, attempt_number)
                use_prior_remediation = (
                    plan_signature is None
                    and request.preferred_remediation_id
                    and request.preferred_strategy_id
                    and plan["strategy_id"] == request.preferred_strategy_id
                    and request.preferred_remediation_id not in tried_remediation_ids
                )
                remediation = _next_remediation(
                    plan_signature,
                    tried_remediation_ids,
                    allow_container=container_viable,
                    installer=installer,
                    electron=electron,
                    preferred_remediation_id=(
                        request.preferred_remediation_id if use_prior_remediation else None
                    ),
                )
                if remediation is None:
                    break

                tried_remediation_ids.add(remediation.get("id"))
                attempt_number += 1
                if exhausted := session_budget.record_execution_attempt():
                    return self._budget_exhausted_result(
                        request=request,
                        session_id=session_id,
                        lifecycle=lifecycle,
                        started_at=started_at,
                        digest=digest,
                        hardware=hardware,
                        attempts=attempt_records,
                        budget=session_budget,
                        detail=exhausted,
                    )
                if remediation.get("id"):
                    if exhausted := session_budget.record_remediation():
                        return self._budget_exhausted_result(
                            request=request,
                            session_id=session_id,
                            lifecycle=lifecycle,
                            started_at=started_at,
                            digest=digest,
                            hardware=hardware,
                            attempts=attempt_records,
                            budget=session_budget,
                            detail=exhausted,
                        )
                env, launch_args = apply_remediation(plan["env"], remediation, plan_args)
                shim_prep = apply_electron_remediation_shims(
                    remediation,
                    env,
                    app_file=request.file_path,
                )
                if shim_prep:
                    electron_prep = shim_prep

                if plan["runtime"] == "proton" and plan.get("command"):
                    env.update(build_proton_env(plan["command"][0], session_id))
                elif plan["runtime"] == "wine":
                    env.setdefault("WINEPREFIX", wine_prefix or fresh_prefix_path(session_id))
                    env.setdefault("WINEDEBUG", "-all")
                    if electron and not installer:
                        env.update(electron_launch_env())

                # Tell the sidecar guard wrapper what the launcher is named so its
                # decoy passes the guard's process-name check.
                if electron and plan["runtime"] in {"wine", "proton"} and electron_prep:
                    name = electron_prep.get("launcher_exe_name")
                    if name:
                        env.setdefault("ALMA_LAUNCHER_EXE_NAME", str(name))

                if env.pop("ALMA_FRESH_PREFIX", None):
                    env["WINEPREFIX"] = fresh_prefix_path(f"{session_id}-{attempt_number}")

                if attempt_number <= 2:
                    for shim in shims_for_indicators(
                        hardware.get("legacy_indicators", []),
                        last_signature,
                    ):
                        env.update(shim.get("env", {}))

                mode = ExecutionMode.HOST
                if container_viable and plan["mode"] == "container":
                    mode = ExecutionMode.CONTAINER
                if (
                    remediation.get("force_mode") == "container"
                    and container_viable
                ):
                    mode = ExecutionMode.CONTAINER

                electron_args = env.pop("ALMA_ELECTRON_ARGS", None)
                if electron_args and plan["runtime"] in {"wine", "proton"}:
                    for arg in electron_args.split():
                        if arg not in launch_args:
                            launch_args.append(arg)
                if electron and not installer:
                    apply_electron_launch_overrides(env, launch_args)

                winetricks_hint = _winetricks_packages_for_attempt(remediation, env)
                if winetricks_hint and plan["runtime"] in {"wine", "proton"}:
                    prefix = env.get("WINEPREFIX", wine_prefix or "")
                    packages = [p.strip() for p in winetricks_hint.split(",") if p.strip()]
                    run_winetricks(prefix, packages)

                wine_version_hint = env.pop("ALMA_WINE_WINDOWS_VERSION", None)
                if wine_version_hint and plan["runtime"] in {"wine", "proton"}:
                    prefix = env.get("WINEPREFIX", wine_prefix or "")
                    set_wine_windows_version(prefix, wine_version_hint)
                elif (
                    installer
                    and attempt_number == 1
                    and plan["runtime"] == "wine"
                ):
                    prefix = env.get("WINEPREFIX", wine_prefix or "")
                    ensure_wine_windows_version(prefix)

                active_prefix = env.get("WINEPREFIX", wine_prefix or "")
                if (
                    installer
                    and plan["runtime"] == "wine"
                    and active_prefix
                    and active_prefix not in prefix_snapshots
                ):
                    prefix_snapshots[active_prefix] = snapshot_wine_prefix(active_prefix)

                gui_launcher = (
                    electron
                    and not installer
                    and plan["runtime"] in {"wine", "proton"}
                )
                wine_gui_launch = (
                    wine_gui
                    and not installer
                    and plan["runtime"] in {"wine", "proton"}
                )
                attempt_timeout = (
                    settings.launcher_bootstrap_timeout_sec
                    if gui_launcher
                    else (
                        settings.wine_gui_bootstrap_timeout_sec
                        if wine_gui_launch
                        else execution_timeout
                    )
                )
                try:
                    self._transition(
                        lifecycle,
                        SessionState.EXECUTING,
                        reason="attempt_execute",
                        attempt_number=attempt_number,
                    )
                except InvalidSessionTransition:
                    pass

                baseline_pids: List[int] = []
                if gui_launcher or wine_gui_launch:
                    prefix = env.get("WINEPREFIX", wine_prefix or "")
                    baseline_pids = list(snapshot_wine_pids(prefix)) if prefix else []
                detach_gui = gui_launcher or wine_gui_launch
                result = execute_attempt(
                    command=plan["command"],
                    env=env,
                    file_path=request.file_path,
                    mode=mode,
                    extra_args=launch_args,
                    use_sudo=use_sudo and not sudo_disabled,
                    timeout_sec=attempt_timeout,
                    detach_gui=detach_gui,
                    detach_after_sec=(
                        settings.launcher_detach_after_sec
                        if gui_launcher
                        else min(settings.launcher_detach_after_sec, 20)
                    ),
                )

                signature = result.get("error_signature")
                recommended = list(result.get("likely_causes") or [])

                # Electron auto-updater stalled on Wine's flaky winsock: the log
                # reaches "Checking for update" but never "up to date" / elevated.
                if electron and not result["success"]:
                    combined = (
                        str(result.get("stdout", "")) + "\n" + str(result.get("stderr", ""))
                    ).lower()
                    if (
                        "checking for update" in combined
                        and "up to date" not in combined
                        and "launching elevated" not in combined
                    ):
                        signature = "winsock_update_hang"
                        recommended = list(RECOMMENDED_ACTIONS["winsock_update_hang"])

                if signature == "sudo_password_required":
                    sudo_disabled = True
                    use_sudo = False
                    recommended = list(RECOMMENDED_ACTIONS["sudo_password_required"])

                raw_stderr = str(result.get("stderr", ""))[:8000]
                display_stderr = raw_stderr
                if plan["runtime"] == "wine" and bool(result["success"]):
                    display_stderr = format_wine_log_for_display(raw_stderr, success=True)

                phase = (
                    "install"
                    if installer
                    else (
                        "launcher"
                        if gui_launcher
                        else ("wine_gui" if wine_gui_launch else "native")
                    )
                )
                evidence = ExecutionEvidence(
                    session_id=session_id,
                    attempt_number=attempt_number,
                    phase=phase,
                    result=dict(result),
                    file_path=request.file_path,
                    installer=installer,
                    electron=electron,
                    gui_launcher=gui_launcher,
                    wine_gui=wine_gui_launch,
                    wine_prefix=active_prefix or None,
                    launcher_path=request.file_path,
                    before_snapshot=prefix_snapshots.get(active_prefix),
                    baseline_pids=set(baseline_pids) if baseline_pids else None,
                )

                record = AttemptRecord(
                    attempt_number=attempt_number,
                    strategy_id=plan["strategy_id"],
                    remediation_id=remediation.get("id"),
                    runtime=plan["runtime"],
                    command=plan["command"],
                    env=env,
                    mode=mode,
                    success=False,
                    exit_code=result.get("exit_code"),  # type: ignore[arg-type]
                    error_signature=signature,  # type: ignore[arg-type]
                    detected_error=result.get("detected_error"),  # type: ignore[arg-type]
                    suggested_fix=result.get("suggested_fix"),  # type: ignore[arg-type]
                    recommended_actions=recommended,
                    stdout=str(result.get("stdout", ""))[:8000],
                    stderr=display_stderr,
                    duration_ms=int(result.get("duration_ms", 0)),
                    phase=phase,
                )

                boundary = self._verification_gateway.run(
                    lifecycle=lifecycle,
                    evidence=evidence,
                    record=record,
                )
                verified, verification_dict = self._persist_verified_attempt(
                    session_id=session_id,
                    record=record,
                    boundary=boundary,
                    lifecycle=lifecycle,
                )
                if boundary.error_signature:
                    signature = boundary.error_signature
                if boundary.recommended_actions:
                    recommended = boundary.recommended_actions

                attempt_records.append(record)

                if not record.success:
                    session_budget.record_failure_signature(signature)
                    active_prefix = env.get("WINEPREFIX", wine_prefix or "")
                    _maybe_apply_immediate_wine_fix(
                        session_id,
                        record.error_signature,
                        active_prefix,
                        request.file_path,
                        signature_fixes_applied,
                        stderr=str(record.stderr or ""),
                    )
                    if (
                        record.error_signature in _AUTO_FIX_SIGNATURES
                        and not early_compat_attempted
                    ):
                        early_compat_attempted = True
                        auto_result = self._try_auto_compatibility(
                            request=request,
                            session_id=session_id,
                            lifecycle=lifecycle,
                            retry_guard=retry_guard,
                            attempt_records=attempt_records,
                            hardware=hardware,
                            started_at=started_at,
                            digest=digest,
                            last_recommended=last_recommended,
                            rerank_events=rerank_events,
                            last_signature=record.error_signature,
                            wine_prefix=wine_prefix,
                            inspection=inspection,
                            budget=session_budget,
                        )
                        if auto_result is not None:
                            return auto_result

                if record.success:
                    summary = (
                        f"Succeeded on attempt {record.attempt_number} "
                        f"using {record.strategy_id}"
                        + (f" with remediation {record.remediation_id}" if record.remediation_id else "")
                        + "."
                    )
                    if installer and plan["runtime"] == "wine":
                        summary += (
                            " Wine may log OLE/COM warnings during GUI installers; "
                            "those are expected and do not mean the install failed."
                        )
                    verify_evidence = verification_dict.get("evidence") or []
                    if verify_evidence:
                        summary += f" Verified: {verify_evidence[0]}."
                    summary += _electron_prep_note(electron_prep)
                    if installer and request.launch_after_install and plan["runtime"] == "wine":
                        launcher_path = discover_installed_launcher(
                            env.get("WINEPREFIX", wine_prefix or ""),
                            request.file_path,
                        )
                        if launcher_path:
                            try:
                                self._transition(
                                    lifecycle,
                                    SessionState.POLICY_CHECK,
                                    reason="install_verified_launch_pending",
                                )
                            except InvalidSessionTransition:
                                pass
                            return self._run_launcher_handoff(
                                request=request,
                                session_id=session_id,
                                lifecycle=lifecycle,
                                launcher_path=launcher_path,
                                wine_prefix=env.get("WINEPREFIX", wine_prefix or ""),
                                hardware=hardware,
                                started_at=started_at,
                                digest=digest,
                                prior_attempts=attempt_records,
                                skipped_installer=False,
                                install_summary=summary,
                                budget=session_budget,
                            )
                    candidate_id = self._persist_profile_candidate_before_success(
                        session_id=session_id,
                        file_path=request.file_path,
                        executable_hash=digest or "",
                        hardware=hardware,
                        record=record,
                        verification_dict=verification_dict,
                        attempt_records=attempt_records,
                    )
                    declare_verified_session_success(
                        lifecycle=lifecycle,
                        session_id=session_id,
                        transition=self._transition,
                        summary=summary,
                        rerank_events=[event.model_dump() for event in rerank_events],
                    )
                    self._promote_profile_candidate_after_success(candidate_id)
                    return BridgeSessionResult(
                        session_id=session_id,
                        file_path=request.file_path,
                        file_hash=digest,
                        started_at=started_at,
                        finished_at=datetime.now(timezone.utc),
                        success=True,
                        winning_attempt=record,
                        attempts=attempt_records,
                        hardware_profile=hardware,
                        summary=summary,
                        rerank_events=rerank_events,
                    )

                plan_signature = record.error_signature
                last_signature = plan_signature
                last_recommended = recommended or last_recommended

            if remaining_plans and last_signature:
                previous_order = [item["strategy_id"] for item in remaining_plans]
                remaining_plans = rerank_plans(
                    remaining_plans,
                    file_path=request.file_path,
                    hardware_profile=hardware,
                    error_signature=last_signature,
                )
                rerank_events.append(
                    _build_rerank_event(
                        sequence=len(rerank_events) + 1,
                        after_strategy_id=plan["strategy_id"],
                        error_signature=last_signature,
                        previous_order=previous_order,
                        remaining_plans=remaining_plans,
                    )
                )
                rerank_count += 1

        auto_result = self._try_auto_compatibility(
            request=request,
            session_id=session_id,
            lifecycle=lifecycle,
            retry_guard=retry_guard,
            attempt_records=attempt_records,
            hardware=hardware,
            started_at=started_at,
            digest=digest,
            last_recommended=last_recommended,
            rerank_events=rerank_events,
            last_signature=last_signature,
            wine_prefix=wine_prefix,
            inspection=inspection,
            budget=session_budget,
        )
        if auto_result is not None:
            return auto_result

        strategies_tried = len({record.strategy_id for record in attempt_records})
        summary = _failure_summary(
            attempt_number,
            strategies_tried or len(plans),
            last_signature,
            last_recommended,
            installer=installer,
            sudo_requested=request.use_sudo,
            passwordless_sudo=passwordless_sudo_works(),
            rerank_count=rerank_count,
        )
        summary += _electron_prep_note(electron_prep)
        outcomes.finalize_session(
            session_id,
            success=False,
            summary=summary,
            rerank_events=[event.model_dump() for event in rerank_events],
        )
        return BridgeSessionResult(
            session_id=session_id,
            file_path=request.file_path,
            file_hash=digest,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            success=False,
            winning_attempt=None,
            attempts=attempt_records,
            hardware_profile=hardware,
            summary=summary,
            recommended_actions=last_recommended,
            rerank_events=rerank_events,
        )

    def _try_auto_compatibility(
        self,
        *,
        request: BridgeRequest,
        session_id: str,
        lifecycle: Optional[SessionLifecycleManager] = None,
        retry_guard: Optional[RetryGuard] = None,
        attempt_records: List[AttemptRecord],
        hardware: Dict[str, Any],
        started_at: datetime,
        digest: Optional[str],
        last_recommended: List[str],
        rerank_events: List[RerankEvent],
        target_path: Optional[str] = None,
        installed_launcher_path: Optional[str] = None,
        skipped_installer: bool = False,
        install_summary: str = "",
        last_signature: Optional[str] = None,
        wine_prefix: Optional[str] = None,
        inspection: Any = None,
        budget: Optional[AutoCompatibilityBudget] = None,
    ) -> Optional[BridgeSessionResult]:
        """In-session escalation via route services — no orphan child sessions.

        Canonical multi-route lifecycle for bridge-retry routes:
          initial exhaustion: CLASSIFYING → ESCALATING
          per route (first):  ESCALATING → POLICY_CHECK → EXECUTING
          after failed retry: CLASSIFYING → RETRYING → POLICY_CHECK → EXECUTING
        """
        session_budget = budget or AutoCompatibilityBudget.from_settings(settings)
        if exhausted := session_budget.check():
            return self._budget_exhausted_result(
                request=request,
                session_id=session_id,
                lifecycle=lifecycle,
                started_at=started_at,
                digest=digest,
                hardware=hardware,
                attempts=attempt_records,
                budget=session_budget,
                detail=exhausted,
            )
        if request.auto_remediate is not None:
            enabled = request.auto_remediate
        else:
            enabled = settings.bridge_auto_remediate
        if not enabled:
            return None
        if retry_guard and not retry_guard.escalation_allowed(last_signature):
            return None

        target = target_path or request.file_path
        err = _failure_error_text(attempt_records)
        _report_progress(
            session_id,
            "Initial attempts exhausted — applying compatibility fixes "
            "(winetricks, pathways, best routes)…",
        )

        if lifecycle:
            if lifecycle.state == SessionState.CLASSIFYING:
                self._transition(lifecycle, SessionState.ESCALATING, reason="retry_exhausted")
            elif lifecycle.state != SessionState.ESCALATING:
                self._prepare_route_policy_check(
                    lifecycle,
                    attempt_number=len(attempt_records) + 1,
                )

        discovery = self._route_discovery.discover(err, file_path=target)
        routes = self._route_selection.select(
            discovery,
            budget=int(settings.operator_max_route_attempts),
        )
        exhausted_ids = [
            str(record.remediation_id)
            for record in attempt_records
            if record.remediation_id
        ]
        escalation_meta = {
            "triggering_signature": last_signature,
            "exhausted_remediation_ids": exhausted_ids,
            "routes_considered": [route.get("id") for route in routes],
            "auto_compat_budget": session_budget.to_dict(),
        }
        outcomes.update_session_escalation(session_id, escalation_meta)

        ctx = RouteExecutionContext(
            session_id=session_id,
            correlation_id=session_id,
            file_path=target,
            wine_prefix=wine_prefix or find_best_prefix(target),
            error_text=err,
            bridge_signature=discovery.get("bridge_signature"),
            preferred_remediation_id=discovery.get("preferred_remediation_id"),
            sudo_password=request.sudo_password,
            auto_remediate=enabled,
        )
        allow_host = bool(settings.operator_allow_mutations)

        winning_route: Optional[str] = None
        bridge_retry_request = request
        route_attempt_number = len(attempt_records)

        for route in routes:
            if exhausted := session_budget.record_route():
                return self._budget_exhausted_result(
                    request=request,
                    session_id=session_id,
                    lifecycle=lifecycle,
                    started_at=started_at,
                    digest=digest,
                    hardware=hardware,
                    attempts=attempt_records,
                    budget=session_budget,
                    detail=exhausted,
                )
            intent = build_route_intent(
                route=route,
                session_id=session_id,
                correlation_id=session_id,
                auto_remediate=enabled,
            )
            decision = evaluate_or_block(intent, self._policy)
            if not decision.allowed:
                if lifecycle:
                    try:
                        self._transition(
                            lifecycle,
                            SessionState.AWAITING_APPROVAL,
                            reason=decision.reason,
                            metadata={"route_id": route.get("id")},
                        )
                    except InvalidSessionTransition:
                        pass
                continue

            if lifecycle:
                route_attempt_number += 1
                self._prepare_route_policy_check(lifecycle, attempt_number=route_attempt_number)

            result = self._route_executor.execute_route(
                route,
                discovery,
                ctx,
                apply=True,
                allow_host_mutations=allow_host,
            )
            if result.requires_bridge_retry:
                winning_route = result.route_id
                if result.preferred_strategy_id:
                    bridge_retry_request = request.model_copy(
                        update={
                            "preferred_strategy_id": result.preferred_strategy_id,
                            "preferred_remediation_id": result.preferred_remediation_id,
                            "file_path": target,
                        }
                    )
                if exhausted := session_budget.record_bridge_retry():
                    return self._budget_exhausted_result(
                        request=request,
                        session_id=session_id,
                        lifecycle=lifecycle,
                        started_at=started_at,
                        digest=digest,
                        hardware=hardware,
                        attempts=attempt_records,
                        budget=session_budget,
                        detail=exhausted,
                    )
                if lifecycle:
                    self._transition(
                        lifecycle,
                        SessionState.EXECUTING,
                        reason="route_bridge_retry",
                        attempt_number=route_attempt_number,
                    )
                retry_result = self._run_session(
                    request=bridge_retry_request,
                    session_id=session_id,
                    lifecycle=lifecycle or SessionLifecycleManager(session_id),
                    retry_guard=retry_guard or RetryGuard(max_attempts=settings.max_attempts),
                    budget=session_budget,
                    hardware=hardware,
                    started_at=started_at,
                    digest=digest,
                    inspection=inspection or self._inspector.inspect(target, wine_prefix=wine_prefix),
                    cancel_check=None,
                    resume_after_escalation=True,
                )
                if not retry_result.success and lifecycle:
                    self._normalize_post_bridge_retry_lifecycle(lifecycle)
                if retry_result.success:
                    summary = (
                        f"Auto-compatibility succeeded via {winning_route or result.route_id}: "
                        f"{retry_result.summary}"
                    )
                    if install_summary:
                        summary = f"{install_summary.strip()} {summary}"
                    return BridgeSessionResult(
                        session_id=session_id,
                        file_path=request.file_path,
                        file_hash=digest,
                        started_at=started_at,
                        finished_at=datetime.now(timezone.utc),
                        success=True,
                        winning_attempt=retry_result.winning_attempt,
                        attempts=attempt_records + retry_result.attempts,
                        hardware_profile=hardware,
                        summary=summary,
                        recommended_actions=last_recommended,
                        rerank_events=rerank_events,
                        installed_launcher_path=installed_launcher_path
                        or retry_result.installed_launcher_path,
                        skipped_installer=skipped_installer,
                    )
                continue

        routes_tried = len(routes)
        if not winning_route:
            _report_progress(
                session_id,
                f"Compatibility pass finished — tried {routes_tried} route(s), still working on it.",
            )
            return None

        _report_progress(
            session_id,
            f"Host fixes applied via {winning_route} — retry may succeed now.",
        )
        return None

    def _run_launcher_handoff(
        self,
        *,
        request: BridgeRequest,
        session_id: str,
        lifecycle: SessionLifecycleManager,
        launcher_path: str,
        wine_prefix: str,
        hardware: Dict[str, Any],
        started_at: datetime,
        digest: Optional[str],
        prior_attempts: List[AttemptRecord],
        skipped_installer: bool,
        install_summary: str = "",
        budget: Optional[AutoCompatibilityBudget] = None,
    ) -> BridgeSessionResult:
        """Run the installed app launcher instead of (or after) the installer."""
        session_budget = budget or AutoCompatibilityBudget.from_settings(settings)
        win_ok, win_msg = require_wine_windows_version(wine_prefix)
        if not win_ok:
            _report_progress(session_id, f"Launcher blocked: Wine still reports XP — {win_msg}")
        _ensure_prefix_runtimes(
            session_id,
            wine_prefix,
            launcher_path,
            classify_program_kind(launcher_path, host_arch=hardware.get("architecture", "x86_64")),
        )
        electron_prep = prepare_electron_wine(launcher_path)
        self._create_shadow_prediction_before_plan(
            session_id=session_id,
            correlation_id=lifecycle.correlation_id,
            file_path=launcher_path,
            executable_hash=digest or file_hash(launcher_path),
            hardware=hardware,
            wine_prefix=wine_prefix,
            runtime_hint=request.runtime_hint,
            preferred_strategy_id=request.preferred_strategy_id,
        )
        plans = build_execution_plan(
            launcher_path,
            runtime_hint=request.runtime_hint,
            preferred_strategy_id=request.preferred_strategy_id,
            wine_prefix=wine_prefix,
            proton_path=request.proton_path,
            base_env=request.env,
        )
        if not plans:
            summary = (
                (install_summary + " ")
                if install_summary
                else ""
            ) + f"Found launcher at {launcher_path} but no execution strategy is available."
            outcomes.finalize_session(session_id, success=False, summary=summary)
            return BridgeSessionResult(
                session_id=session_id,
                file_path=request.file_path,
                file_hash=digest,
                started_at=started_at,
                finished_at=datetime.now(timezone.utc),
                success=False,
                attempts=prior_attempts,
                hardware_profile=hardware,
                summary=summary,
                installed_launcher_path=launcher_path,
                skipped_installer=skipped_installer,
            )

        attempt_records = list(prior_attempts)
        attempt_number = len(prior_attempts)
        max_launcher_attempts = min(10, request.max_attempts or 10)
        plan = plans[0]
        plan_args = _plan_launch_args(plan)
        tried_remediation_ids: set[Optional[str]] = set()
        applied_remediations: List[Dict[str, Any]] = []
        plan_signature: Optional[str] = None
        last_signature: Optional[str] = None
        last_recommended: List[str] = []
        signature_fixes_applied: set[str] = set()
        early_compat_attempted = False

        while attempt_number < max_launcher_attempts:
            self._prepare_retry_attempt(lifecycle, attempt_number)
            if plan_signature is None and attempt_number == len(prior_attempts):
                remediation = _baseline_launcher_remediation()
            else:
                remediation = next_launcher_remediation(
                    plan_signature,
                    tried_remediation_ids,
                )
            if remediation is None:
                break

            tried_remediation_ids.add(remediation.get("id"))
            applied_remediations.append(remediation)
            attempt_number += 1
            if exhausted := session_budget.record_execution_attempt():
                return self._budget_exhausted_result(
                    request=request,
                    session_id=session_id,
                    lifecycle=lifecycle,
                    started_at=started_at,
                    digest=digest,
                    hardware=hardware,
                    attempts=attempt_records,
                    budget=session_budget,
                    detail=exhausted,
                )
            if remediation.get("id"):
                if exhausted := session_budget.record_remediation():
                    return self._budget_exhausted_result(
                        request=request,
                        session_id=session_id,
                        lifecycle=lifecycle,
                        started_at=started_at,
                        digest=digest,
                        hardware=hardware,
                        attempts=attempt_records,
                        budget=session_budget,
                        detail=exhausted,
                    )
            remediation_label = remediation.get("id") or "baseline"
            _report_progress(
                session_id,
                f"Launcher attempt {attempt_number}/{max_launcher_attempts} "
                f"({remediation_label})…",
            )
            env, launch_args = dict(plan["env"]), list(plan_args)
            for step in applied_remediations:
                env, launch_args = apply_remediation(env, step, launch_args)
            shim_prep = apply_electron_remediation_shims(
                remediation,
                env,
                app_file=launcher_path,
            )
            electron_prep = shim_prep or prepare_electron_wine(launcher_path)
            env.update(electron_launch_env())
            env.setdefault("WINEPREFIX", wine_prefix)
            env.setdefault("WINEDEBUG", "-all")

            if electron_prep and electron_prep.get("launcher_exe_name"):
                env.setdefault(
                    "ALMA_LAUNCHER_EXE_NAME",
                    str(electron_prep["launcher_exe_name"]),
                )

            winetricks_hint = _winetricks_packages_for_attempt(remediation, env)
            if winetricks_hint:
                packages = [p.strip() for p in winetricks_hint.split(",") if p.strip()]
                _report_progress(
                    session_id,
                    f"Launcher attempt {attempt_number}: installing "
                    f"{', '.join(packages)} via winetricks — this can take several minutes…",
                )
                run_winetricks(wine_prefix, packages)
                _report_progress(
                    session_id,
                    f"Launcher attempt {attempt_number}: winetricks finished, launching…",
                )

            electron_args = env.pop("ALMA_ELECTRON_ARGS", None)
            if electron_args:
                for arg in electron_args.split():
                    if arg not in launch_args:
                        launch_args.append(arg)
            apply_electron_launch_overrides(env, launch_args)

            baseline_pids = snapshot_wine_pids(wine_prefix)
            win_ok, win_msg = require_wine_windows_version(wine_prefix)
            if not win_ok:
                _report_progress(
                    session_id,
                    f"Launcher attempt {attempt_number}: Wine version not confirmed ({win_msg}) — retrying set…",
                )
            try:
                self._transition(
                    lifecycle,
                    SessionState.EXECUTING,
                    reason="launcher_execute",
                    attempt_number=attempt_number,
                )
            except InvalidSessionTransition:
                pass
            result = execute_attempt(
                command=plan["command"],
                env=env,
                file_path=launcher_path,
                mode=ExecutionMode.HOST,
                extra_args=launch_args,
                use_sudo=False,
                timeout_sec=settings.launcher_bootstrap_timeout_sec,
                detach_gui=True,
                detach_after_sec=settings.launcher_detach_after_sec,
            )

            evidence = ExecutionEvidence(
                session_id=session_id,
                attempt_number=attempt_number,
                phase="launcher",
                result=dict(result),
                file_path=launcher_path,
                installer=False,
                electron=True,
                gui_launcher=True,
                wine_prefix=wine_prefix,
                launcher_path=launcher_path,
                baseline_pids=set(baseline_pids),
            )

            record = AttemptRecord(
                attempt_number=attempt_number,
                strategy_id=plan["strategy_id"],
                remediation_id=remediation.get("id"),
                runtime=plan["runtime"],
                command=plan["command"],
                env=env,
                mode=ExecutionMode.HOST,
                success=False,
                exit_code=result.get("exit_code"),  # type: ignore[arg-type]
                error_signature=result.get("error_signature"),  # type: ignore[arg-type]
                detected_error=result.get("detected_error"),  # type: ignore[arg-type]
                suggested_fix=result.get("suggested_fix"),  # type: ignore[arg-type]
                recommended_actions=list(result.get("likely_causes") or []),
                stdout=str(result.get("stdout", ""))[:8000],
                stderr=str(result.get("stderr", ""))[:8000],
                duration_ms=int(result.get("duration_ms", 0)),
                phase="launcher",
            )

            boundary = self._verification_gateway.run(
                lifecycle=lifecycle,
                evidence=evidence,
                record=record,
            )
            verified, verification_dict = self._persist_verified_attempt(
                session_id=session_id,
                record=record,
                boundary=boundary,
                lifecycle=lifecycle,
            )
            signature = boundary.error_signature or record.error_signature
            recommended = boundary.recommended_actions or record.recommended_actions

            attempt_records.append(record)

            if not record.success:
                program_identity = digest or file_hash(launcher_path)
                fp = remediation_fingerprint(
                    strategy_id=record.strategy_id,
                    remediation_id=record.remediation_id,
                    env=record.env,
                    launch_args=launch_args,
                    phase="launcher",
                )
                verify_conf = float(
                    (verification_dict.get("confidence") or 0.0)
                    if verification_dict
                    else 0.0
                )
                if exhausted := session_budget.record_no_progress_tuple(
                    program_identity=program_identity,
                    strategy_id=record.strategy_id,
                    remediation_ids=[r.get("id") for r in applied_remediations],
                    failure_signature=signature,
                    state_fingerprint=fp,
                    verification_confidence=verify_conf,
                ):
                    return self._budget_exhausted_result(
                        request=request,
                        session_id=session_id,
                        lifecycle=lifecycle,
                        started_at=started_at,
                        digest=digest,
                        hardware=hardware,
                        attempts=attempt_records,
                        budget=session_budget,
                        detail=exhausted,
                    )
                session_budget.record_failure_signature(signature)
                if record.error_signature in {"dotnet_missing", "wine_int3_crash"}:
                    invalidate_prefix_profile(wine_prefix)
                _maybe_apply_immediate_wine_fix(
                    session_id,
                    record.error_signature,
                    wine_prefix,
                    launcher_path,
                    signature_fixes_applied,
                    stderr=str(record.stderr or ""),
                )
                if (
                    record.error_signature in _AUTO_FIX_SIGNATURES
                    and not early_compat_attempted
                ):
                    early_compat_attempted = True
                    auto_result = self._try_auto_compatibility(
                        request=request,
                        session_id=session_id,
                        lifecycle=lifecycle,
                        retry_guard=RetryGuard(max_attempts=settings.max_attempts),
                        attempt_records=attempt_records,
                        hardware=hardware,
                        started_at=started_at,
                        digest=digest,
                        last_recommended=last_recommended,
                        rerank_events=[],
                        target_path=launcher_path,
                        installed_launcher_path=launcher_path,
                        skipped_installer=skipped_installer,
                        install_summary=install_summary,
                        last_signature=record.error_signature,
                        wine_prefix=wine_prefix,
                        budget=session_budget,
                    )
                    if auto_result is not None:
                        return auto_result

            if record.success:
                _persist_prefix_profile(wine_prefix, launcher_path)
                summary = install_summary or "Launcher handoff complete."
                if not summary.endswith("."):
                    summary += "."
                summary += f" Started {Path(launcher_path).name} on attempt {record.attempt_number}."
                if recommended:
                    summary += f" {recommended[0]}"
                verify_evidence = verification_dict.get("evidence") or []
                if verify_evidence:
                    summary += f" {verify_evidence[0]}"
                summary += _electron_prep_note(electron_prep)
                candidate_id = self._persist_profile_candidate_before_success(
                    session_id=session_id,
                    file_path=request.file_path,
                    executable_hash=digest or "",
                    hardware=hardware,
                    record=record,
                    verification_dict=verification_dict,
                    attempt_records=attempt_records,
                )
                declare_verified_session_success(
                    lifecycle=lifecycle,
                    session_id=session_id,
                    transition=self._transition,
                    summary=summary,
                )
                self._promote_profile_candidate_after_success(candidate_id)
                return BridgeSessionResult(
                    session_id=session_id,
                    file_path=request.file_path,
                    file_hash=digest,
                    started_at=started_at,
                    finished_at=datetime.now(timezone.utc),
                    success=True,
                    winning_attempt=record,
                    attempts=attempt_records,
                    hardware_profile=hardware,
                    summary=summary,
                    installed_launcher_path=launcher_path,
                    skipped_installer=skipped_installer,
                )

            plan_signature = record.error_signature
            last_signature = plan_signature
            last_recommended = recommended or last_recommended

        auto_result = self._try_auto_compatibility(
            request=request,
            session_id=session_id,
            lifecycle=lifecycle,
            retry_guard=RetryGuard(max_attempts=settings.max_attempts),
            attempt_records=attempt_records,
            hardware=hardware,
            started_at=started_at,
            digest=digest,
            last_recommended=last_recommended,
            rerank_events=[],
            target_path=launcher_path,
            installed_launcher_path=launcher_path,
            skipped_installer=skipped_installer,
            install_summary=install_summary,
            last_signature=last_signature,
            wine_prefix=wine_prefix,
            budget=session_budget,
        )
        if auto_result is not None:
            return auto_result

        summary_parts = []
        if install_summary:
            summary_parts.append(install_summary.strip())
        summary_parts.append(
            "Install completed but the launcher did not start successfully. "
            f"Last error: {last_signature or 'unknown'}. "
            f"Try running: {launcher_path}"
        )
        summary = " ".join(summary_parts)
        summary += _electron_prep_note(electron_prep)
        outcomes.finalize_session(session_id, success=False, summary=summary)
        return BridgeSessionResult(
            session_id=session_id,
            file_path=request.file_path,
            file_hash=digest,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            success=False,
            winning_attempt=None,
            attempts=attempt_records,
            hardware_profile=hardware,
            summary=summary,
            recommended_actions=last_recommended,
            installed_launcher_path=launcher_path,
            skipped_installer=skipped_installer,
        )


    def _normalize_post_bridge_retry_lifecycle(
        self,
        lifecycle: SessionLifecycleManager,
    ) -> None:
        """Return lifecycle to CLASSIFYING after a failed nested bridge retry."""
        state = lifecycle.state
        if state == SessionState.CLASSIFYING:
            return
        if state == SessionState.EXECUTING:
            self._transition(
                lifecycle,
                SessionState.OBSERVING,
                reason="route_bridge_retry_failed",
            )
            state = lifecycle.state
        if state == SessionState.OBSERVING:
            self._transition(
                lifecycle,
                SessionState.CLASSIFYING,
                reason="route_bridge_retry_failed",
            )
            return
        if state == SessionState.VERIFYING:
            self._transition(
                lifecycle,
                SessionState.CLASSIFYING,
                reason="route_bridge_retry_failed",
            )

    def _prepare_route_policy_check(
        self,
        lifecycle: SessionLifecycleManager,
        *,
        attempt_number: int,
    ) -> None:
        """Legal policy-check spine before route execution or bridge retry.

        Canonical paths:
          ESCALATING → POLICY_CHECK  (first route in escalation batch)
          CLASSIFYING → RETRYING → POLICY_CHECK  (after failed nested bridge retry)
        """
        state = lifecycle.state
        if state == SessionState.POLICY_CHECK:
            return
        if state == SessionState.ESCALATING:
            self._transition(
                lifecycle,
                SessionState.POLICY_CHECK,
                reason="route_approved",
                attempt_number=attempt_number,
            )
            return
        if state in {
            SessionState.CLASSIFYING,
            SessionState.VERIFYING,
            SessionState.OBSERVING,
        }:
            self._transition(
                lifecycle,
                SessionState.RETRYING,
                reason="route_bridge_retry_prepare",
                attempt_number=attempt_number,
            )
            self._transition(
                lifecycle,
                SessionState.POLICY_CHECK,
                reason="route_bridge_retry_prepare",
                attempt_number=attempt_number,
            )
            return
        if state == SessionState.REMEDIATING:
            self._transition(
                lifecycle,
                SessionState.POLICY_CHECK,
                reason="remediation_complete",
                attempt_number=attempt_number,
            )
            return
        if state == SessionState.AWAITING_APPROVAL:
            self._transition(
                lifecycle,
                SessionState.POLICY_CHECK,
                reason="route_retry_after_denial",
                attempt_number=attempt_number,
            )
            return
        raise InvalidSessionTransition(
            f"Cannot prepare route policy check from {state.value}"
        )

    def _prepare_retry_attempt(
        self,
        lifecycle: SessionLifecycleManager,
        attempt_number: int,
    ) -> None:
        """Return lifecycle to POLICY_CHECK before the next execution attempt."""
        state = lifecycle.state
        if state in {
            SessionState.CLASSIFYING,
            SessionState.VERIFYING,
            SessionState.OBSERVING,
            SessionState.REMEDIATING,
        }:
            try:
                if state == SessionState.REMEDIATING:
                    self._transition(
                        lifecycle,
                        SessionState.POLICY_CHECK,
                        reason="remediation_complete",
                        attempt_number=attempt_number,
                    )
                else:
                    self._transition(
                        lifecycle,
                        SessionState.RETRYING,
                        reason="prepare_retry",
                        attempt_number=attempt_number,
                    )
                    self._transition(
                        lifecycle,
                        SessionState.POLICY_CHECK,
                        reason="prepare_retry",
                        attempt_number=attempt_number,
                    )
            except InvalidSessionTransition:
                pass

    def _confirm_verified_attempt(
        self,
        session_id: str,
        record: AttemptRecord,
        boundary: VerificationBoundaryResult,
        *,
        lifecycle: Optional[SessionLifecycleManager] = None,
    ) -> tuple[bool, Dict[str, Any]]:
        """Authorize attempt success only when aggregate verification policy passes."""
        verification_dict = boundary.verification or {}
        if not boundary.policy_passed:
            record.success = False
            return False, verification_dict
        record.success = True
        return True, verification_dict

    def _safe_persist_verification(
        self,
        session_id: str,
        record: AttemptRecord,
        verification: Dict[str, Any],
    ) -> bool:
        try:
            _persist_attempt(session_id, record, verification=verification)
            return True
        except Exception:  # noqa: BLE001
            return False

    def _persist_verified_attempt(
        self,
        *,
        session_id: str,
        record: AttemptRecord,
        boundary: VerificationBoundaryResult,
        lifecycle: SessionLifecycleManager,
    ) -> tuple[bool, Dict[str, Any]]:
        verified, verification_dict = self._confirm_verified_attempt(
            session_id,
            record,
            boundary,
            lifecycle=lifecycle,
        )
        if boundary.error_signature:
            record.error_signature = boundary.error_signature  # type: ignore[assignment]
        if boundary.recommended_actions:
            record.recommended_actions = boundary.recommended_actions
        persist_ok = self._safe_persist_verification(session_id, record, verification_dict)
        if verified and not persist_ok:
            record.success = False
            verified = False
            try:
                self._transition(
                    lifecycle,
                    SessionState.CLASSIFYING,
                    reason="verification_persist_failed",
                    attempt_number=record.attempt_number,
                )
            except InvalidSessionTransition:
                pass
        elif not persist_ok:
            record.success = False
        return verified, verification_dict

    def _applied_remediation_ids(
        self,
        attempt_records: List[AttemptRecord],
    ) -> List[Optional[str]]:
        return [record.remediation_id for record in attempt_records]

    def _persist_profile_candidate_before_success(
        self,
        *,
        session_id: str,
        file_path: str,
        executable_hash: str,
        hardware: Dict[str, Any],
        record: AttemptRecord,
        verification_dict: Dict[str, Any],
        attempt_records: List[AttemptRecord],
    ) -> Optional[str]:
        return ProfileCandidateService.persist_from_verified(
            VerifiedAttemptInputs(
                session_id=session_id,
                file_path=file_path,
                executable_hash=executable_hash or "",
                hardware=hardware,
                record=record,
                verification_payload=verification_dict,
                applied_remediation_ids=self._applied_remediation_ids(attempt_records),
            )
        )

    def _promote_profile_candidate_after_success(
        self,
        candidate_id: Optional[str],
    ) -> None:
        if candidate_id:
            ProfileCreationService.promote(candidate_id)

    def _create_shadow_prediction_before_plan(
        self,
        *,
        session_id: str,
        correlation_id: str,
        file_path: str,
        executable_hash: str,
        hardware: Dict[str, Any],
        wine_prefix: Optional[str],
        runtime_hint: Optional[Any] = None,
        preferred_strategy_id: Optional[str] = None,
    ) -> None:
        try:
            ProfileShadowService.create_prediction(
                ShadowPlanningInputs(
                    session_id=session_id,
                    correlation_id=correlation_id,
                    file_path=file_path,
                    executable_hash=executable_hash,
                    hardware=hardware,
                    wine_prefix=wine_prefix,
                    runtime_hint=str(runtime_hint) if runtime_hint else None,
                    preferred_strategy_id=preferred_strategy_id,
                    feature_flags={
                        "compatibility_profiles_enabled": settings.compatibility_profiles_enabled,
                        "compatibility_profile_shadow_mode": settings.compatibility_profile_shadow_mode,
                        "compatibility_profile_creation_enabled": settings.compatibility_profile_creation_enabled,
                        "compatibility_profile_reuse_enabled": settings.compatibility_profile_reuse_enabled,
                    },
                )
            )
        except Exception:  # noqa: BLE001
            pass

    def _record_shadow_actual_outcome(
        self,
        *,
        lifecycle: SessionLifecycleManager,
        result: BridgeSessionResult,
        budget: Optional[AutoCompatibilityBudget] = None,
    ) -> None:
        winning = result.winning_attempt
        candidate_id: Optional[str] = None
        actual_family: Optional[str] = None
        actual_manifest: Optional[str] = None
        actual_remediation: Optional[List[Dict[str, str]]] = None
        verification_ref: Optional[str] = None
        policy_id: Optional[str] = None
        policy_version: Optional[str] = None

        if winning:
            from alma_bridge.compatibility.profile_store import load_candidate_for_session_attempt

            snap = load_candidate_for_session_attempt(
                result.session_id,
                winning.attempt_number,
            )
            if snap:
                candidate_id = snap.candidate_id
                actual_family = snap.bridge_family_key
                actual_manifest = snap.bridge_manifest_hash
                actual_remediation = list(snap.remediation_protocol)
                policy = snap.verification_binding_payload
                policy_id = str(policy.get("policy_id") or "")
                policy_version = str(policy.get("policy_version") or "")
                verification_ref = snap.verification_binding_key

        failure_signature = None
        if not result.success and result.attempts:
            for attempt in reversed(result.attempts):
                if attempt.error_signature:
                    failure_signature = attempt.error_signature
                    break
        if budget and budget.exhausted:
            failure_signature = failure_signature or AUTO_COMPATIBILITY_BUDGET_EXHAUSTED

        escalation_indicators: List[str] = []
        if budget and budget.exhausted:
            escalation_indicators.append(budget.exhaustion_dimension or "budget_exhausted")

        try:
            ProfileShadowService.record_actual_outcome(
                ShadowActualInputs(
                    session_id=result.session_id,
                    correlation_id=lifecycle.correlation_id,
                    terminal_session_state=str(lifecycle.state.value),
                    success=result.success,
                    winning_attempt_number=winning.attempt_number if winning else None,
                    actual_strategy_id=winning.strategy_id if winning else None,
                    actual_bridge_family_key=actual_family,
                    actual_bridge_manifest_hash=actual_manifest,
                    actual_remediation_protocol=actual_remediation,
                    verification_result_ref=verification_ref,
                    verification_policy_id=policy_id,
                    verification_policy_version=policy_version,
                    failure_signature=failure_signature,
                    fallback_indicators=["skipped_installer"] if result.skipped_installer else [],
                    escalation_indicators=escalation_indicators,
                    profile_candidate_id=candidate_id,
                )
            )
        except Exception:  # noqa: BLE001
            pass

    def _finalize_bridge_session(
        self,
        *,
        lifecycle: SessionLifecycleManager,
        result: BridgeSessionResult,
        budget: AutoCompatibilityBudget,
    ) -> None:
        """Single terminal observation boundary for every finalized Bridge session."""
        if not result.finished_at:
            result.finished_at = datetime.now(timezone.utc)
        if budget.exhausted:
            outcomes.update_session_escalation(
                lifecycle.session_id,
                {"auto_compat_budget": budget.to_dict()},
            )
        self._ensure_terminal_lifecycle_state(lifecycle=lifecycle, result=result, budget=budget)
        self._record_shadow_actual_outcome(lifecycle=lifecycle, result=result, budget=budget)

    def _ensure_terminal_lifecycle_state(
        self,
        *,
        lifecycle: SessionLifecycleManager,
        result: BridgeSessionResult,
        budget: AutoCompatibilityBudget,
    ) -> None:
        if lifecycle.state in {
            SessionState.SUCCEEDED,
            SessionState.FAILED,
            SessionState.CANCELLED,
        }:
            return
        try:
            if result.success:
                return
            if budget.exhausted:
                self._transition(
                    lifecycle,
                    SessionState.FAILED,
                    reason=AUTO_COMPATIBILITY_BUDGET_EXHAUSTED,
                )
                return
            if "lifecycle error" in (result.summary or "").lower():
                self._transition(lifecycle, SessionState.FAILED, reason="lifecycle_exception")
                return
            self._transition(lifecycle, SessionState.FAILED, reason="session_terminal_failure")
        except InvalidSessionTransition:
            pass

    def _lifecycle_error_result(
        self,
        *,
        request: BridgeRequest,
        session_id: str,
        lifecycle: SessionLifecycleManager,
        started_at: datetime,
        digest: Optional[str],
        hardware: Dict[str, Any],
        exc: InvalidSessionTransition,
    ) -> BridgeSessionResult:
        summary = f"Session lifecycle error: {exc}"
        attempts = self._load_attempt_records(session_id)
        outcomes.finalize_session(session_id, success=False, summary=summary)
        return BridgeSessionResult(
            session_id=session_id,
            file_path=request.file_path,
            file_hash=digest,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            success=False,
            attempts=attempts,
            hardware_profile=hardware,
            summary=summary,
        )

    def _internal_error_result(
        self,
        *,
        request: BridgeRequest,
        session_id: str,
        lifecycle: SessionLifecycleManager,
        started_at: datetime,
        digest: Optional[str],
        hardware: Dict[str, Any],
        exc: Exception,
    ) -> BridgeSessionResult:
        summary = f"Bridge session internal error: {exc}"
        attempts = self._load_attempt_records(session_id)
        outcomes.finalize_session(session_id, success=False, summary=summary)
        return BridgeSessionResult(
            session_id=session_id,
            file_path=request.file_path,
            file_hash=digest,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            success=False,
            attempts=attempts,
            hardware_profile=hardware,
            summary=summary,
        )

    def _budget_exhausted_result(
        self,
        *,
        request: BridgeRequest,
        session_id: str,
        lifecycle: Optional[SessionLifecycleManager],
        started_at: datetime,
        digest: Optional[str],
        hardware: Dict[str, Any],
        attempts: List[AttemptRecord],
        budget: AutoCompatibilityBudget,
        detail: str,
    ) -> BridgeSessionResult:
        summary = (
            f"Auto-compatibility budget exhausted ({budget.exhaustion_dimension}): {detail}. "
            f"Counters: {budget.to_dict()}"
        )
        if lifecycle:
            try:
                if lifecycle.state in {
                    SessionState.CLASSIFYING,
                    SessionState.VERIFYING,
                    SessionState.OBSERVING,
                }:
                    self._transition(lifecycle, SessionState.FAILED, reason=detail)
                elif lifecycle.state not in {
                    SessionState.SUCCEEDED,
                    SessionState.FAILED,
                    SessionState.CANCELLED,
                }:
                    self._transition(lifecycle, SessionState.FAILED, reason=detail)
            except InvalidSessionTransition:
                pass
        outcomes.update_session_escalation(
            session_id,
            {"auto_compat_budget": budget.to_dict()},
        )
        outcomes.finalize_session(session_id, success=False, summary=summary)
        return BridgeSessionResult(
            session_id=session_id,
            file_path=request.file_path,
            file_hash=digest,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            success=False,
            winning_attempt=None,
            attempts=attempts,
            hardware_profile=hardware,
            summary=summary,
        )

    def _load_attempt_records(self, session_id: str) -> List[AttemptRecord]:
        session = outcomes.get_session(session_id)
        if not session:
            return []
        raw = session.get("attempts") or []
        records: List[AttemptRecord] = []
        for item in raw:
            try:
                records.append(AttemptRecord.model_validate(item))
            except Exception:  # noqa: BLE001
                continue
        return records

    def _transition(
        self,
        lifecycle: SessionLifecycleManager,
        state: SessionState,
        *,
        reason: str,
        attempt_number: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        lifecycle.transition(
            state,
            reason=reason,
            attempt_number=attempt_number,
            metadata=metadata,
            expected_from=lifecycle.state,
        )
        self._lease_manager.renew(lifecycle.session_id)

    def _check_cancelled(
        self,
        lifecycle: SessionLifecycleManager,
        retry_guard: RetryGuard,
        cancel_check: Optional[callable],
    ) -> bool:
        return bool(cancel_check and cancel_check())

    def _cancelled_result(
        self,
        request: BridgeRequest,
        session_id: str,
        started_at: datetime,
        digest: Optional[str],
        hardware: Dict[str, Any],
        attempts: List[AttemptRecord],
    ) -> BridgeSessionResult:
        try:
            lifecycle = SessionLifecycleManager(session_id)
            if lifecycle.state not in {SessionState.SUCCEEDED, SessionState.FAILED, SessionState.CANCELLED}:
                self._transition(lifecycle, SessionState.CANCELLED, reason="user_cancelled")
        except InvalidSessionTransition:
            pass
        summary = "Bridge session cancelled by user."
        outcomes.finalize_session(session_id, success=False, summary=summary)
        return BridgeSessionResult(
            session_id=session_id,
            file_path=request.file_path,
            file_hash=digest,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            success=False,
            attempts=attempts,
            hardware_profile=hardware,
            summary=summary,
        )

    def _timeout_result(
        self,
        request: BridgeRequest,
        session_id: str,
        started_at: datetime,
        digest: Optional[str],
        hardware: Dict[str, Any],
        attempts: List[AttemptRecord],
    ) -> BridgeSessionResult:
        try:
            lifecycle = SessionLifecycleManager(session_id)
            if lifecycle.state not in {SessionState.SUCCEEDED, SessionState.FAILED, SessionState.CANCELLED}:
                self._transition(lifecycle, SessionState.FAILED, reason="session_timeout")
        except InvalidSessionTransition:
            pass
        summary = "Bridge session failed: session_timeout exceeded."
        outcomes.finalize_session(session_id, success=False, summary=summary)
        return BridgeSessionResult(
            session_id=session_id,
            file_path=request.file_path,
            file_hash=digest,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            success=False,
            attempts=attempts,
            hardware_profile=hardware,
            summary=summary,
        )


_AUTO_FIX_SIGNATURES = frozenset({
    "dotnet_missing",
    "wine_int3_crash",
    "missing_dll",
    "missing_visual_c_runtime",
    "client_services_stalled",
    "sidecar_silent_crash",
    "electron_crashpad_failure",
})


def _baseline_launcher_remediation() -> Dict[str, Any]:
    return {
        "id": None,
        "signature": "*",
        "description": "Baseline Electron launcher attempt (GPU off, no auto-update, Wine wrappers).",
        "env": {
            "ELECTRON_DISABLE_CRASH_REPORTER": "1",
            "ALMA_SKIP_ELECTRON_UPDATE": "1",
            "WINEDEBUG": "-all",
        },
        "shims": [
            "electron_launcher_guard_workaround",
            "electron_elevate_passthrough",
        ],
        "args": electron_software_gl_args() + ["--no-update", "--skip-update"],
    }


def _maybe_apply_immediate_wine_fix(
    session_id: str,
    signature: Optional[str],
    wine_prefix: str,
    file_path: str,
    applied: set[str],
    *,
    stderr: str = "",
) -> bool:
    """Apply ML-ranked Wine fixes immediately when a failure signature is known."""
    from alma_bridge.execution.errors import launch_failure_in_log
    from alma_bridge.execution.wine_process import wine_rundll32_active

    sig = signature or launch_failure_in_log(stderr, "")
    if not sig and wine_prefix and wine_rundll32_active(wine_prefix):
        sig = "dotnet_missing"
    if not sig or sig not in _AUTO_FIX_SIGNATURES:
        return False
    fix_key = f"{sig}:{wine_prefix}"
    if fix_key in applied:
        return False
    applied.add(fix_key)
    apply_ml_wine_fix(
        sig,
        wine_prefix,
        file_path,
        progress_callback=lambda msg: _report_progress(session_id, msg),
    )
    return True


def _artifact_needs_dotnet_bootstrap(file_path: str, kind: Dict[str, Any]) -> bool:
    if not kind.get("needs_wine"):
        return False
    if kind.get("program_kind") == "pe_windows_gui":
        return False
    if kind.get("is_installer") or kind.get("is_electron"):
        return True
    lower = file_path.lower()
    if "ascension" in lower:
        return True
    return Path(file_path).suffix.lower() in {".exe", ".msi"}


def _ensure_prefix_runtimes(
    session_id: str,
    wine_prefix: str,
    file_path: str,
    kind: Dict[str, Any],
) -> None:
    if not wine_prefix or not _artifact_needs_dotnet_bootstrap(file_path, kind):
        return

    ascension = "ascension" in file_path.lower()
    if ascension:
        _report_progress(
            session_id,
            "Ascension detected — lightweight preflight (win10 + wrappers, skip .NET if ready)…",
        )
        ascension_wine_preflight(
            wine_prefix,
            file_path,
            progress_callback=lambda msg: _report_progress(session_id, msg),
        )
        return

    if prefix_runtimes_ready(wine_prefix):
        return
    _report_progress(
        session_id,
        "Installing VC++ and .NET 4.8 in the Wine prefix before launch "
        "(ignore any browser tab about .NET — Bridge handles it)…",
    )
    result = bootstrap_wine_runtimes(
        wine_prefix,
        progress_callback=lambda msg: _report_progress(session_id, msg),
    )
    if result.get("dotnet_ready") and result.get("vcrun_ready"):
        _report_progress(session_id, "Wine prefix runtimes are ready.")
    elif result.get("dotnet_ready"):
        _report_progress(session_id, ".NET is installed; VC++ may still be incomplete.")
    elif result.get("vcrun_ready"):
        _report_progress(
            session_id,
            "VC++ runtimes installed but .NET may still be incomplete — Bridge will retry if needed.",
        )
    else:
        _report_progress(
            session_id,
            "Wine runtimes may still be incomplete — Bridge will apply fixes after launch if needed.",
        )


def _build_rerank_event(
    *,
    sequence: int,
    after_strategy_id: str,
    error_signature: str,
    previous_order: List[str],
    remaining_plans: List[Dict[str, Any]],
) -> RerankEvent:
    new_order = [plan["strategy_id"] for plan in remaining_plans]
    top = remaining_plans[0] if remaining_plans else {}
    return RerankEvent(
        sequence=sequence,
        after_strategy_id=after_strategy_id,
        error_signature=error_signature,
        previous_order=previous_order,
        new_order=new_order,
        order_changed=previous_order != new_order,
        top_pick=top.get("strategy_id"),
        top_success_probability=top.get("success_probability"),
        rank_source=top.get("rank_source"),
    )


def _next_remediation(
    plan_signature: Optional[str],
    tried_ids: set[Optional[str]],
    *,
    allow_container: bool,
    installer: bool,
    electron: bool,
    preferred_remediation_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Pick the next remediation for the current strategy (baseline first)."""
    if plan_signature is None:
        if preferred_remediation_id and preferred_remediation_id not in tried_ids:
            prior = get_remediation_by_id(
                preferred_remediation_id,
                allow_container=allow_container,
                installer=installer,
                electron=electron,
            )
            if prior:
                return prior

        baseline_id = None
        if baseline_id in tried_ids:
            return None
        return {
            "id": None,
            "signature": "*",
            "env": {},
            "shims": [],
            "args": [],
        }

    for candidate in remediations_for_signature(
        plan_signature,
        allow_container=allow_container,
        installer=installer,
        electron=electron,
    ):
        if candidate.get("id") not in tried_ids:
            return candidate
    return None


def _failure_summary(
    attempts: int,
    plan_count: int,
    last_signature: Optional[str],
    recommended: List[str],
    *,
    installer: bool,
    sudo_requested: bool,
    passwordless_sudo: bool,
    rerank_count: int = 0,
) -> str:
    parts = [
        f"Exhausted {attempts} attempts across {plan_count} strategies.",
        f"Last error: {last_signature or 'unknown'}.",
    ]
    if rerank_count:
        parts.append(f"Re-ranked remaining strategies {rerank_count} time(s) from error feedback.")
    if sudo_requested and not passwordless_sudo:
        parts.append(
            "Sudo was requested but passwordless sudo is not configured — "
            "Wine/Proton now run without sudo."
        )
    if recommended:
        parts.append(f"Try next: {recommended[0]}")
    if installer:
        parts.append(
            "This looks like a Windows installer — ensure a GUI is available (DISPLAY) "
            "or retry with silent flags."
        )
    return " ".join(parts)


def _electron_prep_note(prep: Optional[Dict[str, Any]]) -> str:
    if not prep:
        return ""
    done = [
        a for a in prep.get("actions", [])
        if isinstance(a, dict) and a.get("status") == "installed"
    ]
    if done:
        kinds = sorted({str(a.get("action")) for a in done})
        return " Electron-on-Wine prep: " + ", ".join(kinds) + " installed; launched with --disable-gpu."
    unavailable = [
        a for a in prep.get("actions", [])
        if isinstance(a, dict) and a.get("status") == "unavailable"
    ]
    if unavailable:
        return (
            " Electron-on-Wine workarounds need the mingw-w64 cross-compiler "
            "(apt install gcc-mingw-w64-x86-64) to build the elevate/guard helpers."
        )
    return ""


def _plan_launch_args(plan: Dict[str, Any]) -> List[str]:
    command = plan.get("command") or []
    runtime = plan.get("runtime")
    if runtime == "proton" and len(command) >= 3:
        return list(command[3:])
    if runtime == "wine" and len(command) >= 2:
        return list(command[2:])
    return []


def _winetricks_packages_for_attempt(
    remediation: Dict[str, Any],
    env: Dict[str, str],
) -> Optional[str]:
    """Run winetricks only for the current attempt's remediation, not stacked history."""
    env.pop("ALMA_RUN_WINETRICKS", None)
    return (remediation.get("env") or {}).get("ALMA_RUN_WINETRICKS")


def _failure_error_text(attempt_records: List[AttemptRecord]) -> str:
    parts: List[str] = []
    for record in attempt_records:
        if record.success:
            continue
        for field in (record.stderr, record.detected_error, record.error_signature):
            text = str(field or "").strip()
            if text:
                parts.append(text)
    return "\n".join(dict.fromkeys(parts))[:8000]


def _persist_prefix_profile(wine_prefix: str, launcher_path: str) -> None:
    from alma_bridge.execution.preflight import prefix_vcrun_installed

    save_prefix_profile(
        PrefixReadinessProfile(
            wine_prefix=str(Path(wine_prefix).expanduser().resolve()),
            launcher_path=launcher_path,
            windows_version=read_wine_windows_version(wine_prefix),
            dotnet_functional=prefix_dotnet_functional(wine_prefix),
            vcrun_ready=prefix_vcrun_installed(wine_prefix),
            wrappers_applied=ascension_wrappers_present(launcher_path),
            updater_disabled=True,
        )
    )


def _report_progress(session_id: str, message: str) -> None:
    outcomes.update_session_progress(session_id, message)


def _persist_attempt(
    session_id: str,
    record: AttemptRecord,
    *,
    verification: Optional[Dict[str, Any]] = None,
    policy_decision: Optional[Dict[str, Any]] = None,
    state_fingerprint: Optional[str] = None,
    route_id: Optional[str] = None,
    escalation_kind: Optional[str] = None,
) -> None:
    outcomes.record_attempt(
        session_id=session_id,
        attempt_number=record.attempt_number,
        strategy_id=record.strategy_id,
        remediation_id=record.remediation_id,
        runtime=record.runtime,
        command=record.command,
        env=record.env,
        mode=record.mode.value,
        success=record.success,
        exit_code=record.exit_code,
        error_signature=record.error_signature,
        detected_error=record.detected_error,
        stdout=record.stdout,
        stderr=record.stderr,
        duration_ms=record.duration_ms,
        phase=record.phase,
        policy_decision=policy_decision,
        verification=verification,
        state_fingerprint=state_fingerprint,
        route_id=route_id,
        escalation_kind=escalation_kind,
    )
    if record.remediation_id and record.error_signature:
        try:
            from alma_bridge.learning.remediation_learning import record_remediation_outcome

            record_remediation_outcome(
                record.error_signature,
                record.remediation_id,
                bool(record.success),
            )
        except Exception:  # noqa: BLE001
            pass
