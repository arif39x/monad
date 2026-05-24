from __future__ import annotations

from cli.context import CliContext
from orchestration.agent_detector import detect_agents
from orchestration.adapters.registry import get_adapter
from orchestration.adapters.base import AdapterContext


def execute(context: CliContext | None) -> dict[str, object]:
    detected = detect_agents()

    agents_list: list[dict[str, object]] = []
    for agent in sorted(detected, key=lambda a: a.name):
        adapter = get_adapter(agent.binary)
        ctx = AdapterContext(prompt="<prompt>", model="<model>")
        cmd = adapter.build_command(agent.binary, ctx)
        signature_display = " ".join(cmd)
        agents_list.append(
            {
                "name": agent.name,
                "binary": agent.binary,
                "path": agent.path,
                "description": agent.description,
                "signature": signature_display,
            }
        )

    config_agents: list[dict[str, object]] = []
    if context is not None:
        for _name, agent_settings in context.settings.agents.items():
            config_agents.append(
                {
                    "name": agent_settings.name,
                    "role": agent_settings.role.value,
                    "provider": agent_settings.provider,
                    "model": agent_settings.model,
                    "description": agent_settings.description,
                }
            )

    return {
        "status": "ok",
        "agents": agents_list,
        "config_agents": config_agents,
    }
