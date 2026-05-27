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
from providers.base import ProviderRequest
from providers.registry import ProviderRegistry
from repair import RepairPlan, build_repair_plan
from sandbox import SecurityAuditLogger
from state import ConversationTurn, InMemorySessionStore, SessionMemoryManager, SessionState


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
        self._minifier: object | None = None
        self._prefix_cache: object | None = None
        self._intent_router: object | None = None
        self._diff_engine: object | None = None
        self._session_memory: SessionMemoryManager | None = None
        self._audit_logger: SecurityAuditLogger | None = None

    def _get_minifier(self):
        if self._minifier is None:
            from orchestration.minify import PromptMinifier
            self._minifier = PromptMinifier(
                enabled=self._settings.minification.enabled,
                target_tokens=self._settings.minification.target_tokens,
                hard_limit=self._settings.minification.hard_limit,
                preserve_user_message=self._settings.minification.preserve_user_message,
                structural_only=self._settings.minification.structural_only,
            )
        return self._minifier

    def _get_prefix_cache(self):
        if self._prefix_cache is None:
            from orchestration.cache import PrefixCacheManager
            self._prefix_cache = PrefixCacheManager(
                enabled=self._settings.cache.prefix_cache_enabled,
                ttl_seconds=self._settings.cache.prefix_cache_ttl_seconds,
                max_entries=self._settings.cache.prefix_cache_max_entries,
            )
        return self._prefix_cache

    def _get_intent_router(self):
        if self._intent_router is None:
            from orchestration.routing import IntentRouter
            self._intent_router = IntentRouter(
                enabled=self._settings.routing.intent_router_enabled,
                confidence_threshold=self._settings.routing.confidence_threshold,
                enable_shell_commands=self._settings.routing.enable_shell_commands,
                enable_file_operations=self._settings.routing.enable_file_operations,
            )
        return self._intent_router

    def _get_diff_engine(self):
        if self._diff_engine is None:
            from orchestration.diff import ContextDiffEngine
            self._diff_engine = ContextDiffEngine(
                enabled=self._settings.diff.enabled,
                max_snapshots=self._settings.diff.max_snapshots,
            )
        return self._diff_engine

    def _get_session_memory(self) -> SessionMemoryManager:
        if self._session_memory is None:
            self._session_memory = SessionMemoryManager(
                working_memory_turns=self._settings.session_memory.working_memory_turns,
                working_memory_max_tokens=self._settings.session_memory.working_memory_max_tokens,
                summarized_memory_max_depth=self._settings.session_memory.summarized_memory_max_depth,
                auto_summarize_threshold_tokens=self._settings.session_memory.auto_summarize_threshold_tokens,
            )
        return self._session_memory

    def _get_audit_logger(self) -> SecurityAuditLogger:
        if self._audit_logger is None:
            self._audit_logger = SecurityAuditLogger(
                log_path=self._settings.security.audit_log_path,
                retention_days=self._settings.security.audit_log_retention_days,
            )
        return self._audit_logger

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

        memory = self._get_session_memory() if self._settings.session_memory.enabled else None
        if memory and session.attributes.get("memory"):
            try:
                restored = SessionMemoryManager.deserialize(session.attributes["memory"])
                memory._working = restored._working
                memory._summarized = restored._summarized
                memory._token_budget = restored._token_budget
            except Exception:
                pass

        await self._emit(
            EventType.PROMPT_ISSUED,
            payload={"session_id": session.session_id, "prompt_chars": len(prompt)},
            trace_id=active_trace_id,
            actor="planner",
        )

        intent_router = self._get_intent_router()
        intent_result = intent_router.classify(prompt)

        await self._emit(
            EventType.INTENT_CLASSIFIED,
            payload={
                "intent": intent_result.intent,
                "confidence": intent_result.confidence,
                "prompt": prompt[:200],
            },
            trace_id=active_trace_id,
            actor="planner",
        )

        if intent_result.intent in ("shell_command", "file_operation") and intent_result.confidence >= 0.85:
            await self._emit(
                EventType.INTENT_ROUTED_LOCAL,
                payload={
                    "intent": intent_result.intent,
                    "command": intent_result.command or "",
                    "file_path": intent_result.file_path or "",
                },
                trace_id=active_trace_id,
                actor="planner",
            )
            if intent_result.intent == "shell_command" and intent_result.command:
                cmd = intent_result.command
                rest = prompt.strip()[len(cmd.split()[0]):].strip()
                full_cmd = [cmd] + (rest.split() if rest else [])
                exec_response = await self.execute_runtime_command(
                    command=full_cmd,
                    cwd=".",
                    trace_id=active_trace_id,
                )
                text = exec_response.stdout
                if memory:
                    turn = ConversationTurn(prompt=prompt, response=text)
                    memory.append_turn(turn)
                    session = session.model_copy(update={
                        "event_ids": session.event_ids + (active_trace_id,),
                        "attributes": {**(session.attributes or {}), "memory": memory.serialize()},
                    })
                    await self._session_store.upsert(session)
                return text
            return f"[local: {intent_result.intent}]"

        minifier = self._get_minifier()
        minified_prompt, minification_report = minifier.minify(prompt)

        prefix_cache = None
        cached_prefix_hash = ""
        cache_ttl_seconds = 0
        cacheable_prefix_tokens = 0
        if self._settings.cache.prefix_cache_enabled:
            prefix_cache = self._get_prefix_cache()
            cacheable_prefix = prefix_cache.extract_prefix(minified_prompt)
            entry = await prefix_cache.lookup(session.session_id, cacheable_prefix)
            if entry is not None:
                cached_prefix_hash = entry.prefix_hash
                cache_ttl_seconds = int(entry.ttl_seconds)
                cacheable_prefix_tokens = minification_report.final_tokens
            else:
                await prefix_cache.store(session.session_id, cacheable_prefix)

        memory_context = memory.build_context() if memory else ""
        import hashlib
        session_memory_hash = hashlib.sha256(memory_context.encode()).hexdigest()[:16] if memory_context else ""

        request = ProviderRequest(
            prompt=minified_prompt,
            model=provider_settings.model,
            temperature=provider_settings.default_temperature,
            max_tokens=provider_settings.default_max_tokens,
            timeout_seconds=provider_settings.timeout_seconds,
            trace_id=active_trace_id,
            pre_minified_tokens=minification_report.original_tokens,
            post_minified_tokens=minification_report.final_tokens,
            minification_ratio=minification_report.ratio,
            cached_prefix_hash=cached_prefix_hash,
            cache_ttl_seconds=cache_ttl_seconds,
            cacheable_prefix_tokens=cacheable_prefix_tokens,
            intent=intent_result.intent,
            intent_confidence=intent_result.confidence,
            session_memory_hash=session_memory_hash,
            session_memory_context=memory_context,
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

            if memory:
                turn = ConversationTurn(
                    prompt=prompt,
                    response=text,
                    token_count=minification_report.final_tokens + len(text) // 4,
                )
                memory.append_turn(turn)
                if memory.needs_summarization():
                    from state.summarizer import ExtractiveSummarizer
                    summarizer = ExtractiveSummarizer()
                    oldest = memory.working_memory.pop_oldest(2)
                    if oldest:
                        summary = summarizer.summarize(oldest)
                        memory.push_summary(summary)
                        await self._emit(
                            EventType.MEMORY_SUMMARIZED,
                            payload={"summary": summary.content[:200], "turn_count": summary.turn_count},
                            trace_id=active_trace_id,
                            actor="planner",
                        )
                session = session.model_copy(update={
                    "event_ids": session.event_ids + (active_trace_id,),
                    "attributes": {**(session.attributes or {}), "memory": memory.serialize()},
                })
                await self._session_store.upsert(session)

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
