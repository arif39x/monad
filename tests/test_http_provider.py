from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

def _run(coro):
    return asyncio.run(coro)

from orchestration.config import ProviderSettings
from providers.base import ProviderRequest
from providers.http_provider import (
    HttpProvider,
    ProviderExecutionError,
    _extract_text,
    _extract_usage,
)


def test_extract_text_direct() -> None:
    assert _extract_text({"text": "hello"}) == "hello"


def test_extract_text_output() -> None:
    assert _extract_text({"output": "world"}) == "world"


def test_extract_text_choices_completion() -> None:
    data = {"choices": [{"text": "completion text"}]}
    assert _extract_text(data) == "completion text"


def test_extract_text_choices_chat() -> None:
    data = {"choices": [{"message": {"content": "chat response"}}]}
    assert _extract_text(data) == "chat response"


def test_extract_text_choices_content_array() -> None:
    data = {
        "choices": [{"message": {"content": [{"type": "text", "text": "part1"}, {"type": "text", "text": "part2"}]}}]
    }
    assert _extract_text(data) == "part1part2"


def test_extract_text_anthropic_content_array() -> None:
    data = {"content": [{"type": "text", "text": "anthropic response"}]}
    assert _extract_text(data) == "anthropic response"


def test_extract_text_anthropic_string() -> None:
    assert _extract_text({"content": "plain string"}) == "plain string"


def test_extract_text_raises_on_unsupported() -> None:
    with pytest.raises(ProviderExecutionError, match="supported text field"):
        _extract_text({"unrelated": "data"})


def test_extract_usage_missing() -> None:
    assert _extract_usage({}, "input_tokens") == 0


def test_extract_usage_present() -> None:
    assert _extract_usage({"usage": {"input_tokens": 42}}, "input_tokens") == 42


def test_extract_usage_non_dict() -> None:
    assert _extract_usage({"usage": "invalid"}, "input_tokens") == 0


def test_extract_usage_float_value() -> None:
    assert _extract_usage({"usage": {"input_tokens": 42.5}}, "input_tokens") == 42


def test_http_provider_complete_success() -> None:
    settings = ProviderSettings(
        name="test",
        base_url="http://test.local/api",
        model="test-model",
        default_temperature=0.0,
        default_max_tokens=64,
        timeout_seconds=5.0,
        max_retries=0,
    )
    provider = HttpProvider(settings=settings, api_key=None)

    class FakeResponse:
        status_code = 200
        def json(self):
            return {"text": "response text"}
        def raise_for_status(self):
            pass

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            return FakeResponse()

    request = ProviderRequest(
        prompt="hello",
        model="test-model",
        temperature=0.0,
        max_tokens=64,
        timeout_seconds=5.0,
        trace_id="trace-1",
    )

    with patch("providers.http_provider.httpx.AsyncClient", return_value=FakeClient()):
        result = _run(provider.complete(request))

    assert result.text == "response text"
    assert result.latency_ms >= 0


def test_http_provider_auth_error() -> None:
    settings = ProviderSettings(
        name="test",
        base_url="http://test.local/api",
        model="test-model",
        default_temperature=0.0,
        default_max_tokens=64,
        timeout_seconds=5.0,
        max_retries=1,
    )
    provider = HttpProvider(settings=settings, api_key="bad-key")

    import httpx
    class FakeAuthResponse:
        status_code = 401
        def json(self):
            return {"error": "unauthorized"}
        def raise_for_status(self):
            raise httpx.HTTPStatusError("401", request=MagicMock(), response=self)

    class FakeAuthClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            pass
        async def post(self, url, **kwargs):
            return FakeAuthResponse()

    request = ProviderRequest(
        prompt="test",
        model="test-model",
        temperature=0.0,
        max_tokens=64,
        timeout_seconds=5.0,
        trace_id="trace-auth",
    )

    with patch("providers.http_provider.httpx.AsyncClient", return_value=FakeAuthClient()):
        with pytest.raises(ProviderExecutionError, match="Auth error"):
            _run(provider.complete(request))
