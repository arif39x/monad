from __future__ import annotations

import argparse
import asyncio
import os
import shlex
from pathlib import Path
from typing import Any

from cli.banner import run_interactive
from cli.commands import (
    agents_execute,
    doctor_execute,
    execute_runtime_compile,
    execute_zero_compile,
    init_execute,
    parse_diagnostics_file,
    project_execute,
    providers_execute,
    repair_execute,
    run_execute,
    sandbox_execute,
    trace_execute,
)
from cli.context import build_context
from cli.output import render


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="monad", add_help=False)
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    parser.add_argument("--help", action="store_true", help="Show this help message")

    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init")
    init_parser.add_argument("--output", required=True)
    init_parser.add_argument("--force", action="store_true")

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--config")
    run_parser.add_argument("--prompt", required=True)
    run_parser.add_argument("--provider")
    run_parser.add_argument("--stream", action="store_true")
    run_parser.add_argument("--session-id")

    repair_parser = subparsers.add_parser("repair")
    repair_parser.add_argument("--config")
    repair_parser.add_argument("--diagnostics", required=True)
    repair_parser.add_argument("--attempt", required=True, type=int)

    doctor_parser = subparsers.add_parser("doctor")
    doctor_parser.add_argument("--config")

    providers_parser = subparsers.add_parser("providers")
    providers_parser.add_argument("--config")

    agents_parser = subparsers.add_parser("agents")
    agents_parser.add_argument("--config")

    project_parser = subparsers.add_parser("project")
    project_parser.add_argument("--config")
    project_parser.add_argument("--file", required=True, help="Path to JSONL project file")
    project_parser.add_argument("--cwd", default=".", help="Working directory for task execution")
    project_parser.add_argument("--dry-run", action="store_true", help="Simulate without executing")

    sandbox_parser = subparsers.add_parser("sandbox")
    sandbox_parser.add_argument("--config")
    sandbox_parser.add_argument("--command", dest="sandbox_command", nargs="+")

    trace_parser = subparsers.add_parser("trace")
    trace_parser.add_argument("--config")
    trace_parser.add_argument("--trace-id", required=True)

    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--config")
    compile_parser.add_argument("--diagnostics")
    compile_parser.add_argument("--exec-command")
    compile_parser.add_argument("--zero", type=str, help="Compile a .zero file and estimate token savings")
    compile_parser.add_argument("--cwd", default=".")
    compile_parser.add_argument("--timeout-seconds", type=float)

    subparsers.add_parser("shell")
    subparsers.add_parser("tui")

    return parser


def _resolve_config_path(raw_path: str | None) -> Path:
    env_path = os.getenv("MONAD_CONFIG")
    selected = raw_path or env_path
    if selected is None:
        raise ValueError("No config path provided. Pass --config or set MONAD_CONFIG.")
    return Path(selected)


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "init":
        return init_execute(Path(args.output), force=args.force)

    if args.command == "compile" and args.diagnostics:
        return parse_diagnostics_file(Path(args.diagnostics))

    if args.command == "compile" and args.zero:
        return execute_zero_compile(Path(args.zero))

    if args.command == "agents":
        config_path = getattr(args, "config", None) or os.getenv("MONAD_CONFIG")
        if config_path:
            context = build_context(Path(config_path))
            return agents_execute(context)
        return agents_execute(None)

    config_path = _resolve_config_path(getattr(args, "config", None))
    context = build_context(config_path)

    if args.command == "run":
        return await run_execute(
            context,
            prompt=args.prompt,
            provider=args.provider,
            stream=args.stream,
            session_id=args.session_id,
        )

    if args.command == "repair":
        return await repair_execute(
            context,
            diagnostics_path=Path(args.diagnostics),
            attempt=args.attempt,
        )

    if args.command == "doctor":
        return doctor_execute(context)

    if args.command == "providers":
        return providers_execute(context)

    if args.command == "project":
        return await project_execute(context, project_file=args.file, cwd=args.cwd, dry_run=args.dry_run)

    if args.command == "sandbox":
        return sandbox_execute(context, command=args.sandbox_command)

    if args.command == "trace":
        return await trace_execute(context, trace_id=args.trace_id)

    if args.command == "compile":
        if not args.exec_command:
            raise ValueError("compile requires either --diagnostics or --exec-command")
        command = shlex.split(args.exec_command)
        if not command:
            raise ValueError("--exec-command cannot be empty")
        return await execute_runtime_compile(
            context,
            command=command,
            cwd=args.cwd,
            timeout_seconds=args.timeout_seconds,
        )

    raise ValueError(f"Unsupported command: {args.command}")


def main() -> None:
    parser = _build_parser()
    args, _ = parser.parse_known_args()

    if args.command is None and not args.help:
        if args.json:
            import json as j
            print(j.dumps({"status": "ok", "message": "Monad v0.1.0 — multi-agent CLI workspace"}))
        else:
            from cli.tui import run_tui
            run_tui()
        return

    if args.help:
        if args.json:
            import json as j
            print(j.dumps({"status": "ok", "message": "Monad v0.1.0 — multi-agent CLI workspace"}))
        else:
            from cli.banner import HELP_TEXT
            print(HELP_TEXT)
        return

    if args.command == "shell":
        run_interactive()
        return

    if args.command == "tui":
        from cli.tui import run_tui
        run_tui()
        return

    try:
        payload = asyncio.run(_run(args))
        print(render(payload, as_json=args.json))
    except Exception as exc:
        error_payload = {"status": "error", "error": str(exc)}
        print(render(error_payload, as_json=args.json))
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
