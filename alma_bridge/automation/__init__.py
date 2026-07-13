"""Alma automation platform — unified scan → modernize → run → verify → learn."""

from alma_bridge.automation.agent import agent_heartbeat, agent_run_job, register_agent
from alma_bridge.automation.approval import create_approval_token
from alma_bridge.automation.playbooks import list_playbooks
from alma_bridge.automation.runner import (
    machine_health,
    request_approval,
    run_automation,
)
from alma_bridge.automation.sessions import (
    get_automation_session,
    init_automation_store,
    list_automation_sessions,
)

__all__ = [
    "init_automation_store",
    "machine_health",
    "run_automation",
    "request_approval",
    "list_playbooks",
    "list_automation_sessions",
    "get_automation_session",
    "register_agent",
    "agent_heartbeat",
    "agent_run_job",
    "create_approval_token",
]
