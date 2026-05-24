from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field


class EventType(str, Enum):
    PROMPT_ISSUED = "prompt_issued"
    PROVIDER_REQUESTED = "provider_requested"
    PROVIDER_RESPONDED = "provider_responded"
    COMPILE_EXECUTED = "compile_executed"
    DIAGNOSTIC_EMITTED = "diagnostic_emitted"
    REPAIR_GENERATED = "repair_generated"
    PATCH_APPLIED = "patch_applied"
    SUBPROCESS_SPAWNED = "subprocess_spawned"
    RUN_FAILED = "run_failed"


class EventMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)

    trace_id: str
    actor: str
    occurred_at: datetime
    duration_ms: int | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ElyonEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    event_type: EventType
    payload: dict[str, Any]
    metadata: EventMetadata

    @classmethod
    def create(
        cls,
        *,
        event_type: EventType,
        payload: dict[str, Any],
        trace_id: str,
        actor: str,
        duration_ms: int | None = None,
        context: dict[str, Any] | None = None,
    ) -> "ElyonEvent":
        return cls(
            event_id=str(uuid4()),
            event_type=event_type,
            payload=payload,
            metadata=EventMetadata(
                trace_id=trace_id,
                actor=actor,
                occurred_at=datetime.now(tz=UTC),
                duration_ms=duration_ms,
                context=context or {},
            ),
        )
