"""Automated compatibility bridge domain layer (Phase A)."""

from alma_bridge.bridge.gap_analyzer import analyze_compatibility_gaps, build_wine_environment_profile
from alma_bridge.bridge.profile_builder import (
    build_compatibility_inspection,
    build_host_capability_profile,
    build_program_profile,
    compute_host_fingerprint,
    compute_program_fingerprint,
)

__all__ = [
    "analyze_compatibility_gaps",
    "build_compatibility_inspection",
    "build_host_capability_profile",
    "build_program_profile",
    "build_wine_environment_profile",
    "compute_host_fingerprint",
    "compute_program_fingerprint",
]
