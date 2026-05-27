from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from cli.context import CliContext


async def execute(
    context: CliContext,
    *,
    diagnostics_path: Path,
    attempt: int,
    apply: bool = False,
) -> dict[str, object]:
    diagnostics_blob = diagnostics_path.read_text(encoding="utf-8")
    trace_id = str(uuid4())
    plan = await context.engine.create_repair_plan(
        diagnostics_blob=diagnostics_blob,
        attempt=attempt,
        trace_id=trace_id,
    )

    from repair.executor import execute_repair_plan
    
    execution_results = await execute_repair_plan(plan, Path("."), apply=apply)

    return {
        "status": "ok",
        "trace_id": trace_id,
        "attempt": attempt,
        "directives": [directive.model_dump(mode="json") for directive in plan.directives],
        "requires_recompile": plan.requires_recompile,
        "execution_results": execution_results,
    }
