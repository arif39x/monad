from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from orchestration.agents import AgentSettings


class ConfigError(RuntimeError):
    pass


class ProviderSettings(BaseModel):
    name: str
    base_url: str | None = None
    model: str
    default_temperature: float = Field(ge=0, le=2)
    default_max_tokens: int = Field(gt=0)
    timeout_seconds: float = Field(gt=0)
    max_retries: int = Field(ge=0)
    api_key_env: str | None = None

    @field_validator("base_url", "api_key_env", mode="before")
    @classmethod
    def _normalize_optional_string(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value


class RuntimeSettings(BaseModel):
    command: list[str]
    request_timeout_seconds: float = Field(gt=0)
    max_stdout_bytes: int = Field(gt=0)
    max_stderr_bytes: int = Field(gt=0)


class RepairSettings(BaseModel):
    max_attempts: int = Field(gt=0)
    verify_after_repair: bool
    allowed_extensions: list[str]


class TelemetrySettings(BaseModel):
    log_level: str
    json_logs: bool


class SandboxSettings(BaseModel):
    allowed_command_prefixes: list[str]
    allowed_read_roots: list[str]
    allowed_write_roots: list[str]
    default_policy_level: str = "standard"


class StateSettings(BaseModel):
    event_log_path: str


class CompilerSettings(BaseModel):
    zerolang_path: str | None = Field(default=None)


class ElyonSettings(BaseModel):
    default_provider: str
    providers: dict[str, ProviderSettings]
    agents: dict[str, AgentSettings] = {}
    runtime: RuntimeSettings
    repair: RepairSettings
    telemetry: TelemetrySettings
    sandbox: SandboxSettings
    state: StateSettings
    compiler: CompilerSettings = Field(default_factory=CompilerSettings)

    def provider(self, name: str | None = None) -> ProviderSettings:
        selected_name = name or self.default_provider
        if selected_name not in self.providers:
            raise ConfigError(f"Provider '{selected_name}' is not configured")
        return self.providers[selected_name]

    def agent(self, name: str) -> AgentSettings:
        if name not in self.agents:
            raise ConfigError(f"Agent '{name}' is not configured")
        return self.agents[name]

    def provider_api_key(self, provider_name: str) -> str | None:
        provider = self.provider(provider_name)
        if not provider.api_key_env:
            return None
        return os.getenv(provider.api_key_env)


def load_settings(path: Path) -> ElyonSettings:
    if not path.exists():
        raise ConfigError(f"Config file does not exist: {path}")

    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"Unable to read config file: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"Config file has invalid TOML: {path}") from exc

    try:
        return ElyonSettings.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError("Config validation failed") from exc


def settings_to_dict(settings: ElyonSettings) -> dict[str, Any]:
    return settings.model_dump(mode="json")
