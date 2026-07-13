from __future__ import annotations

import asyncio
import shutil
import ssl
import subprocess

import pytest

from alma_bridge.compliance.bridge import TlsModernizer


def test_bridge_start_list_stop():
    """Bridge lifecycle without any upstream traffic (binds a real listener)."""

    async def _run():
        mod = TlsModernizer()
        spec = await mod.start(
            "127.0.0.1", 65000, listen_host="127.0.0.1", listen_port=0, verify=False
        )
        assert spec.listen_port > 0
        listing = mod.list()
        assert len(listing) == 1
        assert listing[0]["id"] == spec.id
        assert listing[0]["upstream"] == "127.0.0.1:65000"
        assert await mod.stop(spec.id) is True
        assert mod.list() == []
        assert await mod.stop(spec.id) is False

    asyncio.run(_run())


@pytest.mark.skipif(shutil.which("openssl") is None, reason="openssl not available")
def test_bridge_modernizes_plaintext_to_tls(tmp_path):
    cert = tmp_path / "cert.pem"
    key = tmp_path / "key.pem"
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048",
            "-keyout", str(key), "-out", str(cert),
            "-days", "1", "-nodes", "-subj", "/CN=localhost",
        ],
        check=True,
        capture_output=True,
    )

    async def _run():
        # Modern TLS echo server standing in for a real HTTPS upstream.
        server_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        server_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        server_ctx.load_cert_chain(certfile=str(cert), keyfile=str(key))

        async def echo(reader, writer):
            data = await reader.read(1024)
            writer.write(b"ECHO:" + data)
            await writer.drain()
            writer.close()

        upstream = await asyncio.start_server(echo, "127.0.0.1", 0, ssl=server_ctx)
        upstream_port = upstream.sockets[0].getsockname()[1]

        mod = TlsModernizer()
        spec = await mod.start(
            "127.0.0.1",
            upstream_port,
            listen_host="127.0.0.1",
            listen_port=0,
            verify=False,  # self-signed test cert
            upstream_sni="localhost",
            min_tls="TLSv1.2",
        )

        # Legacy client speaks *plaintext* to the bridge; bridge upgrades to TLS.
        reader, writer = await asyncio.open_connection("127.0.0.1", spec.listen_port)
        writer.write(b"hello-legacy")
        await writer.drain()
        if writer.can_write_eof():
            writer.write_eof()
        response = await asyncio.wait_for(reader.read(1024), timeout=5)
        writer.close()

        assert response == b"ECHO:hello-legacy"
        assert spec.total_connections == 1
        assert spec.bytes_up >= len(b"hello-legacy")

        await mod.stop(spec.id)
        upstream.close()
        await upstream.wait_closed()

    asyncio.run(_run())
