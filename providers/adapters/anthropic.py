from __future__ import annotations

import json
from typing import Any

from providers.adapters.base import ProviderAdapter
from providers.base import (
    ChatMessage,
    ProviderCapabilities,
    ProviderRequest,
    ProviderResponse,
)


class AnthropicAdapter(ProviderAdapter):
    def __init__(self, model: str = "claude-sonnet-4-20250514", base_url: str = "") -> None:
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
            max_context_tokens=200000,
            max_output_tokens=8192,
            supported_models=["claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022"],
            provider_name="anthropic",
            base_url=self._base_url or "https://api.anthropic.com/v1/messages",
        )

    def serialize_request(self, request: ProviderRequest) -> dict[str, Any]:
        messages = request.build_messages()
        system = self._extract_system(messages)
        payload: dict[str, Any] = {
            "model": request.model or self._model,
            "messages": self._serialize_messages(messages),
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if system:
            payload["system"] = system
        if request.stream:
            payload["stream"] = True
        if request.stop_sequences:
            payload["stop_sequences"] = request.stop_sequences
        return payload

    def deserialize_response(self, raw: dict[str, Any]) -> ProviderResponse:
        text = ""
        content = raw.get("content", [])
        if isinstance(content, list):
            parts = [
                c.get("text", "")
                for c in content
                if isinstance(c, dict) and c.get("type") == "text"
            ]
            text = "".join(parts)
        elif isinstance(content, str):
            text = content
        usage = raw.get("usage", {})
        return ProviderResponse(
            text=text,
            usage_input_tokens=usage.get("input_tokens", 0) or 0,
            usage_output_tokens=usage.get("output_tokens", 0) or 0,
            finish_reason=raw.get("stop_reason", "end_turn") or "end_turn",
            latency_ms=0,
        )

    def deserialize_stream_chunk(self, chunk: str) -> str | None:
        if not chunk.startswith("data: "):
            return None
        try:
            data = json.loads(chunk[6:])
        except json.JSONDecodeError:
            return None
        if data.get("type") == "content_block_delta":
            delta = data.get("delta", {})
            return delta.get("text")
        return None

    @staticmethod
    def _extract_system(messages: list[ChatMessage]) -> str:
        parts = [m.content for m in messages if m.role == "system" and isinstance(m.content, str)]
        return "\n".join(parts)

    @staticmethod
    def _serialize_messages(messages: list[ChatMessage]) -> list[dict[str, Any]]:
        result = []
        for m in messages:
            if m.role == "system":
                continue
            if isinstance(m.content, str):
                result.append({"role": m.role, "content": m.content})
            else:
                parts = []
                for p in m.content:
                    entry: dict[str, Any] = {"type": p.type}
                    if p.text is not None:
                        entry["text"] = p.text
                    if p.image_url is not None:
                        entry["source"] = {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": p.image_url,
                        }
                    parts.append(entry)
                result.append({"role": m.role, "content": parts})
        return result
