from __future__ import annotations

from state.memory import ConversationTurn
from state.summarizer import ExtractiveSummarizer


def test_extractive_summarizer_empty() -> None:
    summarizer = ExtractiveSummarizer()
    summary = summarizer.summarize([])
    assert summary.turn_count == 0
    assert "General conversation" in summary.content


def test_extractive_summarizer_decisions() -> None:
    summarizer = ExtractiveSummarizer()
    turn = ConversationTurn(
        prompt="we decided to use python",
        response="yes, python is best",
        token_count=10,
    )
    summary = summarizer.summarize([turn])
    assert "Decisions:" in summary.content
    assert "decided" in summary.content.lower()


def test_extractive_summarizer_issues() -> None:
    summarizer = ExtractiveSummarizer()
    turn = ConversationTurn(
        prompt="this bug is causing issues",
        response="we need to fix it",
        token_count=10,
    )
    summary = summarizer.summarize([turn])
    assert "Open Issues:" in summary.content


def test_extractive_summarizer_code_refs() -> None:
    summarizer = ExtractiveSummarizer()
    turn = ConversationTurn(
        prompt="check `main.py` at src/app.py",
        response="function foo is there",
        token_count=10,
    )
    summary = summarizer.summarize([turn])
    assert "Code References:" in summary.content


def test_extractive_summarizer_topics() -> None:
    summarizer = ExtractiveSummarizer()
    turn = ConversationTurn(
        prompt="PythonProject needs work",
        response="yes, PythonProject",
        token_count=10,
    )
    summary = summarizer.summarize([turn])
    assert "Topics:" in summary.content
    assert "PythonProject" in summary.content


def test_extractive_summarizer_multiple_turns() -> None:
    summarizer = ExtractiveSummarizer()
    turns = [
        ConversationTurn(prompt="we decided to use rust", response="good choice", token_count=5),
        ConversationTurn(prompt="error in parser.rs", response="fix the bug", token_count=5),
    ]
    summary = summarizer.summarize(turns)
    assert summary.turn_count == 2
    assert "Decisions:" in summary.content
    assert "Open Issues:" in summary.content
