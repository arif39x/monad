from __future__ import annotations

import asyncio
import time

from providers.base import ProviderRequest, ProviderResponse
from providers.middleware import (
    CacheMiddleware,
    LoggingMiddleware,
    Middleware,
    MiddlewarePipeline,
    RateLimitMiddleware,
    RetryMiddleware,
)


def test_middleware_pipeline_empty() -> None:
    pipeline = MiddlewarePipeline()

    async def dispatch(req: ProviderRequest) -> ProviderResponse:
        return ProviderResponse(text="ok", usage_input_tokens=0, usage_output_tokens=0, latency_ms=0)

    request = ProviderRequest(prompt="test", model="m", temperature=0.0, max_tokens=10, trace_id="t1")

    async def run() -> str:
        response = await pipeline.run(request, dispatch)
        return response.text

    result = asyncio.run(run())
    assert result == "ok"


def test_middleware_before_after() -> None:
    events: list[str] = []

    class TestMiddleware(Middleware):
        async def before(self, request: ProviderRequest) -> ProviderRequest:
            events.append("before")
            return request

        async def after(self, request: ProviderRequest, response: ProviderResponse) -> ProviderResponse:
            events.append("after")
            return response

    pipeline = MiddlewarePipeline()
    pipeline.add(TestMiddleware())

    async def dispatch(req: ProviderRequest) -> ProviderResponse:
        events.append("dispatch")
        return ProviderResponse(text="ok", usage_input_tokens=0, usage_output_tokens=0, latency_ms=0)

    request = ProviderRequest(prompt="test", model="m", temperature=0.0, max_tokens=10, trace_id="t2")

    async def run() -> None:
        await pipeline.run(request, dispatch)

    asyncio.run(run())
    assert events == ["before", "dispatch", "after"]


def test_rate_limit_middleware() -> None:
    rl = RateLimitMiddleware(max_per_minute=1000, burst=100)
    request = ProviderRequest(prompt="test", model="m", temperature=0.0, max_tokens=10, trace_id="t3")

    async def run() -> None:
        for _ in range(10):
            await rl.before(request)

    asyncio.run(run())


def test_retry_middleware_max_retries() -> None:
    retry = RetryMiddleware(max_retries=2, base_delay_ms=1.0)
    request = ProviderRequest(prompt="test", model="m", temperature=0.0, max_tokens=10, trace_id="t4")
    call_count = 0

    async def failing_dispatch(req: ProviderRequest) -> ProviderResponse:
        nonlocal call_count
        call_count += 1
        raise RuntimeError("Transient error")

    async def run() -> None:
        import pytest
        with pytest.raises(RuntimeError):
            await retry.dispatch_with_retry(request, failing_dispatch)

    asyncio.run(run())
    assert call_count == 3  # max_retries + 1


def test_retry_middleware_succeeds() -> None:
    retry = RetryMiddleware(max_retries=2, base_delay_ms=1.0)
    request = ProviderRequest(prompt="success", model="m", temperature=0.0, max_tokens=10, trace_id="t5")
    call_count = 0

    async def eventually_succeeds(req: ProviderRequest) -> ProviderResponse:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RuntimeError("First attempt fails")
        return ProviderResponse(text="success", usage_input_tokens=0, usage_output_tokens=0, latency_ms=0)

    async def run() -> str:
        response = await retry.dispatch_with_retry(request, eventually_succeeds)
        return response.text

    result = asyncio.run(run())
    assert result == "success"
    assert call_count == 2


def test_cache_middleware_hit() -> None:
    cache = CacheMiddleware(enabled=True, ttl_seconds=60)
    request = ProviderRequest(prompt="hello", model="m", temperature=0.0, max_tokens=10, trace_id="t6")

    async def run() -> None:
        cached = await cache.check_cache(request)
        assert cached is None
        response = ProviderResponse(text="cached", usage_input_tokens=0, usage_output_tokens=0, latency_ms=0)
        await cache.store_cache(request, response)
        cached = await cache.check_cache(request)
        assert cached is not None
        assert cached.text == "cached"

    asyncio.run(run())


def test_cache_middleware_disabled() -> None:
    cache = CacheMiddleware(enabled=False)
    request = ProviderRequest(prompt="test", model="m", temperature=0.0, max_tokens=10, trace_id="t7")

    async def run() -> None:
        cached = await cache.check_cache(request)
        assert cached is None

    asyncio.run(run())


def test_logging_middleware() -> None:
    lm = LoggingMiddleware()
    request = ProviderRequest(prompt="test", model="m", temperature=0.0, max_tokens=10, trace_id="t8")

    async def run() -> None:
        result = await lm.before(request)
        assert result is request
        response = await lm.after(request, ProviderResponse(text="ok", usage_input_tokens=1, usage_output_tokens=2, latency_ms=5))
        assert response is not None

    asyncio.run(run())
