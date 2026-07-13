"""Validation-campaign prefix guards (operational only, not global production policy)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from alma_bridge.config import settings
from alma_bridge.schemas.models import BridgeRequest


class CampaignPrefixRejected(Exception):
    """Raised when a campaign-mode Bridge run targets a forbidden prefix."""

    def __init__(self, reason_code: str, detail: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"{reason_code}: {detail}")


@dataclass(frozen=True)
class CampaignGuardConfig:
    campaign_id: str
    disposable_root: Path
    primary_prefix: Optional[Path] = None
    source_snapshot: Optional[Path] = None

    @classmethod
    def from_settings(cls) -> Optional["CampaignGuardConfig"]:
        if not settings.validation_campaign_mode:
            return None
        root = settings.validation_campaign_disposable_root
        if not root:
            return None
        return cls(
            campaign_id=settings.validation_campaign_id or "unknown",
            disposable_root=Path(root).expanduser().resolve(),
            primary_prefix=_resolve_optional(settings.validation_campaign_primary_prefix),
            source_snapshot=_resolve_optional(settings.validation_campaign_source_snapshot),
        )


def _resolve_optional(path: Optional[str]) -> Optional[Path]:
    if not path:
        return None
    return Path(path).expanduser().resolve()


def _realpath(path: Path) -> Path:
    return Path(os.path.realpath(path))


def _is_within(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def requires_wine_prefix(request: BridgeRequest) -> bool:
    if request.wine_prefix:
        return True
    if request.runtime_hint and str(request.runtime_hint) in {"wine", "proton"}:
        return True
    suffix = Path(request.file_path).suffix.lower()
    return suffix in {".exe", ".msi"}


def validate_campaign_bridge_request(request: BridgeRequest) -> None:
    """Reject campaign runs that target protected or out-of-scope Wine prefixes."""
    config = CampaignGuardConfig.from_settings()
    if config is None:
        return
    if not requires_wine_prefix(request):
        return
    if not request.wine_prefix:
        raise CampaignPrefixRejected(
            "CAMPAIGN_WINE_PREFIX_REQUIRED",
            "Campaign mode requires an explicit disposable wine_prefix for Wine/Proton targets.",
        )
    prefix = _realpath(Path(request.wine_prefix).expanduser())
    if not prefix.exists():
        raise CampaignPrefixRejected(
            "CAMPAIGN_PREFIX_MISSING",
            f"Disposable prefix does not exist: {prefix}",
        )
    if config.primary_prefix and (
        prefix == config.primary_prefix or _is_within(prefix, config.primary_prefix)
    ):
        raise CampaignPrefixRejected(
            "CAMPAIGN_PRIMARY_PREFIX_FORBIDDEN",
            f"Campaign mode forbids primary prefix: {prefix}",
        )
    if config.source_snapshot and (
        prefix == config.source_snapshot or _is_within(prefix, config.source_snapshot)
    ):
        raise CampaignPrefixRejected(
            "CAMPAIGN_SOURCE_SNAPSHOT_FORBIDDEN",
            f"Campaign mode forbids source snapshot prefix: {prefix}",
        )
    if not _is_within(prefix, config.disposable_root):
        raise CampaignPrefixRejected(
            "CAMPAIGN_PREFIX_OUTSIDE_ROOT",
            f"Prefix {prefix} is outside disposable root {config.disposable_root}",
        )
    # Symlink escape: realpath must remain under disposable root.
    if not _is_within(prefix, config.disposable_root):
        raise CampaignPrefixRejected(
            "CAMPAIGN_PREFIX_SYMLINK_ESCAPE",
            f"Prefix realpath escaped disposable root: {prefix}",
        )


def disposable_prefix_initial_hash(prefix: Path) -> Optional[str]:
    """Aggregate sha256 of prefix tree for campaign evidence (best-effort)."""
    import hashlib

    if not prefix.exists():
        return None
    digest = hashlib.sha256()
    for path in sorted(prefix.rglob("*")):
        if path.is_file():
            rel = str(path.relative_to(prefix)).encode("utf-8")
            digest.update(rel)
            digest.update(path.read_bytes())
    return digest.hexdigest()
