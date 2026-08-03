"""Link native_engineering specs and ACI behavior profiles for certification."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Set

from alma_bridge.compatibility_intelligence.behavior_requirements import (
    get_behavior_profile,
    list_behavior_profiles,
)
from alma_bridge.native_engineering.behavior_suites import get_behavior_suite
from alma_bridge.native_engineering.models import NATIVE_PROVIDER_ID
from alma_bridge.native_engineering.specifications import API_CAPABILITY_MAP, get_specification


@dataclass
class BehaviorTarget:
    capability_id: str
    behavior_id: str
    api_symbols: List[str] = field(default_factory=list)
    supported: bool = True
    limitations: List[str] = field(default_factory=list)
    verified_scenarios: List[str] = field(default_factory=list)
    evidence_references: List[str] = field(default_factory=list)


def _apis_for_behavior(behavior_id: str) -> List[str]:
    apis: List[str] = []
    for sym, (cap_id, behaviors) in API_CAPABILITY_MAP.items():
        spec = get_specification(sym)
        all_behaviors = spec.supported_behaviors + spec.unsupported_behaviors
        if behavior_id in all_behaviors or behavior_id in behaviors:
            apis.append(sym)
    return sorted(set(apis))


def list_behavior_targets(provider_id: str = NATIVE_PROVIDER_ID) -> List[BehaviorTarget]:
    """All behavior certification targets from ACI profiles + engineering specs."""
    seen: Set[tuple[str, str]] = set()
    targets: List[BehaviorTarget] = []

    for profile in list_behavior_profiles(provider_id):
        for behavior_id in profile.supported_behaviors:
            key = (profile.capability_id, behavior_id)
            if key in seen:
                continue
            seen.add(key)
            targets.append(
                BehaviorTarget(
                    capability_id=profile.capability_id,
                    behavior_id=behavior_id,
                    api_symbols=_apis_for_behavior(behavior_id),
                    supported=True,
                    limitations=list(profile.limitations),
                    verified_scenarios=list(profile.verified_scenarios),
                    evidence_references=list(profile.evidence_references),
                )
            )
        for behavior_id in profile.unsupported_behaviors:
            key = (profile.capability_id, behavior_id)
            if key in seen:
                continue
            seen.add(key)
            targets.append(
                BehaviorTarget(
                    capability_id=profile.capability_id,
                    behavior_id=behavior_id,
                    api_symbols=_apis_for_behavior(behavior_id),
                    supported=False,
                    limitations=list(profile.limitations),
                    verified_scenarios=list(profile.verified_scenarios),
                    evidence_references=list(profile.evidence_references),
                )
            )

    for sym in API_CAPABILITY_MAP:
        cap_id, behavior_ids = API_CAPABILITY_MAP[sym]
        spec = get_specification(sym)
        for behavior_id in spec.supported_behaviors + spec.unsupported_behaviors:
            key = (cap_id, behavior_id)
            if key in seen:
                continue
            seen.add(key)
            supported = behavior_id in spec.supported_behaviors
            targets.append(
                BehaviorTarget(
                    capability_id=cap_id,
                    behavior_id=behavior_id,
                    api_symbols=_apis_for_behavior(behavior_id),
                    supported=supported,
                    limitations=list(spec.limitations),
                )
            )

    return sorted(targets, key=lambda t: (t.capability_id, t.behavior_id))


def get_behavior_target(
    capability_id: str,
    behavior_id: str,
    provider_id: str = NATIVE_PROVIDER_ID,
) -> Optional[BehaviorTarget]:
    for target in list_behavior_targets(provider_id):
        if target.capability_id == capability_id and target.behavior_id == behavior_id:
            return target
    return None


def suite_cases_for_behavior(api_symbols: List[str], behavior_id: str) -> dict:
    """Collect behavior suite cases matching a behavior across APIs."""
    case_ids: List[str] = []
    fixture_paths: List[str] = []
    suite_id = ""
    for sym in api_symbols:
        suite = get_behavior_suite(sym)
        if not suite_id:
            suite_id = suite.suite_id
        for case in suite.cases:
            if case.behavior_id == behavior_id:
                case_ids.append(case.case_id)
                if case.fixture_path:
                    fixture_paths.append(case.fixture_path)
    return {
        "suite_id": suite_id,
        "case_ids": sorted(set(case_ids)),
        "fixture_paths": sorted(set(fixture_paths)),
    }
