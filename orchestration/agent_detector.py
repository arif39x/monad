from __future__ import annotations

import asyncio
import os
import shutil
from dataclasses import dataclass
from orchestration.adapters.registry import get_adapter
from orchestration.adapters.base import AbstractAgentAdapter

AGENT_NAME_PATTERNS = [
    "opencode", "aider", "claude", "codex", "gemini", "gpt",
    "copilot", "mentat", "sweagent", "swe-agent", "continue",
    "llm", "chatgpt", "codellama", "codestral", "qwen",
    "deepseek", "tabby", "localai", "ollama",
    "cline", "goose", "openhands", "opendevin", "warp",
    "amazonq", "q-developer", "roo-code", "ampcode", "devin",
]


@dataclass(frozen=True)
class DetectedAgent:
    name: str
    binary: str
    path: str
    description: str
    adapter: AbstractAgentAdapter


_AGENT_DESCRIPTIONS: dict[str, str] = {
    "claude": "Autonomous SWE agent with multi-agent workflows (Anthropic)",
    "claude.exe": "Autonomous SWE agent with multi-agent workflows (Anthropic)",
    "codex": "AI coding + execution with cloud sandboxing (OpenAI)",
    "codex.exe": "AI coding + execution with cloud sandboxing (OpenAI)",
    "copilot": "Shell + git assistance CLI (GitHub)",
    "github-copilot-cli": "Shell + git assistance CLI (GitHub)",
    "gemini": "Large-context coding workflows (Google AI)",
    "aider": "Git-native AI coding with patch-based edits",
    "cline": "Autonomous coding with filesystem + shell automation",
    "goose": "Open CLI agent for extensible agentic coding",
    "openhands": "Autonomous SWE engineering with planning + debugging",
    "opendevin": "End-to-end autonomous SWE agent",
    "warp": "AI-enhanced shell with command suggestions",
    "q": "Cloud + infra development CLI (AWS Amazon Q)",
    "amazon-q": "Cloud + infra development CLI (AWS Amazon Q)",
    "roo": "Structured AI coding with configurable agent modes",
    "roo-code": "Structured AI coding with configurable agent modes",
    "continue": "Extensible local/cloud AI coding (BYOM)",
    "ampcode": "Autonomous development with workflow orchestration",
    "devin": "Long-horizon autonomous software engineering",
    "opencode": "AI coding assistant with multi-agent orchestration",
    "gpt": "OpenAI GPT command-line interface",
    "ollama": "Local LLM runner with model management",
    "deepseek": "DeepSeek AI coding assistant",
    "deepseek-tui": "DeepSeek AI coding assistant (TUI)",
}


def _heuristic_name(binary: str) -> bool:
    name = binary.lower().replace(".exe", "")
    tokens = set()
    for sep in ("-", "_", ".", " "):
        tokens.update(name.split(sep))
    return any(pattern in tokens for pattern in AGENT_NAME_PATTERNS)


def _heuristic_ai_keywords(binary_path: str) -> bool:
    try:
        # Use a fresh event loop or just run it synchronously if possible, 
        # but asyncio.run is generally fine here for a single call.
        result = asyncio.run(
            asyncio.create_subprocess_exec(
                binary_path, "--help",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        )
        stdout, stderr = asyncio.run(result.communicate())
        output = (stdout.decode() + stderr.decode()).lower()
        ai_keywords = {"ai", "language model", "llm", "completion", "chat", "prompt"}
        return any(kw in output for kw in ai_keywords)
    except Exception:
        return False


def _resolve_description(binary: str) -> str:
    name = os.path.splitext(binary)[0].lower()
    return _AGENT_DESCRIPTIONS.get(name, f"AI CLI tool detected on PATH: {binary}")


def detect_agents() -> list[DetectedAgent]:
    found: dict[str, DetectedAgent] = {}
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)

    seen_binaries: set[str] = set()
    for directory in path_dirs:
        if not os.path.isdir(directory):
            continue
        try:
            for entry in os.listdir(directory):
                if entry in seen_binaries:
                    continue
                seen_binaries.add(entry)

                full_path = os.path.join(directory, entry)
                if not os.path.isfile(full_path) or not os.access(full_path, os.X_OK):
                    continue

                binary_base = entry.lower()
                if not _heuristic_name(binary_base):
                    continue

                resolved = shutil.which(entry)
                if resolved is None:
                    continue

                desc = _resolve_description(entry)
                found[entry] = DetectedAgent(
                    name=entry,
                    binary=entry,
                    path=resolved,
                    description=desc,
                    adapter=get_adapter(entry),
                )
        except PermissionError:
            continue

    return list(found.values())
