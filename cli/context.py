from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from bindings import RuntimeClient, RustRuntimeClient
from orchestration import ElyonEngine, ElyonSettings, load_settings
from orchestration.events import JsonlEventStore, SqliteEventStore
from orchestration.logging import configure_logging
from providers import MockProvider, ProviderRegistry, build_registry
from state import InMemorySessionStore


@dataclass(frozen=True)
class CliContext:
    settings: ElyonSettings
    engine: ElyonEngine
    providers: ProviderRegistry
    event_store: JsonlEventStore
    runtime_client: RuntimeClient


def build_context(config_path: Path) -> CliContext:
    import os
    settings = load_settings(config_path)
    configure_logging(settings.telemetry)

    if settings.state.backend == "sqlite":
        event_store = SqliteEventStore(db_path=Path(settings.state.event_log_path).with_suffix(".db"))
    else:
        event_store = JsonlEventStore(path=Path(settings.state.event_log_path))
    providers = build_registry(settings)

    for provider_name, provider_settings in settings.providers.items():
        if provider_settings.base_url is None:
            providers.register_factory(
                provider_name,
                lambda provider_name=provider_name: MockProvider(
                    response_text=f"{provider_name}:ok"
                ),
            )

    config_dir = config_path.parent
    runtime_command = [
        str((config_dir / cmd).resolve())
        if not os.path.isabs(cmd) and (config_dir / cmd).exists()
        else cmd
        for cmd in settings.runtime.command
    ]

    runtime_client = RustRuntimeClient(
        runtime_command=runtime_command,
        allowed_command_prefixes=settings.sandbox.allowed_command_prefixes,
    )

    engine = ElyonEngine(
        settings=settings,
        event_store=event_store,
        session_store=InMemorySessionStore(),
        provider_registry=providers,
        runtime_client=runtime_client,
    )

    return CliContext(
        settings=settings,
        engine=engine,
        providers=providers,
        event_store=event_store,
        runtime_client=runtime_client,
    )
