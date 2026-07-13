"""Fleet agent registration and job reporting."""

from __future__ import annotations

import json
import platform
import socket
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from alma_bridge.automation.runner import machine_health, run_automation
from alma_bridge.automation.sessions import _connect, init_automation_store


def register_agent(*, agent_id: Optional[str] = None, meta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    init_automation_store()
    agent_id = agent_id or str(uuid4())
    hostname = socket.gethostname()
    capabilities = {
        "machine": platform.machine(),
        "system": platform.system(),
        "python": platform.python_version(),
    }
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO automation_agents (agent_id, hostname, last_seen, capabilities, meta)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                hostname = excluded.hostname,
                last_seen = excluded.last_seen,
                capabilities = excluded.capabilities,
                meta = excluded.meta
            """,
            (agent_id, hostname, now, json.dumps(capabilities), json.dumps(meta or {})),
        )
        conn.commit()
    return {"agent_id": agent_id, "hostname": hostname, "capabilities": capabilities}


def agent_heartbeat(agent_id: str) -> Dict[str, Any]:
    init_automation_store()
    health = machine_health()
    now = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        conn.execute(
            "UPDATE automation_agents SET last_seen = ? WHERE agent_id = ?",
            (now, agent_id),
        )
        conn.commit()
    return {"agent_id": agent_id, "last_seen": now, "health": health}


def agent_run_job(
    agent_id: str,
    *,
    scan_path: Optional[str] = None,
    apply: bool = False,
    allow_mutations: bool = False,
    approval_token: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    register_agent(agent_id=agent_id)
    result = run_automation(
        scan_path=scan_path,
        apply=apply,
        allow_mutations=allow_mutations,
        approval_token=approval_token,
        **kwargs,
    )
    result["agent_id"] = agent_id
    return result
