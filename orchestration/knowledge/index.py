from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class IndexEntry:
    chunk_id: str
    embedding: list[float]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    chunk_id: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorIndex:
    def __init__(self, dimension: int = 128) -> None:
        self._dimension = dimension
        self._entries: dict[str, IndexEntry] = {}
        self._dirty = False

    def upsert(self, chunk_id: str, embedding: list[float], metadata: dict[str, Any] | None = None) -> None:
        if len(embedding) != self._dimension:
            raise ValueError(f"Expected dimension {self._dimension}, got {len(embedding)}")
        self._entries[chunk_id] = IndexEntry(
            chunk_id=chunk_id,
            embedding=embedding,
            metadata=metadata or {},
        )
        self._dirty = True

    def delete(self, chunk_id: str) -> bool:
        if chunk_id in self._entries:
            del self._entries[chunk_id]
            self._dirty = True
            return True
        return False

    def search(self, query_embedding: list[float], k: int = 10) -> list[SearchResult]:
        if not self._entries:
            return []

        scored: list[tuple[float, IndexEntry]] = []
        for entry in self._entries.values():
            score = self._cosine_similarity(query_embedding, entry.embedding)
            scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            SearchResult(chunk_id=e.chunk_id, score=s, metadata=e.metadata)
            for s, e in scored[:k]
        ]

    def search_with_filter(
        self,
        query_embedding: list[float],
        k: int = 10,
        filter_fn: Any = None,
    ) -> list[SearchResult]:
        if filter_fn is None:
            return self.search(query_embedding, k)

        scored: list[tuple[float, IndexEntry]] = []
        for entry in self._entries.values():
            if not filter_fn(entry.metadata):
                continue
            score = self._cosine_similarity(query_embedding, entry.embedding)
            scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            SearchResult(chunk_id=e.chunk_id, score=s, metadata=e.metadata)
            for s, e in scored[:k]
        ]

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def dimension(self) -> int:
        return self._dimension

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "dimension": self._dimension,
            "entries": [
                {
                    "chunk_id": e.chunk_id,
                    "embedding": e.embedding,
                    "metadata": e.metadata,
                }
                for e in self._entries.values()
            ],
        }
        path.write_text(json.dumps(data))
        self._dirty = False

    def load(self, path: Path) -> None:
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text())
            self._dimension = data.get("dimension", 128)
            self._entries.clear()
            for entry_data in data.get("entries", []):
                entry = IndexEntry(
                    chunk_id=entry_data["chunk_id"],
                    embedding=entry_data["embedding"],
                    metadata=entry_data.get("metadata", {}),
                )
                self._entries[entry.chunk_id] = entry
            self._dirty = False
        except (json.JSONDecodeError, OSError, KeyError):
            pass

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
