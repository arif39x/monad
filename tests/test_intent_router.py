from __future__ import annotations

from orchestration.routing import Intent, IntentRouter


def _router(**kwargs) -> IntentRouter:
    return IntentRouter(**kwargs)


def test_classify_shell_command() -> None:
    router = _router()
    result = router.classify("list files in src/")
    assert result.intent == Intent.SHELL_COMMAND
    assert result.confidence >= 0.7


def test_classify_git_command() -> None:
    router = _router()
    result = router.classify("git status")
    assert result.intent == Intent.SHELL_COMMAND
    assert result.confidence >= 0.7


def test_classify_file_operation() -> None:
    router = _router()
    result = router.classify("read main.py")
    assert result.intent == Intent.FILE_OPERATION
    assert result.confidence >= 0.7


def test_classify_code_gen() -> None:
    router = _router(enabled=True)
    result = router.classify("write a function that calculates fibonacci")
    assert result.intent == Intent.CODE_GENERATION
    assert result.confidence >= 0.7


def test_classify_explanation() -> None:
    router = _router()
    result = router.classify("explain this code to me")
    assert result.intent == Intent.EXPLANATION


def test_classify_debugging() -> None:
    router = _router()
    result = router.classify("fix this error in my code")
    assert result.intent == Intent.DEBUGGING


def test_classify_ambiguous() -> None:
    router = _router()
    result = router.classify("banana yellow fruit")
    assert result.intent == Intent.AMBIGUOUS


def test_classify_empty() -> None:
    router = _router()
    result = router.classify("")
    assert result.intent == Intent.AMBIGUOUS
    assert result.confidence == 0.0


def test_disabled_router() -> None:
    router = _router(enabled=False)
    result = router.classify("list files")
    assert result.intent == Intent.AMBIGUOUS


def test_shell_translation() -> None:
    router = _router()
    cmd = router.translate_to_shell("list files in src/")
    assert "ls" in cmd


def test_file_path_extraction() -> None:
    router = _router()
    result = router.classify("read main.py")
    assert result.file_path == "main.py"


def test_classify_shell_with_path() -> None:
    router = _router()
    result = router.classify("ls src/components")
    assert result.intent == Intent.SHELL_COMMAND
    assert result.command is not None


def test_classify_pwd() -> None:
    router = _router()
    result = router.classify("pwd")
    assert result.intent == Intent.SHELL_COMMAND
    assert result.confidence >= 0.9
