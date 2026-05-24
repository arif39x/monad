from __future__ import annotations

import asyncio

import pytest

from bindings import RuntimeExecRequest, RuntimeExecResponse, RuntimeExecutionError
from orchestration.config import ElyonSettings
from orchestration.engine import ElyonEngine
from orchestration.events import EventType, InMemoryEventStore
from providers import ProviderRegistry
from state import InMemorySessionStore


class SuccessRuntimeClient:
    async def execute(self, request: RuntimeExecRequest) -> RuntimeExecResponse:
        return RuntimeExecResponse(
            exit_code=0,
            stdout='{"code":"E1","message":"ok","severity":"note","span":{"path":"a.zero","line":1,"column":1}}',
            stderr="",
            duration_ms=5,
        )


class FailingRuntimeClient:
    async def execute(self, request: RuntimeExecRequest) -> RuntimeExecResponse:
        raise RuntimeExecutionError("runtime failed")


def _settings() -> ElyonSettings:
    return ElyonSettings.model_validate(
        {
            "default_provider": "mock",
            "providers": {
                "mock": {
                    "name": "mock",
                    "base_url": "",
                    "model": "test-model",
                    "default_temperature": 0.0,
                    "default_max_tokens": 64,
                    "timeout_seconds": 0.1,
                    "max_retries": 0,
                    "api_key_env": "",
                }
            },
            "runtime": {
                "command": ["runtime"],
                "request_timeout_seconds": 1.0,
                "max_stdout_bytes": 1024,
                "max_stderr_bytes": 1024,
            },
            "repair": {
                "max_attempts": 3,
                "verify_after_repair": True,
                "allowed_extensions": [".py"],
            },
            "telemetry": {"log_level": "INFO", "json_logs": True},
            "sandbox": {
                "allowed_command_prefixes": ["pytest"],
                "allowed_read_roots": ["."],
                "allowed_write_roots": ["."],
            },
            "state": {"event_log_path": "./state/test-events.jsonl"},
        }
    )


def test_execute_runtime_command_emits_success_events() -> None:
    async def scenario() -> None:
        events = InMemoryEventStore()
        engine = ElyonEngine(
            settings=_settings(),
            event_store=events,
            session_store=InMemorySessionStore(),
            provider_registry=ProviderRegistry(),
            runtime_client=SuccessRuntimeClient(),
        )

        response = await engine.execute_runtime_command(command=["pytest", "-q"], cwd=".", trace_id="trace-ok")

        assert response.exit_code == 0
        trace_events = await events.list_by_trace("trace-ok")
        event_types = [event.event_type for event in trace_events]
        assert EventType.SUBPROCESS_SPAWNED in event_types
        assert EventType.COMPILE_EXECUTED in event_types

    asyncio.run(scenario())


def test_execute_runtime_command_emits_failure_event() -> None:
    async def scenario() -> None:
        events = InMemoryEventStore()
        engine = ElyonEngine(
            settings=_settings(),
            event_store=events,
            session_store=InMemorySessionStore(),
            provider_registry=ProviderRegistry(),
            runtime_client=FailingRuntimeClient(),
        )

        with pytest.raises(RuntimeExecutionError):
            await engine.execute_runtime_command(command=["pytest", "-q"], cwd=".", trace_id="trace-fail")

        trace_events = await events.list_by_trace("trace-fail")
        assert any(event.event_type is EventType.RUN_FAILED for event in trace_events)

    asyncio.run(scenario())
