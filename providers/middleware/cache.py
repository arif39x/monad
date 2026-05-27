from __future__ import annotations

import hashlib
import time

from providers.base import ProviderRequest, ProviderResponse
from providers.middleware.core import Middleware


class _MemoryCache:
    def __init__(self) -> None:
        self._data: dict[str, tuple[ProviderResponse, float]] = {}

    def get(self, key: str) -> ProviderResponse | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        response, expires = entry
        if time.time() > expires:
            del self._data[key]
            return None
        return response

    def set(self, key: str, response: ProviderResponse, ttl: float = 300.0) -> None:
        self._data[key] = (response, time.time() + ttl)

    def clear(self) -> None:
        self._data.clear()


class CacheMiddleware(Middleware):
    def __init__(self, enabled: bool = True, ttl_seconds: float = 300.0) -> None:
        self._enabled = enabled
        self._ttl = ttl_seconds
        self._cache = _MemoryCache()

    def _make_key(self, request: ProviderRequest) -> str:
        raw = f"{request.model}:{request.prompt}:{request.temperature}:{request.max_tokens}"
        return hashlib.sha256(raw.encode()).hexdigest()

    async def before(self, request: ProviderRequest) -> ProviderRequest:
        if not self._enabled:
            return request
        return request

    async def after(self, request: ProviderRequest, response: ProviderResponse) -> ProviderResponse:
        if not self._enabled:
            return response
        return response

    async def check_cache(self, request: ProviderRequest) -> ProviderResponse | None:
        if not self._enabled:
            return None
        key = self._make_key(request)
        cached = self._cache.get(key)
        if cached is not None:
            cached.cache_hit = True
        return cached

    async def store_cache(self, request: ProviderRequest, response: ProviderResponse) -> None:
        if not self._enabled:
            return
        key = self._make_key(request)
        self._cache.set(key, response, ttl=self._ttl)
