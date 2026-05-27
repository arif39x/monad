from __future__ import annotations

import asyncio
import logging

from providers.base import ProviderRequest, ProviderResponse
from providers.middleware.core import Middleware

logger = logging.getLogger(__name__)


class RetryMiddleware(Middleware):
    def __init__(self, max_retries: int = 3, base_delay_ms: float = 1000.0) -> None:
        self._max_retries = max_retries
        self._base_delay_ms = base_delay_ms

    async def before(self, request: ProviderRequest) -> ProviderRequest:
        return request

    async def after(self, request: ProviderRequest, response: ProviderResponse) -> ProviderResponse:
        return response

    async def dispatch_with_retry(
        self, request: ProviderRequest, dispatch_func: object
    ) -> ProviderResponse:
        from providers.http_provider import ProviderExecutionError

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                result = await dispatch_func(request)
                if isinstance(result, ProviderResponse):
                    return result
                return result
            except ProviderExecutionError as exc:
                last_error = exc
                logger.warning(
                    "Retry attempt %d/%d failed: %s", attempt + 1, self._max_retries, exc
                )
                if attempt < self._max_retries:
                    delay = self._base_delay_ms * (2**attempt) / 1000.0
                    await asyncio.sleep(delay)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "Retry attempt %d/%d failed (non-provider): %s",
                    attempt + 1,
                    self._max_retries,
                    exc,
                )
                if attempt < self._max_retries:
                    delay = self._base_delay_ms * (2**attempt) / 1000.0
                    await asyncio.sleep(delay)

        raise ProviderExecutionError(
            f"Request failed after {self._max_retries + 1} attempts"
        ) from last_error
