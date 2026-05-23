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
        self.process: subprocess.Popen | None = None
        self.settings = None
        self.project_root = Path(__file__).parent.parent.resolve()

    def _get_tui_bin(self) -> Path | None:
        release_bin = self.project_root / "runtime" / "target" / "release" / "monad-tui"
        debug_bin = self.project_root / "runtime" / "target" / "debug" / "monad-tui"
        return release_bin if release_bin.exists() else (debug_bin if debug_bin.exists() else None)

    async def run(self):
        tui_bin = self._get_tui_bin()
        if not tui_bin:
            print("\033[31mError: monad-tui binary not found.\033[0m")
            print(f"Please build it: cd runtime && cargo build --bin monad-tui --features tui")
            return

        try:
            config_path = os.getenv("MONAD_CONFIG")
            if config_path:
                self.settings = load_settings(Path(config_path))
        except Exception:
            pass

        self.process = subprocess.Popen(
            [str(tui_bin)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=os.environ.copy()
        )

        # Start state monitoring thread
        threading.Thread(target=self._monitor_state, daemon=True).start()
        
        # Monitor TUI output (user commands)
        await self._handle_tui_output()

    def _send_event(self, event: dict[str, Any]):
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(json.dumps(event) + "\n")
                self.process.stdin.flush()
            except Exception:
                pass

    def _monitor_state(self):
        """
        Periodically scan system for agents and metrics to update the TUI.
        """
        import time
        
        # Initial agent detection
        agents = detect_agents()
        for agent in agents:
            self._send_event({
                "type": "agent_update",
                "name": agent.name,
                "status": "idle",
                "action": "Standing by",
                "tokens": 0
            })

        self._send_event({
            "type": "interaction",
            "text": "[System]: Monad-Zero Orchestrator initialized.",
            "level": "info"
        })

        while self.process and self.process.poll() is None:
            # In a real implementation, this would pull from the actual engine
            # For now, we simulate basic heartbeat or metrics
            time.sleep(5)

    async def _handle_tui_output(self):
        if not self.process or not self.process.stdout:
            return

        import sys
        
        while self.process.poll() is None:
            line = await asyncio.to_thread(self.process.stdout.readline)
            if not line:
                break
            
            try:
                data = json.loads(line)
                if data.get("type") == "user_input":
                    text = data.get("text", "")
                    # Process orchestration command
                    await self._process_command(text)
            except json.JSONDecodeError:
                # Log non-JSON output for debugging
                pass

        if self.process:
            self.process.wait()

    async def _process_command(self, text: str):
        # Basic command routing logic
        if text.startswith("/"):
            cmd = text[1:].split()[0]
            self._send_event({
                "type": "interaction",
                "text": f"[System]: Command '{cmd}' received.",
                "level": "info"
            })
        else:
            # Simulate agent reaction
            self._send_event({
                "type": "interaction",
                "text": f"[System]: Processing prompt with ZeroLang...",
                "level": "info"
            })
            
            # Simulate AST update
            self._send_event({
                "type": "ast_update",
                "skeleton": [
                    "- current_context.py",
                    "  + func analyze()",
                    "  + class MonadEngine"
                ]
            })


def run_tui() -> None:
    bridge = TuiBridge()
    asyncio.run(bridge.run())
