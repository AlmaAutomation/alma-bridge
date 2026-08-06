"""Engineering Roadmap Generator — read-only composition over existing planning evidence."""

from alma_bridge.engineering_roadmap.clustering import (
    BLOCKER_CLUSTER_REGISTRY,
    BLOCKER_CLUSTER_REGISTRY_VERSION,
    BlockerClusterRegistryError,
    cluster_blockers,
    compute_cluster_digest,
    compute_clustering_report_digest,
    compute_unclustered_digest,
    parse_blocker,
)
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
    BlockerClusterClassification,
    BlockerClusterSpec,
    BlockerClusteringResult,
    ENGINEERING_ROADMAP_ENGINE_VERSION,
    ENGINEERING_ROADMAP_FORMULA_VERSION,
    ENGINEERING_ROADMAP_SCHEMA_VERSION,
    PREDICTED_UNLOCK_DISCLAIMER_TEMPLATE,
    EngineeringConfidenceLevel,
    EngineeringRoadmapOpportunity,
    EngineeringRoadmapReport,
    ProvisionalBlockerCluster,
    RoadmapOpportunityStatus,
    UnclusteredBlocker,
)

__all__ = [
    "BLOCKER_CLUSTER_REGISTRY",
    "BLOCKER_CLUSTER_REGISTRY_VERSION",
    "BlockerClusterClassification",
    "BlockerClusterRegistryError",
    "BlockerClusterSpec",
    "BlockerClusteringResult",
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
    "ProvisionalBlockerCluster",
    "UnclusteredBlocker",
    "cluster_blockers",
    "compute_cluster_digest",
    "compute_clustering_report_digest",
    "compute_unclustered_digest",
    "compute_opportunity_digest",
    "compute_opportunity_id",
    "compute_report_digest",
    "parse_blocker",
]
