"""Windows host modernization — assess, playbook, apply (PowerShell)."""

from alma_bridge.compliance.modernization.windows.apply import (
    apply_windows_playbook,
    export_playbook_script,
    is_windows_host,
)
from alma_bridge.compliance.modernization.windows.assess import assess_windows_host
from alma_bridge.compliance.modernization.windows.playbook import build_windows_playbook

__all__ = [
    "assess_windows_host",
    "build_windows_playbook",
    "apply_windows_playbook",
    "export_playbook_script",
    "is_windows_host",
]
