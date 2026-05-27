from __future__ import annotations

from datetime import UTC, datetime

from state.memory import (
    ConversationTurn,
    SessionMemoryManager,
    SessionSummary,
    TokenBudgetTracker,
    WorkingMemory,
)


def test_conversation_turn_defaults() -> None:
    turn = ConversationTurn(prompt="hello", response="world")
    assert turn.prompt == "hello"
    assert turn.response == "world"
    assert turn.token_count == 0
    assert isinstance(turn.timestamp, datetime)


def test_conversation_turn_compact() -> None:
    turn = ConversationTurn(prompt="a" * 200, response="b" * 400)
    compact = turn.compact()
    assert "..." in compact
    assert "User:" in compact
    assert "Assistant:" in compact


def test_working_memory_append() -> None:
    wm = WorkingMemory(max_turns=3, max_tokens=100)
    assert len(wm) == 0
    wm.append(ConversationTurn(prompt="hi", response="there", token_count=10))
    assert len(wm) == 1
    assert wm.tokens == 10


def test_working_memory_overflow() -> None:
    wm = WorkingMemory(max_turns=5, max_tokens=50)
    wm.append(ConversationTurn(prompt="", response="", token_count=30))
    assert wm.overflow() is False
    wm.append(ConversationTurn(prompt="", response="", token_count=30))
    assert wm.overflow() is True


def test_working_memory_pop_oldest() -> None:
    wm = WorkingMemory(max_turns=5, max_tokens=100)
    wm.append(ConversationTurn(prompt="a", response="1", token_count=10))
    wm.append(ConversationTurn(prompt="b", response="2", token_count=10))
    removed = wm.pop_oldest(1)
    assert len(removed) == 1
    assert removed[0].prompt == "a"
    assert wm.tokens == 10


def test_working_memory_recent() -> None:
    wm = WorkingMemory(max_turns=10, max_tokens=100)
    for i in range(5):
        wm.append(ConversationTurn(prompt=str(i), response=str(i)))
    recent = wm.recent(2)
    assert len(recent) == 2
    assert recent[0].prompt == "3"


def test_working_memory_max_turns() -> None:
    wm = WorkingMemory(max_turns=3, max_tokens=1000)
    for i in range(5):
        wm.append(ConversationTurn(prompt=str(i), response=str(i)))
    assert len(wm) == 3


def test_token_budget_tracker() -> None:
    tbt = TokenBudgetTracker(total_budget=1000)
    assert tbt.remaining == 1000
    tbt.record_usage(300)
    assert tbt.total_used == 300
    assert tbt.remaining == 700


def test_token_budget_recommended_truncation() -> None:
    tbt = TokenBudgetTracker(total_budget=100)
    assert tbt.recommended_truncation() == "ok"
    tbt.record_usage(60)
    assert tbt.recommended_truncation() == "caution"
    tbt.record_usage(25)
    assert tbt.recommended_truncation() == "warning"
    tbt.record_usage(15)
    assert tbt.recommended_truncation() == "critical"


def test_session_summary_compact() -> None:
    summary = SessionSummary(content="test content here", turn_count=3)
    compact = summary.compact()
    assert "test content" in compact
    assert "3 turns" in compact


def test_session_memory_manager_append() -> None:
    mgr = SessionMemoryManager()
    mgr.append_turn(ConversationTurn(prompt="hi", response="there", token_count=10))
    assert len(mgr.working_memory) == 1
    assert mgr.token_budget.total_used == 10


def test_session_memory_manager_needs_summarization() -> None:
    mgr = SessionMemoryManager(
        working_memory_max_tokens=50,
        auto_summarize_threshold_tokens=30,
    )
    assert mgr.needs_summarization() is False
    mgr.append_turn(ConversationTurn(prompt="", response="", token_count=20))
    assert mgr.needs_summarization() is False  # only 1 turn
    mgr.append_turn(ConversationTurn(prompt="", response="", token_count=20))
    assert mgr.needs_summarization() is True  # 40 > 30 and len > 2


def test_session_memory_manager_push_summary() -> None:
    mgr = SessionMemoryManager(summarized_memory_max_depth=3)
    for i in range(4):
        mgr.push_summary(SessionSummary(content=f"summary_{i}", turn_count=1))
    assert len(mgr.summarized_memory) == 1
    assert "META SUMMARY" in mgr.summarized_memory[0].content


def test_session_memory_build_context() -> None:
    mgr = SessionMemoryManager()
    context = mgr.build_context()
    assert context == ""

    mgr.append_turn(ConversationTurn(prompt="hello", response="world", token_count=10))
    context = mgr.build_context()
    assert "hello" in context
    assert "world" in context


def test_session_memory_serialize_roundtrip() -> None:
    mgr = SessionMemoryManager()
    mgr.append_turn(ConversationTurn(prompt="hello", response="world", token_count=10))
    mgr.push_summary(SessionSummary(content="test summary", turn_count=2))
    serialized = mgr.serialize()
    restored = SessionMemoryManager.deserialize(serialized)
    assert len(restored.summarized_memory) == 1
    assert restored.summarized_memory[0].content == "test summary"
    assert restored.token_budget.total_used == 10


def test_session_memory_deserialize_invalid() -> None:
    restored = SessionMemoryManager.deserialize("not json")
    assert len(restored.summarized_memory) == 0
    assert restored.token_budget.total_used == 0


def test_session_memory_deserialize_empty() -> None:
    restored = SessionMemoryManager.deserialize("")
    assert len(restored.summarized_memory) == 0
