from __future__ import annotations

import asyncio
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from bindings import RuntimeClient, RuntimeExecLimits, RuntimeExecRequest, RuntimeExecResponse
from compiler import parse_structured_diagnostics
from orchestration.config import ElyonSettings
from orchestration.events import ElyonEvent, EventStore, EventType
from orchestration.logging import get_logger
from providers import ProviderRegistry, ProviderRequest
from repair import RepairPlan, build_repair_plan
from state import InMemorySessionStore, SessionState


class ElyonEngine:
    def __init__(
        self,
        *,
        settings: ElyonSettings,
        event_store: EventStore,
        session_store: InMemorySessionStore,
        provider_registry: ProviderRegistry,
        runtime_client: RuntimeClient,
    ) -> None:
        self._settings = settings
        self._event_store = event_store
        self._session_store = session_store
        self._provider_registry = provider_registry
        self._runtime_client = runtime_client
        self._logger = get_logger("elyon.engine")

    async def run_prompt(
        self,
        *,
        prompt: str,
        provider_name: str | None,
        trace_id: str | None = None,
        session_id: str | None = None,
        stream: bool = False,
    ) -> str:
        active_trace_id = trace_id or str(uuid4())
        session = await self._resolve_session(session_id)
        provider_settings = self._settings.provider(provider_name)

        await self._emit(
            EventType.PROMPT_ISSUED,
            payload={"session_id": session.session_id, "prompt_chars": len(prompt)},
            trace_id=active_trace_id,
            actor="planner",
        )

        request = ProviderRequest(
            prompt=prompt,
            model=provider_settings.model,
            temperature=provider_settings.default_temperature,
            max_tokens=provider_settings.default_max_tokens,
            timeout_seconds=provider_settings.timeout_seconds,
            trace_id=active_trace_id,
        )

        provider = await self._provider_registry.get(provider_settings.name)
        await self._emit(
            EventType.PROVIDER_REQUESTED,
            payload={"provider": provider_settings.name, "model": provider_settings.model},
            trace_id=active_trace_id,
            actor="planner",
        )

        try:
            start = perf_counter()
            if stream:
                chunks: list[str] = []
                async with asyncio.timeout(provider_settings.timeout_seconds):
                    async for chunk in provider.stream_complete(request):
                        chunks.append(chunk)
                text = "".join(chunks).strip()
            else:
                response = await asyncio.wait_for(
                    provider.complete(request),
                    timeout=provider_settings.timeout_seconds,
                )
                text = response.text

            await self._emit(
                EventType.PROVIDER_RESPONDED,
                payload={"provider": provider_settings.name, "output_chars": len(text)},
                trace_id=active_trace_id,
                actor="planner",
                duration_ms=int((perf_counter() - start) * 1000),
            )
            self._log(
                "info",
                "provider_completed",
                trace_id=active_trace_id,
                provider=provider_settings.name,
                output_chars=len(text),
            )
            return text
        except Exception as exc:
            await self._emit(
                EventType.RUN_FAILED,
                payload={"provider": provider_settings.name, "error": str(exc)},
                trace_id=active_trace_id,
                actor="planner",
            )
            self._log(
                "error",
                "provider_failed",
                trace_id=active_trace_id,
                provider=provider_settings.name,
                error=str(exc),
            )
            raise

    async def run_prompt_parallel(
        self,
        prompt: str,
        providers: list[str],
        trace_id: str,
    ) -> list[str]:
        async def run_single(provider: str) -> str:
            return await self.run_prompt(
                prompt=prompt,
                provider_name=provider,
                trace_id=trace_id,
            )

        return await asyncio.gather(*[run_single(p) for p in providers])

    async def execute_runtime_command(
        self,
        *,
        command: list[str],
        cwd: str,
        trace_id: str | None = None,
        timeout_seconds: float | None = None,
        env: dict[str, str] | None = None,
        policy_level: str | None = None,
    ) -> RuntimeExecResponse:
        from bindings.runtime_client import RuntimePolicyLevel

        active_trace_id = trace_id or str(uuid4())
        resolved_cwd = str(Path(cwd).resolve())
        limits = RuntimeExecLimits(
            timeout_seconds=timeout_seconds or self._settings.runtime.request_timeout_seconds,
            max_stdout_bytes=self._settings.runtime.max_stdout_bytes,
            max_stderr_bytes=self._settings.runtime.max_stderr_bytes,
        )
        request = RuntimeExecRequest(
            command=command,
            cwd=resolved_cwd,
            env=env or {},
            limits=limits,
            policy_level=RuntimePolicyLevel(
                policy_level or self._settings.sandbox.default_policy_level
            ),
        )

        await self._emit(
            EventType.SUBPROCESS_SPAWNED,
            payload={"command": command, "cwd": resolved_cwd},
            trace_id=active_trace_id,
            actor="verifier",
        )

        start = perf_counter()
        try:
            response = await self._runtime_client.execute(request)
            await self._emit(
                EventType.COMPILE_EXECUTED,
                payload={
                    "command": command,
                    "cwd": resolved_cwd,
                    "exit_code": response.exit_code,
                    "stdout_bytes": len(response.stdout.encode("utf-8")),
                    "stderr_bytes": len(response.stderr.encode("utf-8")),
                },
                trace_id=active_trace_id,
                actor="verifier",
                duration_ms=int((perf_counter() - start) * 1000),
            )
            return response
        except Exception as exc:
            await self._emit(
                EventType.RUN_FAILED,
                payload={"command": command, "cwd": resolved_cwd, "error": str(exc)},
                trace_id=active_trace_id,
                actor="verifier",
            )
            raise

    async def create_repair_plan(
        self,
        *,
        diagnostics_blob: str,
        attempt: int,
        trace_id: str | None = None,
    ) -> RepairPlan:
        active_trace_id = trace_id or str(uuid4())
        await self._emit(
            EventType.COMPILE_EXECUTED,
            payload={"attempt": attempt, "diagnostics_bytes": len(diagnostics_blob)},
            trace_id=active_trace_id,
            actor="repairer",
        )

        diagnostics = parse_structured_diagnostics(diagnostics_blob)
        for diagnostic in diagnostics:
            await self._emit(
                EventType.DIAGNOSTIC_EMITTED,
                payload=diagnostic.model_dump(mode="json"),
                trace_id=active_trace_id,
                actor="repairer",
            )

        plan = build_repair_plan(diagnostics, attempt=attempt, settings=self._settings.repair)
        await self._emit(
            EventType.REPAIR_GENERATED,
            payload=plan.model_dump(mode="json"),
            trace_id=active_trace_id,
            actor="repairer",
        )
        return plan

    async def events_for_trace(self, trace_id: str) -> list[ElyonEvent]:
        return await self._event_store.list_by_trace(trace_id)

    async def _resolve_session(self, session_id: str | None) -> SessionState:
        if session_id is None:
            return await self._session_store.create(attributes={"origin": "cli"})

        existing = await self._session_store.get(session_id)
        if existing is None:
            return await self._session_store.create(
                attributes={"origin": "cli", "requested": session_id}
            )
        return existing

    async def _emit(
        self,
        event_type: EventType,
        *,
        payload: dict[str, object],
        trace_id: str,
        actor: str,
        duration_ms: int | None = None,
    ) -> ElyonEvent:
        event = ElyonEvent.create(
            event_type=event_type,
            payload=payload,
            trace_id=trace_id,
            actor=actor,
            duration_ms=duration_ms,
        )
        await self._event_store.append(event)
        return event

    def _log(self, level: str, message: str, **fields: object) -> None:
        logger_method = getattr(self._logger, level)
        try:
            logger_method(message, **fields)
        except TypeError:
            logger_method(f"{message} {fields}")
