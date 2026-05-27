from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from orchestration.events import ElyonEvent, EventType, SqliteEventStore


def _make_store(tmp_path: Path | None = None) -> SqliteEventStore:
    db_path = (tmp_path or Path("/tmp")) / "test_events.db"
    return SqliteEventStore(db_path=db_path, max_rows=100)


def test_sqlite_append() -> None:
    async def run():
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            store = SqliteEventStore(db_path=Path(td) / "test.db", max_rows=100)
            event = ElyonEvent.create(
                event_type=EventType.PROMPT_ISSUED,
                payload={"text": "hello"},
                trace_id="trace-1",
                actor="test",
            )
            await store.append(event)
            events = await store.list_all()
            assert len(events) == 1
            assert events[0].event_id == event.event_id

    asyncio.run(run())


def test_sqlite_indexed_query() -> None:
    async def run():
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            store = SqliteEventStore(db_path=Path(td) / "test.db", max_rows=100)
            for i in range(10):
                event = ElyonEvent.create(
                    event_type=EventType.PROMPT_ISSUED if i % 2 == 0 else EventType.PROVIDER_RESPONDED,
                    payload={"idx": i},
                    trace_id=f"trace-{i % 3}",
                    actor="test",
                )
                await store.append(event)
            events = await store.list_by_trace("trace-0")
            assert len(events) == 4

    asyncio.run(run())


def test_sqlite_list_by_type() -> None:
    async def run():
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            store = SqliteEventStore(db_path=Path(td) / "test.db", max_rows=100)
            for i in range(5):
                await store.append(
                    ElyonEvent.create(
                        event_type=EventType.PROMPT_ISSUED,
                        payload={"i": i},
                        trace_id="t",
                        actor="test",
                    )
                )
            for i in range(3):
                await store.append(
                    ElyonEvent.create(
                        event_type=EventType.RUN_FAILED,
                        payload={"i": i},
                        trace_id="t",
                        actor="test",
                    )
                )
            prompts = await store.list_by_type(EventType.PROMPT_ISSUED)
            assert len(prompts) == 5
            failures = await store.list_by_type(EventType.RUN_FAILED)
            assert len(failures) == 3

    asyncio.run(run())


def test_sqlite_append_many() -> None:
    async def run():
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            store = SqliteEventStore(db_path=Path(td) / "test.db", max_rows=100)
            events = [
                ElyonEvent.create(
                    event_type=EventType.PROMPT_ISSUED,
                    payload={"idx": i},
                    trace_id="batch",
                    actor="test",
                )
                for i in range(10)
            ]
            await store.append_many(events)
            all_events = await store.list_all()
            assert len(all_events) == 10

    asyncio.run(run())


def test_sqlite_list_since() -> None:
    async def run():
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            store = SqliteEventStore(db_path=Path(td) / "test.db", max_rows=100)
            for i in range(3):
                await store.append(
                    ElyonEvent.create(
                        event_type=EventType.PROMPT_ISSUED,
                        payload={"i": i},
                        trace_id="t",
                        actor="test",
                    )
                )
            events = await store.list_since(datetime(2000, 1, 1, tzinfo=UTC))
            assert len(events) == 3

    asyncio.run(run())


def test_sqlite_count_by_type() -> None:
    async def run():
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            store = SqliteEventStore(db_path=Path(td) / "test.db", max_rows=100)
            for i in range(5):
                await store.append(
                    ElyonEvent.create(
                        event_type=EventType.PROMPT_ISSUED,
                        payload={"i": i},
                        trace_id="t",
                        actor="test",
                    )
                )
            since = datetime(2000, 1, 1, tzinfo=UTC)
            counts = await store.count_by_type(since)
            total = sum(counts.values())
            assert total >= 5

    asyncio.run(run())


def test_sqlite_get_stats() -> None:
    async def run():
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            store = SqliteEventStore(db_path=Path(td) / "test.db", max_rows=100)
            stats = await store.get_stats()
            assert "active_events" in stats
            assert "active_size_bytes" in stats
            for i in range(10):
                await store.append(
                    ElyonEvent.create(
                        event_type=EventType.PROMPT_ISSUED,
                        payload={"i": i},
                        trace_id="t",
                        actor="test",
                    )
                )
            stats = await store.get_stats()
            assert stats["active_events"] >= 10

    asyncio.run(run())


def test_sqlite_purge_old() -> None:
    async def run():
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            store = SqliteEventStore(db_path=Path(td) / "test.db", max_rows=100)
            for i in range(5):
                await store.append(
                    ElyonEvent.create(
                        event_type=EventType.PROMPT_ISSUED,
                        payload={"i": i},
                        trace_id="t",
                        actor="test",
                    )
                )
            deleted = await store.purge_old(datetime(2099, 1, 1, tzinfo=UTC))
            assert isinstance(deleted, int)
            assert deleted == 5

    asyncio.run(run())
