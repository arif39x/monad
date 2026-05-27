from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Protocol

from pydantic import BaseModel, Field


class ContentPart(BaseModel):
    type: str = "text"
    text: str | None = None
    image_url: str | None = None
    tool_call_id: str | None = None


class ChatMessage(BaseModel):
    role: str = "user"
    content: str | list[ContentPart] = ""
    name: str | None = None


@dataclass
class ProviderCapabilities:
    supports_streaming: bool = False
    supports_caching: bool = False
    supports_tools: bool = False
    supports_json_mode: bool = False
    supports_image_input: bool = False
    max_context_tokens: int = 8192
    max_output_tokens: int = 4096
    supported_models: list[str] = field(default_factory=list)
    provider_name: str = ""
    base_url: str = ""


class ProviderRequest(BaseModel):
    prompt: str = ""
    messages: list[ChatMessage] = Field(default_factory=list)
    model: str = ""
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=1024, gt=0)
    timeout_seconds: float = Field(default=30.0, gt=0)
    trace_id: str = ""
    stream: bool = False
    response_format: str | None = None
    stop_sequences: list[str] | None = None
    pre_minified_tokens: int = 0
    post_minified_tokens: int = 0
    minification_ratio: float = 1.0
    cached_prefix_hash: str = ""
    cache_ttl_seconds: int = 0
    cacheable_prefix_tokens: int = 0
    intent: str = "ambiguous"
    intent_confidence: float = 0.0
    context_hash: str = ""
    parent_context_hash: str = ""
    session_memory_hash: str = ""
    session_memory_context: str = ""

    def build_messages(self) -> list[ChatMessage]:
        if self.messages:
            return self.messages
        if self.prompt:
            return [ChatMessage(role="user", content=self.prompt)]
        return []


class ProviderResponse(BaseModel):
    text: str = ""
    usage_input_tokens: int = Field(default=0, ge=0)
    usage_output_tokens: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    cache_hit: bool = False
    cache_saved_tokens: int = 0
    finish_reason: str = "stop"
    tool_calls: list[dict[str, Any]] | None = None
    provider_metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.usage_input_tokens + self.usage_output_tokens


class ProviderClient(Protocol):
    async def complete(self, request: ProviderRequest) -> ProviderResponse: ...

    async def stream_complete(self, request: ProviderRequest) -> AsyncIterator[str]: ...
