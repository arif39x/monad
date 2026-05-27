from __future__ import annotations

import asyncio

from providers.adapters import MockAdapter
from providers.base import ProviderRequest
from providers.gateway import DispatchStrategy, ProviderGateway


def _make_gateway() -> ProviderGateway:
    gw = ProviderGateway(strategy=DispatchStrategy.FALLBACK)
    gw.register_adapter("mock_a", lambda: MockAdapter(response_text="Response A"))
    gw.register_adapter("mock_b", lambda: MockAdapter(response_text="Response B"))
    return gw


def test_gateway_dispatch_basic() -> None:
    gw = _make_gateway()
    request = ProviderRequest(prompt="Hello", model="mock", temperature=0.0, max_tokens=10, trace_id="t1")

    async def run() -> str:
        response = await gw.dispatch(request, adapter_name="mock_a")
        return response.text

    result = asyncio.run(run())
    assert "Response A" in result


def test_gateway_fallback() -> None:
    gw = _make_gateway()
    request = ProviderRequest(prompt="Hi", model="mock", temperature=0.0, max_tokens=10, trace_id="t2")

    async def run() -> str:
        response = await gw.dispatch(request, adapter_name="nonexistent", strategy=DispatchStrategy.FALLBACK)
        return response.text

    with pytest_raises_match(RuntimeError, "All providers failed"):
        asyncio.run(run())


def test_gateway_parallel() -> None:
    gw = _make_gateway()
    request = ProviderRequest(prompt="Parallel", model="mock", temperature=0.0, max_tokens=10, trace_id="t3")

    async def run() -> str:
        response = await gw.dispatch(request, adapter_name="mock_b", strategy=DispatchStrategy.PARALLEL)
        return response.text

    result = asyncio.run(run())
    assert "Response B" in result


def test_gateway_list_adapters() -> None:
    gw = _make_gateway()
    adapters = gw.list_adapters()
    assert "mock_a" in adapters
    assert "mock_b" in adapters


def test_gateway_fallback_providers() -> None:
    gw = ProviderGateway(
        strategy=DispatchStrategy.FALLBACK,
        fallback_providers=["mock_b"],
    )
    gw.register_adapter("mock_b", lambda: MockAdapter(response_text="Fallback B"))
    request = ProviderRequest(prompt="Fallback test", model="mock", temperature=0.0, max_tokens=10, trace_id="t4")

    async def run() -> str:
        response = await gw.dispatch(request)
        return response.text

    result = asyncio.run(run())
    assert "Fallback B" in result


def test_gateway_dispatch_with_messages() -> None:
    from providers.base import ChatMessage

    gw = _make_gateway()
    request = ProviderRequest(
        messages=[ChatMessage(role="user", content="Structured")],
        model="mock",
        temperature=0.0,
        max_tokens=10,
        trace_id="t5",
    )

    async def run() -> str:
        response = await gw.dispatch(request, adapter_name="mock_a")
        return response.text

    result = asyncio.run(run())
    assert "Response A" in result


def test_gateway_unknown_adapter() -> None:
    gw = _make_gateway()
    request = ProviderRequest(prompt="test", model="mock", temperature=0.0, max_tokens=10, trace_id="t6")

    async def run() -> ProviderRequest:
        return await gw.dispatch(request, adapter_name="does_not_exist")

    with pytest_raises_match(RuntimeError, "failed"):
        asyncio.run(run())


def pytest_raises_match(exc_type, match: str):
    import pytest
    return pytest.raises(exc_type, match=match)
