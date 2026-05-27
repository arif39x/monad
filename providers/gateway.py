from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from providers.adapters import GenericAdapter, ProviderAdapter
from providers.base import ProviderRequest, ProviderResponse
from providers.middleware import CacheMiddleware, MiddlewarePipeline
from providers.middleware.retry import RetryMiddleware

logger = logging.getLogger(__name__)


class DispatchStrategy(StrEnum):
    FALLBACK = "fallback"
    PARALLEL = "parallel"
    CHEAPEST = "cheapest"


AdapterFactory = Callable[[], ProviderAdapter]


class ProviderGateway:
    def __init__(
        self,
        *,
        pipeline: MiddlewarePipeline | None = None,
        retry_middleware: RetryMiddleware | None = None,
        cache_middleware: CacheMiddleware | None = None,
        strategy: DispatchStrategy = DispatchStrategy.FALLBACK,
        fallback_providers: list[str] | None = None,
    ) -> None:
        self._pipeline = pipeline or MiddlewarePipeline()
        self._retry = retry_middleware
        self._cache = cache_middleware
        self._strategy = strategy
        self._fallback_providers = fallback_providers or []
        self._adapters: dict[str, AdapterFactory] = {}
        self._http_provider: object | None = None

    def set_http_provider(self, provider: object) -> None:
        self._http_provider = provider

    def register_adapter(self, name: str, factory: AdapterFactory) -> None:
        self._adapters[name] = factory

    def list_adapters(self) -> list[str]:
        return sorted(self._adapters.keys())

    async def dispatch(
        self,
        request: ProviderRequest,
        adapter_name: str | None = None,
        strategy: DispatchStrategy | None = None,
    ) -> ProviderResponse:
        active_strategy = strategy or self._strategy
        providers = self._resolve_providers(adapter_name)

        if self._cache:
            cached = await self._cache.check_cache(request)
            if cached is not None:
                logger.info("Cache hit for request trace=%s", request.trace_id)
                return cached

        if active_strategy == DispatchStrategy.PARALLEL:
            return await self._dispatch_parallel(request, providers)

        last_error: Exception | None = None
        for provider_name in providers:
            try:
                response = await self._dispatch_with_middleware(request, provider_name)
                if self._cache:
                    await self._cache.store_cache(request, response)
                return response
            except Exception as exc:
                logger.warning("Provider '%s' failed: %s", provider_name, exc)
                last_error = exc
                if active_strategy != DispatchStrategy.FALLBACK:
                    raise

        raise RuntimeError(
            f"All providers failed (tried: {providers})"
        ) from last_error

    async def _dispatch_with_middleware(
        self,
        request: ProviderRequest,
        provider_name: str,
    ) -> ProviderResponse:
        async def dispatch_func(req: ProviderRequest) -> ProviderResponse:
            return await self._execute_dispatch(req, provider_name)

        if self._retry:
            return await self._retry.dispatch_with_retry(
                request,
                lambda req: self._pipeline.run(
                    req, lambda r: self._execute_dispatch(r, provider_name)
                ),
            )

        return await self._pipeline.run(request, dispatch_func)

    async def _execute_dispatch(
        self,
        request: ProviderRequest,
        provider_name: str,
    ) -> ProviderResponse:
        factory = self._adapters.get(provider_name)
        if factory is not None:
            adapter = factory()
            payload = adapter.serialize_request(request)
            return adapter.deserialize_response(payload)

        if self._http_provider is not None:
            from providers.http_provider import HttpProvider

            if hasattr(self._http_provider, "complete"):
                return await self._http_provider.complete(request)  # type: ignore[union-attr]

        raise KeyError(f"Provider '{provider_name}' has no adapter or legacy provider")

    async def _dispatch_parallel(
        self,
        request: ProviderRequest,
        providers: list[str],
    ) -> ProviderResponse:
        async def try_provider(name: str) -> ProviderResponse:
            return await self._dispatch_with_middleware(request, name)

        results = await asyncio.gather(
            *[try_provider(p) for p in providers], return_exceptions=True
        )
        successes = [r for r in results if isinstance(r, ProviderResponse)]
        if successes:
            return successes[0]
        raise RuntimeError(f"All parallel providers failed: {providers}")

    def _resolve_providers(self, adapter_name: str | None) -> list[str]:
        if adapter_name:
            return [adapter_name] + [p for p in self._fallback_providers if p != adapter_name]
        if self._adapters:
            primary = next(iter(self._adapters.keys()))
            return [primary] + [p for p in self._fallback_providers if p != primary]
        return list(self._fallback_providers)
