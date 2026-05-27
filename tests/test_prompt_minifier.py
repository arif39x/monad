from __future__ import annotations

from orchestration.minify import PromptMinifier


def test_whitespace_reduction() -> None:
    minifier = PromptMinifier(enabled=True)
    text = "line1\n\n\n\nline2\n   \nline3  "
    result, report = minifier.minify(text)
    assert "\n\n\n\n" not in result
    assert result == result.strip()


def test_label_shortening() -> None:
    minifier = PromptMinifier(enabled=True)
    text = "File: /path/to/main.py\nContent:\ndef foo(): pass"
    result, report = minifier.minify(text)
    assert "# main.py" in result
    assert "File:" not in result


def test_json_compaction() -> None:
    minifier = PromptMinifier(enabled=True, structural_only=False)
    text = 'data = {\n    "key": "value",\n    "num": 42\n}'
    result, report = minifier.minify(text)
    assert '"key":"value"' in result or '"key": "value"' in result
    assert report.stages_applied


def test_user_message_preserved() -> None:
    minifier = PromptMinifier(enabled=True, target_tokens=20)
    system = "System: " + "x" * 200
    user = "User: can you fix this error?"
    text = f"{system}\n\n{user}"
    result, report = minifier.minify(text)
    assert "can you fix this error" in result


def test_empty_prompt() -> None:
    minifier = PromptMinifier(enabled=True)
    result, report = minifier.minify("")
    assert result == ""
    assert report.original_tokens == 0
    assert report.final_tokens == 0


def test_minification_ratio() -> None:
    minifier = PromptMinifier(enabled=True)
    text = "File: /a/b/c.py\nContent:\n" + "x" * 1000
    result, report = minifier.minify(text)
    assert 0 < report.ratio <= 1.0
    assert report.original_tokens > 0
    assert report.final_tokens > 0


def test_disabled_minifier() -> None:
    minifier = PromptMinifier(enabled=False)
    text = "Hello world!"
    result, report = minifier.minify(text)
    assert result == text
    assert report.ratio == 1.0


def test_structural_only_mode() -> None:
    minifier = PromptMinifier(enabled=True, structural_only=True)
    text = "line1\n\n\n\n\nline2\n   \nline3  "
    result, report = minifier.minify(text)
    applied = report.stages_applied
    assert "whitespace" in applied or "labels" in applied or "structs" in applied


def test_system_prompt_compression() -> None:
    minifier = PromptMinifier(enabled=True, structural_only=False)
    text = "You are an AI assistant. You must follow these instructions:\nAnalyze the code\n"
    result, report = minifier.minify(text)
    assert "#SYSTEM:" in result or len(result) < len(text)


def test_hard_limit_enforcement() -> None:
    minifier = PromptMinifier(enabled=True, hard_limit=10)
    text = "hello world and welcome to the universe of python programming"
    result, report = minifier.minify(text)
    assert len(result) < len(text) or result == text
