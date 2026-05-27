from __future__ import annotations

import asyncio
import gzip
import json
import shutil
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

from orchestration.events.models import ElyonEvent, EventType


class SqliteEventStore:
    def __init__(
        self,
        db_path: Path,
        *,
        max_rows: int = 10000,
        max_mb: int = 100,
        archive_ttl_days: int = 90,
        archive_dir: Path | None = None,
    ) -> None:
        self._db_path = db_path
        self._max_rows = max_rows
        self._max_bytes = max_mb * 1024 * 1024
        self._archive_ttl_days = archive_ttl_days
        self._archive_dir = archive_dir or db_path.parent / "archive"
        self._lock = asyncio.Lock()
        self._conn: object = None
        self._init_lock = asyncio.Lock()
        self._initialized = False

    async def _ensure_connected(self) -> None:
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            import aiosqlite
            self._conn = await aiosqlite.connect(str(self._db_path))
            conn: aiosqlite.Connection = self._conn
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA cache_size=-2000")
            await conn.execute("PRAGMA synchronous=NORMAL")
            await self._init_schema(conn)
            self._initialized = True

    async def _init_schema(self, conn) -> None:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                trace_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                actor TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                duration_ms INTEGER
            )
        """)
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_trace_id ON events(trace_id)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_events_ts ON events(occurred_at)")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS metrics_rollup (
                bucket TEXT NOT NULL,
                event_type TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (bucket, event_type)
            )
        """)
        await conn.commit()

    async def append(self, event: ElyonEvent) -> None:
        await self._ensure_connected()
        import aiosqlite
        conn: aiosqlite.Connection = self._conn

        async with self._lock:
            await conn.execute(
                "INSERT OR IGNORE INTO events (id, trace_id, event_type, payload, actor, occurred_at, duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event.event_id,
                    event.metadata.trace_id,
                    event.event_type.value,
                    json.dumps(event.payload),
                    event.metadata.actor,
                    event.metadata.occurred_at.isoformat(),
                    event.metadata.duration_ms,
                ),
            )
            await conn.commit()
            await self._check_size(conn)

    async def append_many(self, events: list[ElyonEvent]) -> None:
        await self._ensure_connected()
        import aiosqlite
        conn: aiosqlite.Connection = self._conn

        async with self._lock:
            await conn.executemany(
                "INSERT OR IGNORE INTO events (id, trace_id, event_type, payload, actor, occurred_at, duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        e.event_id,
                        e.metadata.trace_id,
                        e.event_type.value,
                        json.dumps(e.payload),
                        e.metadata.actor,
                        e.metadata.occurred_at.isoformat(),
                        e.metadata.duration_ms,
                    )
                    for e in events
                ],
            )
            await conn.commit()
            await self._check_size(conn)

    async def list_all(self) -> list[ElyonEvent]:
        await self._ensure_connected()
        import aiosqlite
        conn: aiosqlite.Connection = self._conn
        async with self._lock:
            cursor = await conn.execute("SELECT * FROM events ORDER BY occurred_at")
            rows = await cursor.fetchall()
        return [self._row_to_event(r) for r in rows]

    async def list_by_trace(self, trace_id: str) -> list[ElyonEvent]:
        await self._ensure_connected()
        import aiosqlite
        conn: aiosqlite.Connection = self._conn
        async with self._lock:
            cursor = await conn.execute(
                "SELECT * FROM events WHERE trace_id = ? ORDER BY occurred_at",
                (trace_id,),
            )
            rows = await cursor.fetchall()
        return [self._row_to_event(r) for r in rows]

    async def list_by_type(self, event_type: EventType, limit: int = 100) -> list[ElyonEvent]:
        await self._ensure_connected()
        import aiosqlite
        conn: aiosqlite.Connection = self._conn
        async with self._lock:
            cursor = await conn.execute(
                "SELECT * FROM events WHERE event_type = ? ORDER BY occurred_at DESC LIMIT ?",
                (event_type.value, limit),
            )
            rows = await cursor.fetchall()
        return [self._row_to_event(r) for r in rows]

    async def list_since(self, timestamp: datetime) -> list[ElyonEvent]:
        await self._ensure_connected()
        import aiosqlite
        conn: aiosqlite.Connection = self._conn
        async with self._lock:
            cursor = await conn.execute(
                "SELECT * FROM events WHERE occurred_at >= ? ORDER BY occurred_at",
                (timestamp.isoformat(),),
            )
            rows = await cursor.fetchall()
        return [self._row_to_event(r) for r in rows]

    async def count_by_type(self, since: datetime) -> dict[str, int]:
        await self._ensure_connected()
        import aiosqlite
        conn: aiosqlite.Connection = self._conn
        async with self._lock:
            cursor = await conn.execute(
                "SELECT event_type, COUNT(*) FROM events WHERE occurred_at >= ? GROUP BY event_type",
                (since.isoformat(),),
            )
            rows = await cursor.fetchall()
        return {row[0]: row[1] for row in rows}

    async def purge_old(self, before: datetime) -> int:
        await self._ensure_connected()
        import aiosqlite
        conn: aiosqlite.Connection = self._conn
        async with self._lock:
            cursor = await conn.execute(
                "DELETE FROM events WHERE occurred_at < ?",
                (before.isoformat(),),
            )
            deleted = cursor.rowcount
            await conn.commit()
            await conn.execute("PRAGMA optimize")
        return deleted

    async def get_stats(self) -> dict:
        await self._ensure_connected()
        import aiosqlite
        conn: aiosqlite.Connection = self._conn
        async with self._lock:
            cursor = await conn.execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(payload)), 0) FROM events")
            row = await cursor.fetchone()
            active_events = row[0] if row else 0
            active_bytes = row[1] if row else 0

            cursor = await conn.execute("SELECT MIN(occurred_at), MAX(occurred_at) FROM events")
            row = await cursor.fetchone()

        archive_files = list(self._archive_dir.glob("*.jsonl.gz")) if self._archive_dir.exists() else []
        archive_bytes = sum(f.stat().st_size for f in archive_files)

        return {
            "active_events": active_events,
            "active_size_bytes": active_bytes,
            "archive_files": len(archive_files),
            "archive_size_bytes": archive_bytes,
            "oldest_event": row[0] if row and row[0] else None,
            "newest_event": row[1] if row and row[1] else None,
        }

    async def _check_size(self, conn) -> None:
        cursor = await conn.execute("SELECT COUNT(*) FROM events")
        row = await cursor.fetchone()
        count = row[0] if row else 0
        if count > self._max_rows:
            await self._archive_oldest(conn)

    async def _archive_oldest(self, conn) -> None:
        import aiosqlite
        conn_typed: aiosqlite.Connection = conn
        count = await conn_typed.execute_fetchall(
            "SELECT COUNT(*) FROM events"
        )
        if not count or count[0][0] <= self._max_rows:
            return

        excess = count[0][0] - int(self._max_rows * 0.9)
        cursor = await conn_typed.execute(
            "SELECT * FROM events ORDER BY occurred_at ASC LIMIT ?",
            (excess,),
        )
        rows = await cursor.fetchall()
        if not rows:
            return

        self._archive_dir.mkdir(parents=True, exist_ok=True)
        archive_name = f"{datetime.now(UTC).strftime('%Y-%m')}.jsonl.gz"
        archive_path = self._archive_dir / archive_name

        lines = []
        for row in rows:
            event = self._row_to_event(row)
            lines.append(event.model_dump_json(mode="json"))

        gz_data = gzip.compress("\n".join(lines).encode("utf-8"))
        archive_path.write_bytes(gz_data)

        ids = tuple(r[0] for r in rows)
        placeholders = ",".join("?" for _ in ids)
        await conn_typed.execute(f"DELETE FROM events WHERE id IN ({placeholders})", ids)
        await conn_typed.commit()

    @staticmethod
    def _row_to_event(row) -> ElyonEvent:
        return ElyonEvent.model_validate_json(
            json.dumps({
                "event_id": row[0],
                "event_type": row[2],
                "payload": json.loads(row[3]),
                "metadata": {
                    "trace_id": row[1],
                    "actor": row[4],
                    "occurred_at": row[5],
                    "duration_ms": row[6],
                },
            })
        )
