from __future__ import annotations

import asyncio

import pytest

from bindings import NullRuntimeClient
from orchestration.config import ElyonSettings
from orchestration.engine import ElyonEngine
from orchestration.events import EventType, InMemoryEventStore
from providers import ProviderRegistry
from providers.base import ProviderRequest, ProviderResponse
from state import InMemorySessionStore


class SlowProvider:
    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        await asyncio.sleep(request.timeout_seconds * 2)
        return ProviderResponse(text="never", usage_input_tokens=0, usage_output_tokens=0, latency_ms=0)

    async def stream_complete(self, request: ProviderRequest):
        yield ""


def _settings() -> ElyonSettings:
    return ElyonSettings.model_validate(
        {
            "default_provider": "slow",
            "providers": {
                "slow": {
                    "name": "slow",
                    "base_url": "",
                    "model": "test-model",
                    "default_temperature": 0.0,
                    "default_max_tokens": 64,
                    "timeout_seconds": 0.05,
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


def test_engine_timeout_emits_failure_event() -> None:
    async def scenario() -> None:
        settings = _settings()
        events = InMemoryEventStore()
        sessions = InMemorySessionStore()
        registry = ProviderRegistry()
        registry.register_factory("slow", lambda: SlowProvider())

        engine = ElyonEngine(
            settings=settings,
            event_store=events,
            session_store=sessions,
            provider_registry=registry,
            runtime_client=NullRuntimeClient(),
        )

        trace_id = "trace-timeout"
        with pytest.raises(TimeoutError):
            await engine.run_prompt(
                prompt="test",
                provider_name="slow",
                trace_id=trace_id,
                stream=False,
            )

        trace_events = await events.list_by_trace(trace_id)
        assert any(event.event_type is EventType.RUN_FAILED for event in trace_events)

    asyncio.run(scenario())
