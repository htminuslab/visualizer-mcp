"""VCC wire protocol: 10-byte header + body.

Header: "<type> <8-hex-size>"  (type, single space, zero-padded uppercase or
lowercase hex size of the body in bytes).

Body shape per type:
  t (send Tcl)         : " <decimal_msg_no> {<tcl>}"   leading+trailing space count
  r (reply ok)         : " <decimal_msg_no> {<result>}"
  x (reply failure)    : " <decimal_msg_no> {<error>}"
  s (signal, async)    : " {<signal_name> [value]}"    no msg_no
  q (server quitting)  : ""                            size 00000000
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal


HEADER_LEN = 10
FrameType = Literal["t", "r", "x", "s", "q"]


@dataclass
class Frame:
    type: FrameType
    msg_no: int | None
    body: str  # the contents inside { } (or empty for q / outer payload for s)
    raw_payload: str  # full body bytes after header, decoded as utf-8

    @property
    def is_reply(self) -> bool:
        return self.type in ("r", "x")


class ProtocolError(ValueError):
    pass


def encode_tcl(msg_no: int, tcl: str) -> bytes:
    """Encode a Tcl command frame (type 't').

    The spec example shows a leading and trailing space around the message
    number, both included in the header size:
        "t 00000010 37    {wave add *}"
    We emit a single leading space + msg_no + single space + braced body.
    """
    if msg_no < 0:
        raise ValueError("msg_no must be non-negative")
    payload = f" {msg_no} {{{tcl}}}"
    payload_bytes = payload.encode("utf-8")
    header = f"t {len(payload_bytes):08x}".encode("ascii")
    return header + payload_bytes


def decode_header(header: bytes) -> tuple[FrameType, int]:
    if len(header) != HEADER_LEN:
        raise ProtocolError(f"header must be {HEADER_LEN} bytes, got {len(header)}")
    text = header.decode("ascii", errors="replace")
    if text[1] != " ":
        raise ProtocolError(f"malformed header (no space at idx 1): {text!r}")
    type_char = text[0]
    if type_char not in ("t", "r", "x", "s", "q"):
        raise ProtocolError(f"unknown frame type: {type_char!r}")
    size_hex = text[2:]
    try:
        size = int(size_hex, 16)
    except ValueError as e:
        raise ProtocolError(f"bad size hex {size_hex!r}") from e
    return type_char, size  # type: ignore[return-value]


def parse_body(type_: FrameType, payload: str) -> tuple[int | None, str]:
    """Split a body into (msg_no, inner) for r/x/t, or (None, inner) for s/q.

    `inner` is the string between the outermost braces; the spec guarantees
    the body is brace-delimited (or empty for q).
    """
    if type_ == "q":
        return None, ""
    open_idx = payload.find("{")
    close_idx = payload.rfind("}")
    if open_idx == -1 or close_idx == -1 or close_idx < open_idx:
        if type_ == "s":
            return None, payload.strip()
        raise ProtocolError(f"body missing braces: {payload!r}")
    inner = payload[open_idx + 1 : close_idx]
    if type_ == "s":
        return None, inner
    prefix = payload[:open_idx].strip()
    if not prefix:
        raise ProtocolError(f"body for type {type_!r} missing msg_no: {payload!r}")
    try:
        msg_no = int(prefix)
    except ValueError as e:
        raise ProtocolError(f"bad msg_no {prefix!r}") from e
    return msg_no, inner


async def read_frame(reader: asyncio.StreamReader) -> Frame:
    """Read one full frame from a stream. Raises on EOF mid-frame."""
    header = await reader.readexactly(HEADER_LEN)
    type_, size = decode_header(header)
    payload_bytes = await reader.readexactly(size) if size else b""
    payload = payload_bytes.decode("utf-8", errors="replace")
    msg_no, inner = parse_body(type_, payload)
    return Frame(type=type_, msg_no=msg_no, body=inner, raw_payload=payload)
