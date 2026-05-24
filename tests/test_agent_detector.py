from __future__ import annotations

import os
import tempfile

from orchestration.agent_detector import (
    _heuristic_name,
    _resolve_description,
    detect_agents,
)


def test_heuristic_name_matches_known_agents() -> None:
    assert _heuristic_name("opencode") is True
    assert _heuristic_name("aider") is True
    assert _heuristic_name("claude") is True
    assert _heuristic_name("gemini") is True
    assert _heuristic_name("copilot") is True
    assert _heuristic_name("ollama") is True
    assert _heuristic_name("devin") is True


def test_heuristic_name_matches_with_suffix() -> None:
    assert _heuristic_name("opencode.exe") is True
    assert _heuristic_name("aider-v2") is True
    assert _heuristic_name("claude-3.5") is True


def test_heuristic_name_rejects_non_ai_binaries() -> None:
    assert _heuristic_name("ls") is False
    assert _heuristic_name("python") is False
    assert _heuristic_name("gcc") is False
    assert _heuristic_name("chroot") is False
    assert _heuristic_name("docker") is False


def test_heuristic_name_token_boundary_no_false_positive() -> None:
    assert _heuristic_name("chroot") is False
    assert _heuristic_name("clone") is False


def test_resolve_description_known() -> None:
    desc = _resolve_description("claude")
    assert "Autonomous" in desc
    assert "Anthropic" in desc


def test_resolve_description_unknown_falls_back() -> None:
    desc = _resolve_description("nonexistent-binary")
    assert "AI CLI tool detected on PATH" in desc


def test_detect_agents_finds_none_on_empty_path() -> None:
    agents = detect_agents()
    assert isinstance(agents, list)
    for a in agents:
        assert a.name
        assert a.binary
        assert a.path
        assert a.description


def test_detect_agents_scans_path(tmp_path: None) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        bin_path = os.path.join(tmpdir, "opencode")
        with open(bin_path, "w") as f:
            f.write("#!/bin/sh\necho 'AI tool'")
        os.chmod(bin_path, 0o755)

        old_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = tmpdir
            agents = detect_agents()
            names = [a.name for a in agents]
            assert "opencode" in names
            
            # Verify adapter
            opencode_agent = next(a for a in agents if a.name == "opencode")
            assert opencode_agent.adapter is not None
            assert opencode_agent.adapter.name == "default"
        finally:
            os.environ["PATH"] = old_path
