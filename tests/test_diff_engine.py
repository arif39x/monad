from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from orchestration.diff import ContextDiffEngine


def _write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_diff_unchanged_file() -> None:
    async def run():
        engine = ContextDiffEngine(enabled=True)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.py"
            _write_file(path, "line1\nline2\nline3\n")
            delta1 = await engine.compute_delta(path)
            assert not delta1.has_changes
            assert delta1.is_new
            delta2 = await engine.compute_delta(path)
            assert not delta2.has_changes
            assert not delta2.is_new

    asyncio.run(run())


def test_diff_single_line_change() -> None:
    async def run():
        engine = ContextDiffEngine(enabled=True)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.py"
            _write_file(path, "line1\nline2\nline3\n")
            await engine.compute_delta(path)
            _write_file(path, "line1\nchanged\nline3\n")
            delta = await engine.compute_delta(path)
            assert delta.has_changes

    asyncio.run(run())


def test_diff_new_file() -> None:
    async def run():
        engine = ContextDiffEngine(enabled=True)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "new.py"
            _write_file(path, "def foo(): pass\n")
            delta = await engine.compute_delta(path)
            assert delta.is_new
            assert not delta.has_changes

    asyncio.run(run())


def test_diff_hash_consistency() -> None:
    async def run():
        engine = ContextDiffEngine(enabled=True)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.py"
            _write_file(path, "same content\n")
            await engine.compute_delta(path)
            snapshot1 = engine.get_snapshot(path)
            engine2 = ContextDiffEngine(enabled=True)
            await engine2.compute_delta(path)
            snapshot2 = engine2.get_snapshot(path)
            assert snapshot1 is not None and snapshot2 is not None
            assert snapshot1.hash == snapshot2.hash

    asyncio.run(run())


def test_disabled_engine() -> None:
    async def run():
        engine = ContextDiffEngine(enabled=False)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.py"
            _write_file(path, "content\n")
            delta = await engine.compute_delta(path)
            assert delta.is_new
            snapshot = engine.get_snapshot(path)
            assert snapshot is None

    asyncio.run(run())


def test_render_unchanged() -> None:
    async def run():
        engine = ContextDiffEngine(enabled=True)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.py"
            _write_file(path, "content\n")
            await engine.compute_delta(path)
            delta = await engine.compute_delta(path)
            rendered = engine.render_delta(delta)
            assert "unchanged" in rendered
            assert "test.py" in rendered

    asyncio.run(run())


def test_render_new_file() -> None:
    async def run():
        engine = ContextDiffEngine(enabled=True)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "new.py"
            _write_file(path, "def foo(): pass\n")
            delta = await engine.compute_delta(path)
            rendered = engine.render_delta(delta)
            assert "new.py" in rendered

    asyncio.run(run())


def test_stats() -> None:
    engine = ContextDiffEngine(enabled=True)
    stats = engine.stats
    assert stats["num_snapshots"] == 0
    assert stats["enabled"] is True
    assert stats["max_snapshots"] == 100


def test_clear() -> None:
    async def run():
        engine = ContextDiffEngine(enabled=True)
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "test.py"
            _write_file(path, "content\n")
            await engine.compute_delta(path)
            assert engine.stats["num_snapshots"] == 1
            engine.clear()
            assert engine.stats["num_snapshots"] == 0

    asyncio.run(run())


def test_max_snapshots_eviction() -> None:
    async def run():
        engine = ContextDiffEngine(enabled=True, max_snapshots=2)
        with tempfile.TemporaryDirectory() as td:
            for i in range(3):
                path = Path(td) / f"file_{i}.py"
                _write_file(path, f"content {i}\n")
                await engine.compute_delta(path)
            assert engine.stats["num_snapshots"] <= 2

    asyncio.run(run())
