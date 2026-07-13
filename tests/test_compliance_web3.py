from __future__ import annotations

import pytest

from alma_bridge.compliance.web3 import (
    build_jsonrpc_request,
    chain_info,
    decode_quantity,
    evaluate_web3_posture,
    is_valid_cid,
    normalize_ipfs_uri,
    parse_jsonrpc_response,
)


def test_build_jsonrpc_request():
    req = build_jsonrpc_request("eth_chainId")
    assert req == {"jsonrpc": "2.0", "id": 1, "method": "eth_chainId", "params": []}


@pytest.mark.parametrize(
    "raw,ok,result",
    [
        ('{"jsonrpc":"2.0","id":1,"result":"0x1"}', True, "0x1"),
        (b'{"jsonrpc":"2.0","id":1,"result":"0x89"}', True, "0x89"),
        ('{"jsonrpc":"2.0","id":1,"error":{"code":-32601,"message":"nope"}}', False, None),
        ("not json at all", False, None),
        ("[1,2,3]", False, None),
        ('{"jsonrpc":"2.0","id":1}', False, None),
        (12345, False, None),
    ],
)
def test_parse_jsonrpc_response(raw, ok, result):
    parsed = parse_jsonrpc_response(raw)
    assert parsed["ok"] is ok
    assert parsed["result"] == result


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0x1", 1),
        ("0x89", 137),
        ("0xa", 10),
        ("42", 42),
        (7, 7),
        ("0xZZ", None),
        ("", None),
        (None, None),
        ([], None),
    ],
)
def test_decode_quantity(value, expected):
    assert decode_quantity(value) == expected


def test_chain_info_known_and_unknown():
    assert chain_info(1)["name"] == "Ethereum Mainnet"
    assert chain_info(137)["currency"] == "POL"
    unknown = chain_info(999999)
    assert unknown["known"] is False
    assert unknown["name"] == "chain 999999"
    assert chain_info(None)["known"] is False


@pytest.mark.parametrize(
    "cid,valid",
    [
        ("QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG", True),  # CIDv0
        ("bafybeigdyrzt5sfp7udm7hu76uh7y26nf3efuylqabf3oclgtqy55fbzdi", True),  # CIDv1
        ("Qmtooshort", False),
        ("notacid", False),
        ("", False),
        ("Qm0OIl0000000000000000000000000000000000000000", False),  # 0,O,I,l not base58
    ],
)
def test_is_valid_cid(cid, valid):
    assert is_valid_cid(cid) is valid


@pytest.mark.parametrize(
    "uri,expected_url",
    [
        ("ipfs://QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG", "https://ipfs.io/ipfs/QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG"),
        ("ipfs://Qmhash/dir/file.json", "https://ipfs.io/ipfs/Qmhash/dir/file.json"),
        ("ipns://example.eth", "https://ipfs.io/ipns/example.eth"),
        ("ipfs://ipfs/Qmhash", "https://ipfs.io/ipfs/Qmhash"),
        ("https://already.example/x", "https://already.example/x"),
    ],
)
def test_normalize_ipfs_uri(uri, expected_url):
    assert normalize_ipfs_uri(uri)["url"] == expected_url


def test_normalize_ipfs_custom_gateway_strips_trailing_slash():
    out = normalize_ipfs_uri("ipfs://Qmhash", gateway="https://gw.example/")
    assert out["url"] == "https://gw.example/ipfs/Qmhash"


def test_normalize_ipfs_unsupported_scheme():
    out = normalize_ipfs_uri("ftp://nope")
    assert out["url"] is None
    assert out["error"] == "unsupported scheme"


def test_evaluate_web3_ready():
    verdict = evaluate_web3_posture(
        {"reachable": True, "chain_id": 1, "client_version": "geth/v1", "latency_ms": 30},
        {"compliant": True},
    )
    assert verdict["web3_ready"] is True
    assert verdict["chain"]["name"] == "Ethereum Mainnet"


def test_evaluate_web3_unreachable():
    verdict = evaluate_web3_posture({"reachable": False, "error": "timeout"}, None)
    assert verdict["web3_ready"] is False
    assert "timeout" in verdict["blockers"][0]


def test_evaluate_web3_bad_tls_blocks_and_recommends_bridge():
    verdict = evaluate_web3_posture(
        {"reachable": True, "chain_id": 1},
        {"compliant": False, "blockers": ["negotiates TLSv1"]},
    )
    assert verdict["web3_ready"] is False
    assert "TLS-modernizing bridge" in (verdict["recommendation"] or "")


def test_evaluate_web3_unknown_chain_is_warning_only():
    verdict = evaluate_web3_posture({"reachable": True, "chain_id": 424242}, {"compliant": True})
    assert verdict["web3_ready"] is True
    assert any("unrecognized chain" in w for w in verdict["warnings"])
