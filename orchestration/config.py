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
    adapter: str = "generic"

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
    backend: str = "jsonl"
    retention: RetentionSettings | None = None


class RetentionSettings(BaseModel):
    active_max_rows: int = 10000
    active_max_mb: int = 100
    archive_ttl_days: int = 90
    archive_compression: str = "gzip"
    prune_interval_minutes: int = 60


class MinificationSettings(BaseModel):
    enabled: bool = False
    target_tokens: int = 4096
    hard_limit: int = 8192
    preserve_user_message: bool = True
    structural_only: bool = False


class CacheSettings(BaseModel):
    prefix_cache_enabled: bool = False
    prefix_cache_ttl_seconds: int = 300
    prefix_cache_max_entries: int = 500
    prefix_cache_backend: str = "memory"
    provider_cache_enabled: bool = False


class RoutingSettings(BaseModel):
    intent_router_enabled: bool = False
    classifier_backend: str = "pattern"
    confidence_threshold: float = 0.7
    enable_shell_commands: bool = True
    enable_file_operations: bool = True
    allowed_shell_commands: list[str] = Field(default_factory=lambda: ["ls", "cat", "head", "tail", "wc", "find", "grep", "git"])
    max_command_length: int = 200


class DiffSettings(BaseModel):
    enabled: bool = False
    max_snapshots: int = 100


class KnowledgeSettings(BaseModel):
    vector_enabled: bool = False
    embedding_backend: str = "simple"
    chunk_strategy: str = "auto"
    chunk_max_tokens: int = 200
    chunk_overlap_tokens: int = 50
    search_top_k: int = 15
    min_score: float = 0.0


class SessionMemorySettings(BaseModel):
    enabled: bool = False
    working_memory_turns: int = 5
    working_memory_max_tokens: int = 4096
    summarized_memory_max_depth: int = 10
    summarization_mode: str = "extractive"
    abstractive_provider: str = "cheapest"
    auto_summarize_threshold_tokens: int = 3072
    cross_session_memory: bool = False


class AgentRoutingSettings(BaseModel):
    strategy: str = "legacy"
    fallback_enabled: bool = True
    max_fallback_depth: int = 3
    history_ttl_days: int = 30
    scoring_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "capability": 0.30,
            "cost": 0.25,
            "load": 0.20,
            "reliability": 0.15,
            "latency": 0.10,
        }
    )


class SecuritySandboxSettings(BaseModel):
    enable_argument_filtering: bool = False
    dangerous_arg_patterns: list[str] = Field(
        default_factory=lambda: [
            r"rm\s+-rf\s+/",
            r"sudo\s+",
            r">\s*/etc/",
            r"\|\s*(curl|wget|nc|bash|sh)",
            r"`.*`",
            r"\$\(.*\)",
        ]
    )
    enable_network_egress_control: bool = False
    allowed_egress_hosts: list[str] = Field(
        default_factory=lambda: ["api.openai.com", "api.anthropic.com"]
    )
    max_commands_per_minute: int = 30
    enable_composition_check: bool = False
    deny_privileged_escalation: bool = False


class SecuritySettings(BaseModel):
    audit_log_path: str = ".elyon/security.log"
    audit_log_retention_days: int = 90
    encrypt_api_keys: bool = False
    key_encryption_key_env: str = "ELYON_ENCRYPTION_KEY"
    sandbox: SecuritySandboxSettings = Field(default_factory=SecuritySandboxSettings)


class ElyonSettings(BaseModel):
    default_provider: str
    providers: dict[str, ProviderSettings]
    agents: dict[str, AgentSettings] = {}
    runtime: RuntimeSettings
    repair: RepairSettings
    telemetry: TelemetrySettings
    sandbox: SandboxSettings
    state: StateSettings
    minification: MinificationSettings = Field(default_factory=MinificationSettings)
    cache: CacheSettings = Field(default_factory=CacheSettings)
    routing: RoutingSettings = Field(default_factory=RoutingSettings)
    diff: DiffSettings = Field(default_factory=DiffSettings)
    knowledge: KnowledgeSettings = Field(default_factory=KnowledgeSettings)
    session_memory: SessionMemorySettings = Field(default_factory=SessionMemorySettings)
    agent_routing: AgentRoutingSettings = Field(default_factory=AgentRoutingSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)

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
