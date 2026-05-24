from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Protocol

from orchestration.events.models import EventType, ElyonEvent


class EventStore(Protocol):
    async def append(self, event: ElyonEvent) -> None: ...

    async def list_all(self) -> list[ElyonEvent]: ...

    async def list_by_trace(self, trace_id: str) -> list[ElyonEvent]: ...


class InMemoryEventStore:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._events: list[ElyonEvent] = []

    async def append(self, event: ElyonEvent) -> None:
        async with self._lock:
            self._events.append(event)

    async def append_many(self, events: list[ElyonEvent]) -> None:
        async with self._lock:
            self._events.extend(events)

    async def list_all(self) -> list[ElyonEvent]:
        async with self._lock:
            return list(self._events)

    async def list_by_trace(self, trace_id: str) -> list[ElyonEvent]:
        events = await self.list_all()
        return [event for event in events if event.metadata.trace_id == trace_id]

    async def list_by_type(self, event_type: EventType) -> list[ElyonEvent]:
        events = await self.list_all()
        return [event for event in events if event.event_type == event_type]


class JsonlEventStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    async def append(self, event: ElyonEvent) -> None:
        line = json.dumps(event.model_dump(mode="json"), separators=(",", ":"))
        def _write():
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.write("\n")
        async with self._lock:
            await asyncio.to_thread(_write)

    async def list_all(self) -> list[ElyonEvent]:
        async with self._lock:
            if not self._path.exists():
                return []
            def _read():
                with self._path.open("r", encoding="utf-8") as handle:
                    return handle.readlines()
            lines = await asyncio.to_thread(_read)
        return [ElyonEvent.model_validate_json(line) for line in lines if line.strip()]

    async def list_by_trace(self, trace_id: str) -> list[ElyonEvent]:
        events = await self.list_all()
        return [event for event in events if event.metadata.trace_id == trace_id]
