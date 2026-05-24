from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from state.session import InMemorySessionStore, SessionState


def test_session_state_create() -> None:
    session = SessionState.create(attributes={"origin": "test"})
    assert session.session_id is not None
    assert session.attributes["origin"] == "test"
    assert session.event_ids == ()
    assert isinstance(session.created_at, datetime)


def test_session_state_default_attributes() -> None:
    session = SessionState.create()
    assert session.attributes == {}


def test_session_state_with_event() -> None:
    session = SessionState.create()
    updated = session.with_event("evt-1")
    assert updated.event_ids == ("evt-1",)
    assert session.event_ids == ()


def test_session_state_multiple_events() -> None:
    session = SessionState.create()
    s1 = session.with_event("evt-1")
    s2 = s1.with_event("evt-2")
    assert s2.event_ids == ("evt-1", "evt-2")


def test_session_state_immutable() -> None:
    session = SessionState.create()
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        session.session_id = "changed"


def test_store_create_and_get() -> None:
    async def scenario() -> None:
        store = InMemorySessionStore()
        created = await store.create(attributes={"user": "alice"})
        retrieved = await store.get(created.session_id)
        assert retrieved is not None
        assert retrieved.attributes["user"] == "alice"

    asyncio.run(scenario())


def test_store_get_missing() -> None:
    async def scenario() -> None:
        store = InMemorySessionStore()
        result = await store.get("nonexistent")
        assert result is None

    asyncio.run(scenario())


def test_store_upsert() -> None:
    async def scenario() -> None:
        store = InMemorySessionStore()
        session = await store.create()
        updated = session.with_event("evt-1")
        await store.upsert(updated)
        retrieved = await store.get(session.session_id)
        assert retrieved is not None
        assert "evt-1" in retrieved.event_ids

    asyncio.run(scenario())
