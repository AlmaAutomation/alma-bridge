"""Append-only versioned capability maturity registry persistence."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from alma_bridge.compatibility.profile_fingerprints import sha256_v1
from alma_bridge.compatibility_intelligence.behavior_requirements import (
    get_behavior_profile,
    list_behavior_profiles,
)
from alma_bridge.compatibility_intelligence.capabilities import (
    CAPABILITY_REGISTRY,
    PROVIDER_IDS,
)
from alma_bridge.compatibility_intelligence.models import ImplementationStatus
from alma_bridge.config import settings

from alma_bridge.compatibility_intelligence.governance.models import (
    ACI_GOVERNANCE_SCHEMA_VERSION,
    CapabilityMaturityEntry,
    CapabilityMaturityState,
    CapabilityScope,
    GOVERNANCE_REGISTRY_SEED_VERSION,
    RegistryVersion,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _implementation_status_to_maturity(status: ImplementationStatus) -> CapabilityMaturityState:
    if status == ImplementationStatus.SUPPORTED:
        return CapabilityMaturityState.EXPERIMENTAL
    if status == ImplementationStatus.PARTIAL:
        return CapabilityMaturityState.DECLARED
    if status == ImplementationStatus.EXPERIMENTAL:
        return CapabilityMaturityState.EXPERIMENTAL
    if status == ImplementationStatus.UNSUPPORTED:
        return CapabilityMaturityState.DECLARED
    if status == ImplementationStatus.DELEGATED:
        return CapabilityMaturityState.DECLARED
    return CapabilityMaturityState.DECLARED


def seed_registry_entries() -> List[CapabilityMaturityEntry]:
    """Build initial maturity entries from static capability and behavior profiles."""
    entries: List[CapabilityMaturityEntry] = []
    seen: set[str] = set()

    for cap in CAPABILITY_REGISTRY.values():
        for provider_id in PROVIDER_IDS:
            if provider_id == "container":
                continue
            status = (
                cap.native
                if provider_id == "native_alma"
                else cap.wine
                if provider_id == "wine"
                else cap.proton
            )
            profile = get_behavior_profile(cap.capability_id, provider_id)
            scope = CapabilityScope(
                provider_id=provider_id,
                provider_version=profile.implementation_version if profile else "",
                capability_id=cap.capability_id,
                behavior_profile=profile.supported_behaviors if profile else [],
                implementation_version=profile.implementation_version if profile else "",
            )
            key = scope.scope_key()
            if key in seen:
                continue
            seen.add(key)
            entries.append(
                CapabilityMaturityEntry(
                    scope=scope,
                    maturity_state=_implementation_status_to_maturity(status),
                    limitations=list(profile.limitations) if profile else [],
                    evidence_references=list(profile.evidence_references) if profile else [],
                    supported_behaviors=list(profile.supported_behaviors) if profile else [],
                    unsupported_behaviors=list(profile.unsupported_behaviors) if profile else [],
                )
            )

    for profile in list_behavior_profiles():
        scope = CapabilityScope(
            provider_id=profile.provider_id,
            provider_version=profile.implementation_version,
            capability_id=profile.capability_id,
            behavior_profile=list(profile.supported_behaviors),
            implementation_version=profile.implementation_version,
        )
        key = scope.scope_key()
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            CapabilityMaturityEntry(
                scope=scope,
                maturity_state=CapabilityMaturityState.EXPERIMENTAL,
                limitations=list(profile.limitations),
                evidence_references=list(profile.evidence_references),
                supported_behaviors=list(profile.supported_behaviors),
                unsupported_behaviors=list(profile.unsupported_behaviors),
            )
        )

    return sorted(entries, key=lambda e: e.scope.scope_key())


def compute_registry_digest(entries: List[CapabilityMaturityEntry]) -> str:
    payload = {
        "schema": ACI_GOVERNANCE_SCHEMA_VERSION,
        "entries": [e.model_dump(mode="json") for e in entries],
    }
    return sha256_v1(payload)


class GovernanceRepository:
    """File-backed append-only versioned capability maturity registry."""

    ENGINE_VERSION = "aci_governance_repository_v1"

    def __init__(self, store_dir: Optional[Path] = None) -> None:
        base = store_dir or (settings.data_dir / "compatibility_intelligence" / "governance")
        self._base = base
        self._registry_dir = base / "registry" / "versions"
        self._proposals_dir = base / "proposals"
        self._reviews_dir = base / "reviews"
        self._current_path = base / "registry" / "current.json"
        self._version_cache: Dict[str, RegistryVersion] = {}

    def _ensure_dirs(self) -> None:
        self._registry_dir.mkdir(parents=True, exist_ok=True)
        self._proposals_dir.mkdir(parents=True, exist_ok=True)
        self._reviews_dir.mkdir(parents=True, exist_ok=True)

    def get_current_version_id(self) -> str:
        version = self.get_current_version()
        return version.version_id

    def get_current_version(self) -> RegistryVersion:
        self._ensure_dirs()
        if self._current_path.is_file():
            data = json.loads(self._current_path.read_text(encoding="utf-8"))
            return self.get_version(str(data["version_id"]))

        seed = self._create_seed_version()
        return seed

    def get_version(self, version_id: str) -> RegistryVersion:
        if version_id in self._version_cache:
            return self._version_cache[version_id]
        path = self._registry_dir / f"{version_id}.json"
        if not path.is_file():
            raise FileNotFoundError(f"Registry version not found: {version_id}")
        version = RegistryVersion.model_validate_json(path.read_text(encoding="utf-8"))
        self._version_cache[version_id] = version
        return version

    def list_versions(self) -> List[RegistryVersion]:
        self._ensure_dirs()
        if not self._current_path.is_file():
            self._create_seed_version()
        versions: List[RegistryVersion] = []
        for path in sorted(self._registry_dir.glob("*.json")):
            try:
                versions.append(
                    RegistryVersion.model_validate_json(path.read_text(encoding="utf-8"))
                )
            except (json.JSONDecodeError, ValueError):
                continue
        return sorted(versions, key=lambda v: v.created_at)

    def _create_seed_version(self) -> RegistryVersion:
        entries = seed_registry_entries()
        ts = _utc_now_iso()
        digest = compute_registry_digest(entries)
        version = RegistryVersion(
            version_id=GOVERNANCE_REGISTRY_SEED_VERSION,
            parent_version_id=None,
            created_at=ts,
            digest=digest,
            entries=entries,
            change_summary="Initial seed from static capability and behavior profiles",
        )
        self._persist_version(version, set_current=True)
        return version

    def _persist_version(self, version: RegistryVersion, *, set_current: bool) -> None:
        self._ensure_dirs()
        path = self._registry_dir / f"{version.version_id}.json"
        if path.is_file():
            existing = RegistryVersion.model_validate_json(path.read_text(encoding="utf-8"))
            if existing.digest != version.digest:
                raise ValueError(
                    f"Registry version {version.version_id} already exists with different digest"
                )
            return
        path.write_text(version.model_dump_json(indent=2), encoding="utf-8")
        self._version_cache[version.version_id] = version
        if set_current:
            self._current_path.write_text(
                json.dumps({"version_id": version.version_id}, indent=2),
                encoding="utf-8",
            )

    def append_version(
        self,
        entries: List[CapabilityMaturityEntry],
        *,
        parent_version_id: str,
        change_summary: str,
    ) -> RegistryVersion:
        """Create a new append-only registry version."""
        self.get_version(parent_version_id)
        ts = _utc_now_iso()
        digest = compute_registry_digest(entries)
        version_id = sha256_v1(
            {
                "parent": parent_version_id,
                "digest": digest,
                "created_at": ts,
            }
        )[:16]
        version = RegistryVersion(
            version_id=f"aci_governance_registry_{version_id}",
            parent_version_id=parent_version_id,
            created_at=ts,
            digest=digest,
            entries=entries,
            change_summary=change_summary,
        )
        self._persist_version(version, set_current=True)
        return version

    def find_maturity(
        self,
        scope: CapabilityScope,
        *,
        version_id: Optional[str] = None,
    ) -> Optional[CapabilityMaturityEntry]:
        version = self.get_version(version_id) if version_id else self.get_current_version()
        exact = scope.scope_key()
        for entry in version.entries:
            if entry.scope.scope_key() == exact:
                return entry
        for entry in version.entries:
            if (
                entry.scope.provider_id == scope.provider_id
                and entry.scope.capability_id == scope.capability_id
                and not entry.scope.application_scope
                and not scope.application_scope
            ):
                return entry
        return None

    def get_maturity_state(
        self,
        provider_id: str,
        capability_id: str,
        *,
        version_id: Optional[str] = None,
        application_scope: Optional[List[str]] = None,
    ) -> CapabilityMaturityState:
        scope = CapabilityScope(
            provider_id=provider_id,
            capability_id=capability_id,
            application_scope=application_scope or [],
        )
        entry = self.find_maturity(scope, version_id=version_id)
        if entry is None:
            return CapabilityMaturityState.DECLARED
        return entry.maturity_state

    def save_proposal(self, proposal: dict) -> dict:
        self._ensure_dirs()
        path = self._proposals_dir / f"{proposal['proposal_id']}.json"
        path.write_text(json.dumps(proposal, indent=2, sort_keys=True), encoding="utf-8")
        return proposal

    def get_proposal(self, proposal_id: str) -> Optional[dict]:
        path = self._proposals_dir / f"{proposal_id}.json"
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
        return None

    def list_proposals(self, limit: int = 100) -> List[dict]:
        self._ensure_dirs()
        results: List[dict] = []
        files = sorted(
            self._proposals_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for path in files[:limit]:
            try:
                results.append(json.loads(path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
        return results

    def save_review(self, review: dict) -> dict:
        self._ensure_dirs()
        path = self._reviews_dir / f"{review['review_id']}.json"
        path.write_text(json.dumps(review, indent=2, sort_keys=True), encoding="utf-8")
        return review

    def list_reviews_for_proposal(self, proposal_id: str) -> List[dict]:
        self._ensure_dirs()
        results: List[dict] = []
        for path in self._reviews_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("proposal_id") == proposal_id:
                    results.append(data)
            except json.JSONDecodeError:
                continue
        return sorted(results, key=lambda r: r.get("created_at", ""), reverse=True)
