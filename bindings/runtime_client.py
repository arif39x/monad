from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
from time import perf_counter
from typing import Protocol

from pydantic import BaseModel, Field


from enum import StrEnum

class RuntimeExecutionError(RuntimeError):
    pass


class RuntimePolicyLevel(StrEnum):
    RESTRICTED = "restricted"
    STANDARD = "standard"
    PRIVILEGED = "privileged"


class RuntimeExecLimits(BaseModel):
    timeout_seconds: float = Field(gt=0)
    max_stdout_bytes: int = Field(gt=0)
    max_stderr_bytes: int = Field(gt=0)


class RuntimeExecRequest(BaseModel):
    command: list[str]
    cwd: str
    env: dict[str, str] = Field(default_factory=dict)
    limits: RuntimeExecLimits
    policy_level: RuntimePolicyLevel = RuntimePolicyLevel.STANDARD


class RuntimeExecResponse(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int = Field(ge=0)


class RuntimeClient(Protocol):
    async def execute(self, request: RuntimeExecRequest) -> RuntimeExecResponse: ...


class RustRuntimeClient:
    def __init__(
        self,
        *,
        runtime_command: list[str],
        allowed_command_prefixes: list[str],
    ) -> None:
        self._runtime_command = _resolve_runtime_command(runtime_command, base_dir=Path.cwd())
        self._allowed_command_prefixes = allowed_command_prefixes

    async def execute(self, request: RuntimeExecRequest) -> RuntimeExecResponse:
        if not self._runtime_command:
            raise RuntimeExecutionError("runtime.command is empty")

        runtime_payload = {
            "command": request.command,
            "cwd": request.cwd,
            "env": request.env,
            "limits": {
                "timeout_ms": int(request.limits.timeout_seconds * 1000),
                "max_stdout_bytes": request.limits.max_stdout_bytes,
                "max_stderr_bytes": request.limits.max_stderr_bytes,
            },
            "policy_level": request.policy_level.value,
        }

        runtime_env = os.environ.copy()
        runtime_env["ELYON_RUNTIME_ALLOWED_PREFIXES"] = ",".join(self._allowed_command_prefixes)

        start = perf_counter()
        try:
            process = await asyncio.create_subprocess_exec(
                *self._runtime_command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=request.cwd,
                env=runtime_env,
            )
        except FileNotFoundError as exc:
            command_display = " ".join(self._runtime_command)
            raise RuntimeExecutionError(f"runtime executable not found: {command_display}") from exc

        payload_bytes = json.dumps(runtime_payload, separators=(",", ":")).encode("utf-8")
        timeout_with_guard = request.limits.timeout_seconds + 2.0

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(input=payload_bytes),
                timeout=timeout_with_guard,
            )
        except TimeoutError as exc:
            process.kill()
            await process.wait()
            raise RuntimeExecutionError("runtime process timed out") from exc

        stdout_text = stdout_bytes.decode("utf-8", errors="replace")
        stderr_text = stderr_bytes.decode("utf-8", errors="replace")

        if process.returncode != 0:
            error_message = _extract_error(stdout_text) or stderr_text or "runtime process failed"
            raise RuntimeExecutionError(error_message)

        try:
            response = RuntimeExecResponse.model_validate_json(stdout_text)
        except Exception as exc:
            raise RuntimeExecutionError("runtime response was not valid JSON") from exc

        duration_ms = int((perf_counter() - start) * 1000)
        if response.duration_ms > 0:
            return response

        return response.model_copy(update={"duration_ms": duration_ms})


class NullRuntimeClient:
    async def execute(self, request: RuntimeExecRequest) -> RuntimeExecResponse:
        return RuntimeExecResponse(
            exit_code=1,
            stdout="",
            stderr=(
                "Runtime execution is not connected. Configure runtime bindings to delegate "
                "subprocess management to Rust runtime core."
            ),
            duration_ms=0,
        )


def ensure_runtime_command_is_executable(runtime_command: list[str], project_root: Path) -> bool:
    if not runtime_command:
        return False

    executable = runtime_command[0]
    executable_path = Path(executable)
    if executable_path.is_absolute():
        return executable_path.exists()

    if "/" in executable or executable.startswith("."):
        return (project_root / executable_path).exists()

    return shutil.which(executable) is not None


def _extract_error(raw_stdout: str) -> str | None:
    stripped = raw_stdout.strip()
    if not stripped:
        return None

    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError:
        return None

    candidate = payload.get("error") if isinstance(payload, dict) else None
    return candidate if isinstance(candidate, str) else None


def _resolve_runtime_command(runtime_command: list[str], *, base_dir: Path) -> list[str]:
    if not runtime_command:
        return runtime_command

    executable = runtime_command[0]
    executable_path = Path(executable)
    if executable_path.is_absolute():
        return runtime_command

    if "/" in executable or executable.startswith("."):
        resolved = (base_dir / executable_path).resolve()
        return [str(resolved), *runtime_command[1:]]

    return runtime_command
