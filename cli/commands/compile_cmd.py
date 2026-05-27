from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from cli.context import CliContext
from compiler import parse_structured_diagnostics


def parse_diagnostics_file(diagnostics_path: Path) -> dict[str, object]:
    raw = diagnostics_path.read_text(encoding="utf-8")
    diagnostics = parse_structured_diagnostics(raw)
    return {
        "status": "ok",
        "diagnostic_count": len(diagnostics),
        "diagnostics": [diagnostic.model_dump(mode="json") for diagnostic in diagnostics],
    }


async def execute_runtime_compile(
    context: CliContext,
    *,
    command: list[str],
    cwd: str,
    timeout_seconds: float | None,
) -> dict[str, object]:
    trace_id = str(uuid4())
    result = await context.engine.execute_runtime_command(
        command=command,
        cwd=cwd,
        timeout_seconds=timeout_seconds,
        trace_id=trace_id,
    )

    combined = "\n".join(part for part in (result.stdout, result.stderr) if part)
    diagnostics = parse_structured_diagnostics(combined)

    return {
        "status": "ok",
        "trace_id": trace_id,
        "exit_code": result.exit_code,
        "duration_ms": result.duration_ms,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "diagnostic_count": len(diagnostics),
        "diagnostics": [diagnostic.model_dump(mode="json") for diagnostic in diagnostics],
    }
