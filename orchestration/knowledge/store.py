from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class KnowledgeEntry:
    path: str
    symbol: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class KnowledgeStore:
    def __init__(self, index_path: Path) -> None:
        self._index_path = index_path
        self._entries: list[KnowledgeEntry] = []
        self._load()

    def _load(self) -> None:
        if not self._index_path.exists():
            return
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
            self._entries = [KnowledgeEntry(**entry) for entry in data]
        except (json.JSONDecodeError, OSError, TypeError):
            self._entries = []

    def save(self) -> None:
        data = [
            {
                "path": e.path,
                "symbol": e.symbol,
                "content": e.content,
                "metadata": e.metadata,
            }
            for e in self._entries
        ]
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        self._index_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def add_entry(self, entry: KnowledgeEntry) -> None:
        # Avoid duplicates for same path/symbol
        self._entries = [
            e for e in self._entries if not (e.path == entry.path and e.symbol == entry.symbol)
        ]
        self._entries.append(entry)

    def search(self, query: str, limit: int = 5) -> list[KnowledgeEntry]:
        # Basic keyword search for now as a baseline
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
                    score += 2.0  # Symbol match weighted higher
            if score > 0:
                scored.append((score, entry))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [e for _, e in scored[:limit]]

    def get_for_file(self, path: str) -> list[KnowledgeEntry]:
        return [e for e in self._entries if e.path == path]
