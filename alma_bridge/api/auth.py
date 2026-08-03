"""Optional API key gate for high-risk Alma Bridge mutations."""

from __future__ import annotations

import hmac
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from alma_bridge.config import settings

MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Mutations that change the host, run sudo, or start listeners require a key when configured.
PROTECTED_PREFIXES = (
    "/bridge/run",
    "/modernization/apply",
    "/modernization/windows/apply",
    "/automation/run",
    "/automation/approve",
    "/automation/agent/",
    "/container/run",
    "/import/",
    "/train/ranker",
    "/datasets/export",
    "/compliance/tls/bridge",
    "/compliance/autopilot/run",
    "/compliance/program/data",
    "/operator/tick",
    "/operator/remediate",
    "/operator/start",
    "/operator/stop",
    "/bridge/compatibility/governance/",
    "/bridge/native-lab/",
)


def _extract_api_key(request: Request) -> str | None:
    header = request.headers.get("X-API-Key")
    if header:
        return header.strip()
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return None


def _requires_api_key(request: Request) -> bool:
    if request.method not in MUTATION_METHODS:
        return False
    path = request.url.path
    return any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)


def _keys_match(provided: str | None, expected: str) -> bool:
    if not provided:
        return False
    return hmac.compare_digest(provided, expected)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        expected = (settings.api_key or "").strip()
        if not expected or not _requires_api_key(request):
            return await call_next(request)

        provided = _extract_api_key(request)
        if not _keys_match(provided, expected):
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "Valid API key required (X-API-Key or Authorization: Bearer)",
                },
            )
        return await call_next(request)
