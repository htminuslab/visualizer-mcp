# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**visualizer-mcp** is an MCP (Model Context Protocol) server that bridges AI assistants (Claude Code, Claude Desktop, VS Code Copilot Chat) to **Siemens Visualizer** via its VCC TCP socket interface. The server exposes Visualizer's Tcl command set as MCP tools, enabling AI-driven hardware simulation workflows.

```
LLM host  <--stdio MCP-->  visualizer-mcp server  <--TCP VCC-->  Visualizer GUI
```

## Commands

```powershell
# Set up environment (Python 3.10+)
py -3.12 -m venv .venv
.venv\Scripts\python -m pip install -e .

# Run all tests
.venv\Scripts\python -m pytest -q

# Run a single test file
.venv\Scripts\python -m pytest tests/test_protocol.py -v

# Run a single test by name
.venv\Scripts\python -m pytest tests/test_vcc_client.py -k "test_eval" -v

# Verify MCP tools with Inspector
npx @modelcontextprotocol/inspector uvx --from . visualizer-mcp
```

## Architecture

### Source Layout (`src/visualizer_mcp/`)

- **`server.py`** — FastMCP server entry point; defines all 12 MCP tools. Each tool calls through to `vcc_client`. The global `_client` is a module-level `VccClient` instance lazily connected.
- **`vcc_client.py`** — Async TCP client. A single background reader task demuxes frames: replies match pending Futures by message number; async signals go into a 256-entry ring buffer. Handles reconnect and auto-launch.
- **`protocol.py`** — VCC wire format: 10-byte header (`type | msg_num | length`) + brace-delimited Tcl body. Frame types: `t` (send), `r` (reply ok), `x` (reply fail), `s` (signal), `q` (quit).
- **`launcher.py`** — Discovers Visualizer by polling `<work_dir>/.Visualizer/vccserver.cfg` (written by Visualizer at startup, format: `port@host`). Can also exec `visualizer` binary.
- **`config.py`** — All configuration via environment variables (see below).

### Key Design Points

- **Async-first**: All I/O uses `asyncio`. Frame sends are serialized with a lock; each request gets a `Future` keyed by message number.
- **Error types**: `VccCommandError` (Tcl `x` reply), `VccConnectionClosed`, `VisualizerNotRunning`.
- **Tcl parsing helpers** in `server.py`: `_tcl_split` handles brace-group nesting; `_strip_vcc_annotation` strips Verilog radix prefixes (e.g., `4'd3` → `3`).
- **Signal ring buffer**: async Visualizer notifications (`vTimeChange`, `vDesignStateChange`, `vHierarchyChange`) are buffered; accessed via the `vcc_recent_signals` tool.

### MCP Tools

| Tool | Purpose |
|---|---|
| `vcc_connect` | Auto-launch Visualizer if needed, register client (idempotent) |
| `vcc_status` | Report cfg/connection status without auto-connecting |
| `vcc_eval` | Send any Tcl command (escape hatch) |
| `vcc_run` | `run [time]` (e.g., `"100ns"`, `"-all"`) |
| `vcc_step` | Single-step simulation N times |
| `vcc_run_status` | Get simulator state |
| `vcc_get_time` | Current simulation time |
| `vcc_wave_add` | Add signals to waveform viewer |
| `vcc_force` | Force a signal to a value with optional timing |
| `vcc_examine` | Examine signal value (radix/time options) |
| `vcc_scan_signal` | Scan signal across a time range, search for value |
| `vcc_recent_signals` | Return buffered async notifications |

## Configuration (Environment Variables)

| Variable | Default | Purpose |
|---|---|---|
| `VCC_WORK_DIR` | server CWD | Working directory for cfg file lookup |
| `VCC_CFG_FILE` | *(derived)* | Explicit path to `vccserver.cfg`, overrides work dir |
| `VCC_CLIENT_NAME` | `"Claude-MCP"` | Client name registered with Visualizer |
| `VCC_VISUALIZER_BIN` | `"visualizer"` | Binary to exec on auto-launch |
| `VCC_LAUNCH_TIMEOUT_S` | `60.0` | Max seconds to wait for Visualizer to start |
| `VCC_CMD_TIMEOUT_S` | `30.0` | Timeout per Tcl command |

## Testing Notes

- `pytest-asyncio` is used in **auto mode** (`asyncio_mode = "auto"` in `pyproject.toml`) — mark async tests with `async def` only, no decorator needed.
- `test_vcc_client.py` spins up a real `asyncio` fake VCC server in-process to test frame demux, registration, signals, and concurrent requests.
- `test_protocol.py` validates frame encoding/decoding against the Siemens spec examples.
