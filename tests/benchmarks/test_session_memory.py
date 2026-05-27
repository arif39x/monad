from __future__ import annotations

import time

from state.memory import ConversationTurn, SessionMemoryManager, WorkingMemory
from state.summarizer import ExtractiveSummarizer


class TestWorkingMemoryBenchmarks:
    def test_working_memory_append(self) -> None:
        wm = WorkingMemory(max_turns=10, max_tokens=10000)
        turn = ConversationTurn(prompt="hello world", response="hi there", token_count=10)
        start = time.perf_counter()
        for _ in range(1000):
            wm.append(turn)
        elapsed = (time.perf_counter() - start) / 1000
        assert elapsed < 0.001

    def test_working_memory_pop(self) -> None:
        wm = WorkingMemory(max_turns=10, max_tokens=10000)
        for i in range(10):
            wm.append(ConversationTurn(prompt=str(i), response=str(i), token_count=5))
        start = time.perf_counter()
        for _ in range(1000):
            wm.pop_oldest(1)
            wm.append(ConversationTurn(prompt="new", response="new", token_count=5))
        elapsed = (time.perf_counter() - start) / 1000
        assert elapsed < 0.001


class TestSummarizerBenchmarks:
    def test_extractive_summarize(self) -> None:
        summarizer = ExtractiveSummarizer()
        turns = [ConversationTurn(prompt="we decided to use python", response="good", token_count=5) for _ in range(5)]
        start = time.perf_counter()
        for _ in range(500):
            summarizer.summarize(turns)
        elapsed = (time.perf_counter() - start) / 500
        assert elapsed < 0.005


class TestMemoryManagerBenchmarks:
    def test_serialize_deserialize(self) -> None:
        mgr = SessionMemoryManager()
        for i in range(5):
            mgr.append_turn(ConversationTurn(prompt=f"prompt{i}", response=f"resp{i}", token_count=10))
        serialized = mgr.serialize()
        start = time.perf_counter()
        for _ in range(1000):
            restored = SessionMemoryManager.deserialize(serialized)
        elapsed = (time.perf_counter() - start) / 1000
        assert elapsed < 0.005

    def test_build_context(self) -> None:
        mgr = SessionMemoryManager()
        for i in range(10):
            mgr.append_turn(ConversationTurn(prompt=f"prompt{i}", response=f"resp{i}", token_count=10))
        start = time.perf_counter()
        for _ in range(1000):
            mgr.build_context()
        elapsed = (time.perf_counter() - start) / 1000
        assert elapsed < 0.001
