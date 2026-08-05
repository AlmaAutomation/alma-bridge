"""Behavior-family mapping tests for Runtime Intelligence."""

from __future__ import annotations

import pytest

from alma_bridge.compatibility_intelligence.behavior_requirements import BEHAVIOR_PROFILES
from alma_bridge.compatibility_intelligence.capabilities import CAPABILITY_REGISTRY
from alma_bridge.runtime_intelligence.family import (
    BEHAVIOR_FAMILY_REGISTRY,
    CANONICAL_FAMILIES,
    FAMILY_REGISTRY,
    all_profile_behaviors_mapped,
    all_registry_capabilities_mapped,
    family_for_behavior,
    family_for_capability,
    list_families,
    list_behavior_family_mappings,
)
from alma_bridge.runtime_intelligence.models import BehaviorFamilyId


class TestCanonicalFamilies:
    def test_list_families_returns_exactly_eight(self):
        families = list_families()
        assert len(families) == 8
        assert set(families) == set(BehaviorFamilyId)

    def test_canonical_family_metadata_covers_all_families(self):
        assert set(CANONICAL_FAMILIES) == set(BehaviorFamilyId)

    def test_no_extra_top_level_families(self):
        allowed = {
            "filesystem",
            "console",
            "memory",
            "crt",
            "registry",
            "networking",
            "synchronization",
            "gui",
        }
        assert {family.value for family in BehaviorFamilyId} == allowed


class TestCapabilityFamilyMapping:
    @pytest.mark.parametrize(
        ("capability_id", "expected_family"),
        [
            ("filesystem.basic_io", BehaviorFamilyId.FILESYSTEM),
            ("console.stdout", BehaviorFamilyId.CONSOLE),
            ("console.stderr", BehaviorFamilyId.CONSOLE),
            ("process.exit", BehaviorFamilyId.CRT),
            ("process.arguments", BehaviorFamilyId.CRT),
            ("process.environment", BehaviorFamilyId.CRT),
            ("process.identity", BehaviorFamilyId.CRT),
            ("process.timing", BehaviorFamilyId.CRT),
            ("process.creation", BehaviorFamilyId.CRT),
            ("error.handling", BehaviorFamilyId.CRT),
            ("dotnet.clr", BehaviorFamilyId.CRT),
            ("registry.read", BehaviorFamilyId.REGISTRY),
            ("registry.write", BehaviorFamilyId.REGISTRY),
            ("threading.basic", BehaviorFamilyId.SYNCHRONIZATION),
            ("com.initialization", BehaviorFamilyId.SYNCHRONIZATION),
            ("gui.windowing", BehaviorFamilyId.GUI),
        ],
    )
    def test_capability_maps_to_canonical_family(self, capability_id: str, expected_family: BehaviorFamilyId):
        assert family_for_capability(capability_id) == expected_family

    def test_unknown_capability_returns_none(self):
        assert family_for_capability("api.unknown") is None
        assert family_for_capability("totally.made_up") is None

    def test_all_registry_capabilities_mapped_except_unknown(self):
        assert all_registry_capabilities_mapped()
        assert "api.unknown" not in FAMILY_REGISTRY

    def test_registry_has_no_ninth_family(self):
        assert len(set(FAMILY_REGISTRY.values())) <= 8


class TestBehaviorFamilyMapping:
    @pytest.mark.parametrize(
        ("behavior_id", "expected_family"),
        [
            ("create_always_write", BehaviorFamilyId.FILESYSTEM),
            ("sequential_read", BehaviorFamilyId.FILESYSTEM),
            ("write_stdout", BehaviorFamilyId.CONSOLE),
            ("write_stderr", BehaviorFamilyId.CONSOLE),
            ("process_exit_with_code", BehaviorFamilyId.CRT),
            ("read_environment_variable", BehaviorFamilyId.CRT),
            ("read_command_line", BehaviorFamilyId.CRT),
        ],
    )
    def test_behavior_maps_to_canonical_family(self, behavior_id: str, expected_family: BehaviorFamilyId):
        assert family_for_behavior(behavior_id) == expected_family

    def test_unknown_behavior_returns_none(self):
        assert family_for_behavior("nonexistent_behavior") is None

    def test_all_profile_behaviors_are_mapped(self):
        assert all_profile_behaviors_mapped()

    def test_behavior_mappings_reference_only_canonical_families(self):
        mappings = list_behavior_family_mappings()
        assert mappings
        assert all(mapping.family_id in BehaviorFamilyId for mapping in mappings)
        assert len(BEHAVIOR_FAMILY_REGISTRY) == len(mappings)

    def test_behavior_profiles_only_use_mapped_behaviors(self):
        for profile in BEHAVIOR_PROFILES.values():
            for behavior_id in profile.supported_behaviors + profile.unsupported_behaviors:
                assert behavior_id in BEHAVIOR_FAMILY_REGISTRY

    def test_capability_registry_keys_are_subset_of_known_capabilities(self):
        for capability_id in CAPABILITY_REGISTRY:
            if capability_id == "api.unknown":
                continue
            assert capability_id in FAMILY_REGISTRY
