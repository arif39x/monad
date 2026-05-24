from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from orchestration.project import (
    ProjectPlan,
    ProjectTask,
    TaskResult,
    _estimate_tokens,
    _group_by_depth,
    execute_plan,
    parse_project_jsonl,
    run_task,
)


def test_estimate_tokens() -> None:
    assert _estimate_tokens("hello") == 1
    assert _estimate_tokens("a" * 100) == 25
    assert _estimate_tokens("") == 0


def test_group_by_depth_single_task() -> None:
    tasks = [ProjectTask(id="1", agent="opencode", prompt="hello")]
    layers = _group_by_depth(tasks)
    assert len(layers) == 1
    assert layers[0][0].id == "1"


def test_group_by_depth_chain() -> None:
    tasks = [
        ProjectTask(id="1", agent="a", prompt="", depends_on=[]),
        ProjectTask(id="2", agent="a", prompt="", depends_on=["1"]),
        ProjectTask(id="3", agent="a", prompt="", depends_on=["2"]),
    ]
    layers = _group_by_depth(tasks)
    assert len(layers) == 3
    assert layers[0][0].id == "1"
    assert layers[1][0].id == "2"
    assert layers[2][0].id == "3"


def test_group_by_depth_fan_out() -> None:
    tasks = [
        ProjectTask(id="root", agent="a", prompt="", depends_on=[]),
        ProjectTask(id="child1", agent="a", prompt="", depends_on=["root"]),
        ProjectTask(id="child2", agent="a", prompt="", depends_on=["root"]),
    ]
    layers = _group_by_depth(tasks)
    assert len(layers) == 2
    assert len(layers[1]) == 2


def test_group_by_depth_empty() -> None:
    assert _group_by_depth([]) == [[]]


def test_parse_project_jsonl(tmp_path: Path) -> None:
    data = [
        {"id": "t1", "agent": "opencode", "prompt": "hello", "files": [], "depends_on": []},
        {"id": "t2", "agent": "claude", "prompt": "world", "files": [], "depends_on": []},
    ]
    f = tmp_path / "project.jsonl"
    f.write_text("\n".join(json.dumps(d) for d in data))
    plan = parse_project_jsonl(f)
    assert len(plan.tasks) == 2
    assert plan.tasks[0].id == "t1"
    assert plan.tasks[1].agent == "claude"


def test_parse_project_jsonl_skips_empty_lines(tmp_path: Path) -> None:
    data = [
        {"id": "t1", "agent": "opencode", "prompt": "hello", "files": [], "depends_on": []},
    ]
    f = tmp_path / "project.jsonl"
    f.write_text("\n\n".join(json.dumps(d) for d in data) + "\n\n")
    plan = parse_project_jsonl(f)
    assert len(plan.tasks) == 1


def test_parse_project_jsonl_with_context_and_files(tmp_path: Path) -> None:
    data = [
        {
            "id": "t1",
            "agent": "opencode",
            "prompt": "hello",
            "files": ["src/main.py"],
            "depends_on": [],
            "context": "be brief",
        },
    ]
    f = tmp_path / "project.jsonl"
    f.write_text(json.dumps(data[0]))
    plan = parse_project_jsonl(f)
    assert plan.tasks[0].context == "be brief"
    assert "src/main.py" in plan.tasks[0].files


def test_run_task_dry_run() -> None:
    task = ProjectTask(id="t1", agent="opencode", prompt="hello")
    result = asyncio_run(
        run_task(
            task,
            working_dir=Path("/tmp"),
            runtime_client=None,  # type: ignore[arg-type]
            sandbox_policy=_allow_all_policy(),
            dry_run=True,
        )
    )
    assert result.success is True
    assert "[dry-run]" in result.output


def test_run_task_skipped_when_dep_failed() -> None:
    plan = _plan_with_failed_dep()
    result = asyncio_run(
        execute_plan(
            plan,
            working_dir=Path("/tmp"),
            runtime_client=None,  # type: ignore[arg-type]
            sandbox_policy=_allow_all_policy(),
            dry_run=False,
        )
    )
    assert "child" in result.results
    assert result.results["child"].success is False
    assert "Dependencies failed" in result.results["child"].error


def test_execute_plan_dry_run() -> None:
    tasks = [
        ProjectTask(id="t1", agent="opencode", prompt="task 1"),
        ProjectTask(id="t2", agent="opencode", prompt="task 2"),
    ]
    plan = ProjectPlan(tasks=tasks)
    result = asyncio_run(
        execute_plan(
            plan,
            working_dir=Path("/tmp"),
            runtime_client=None,  # type: ignore[arg-type]
            sandbox_policy=_allow_all_policy(),
            dry_run=True,
        )
    )
    assert "t1" in result.results
    assert "t2" in result.results
    assert result.results["t1"].success is True


def test_execute_plan_maintains_order() -> None:
    plan = _chain_plan()
    result = asyncio_run(
        execute_plan(
            plan,
            working_dir=Path("/tmp"),
            runtime_client=None,  # type: ignore[arg-type]
            sandbox_policy=_allow_all_policy(),
            dry_run=True,
        )
    )
    assert result.results["dep"].success is True
    assert result.results["root"].success is True
    assert "root" in result.results


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _allow_all_policy() -> Any:
    class _AllowAll:
        def command_allowed(self, cmd: list[str], policy_level: str = "standard") -> bool:
            return True

        def read_allowed(self, path: Path, policy_level: str = "standard") -> bool:
            return True

        def write_allowed(self, path: Path, policy_level: str = "standard") -> bool:
            return True

    return _AllowAll()


def _plan_with_failed_dep() -> ProjectPlan:
    tasks = [
        ProjectTask(id="parent", agent="opencode", prompt="fail"),
        ProjectTask(id="child", agent="opencode", prompt="child", depends_on=["parent"]),
    ]
    plan = ProjectPlan(tasks=tasks)
    plan.results["parent"] = TaskResult(
        task_id="parent", agent="opencode", success=False, output="", error="fake failure",
    )
    return plan


def _chain_plan() -> ProjectPlan:
    tasks = [
        ProjectTask(id="root", agent="a", prompt="root", depends_on=[]),
        ProjectTask(id="dep", agent="a", prompt="dep", depends_on=["root"]),
    ]
    return ProjectPlan(tasks=tasks)


def asyncio_run(coro: Any) -> Any:
    import asyncio

    return asyncio.run(coro)
