"""Tests for the self-healing autopilot: diagnosis, pathways, learning, rebuild."""

from __future__ import annotations

import pytest

from alma_bridge.compliance import autopilot
from alma_bridge.compliance import learning


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    monkeypatch.setattr("alma_bridge.config.settings.db_path", tmp_path / "outcomes.db")
    monkeypatch.setattr("alma_bridge.config.settings.data_dir", tmp_path)
    learning.init_healing_store()
    return tmp_path


# --------------------------------------------------------------------------- #
# Diagnosis
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text,expected",
    [
        ("error while loading shared libraries: libfoo.so.2: cannot open shared object file",
         "missing_shared_library"),
        ("/app: /lib/x86_64-linux-gnu/libm.so.6: version `GLIBC_2.29' not found",
         "glibc_too_old"),
        ("cannot execute binary file: Exec format error (ELFCLASS32)", "arch_32bit"),
        ("sslv3 alert handshake failure: unsupported protocol", "tls_obsolete_protocol"),
        ("SSL: CERTIFICATE_VERIFY_FAILED unable to get local issuer certificate",
         "tls_cert_untrusted"),
        ("curl: (6) Could not resolve host: example.com", "dns_failure"),
        ("modprobe: FATAL: no driver found for device", "driver_missing"),
    ],
)
def test_diagnose_signatures(text, expected):
    diagnoses = autopilot.diagnose(text)
    assert diagnoses[0]["signature"] == expected
    assert 0 < diagnoses[0]["confidence"] <= 1.0


def test_diagnose_unknown():
    diagnoses = autopilot.diagnose("the flux capacitor overheated")
    assert diagnoses[0]["signature"] == "unknown_error"


def test_extract_missing_library():
    diagnoses = autopilot.diagnose(
        "error while loading shared libraries: libssl.so.1.0.0: cannot open shared object file"
    )
    assert diagnoses[0]["missing_library"] == "libssl.so.1.0.0"


# --------------------------------------------------------------------------- #
# Package-manager detection
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "os_release,expected",
    [
        ('ID=ubuntu\nID_LIKE=debian', "apt"),
        ('ID=fedora', "dnf"),
        ('ID=arch', "pacman"),
        ('ID=opensuse-leap\nID_LIKE="suse opensuse"', "zypper"),
        ('ID=alpine', "apk"),
    ],
)
def test_detect_package_manager(os_release, expected):
    assert autopilot.detect_package_manager(os_release) == expected


# --------------------------------------------------------------------------- #
# Pathway planning + synthesis
# --------------------------------------------------------------------------- #


def test_plan_pathways_materializes_commands(isolated_db):
    plan = autopilot.plan_pathways(
        "error while loading shared libraries: libcrypto.so.1.1: cannot open shared object file",
        os_release="ID=ubuntu\nID_LIKE=debian",
    )
    assert plan["primary_signature"] == "missing_shared_library"
    assert plan["package_manager"] == "apt"
    # A bespoke (synthesized) pathway for the specific lib should lead.
    assert plan["pathways"][0].get("synthesized") is True
    assert "libcrypto.so.1.1" in plan["pathways"][0]["title"]
    # No unresolved placeholders should remain in any command.
    for path in plan["pathways"]:
        for step in path["steps"]:
            cmd = step.get("command") or ""
            assert "{pm-" not in cmd


def test_plan_pathways_tls_bridge_first(isolated_db):
    plan = autopilot.plan_pathways("sslv3 alert handshake failure unsupported protocol")
    ids = [p["id"] for p in plan["pathways"]]
    assert "tls_modernizer_bridge" in ids
    # Highest-priority pathway leads before any learning.
    assert plan["pathways"][0]["id"] == "tls_modernizer_bridge"


# --------------------------------------------------------------------------- #
# Online learning re-ranks pathways
# --------------------------------------------------------------------------- #


def test_feedback_reranks_pathways(isolated_db):
    sig = "tls_obsolete_protocol"
    # Initially the bridge pathway leads by static priority.
    first = autopilot.plan_pathways("unsupported protocol handshake failure")
    assert first["pathways"][0]["id"] == "tls_modernizer_bridge"

    # Teach the learner that the lower-priority openssl pathway keeps working.
    for _ in range(8):
        autopilot.record_outcome(sig, "tls_enable_modern_openssl", True)
        autopilot.record_outcome(sig, "tls_modernizer_bridge", False)

    after = autopilot.plan_pathways("unsupported protocol handshake failure")
    assert after["pathways"][0]["id"] == "tls_enable_modern_openssl"
    # Learned rate is surfaced for transparency.
    lead = after["pathways"][0]
    assert lead["learned_rate"] is not None


def test_feedback_summary_records(isolated_db):
    autopilot.record_outcome("dns_failure", "dns_over_https", True)
    summary = learning.feedback_summary()
    assert any(
        row["signature"] == "dns_failure" and row["pathway_id"] == "dns_over_https"
        for row in summary
    )


# --------------------------------------------------------------------------- #
# run_autopilot: safe diagnostic execution only
# --------------------------------------------------------------------------- #


def test_run_autopilot_no_execute(isolated_db):
    plan = autopilot.run_autopilot("could not resolve host example.com", execute=False)
    assert plan["mutations_applied"] is False
    assert plan["executed_diagnostics"] == []


def test_run_autopilot_executes_only_safe_diagnostics(isolated_db):
    # glibc pathway has a safe diagnostic `ldd --version`.
    plan = autopilot.run_autopilot(
        "version `GLIBC_2.34' not found", execute=True
    )
    assert plan["mutations_applied"] is False
    # Any executed command must be a read-only probe, never a mutation.
    for entry in plan["executed_diagnostics"]:
        cmd = entry["command"]
        assert "sudo" not in cmd
        assert "install" not in cmd


def test_is_safe_diagnostic_rejects_mutations():
    assert autopilot._is_safe_diagnostic("ldd --version") is True
    assert autopilot._is_safe_diagnostic("sudo apt-get install -y libc6") is False
    assert autopilot._is_safe_diagnostic("rm -rf /") is False
    assert autopilot._is_safe_diagnostic("modprobe foo") is False
