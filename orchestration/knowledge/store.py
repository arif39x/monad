from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orchestration.knowledge.chunker import CodeAwareChunker
from orchestration.knowledge.embedder import EmbeddingCache, create_embedder
from orchestration.knowledge.index import SearchResult, VectorIndex


@dataclass
class KnowledgeEntry:
    path: str
    symbol: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoredKnowledgeEntry:
    entry: KnowledgeEntry
    score: float
    chunk_range: tuple[int, int] | None = None


class KnowledgeStore:
    def __init__(
        self,
        index_path: Path,
        *,
        vector_enabled: bool = False,
        embedding_backend: str = "simple",
        chunk_strategy: str = "auto",
    ) -> None:
        self._index_path = index_path
        self._json_path = index_path / "knowledge.json"
        self._vector_path = index_path / "vector_index.json"
        self._cache_dir = index_path / "embedding_cache"
        self._vector_enabled = vector_enabled
        self._entries: list[KnowledgeEntry] = []
        self._chunker = CodeAwareChunker()
        self._embedder, self._dimension = create_embedder(embedding_backend)
        self._embedding_cache = EmbeddingCache(cache_dir=self._cache_dir if vector_enabled else None)
        self._vector_index = VectorIndex(dimension=self._dimension)
        self._load()

    def _load(self) -> None:
        if self._json_path.exists():
            try:
                data = json.loads(self._json_path.read_text(encoding="utf-8"))
                self._entries = [KnowledgeEntry(**entry) for entry in data]
            except (json.JSONDecodeError, OSError, TypeError):
                self._entries = []

        if self._vector_enabled:
            self._vector_index.load(self._vector_path)
            if self._vector_index.size == 0 and self._entries:
                self._rebuild_vector_index()

    def save(self) -> None:
        self._index_path.mkdir(parents=True, exist_ok=True)
        data = [
            {
                "path": e.path,
                "symbol": e.symbol,
                "content": e.content,
                "metadata": e.metadata,
            }
            for e in self._entries
        ]
        self._json_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        if self._vector_enabled:
            self._vector_index.save(self._vector_path)

    def add_entry(self, entry: KnowledgeEntry) -> str:
        self._entries = [
            e for e in self._entries if not (e.path == entry.path and e.symbol == entry.symbol)
        ]
        self._entries.append(entry)

        if self._vector_enabled:
            chunk_id = str(uuid.uuid4())
            embedding = self._embed(entry.content)
            self._vector_index.upsert(
                chunk_id=chunk_id,
                embedding=embedding,
                metadata={
                    "path": entry.path,
                    "symbol": entry.symbol,
                    "content_preview": entry.content[:200],
                },
            )
            return chunk_id
        return ""

    def add_entries(self, entries: list[KnowledgeEntry]) -> list[str]:
        return [self.add_entry(e) for e in entries]

    async def search(
        self,
        query: str,
        limit: int = 5,
        filter_path: str | None = None,
        min_score: float = 0.0,
    ) -> list[ScoredKnowledgeEntry]:
        if self._vector_enabled:
            return self._vector_search(query, limit, filter_path, min_score)
        return self._keyword_search(query, limit)

    async def delete_entry(self, entry_id: str) -> bool:
        return self._vector_index.delete(entry_id)

    async def rebuild_index(self) -> int:
        self._vector_index = VectorIndex(dimension=self._dimension)
        count = 0
        for entry in self._entries:
            if entry.content.strip():
                chunks = self._chunker.chunk(entry.content)
                for chunk in chunks:
                    chunk_id = str(uuid.uuid4())
                    embedding = self._embed(chunk.text)
                    self._vector_index.upsert(
                        chunk_id=chunk_id,
                        embedding=embedding,
                        metadata={
                            "path": entry.path,
                            "symbol": entry.symbol,
                            "start_line": chunk.start_line,
                            "end_line": chunk.end_line,
                        },
                    )
                    count += 1
        return count

    def get_for_file(self, path: str) -> list[KnowledgeEntry]:
        return [e for e in self._entries if e.path == path]

    def _vector_search(
        self,
        query: str,
        limit: int,
        filter_path: str | None,
        min_score: float,
    ) -> list[ScoredKnowledgeEntry]:
        query_embedding = self._embed(query)
        if filter_path:
            results = self._vector_index.search_with_filter(
                query_embedding,
                k=limit * 3,
                filter_fn=lambda m: m.get("path") == filter_path,
            )
        else:
            results = self._vector_index.search(query_embedding, k=limit * 3)

        scored_entries: list[ScoredKnowledgeEntry] = []
        for result in results:
            if result.score < min_score:
                continue
            entry = self._find_entry(result)
            if entry is not None:
                scored_entries.append(ScoredKnowledgeEntry(
                    entry=entry,
                    score=result.score,
                    chunk_range=(
                        result.metadata.get("start_line"),
                        result.metadata.get("end_line"),
                    ) if "start_line" in result.metadata else None,
                ))

        return scored_entries[:limit]

    def _keyword_search(self, query: str, limit: int) -> list[ScoredKnowledgeEntry]:
        query_tokens = query.lower().split()
        scored: list[tuple[float, KnowledgeEntry]] = []
        for entry in self._entries:
            score = 0.0
            content_lower = entry.content.lower()
            symbol_lower = entry.symbol.lower()
            for token in query_tokens:
                if token in content_lower:
                    score += 1.0
                if token in symbol_lower:
                    score += 2.0
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            ScoredKnowledgeEntry(entry=e, score=s)
            for s, e in scored[:limit]
        ]

    def _embed(self, text: str) -> list[float]:
        cached = self._embedding_cache.get(text)
        if cached is not None:
            return cached
        embedding = self._embedder.embed(text)
        self._embedding_cache.set(text, embedding)
        return embedding

    def _find_entry(self, result: SearchResult) -> KnowledgeEntry | None:
        path = result.metadata.get("path", "")
        for entry in self._entries:
            if entry.path == path:
                return entry
        return None

    def _rebuild_vector_index(self) -> None:
        import asyncio
        try:
            asyncio.run(self.rebuild_index())
        except RuntimeError:
            pass
