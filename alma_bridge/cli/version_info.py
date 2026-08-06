"""Version and build metadata for the Alma CLI."""

from __future__ import annotations

import platform
import sys
from importlib.metadata import PackageNotFoundError, version as pkg_version
from typing import Any, Dict

from alma_bridge.compatibility_intelligence.service import CompatibilityIntelligenceService
from alma_bridge.runtime.registry import build_default_registry
from alma_bridge.runtime_intelligence.models import RUNTIME_INTELLIGENCE_SCHEMA_VERSION
from alma_bridge.session.services.verification import VERIFIER_VERSION


def get_version_info() -> Dict[str, Any]:
    try:
        package_version = pkg_version("alma-bridge")
    except PackageNotFoundError:
        package_version = "0.1.0"
    providers = {
        entry.provider_id: entry.provider_version
        for entry in build_default_registry().inventory()
    }
    return {
        "cli": "alma",
        "package": "alma-bridge",
        "version": package_version,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "compatibility_intelligence_engine": CompatibilityIntelligenceService.ENGINE_VERSION,
        "runtime_intelligence_schema": RUNTIME_INTELLIGENCE_SCHEMA_VERSION,
        "verification_engine_version": VERIFIER_VERSION,
        "providers": providers,
    }
