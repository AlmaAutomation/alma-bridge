"""Tests for the 32-bit legacy readiness assessor and enablement planner."""

from __future__ import annotations

from alma_bridge.compliance import legacy32


def test_assess_returns_structure():
    result = legacy32.assess_32bit_support()
    assert set(result) >= {"ready", "verdict", "capabilities", "gaps", "notes"}
    assert result["verdict"] in {"ready", "needs_enablement"}
    assert "cpu_machine" in result["capabilities"]


def test_assess_64bit_missing_everything(tmp_path, monkeypatch):
    # Empty fake root => no loader, no i386 libs, multiarch off.
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    monkeypatch.setattr(legacy32, "_foreign_architectures", lambda: [])
    result = legacy32.assess_32bit_support(root=str(tmp_path))
    assert result["ready"] is False
    assert "missing_elf32_loader" in result["gaps"]
    assert "missing_core_i386_libs" in result["gaps"]
    assert "multiarch_disabled" in result["gaps"]


def test_assess_native_32bit_is_ready(monkeypatch):
    monkeypatch.setattr("platform.machine", lambda: "i686")
    result = legacy32.assess_32bit_support()
    assert result["ready"] is True
    assert result["capabilities"]["os_is_native_32bit"] is True


def test_assess_arm_needs_translation(tmp_path, monkeypatch):
    monkeypatch.setattr("platform.machine", lambda: "aarch64")
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(legacy32, "_foreign_architectures", lambda: [])
    result = legacy32.assess_32bit_support(root=str(tmp_path))
    assert "missing_x86_translation" in result["gaps"]


def test_plan_apt_enablement(tmp_path, monkeypatch):
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    monkeypatch.setattr(legacy32, "_foreign_architectures", lambda: [])
    assessment = legacy32.assess_32bit_support(root=str(tmp_path))
    plan = legacy32.plan_32bit_enablement(assessment, os_release="ID=ubuntu\nID_LIKE=debian")
    assert plan["package_manager"] == "apt"
    commands = " ".join(s.get("command") or "" for s in plan["steps"])
    assert "dpkg --add-architecture i386" in commands
    assert "libc6:i386" in commands
    # Connectivity modernization is always appended.
    assert "ca-bundle" in commands


def test_plan_pacman_enablement(tmp_path, monkeypatch):
    monkeypatch.setattr("platform.machine", lambda: "x86_64")
    monkeypatch.setattr(legacy32, "_foreign_architectures", lambda: [])
    assessment = legacy32.assess_32bit_support(root=str(tmp_path))
    plan = legacy32.plan_32bit_enablement(assessment, os_release="ID=arch")
    assert plan["package_manager"] == "pacman"
    commands = " ".join(s.get("command") or "" for s in plan["steps"])
    assert "multilib" in commands
    assert "lib32-glibc" in commands


def test_plan_ready_host_is_verification_only(monkeypatch):
    monkeypatch.setattr("platform.machine", lambda: "i686")
    assessment = legacy32.assess_32bit_support()
    plan = legacy32.plan_32bit_enablement(assessment, os_release="ID=debian")
    assert plan["ready"] is True
    # No multiarch enablement steps when already native 32-bit.
    commands = " ".join(s.get("command") or "" for s in plan["steps"])
    assert "dpkg --add-architecture" not in commands
