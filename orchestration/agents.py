from __future__ import annotations

import logging
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from orchestration.adapters.base import AbstractAgentAdapter, AdapterContext
from orchestration.adapters.registry import get_adapter
from orchestration.knowledge.store import KnowledgeStore, KnowledgeEntry

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
    capabilities: list[str] = Field(default_factory=list)
    cost_per_1k_tokens: float = 0.0
    max_concurrent: int = 1
    priority: int = 0


class AgentTask(BaseModel):
    role: AgentRole
    objective: str
    trace_id: str


class Agent:
    def __init__(self, settings: AgentSettings):
        self.settings = settings
        self._adapter = get_adapter(settings.name)

    @property
    def adapter(self) -> AbstractAgentAdapter:
        return self._adapter

    async def prepare_context(self, files: list[Path], knowledge_store: KnowledgeStore | None = None) -> str:
        """
        Convert full files into context before the prompt reaches the LLM.
        """
        contexts = []
        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8")
                contexts.append(f"File: {file_path}\nContent:\n{content}")
            except Exception as e:
                logger.error(f"Failed to read {file_path}: {e}")
                contexts.append(f"File: {file_path}\n(Reading failed)")

        if knowledge_store:
            knowledge_store.save()

        return "\n\n".join(contexts)



class AgentRegistry:
    _instance: AgentRegistry | None = None
    _agents: dict[str, Agent] = {}

    def __new__(cls) -> AgentRegistry:
        if cls._instance is not None:
            return cls._instance
        cls._instance = super().__new__(cls)
        cls._instance._agents = {}
        return cls._instance

    def register(self, agent: Agent) -> None:
        self._agents[agent.settings.name] = agent
        logger.info(f"Registered agent: {agent.settings.name}")

    def get_agent(self, name: str) -> Agent | None:
        return self._agents.get(name)

    def list_agents(self) -> list[Agent]:
        return list(self._agents.values())

    @classmethod
    def _reset(cls) -> None:
        cls._instance = None
        cls._agents.clear()
