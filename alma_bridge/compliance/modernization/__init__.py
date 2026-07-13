"""Legacy host modernization — assess, plan, apply, browser enablement."""

from alma_bridge.compliance.modernization.assess import assess_host
from alma_bridge.compliance.modernization.apply import apply_playbook_steps, apply_pathway_steps
from alma_bridge.compliance.modernization.browser import assess_browsers, recommend_browser
from alma_bridge.compliance.modernization.playbook import build_modernization_playbook

__all__ = [
    "assess_host",
    "assess_browsers",
    "recommend_browser",
    "build_modernization_playbook",
    "apply_playbook_steps",
    "apply_pathway_steps",
]
