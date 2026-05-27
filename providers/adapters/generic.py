from __future__ import annotations

from typing import Any

from providers.adapters.base import ProviderAdapter
from providers.base import (
    ChatMessage,
    ProviderCapabilities,
    ProviderRequest,
    ProviderResponse,
)


class GenericAdapter(ProviderAdapter):
    def __init__(self, model: str = "default", base_url: str = "") -> None:
        self._model = model
        self._base_url = base_url

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            supports_streaming=False,
            supports_caching=False,
            supports_tools=False,
            supports_json_mode=False,
            supports_image_input=False,
            max_context_tokens=4096,
            max_output_tokens=1024,
            supported_models=[self._model],
            provider_name="generic",
            base_url=self._base_url,
        )

    def serialize_request(self, request: ProviderRequest) -> dict[str, Any]:
        messages = request.build_messages()
        prompt = "\n".join(
            f"{m.role}: {m.content}" if isinstance(m.content, str) else str(m.content)
            for m in messages
        )
        return {
            "model": request.model or self._model,
            "prompt": prompt,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

    def deserialize_response(self, raw: dict[str, Any]) -> ProviderResponse:
        text = self._extract_text(raw)
        usage = raw.get("usage", {})
        return ProviderResponse(
            text=text,
            usage_input_tokens=usage.get("input_tokens", 0) or usage.get("prompt_tokens", 0) or 0,
            usage_output_tokens=usage.get("output_tokens", 0) or usage.get("completion_tokens", 0) or 0,
            latency_ms=0,
        )

    @staticmethod
    def _extract_text(raw: dict[str, Any]) -> str:
        direct = raw.get("text") or raw.get("output") or raw.get("response")
        if isinstance(direct, str):
            return direct
        choices = raw.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                text = first.get("text") or first.get("message", {}).get("content", "")
                if isinstance(text, str):
                    return text
        content = raw.get("content")
        if isinstance(content, list):
            return "".join(c.get("text", "") for c in content if isinstance(c, dict))
        if isinstance(content, str):
            return content
        return ""
