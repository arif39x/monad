from __future__ import annotations

from pathlib import Path

from cli.context import CliContext
from orchestration.agent_detector import KNOWN_SIGNATURES
from orchestration.project import execute_plan, parse_project_jsonl
from sandbox.policy import SandboxPolicy


async def execute(
    context: CliContext,
    *,
    project_file: str,
    cwd: str = ".",
    dry_run: bool = False,
) -> dict[str, object]:
    path = Path(project_file).resolve()
    if not path.exists():
        return {"status": "error", "error": f"Project file not found: {path}"}

    working_dir = Path(cwd).resolve()
    if not working_dir.exists():
        working_dir = path.parent

    plan = parse_project_jsonl(path)
    sandbox_policy = SandboxPolicy(context.settings.sandbox)

    result = await execute_plan(
        plan,
        working_dir=working_dir,
        runtime_client=context.runtime_client,
        sandbox_policy=sandbox_policy,
        agent_signatures=KNOWN_SIGNATURES,
        dry_run=dry_run,
        zerolang_path=context.settings.compiler.zerolang_path,
    )

    task_results = []
    total_tokens = 0
    for task_result in result.results.values():
        total_tokens += task_result.token_estimate
        preview = task_result.output[:200] if task_result.output else ""
        task_results.append(
            {
                "task_id": task_result.task_id,
                "agent": task_result.agent,
                "success": task_result.success,
                "output_preview": preview,
                "error": task_result.error,
                "token_estimate": task_result.token_estimate,
            }
        )

    all_ok = all(r.success for r in result.results.values())
    return {
        "status": "ok" if all_ok else "partial",
        "total_tasks": len(result.tasks),
        "completed": sum(1 for r in result.results.values() if r.success),
        "failed": sum(1 for r in result.results.values() if not r.success),
        "total_token_estimate": total_tokens,
        "tasks": task_results,
    }
