from __future__ import annotations

from providers.base import ChatMessage, ContentPart, ProviderCapabilities, ProviderRequest, ProviderResponse


def test_chat_message_defaults() -> None:
    msg = ChatMessage()
    assert msg.role == "user"
    assert msg.content == ""
    assert msg.name is None


def test_chat_message_with_content() -> None:
    msg = ChatMessage(role="system", content="Be brief")
    assert msg.role == "system"
    assert msg.content == "Be brief"


def test_chat_message_with_content_parts() -> None:
    parts = [ContentPart(type="text", text="hello")]
    msg = ChatMessage(role="user", content=parts)
    assert isinstance(msg.content, list)
    assert msg.content[0].text == "hello"


def test_content_part_defaults() -> None:
    part = ContentPart()
    assert part.type == "text"
    assert part.text is None


def test_content_part_image() -> None:
    part = ContentPart(type="image_url", image_url="data:image/...")
    assert part.type == "image_url"
    assert part.image_url is not None


def test_provider_capabilities_defaults() -> None:
    caps = ProviderCapabilities()
    assert caps.supports_streaming is False
    assert caps.max_context_tokens == 8192
    assert caps.provider_name == ""


def test_provider_capabilities_custom() -> None:
    caps = ProviderCapabilities(
        supports_streaming=True,
        max_context_tokens=128000,
        provider_name="openai",
        base_url="https://api.openai.com",
    )
    assert caps.supports_streaming is True
    assert caps.max_context_tokens == 128000


def test_provider_request_build_messages_from_prompt() -> None:
    req = ProviderRequest(prompt="Hello", model="m", temperature=0.0, max_tokens=10, trace_id="t1")
    messages = req.build_messages()
    assert len(messages) == 1
    assert messages[0].role == "user"
    assert messages[0].content == "Hello"


def test_provider_request_build_messages_uses_existing() -> None:
    msgs = [ChatMessage(role="system", content="Hi")]
    req = ProviderRequest(messages=msgs, model="m", temperature=0.0, max_tokens=10, trace_id="t2")
    messages = req.build_messages()
    assert len(messages) == 1
    assert messages[0].role == "system"
    assert messages[0].content == "Hi"


def test_provider_request_build_messages_empty() -> None:
    req = ProviderRequest(model="m", temperature=0.0, max_tokens=10, trace_id="t3")
    messages = req.build_messages()
    assert messages == []


def test_provider_response_total_tokens() -> None:
    resp = ProviderResponse(
        text="hello",
        usage_input_tokens=10,
        usage_output_tokens=20,
        latency_ms=5,
    )
    assert resp.total_tokens == 30


def test_provider_response_defaults() -> None:
    resp = ProviderResponse(text="", usage_input_tokens=0, usage_output_tokens=0, latency_ms=0)
    assert resp.finish_reason == "stop"
    assert resp.tool_calls is None
    assert resp.provider_metadata == {}


def test_provider_response_cache_hit() -> None:
    resp = ProviderResponse(text="cached", usage_input_tokens=0, usage_output_tokens=0, latency_ms=0)
    assert resp.cache_hit is False
    resp.cache_hit = True
    assert resp.cache_hit is True


def test_chat_message_content_parts_list_validation() -> None:
    parts = [
        ContentPart(type="text", text="Part 1"),
        ContentPart(type="text", text="Part 2"),
    ]
    msg = ChatMessage(role="user", content=parts)
    assert len(msg.content) == 2  # type: ignore[arg-type]
    assert msg.content[1].text == "Part 2"  # type: ignore[index]
