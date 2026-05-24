from __future__ import annotations

import asyncio

from orchestration.config import ElyonSettings
from orchestration.engine import ElyonEngine
from orchestration.events import InMemoryEventStore
from providers import ProviderRegistry
from providers.base import ProviderRequest, ProviderResponse
from state import InMemorySessionStore


class EchoProvider:
    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(text=f"echo: {request.prompt}", usage_input_tokens=5, usage_output_tokens=10, latency_ms=1)

    async def stream_complete(self, request: ProviderRequest):
        yield request.prompt


class FailingProvider:
    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        raise RuntimeError("provider failure")

    async def stream_complete(self, request: ProviderRequest):
        yield ""


def _settings() -> ElyonSettings:
    return ElyonSettings.model_validate({
        "default_provider": "echo",
        "providers": {
            "echo": {
                "name": "echo", "base_url": "", "model": "m",
                "default_temperature": 0.0, "default_max_tokens": 64,
                "timeout_seconds": 5.0, "max_retries": 0, "api_key_env": "",
            },
            "echo2": {
                "name": "echo2", "base_url": "", "model": "m",
                "default_temperature": 0.0, "default_max_tokens": 64,
                "timeout_seconds": 5.0, "max_retries": 0, "api_key_env": "",
            },
        },
        "runtime": {"command": ["run"], "request_timeout_seconds": 1.0,
                     "max_stdout_bytes": 1024, "max_stderr_bytes": 1024},
        "repair": {"max_attempts": 3, "verify_after_repair": True, "allowed_extensions": [".py"]},
        "telemetry": {"log_level": "INFO", "json_logs": True},
        "sandbox": {"allowed_command_prefixes": ["pytest"], "allowed_read_roots": ["."], "allowed_write_roots": ["."]},
        "state": {"event_log_path": "./state/test-events.jsonl"},
    })


def test_run_prompt_parallel_returns_all_results() -> None:
    async def scenario() -> None:
        registry = ProviderRegistry()
        registry.register_factory("echo", lambda: EchoProvider())
        registry.register_factory("echo2", lambda: EchoProvider())

        engine = ElyonEngine(
            settings=_settings(),
            event_store=InMemoryEventStore(),
            session_store=InMemorySessionStore(),
            provider_registry=registry,
            runtime_client=None,  # type: ignore[arg-type]
        )

        results = await engine.run_prompt_parallel(
            prompt="hello",
            providers=["echo", "echo2"],
            trace_id="trace-parallel",
        )
        assert len(results) == 2
        assert "echo: hello" in results[0]
        assert "echo: hello" in results[1]

    asyncio.run(scenario())


def test_run_prompt_parallel_propagates_failures() -> None:
    async def scenario() -> None:
        registry = ProviderRegistry()
        registry.register_factory("echo", lambda: EchoProvider())
        registry.register_factory("echo2", lambda: FailingProvider())

        engine = ElyonEngine(
            settings=_settings(),
            event_store=InMemoryEventStore(),
            session_store=InMemorySessionStore(),
            provider_registry=registry,
            runtime_client=None,  # type: ignore[arg-type]
        )

        with __import__("pytest").raises(RuntimeError, match="provider failure"):
            await engine.run_prompt_parallel(
                prompt="test",
                providers=["echo", "echo2"],
                trace_id="trace-fail",
            )

    asyncio.run(scenario())


def test_run_prompt_parallel_single_provider() -> None:
    async def scenario() -> None:
        registry = ProviderRegistry()
        registry.register_factory("echo", lambda: EchoProvider())

        engine = ElyonEngine(
            settings=_settings(),
            event_store=InMemoryEventStore(),
            session_store=InMemorySessionStore(),
            provider_registry=registry,
            runtime_client=None,  # type: ignore[arg-type]
        )

        results = await engine.run_prompt_parallel(
            prompt="single",
            providers=["echo"],
            trace_id="trace-single",
        )
        assert len(results) == 1
        assert "single" in results[0]

    asyncio.run(scenario())
