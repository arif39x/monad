from __future__ import annotations

from pathlib import Path

from bindings import ensure_runtime_command_is_executable
from cli.context import CliContext
from orchestration.agent_detector import detect_agents


def execute(context: CliContext) -> dict[str, object]:
    warnings: list[str] = []

    runtime_command = context.settings.runtime.command
    if not runtime_command:
        warnings.append("runtime.command is empty")

    event_path = Path(context.settings.state.event_log_path)
    if not event_path.parent.exists():
        warnings.append(f"event log parent directory does not exist: {event_path.parent}")

    provider_names = context.providers.list_names()
    if not provider_names:
        warnings.append("no providers are registered")

    if not ensure_runtime_command_is_executable(runtime_command, Path.cwd()):
        warnings.append(
            "runtime executable was not found from runtime.command; build runtime crate before compile/repair execution"
        )

    agents = detect_agents(use_heuristics=True)
    agent_names = [a.name for a in sorted(agents, key=lambda x: x.name)]
    if not agents:
        warnings.append("no CLI agents (aider, claude, opencode, etc.) were detected on your PATH")

    gateway_adapters = context.providers.list_gateway_adapters()
    config_path = context.settings.model_dump(mode="json")

    minification_enabled = config_path.get("minification", {}).get("enabled", False)
    cache_enabled = config_path.get("cache", {}).get("prefix_cache_enabled", False)
    intent_router_enabled = config_path.get("routing", {}).get("intent_router_enabled", False)
    diff_enabled = config_path.get("diff", {}).get("enabled", False)
    knowledge_enabled = config_path.get("knowledge", {}).get("vector_enabled", False)
    session_memory_enabled = config_path.get("session_memory", {}).get("enabled", False)
    agent_routing_strategy = config_path.get("agent_routing", {}).get("strategy", "legacy")
    arg_filtering = config_path.get("security", {}).get("sandbox", {}).get("enable_argument_filtering", False)

    return {
        "status": "ok" if not warnings else "warn",
        "provider_count": len(provider_names),
        "providers": provider_names,
        "agent_count": len(agents),
        "detected_agents": agent_names,
        "runtime_command": runtime_command,
        "gateway_adapters": gateway_adapters,
        "features": {
            "minification": minification_enabled,
            "prefix_cache": cache_enabled,
            "intent_router": intent_router_enabled,
            "context_diff": diff_enabled,
            "vector_rag": knowledge_enabled,
            "session_memory": session_memory_enabled,
            "agent_routing_strategy": agent_routing_strategy,
            "arg_filtering": arg_filtering,
        },
        "warnings": warnings,
    }
