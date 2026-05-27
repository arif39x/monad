from __future__ import annotations

import logging

from providers.base import ProviderRequest, ProviderResponse
from providers.middleware.core import Middleware

logger = logging.getLogger(__name__)


class LoggingMiddleware(Middleware):
    async def before(self, request: ProviderRequest) -> ProviderRequest:
        logger.info(
            "Provider request: model=%s stream=%s tokens=%d trace=%s",
            request.model,
            request.stream,
            request.max_tokens,
            request.trace_id,
        )
        return request

    async def after(self, request: ProviderRequest, response: ProviderResponse) -> ProviderResponse:
        logger.info(
            "Provider response: finish=%s input_tokens=%d output_tokens=%d latency=%dms",
            response.finish_reason,
            response.usage_input_tokens,
            response.usage_output_tokens,
            response.latency_ms,
        )
        return response
