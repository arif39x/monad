from __future__ import annotations

import time

from providers.adapters import GenericAdapter, MockAdapter, OpenAIAdapter
from providers.base import ChatMessage, ProviderRequest


class TestAdapterBenchmarks:
    def test_openai_serialize(self) -> None:
        adapter = OpenAIAdapter()
        request = ProviderRequest(
            messages=[ChatMessage(role="user", content="hello")],
            model="gpt-4o",
            temperature=0.0,
            max_tokens=100,
            trace_id="b1",
        )
        start = time.perf_counter()
        for _ in range(1000):
            adapter.serialize_request(request)
        elapsed = (time.perf_counter() - start) / 1000
        assert elapsed < 0.001

    def test_openai_deserialize(self) -> None:
        adapter = OpenAIAdapter()
        raw = {
            "choices": [{"message": {"content": "response text"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        start = time.perf_counter()
        for _ in range(1000):
            adapter.deserialize_response(raw)
        elapsed = (time.perf_counter() - start) / 1000
        assert elapsed < 0.001

    def test_generic_serialize(self) -> None:
        adapter = GenericAdapter()
        request = ProviderRequest(
            messages=[ChatMessage(role="user", content="hello")],
            model="test",
            temperature=0.0,
            max_tokens=100,
            trace_id="b2",
        )
        start = time.perf_counter()
        for _ in range(1000):
            adapter.serialize_request(request)
        elapsed = (time.perf_counter() - start) / 1000
        assert elapsed < 0.001

    def test_mock_roundtrip(self) -> None:
        adapter = MockAdapter(response_text="test")
        request = ProviderRequest(prompt="hello", model="mock", temperature=0.0, max_tokens=10, trace_id="b3")
        start = time.perf_counter()
        for _ in range(1000):
            payload = adapter.serialize_request(request)
            adapter.deserialize_response(payload)
        elapsed = (time.perf_counter() - start) / 1000
        assert elapsed < 0.001


class TestGatewayBenchmarks:
    def test_gateway_dispatch_mock(self) -> None:
        from providers.gateway import ProviderGateway

        gw = ProviderGateway()
        gw.register_adapter("mock", lambda: MockAdapter(response_text="ok"))
        request = ProviderRequest(prompt="hello", model="mock", temperature=0.0, max_tokens=10, trace_id="b4")
        import asyncio
        async def run():
            start = time.perf_counter()
            for _ in range(100):
                await gw.dispatch(request, adapter_name="mock")
            return (time.perf_counter() - start) / 100
        elapsed = asyncio.run(run())
        assert elapsed < 0.01
