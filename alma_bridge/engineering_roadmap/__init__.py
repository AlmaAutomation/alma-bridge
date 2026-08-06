"""Engineering Roadmap Generator — read-only composition over existing planning evidence."""

from alma_bridge.engineering_roadmap.digest import (
    compute_opportunity_digest,
    compute_opportunity_id,
    compute_report_digest,
)
from alma_bridge.engineering_roadmap.errors import (
    EngineeringRoadmapError,
    InsufficientEvidenceError,
    OpportunityNotFoundError,
)
from alma_bridge.engineering_roadmap.models import (
    ENGINEERING_ROADMAP_ENGINE_VERSION,
    ENGINEERING_ROADMAP_FORMULA_VERSION,
    ENGINEERING_ROADMAP_SCHEMA_VERSION,
    PREDICTED_UNLOCK_DISCLAIMER_TEMPLATE,
    EngineeringConfidenceLevel,
    EngineeringRoadmapOpportunity,
    EngineeringRoadmapReport,
    RoadmapOpportunityStatus,
)

__all__ = [
    "ENGINEERING_ROADMAP_ENGINE_VERSION",
    "ENGINEERING_ROADMAP_FORMULA_VERSION",
    "ENGINEERING_ROADMAP_SCHEMA_VERSION",
    "PREDICTED_UNLOCK_DISCLAIMER_TEMPLATE",
    "EngineeringConfidenceLevel",
    "EngineeringRoadmapError",
    "EngineeringRoadmapOpportunity",
    "EngineeringRoadmapReport",
    "InsufficientEvidenceError",
    "OpportunityNotFoundError",
    "RoadmapOpportunityStatus",
    "compute_opportunity_digest",
    "compute_opportunity_id",
    "compute_report_digest",
]
