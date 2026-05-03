from __future__ import annotations

from pathlib import Path

import pytest

from visualizer_mcp.launcher import (
    VisualizerNotRunning,
    get_endpoint,
    parse_cfg,
    read_cfg_if_present,
)


def test_parse_cfg_basic():
    ep = parse_cfg("14001@vismach08\n")
    assert ep.host == "vismach08"
    assert ep.port == 14001


def test_parse_cfg_missing_at_raises():
    with pytest.raises(VisualizerNotRunning):
        parse_cfg("nope")


def test_parse_cfg_bad_port():
    with pytest.raises(VisualizerNotRunning):
        parse_cfg("abc@host")


def test_read_cfg_missing_returns_none(tmp_path: Path):
    assert read_cfg_if_present(tmp_path / "vccserver.cfg") is None


def test_read_cfg_present(tmp_path: Path):
    cfg = tmp_path / "vccserver.cfg"
    cfg.write_text("9000@localhost", encoding="utf-8")
    ep = read_cfg_if_present(cfg)
    assert ep is not None and ep.port == 9000 and ep.host == "localhost"


def test_get_endpoint_raises_when_missing(tmp_path: Path):
    with pytest.raises(VisualizerNotRunning, match="Please start Visualizer"):
        get_endpoint(tmp_path / "vccserver.cfg")


def test_get_endpoint_returns_endpoint(tmp_path: Path):
    cfg = tmp_path / "vccserver.cfg"
    cfg.write_text("14001@localhost", encoding="utf-8")
    ep = get_endpoint(cfg)
    assert ep.port == 14001 and ep.host == "localhost"
