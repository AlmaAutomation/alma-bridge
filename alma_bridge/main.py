from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alma_bridge.api.routes import router
from alma_bridge.api.auth import ApiKeyMiddleware
from alma_bridge.automation import init_automation_store
from alma_bridge.config import settings
from alma_bridge.storage.outcomes import init_outcome_store


@asynccontextmanager
async def _lifespan(app: FastAPI):
    if settings.operator_enabled:
        from alma_bridge.operator import operator_loop

        # When mutations are permitted, the autonomous loop applies within its
        # risk budget; otherwise it runs plan-only.
        operator_loop.start(apply=settings.operator_allow_mutations)
    yield
    # Stop the autonomous operator loop, then tear down TLS bridges.
    from alma_bridge.operator import operator_loop

    await operator_loop.stop()

    from alma_bridge.api.routes import tls_modernizer

    await tls_modernizer.stop_all()


def create_app() -> FastAPI:
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    init_outcome_store()
    init_automation_store()

    # Cap total concurrent network operations so heavy/overlapping compliance
    # scans never exhaust file descriptors or CPU on low-end hardware.
    from alma_bridge.compliance._perf import MAX_WORKER_CAP, set_network_concurrency
    from alma_bridge.compliance.learning import init_healing_store

    set_network_concurrency(settings.compliance_max_workers or MAX_WORKER_CAP)
    init_healing_store()

    app = FastAPI(
        title="Alma Lab Platform",
        description=(
            "Flagship: Alma Lab Modernization Program — assess, plan, apply, and verify "
            "K-12 computer labs without a hardware refresh. Includes Bridge execution engine."
        ),
        version="0.1.0",
        lifespan=_lifespan,
        openapi_tags=[
            {"name": "System", "description": "Health, metrics, and service metadata."},
            {"name": "Hardware", "description": "Host hardware profiling and shim recommendations."},
            {"name": "Bridge", "description": "Adaptive binary execution and session history."},
            {"name": "Intelligence", "description": "Read-only compatibility intelligence assessments."},
            {"name": "Graph", "description": "Read-only compatibility graph knowledge representation."},
            {"name": "Knowledge", "description": "Read-only compatibility knowledge aggregation."},
            {"name": "Learning", "description": "Outcome statistics and strategy learning."},
            {"name": "Import", "description": "Import legacy scan and resolve datasets."},
            {"name": "Training", "description": "Ranker training and dataset export."},
            {"name": "Compliance", "description": "TLS, DNS, drivers, autopilot, and unified scans."},
            {"name": "Modernization", "description": "Linux and Windows host modernization playbooks."},
            {"name": "Automation", "description": "Unified scan → assess → apply → verify automation spine."},
            {"name": "Operator", "description": "Autonomous AI operator: observes systems + ML and applies modernization/self-healing."},
            {"name": "Container", "description": "Sandbox status and container shim pack execution."},
        ],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:9002",
            "http://localhost:9002",
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:3001",
            "http://localhost:3001",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(ApiKeyMiddleware)
    app.include_router(router)
    return app


app = create_app()


def main() -> None:
    import uvicorn

    uvicorn.run(
        "alma_bridge.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )


if __name__ == "__main__":
    main()
