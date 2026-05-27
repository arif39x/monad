from __future__ import annotations

from providers.adapters import GenericAdapter, MockAdapter, OpenAIAdapter
from providers.adapters.base import ProviderAdapter
from providers.base import ChatMessage, ContentPart, ProviderRequest, ProviderResponse


def test_openai_adapter_serialize_simple() -> None:
    adapter = OpenAIAdapter()
    request = ProviderRequest(
        prompt="Hello",
        model="gpt-4o",
        temperature=0.5,
        max_tokens=100,
        trace_id="t1",
    )
    payload = adapter.serialize_request(request)
    assert payload["model"] == "gpt-4o"
    assert payload["temperature"] == 0.5
    assert payload["max_tokens"] == 100
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][0]["content"] == "Hello"


def test_openai_adapter_serialize_messages() -> None:
    adapter = OpenAIAdapter()
    request = ProviderRequest(
        messages=[
            ChatMessage(role="system", content="Be brief"),
            ChatMessage(role="user", content="Hi"),
        ],
        model="gpt-4o",
        temperature=0.0,
        max_tokens=50,
        trace_id="t2",
    )
    payload = adapter.serialize_request(request)
    assert len(payload["messages"]) == 2
    assert payload["messages"][0]["role"] == "system"
    assert payload["messages"][1]["role"] == "user"


def test_openai_adapter_serialize_content_parts() -> None:
    adapter = OpenAIAdapter()
    request = ProviderRequest(
        messages=[
            ChatMessage(
                role="user",
                content=[
                    ContentPart(type="text", text="Describe this image"),
                    ContentPart(type="text", text="Thanks"),
                ],
            )
        ],
        model="gpt-4o",
        temperature=0.0,
        max_tokens=50,
        trace_id="t3",
    )
    payload = adapter.serialize_request(request)
    assert len(payload["messages"][0]["content"]) == 2
    assert payload["messages"][0]["content"][0]["type"] == "text"


def test_openai_adapter_deserialize_chat() -> None:
    adapter = OpenAIAdapter()
    raw = {
        "choices": [{"message": {"content": "Hello there"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }
    response = adapter.deserialize_response(raw)
    assert response.text == "Hello there"
    assert response.usage_input_tokens == 10
    assert response.usage_output_tokens == 5
    assert response.finish_reason == "stop"


def test_openai_adapter_deserialize_completion() -> None:
    adapter = OpenAIAdapter()
    raw = {"choices": [{"text": "completion text"}], "usage": {}}
    response = adapter.deserialize_response(raw)
    assert response.text == "completion text"


def test_openai_adapter_deserialize_empty() -> None:
    adapter = OpenAIAdapter()
    response = adapter.deserialize_response({})
    assert response.text == ""


def test_openai_adapter_stream_chunk() -> None:
    adapter = OpenAIAdapter()
    chunk_data = 'data: {"choices": [{"delta": {"content": "Hello"}}]}'
    result = adapter.deserialize_stream_chunk(chunk_data[6:])
    assert result == "Hello"


def test_openai_adapter_capabilities() -> None:
    adapter = OpenAIAdapter()
    caps = adapter.capabilities
    assert caps.supports_streaming is True
    assert caps.supports_tools is True
    assert caps.provider_name == "openai"


def test_generic_adapter_serialize() -> None:
    adapter = GenericAdapter(model="test-model")
    request = ProviderRequest(
        messages=[
            ChatMessage(role="system", content="Be brief"),
            ChatMessage(role="user", content="Hello"),
        ],
        model="test-model",
        temperature=0.0,
        max_tokens=50,
        trace_id="t1",
    )
    payload = adapter.serialize_request(request)
    assert "prompt" in payload
    assert "system: Be brief" in payload["prompt"]
    assert "user: Hello" in payload["prompt"]


def test_generic_adapter_deserialize_text() -> None:
    adapter = GenericAdapter()
    raw = {"text": "Hello world"}
    response = adapter.deserialize_response(raw)
    assert response.text == "Hello world"


def test_generic_adapter_deserialize_choices() -> None:
    adapter = GenericAdapter()
    raw = {"choices": [{"text": "completion"}]}
    response = adapter.deserialize_response(raw)
    assert response.text == "completion"


def test_generic_adapter_deserialize_anthropic() -> None:
    adapter = GenericAdapter()
    raw = {"content": [{"type": "text", "text": "Anthropic response"}]}
    response = adapter.deserialize_response(raw)
    assert response.text == "Anthropic response"


def test_generic_adapter_capabilities() -> None:
    adapter = GenericAdapter()
    caps = adapter.capabilities
    assert caps.supports_streaming is False
    assert caps.provider_name == "generic"


def test_mock_adapter_serialize() -> None:
    adapter = MockAdapter(response_text="Mock reply")
    request = ProviderRequest(prompt="Hello", model="mock", temperature=0.0, max_tokens=10, trace_id="t1")
    payload = adapter.serialize_request(request)
    assert "prompt" in payload
    assert payload["model"] == "mock"


def test_mock_adapter_deserialize() -> None:
    adapter = MockAdapter(response_text="Mock reply")
    response = adapter.deserialize_response({"prompt": "Hello", "model": "mock"})
    assert "Mock reply" in response.text
    assert "Hello" in response.text


def test_abstract_adapter_not_instantiable() -> None:
    import pytest
    with pytest.raises(TypeError):
        ProviderAdapter()  # type: ignore[abstract]
