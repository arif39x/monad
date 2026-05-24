from __future__ import annotations

import asyncio
import json
import os
import subprocess
import threading
from pathlib import Path
from typing import Any

from orchestration.agent_detector import detect_agents
from orchestration.config import load_settings


class TuiBridge:
    def __init__(self):
        self.project_root = Path(__file__).parent.parent.resolve()

    def _get_tui_bin(self) -> Path | None:
        release_bin = self.project_root / "runtime" / "target" / "release" / "elyon-tui"
        debug_bin = self.project_root / "runtime" / "target" / "debug" / "elyon-tui"
        return release_bin if release_bin.exists() else (debug_bin if debug_bin.exists() else None)

    async def run(self):
        tui_bin = self._get_tui_bin()
        if not tui_bin:
            print("\033[31mError: elyon-tui binary not found.\033[0m")
            print(f"Please build it: cd runtime && cargo build --bin elyon-tui --features tui")
            return

        try:
            subprocess.run([str(tui_bin)])
        except KeyboardInterrupt:
            pass


def run_tui() -> None:
    bridge = TuiBridge()
    asyncio.run(bridge.run())
