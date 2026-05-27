from __future__ import annotations

import asyncio
import importlib
from collections.abc import Callable

from orchestration.config import ElyonSettings
from providers.adapters import GenericAdapter, MockAdapter, OpenAIAdapter, ProviderAdapter
from providers.base import ProviderClient
from providers.gateway import DispatchStrategy, ProviderGateway
class ProviderRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], ProviderClient]] = {}
        self._instances: dict[str, ProviderClient] = {}
        self._lock = asyncio.Lock()
        self._gateway: ProviderGateway | None = None

    def set_gateway(self, gateway: ProviderGateway) -> None:
        self._gateway = gateway

    def register_factory(self, name: str, factory: Callable[[], ProviderClient]) -> None:
        self._factories[name] = factory

    def register_lazy(self, name: str, module_name: str, attribute_name: str) -> None:
        def lazy_factory() -> ProviderClient:
            module = importlib.import_module(module_name)
            provider_factory = getattr(module, attribute_name)
            return provider_factory()

        self._factories[name] = lazy_factory

    async def get(self, name: str) -> ProviderClient:
        async with self._lock:
            if name in self._instances:
                return self._instances[name]
            if name not in self._factories:
                raise KeyError(f"Unknown provider: {name}")
            instance = self._factories[name]()
            self._instances[name] = instance
            return instance

    async def get_gateway(self) -> ProviderGateway:
        if self._gateway is None:
            raise RuntimeError("Gateway not configured")
        return self._gateway

    def list_names(self) -> list[str]:
        return sorted(self._factories.keys())

    def list_gateway_adapters(self) -> list[str]:
        return self._gateway.list_adapters() if self._gateway else []


def build_registry(settings: ElyonSettings) -> ProviderRegistry:
    registry = ProviderRegistry()

    gateway = ProviderGateway(
        strategy=DispatchStrategy.FALLBACK,
        fallback_providers=[],
    )

    from providers.http_provider import HttpProvider

    for provider_name, provider_settings in settings.providers.items():
        if provider_settings.base_url is None:
            continue

        registry.register_factory(
            provider_name,
            lambda provider_name=provider_name: HttpProvider(
                settings=settings.provider(provider_name),
                api_key=settings.provider_api_key(provider_name),
            ),
        )

        adapter_type_name = provider_settings.adapter.lower()
        base_url = provider_settings.base_url or ""
        model = provider_settings.model

        if adapter_type_name == "openai":
            factory = lambda: OpenAIAdapter(model=model, base_url=base_url)
        elif adapter_type_name == "anthropic":
            try:
                from providers.adapters.anthropic import AnthropicAdapter
                factory = lambda: AnthropicAdapter(model=model, base_url=base_url)
            except ImportError:
                factory = lambda: GenericAdapter(model=model, base_url=base_url)
        elif adapter_type_name == "mock":
            factory = lambda: MockAdapter(response_text=f"Mock:{model}")
        else:
            factory = lambda: GenericAdapter(model=model, base_url=base_url)

        gateway.register_adapter(provider_name, factory)

    registry.set_gateway(gateway)
    return registry
