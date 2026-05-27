from __future__ import annotations

import asyncio
import time

from providers.base import ProviderRequest, ProviderResponse
from providers.middleware.core import Middleware


class RateLimitMiddleware(Middleware):
    def __init__(self, max_per_minute: int = 60, burst: int = 10) -> None:
        self._max_per_minute = max_per_minute
        self._burst = burst
        self._tokens: float = float(burst)
        self._last_refill: float = time.time()
        self._lock = asyncio.Lock()

    async def before(self, request: ProviderRequest) -> ProviderRequest:
        async with self._lock:
            self._refill()
            if self._tokens < 1.0:
                wait = (1.0 - self._tokens) * (60.0 / self._max_per_minute)
                await asyncio.sleep(wait)
                self._refill()
            self._tokens -= 1.0
        return request

    async def after(self, request: ProviderRequest, response: ProviderResponse) -> ProviderResponse:
        return response

    def _refill(self) -> None:
        now = time.time()
        elapsed = now - self._last_refill
        self._tokens = min(float(self._burst), self._tokens + elapsed * (self._max_per_minute / 60.0))
        self._last_refill = now
