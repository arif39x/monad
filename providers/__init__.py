import importlib

from providers.base import ChatMessage, ContentPart, ProviderCapabilities, ProviderClient, ProviderRequest, ProviderResponse


def __getattr__(name: str):
    module_map = {
        "HttpProvider": ("providers.http_provider", "HttpProvider"),
        "ProviderExecutionError": ("providers.http_provider", "ProviderExecutionError"),
        "MockProvider": ("providers.mock_provider", "MockProvider"),
        "ProviderRegistry": ("providers.registry", "ProviderRegistry"),
        "build_registry": ("providers.registry", "build_registry"),
        "ProviderAdapter": ("providers.adapters", "ProviderAdapter"),
        "GenericAdapter": ("providers.adapters", "GenericAdapter"),
        "MockAdapter": ("providers.adapters", "MockAdapter"),
        "OpenAIAdapter": ("providers.adapters", "OpenAIAdapter"),
        "ProviderGateway": ("providers.gateway", "ProviderGateway"),
        "DispatchStrategy": ("providers.gateway", "DispatchStrategy"),
    }
    if name in module_map:
        mod_name, attr_name = module_map[name]
        mod = importlib.import_module(mod_name)
        return getattr(mod, attr_name)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = [
    "ChatMessage",
    "ContentPart",
    "DispatchStrategy",
    "GenericAdapter",
    "HttpProvider",
    "MockAdapter",
    "MockProvider",
    "OpenAIAdapter",
    "ProviderAdapter",
    "ProviderCapabilities",
    "ProviderClient",
    "ProviderExecutionError",
    "ProviderGateway",
    "ProviderRegistry",
    "ProviderRequest",
    "ProviderResponse",
    "build_registry",
]
