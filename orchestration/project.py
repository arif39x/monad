from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path

from bindings import RuntimeClient, RuntimeExecLimits, RuntimeExecRequest, RuntimeExecutionError
from sandbox.policy import SandboxPolicy


@dataclass(frozen=True)
class ProjectTask:
    id: str
    agent: str
    prompt: str
    files: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    context: str = ""


@dataclass
class TaskResult:
    task_id: str
    agent: str
    success: bool
    output: str
    error: str = ""
    token_estimate: int = 0


@dataclass
class ProjectPlan:
    tasks: list[ProjectTask] = field(default_factory=list)
    results: dict[str, TaskResult] = field(default_factory=dict)


def parse_project_jsonl(path: Path) -> ProjectPlan:
    tasks: list[ProjectTask] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        payload = json.loads(stripped)
        tasks.append(
            ProjectTask(
                id=payload["id"],
                agent=payload["agent"],
                prompt=payload["prompt"],
                files=tuple(payload.get("files", [])),
                depends_on=tuple(payload.get("depends_on", [])),
                context=payload.get("context", ""),
            )
        )
    return ProjectPlan(tasks=tasks)


def _estimate_tokens(text: str) -> int:
    return len(text) // 4


def _build_command(binary: str, prompt: str, signature: tuple[str, ...]) -> list[str]:
    cmd = [binary]
    for part in signature:
        if "{prompt}" in part:
            cmd.append(prompt)
        elif "{model}" in part:
            cmd.append("default")
        else:
            cmd.append(part)
    return cmd


async def run_task(
    task: ProjectTask,
    working_dir: Path,
    runtime_client: RuntimeClient,
    sandbox_policy: SandboxPolicy,
    signature: tuple[str, ...],
    *,
    dry_run: bool = False,
    zerolang_path: str = "zerolang",
) -> TaskResult:
    from orchestration.agents import AgentRegistry, Agent, AgentSettings, AgentRole

    full_prompt = task.prompt
    if task.context:
        full_prompt = f"{task.context}\n\n{task.prompt}"

    # Zero-Context Integration
    if task.files:
        registry = AgentRegistry()
        agent_obj = registry.get_agent(task.agent)
        if not agent_obj:
            # On-the-fly registration for detected agents
            agent_obj = Agent(
                AgentSettings(name=task.agent, role=AgentRole.PLANNER, provider="default"),
                zerolang_path=zerolang_path
            )
            registry.register(agent_obj)

        file_paths = [working_dir / f for f in task.files if (working_dir / f).exists()]
        if file_paths:
            ast_context = await agent_obj.prepare_context(file_paths)
            full_prompt = f"{full_prompt}\n\nCode Context (AST):\n{ast_context}"
        else:
            file_refs = ", ".join(task.files)
            full_prompt = f"{full_prompt}\n\nRelevant files (not found): {file_refs}"

    token_estimate = _estimate_tokens(full_prompt)
    command = _build_command(task.agent, full_prompt, signature)

    if dry_run:
        return TaskResult(
            task_id=task.id,
            agent=task.agent,
            success=True,
            output=f"[dry-run] would invoke: {' '.join(command)} ({token_estimate} est. tokens)",
            token_estimate=token_estimate,
        )

    if not sandbox_policy.command_allowed(command):
        return TaskResult(
            task_id=task.id,
            agent=task.agent,
            success=False,
            output="",
            error=f"Sandbox denied command: {' '.join(command[:2])}...",
            token_estimate=token_estimate,
        )

    request = RuntimeExecRequest(
        command=command,
        cwd=str(working_dir),
        env={},
        limits=RuntimeExecLimits(
            timeout_seconds=60.0,
            max_stdout_bytes=1_048_576,
            max_stderr_bytes=1_048_576,
        ),
    )

    try:
        response = await runtime_client.execute(request)
        return TaskResult(
            task_id=task.id,
            agent=task.agent,
            success=response.exit_code == 0,
            output=response.stdout.strip(),
            error=response.stderr.strip(),
            token_estimate=token_estimate,
        )
    except RuntimeExecutionError:
        return await _run_direct(task, command, working_dir, token_estimate)
    except Exception as exc:
        return TaskResult(
            task_id=task.id,
            agent=task.agent,
            success=False,
            output="",
            error=str(exc),
            token_estimate=token_estimate,
        )


async def _run_direct(
    task: ProjectTask,
    command: list[str],
    working_dir: Path,
    token_estimate: int,
) -> TaskResult:
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
        )
        stdout, stderr = await process.communicate()
        return TaskResult(
            task_id=task.id,
            agent=task.agent,
            success=process.returncode == 0,
            output=stdout.decode("utf-8", errors="replace").strip(),
            error=stderr.decode("utf-8", errors="replace").strip(),
            token_estimate=token_estimate,
        )
    except FileNotFoundError:
        return TaskResult(
            task_id=task.id,
            agent=task.agent,
            success=False,
            output="",
            error=f"Agent binary not found on PATH: {command[0]}",
            token_estimate=token_estimate,
        )


def _group_by_depth(tasks: list[ProjectTask]) -> list[list[ProjectTask]]:
    task_map = {t.id: t for t in tasks}
    depth: dict[str, int] = {}

    def compute_depth(task_id: str) -> int:
        if task_id in depth:
            return depth[task_id]
        task = task_map[task_id]
        if not task.depends_on:
            depth[task_id] = 0
            return 0
        max_dep = 0
        for dep in task.depends_on:
            if dep in task_map:
                max_dep = max(max_dep, compute_depth(dep) + 1)
        depth[task_id] = max_dep
        return max_dep

    for t in tasks:
        compute_depth(t.id)

    max_depth = max(depth.values()) if depth else 0
    layers: list[list[ProjectTask]] = [[] for _ in range(max_depth + 1)]
    for t in tasks:
        layers[depth[t.id]].append(t)

    return layers


async def execute_plan(
    plan: ProjectPlan,
    working_dir: Path,
    runtime_client: RuntimeClient,
    sandbox_policy: SandboxPolicy,
    agent_signatures: dict[str, tuple[str, ...]],
    *,
    dry_run: bool = False,
    zerolang_path: str = "zerolang",
) -> ProjectPlan:
    layers = _group_by_depth(plan.tasks)
    completed: dict[str, TaskResult] = {}

    for layer in layers:
        async def run_layer_task(task: ProjectTask) -> TaskResult:
            deps = [completed[d] for d in task.depends_on if d in completed]
            failed_deps = [d for d in deps if not d.success]
            if failed_deps:
                return TaskResult(
                    task_id=task.id,
                    agent=task.agent,
                    success=False,
                    output="",
                    error=f"Dependencies failed: {[d.task_id for d in failed_deps]}",
                )

            sig = agent_signatures.get(task.agent, ("{prompt}",))
            return await run_task(
                task,
                working_dir,
                runtime_client,
                sandbox_policy,
                sig,
                dry_run=dry_run,
                zerolang_path=zerolang_path,
            )

        results = await asyncio.gather(*[run_layer_task(t) for t in layer])
        for r in results:
            completed[r.task_id] = r

    plan.results = completed
    return plan
