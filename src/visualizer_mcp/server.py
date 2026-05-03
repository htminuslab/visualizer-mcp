"""MCP server entry point exposing Siemens Visualizer to LLM hosts."""

from __future__ import annotations

import asyncio
import logging
import re
import shlex
from typing import Any

from mcp.server.fastmcp import FastMCP

from .config import Settings
from .launcher import VccEndpoint, VisualizerNotRunning, get_endpoint, read_cfg_if_present
from .vcc_client import (
    SignalEvent,
    VccClient,
    VccCommandError,
    VccConnectionClosed,
)


log = logging.getLogger(__name__)

DEFAULT_SIGNAL_SUBSCRIPTIONS = (
    "vDesignStateChange",
    "vTimeChange",
    "vHierarchyChange",
)


class VisualizerSession:
    """Lazy connection manager. One Visualizer GUI, one VCC client."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client: VccClient | None = None
        self._lock = asyncio.Lock()

    async def client(self) -> VccClient:
        async with self._lock:
            if self._client is not None and self._client.is_open:
                return self._client
            ep = get_endpoint(self.settings.cfg_path())
            self._client = VccClient(
                host=ep.host,
                port=ep.port,
                client_name=self.settings.client_name,
            )
            await self._client.connect()
            await self._client.subscribe_signals(DEFAULT_SIGNAL_SUBSCRIPTIONS)
            return self._client

    async def eval(self, tcl: str, timeout_s: float | None = None) -> str:
        timeout = timeout_s if timeout_s is not None else self.settings.cmd_timeout_s
        client = await self.client()
        try:
            return await client.eval(tcl, timeout_s=timeout)
        except VccConnectionClosed:
            await self._reset()
            client = await self.client()
            return await client.eval(tcl, timeout_s=timeout)

    async def status_summary(self) -> dict[str, Any]:
        cfg = self.settings.cfg_path()
        ep = read_cfg_if_present(cfg)
        out: dict[str, Any] = {
            "cfg_path": str(cfg),
            "cfg_present": ep is not None,
        }
        if ep is not None:
            out["host"] = ep.host
            out["port"] = ep.port
        client = self._client
        out["connected"] = bool(client and client.is_open)
        if client and client.is_open:
            out["registered_as"] = client.registered_as
        return out

    async def _reset(self) -> None:
        async with self._lock:
            if self._client is not None:
                await self._client.close()
                self._client = None


def _format_event(ev: SignalEvent) -> dict[str, Any]:
    return {"name": ev.name, "value": ev.value}


_ANNOTATED_VALUE_RE = re.compile(r"^\d+'[bBoOdDhHuU](.+)$", re.IGNORECASE)


def _strip_vcc_annotation(token: str) -> str:
    """Return bare value from an annotated VCC token, e.g. "4'd3" → "3"."""
    m = _ANNOTATED_VALUE_RE.match(token.strip())
    return m.group(1) if m else token.strip()


def _tcl_split(s: str) -> list[str]:
    """Split a Tcl list string into tokens, handling {brace groups}."""
    tokens: list[str] = []
    i, n = 0, len(s)
    while i < n:
        while i < n and s[i] in " \t\n\r":
            i += 1
        if i >= n:
            break
        if s[i] == "{":
            depth, j = 0, i
            while j < n:
                if s[j] == "{":
                    depth += 1
                elif s[j] == "}":
                    depth -= 1
                if depth == 0:
                    tokens.append(s[i + 1 : j])
                    i = j + 1
                    break
                j += 1
            else:
                tokens.append(s[i + 1 :])
                break
        else:
            j = i
            while j < n and s[j] not in " \t\n\r":
                j += 1
            tokens.append(s[i:j])
            i = j
    return tokens


def build_server(settings: Settings | None = None) -> FastMCP:
    settings = settings or Settings.from_env()
    session = VisualizerSession(settings)
    mcp = FastMCP("visualizer-mcp")

    @mcp.tool()
    async def vcc_eval(tcl: str, timeout_s: float | None = None) -> dict[str, Any]:
        """Send any Tcl command to Visualizer's command interpreter.

        This is the escape hatch — every Visualizer Tcl command (run, step,
        wave add, force, examine, env, ...) can be sent through this tool.
        """
        try:
            result = await session.eval(tcl, timeout_s=timeout_s)
            return {"ok": True, "result": result}
        except VccCommandError as e:
            return {"ok": False, "error": e.server_message}
        except VisualizerNotRunning as e:
            return {"ok": False, "error": str(e)}
        except VccConnectionClosed as e:
            return {"ok": False, "error": f"connection_closed: {e}"}
        except asyncio.TimeoutError:
            return {"ok": False, "error": "timeout"}

    @mcp.tool()
    async def vcc_status() -> dict[str, Any]:
        """Report VCC server reachability, host/port, and registration status.

        Does NOT auto-launch. Use `vcc_connect` (or any other tool) to trigger
        an auto-launch if Visualizer is not running.
        """
        return await session.status_summary()

    @mcp.tool()
    async def vcc_connect() -> dict[str, Any]:
        """Ensure Visualizer is running and the VCC socket is open. Idempotent.

        Returns an error with instructions if Visualizer is not running.
        """
        try:
            client = await session.client()
            return {
                "ok": True,
                "host": client.host,
                "port": client.port,
                "registered_as": client.registered_as,
            }
        except VisualizerNotRunning as e:
            return {"ok": False, "error": str(e)}

    @mcp.tool()
    async def vcc_run(time: str | None = None) -> dict[str, Any]:
        """Advance simulation. `time` may be "100ns", "-all", or None for default."""
        cmd = "run" if not time else f"run {time}"
        return await vcc_eval(cmd)  # type: ignore[misc]

    @mcp.tool()
    async def vcc_step(count: int = 1) -> dict[str, Any]:
        """Single-step the simulation `count` times."""
        if count <= 1:
            return await vcc_eval("step")  # type: ignore[misc]
        return await vcc_eval(f"step {int(count)}")  # type: ignore[misc]

    @mcp.tool()
    async def vcc_run_status() -> dict[str, Any]:
        """Report runStatus (current simulator state)."""
        return await vcc_eval("runStatus")  # type: ignore[misc]

    @mcp.tool()
    async def vcc_get_time() -> dict[str, Any]:
        """Return the current simulation time."""
        return await vcc_eval("examine $now")  # type: ignore[misc]

    @mcp.tool()
    async def vcc_wave_add(signals: list[str]) -> dict[str, Any]:
        """Add one or more signals to the wave window. Use dot-separated paths with "sim." prefix, e.g. ["sim.top.clk", "sim.top.dut.state", "sim.div_tb.*"]"""
        if not signals:
            return {"ok": False, "error": "no signals provided"}
        quoted = " ".join(shlex.quote(s) for s in signals)
        return await vcc_eval(f"wave add {quoted}")  # type: ignore[misc]

    @mcp.tool()
    async def vcc_force(signal: str, value: str, time: str | None = None) -> dict[str, Any]:
        """Force `signal` to `value` (e.g. force sim.top.rst 1 0; force sim.top.clk 0 50ns)."""
        suffix = f" {time}" if time else ""
        return await vcc_eval(
            f"force {shlex.quote(signal)} {shlex.quote(value)}{suffix}"
        )  # type: ignore[misc]

    @mcp.tool()
    async def vcc_examine(
        signal: str,
        time: str | None = None,
        radix: str = "decimal",
    ) -> dict[str, Any]:
        """Examine the value of a signal, optionally at a specific simulation time.

        signal: dot-separated hierarchical path with "sim." prefix e.g. sim.testbench.u1.my_signal
        time: simulation time e.g. "400 ns" (omit for current time)
        radix: decimal (default), binary, hexadecimal, unsigned, octal

        The returned value may include a size/radix annotation e.g. "4'd3"
        (4-bit vector, decimal value 3). If Visualizer is not configured to
        annotate, the plain value is returned e.g. "3".
        Signal must be last in the examine command; this tool enforces that.
        """
        parts = ["examine"]
        if time:
            parts.append(f"-time {{{time}}}")
        parts.append(f"-radix {radix}")
        parts.append(shlex.quote(signal))
        return await vcc_eval(" ".join(parts))  # type: ignore[misc]

    @mcp.tool()
    async def vcc_scan_signal(
        signal: str,
        find_value: str | None = None,
        from_time: str | None = None,
        to_time: str | None = None,
        radix: str = "decimal",
    ) -> dict[str, Any]:
        """Scan a signal across a time range; optionally search for a specific value.

        Returns all sampled values across the range as a Tcl list. If find_value
        is given, also reports whether the signal ever held that value (handles
        both plain "3" and annotated forms like "4'd3"). When find_value is
        given and no time range is specified, the scan starts from time 0 to
        cover the full simulation.

        signal: dot-separated hierarchical path with "sim." prefix e.g. sim.testbench.u1.my_signal
        find_value: value to search for e.g. "6" (optional)
        from_time: range start e.g. "0 ns" (defaults to "0" when find_value given)
        to_time: range end e.g. "1 us" (omit to scan to simulation end)
        radix: decimal (default), binary, hexadecimal, unsigned, octal
        """
        effective_from = from_time
        if find_value is not None and effective_from is None:
            effective_from = "0"

        parts = ["examine"]
        if effective_from:
            parts.append(f"-from {{{effective_from}}}")
        if to_time:
            parts.append(f"-to {{{to_time}}}")
        parts.append(f"-radix {radix}")
        parts.append(shlex.quote(signal))
        result = await vcc_eval(" ".join(parts))  # type: ignore[misc]

        if not result.get("ok") or find_value is None:
            return result

        tokens = _tcl_split(result.get("result", ""))
        target = find_value.strip().lower()
        matched = [t for t in tokens if _strip_vcc_annotation(t).lower() == target]
        result["find_value"] = find_value
        result["found"] = bool(matched)
        result["match_count"] = len(matched)
        return result

    @mcp.tool()
    async def vcc_recent_signals(limit: int = 20) -> dict[str, Any]:
        """Return recent async signal notifications received from Visualizer
        (e.g. vTimeChange, vDesignStateChange). Newest last."""
        client = session._client
        if client is None or not client.is_open:
            return {"ok": True, "events": []}
        events = client.peek_signals(limit=limit)
        return {"ok": True, "events": [_format_event(e) for e in events]}

    return mcp


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    server = build_server()
    server.run()


if __name__ == "__main__":
    main()
