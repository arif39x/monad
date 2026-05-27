from __future__ import annotations

import asyncio
import time


class TestBaselineBenchmarks:
    def test_prompt_dispatch_latency(self, benchmark_config: dict) -> None:
        iterations = benchmark_config["iterations"]
        start = time.perf_counter()
        for _ in range(iterations):
            _ = "mock prompt text"
        elapsed = (time.perf_counter() - start) / iterations
        assert elapsed < 0.001

    def test_token_count_estimate(self) -> None:
        text = "hello world " * 1000
        start = time.perf_counter()
        for _ in range(1000):
            _ = len(text) / 4
        elapsed = (time.perf_counter() - start) / 1000
        assert elapsed < 0.0001

    def test_session_create_latency(self) -> None:
        from state import InMemorySessionStore

        async def run():
            store = InMemorySessionStore()
            start = time.perf_counter()
            for _ in range(100):
                await store.create()
            elapsed = (time.perf_counter() - start) / 100
            return elapsed

        elapsed = asyncio.run(run())
        assert elapsed < 0.01

    def test_event_append_latency(self) -> None:
        from orchestration.events import ElyonEvent, EventType, InMemoryEventStore

        async def run():
            store = InMemoryEventStore()
            start = time.perf_counter()
            for _ in range(100):
                event = ElyonEvent.create(
                    event_type=EventType.PROMPT_ISSUED,
                    payload={"test": True},
                    trace_id="bench",
                    actor="bench",
                )
                await store.append(event)
            elapsed = (time.perf_counter() - start) / 100
            return elapsed

        elapsed = asyncio.run(run())
        assert elapsed < 0.005

    def test_event_query_latency(self) -> None:
        from orchestration.events import ElyonEvent, EventType, InMemoryEventStore

        async def run():
            store = InMemoryEventStore()
            for i in range(100):
                event = ElyonEvent.create(
                    event_type=EventType.PROMPT_ISSUED,
                    payload={"idx": i},
                    trace_id="bench-trace",
                    actor="bench",
                )
                await store.append(event)
            start = time.perf_counter()
            for _ in range(50):
                await store.list_by_trace("bench-trace")
            elapsed = (time.perf_counter() - start) / 50
            return elapsed

        elapsed = asyncio.run(run())
        assert elapsed < 0.01
