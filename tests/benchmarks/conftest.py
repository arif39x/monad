from __future__ import annotations

import pytest


@pytest.fixture(scope="session")
def benchmark_config() -> dict:
    return {
        "iterations": 100,
        "warmup": 10,
        "provider": "mock",
        "session_turns": 10,
        "file_count": 5,
        "file_size": 500,
    }


@pytest.fixture(scope="session")
def sample_prompt() -> str:
    lines = [
        "System: You are an AI assistant. You must follow these instructions:",
        "1. Analyze the following code",
        "2. Provide a fix for any errors",
        "",
        "File: /home/user/project/src/main.py",
        "Content:",
        "def hello():",
        '    print("hello world")',
        "",
        "def goodbye():",
        '    print("goodbye")',
        "",
        "User: Can you fix this error?",
    ]
    return "\n".join(lines)


@pytest.fixture(scope="session")
def sample_large_prompt() -> str:
    lines = [
        "System: You are an AI assistant for software engineering.",
        "You help users write, debug, and optimize code.",
        "",
    ]
    for i in range(20):
        lines.append(f"File: /home/user/project/src/module_{i}.py")
        lines.append("Content:")
        for j in range(50):
            lines.append(f"def function_{j}():")
            lines.append(f"    return {j * 100}")
        lines.append("")
    lines.append("User: What do you think of this code?")
    return "\n".join(lines)
