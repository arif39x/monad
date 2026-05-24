from __future__ import annotations

from pathlib import Path

from compiler.zero_compiler import (
    ZeroModule,
    compile_zero,
    estimate_token_reduction,
    optimize_module,
    parse_zero_file,
    _count_tokens,
)


def test_count_tokens() -> None:
    assert _count_tokens("") == 0
    assert _count_tokens("hello") == 1
    assert _count_tokens("hello world foo") == 3


def test_parse_zero_file_counts_tokens(tmp_path: Path) -> None:
    zf = tmp_path / "test.zero"
    zf.write_text("task \"refactor\"\nprompt \"fix bugs\"\n")
    module = parse_zero_file(zf)
    assert module.path == str(zf)
    assert len(module.directives) == 2
    assert module.directives[0].kind == "task"
    assert module.directives[1].kind == "prompt"
    assert module.raw_token_count > 0


def test_parse_zero_file_skips_comments(tmp_path: Path) -> None:
    zf = tmp_path / "commented.zero"
    zf.write_text("# comment line\n// also comment\ntask \"real\"\n")
    module = parse_zero_file(zf)
    assert len(module.directives) == 1
    assert module.directives[0].content == 'task "real"'


def test_parse_zero_file_detects_agent_directive(tmp_path: Path) -> None:
    zf = tmp_path / "agent.zero"
    zf.write_text('agent "opencode"\n')
    module = parse_zero_file(zf)
    assert module.directives[0].kind == "agent"


def test_parse_zero_file_unknown_directive(tmp_path: Path) -> None:
    zf = tmp_path / "unknown.zero"
    zf.write_text("some random line\n")
    module = parse_zero_file(zf)
    assert module.directives[0].kind == "directive"


def test_optimize_module_removes_commentary() -> None:
    raw = "do stuff\nbasically this is unnecessary\nessentially verbose\n"
    optimized = optimize_module(raw, [])
    assert "do stuff" in optimized
    assert "basically" not in optimized
    assert "essentially" not in optimized


def test_optimize_module_keeps_normal_lines() -> None:
    raw = "task \"build\"\nprompt \"test\"\n"
    optimized = optimize_module(raw, [])
    assert "task" in optimized
    assert "prompt" in optimized


def test_optimize_module_removes_shell_comments() -> None:
    raw = "# shell comment\ntask real\n"
    optimized = optimize_module(raw, [])
    assert "# shell comment" not in optimized


def test_estimate_token_reduction_zero_raw() -> None:
    module = ZeroModule(path="test.zero", directives=[], raw_token_count=0, optimized_token_count=0)
    result = estimate_token_reduction(module)
    assert result["savings_pct"] == 0
    assert result["sdr"] == 0.0


def test_estimate_token_reduction_with_savings() -> None:
    module = ZeroModule(path="test.zero", directives=[], raw_token_count=100, optimized_token_count=30)
    result = estimate_token_reduction(module)
    assert result["savings_tokens"] == 70
    assert result["savings_pct"] == 70.0
    assert result["sdr"] == 0.7


def test_compile_zero_returns_expected_keys(tmp_path: Path) -> None:
    zf = tmp_path / "sample.zero"
    zf.write_text("task \"one\"\nprompt \"two\"\n")
    result = compile_zero(zf)
    assert result["status"] == "ok"
    assert result["path"] == str(zf)
    assert result["directives"] == 2
    assert "raw_token_count" in result
    assert "optimized_token_count" in result
    assert "can_optimize" in result


def test_compile_zero_no_optimization_needed(tmp_path: Path) -> None:
    zf = tmp_path / "clean.zero"
    zf.write_text("task build\n")
    result = compile_zero(zf)
    assert result["status"] == "ok"
    assert result["directives"] == 1
