"""Async TCP client for the Siemens Visualizer VCC server.

One persistent socket. Single background reader task demuxes incoming frames
to per-message Futures, an async signal queue, and a quit-flag.
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass
from typing import Iterable

from .protocol import Frame, encode_tcl, read_frame


log = logging.getLogger(__name__)


class VccCommandError(RuntimeError):
    """Raised when the server returns an 'x' (failure) reply."""

    def __init__(self, msg_no: int, message: str):
        super().__init__(message)
        self.msg_no = msg_no
        self.server_message = message


class VccConnectionClosed(RuntimeError):
    pass


@dataclass
class SignalEvent:
    name: str
    value: str | None
    raw: str

    @classmethod
    def parse(cls, body: str) -> "SignalEvent":
        body = body.strip()
        if " " in body:
            name, value = body.split(" ", 1)
            return cls(name=name, value=value, raw=body)
        return cls(name=body, value=None, raw=body)


class VccClient:
    def __init__(
        self,
        host: str,
        port: int,
        client_name: str = "Claude-MCP",
        signal_buffer: int = 256,
    ) -> None:
        self.host = host
        self.port = port
        self.client_name = client_name
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._reader_task: asyncio.Task | None = None
        self._next_msg_no: int = 1
        self._pending: dict[int, asyncio.Future] = {}
        self._signal_buffer: deque[SignalEvent] = deque(maxlen=signal_buffer)
        self._signal_event = asyncio.Event()
        self._closed: bool = False
        self._registered_as: str | None = None
        self._send_lock = asyncio.Lock()

    @property
    def registered_as(self) -> str | None:
        return self._registered_as

    @property
    def is_open(self) -> bool:
        return (
            self._writer is not None
            and not self._writer.is_closing()
            and not self._closed
        )

    async def connect(self) -> None:
        if self.is_open:
            return
        self._reader, self._writer = await asyncio.open_connection(self.host, self.port)
        self._closed = False
        self._reader_task = asyncio.create_task(
            self._read_loop(), name="vcc-reader"
        )
        try:
            reply = await self.eval(f"vccRegisterClient {self.client_name}")
        except Exception:
            await self.close()
            raise
        self._registered_as = self.client_name
        log.info("VCC registered: %s", reply)

    async def eval(self, tcl: str, timeout_s: float = 30.0) -> str:
        if not self.is_open:
            raise VccConnectionClosed("VCC client not connected")
        msg_no = self._next_msg_no
        self._next_msg_no += 1
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[msg_no] = future
        frame = encode_tcl(msg_no, tcl)
        try:
            async with self._send_lock:
                assert self._writer is not None
                self._writer.write(frame)
                await self._writer.drain()
            return await asyncio.wait_for(future, timeout=timeout_s)
        finally:
            self._pending.pop(msg_no, None)

    def drain_signals(self) -> list[SignalEvent]:
        events = list(self._signal_buffer)
        self._signal_buffer.clear()
        self._signal_event.clear()
        return events

    def peek_signals(self, limit: int | None = None) -> list[SignalEvent]:
        events = list(self._signal_buffer)
        if limit is not None and limit > 0:
            events = events[-limit:]
        return events

    async def wait_for_signal(self, timeout_s: float | None = None) -> SignalEvent | None:
        if self._signal_buffer:
            return self._signal_buffer[-1]
        try:
            await asyncio.wait_for(self._signal_event.wait(), timeout=timeout_s)
        except asyncio.TimeoutError:
            return None
        self._signal_event.clear()
        return self._signal_buffer[-1] if self._signal_buffer else None

    async def subscribe_signals(self, signal_names: Iterable[str]) -> None:
        for name in signal_names:
            try:
                await self.eval(f"vccConnect {name}")
            except VccCommandError as e:
                log.warning("vccConnect %s failed: %s", name, e.server_message)

    async def close(self) -> None:
        self._closed = True
        if self._writer is not None and not self._writer.is_closing():
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
        if self._reader_task is not None:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except (asyncio.CancelledError, Exception):
                pass
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(VccConnectionClosed("Connection closed"))
        self._pending.clear()
        self._reader = None
        self._writer = None
        self._reader_task = None
        self._registered_as = None

    async def _read_loop(self) -> None:
        assert self._reader is not None
        try:
            while True:
                try:
                    frame = await read_frame(self._reader)
                except asyncio.IncompleteReadError:
                    self._fail_all(VccConnectionClosed("Server closed connection"))
                    return
                self._dispatch(frame)
                if frame.type == "q":
                    self._fail_all(VccConnectionClosed("Server sent quit"))
                    return
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("VCC reader loop crashed")
            self._fail_all(e)

    def _dispatch(self, frame: Frame) -> None:
        if frame.type == "r":
            fut = self._pending.get(frame.msg_no) if frame.msg_no is not None else None
            if fut is not None and not fut.done():
                fut.set_result(frame.body)
        elif frame.type == "x":
            fut = self._pending.get(frame.msg_no) if frame.msg_no is not None else None
            if fut is not None and not fut.done():
                fut.set_exception(VccCommandError(frame.msg_no or -1, frame.body))
        elif frame.type == "s":
            ev = SignalEvent.parse(frame.body)
            self._signal_buffer.append(ev)
            self._signal_event.set()
        elif frame.type == "q":
            pass  # handled in read loop after dispatch
        else:
            log.warning("Unhandled frame type %r", frame.type)

    def _fail_all(self, exc: BaseException) -> None:
        for fut in self._pending.values():
            if not fut.done():
                fut.set_exception(exc)
        self._pending.clear()
