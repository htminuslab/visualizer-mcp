"""Discover the running VCC server via its cfg file.

The cfg file format per Siemens spec is a single line:
    <port>@<host>
e.g. "14001@vismach08".
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


class VisualizerNotRunning(RuntimeError):
    pass


@dataclass
class VccEndpoint:
    host: str
    port: int


def parse_cfg(text: str) -> VccEndpoint:
    line = text.strip().splitlines()[0] if text.strip() else ""
    if "@" not in line:
        raise VisualizerNotRunning(f"cfg file malformed (expected port@host): {line!r}")
    port_str, host = line.split("@", 1)
    port_str = port_str.strip()
    host = host.strip()
    try:
        port = int(port_str)
    except ValueError as e:
        raise VisualizerNotRunning(f"cfg port not an int: {port_str!r}") from e
    if not host:
        host = "localhost"
    return VccEndpoint(host=host, port=port)


def read_cfg_if_present(cfg_path: Path) -> VccEndpoint | None:
    if not cfg_path.exists():
        return None
    try:
        return parse_cfg(cfg_path.read_text(encoding="utf-8"))
    except OSError:
        return None


def get_endpoint(cfg_path: Path) -> VccEndpoint:
    """Return the VCC endpoint from cfg, or raise VisualizerNotRunning."""
    ep = read_cfg_if_present(cfg_path)
    if ep is not None:
        return ep
    raise VisualizerNotRunning(
        f"Visualizer is not running. Please start Visualizer and try again. "
        f"(Expected cfg file at: {cfg_path})"
    )
