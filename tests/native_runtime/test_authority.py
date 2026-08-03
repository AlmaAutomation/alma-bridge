"""Authority and boundary tests (34-38)."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NATIVE_RUNTIME = ROOT / "alma_bridge" / "native_runtime"

FORBIDDEN = (
    "verification_gateway",
    "VerificationGateway",
    "learning.orchestrator",
    "BridgeOrchestrator",
    "session.mutations",
)


def _forbidden_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for frag in FORBIDDEN:
                if frag in node.module:
                    hits.append(f"{path.relative_to(ROOT)}:{frag}")
        if isinstance(node, ast.Import):
            for alias in node.names:
                for frag in FORBIDDEN:
                    if frag in alias.name:
                        hits.append(f"{path.relative_to(ROOT)}:{frag}")
    return hits


class TestAuthorityBoundaries:
    def test_34_native_runtime_no_verification_gateway(self):
        offenders: list[str] = []
        for path in sorted(NATIVE_RUNTIME.rglob("*.py")):
            offenders.extend(_forbidden_imports(path))
        assert offenders == []

    def test_35_provider_no_verification_gateway(self):
        path = ROOT / "alma_bridge" / "runtime" / "providers" / "native_alma.py"
        assert _forbidden_imports(path) == []

    def test_36_inspect_read_only_no_launch(self, tmp_path):
        from alma_bridge.native_runtime.eligibility import inspect_pe

        pe = tmp_path / "hello64.exe"
        pe.write_bytes(b"MZ" + b"\x00" * 126)
        # invalid pe still inspect-only
        result = inspect_pe(pe)
        assert result.eligible is False

    def test_37_runtime_routes_no_orchestrator(self):
        import alma_bridge.api.runtime_routes as mod

        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "orchestrator" not in src.lower()

    def test_38_flags_default_disabled(self):
        from alma_bridge.config import settings

        assert settings.native_runtime_enabled is False
        assert settings.allow_experimental_runtimes is False
