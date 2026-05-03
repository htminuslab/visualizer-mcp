"""Integration tests against a fake asyncio TCP server speaking VCC."""

from __future__ import annotations

import asyncio
import re

import pytest

from visualizer_mcp.protocol import HEADER_LEN, decode_header, encode_tcl, parse_body
from visualizer_mcp.vcc_client import VccClient, VccCommandError


_REGISTER_RE = re.compile(r"vccRegisterClient\s+(\S+)")


class FakeVccServer:
    """A scriptable VCC server for tests.

    `responder(tcl) -> (type, body)` returns `("r", payload)` or `("x", err)`.
    """

    def __init__(self, responder=None) -> None:
        self.responder = responder or self._default_responder
        self.commands: list[str] = []
        self._server: asyncio.base_events.Server | None = None
        self._signal_queues: list[asyncio.Queue[tuple[str, str | None]]] = []

    @staticmethod
    def _default_responder(tcl: str) -> tuple[str, str]:
        m = _REGISTER_RE.match(tcl)
        if m:
            return "r", f"Client registered as {m.group(1)}"
        if tcl.startswith("vccConnect"):
            return "r", ""
        return "r", f"echo:{tcl}"

    @property
    def port(self) -> int:
        assert self._server is not None
        return self._server.sockets[0].getsockname()[1]

    async def __aenter__(self) -> "FakeVccServer":
        self._server = await asyncio.start_server(
            self._handle, host="127.0.0.1", port=0
        )
        return self

    async def __aexit__(self, *_exc) -> None:
        assert self._server is not None
        self._server.close()
        await self._server.wait_closed()

    async def push_signal(self, name: str, value: str | None = None) -> None:
        for q in list(self._signal_queues):
            await q.put((name, value))

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        sigq: asyncio.Queue[tuple[str, str | None]] = asyncio.Queue()
        self._signal_queues.append(sigq)

        async def signal_pump() -> None:
            while True:
                name, value = await sigq.get()
                payload = f" {{{name}{(' ' + value) if value else ''}}}".encode("utf-8")
                header = f"s {len(payload):08x}".encode("ascii")
                writer.write(header + payload)
                await writer.drain()

        pumper = asyncio.create_task(signal_pump())
        try:
            while True:
                try:
                    header = await reader.readexactly(HEADER_LEN)
                except asyncio.IncompleteReadError:
                    return
                type_, size = decode_header(header)
                payload = await reader.readexactly(size) if size else b""
                msg_no, inner = parse_body(type_, payload.decode("utf-8"))
                self.commands.append(inner)
                rtype, rbody = self.responder(inner)
                reply = f" {msg_no} {{{rbody}}}".encode("utf-8")
                rheader = f"{rtype} {len(reply):08x}".encode("ascii")
                writer.write(rheader + reply)
                await writer.drain()
        finally:
            pumper.cancel()
            try:
                await pumper
            except asyncio.CancelledError:
                pass
            self._signal_queues.remove(sigq)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


async def test_connect_registers_client():
    async with FakeVccServer() as srv:
        client = VccClient("127.0.0.1", srv.port, client_name="TestClient")
        await client.connect()
        try:
            assert client.registered_as == "TestClient"
            assert any("vccRegisterClient TestClient" in c for c in srv.commands)
        finally:
            await client.close()


async def test_eval_returns_reply():
    async with FakeVccServer() as srv:
        client = VccClient("127.0.0.1", srv.port)
        await client.connect()
        try:
            result = await client.eval("examine $now")
            assert result == "echo:examine $now"
        finally:
            await client.close()


async def test_eval_failure_raises():
    def responder(tcl: str) -> tuple[str, str]:
        if "vccRegisterClient" in tcl:
            return "r", "ok"
        return "x", "no such command bogus"

    async with FakeVccServer(responder=responder) as srv:
        client = VccClient("127.0.0.1", srv.port)
        await client.connect()
        try:
            with pytest.raises(VccCommandError) as exc:
                await client.eval("bogus")
            assert "no such command" in str(exc.value)
        finally:
            await client.close()


async def test_signal_delivered_to_client():
    async with FakeVccServer() as srv:
        client = VccClient("127.0.0.1", srv.port)
        await client.connect()
        try:
            await srv.push_signal("vTimeChange", "250ns")
            ev = await client.wait_for_signal(timeout_s=2.0)
            assert ev is not None
            assert ev.name == "vTimeChange"
            assert ev.value == "250ns"
            buf = client.peek_signals()
            assert len(buf) >= 1
        finally:
            await client.close()


async def test_concurrent_evals_demuxed_correctly():
    async with FakeVccServer() as srv:
        client = VccClient("127.0.0.1", srv.port)
        await client.connect()
        try:
            results = await asyncio.gather(
                client.eval("cmd-a"),
                client.eval("cmd-b"),
                client.eval("cmd-c"),
            )
            assert results == ["echo:cmd-a", "echo:cmd-b", "echo:cmd-c"]
        finally:
            await client.close()
