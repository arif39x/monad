from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from providers.base import ProviderCapabilities, ProviderRequest, ProviderResponse


class ProviderAdapter(ABC):
    @abstractmethod
    def serialize_request(self, request: ProviderRequest) -> dict[str, Any]: ...

    @abstractmethod
    def deserialize_response(self, raw: dict[str, Any]) -> ProviderResponse: ...

    def deserialize_stream_chunk(self, chunk: str) -> str | None:
        return chunk

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities: ...
