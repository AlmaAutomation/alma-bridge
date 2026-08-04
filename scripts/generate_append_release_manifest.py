#!/usr/bin/env python3
"""Generate deterministic release manifest for native-alma append cycle v1."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from alma_bridge.config import PROJECT_ROOT
from alma_bridge.native_lab.bootstrap_append_cycle import build_completed_append_work_item
from alma_bridge.native_lab.evidence_resolution import build_evidence_manifest

RELEASE_ID = "native-alma-append-cycle-v1"
OUT = PROJECT_ROOT / "data" / "releases" / f"{RELEASE_ID}.json"


def main() -> None:
    item = build_completed_append_work_item()
    manifest = build_evidence_manifest(item)
    fixture_manifest = json.loads(
        (PROJECT_ROOT / "tests/fixtures/native_runtime/manifest.json").read_text()
    )
    body = {
        "release_id": RELEASE_ID,
        "work_item_id": item.work_item_id,
        "provider_id": item.provider_id,
        "capability_id": item.capability_id,
        "behavior_id": item.behavior_id,
        "implementation_version": "0.2.1-m2",
        "engineering_complete": True,
        "governance_disposition": item.governance_disposition.value,
        "status": item.status.value,
        "acceptance_criteria_count": len(item.acceptance_criteria),
        "evidence_reference_count": len(item.evidence_references),
        "evidence_manifest_digest": manifest.manifest_digest,
        "work_item_digest": item.work_item_digest,
        "fixture_count": len(fixture_manifest.get("fixtures", {})),
        "scope": item.bounded_scope,
    }
    integrity = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    payload = {**body, "integrity_digest": integrity}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"integrity_digest={integrity}")


if __name__ == "__main__":
    main()
