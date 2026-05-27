from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import StrEnum

from orchestration.agents import Agent, AgentSettings
from orchestration.project import ProjectTask

logger = logging.getLogger(__name__)


class RoutingStrategy(StrEnum):
    LEGACY = "legacy"
    CHEAPEST = "cheapest"
    FASTEST = "fastest"
    MOST_CAPABLE = "most_capable"
    LOAD_BALANCED = "load_balanced"
    FALLBACK_CHAIN = "fallback"
    COST_EFFICIENT = "cost_efficient"


@dataclass
class AgentStats:
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    total_latency_ms: float = 0.0
    total_tokens: int = 0
    last_seen: float = 0.0

    @property
    def success_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.5
        return self.successful_tasks / self.total_tasks

    @property
    def avg_latency_ms(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return self.total_latency_ms / self.total_tasks


@dataclass
class AgentWithStatus:
    agent: Agent
    current_load: int = 0
    avg_latency_ms: float = 0.0
    success_rate: float = 0.5
    cost_per_1k_tokens: float = 0.0
    available: bool = True
    supported_features: set[str] = field(default_factory=set)


@dataclass
class RoutingContext:
    task: ProjectTask
    available_agents: list[AgentWithStatus]
    history: dict[str, AgentStats] = field(default_factory=dict)
    budget_remaining: float = 0.0
    urgency: str = "medium"


@dataclass
class RoutingDecision:
    primary: AgentWithStatus
    fallback: list[AgentWithStatus] = field(default_factory=list)


class ScoringEngine:
    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self._weights = weights or {
            "capability": 0.30,
            "cost": 0.25,
            "load": 0.20,
            "reliability": 0.15,
            "latency": 0.10,
        }

    def score(self, agent: AgentWithStatus, context: RoutingContext) -> float:
        capability_score = self._capability_match(agent, context)
        cost_score = 1.0 - self._cost_ratio(agent, context)
        load_score = 1.0 - self._load_ratio(agent)
        reliability_score = agent.success_rate
        latency_score = 1.0 - self._latency_ratio(agent, context)

        return (
            self._weights.get("capability", 0) * capability_score
            + self._weights.get("cost", 0) * cost_score
            + self._weights.get("load", 0) * load_score
            + self._weights.get("reliability", 0) * reliability_score
            + self._weights.get("latency", 0) * latency_score
        )

    def _capability_match(self, agent: AgentWithStatus, context: RoutingContext) -> float:
        task_keywords = set(context.task.prompt.lower().split())
        agent_features = agent.supported_features
        if not agent_features or not task_keywords:
            return 0.5
        matched = sum(1 for f in agent_features if f.lower() in task_keywords)
        return min(1.0, matched / max(len(agent_features), 1))

    def _cost_ratio(self, agent: AgentWithStatus, context: RoutingContext) -> float:
        costs = [a.cost_per_1k_tokens for a in context.available_agents if a.available]
        max_cost = max(costs) if costs else 1.0
        if max_cost == 0:
            return 0.0
        return agent.cost_per_1k_tokens / max_cost

    def _load_ratio(self, agent: AgentWithStatus) -> float:
        max_load = 10
        return min(1.0, agent.current_load / max_load)

    def _latency_ratio(self, agent: AgentWithStatus, context: RoutingContext) -> float:
        latencies = [a.avg_latency_ms for a in context.available_agents if a.available]
        max_latency = max(latencies) if latencies else 1.0
        if max_latency == 0:
            return 0.0
        return agent.avg_latency_ms / max_latency


class HistoryStore:
    def __init__(self, ttl_days: int = 30) -> None:
        self._ttl_days = ttl_days
        self._agents: dict[str, AgentStats] = defaultdict(AgentStats)

    def get_stats(self) -> dict[str, AgentStats]:
        return dict(self._agents)

    def get_agent_stats(self, agent_name: str) -> AgentStats:
        return self._agents[agent_name]

    def record(
        self,
        agent_name: str,
        task_id: str,
        success: bool,
        latency_ms: float,
        tokens: int = 0,
    ) -> None:
        stats = self._agents[agent_name]
        stats.total_tasks += 1
        if success:
            stats.successful_tasks += 1
        else:
            stats.failed_tasks += 1
        stats.total_latency_ms += latency_ms
        stats.total_tokens += tokens
        stats.last_seen = time.time()


class HealthMonitor:
    def __init__(self, check_interval_seconds: float = 60.0) -> None:
        self._check_interval = check_interval_seconds
        self._agent_health: dict[str, bool] = {}
        self._last_checks: dict[str, float] = {}
        self._lock = asyncio.Lock()

    async def check_agent(self, agent: Agent) -> bool:
        now = time.time()
        last = self._last_checks.get(agent.settings.name, 0)
        if now - last < self._check_interval:
            return self._agent_health.get(agent.settings.name, True)

        async with self._lock:
            healthy = await self._ping(agent)
            self._agent_health[agent.settings.name] = healthy
            self._last_checks[agent.settings.name] = now
            return healthy

    async def _ping(self, agent: Agent) -> bool:
        try:
            adapter = agent.adapter
            return await asyncio.wait_for(
                adapter._ping() if hasattr(adapter, "_ping") else _default_ping(),
                timeout=5.0,
            )
        except Exception:
            return False

    def mark_unavailable(self, agent_name: str) -> None:
        self._agent_health[agent_name] = False

    def mark_available(self, agent_name: str) -> None:
        self._agent_health[agent_name] = True

    def is_available(self, agent_name: str) -> bool:
        return self._agent_health.get(agent_name, True)


async def _default_ping() -> bool:
    return True


class AgentRouter:
    def __init__(
        self,
        registry: object,
        history_store: HistoryStore | None = None,
        health_monitor: HealthMonitor | None = None,
        scoring_engine: ScoringEngine | None = None,
        strategy: RoutingStrategy = RoutingStrategy.LEGACY,
        fallback_enabled: bool = True,
        max_fallback_depth: int = 3,
    ) -> None:
        from orchestration.agents import AgentRegistry

        self._registry: AgentRegistry = registry
        self._history = history_store or HistoryStore()
        self._health = health_monitor or HealthMonitor()
        self._scoring = scoring_engine or ScoringEngine()
        self._strategy = strategy
        self._fallback_enabled = fallback_enabled
        self._max_fallback_depth = max_fallback_depth

    @property
    def history(self) -> HistoryStore:
        return self._history

    async def select(
        self,
        context: RoutingContext,
        strategy: RoutingStrategy | None = None,
    ) -> RoutingDecision:
        active_strategy = strategy or self._strategy

        if active_strategy == RoutingStrategy.LEGACY:
            return self._legacy_select(context)

        available = [a for a in context.available_agents if a.available]
        if not available:
            raise RuntimeError("No available agents to route to")

        scored = [(self._scoring.score(a, context), a) for a in available]
        scored.sort(key=lambda x: (-x[0], x[1].agent.settings.name))

        if active_strategy == RoutingStrategy.LOAD_BALANCED:
            scored.sort(key=lambda x: (x[1].current_load, -x[0], x[1].agent.settings.name))

        if active_strategy == RoutingStrategy.CHEAPEST:
            scored.sort(key=lambda x: (x[1].cost_per_1k_tokens, x[1].agent.settings.name))

        if active_strategy == RoutingStrategy.FASTEST:
            scored.sort(key=lambda x: (x[1].avg_latency_ms, x[1].agent.settings.name))

        if active_strategy == RoutingStrategy.MOST_CAPABLE:
            scored.sort(
                key=lambda x: (
                    -self._scoring._capability_match(x[1], context),
                    x[1].agent.settings.name,
                )
            )

        candidates = [a for _, a in scored]
        primary = candidates[0]
        fallbacks = candidates[1 : self._max_fallback_depth + 1] if self._fallback_enabled else []

        return RoutingDecision(primary=primary, fallback=fallbacks)

    def _legacy_select(self, context: RoutingContext) -> RoutingDecision:
        agent_name = context.task.agent
        for a in context.available_agents:
            if a.agent.settings.name == agent_name:
                return RoutingDecision(primary=a)
        raise RuntimeError(f"Agent '{agent_name}' not found in available agents")

    def build_agent_status(
        self,
        agent_list: list[Agent],
    ) -> list[AgentWithStatus]:
        result: list[AgentWithStatus] = []
        for agent_obj in agent_list:
            stats = self._history.get_agent_stats(agent_obj.settings.name)
            features = (
                set(agent_obj.settings.capabilities)
                if hasattr(agent_obj.settings, "capabilities")
                else set()
            )
            result.append(
                AgentWithStatus(
                    agent=agent_obj,
                    current_load=0,
                    avg_latency_ms=stats.avg_latency_ms,
                    success_rate=stats.success_rate,
                    cost_per_1k_tokens=getattr(agent_obj.settings, "cost_per_1k_tokens", 0.0),
                    available=self._health.is_available(agent_obj.settings.name),
                    supported_features=features,
                )
            )
        return result
