from __future__ import annotations

import asyncio

from orchestration.events import EventType, InMemoryEventStore, ElyonEvent


def test_in_memory_event_store_persists_events_by_trace() -> None:
    async def scenario() -> None:
        store = InMemoryEventStore()

        first = ElyonEvent.create(
            event_type=EventType.PROMPT_ISSUED,
            payload={"index": 1},
            trace_id="trace-a",
            actor="planner",
        )
        second = ElyonEvent.create(
            event_type=EventType.PROVIDER_RESPONDED,
            payload={"index": 2},
            trace_id="trace-b",
            actor="planner",
        )

        await store.append(first)
        await store.append(second)

        trace_a_events = await store.list_by_trace("trace-a")
        assert [event.event_id for event in trace_a_events] == [first.event_id]

    asyncio.run(scenario())


def test_event_store_supports_concurrent_appends() -> None:
    async def scenario() -> None:
        store = InMemoryEventStore()

        async def append_event(index: int) -> None:
            event = ElyonEvent.create(
                event_type=EventType.SUBPROCESS_SPAWNED,
                payload={"index": index},
                trace_id="trace-concurrency",
                actor="verifier",
            )
            await store.append(event)

        await asyncio.gather(*(append_event(index) for index in range(50)))

        events = await store.list_by_trace("trace-concurrency")
        assert len(events) == 50

    asyncio.run(scenario())
