"""API classification tests."""

from __future__ import annotations

from alma_bridge.compatibility_intelligence.apis import classify_import, lookup_api
from alma_bridge.compatibility_intelligence.models import ImplementationStatus


class TestApiClassification:
    def test_known_kernel32_writefile(self):
        entry = lookup_api("kernel32.dll", "WriteFile")
        assert entry is not None
        assert entry.capability_id == "console.stdout"

    def test_unknown_api_marked_unknown(self):
        result = classify_import("kernel32.dll", "TotallyFakeApi")
        assert result.is_known is False
        assert result.capability_id == "api.unknown"
        assert result.native_status == ImplementationStatus.UNKNOWN
        assert result.wine_status == ImplementationStatus.UNKNOWN

    def test_ordinal_import_unknown(self):
        result = classify_import("kernel32.dll", "ordinal_42")
        assert result.is_known is False

    def test_gui_api_native_unsupported_wine_supported(self):
        result = classify_import("user32.dll", "CreateWindowExW")
        assert result.is_known is True
        assert result.capability_id == "gui.windowing"
        assert result.native_status == ImplementationStatus.UNSUPPORTED
        assert result.wine_status == ImplementationStatus.SUPPORTED

    def test_registry_api_partial_wine(self):
        result = classify_import("advapi32.dll", "RegOpenKeyExW")
        assert result.capability_id == "registry.read"
        assert result.wine_status == ImplementationStatus.PARTIAL

    def test_never_guess_unknown_as_supported(self):
        result = classify_import("unknown.dll", "MysteryFunction")
        assert result.native_status != ImplementationStatus.SUPPORTED
        assert result.wine_status != ImplementationStatus.SUPPORTED
