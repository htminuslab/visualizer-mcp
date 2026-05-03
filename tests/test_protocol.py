"""Frame round-trip tests using the canonical examples from vcc.txt."""

from __future__ import annotations

import asyncio

import pytest

from visualizer_mcp.protocol import (
    Frame,
    HEADER_LEN,
    ProtocolError,
    decode_header,
    encode_tcl,
    parse_body,
    read_frame,
)


def test_encode_tcl_header_size_matches_payload():
    frame = encode_tcl(37, "wave add *")
    header = frame[:HEADER_LEN]
    payload = frame[HEADER_LEN:]
    type_, size = decode_header(header)
    assert type_ == "t"
    assert size == len(payload)
    # Body shape:  " 37 {wave add *}"  -> 16 bytes (matches spec example length 0x10)
    assert payload == b" 37 {wave add *}"
    assert size == 0x10


def test_encode_register_client():
    frame = encode_tcl(1, "vccRegisterClient Virtuoso")
    type_, size = decode_header(frame[:HEADER_LEN])
    assert type_ == "t"
    assert size == len(frame) - HEADER_LEN


def test_decode_header_rejects_bad_space():
    with pytest.raises(ProtocolError):
        decode_header(b"tX0000000A")


def test_decode_header_rejects_unknown_type():
    with pytest.raises(ProtocolError):
        decode_header(b"z 00000001")


def test_decode_header_rejects_bad_size():
    with pytest.raises(ProtocolError):
        decode_header(b"t ZZZZZZZZ")


def test_parse_body_reply_ok():
    msg_no, inner = parse_body("r", " 1 {Client registered as Virtuoso}")
    assert msg_no == 1
    assert inner == "Client registered as Virtuoso"


def test_parse_body_reply_empty():
    msg_no, inner = parse_body("r", " 18 {}")
    assert msg_no == 18
    assert inner == ""


def test_parse_body_signal():
    msg_no, inner = parse_body("s", " {vHierarchyChange t.m.cntl}")
    assert msg_no is None
    assert inner == "vHierarchyChange t.m.cntl"


def test_parse_body_quit():
    msg_no, inner = parse_body("q", "")
    assert msg_no is None
    assert inner == ""


async def test_read_frame_roundtrip_via_streamreader():
    body = b" 27 {Client successfully registered}"
    header = f"r {len(body):08x}".encode("ascii")
    reader = asyncio.StreamReader()
    reader.feed_data(header + body)
    reader.feed_eof()
    frame: Frame = await read_frame(reader)
    assert frame.type == "r"
    assert frame.msg_no == 27
    assert frame.body == "Client successfully registered"


async def test_read_frame_signal():
    body = b" {vTimeChange 250ns}"
    header = f"s {len(body):08x}".encode("ascii")
    reader = asyncio.StreamReader()
    reader.feed_data(header + body)
    reader.feed_eof()
    frame = await read_frame(reader)
    assert frame.type == "s"
    assert frame.msg_no is None
    assert frame.body == "vTimeChange 250ns"


async def test_read_frame_quit():
    reader = asyncio.StreamReader()
    reader.feed_data(b"q 00000000")
    reader.feed_eof()
    frame = await read_frame(reader)
    assert frame.type == "q"
    assert frame.msg_no is None
    assert frame.body == ""
