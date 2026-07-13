"""Alma flagship program — Lab Modernization (K-12)."""

from __future__ import annotations

from typing import Any, Dict, List

FLAGSHIP_PROGRAM_ID = "alma-lab-modernization"

FLAGSHIP_PROGRAM: Dict[str, Any] = {
    "id": FLAGSHIP_PROGRAM_ID,
    "name": "Alma Lab Modernization Program",
    "edition": "District",
    "tagline": "Extend lab PC life 2–3 years without a hardware refresh.",
    "console_title": "Program Console",
    "audience": "K-12 district IT, regional cooperatives, lab technicians",
    "workflow": ["assess", "plan", "apply", "verify", "report"],
    "trust_signals": [
        "FERPA-ready documentation",
        "On-premise data",
        "Audit trail export",
        "Air-gap USB lab kit",
    ],
    "default_recipes": {
        "linux_lab": "school-lab",
        "windows_lab": "school-lab-windows",
        "air_gap": "school-lab",
    },
    "deliverables": [
        "AI Operator — autonomously observes systems + ML and applies fixes",
        "Lab readiness score (before/after)",
        "Automation playbook (Linux or Windows PowerShell)",
        "Classroom Browser shortcut for students",
        "JSON audit export for IT tickets",
        "Optional air-gap USB lab kit",
        "Commercial compliance pack (FERPA DPA, privacy, SLA, third-party notices)",
    ],
    "operator_api": "/operator/status",
    "compliance_api": "/compliance/program",
    "ui_paths": {
        "console": "/app/compliance",
        "alias": "/app/lab",
        "windows_ps1": "/modernization/windows/export.ps1",
    },
    "docs": {
        "deployment": "docs/k12-lab-deployment.md",
        "pricing": "docs/pilot-pricing-sheet.md",
        "lab_kit": "docs/lab-kit.md",
    },
}

FLAGSHIP_RECIPE_IDS = frozenset({"school-lab", "school-lab-windows"})


def is_flagship_recipe(recipe_id: str) -> bool:
    return recipe_id in FLAGSHIP_RECIPE_IDS


def flagship_summary() -> Dict[str, Any]:
    return dict(FLAGSHIP_PROGRAM)
