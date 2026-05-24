from __future__ import annotations

import asyncio
import importlib
from collections.abc import Callable

from orchestration.config import ElyonSettings
from providers.base import ProviderClient
from providers.http_provider import HttpProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], ProviderClient]] = {}
        self._instances: dict[str, ProviderClient] = {}
        self._lock = asyncio.Lock()

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

    def list_names(self) -> list[str]:
        return sorted(self._factories.keys())


def build_registry(settings: ElyonSettings) -> ProviderRegistry:
    registry = ProviderRegistry()

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

    return registry
