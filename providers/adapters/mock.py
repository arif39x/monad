from __future__ import annotations

from typing import Any

from providers.adapters.base import ProviderAdapter
from providers.base import (
    ChatMessage,
    ProviderCapabilities,
    ProviderRequest,
    ProviderResponse,
)


class MockAdapter(ProviderAdapter):
    def __init__(self, response_text: str = "Mock response") -> None:
        self._response_text = response_text

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=True,
            supports_caching=False,
            supports_tools=False,
            supports_json_mode=True,
            supports_image_input=False,
            max_context_tokens=4096,
            max_output_tokens=1024,
            supported_models=["mock"],
            provider_name="mock",
            base_url="",
        )

    def serialize_request(self, request: ProviderRequest) -> dict[str, Any]:
        messages = request.build_messages()
        prompt = "\n".join(
            f"{m.role}: {m.content}" if isinstance(m.content, str) else str(m.content)
            for m in messages
        )
        return {
            "model": request.model or "mock",
            "prompt": prompt,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

    def deserialize_response(self, raw: dict[str, Any]) -> ProviderResponse:
        prompt = raw.get("prompt", "")
        return ProviderResponse(
            text=f"{self._response_text}\n{prompt}",
            usage_input_tokens=len(prompt.split()),
            usage_output_tokens=len(self._response_text.split()),
            latency_ms=1,
        )

    def deserialize_stream_chunk(self, chunk: str) -> str | None:
        return chunk if chunk else None
