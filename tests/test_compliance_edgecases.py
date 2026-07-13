from __future__ import annotations

import warnings

import pytest

from alma_bridge.compliance.report import parse_target
from alma_bridge.compliance.tls import evaluate_tls_posture
from alma_bridge.compliance.web3 import normalize_ipfs_uri, parse_jsonrpc_response


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("[::1]:8443", ("::1", 8443)),
        ("[2001:db8::1]:443", ("2001:db8::1", 443)),
        ("[::1]", ("::1", 443)),
        ("https://[2001:db8::1]:8545/rpc", ("2001:db8::1", 8545)),
    ],
)
def test_parse_target_ipv6(raw, expected):
    # BUG #2 regression: naive ":" split crashed on IPv6 literals.
    assert parse_target(raw) == expected


def test_assess_unreachable_emits_no_deprecation_warning():
    # BUG #1 regression: probing should not spam ssl.TLSVersion deprecation warnings.
    from alma_bridge.compliance.tls import probe_endpoint

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        obs = probe_endpoint("no-such-host.invalid", 443, timeout=2, probe_legacy=True)
    assert obs["reachable"] is False


def test_evaluate_handles_completely_empty_observation():
    verdict = evaluate_tls_posture({})
    # No reachability info -> treated as reachable unknown; should not crash.
    assert "compliant" in verdict
    assert isinstance(verdict["blockers"], list)


@pytest.mark.parametrize(
    "garbage",
    ["", "   ", "://", "ipfs://", "ipns://", "ipfs:///", "not a uri", "🙂://x"],
)
def test_normalize_ipfs_never_crashes(garbage):
    out = normalize_ipfs_uri(garbage)
    assert "url" in out


@pytest.mark.parametrize(
    "garbage",
    ["", "{", "null", "true", '{"result": {"nested": [1,2,3]}}', "\x00\x01"],
)
def test_parse_jsonrpc_never_crashes(garbage):
    out = parse_jsonrpc_response(garbage)
    assert "ok" in out
