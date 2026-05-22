"""Configuration & defaults for the visualizer-mcp server."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_CLIENT_NAME = "Claude-MCP"
DEFAULT_LAUNCH_TIMEOUT_S = 60.0
DEFAULT_CMD_TIMEOUT_S = 30.0
DEFAULT_VISUALIZER_BIN = "visualizer"
CFG_RELATIVE_PATH = Path(".visualizer") / "vccserver.cfg"


@dataclass
class Settings:
    client_name: str
    launch_timeout_s: float
    cmd_timeout_s: float
    visualizer_bin: str
    cfg_path_override: Path | None  # explicit cfg file (mirrors -vccfile)
    work_dir: Path  # cwd used to find ./.visualizer/vccserver.cfg

    @classmethod
    def from_env(cls) -> "Settings":
        cfg_override = os.environ.get("VCC_CFG_FILE")
        return cls(
            client_name=os.environ.get("VCC_CLIENT_NAME", DEFAULT_CLIENT_NAME),
            launch_timeout_s=float(
                os.environ.get("VCC_LAUNCH_TIMEOUT_S", DEFAULT_LAUNCH_TIMEOUT_S)
            ),
            cmd_timeout_s=float(
                os.environ.get("VCC_CMD_TIMEOUT_S", DEFAULT_CMD_TIMEOUT_S)
            ),
            visualizer_bin=os.environ.get("VCC_VISUALIZER_BIN", DEFAULT_VISUALIZER_BIN),
            cfg_path_override=Path(cfg_override) if cfg_override else None,
            work_dir=Path(os.environ.get("VCC_WORK_DIR", os.getcwd())),
        )

    def cfg_path(self) -> Path:
        if self.cfg_path_override is not None:
            return self.cfg_path_override
        return self.work_dir / CFG_RELATIVE_PATH
