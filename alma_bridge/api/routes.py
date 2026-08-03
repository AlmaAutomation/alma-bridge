from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Response

from alma_bridge.schemas.bridge_domain import CompatibilityInspection
from alma_bridge.bridge.profile_builder import build_compatibility_inspection
from alma_bridge.execution.program_preflight import check_program_readiness
from alma_bridge.execution.installer_preflight import check_installer_readiness
from alma_bridge.execution.launcher_preflight import check_launcher_readiness
from alma_bridge.execution.runner import file_hash
from alma_bridge.observability.prometheus import render_bridge_metrics
from alma_bridge.hardware.prefixes import list_prefixes
from alma_bridge.hardware.profiler import profile_hardware
from alma_bridge.hardware.shims import SHIM_CATALOG, recommended_shims_from_profile
from alma_bridge.importers.service import ImportService
from alma_bridge.learning.datasets import export_csv_summary, export_training_dataset
from alma_bridge.learning.orchestrator import BridgeOrchestrator
from alma_bridge.learning.ranker import ranker_status
from alma_bridge.learning.training import maybe_auto_retrain, train_strategy_ranker
from alma_bridge.compliance.autopilot import (
    diagnose,
    host_summary,
    record_outcome,
    run_autopilot,
)
from alma_bridge.compliance.bridge import TlsModernizer
from alma_bridge.compliance.dns import resolve_doh
from alma_bridge.compliance.drivers import inventory_devices
from alma_bridge.compliance.learning import feedback_summary
from alma_bridge.compliance.legacy32 import assess_32bit_support, plan_32bit_enablement
from alma_bridge.compliance.modernization import (
    apply_playbook_steps,
    assess_host,
    build_modernization_playbook,
)
from alma_bridge.compliance.modernization.windows import (
    apply_windows_playbook,
    assess_windows_host,
    build_windows_playbook,
    export_playbook_script,
)
from alma_bridge.compliance.program import compliance_program, data_practices, purge_local_data
from alma_bridge.compliance.report import build_compliance_report
from alma_bridge.compliance.services import scan_insecure_services
from alma_bridge.compliance.timecheck import assess_clock
from alma_bridge.compliance.tls import assess_tls
from alma_bridge.compliance.web3 import (
    CHAIN_REGISTRY,
    assess_web3_endpoint,
    normalize_ipfs_uri,
)
from alma_bridge.flagship import flagship_summary
from alma_bridge.automation import (
    agent_heartbeat,
    agent_run_job,
    get_automation_session,
    list_automation_sessions,
    list_playbooks,
    machine_health,
    register_agent,
    request_approval,
    run_automation,
)
from alma_bridge.schemas.models import (
    AttemptRecord,
    AutopilotDiagnoseResponse,
    AutopilotFeedbackRequest,
    AutopilotFeedbackResponse,
    AutopilotRequest,
    AutopilotResponse,
    AutomationAgentHeartbeatRequest,
    AutomationAgentRegisterRequest,
    AutomationAgentRegisterResponse,
    AutomationAgentRunRequest,
    AutomationApprovalRequest,
    AutomationApprovalResponse,
    AutomationHealthResponse,
    AutomationPlaybooksResponse,
    AutomationRunRequest,
    AutomationRunResponse,
    ContainerRunRequest,
    ContainerRunResponse,
    ContainerShimPackRequest,
    ContainerShimPackResponse,
    SandboxStatusResponse,
    BridgeRequest,
    BridgeRunStartedResponse,
    BridgeSessionResult,
    ClockCheckRequest,
    ClockPostureResponse,
    ComplianceReportResponse,
    ComplianceScanRequest,
    DohResolveRequest,
    DohResolveResponse,
    DriverInventoryResponse,
    Legacy32PlanRequest,
    Legacy32PlanResponse,
    Legacy32Response,
    ModernizationApplyRequest,
    ModernizationApplyResponse,
    ModernizationAssessResponse,
    ModernizationPlaybookRequest,
    ModernizationPlaybookResponse,
    OperatorPlanRequest,
    MakeWorkRequest,
    OperatorRemediateRequest,
    OperatorStartRequest,
    OperatorTickRequest,
    SudoWarmRequest,
    WindowsModernizationApplyRequest,
    WindowsModernizationApplyResponse,
    WindowsModernizationAssessResponse,
    WindowsModernizationPlaybookRequest,
    WindowsModernizationPlaybookResponse,
    HardwareProfileResponse,
    ImportRequest,
    ImportResult,
    InstallerPreflightResponse,
    IpfsUrlRequest,
    IpfsUrlResponse,
    LauncherPreflightResponse,
    OutcomeStatsResponse,
    ProgramPreflightResponse,
    PriorSuccessResponse,
    RecentSessionsResponse,
    ServiceScanRequest,
    ServiceScanResponse,
    TlsAssessRequest,
    TlsBridgeInfo,
    TlsBridgeListResponse,
    TlsBridgeStartRequest,
    TlsPostureResponse,
    TrainRankerResult,
    Web3AssessRequest,
    Web3ChainsResponse,
    Web3PostureResponse,
)
from alma_bridge.execution.shim_pack import build_shim_pack, run_shim_pack, sandbox_status
from alma_bridge.api.intelligence_routes import router as intelligence_router
from alma_bridge.api.graph_routes import router as graph_router
from alma_bridge.api.knowledge_routes import router as knowledge_router
from alma_bridge.api.regression_routes import router as regression_router
from alma_bridge.api.advisor_routes import router as advisor_router
from alma_bridge.api.ask_routes import router as ask_router
from alma_bridge.api.catalog_routes import router as catalog_router
from alma_bridge.api.comparison_routes import router as comparison_router
from alma_bridge.api.decision_routes import router as decision_router
from alma_bridge.api.decision_review_routes import router as decision_review_router
from alma_bridge.api.decision_validation_routes import router as decision_validation_router
from alma_bridge.api.runtime_routes import router as runtime_router
from alma_bridge.api.compatibility_intelligence_routes import (
    router as compatibility_intelligence_router,
)
from alma_bridge.api.governance_routes import router as governance_router
from alma_bridge.api.expansion_routes import router as expansion_router
from alma_bridge.api.evidence_routes import router as evidence_router
from alma_bridge.api.research_routes import router as research_router
from alma_bridge.bridge.recent_sessions import build_recent_sessions_response
from alma_bridge.config import settings
from alma_bridge.storage import outcomes

router = APIRouter()
router.include_router(intelligence_router)
router.include_router(graph_router)
router.include_router(knowledge_router)
router.include_router(regression_router)
router.include_router(advisor_router)
router.include_router(ask_router)
router.include_router(catalog_router)
router.include_router(comparison_router)
router.include_router(decision_router)
router.include_router(decision_review_router)
router.include_router(decision_validation_router)
router.include_router(runtime_router)
router.include_router(compatibility_intelligence_router)
router.include_router(governance_router)
router.include_router(expansion_router)
router.include_router(evidence_router)
router.include_router(research_router)
orchestrator = BridgeOrchestrator()
import_service = ImportService()
tls_modernizer = TlsModernizer(ca_file=settings.compliance_ca_file)
_run_tasks: dict[str, asyncio.Task] = {}


def _session_to_result(session: dict) -> BridgeSessionResult:
    attempts = [AttemptRecord(**attempt) for attempt in session.get("attempts", [])]
    winning = session.get("winning_attempt")
    last = attempts[-1] if attempts else None
    return BridgeSessionResult(
        session_id=session["session_id"],
        file_path=session["file_path"],
        file_hash=session.get("file_hash"),
        started_at=datetime.fromisoformat(session["started_at"]),
        finished_at=datetime.fromisoformat(session["finished_at"]),
        success=bool(session.get("success")),
        winning_attempt=AttemptRecord(**winning) if winning else None,
        attempts=attempts,
        hardware_profile=session.get("hardware_profile") or {},
        summary=session.get("summary") or "",
        recommended_actions=(last.recommended_actions if last else []),
        rerank_events=session.get("rerank_events") or [],
    )


@router.get("/", tags=["System"])
def root() -> dict:
    return {
        "service": "alma-bridge",
        "status": "ok",
        "build": settings.bridge_build,
        "flagship_program": flagship_summary(),
        "message": "Alma Lab Modernization Program — open the flagship console for assess → apply.",
        "ui": "http://127.0.0.1:3001/app/compliance",
        "flagship": "/flagship",
        "docs": "/docs",
        "health": "/health",
    }


@router.get("/flagship", tags=["System"])
def flagship_program() -> dict:
    return flagship_summary()


@router.get("/prefixes", tags=["System"])
def prefixes() -> dict:
    return {"prefixes": list_prefixes()}


@router.get("/health", tags=["System"])
def health() -> dict:
    return {
        "status": "ok",
        "service": "alma-bridge",
        "build": settings.bridge_build,
        "flagship_program_id": "alma-lab-modernization",
    }


@router.get("/metrics", tags=["System"])
def metrics() -> Response:
    return Response(
        content=render_bridge_metrics(),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@router.get("/hardware/profile", response_model=HardwareProfileResponse, tags=["Hardware"])
def hardware_profile() -> HardwareProfileResponse:
    profile = profile_hardware()
    recommended = recommended_shims_from_profile(profile)
    from alma_bridge.hardware.proton import find_proton_installs

    return HardwareProfileResponse(
        profile={
            **profile,
            "recommended_shims": recommended,
            "proton_installs": find_proton_installs(),
        },
        shims_available=SHIM_CATALOG,
        capabilities=profile.get("capabilities", {}),
    )


@router.get("/bridge/inspect", response_model=CompatibilityInspection, tags=["Bridge"])
def bridge_inspect(path: str) -> CompatibilityInspection:
    """Read-only compatibility inspection: program profile, host profile, and gaps."""
    if not path.strip():
        raise HTTPException(status_code=400, detail="path query parameter is required")
    return build_compatibility_inspection(path)


@router.get("/bridge/program/preflight", response_model=ProgramPreflightResponse, tags=["Bridge"])
def program_preflight(path: str, wine_prefix: str | None = None) -> ProgramPreflightResponse:
    if not path.strip():
        raise HTTPException(status_code=400, detail="path query parameter is required")
    return ProgramPreflightResponse(**check_program_readiness(path, wine_prefix=wine_prefix))


@router.get("/bridge/installer/preflight", response_model=InstallerPreflightResponse, tags=["Bridge"])
def installer_preflight(path: str, wine_prefix: str | None = None) -> InstallerPreflightResponse:
    if not path.strip():
        raise HTTPException(status_code=400, detail="path query parameter is required")
    return InstallerPreflightResponse(**check_installer_readiness(path, wine_prefix=wine_prefix))


@router.get("/bridge/launcher/preflight", response_model=LauncherPreflightResponse, tags=["Bridge"])
def launcher_preflight(path: str, wine_prefix: str | None = None) -> LauncherPreflightResponse:
    if not path.strip():
        raise HTTPException(status_code=400, detail="path query parameter is required")
    return LauncherPreflightResponse(**check_launcher_readiness(path, wine_prefix=wine_prefix))


@router.post("/bridge/plan", tags=["Bridge"])
def bridge_plan(request: BridgeRequest) -> dict:
    from alma_bridge.compatibility.planner import plan_ranker_summary
    from alma_bridge.session.services.planner import DefaultCompatibilityPlanner, plan_step_to_dict

    execution_plan = DefaultCompatibilityPlanner().plan(
        request.file_path,
        runtime_hint=request.runtime_hint,
        preferred_strategy_id=request.preferred_strategy_id,
        wine_prefix=request.wine_prefix,
        proton_path=request.proton_path,
        base_env=request.env,
    )
    plans = [plan_step_to_dict(step) for step in execution_plan.steps]
    return {
        "file_path": request.file_path,
        "plans": plans,
        "ranker": plan_ranker_summary(),
    }


@router.post("/bridge/run", response_model=BridgeSessionResult, tags=["Bridge"])
async def bridge_run(request: BridgeRequest) -> BridgeSessionResult:
    if not Path(request.file_path).exists():
        raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")
    from alma_bridge.validation.campaign_guard import (
        CampaignPrefixRejected,
        validate_campaign_bridge_request,
    )

    try:
        validate_campaign_bridge_request(request)
    except CampaignPrefixRejected as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    result = await asyncio.to_thread(orchestrator.run, request)
    if settings.auto_retrain_after_run:
        maybe_auto_retrain(
            min_records=settings.auto_retrain_min_records,
            min_new_records=settings.auto_retrain_min_new_records,
        )
    return result


@router.post("/bridge/run/async", response_model=BridgeRunStartedResponse, tags=["Bridge"])
async def bridge_run_async(request: BridgeRequest) -> BridgeRunStartedResponse:
    if not Path(request.file_path).exists():
        raise HTTPException(status_code=404, detail=f"File not found: {request.file_path}")
    from alma_bridge.validation.campaign_guard import (
        CampaignPrefixRejected,
        validate_campaign_bridge_request,
    )

    try:
        validate_campaign_bridge_request(request)
    except CampaignPrefixRejected as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    hardware = profile_hardware()
    digest = file_hash(request.file_path)
    session_id = outcomes.new_session(request.file_path, digest, hardware)
    outcomes.update_session_progress(session_id, "Bridge run queued…")

    async def _execute() -> None:
        try:
            await asyncio.to_thread(orchestrator.run, request, session_id=session_id)
            if settings.auto_retrain_after_run:
                maybe_auto_retrain(
                    min_records=settings.auto_retrain_min_records,
                    min_new_records=settings.auto_retrain_min_new_records,
                )
        except Exception as exc:
            outcomes.finalize_session(session_id, False, f"Bridge run failed: {exc}")

    task = asyncio.create_task(_execute())
    _run_tasks[session_id] = task
    task.add_done_callback(lambda _t: _run_tasks.pop(session_id, None))
    return BridgeRunStartedResponse(session_id=session_id)


@router.get("/bridge/run/{session_id}/result", response_model=BridgeSessionResult, tags=["Bridge"])
def bridge_run_result(session_id: str) -> BridgeSessionResult:
    session = outcomes.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if not session.get("finished_at"):
        raise HTTPException(status_code=409, detail="Session still running")
    return _session_to_result(session)


@router.get(
    "/bridge/sessions/recent",
    response_model=RecentSessionsResponse,
    tags=["Bridge"],
)
def bridge_sessions_recent(limit: int = 20, path: str | None = None) -> RecentSessionsResponse:
    return build_recent_sessions_response(limit=limit, file_path=path)


@router.get("/bridge/session/{session_id}", tags=["Bridge"])
def bridge_session(session_id: str) -> dict:
    session = outcomes.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


@router.get("/outcomes/stats", response_model=OutcomeStatsResponse, tags=["Learning"])
def outcome_stats() -> OutcomeStatsResponse:
    return OutcomeStatsResponse(**outcomes.get_stats())


@router.get("/outcomes/prior-success", response_model=PriorSuccessResponse, tags=["Learning"])
def prior_success(path: str) -> PriorSuccessResponse:
    if not path.strip():
        raise HTTPException(status_code=400, detail="path query parameter is required")
    return PriorSuccessResponse(**outcomes.get_prior_success(path))


@router.post("/import/all", response_model=ImportResult, tags=["Import"])
def import_all(request: ImportRequest) -> ImportResult:
    result: dict = {}
    if "almasysdet" in request.sources:
        result["almasysdet"] = import_service.import_sysdet(
            db_path=Path(request.sysdet_db) if request.sysdet_db else None,
            limit=request.limit,
            skip_existing=request.skip_existing,
        )
    if "alma_resolve" in request.sources:
        result["alma_resolve"] = import_service.import_resolve(
            audit_dir=Path(request.resolve_audit_dir) if request.resolve_audit_dir else None,
            skip_existing=request.skip_existing,
        )
    result["total_sessions"] = sum(
        item.get("imported_sessions", 0) for item in result.values() if isinstance(item, dict)
    )
    result["total_attempts"] = sum(
        item.get("imported_attempts", 0) for item in result.values() if isinstance(item, dict)
    )
    return ImportResult(**result)


@router.post("/import/sysdet", tags=["Import"])
def import_sysdet(request: ImportRequest) -> dict:
    return import_service.import_sysdet(
        db_path=Path(request.sysdet_db) if request.sysdet_db else None,
        limit=request.limit,
        skip_existing=request.skip_existing,
    )


@router.post("/import/resolve", tags=["Import"])
def import_resolve(request: ImportRequest) -> dict:
    return import_service.import_resolve(
        audit_dir=Path(request.resolve_audit_dir) if request.resolve_audit_dir else None,
        skip_existing=request.skip_existing,
    )


@router.get("/train/ranker/status", tags=["Training"])
def train_ranker_status() -> dict:
    return ranker_status()


@router.post("/train/ranker", response_model=TrainRankerResult, tags=["Training"])
def train_ranker() -> TrainRankerResult:
    result = train_strategy_ranker()
    return TrainRankerResult(**result)


@router.post("/datasets/export", tags=["Training"])
def export_dataset() -> dict:
    jsonl = Path("data/training_dataset.jsonl")
    csv_path = Path("data/outcome_summary.csv")
    return {
        "jsonl": export_training_dataset(jsonl),
        "csv": export_csv_summary(csv_path),
    }


# --------------------------------------------------------------------------- #
# Legacy compliance: HTTPS/TLS + drivers/shims
# --------------------------------------------------------------------------- #


@router.post("/compliance/tls/assess", response_model=TlsPostureResponse, tags=["Compliance"])
async def compliance_tls_assess(request: TlsAssessRequest) -> TlsPostureResponse:
    if not request.host.strip():
        raise HTTPException(status_code=400, detail="host is required")
    verdict = await asyncio.to_thread(
        assess_tls,
        request.host,
        request.port,
        timeout=request.timeout,
        ca_file=settings.compliance_ca_file,
        probe_legacy=request.probe_legacy,
        cache_ttl=settings.compliance_cache_ttl,
    )
    return TlsPostureResponse(**verdict)


@router.post("/compliance/tls/bridge", response_model=TlsBridgeInfo, tags=["Compliance"])
async def compliance_tls_bridge_start(request: TlsBridgeStartRequest) -> TlsBridgeInfo:
    if not request.upstream_host.strip():
        raise HTTPException(status_code=400, detail="upstream_host is required")
    try:
        spec = await tls_modernizer.start(
            request.upstream_host,
            request.upstream_port,
            listen_host=request.listen_host or settings.compliance_bridge_listen_host,
            listen_port=request.listen_port,
            verify=request.verify,
            upstream_sni=request.upstream_sni,
            min_tls=request.min_tls,
        )
    except OSError as exc:
        raise HTTPException(status_code=409, detail=f"Could not start bridge: {exc}")
    return TlsBridgeInfo(**spec.to_dict())


@router.get("/compliance/tls/bridges", response_model=TlsBridgeListResponse, tags=["Compliance"])
def compliance_tls_bridges() -> TlsBridgeListResponse:
    bridges = tls_modernizer.list()
    return TlsBridgeListResponse(
        bridges=[TlsBridgeInfo(**b) for b in bridges], count=len(bridges)
    )


@router.delete("/compliance/tls/bridge/{bridge_id}", tags=["Compliance"])
async def compliance_tls_bridge_stop(bridge_id: str) -> dict:
    stopped = await tls_modernizer.stop(bridge_id)
    if not stopped:
        raise HTTPException(status_code=404, detail="Bridge not found")
    return {"stopped": True, "id": bridge_id}


@router.get("/compliance/drivers", response_model=DriverInventoryResponse, tags=["Compliance"])
async def compliance_drivers() -> DriverInventoryResponse:
    catalog_db = settings.compliance_driver_catalog_db
    inventory = await asyncio.to_thread(
        inventory_devices,
        settings.compliance_sys_root,
        catalog_db=catalog_db if catalog_db and Path(catalog_db).exists() else None,
    )
    return DriverInventoryResponse(**inventory)


@router.post("/compliance/scan", response_model=ComplianceReportResponse, tags=["Compliance"])
async def compliance_scan(request: ComplianceScanRequest) -> ComplianceReportResponse:
    catalog_db = settings.compliance_driver_catalog_db
    report = await asyncio.to_thread(
        build_compliance_report,
        request.targets,
        include_drivers=request.include_drivers,
        include_shims=request.include_shims,
        sys_root=settings.compliance_sys_root,
        catalog_db=catalog_db if catalog_db and Path(catalog_db).exists() else None,
        tls_timeout=request.tls_timeout,
        probe_legacy=request.probe_legacy,
        web3_rpc=request.web3_rpc,
        check_time=request.check_time,
        ntp_server=request.ntp_server,
        scan_services=request.scan_services,
        max_workers=settings.compliance_max_workers,
        cache_ttl=settings.compliance_cache_ttl,
    )
    return ComplianceReportResponse(**report)


@router.get("/compliance/tls/ca-bundle", tags=["Compliance"])
def compliance_ca_bundle() -> Response:
    """Serve Alma's up-to-date CA root bundle (PEM) for legacy trust stores."""
    import certifi

    ca_path = settings.compliance_ca_file or certifi.where()
    try:
        pem = Path(ca_path).read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"CA bundle unavailable: {exc}")
    return Response(
        content=pem,
        media_type="application/x-pem-file",
        headers={"Content-Disposition": "attachment; filename=alma-ca-bundle.pem"},
    )


@router.post("/compliance/time/check", response_model=ClockPostureResponse, tags=["Compliance"])
async def compliance_time_check(request: ClockCheckRequest) -> ClockPostureResponse:
    verdict = await asyncio.to_thread(
        assess_clock, request.ntp_server, timeout=request.timeout
    )
    return ClockPostureResponse(**verdict)


@router.post("/compliance/services/scan", response_model=ServiceScanResponse, tags=["Compliance"])
async def compliance_services_scan(request: ServiceScanRequest) -> ServiceScanResponse:
    if not request.host.strip():
        raise HTTPException(status_code=400, detail="host is required")
    result = await asyncio.to_thread(
        scan_insecure_services, request.host, ports=request.ports, timeout=request.timeout
    )
    return ServiceScanResponse(**result)


@router.post("/compliance/dns/resolve", response_model=DohResolveResponse, tags=["Compliance"])
async def compliance_dns_resolve(request: DohResolveRequest) -> DohResolveResponse:
    if not request.name.strip():
        raise HTTPException(status_code=400, detail="name is required")
    result = await asyncio.to_thread(
        resolve_doh,
        request.name,
        request.record_type,
        provider=request.provider,
        timeout=request.timeout,
        cache_ttl=settings.compliance_cache_ttl,
    )
    return DohResolveResponse(**result)


@router.post("/compliance/web3/assess", response_model=Web3PostureResponse, tags=["Compliance"])
async def compliance_web3_assess(request: Web3AssessRequest) -> Web3PostureResponse:
    if not request.rpc_url.strip():
        raise HTTPException(status_code=400, detail="rpc_url is required")
    verdict = await asyncio.to_thread(
        assess_web3_endpoint,
        request.rpc_url,
        timeout=request.timeout,
        check_tls=request.check_tls,
        cache_ttl=settings.compliance_cache_ttl,
    )
    return Web3PostureResponse(**verdict)


@router.get("/compliance/web3/chains", response_model=Web3ChainsResponse, tags=["Compliance"])
def compliance_web3_chains() -> Web3ChainsResponse:
    return Web3ChainsResponse(chains=CHAIN_REGISTRY, count=len(CHAIN_REGISTRY))


@router.post("/compliance/web3/ipfs-url", response_model=IpfsUrlResponse, tags=["Compliance"])
def compliance_web3_ipfs_url(request: IpfsUrlRequest) -> IpfsUrlResponse:
    if not request.uri.strip():
        raise HTTPException(status_code=400, detail="uri is required")
    return IpfsUrlResponse(**normalize_ipfs_uri(request.uri, request.gateway))


# --------------------------------------------------------------------------- #
# Self-healing autopilot
# --------------------------------------------------------------------------- #


@router.post("/compliance/autopilot/diagnose", response_model=AutopilotDiagnoseResponse, tags=["Compliance"])
def compliance_autopilot_diagnose(request: AutopilotRequest) -> AutopilotDiagnoseResponse:
    if not request.error_text.strip():
        raise HTTPException(status_code=400, detail="error_text is required")
    return AutopilotDiagnoseResponse(diagnoses=diagnose(request.error_text))


@router.post("/compliance/autopilot/run", response_model=AutopilotResponse, tags=["Compliance"])
async def compliance_autopilot_run(request: AutopilotRequest) -> AutopilotResponse:
    if not request.error_text.strip():
        raise HTTPException(status_code=400, detail="error_text is required")
    plan = await asyncio.to_thread(
        run_autopilot,
        request.error_text,
        os_release=request.os_release,
        execute=request.execute,
        allow_mutations=request.allow_mutations,
        binary=request.binary,
        timeout=request.timeout,
        sudo_password=request.sudo_password,
    )
    return AutopilotResponse(**plan)


@router.post("/compliance/autopilot/feedback", response_model=AutopilotFeedbackResponse, tags=["Compliance"])
def compliance_autopilot_feedback(request: AutopilotFeedbackRequest) -> AutopilotFeedbackResponse:
    if not request.signature.strip() or not request.pathway_id.strip():
        raise HTTPException(status_code=400, detail="signature and pathway_id are required")
    record_outcome(request.signature, request.pathway_id, request.success)
    return AutopilotFeedbackResponse(recorded=True, summary=feedback_summary())


@router.get("/compliance/autopilot/host", tags=["Compliance"])
def compliance_autopilot_host() -> dict:
    return host_summary()


# --------------------------------------------------------------------------- #
# 32-bit legacy readiness
# --------------------------------------------------------------------------- #


@router.get("/compliance/legacy32", response_model=Legacy32Response, tags=["Compliance"])
async def compliance_legacy32() -> Legacy32Response:
    assessment = await asyncio.to_thread(assess_32bit_support)
    return Legacy32Response(**assessment)


@router.post("/compliance/legacy32/plan", response_model=Legacy32PlanResponse, tags=["Compliance"])
async def compliance_legacy32_plan(request: Legacy32PlanRequest) -> Legacy32PlanResponse:
    plan = await asyncio.to_thread(
        plan_32bit_enablement, None, os_release=request.os_release
    )
    return Legacy32PlanResponse(**plan)


# --------------------------------------------------------------------------- #
# Commercial program compliance (legal, privacy, retention)
# --------------------------------------------------------------------------- #


@router.get("/compliance/program", tags=["Compliance"])
def compliance_program_info() -> dict:
    return compliance_program()


@router.get("/compliance/program/data-practices", tags=["Compliance"])
def compliance_data_practices() -> dict:
    return data_practices()


@router.delete("/compliance/program/data", tags=["Compliance"])
async def compliance_purge_local_data(older_than_days: int | None = None) -> dict:
    """Purge automation audit data older than retention window (requires API key when set)."""
    return await asyncio.to_thread(purge_local_data, older_than_days=older_than_days)


# --------------------------------------------------------------------------- #
# Legacy host modernization (assess → playbook → apply)
# --------------------------------------------------------------------------- #


@router.get("/modernization/assess", response_model=ModernizationAssessResponse, tags=["Modernization"])
async def modernization_assess() -> ModernizationAssessResponse:
    result = await asyncio.to_thread(assess_host)
    return ModernizationAssessResponse(**result)


@router.post("/modernization/playbook", response_model=ModernizationPlaybookResponse, tags=["Modernization"])
async def modernization_playbook(
    request: ModernizationPlaybookRequest,
) -> ModernizationPlaybookResponse:
    playbook = await asyncio.to_thread(
        build_modernization_playbook,
        None,
        os_release=request.os_release,
        include_browser=request.include_browser,
        include_potato_tuning=request.include_potato_tuning,
    )
    # Drop nested full assessment from API response (large); keep summary fields.
    playbook.pop("assessment", None)
    return ModernizationPlaybookResponse(**playbook)


@router.post("/modernization/apply", response_model=ModernizationApplyResponse, tags=["Modernization"])
async def modernization_apply(request: ModernizationApplyRequest) -> ModernizationApplyResponse:
    if not request.allow_mutations:
        raise HTTPException(
            status_code=400,
            detail="allow_mutations must be true to apply changes (requires sudo on the host)",
        )

    def _run():
        playbook = build_modernization_playbook(
            None,
            os_release=request.os_release,
            include_browser=request.include_browser,
            include_potato_tuning=request.include_potato_tuning,
        )
        outcome = apply_playbook_steps(
            playbook["steps"],
            step_ids=request.step_ids or playbook.get("apply_step_ids"),
            allow_mutations=True,
            stop_on_error=request.stop_on_error,
            package_manager=playbook.get("package_manager"),
            sudo_password=request.sudo_password,
        )
        outcome["playbook_verdict"] = playbook.get("verdict")
        return outcome

    result = await asyncio.to_thread(_run)
    return ModernizationApplyResponse(**result)


@router.get("/modernization/apply", tags=["Modernization"])
def modernization_apply_usage() -> dict:
    """Browser-friendly hint — apply must be POST with allow_mutations."""
    return {
        "method": "POST",
        "detail": "Use POST with JSON body {\"allow_mutations\": true}. Requires sudo on the host.",
        "example": (
            "curl -X POST http://127.0.0.1:9010/modernization/apply "
            "-H 'content-type: application/json' "
            "-d '{\"allow_mutations\": true}'"
        ),
        "ui": "Use the Modernization tab → Build playbook → check confirmation → Apply playbook",
    }


# --------------------------------------------------------------------------- #
# Windows lab modernization (PowerShell — plan on server, apply on lab PCs)
# --------------------------------------------------------------------------- #


@router.get("/modernization/windows/assess", response_model=WindowsModernizationAssessResponse, tags=["Modernization"])
async def windows_modernization_assess() -> WindowsModernizationAssessResponse:
    result = await asyncio.to_thread(assess_windows_host)
    return WindowsModernizationAssessResponse(**result)


@router.post("/modernization/windows/playbook", response_model=WindowsModernizationPlaybookResponse, tags=["Modernization"])
async def windows_modernization_playbook(
    request: WindowsModernizationPlaybookRequest,
) -> WindowsModernizationPlaybookResponse:
    def _build():
        assessment = assess_windows_host()
        playbook = build_windows_playbook(
            assessment,
            recipe_id=request.recipe_id,
            include_browser=request.include_browser,
            include_performance_tuning=request.include_performance_tuning,
        )
        playbook.pop("assessment", None)
        playbook["export_script"] = export_playbook_script(playbook)
        return playbook

    result = await asyncio.to_thread(_build)
    return WindowsModernizationPlaybookResponse(**result)


@router.get("/modernization/windows/export.ps1", tags=["Modernization"])
async def windows_modernization_export_ps1(recipe_id: str = "school-lab-windows") -> Response:
    def _export():
        assessment = assess_windows_host()
        playbook = build_windows_playbook(assessment, recipe_id=recipe_id)
        return export_playbook_script(playbook)

    script = await asyncio.to_thread(_export)
    return Response(
        content=script,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{recipe_id}.ps1"'},
    )


@router.post("/modernization/windows/apply", response_model=WindowsModernizationApplyResponse, tags=["Modernization"])
async def windows_modernization_apply(
    request: WindowsModernizationApplyRequest,
) -> WindowsModernizationApplyResponse:
    def _run():
        assessment = assess_windows_host()
        playbook = build_windows_playbook(
            assessment,
            recipe_id=request.recipe_id,
            include_browser=request.include_browser,
            include_performance_tuning=request.include_performance_tuning,
        )
        outcome = apply_windows_playbook(
            playbook,
            step_ids=request.step_ids or playbook.get("apply_step_ids"),
            allow_mutations=request.allow_mutations,
            stop_on_error=request.stop_on_error,
        )
        outcome["playbook_verdict"] = playbook.get("verdict")
        return outcome

    result = await asyncio.to_thread(_run)
    return WindowsModernizationApplyResponse(**result)


# --------------------------------------------------------------------------- #
# Automation platform (unified scan → assess → apply → verify → learn)
# --------------------------------------------------------------------------- #


@router.get("/automation/health", response_model=AutomationHealthResponse, tags=["Automation"])
async def automation_health() -> AutomationHealthResponse:
    result = await asyncio.to_thread(machine_health)
    return AutomationHealthResponse(**result)


@router.get("/automation/playbooks", response_model=AutomationPlaybooksResponse, tags=["Automation"])
def automation_playbooks() -> AutomationPlaybooksResponse:
    return AutomationPlaybooksResponse(playbooks=list_playbooks())


@router.get("/automation/playbooks/{recipe_id}", tags=["Automation"])
def automation_playbook_recipe(recipe_id: str) -> dict:
    from alma_bridge.automation.playbooks import build_recipe_playbook

    try:
        playbook = build_recipe_playbook(recipe_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    playbook.pop("assessment", None)
    return {
        "id": recipe_id,
        "recipe_id": playbook.get("recipe_id", recipe_id),
        "recipe_title": playbook.get("recipe_title"),
        "apply_step_ids": playbook.get("apply_step_ids", []),
        "steps": playbook.get("steps", []),
        "summary": playbook.get("summary"),
        "export_script": playbook.get("export_script"),
    }


@router.post("/automation/run", response_model=AutomationRunResponse, tags=["Automation"])
async def automation_run(request: AutomationRunRequest) -> AutomationRunResponse:
    if request.apply and not request.allow_mutations and not request.approval_token:
        raise HTTPException(
            status_code=400,
            detail="apply requires allow_mutations=true or a valid approval_token",
        )
    result = await asyncio.to_thread(
        run_automation,
        scan_path=request.scan_path,
        playbook_recipe=request.playbook_recipe,
        apply=request.apply,
        allow_mutations=request.allow_mutations,
        approval_token=request.approval_token,
        sudo_password=request.sudo_password,
        step_ids=request.step_ids,
        verify=request.verify,
        https_probe_host=request.https_probe_host,
        file_path=request.file_path,
        bridge_run=request.bridge_run,
        bridge_max_attempts=request.bridge_max_attempts,
        bridge_sandbox=request.bridge_sandbox,
        error_text=request.error_text,
        os_release=request.os_release,
        container_run=request.container_run,
    )
    return AutomationRunResponse(**result)


@router.post("/automation/approve", response_model=AutomationApprovalResponse, tags=["Automation"])
def automation_approve(request: AutomationApprovalRequest) -> AutomationApprovalResponse:
    if not request.step_ids:
        raise HTTPException(status_code=400, detail="step_ids required")
    result = request_approval(request.step_ids, ttl_minutes=request.ttl_minutes)
    return AutomationApprovalResponse(**result)


@router.get("/automation/sessions", tags=["Automation"])
def automation_sessions(limit: int = 20) -> dict:
    return {"sessions": list_automation_sessions(limit=limit)}


@router.get("/automation/sessions/{session_id}", tags=["Automation"])
def automation_session_detail(session_id: str) -> dict:
    session = get_automation_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return session


@router.post("/automation/agent/register", response_model=AutomationAgentRegisterResponse, tags=["Automation"])
def automation_agent_register(
    request: AutomationAgentRegisterRequest,
) -> AutomationAgentRegisterResponse:
    result = register_agent(agent_id=request.agent_id, meta=request.meta)
    return AutomationAgentRegisterResponse(**result)


@router.post("/automation/agent/heartbeat", tags=["Automation"])
async def automation_agent_heartbeat(
    request: AutomationAgentHeartbeatRequest,
) -> dict:
    return await asyncio.to_thread(agent_heartbeat, request.agent_id)


@router.post("/automation/agent/run", response_model=AutomationRunResponse, tags=["Automation"])
async def automation_agent_run(request: AutomationAgentRunRequest) -> AutomationRunResponse:
    if request.apply and not request.allow_mutations and not request.approval_token:
        raise HTTPException(
            status_code=400,
            detail="apply requires allow_mutations=true or a valid approval_token",
        )
    result = await asyncio.to_thread(
        agent_run_job,
        request.agent_id,
        scan_path=request.scan_path,
        playbook_recipe=request.playbook_recipe,
        apply=request.apply,
        allow_mutations=request.allow_mutations,
        approval_token=request.approval_token,
        sudo_password=request.sudo_password,
        step_ids=request.step_ids,
        verify=request.verify,
        os_release=request.os_release,
        error_text=request.error_text,
    )
    return AutomationRunResponse(**result)


# --------------------------------------------------------------------------- #
# AI Operator — autonomous observe → decide → apply → verify
# --------------------------------------------------------------------------- #


@router.get("/operator/status", tags=["Operator"])
def operator_status() -> dict:
    """Current operator policy + background-loop state and recent cycles."""
    from alma_bridge.operator import operator_loop

    return operator_loop.status()


@router.get("/operator/observe", tags=["Operator"])
async def operator_observe(os_release: Optional[str] = None, error_text: Optional[str] = None) -> dict:
    """What the operator currently 'sees': host, gaps, ML, history."""
    from alma_bridge.operator import observe

    observation = await asyncio.to_thread(observe, os_release=os_release, error_text=error_text)
    return {k: v for k, v in observation.items() if not k.startswith("_")}


@router.post("/operator/plan", tags=["Operator"])
async def operator_plan(request: OperatorPlanRequest) -> dict:
    """Observe + decide: a ranked, risk-scored action plan (no changes made)."""
    from alma_bridge.operator import decide, observe

    def _plan() -> dict:
        observation = observe(os_release=request.os_release, error_text=request.error_text)
        plan = decide(observation)
        return {
            "observation": {k: v for k, v in observation.items() if not k.startswith("_")},
            "plan": plan,
        }

    return await asyncio.to_thread(_plan)


@router.post("/operator/tick", tags=["Operator"])
async def operator_tick(request: OperatorTickRequest) -> dict:
    """Run one operator cycle now. Applies changes only if policy permits."""
    from alma_bridge.execution.privileges import remember_sudo_password
    from alma_bridge.operator import operator_loop

    if request.sudo_password:
        remember_sudo_password(request.sudo_password)
    return await operator_loop.tick_once(
        apply=request.apply,
        sudo_password=request.sudo_password,
    )


@router.get("/operator/failures", tags=["Operator"])
async def operator_failures(limit: int = 10) -> dict:
    """Examine recent failed automation / bridge attempts and propose mitigations."""
    from alma_bridge.operator import examine_failures

    return await asyncio.to_thread(examine_failures, limit=limit)


@router.get("/operator/routes", tags=["Operator"])
async def operator_routes(
    error_text: Optional[str] = None,
    file_path: Optional[str] = None,
    limit: int = 12,
) -> dict:
    """Discover ranked routes: Bridge strategies + pathways + synthesized fixes."""
    from alma_bridge.operator import discover_routes

    def _discover() -> dict:
        result = discover_routes(error_text or "", file_path=file_path)
        routes = result.get("routes") or []
        result["routes"] = routes[: max(1, min(limit, 50))]
        return result

    return await asyncio.to_thread(_discover)


@router.post("/compatibility/make-work", tags=["Compatibility"])
async def compatibility_make_work(request: MakeWorkRequest) -> dict:
    """Build compatibility for a program via authoritative BridgeOrchestrator."""
    from alma_bridge.operator.routes import discover_routes, execute_best_routes
    from alma_bridge.schemas.models import BridgeRequest

    def _make_work() -> dict:
        discovery = discover_routes(
            request.error_text or "",
            file_path=request.file_path,
        )
        bridge_req = BridgeRequest(
            file_path=request.file_path,
            auto_remediate=request.apply,
            sudo_password=request.sudo_password,
            use_sudo=bool(request.sudo_password),
        )
        if request.apply:
            session = orchestrator.run(bridge_req)
            execution = {
                "applied": True,
                "success_count": int(session.success),
                "winning_route": "bridge:orchestrator",
                "results": [
                    {
                        "route_id": "bridge:orchestrator",
                        "success": session.success,
                        "execution": {
                            "summary": session.summary,
                            "session_id": session.session_id,
                        },
                    }
                ],
                "routes_attempted": 1,
                "requires_orchestrator_resume": False,
            }
        else:
            execution = execute_best_routes(discovery, apply=False)
        routes = discovery.get("routes") or []
        return {
            "file_path": request.file_path,
            "error_text": request.error_text,
            "route_count": discovery.get("route_count", len(routes)),
            "primary_signature": discovery.get("primary_signature"),
            "top_routes": [
                {
                    "id": r.get("id"),
                    "kind": r.get("kind"),
                    "title": r.get("title"),
                    "score": r.get("score"),
                }
                for r in routes[:8]
            ],
            "execution": execution,
            "success": bool(execution.get("success_count")),
            "winning_route": execution.get("winning_route"),
        }

    return await asyncio.to_thread(_make_work)


@router.post("/operator/remediate", tags=["Operator"])
async def operator_remediate(request: OperatorRemediateRequest) -> dict:
    """Diagnose failed attempts and apply mitigations when policy permits."""
    from alma_bridge.execution.privileges import remember_sudo_password
    from alma_bridge.operator import apply_mitigations, examine_failures

    if request.sudo_password:
        remember_sudo_password(request.sudo_password)

    def _remediate() -> dict:
        examination = examine_failures(limit=request.limit)
        remediation = apply_mitigations(
            examination,
            apply=request.apply,
            sudo_password=request.sudo_password,
            only_auto=request.only_auto,
        )
        return {"examination": examination, "remediation": remediation}

    return await asyncio.to_thread(_remediate)


@router.post("/operator/start", tags=["Operator"])
def operator_start(request: OperatorStartRequest) -> dict:
    """Start the autonomous background loop (requires operator_enabled)."""
    from alma_bridge.operator import operator_loop

    return operator_loop.start(interval_sec=request.interval_sec, apply=request.apply)


@router.post("/operator/stop", tags=["Operator"])
async def operator_stop() -> dict:
    """Stop the autonomous background loop."""
    from alma_bridge.operator import operator_loop

    return await operator_loop.stop()


# --------------------------------------------------------------------------- #
# Container shim pack — VM-like isolated execution
# --------------------------------------------------------------------------- #


@router.post("/execution/sudo/warm", tags=["Execution"])
def execution_sudo_warm(request: SudoWarmRequest) -> dict:
    """Warm the sudo ticket cache from a UI password (shared with the operator loop)."""
    from alma_bridge.execution.privileges import remember_sudo_password, sudo_ticket_valid

    ready, error = remember_sudo_password(request.sudo_password)
    return {
        "ready": ready,
        "ticket_valid": sudo_ticket_valid(),
        "error": error or None,
    }


@router.get("/execution/sudo/status", tags=["Execution"])
def execution_sudo_status() -> dict:
    from alma_bridge.execution.privileges import (
        get_stored_sudo_password,
        passwordless_sudo_works,
        sudo_ticket_valid,
    )

    return {
        "ready": passwordless_sudo_works() or sudo_ticket_valid(),
        "ticket_valid": sudo_ticket_valid(),
        "password_stored": bool(get_stored_sudo_password()),
        "passwordless": passwordless_sudo_works(),
    }


@router.get("/execution/sandbox/status", response_model=SandboxStatusResponse, tags=["Container"])
def execution_sandbox_status() -> SandboxStatusResponse:
    return SandboxStatusResponse(**sandbox_status())


@router.get("/container/shims", tags=["Container"])
async def container_shims_catalog(file_path: Optional[str] = None) -> dict:
    hardware = await asyncio.to_thread(profile_hardware)
    payload: dict = {
        "catalog": SHIM_CATALOG,
        "recommended": recommended_shims_from_profile(hardware),
    }
    if file_path:
        pack = await asyncio.to_thread(build_shim_pack, file_path)
        payload["pack_preview"] = {
            k: v
            for k, v in pack.items()
            if k in {"ok", "shims", "command", "notes", "sandbox_ready", "binary_format"}
        }
    return payload


@router.post("/container/shim-pack", response_model=ContainerShimPackResponse, tags=["Container"])
async def container_shim_pack(request: ContainerShimPackRequest) -> ContainerShimPackResponse:
    result = await asyncio.to_thread(
        build_shim_pack,
        request.file_path,
        shim_ids=request.shim_ids,
        error_signature=request.error_signature,
        extra_env=request.extra_env,
        sandbox_image=request.sandbox_image,
        use_sudo=request.use_sudo,
    )
    return ContainerShimPackResponse(**result)


@router.post("/container/run", response_model=ContainerRunResponse, tags=["Container"])
async def container_run_endpoint(request: ContainerRunRequest) -> ContainerRunResponse:
    result = await asyncio.to_thread(
        run_shim_pack,
        request.file_path,
        shim_ids=request.shim_ids,
        error_signature=request.error_signature,
        extra_env=request.extra_env,
        sandbox_image=request.sandbox_image,
        use_sudo=request.use_sudo,
        timeout_sec=request.timeout_sec,
        extra_args=request.extra_args,
    )
    return ContainerRunResponse(**result)


@router.get("/compatibility/shadow/validation/report", tags=["Learning"])
async def shadow_validation_report() -> dict:
    """Read-only shadow validation summary and promotion gate status."""
    from alma_bridge.compatibility.profile_shadow_validation_reporter import (
        ShadowValidationReporter,
    )

    return await asyncio.to_thread(ShadowValidationReporter.generate_report)


@router.get("/compatibility/shadow/validation/gates", tags=["Learning"])
async def shadow_validation_gates() -> dict:
    """Read-only promotion gate evaluation."""
    from alma_bridge.compatibility.profile_shadow_validation_reporter import (
        ShadowValidationReporter,
    )

    report = await asyncio.to_thread(ShadowValidationReporter.generate_report)
    return report.get("promotion_gates", {})
