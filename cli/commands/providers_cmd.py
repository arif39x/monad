from __future__ import annotations

from cli.context import CliContext


def execute(context: CliContext) -> dict[str, object]:
    providers = []
    for name in context.providers.list_names():
        provider_settings = context.settings.provider(name)
        entry: dict[str, object] = {
            "name": provider_settings.name,
            "model": provider_settings.model,
            "adapter": provider_settings.adapter,
            "timeout_seconds": provider_settings.timeout_seconds,
            "max_retries": provider_settings.max_retries,
            "remote": provider_settings.base_url is not None,
        }
        providers.append(entry)

    gateway = context.providers.list_gateway_adapters()
    if gateway:
        providers.append({"name": "(gateway_adapters)", "model": ", ".join(gateway), "adapter": "", "timeout_seconds": "", "max_retries": "", "remote": ""})

    return {"status": "ok", "providers": providers}
