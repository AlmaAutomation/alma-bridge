from __future__ import annotations

from datetime import datetime, timedelta, timezone

from alma_bridge.compliance.tls import evaluate_tls_posture


def _future(days: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=days)).strftime(
        "%b %d %H:%M:%S %Y GMT"
    )


def test_modern_endpoint_is_compliant():
    verdict = evaluate_tls_posture(
        {
            "reachable": True,
            "verified": True,
            "negotiated_protocol": "TLSv1.3",
            "cipher_name": "TLS_AES_256_GCM_SHA384",
            "cipher_bits": 256,
            "cert_not_after": _future(200),
            "legacy_protocols": {"TLSv1": "rejected", "TLSv1.1": "rejected"},
        }
    )
    assert verdict["compliant"] is True
    assert verdict["grade"] == "modern"
    assert verdict["blockers"] == []


def test_old_protocol_blocks_compliance():
    verdict = evaluate_tls_posture(
        {
            "reachable": True,
            "verified": True,
            "negotiated_protocol": "TLSv1",
            "cipher_name": "AES128-SHA",
            "cipher_bits": 128,
            "cert_not_after": _future(200),
        }
    )
    assert verdict["compliant"] is False
    assert any("below TLSv1.2" in b for b in verdict["blockers"])
    assert verdict["grade"] == "legacy"
    assert verdict["recommendation"]


def test_untrusted_chain_blocks_compliance():
    verdict = evaluate_tls_posture(
        {
            "reachable": True,
            "verified": False,
            "verify_error": "self signed certificate",
            "negotiated_protocol": "TLSv1.2",
            "cipher_name": "ECDHE-RSA-AES256-GCM-SHA384",
            "cipher_bits": 256,
            "cert_not_after": _future(200),
        }
    )
    assert verdict["compliant"] is False
    assert any("not trusted" in b for b in verdict["blockers"])


def test_legacy_protocol_still_accepted_is_blocker():
    verdict = evaluate_tls_posture(
        {
            "reachable": True,
            "verified": True,
            "negotiated_protocol": "TLSv1.3",
            "cipher_name": "TLS_AES_256_GCM_SHA384",
            "cipher_bits": 256,
            "cert_not_after": _future(200),
            "legacy_protocols": {"TLSv1": "supported", "TLSv1.1": "rejected"},
        }
    )
    assert verdict["compliant"] is False
    assert any("legacy TLSv1" in b for b in verdict["blockers"])


def test_expired_cert_is_blocker():
    verdict = evaluate_tls_posture(
        {
            "reachable": True,
            "verified": True,
            "negotiated_protocol": "TLSv1.3",
            "cipher_name": "TLS_AES_256_GCM_SHA384",
            "cipher_bits": 256,
            "cert_not_after": _future(-3),
        }
    )
    assert verdict["compliant"] is False
    assert any("expired" in b for b in verdict["blockers"])


def test_expiring_soon_is_warning_not_blocker():
    verdict = evaluate_tls_posture(
        {
            "reachable": True,
            "verified": True,
            "negotiated_protocol": "TLSv1.3",
            "cipher_name": "TLS_AES_256_GCM_SHA384",
            "cipher_bits": 256,
            "cert_not_after": _future(10),
        }
    )
    assert verdict["compliant"] is True
    assert verdict["grade"] == "acceptable"
    assert any("expires in" in w for w in verdict["warnings"])


def test_weak_cipher_is_blocker():
    verdict = evaluate_tls_posture(
        {
            "reachable": True,
            "verified": True,
            "negotiated_protocol": "TLSv1.2",
            "cipher_name": "RC4-MD5",
            "cipher_bits": 128,
            "cert_not_after": _future(200),
        }
    )
    assert verdict["compliant"] is False
    assert any("weak cipher" in b for b in verdict["blockers"])


def test_unreachable_host():
    verdict = evaluate_tls_posture({"reachable": False, "error": "timed out"})
    assert verdict["compliant"] is False
    assert verdict["grade"] == "unreachable"


def test_legacy_only_server_reachable_but_handshake_failed():
    # BUG #3 regression: a host that is up but only speaks TLS 1.0/1.1 (which a
    # modern OpenSSL refuses) must be graded "legacy", not "unreachable".
    verdict = evaluate_tls_posture(
        {
            "reachable": True,
            "tls_handshake_failed": True,
            "tls_error": "[SSL: UNSUPPORTED_PROTOCOL] unsupported protocol",
            "negotiated_protocol": None,
            "verified": False,
        }
    )
    assert verdict["compliant"] is False
    assert verdict["grade"] == "legacy"
    assert any("handshake failed" in b for b in verdict["blockers"])
    assert verdict["recommendation"]
