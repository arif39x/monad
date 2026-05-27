from __future__ import annotations

import asyncio
import time
from pathlib import Path

from orchestration.diff import ContextDiffEngine
from orchestration.routing import Intent, IntentRouter


class TestIntentRouterBenchmarks:
    def test_intent_classification_shell(self) -> None:
        router = IntentRouter(enabled=True)
        start = time.perf_counter()
        for _ in range(1000):
            router.classify("list files in src/")
        elapsed = (time.perf_counter() - start) / 1000
        assert elapsed < 0.001

    def test_intent_classification_code_gen(self) -> None:
        router = IntentRouter(enabled=True)
        start = time.perf_counter()
        for _ in range(1000):
            router.classify("write a function for fibonacci")
        elapsed = (time.perf_counter() - start) / 1000
        assert elapsed < 0.001

    def test_intent_classification_ambiguous(self) -> None:
        router = IntentRouter(enabled=True)
        start = time.perf_counter()
        for _ in range(1000):
            router.classify("banana yellow fruit")
        elapsed = (time.perf_counter() - start) / 1000
        assert elapsed < 0.001


class TestDiffEngineBenchmarks:
    def test_diff_first_access(self, tmp_path: Path) -> None:
        engine = ContextDiffEngine(enabled=True, max_snapshots=10)
        p = tmp_path / "test_bench.py"
        p.write_text("line1\nline2\nline3\n" * 50)
        async def run():
            start = time.perf_counter()
            for _ in range(100):
                await engine.compute_delta(p)
            return (time.perf_counter() - start) / 100
        elapsed = asyncio.run(run())
        assert elapsed < 0.05
