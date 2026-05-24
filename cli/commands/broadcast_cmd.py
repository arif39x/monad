from __future__ import annotations

from uuid import uuid4
from cli.context import CliContext

async def execute(context: CliContext, *, prompt: str, providers: list[str]) -> dict[str, object]:
    trace_id = str(uuid4())
    results = await context.engine.run_prompt_parallel(prompt, providers, trace_id)
    return {"trace_id": trace_id, "results": results}
