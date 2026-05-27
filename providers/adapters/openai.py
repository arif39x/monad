from __future__ import annotations

import json
from typing import Any

from providers.adapters.base import ProviderAdapter
from providers.base import (
    ChatMessage,
    ContentPart,
    ProviderCapabilities,
    ProviderRequest,
    ProviderResponse,
)


class OpenAIAdapter(ProviderAdapter):
    def __init__(self, model: str = "gpt-4o", base_url: str = "") -> None:
        self._model = model
        self._base_url = base_url

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_caching=True,
            supports_tools=True,
            supports_json_mode=True,
            supports_image_input=True,
            max_context_tokens=128000,
            max_output_tokens=4096,
            supported_models=["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
            provider_name="openai",
            base_url=self._base_url or "https://api.openai.com/v1/chat/completions",
        )

    def serialize_request(self, request: ProviderRequest) -> dict[str, Any]:
        messages = self._build_messages(request)
        payload: dict[str, Any] = {
            "model": request.model or self._model,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.stream:
            payload["stream"] = True
        if request.response_format == "json_object":
            payload["response_format"] = {"type": "json_object"}
        if request.stop_sequences:
            payload["stop"] = request.stop_sequences
        return payload

    def deserialize_response(self, raw: dict[str, Any]) -> ProviderResponse:
        text = self._extract_text(raw)
        usage = raw.get("usage", {})
        finish_reason = "stop"
        choices = raw.get("choices", [])
        if choices and isinstance(choices[0], dict):
            finish_reason = choices[0].get("finish_reason", "stop") or "stop"
        return ProviderResponse(
            text=text,
            usage_input_tokens=usage.get("prompt_tokens", 0) or 0,
            usage_output_tokens=usage.get("completion_tokens", 0) or 0,
            finish_reason=finish_reason,
            latency_ms=0,
        )

    def deserialize_stream_chunk(self, chunk: str) -> str | None:
        if not chunk or chunk.startswith(":"):
            return None
        try:
            data = json.loads(chunk)
        except json.JSONDecodeError:
            return None
        if "data" in data and data["data"] == "[DONE]":
            return None
        choices = data.get("choices", [])
        if not choices:
            return None
        delta = choices[0].get("delta", {})
        return delta.get("content")

    def _build_messages(self, request: ProviderRequest) -> list[dict[str, Any]]:
        messages = request.build_messages()
        return [_serialize_message(m) for m in messages]

    @staticmethod
    def _extract_text(raw: dict[str, Any]) -> str:
        choices = raw.get("choices", [])
        if not choices:
            return ""
        first = choices[0]
        message = first.get("message", {})
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(
                p.get("text", "") for p in content if isinstance(p, dict) and p.get("type") == "text"
            )
        return first.get("text", "")


def _serialize_message(msg: ChatMessage) -> dict[str, Any]:
    if isinstance(msg.content, str):
        return {"role": msg.role, "content": msg.content}
    parts = []
    for part in msg.content:
        p: dict[str, Any] = {"type": part.type}
        if part.text is not None:
            p["text"] = part.text
        if part.image_url is not None:
            p["image_url"] = {"url": part.image_url}
        parts.append(p)
    return {"role": msg.role, "content": parts}
