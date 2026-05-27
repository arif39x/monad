from __future__ import annotations

from orchestration.agents import Agent, AgentRole, AgentSettings
from orchestration.project import ProjectTask
from orchestration.routing import (
    AgentRouter,
    AgentStats,
    AgentWithStatus,
    HealthMonitor,
    HistoryStore,
    RoutingContext,
    RoutingStrategy,
    ScoringEngine,
)


def _make_agent(name: str, capabilities: list[str] | None = None) -> Agent:
    return Agent(
        AgentSettings(
            name=name,
            role=AgentRole.PLANNER,
            provider="test",
            capabilities=capabilities or [],
            cost_per_1k_tokens=0.01,
        )
    )


def test_routing_strategy_values() -> None:
    assert RoutingStrategy.LEGACY == "legacy"
    assert RoutingStrategy.CHEAPEST == "cheapest"
    assert RoutingStrategy.COST_EFFICIENT == "cost_efficient"


def test_history_store_record() -> None:
    store = HistoryStore()
    store.record("agent_a", "task_1", success=True, latency_ms=100, tokens=500)
    stats = store.get_agent_stats("agent_a")
    assert stats.total_tasks == 1
    assert stats.successful_tasks == 1
    assert stats.success_rate == 1.0


def test_history_store_failure() -> None:
    store = HistoryStore()
    store.record("agent_a", "task_1", success=False, latency_ms=50)
    stats = store.get_agent_stats("agent_a")
    assert stats.total_tasks == 1
    assert stats.failed_tasks == 1
    assert stats.success_rate == 0.0


def test_history_store_multiple_agents() -> None:
    store = HistoryStore()
    store.record("a", "t1", success=True, latency_ms=10)
    store.record("b", "t2", success=False, latency_ms=20)
    stats = store.get_stats()
    assert len(stats) == 2


def test_scoring_engine_basic() -> None:
    engine = ScoringEngine()
    agent_a = AgentWithStatus(
        agent=_make_agent("a"),
        success_rate=0.9,
        cost_per_1k_tokens=0.01,
        available=True,
    )
    agent_b = AgentWithStatus(
        agent=_make_agent("b"),
        success_rate=0.5,
        cost_per_1k_tokens=0.10,
        available=True,
    )
    task = ProjectTask(id="t1", agent="a", prompt="simple task")
    ctx = RoutingContext(task=task, available_agents=[agent_a, agent_b])
    score_a = engine.score(agent_a, ctx)
    score_b = engine.score(agent_b, ctx)
    assert score_a > score_b


def test_scoring_engine_capability_match() -> None:
    engine = ScoringEngine()
    agent_a = AgentWithStatus(
        agent=_make_agent("a", capabilities=["python", "test"]),
        supported_features={"python", "test"},
        available=True,
    )
    agent_b = AgentWithStatus(
        agent=_make_agent("b", capabilities=["rust"]),
        supported_features={"rust"},
        available=True,
    )
    task = ProjectTask(id="t1", agent="a", prompt="write python test")
    ctx = RoutingContext(task=task, available_agents=[agent_a, agent_b])
    assert engine._capability_match(agent_a, ctx) > engine._capability_match(agent_b, ctx)


def test_scoring_engine_empty_agents() -> None:
    engine = ScoringEngine()
    task = ProjectTask(id="t1", agent="a", prompt="hello")
    ctx = RoutingContext(task=task, available_agents=[])
    assert engine.score(AgentWithStatus(agent=_make_agent("a")), ctx) >= 0


def test_agent_router_legacy_select() -> None:
    from orchestration.agents import AgentRegistry

    AgentRegistry._reset()
    registry = AgentRegistry()
    agent = _make_agent("test_agent")
    registry.register(agent)
    router = AgentRouter(registry=registry, strategy=RoutingStrategy.LEGACY)
    agents_status = router.build_agent_status(registry.list_agents())
    task = ProjectTask(id="t1", agent="test_agent", prompt="hello")
    ctx = RoutingContext(task=task, available_agents=agents_status)

    import asyncio

    async def test() -> None:
        decision = await router.select(ctx)
        assert decision.primary.agent.settings.name == "test_agent"

    asyncio.run(test())


def test_agent_router_legacy_not_found() -> None:
    from orchestration.agents import AgentRegistry

    AgentRegistry._reset()
    registry = AgentRegistry()
    router = AgentRouter(registry=registry, strategy=RoutingStrategy.LEGACY)
    task = ProjectTask(id="t1", agent="nonexistent", prompt="hello")
    ctx = RoutingContext(task=task, available_agents=[])
    import asyncio

    async def test() -> None:
        import pytest

        with pytest.raises(RuntimeError, match="nonexistent"):
            await router.select(ctx)

    asyncio.run(test())


def test_agent_router_cheapest() -> None:
    from orchestration.agents import AgentRegistry

    AgentRegistry._reset()
    registry = AgentRegistry()
    cheap = Agent(
        AgentSettings(name="cheap", role=AgentRole.PLANNER, provider="t1", cost_per_1k_tokens=0.01)
    )
    expensive = Agent(
        AgentSettings(name="costly", role=AgentRole.PLANNER, provider="t2", cost_per_1k_tokens=1.0)
    )
    registry.register(cheap)
    registry.register(expensive)
    router = AgentRouter(registry=registry, strategy=RoutingStrategy.CHEAPEST)
    agents_status = router.build_agent_status(registry.list_agents())
    task = ProjectTask(id="t1", agent="cheap", prompt="hello")
    ctx = RoutingContext(task=task, available_agents=agents_status)

    import asyncio

    async def test() -> None:
        decision = await router.select(ctx, strategy=RoutingStrategy.CHEAPEST)
        assert decision.primary.agent.settings.name == "cheap"

    asyncio.run(test())


def test_health_monitor_default_ping() -> None:
    hm = HealthMonitor()
    assert hm.is_available("test") is True
    hm.mark_unavailable("test")
    assert hm.is_available("test") is False
    hm.mark_available("test")
    assert hm.is_available("test") is True


def test_build_agent_status() -> None:
    from orchestration.agents import AgentRegistry

    AgentRegistry._reset()
    registry = AgentRegistry()
    a = _make_agent("agent_a")
    registry.register(a)
    router = AgentRouter(registry=registry)
    status_list = router.build_agent_status(registry.list_agents())
    assert len(status_list) == 1
    assert status_list[0].agent.settings.name == "agent_a"
    assert status_list[0].available is True


def test_agent_stats_defaults() -> None:
    stats = AgentStats()
    assert stats.success_rate == 0.5
    assert stats.avg_latency_ms == 0.0
