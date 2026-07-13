from __future__ import annotations

from alma_bridge.learning.remediation import next_launcher_remediation


def test_next_launcher_remediation_prefers_signature_specific_fix():
    tried = set()
    first = next_launcher_remediation("sidecar_silent_crash", tried)
    assert first and first["id"] == "sidecar_silent_crash_refresh"
    tried.add(first["id"])
    second = next_launcher_remediation("sidecar_silent_crash", tried)
    assert second and second["id"] != "sidecar_silent_crash_refresh"
