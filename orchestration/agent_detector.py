from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass

from orchestration.adapters.base import AbstractAgentAdapter
from orchestration.adapters.registry import get_adapter

AGENT_NAME_PATTERNS = [
    "opencode",
    "aider",
    "claude",
    "codex",
    "gemini",
    "gpt",
    "copilot",
    "mentat",
    "sweagent",
    "swe-agent",
    "continue",
    "llm",
    "chatgpt",
    "codellama",
    "codestral",
    "qwen",
    "deepseek",
    "tabby",
    "localai",
    "ollama",
    "cline",
    "goose",
    "openhands",
    "opendevin",
    "warp",
    "amazonq",
    "q-developer",
    "roo-code",
    "ampcode",
    "devin",
    "interpreter",
    "open-interpreter",
    "fabric",
    "mods",
    "shell-gpt",
    "sgpt",
    "tgpt",
    "gh-copilot",
    "cursor-cli",
    "supermaven",
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
    "gh-copilot": "GitHub Copilot CLI extension",
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
    "interpreter": "Open Interpreter - A natural language interface for your computer",
}


def _heuristic_name(binary: str) -> bool:
    name = binary.lower().replace(".exe", "")
    tokens = set()
    for sep in ("-", "_", ".", " "):
        tokens.update(name.split(sep))

    if any(pattern in tokens for pattern in AGENT_NAME_PATTERNS):
        return True

    if "ai" in tokens and len(tokens) > 1:
        return True

    return False


def _run_help_check(binary_path: str) -> bool:
    try:
        result = subprocess.run(
            [binary_path, "--help"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=2.0,
        )
        output = (result.stdout + result.stderr).lower()
        ai_keywords = {"ai", "language model", "llm", "completion", "chat", "prompt", "inference"}
        return any(kw in output for kw in ai_keywords)
    except Exception:
        return False


def _resolve_description(binary: str) -> str:
    name = os.path.splitext(binary)[0].lower()
    return _AGENT_DESCRIPTIONS.get(name, f"AI CLI tool detected on PATH: {binary}")


def detect_agents(use_heuristics: bool = False) -> list[DetectedAgent]:
    found: dict[str, DetectedAgent] = {}
    path_str = os.environ.get("PATH", "")
    path_dirs = path_str.split(os.pathsep)

    seen_binaries: set[str] = set()
    for directory in path_dirs:
        if not directory or not os.path.isdir(directory):
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
                is_agent = _heuristic_name(binary_base)

                if not is_agent and use_heuristics:
                    if any(kw in binary_base for kw in ("ai", "gpt", "agent", "bot", "llm")):
                        if _run_help_check(full_path):
                            is_agent = True

                if not is_agent:
                    continue

                found[entry] = DetectedAgent(
                    name=entry,
                    binary=entry,
                    path=full_path,
                    description=_resolve_description(entry),
                    adapter=get_adapter(entry),
                )
        except PermissionError:
            continue

    return list(found.values())
