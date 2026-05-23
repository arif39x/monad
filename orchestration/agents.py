from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from compiler.zero_compiler import ZeroModule

logger = logging.getLogger(__name__)


class AgentRole(StrEnum):
    PLANNER = "planner"
    REPAIRER = "repairer"
    VERIFIER = "verifier"
    OPTIMIZER = "optimizer"
    SECURITY_AUDITOR = "security_auditor"
    TEST_GENERATOR = "test_generator"


class AgentSettings(BaseModel):
    name: str
    role: AgentRole
    provider: str
    model: str | None = None
    description: str = ""
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)


class AgentTask(BaseModel):
    role: AgentRole
    objective: str
    trace_id: str


class Agent:
    def __init__(self, settings: AgentSettings, zerolang_path: str = "zerolang"):
        self.settings = settings
        self.zerolang_path = zerolang_path

    async def prepare_context(self, files: list[Path]) -> str:
        """
        Convert full files into AST skeletons before the prompt reaches the LLM.
        """
        from compiler.zero_compiler import get_ast_skeleton

        contexts = []
        for file_path in files:
            try:
                skeleton = await get_ast_skeleton(file_path, zerolang_path=self.zerolang_path)
                contexts.append(f"File: {file_path}\nAST Skeleton:\n{skeleton}")
            except Exception as e:
                logger.error(f"Failed to get AST for {file_path}: {e}")
                # Fallback to raw content if AST fails?
                # The prompt says "Never pass raw .py or .ts code if an AST representation exists."
                # For now, let's just log and skip or maybe use a basic placeholder.
                contexts.append(f"File: {file_path}\n(AST generation failed)")

        return "\n\n".join(contexts)


class AgentRegistry:
    _instance: AgentRegistry | None = None
    _agents: dict[str, Agent] = {}

    def __new__(cls) -> AgentRegistry:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, agent: Agent) -> None:
        self._agents[agent.settings.name] = agent
        logger.info(f"Registered agent: {agent.settings.name}")

    def get_agent(self, name: str) -> Agent | None:
        return self._agents.get(name)

    def list_agents(self) -> list[Agent]:
        return list(self._agents.values())
