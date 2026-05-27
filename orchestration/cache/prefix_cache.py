from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CacheEntry:
    prefix_hash: str
    prefix_text: str
    created_at: float
    ttl_seconds: float
    access_count: int = 0
    provider_cache_id: str | None = None


@dataclass
class ProviderCacheInfo:
    supports_context_caching: bool
    provider_name: str


class PrefixCacheManager:
    def __init__(
        self,
        *,
        enabled: bool = True,
        ttl_seconds: float = 300.0,
        max_entries: int = 500,
        cache_dir: str | None = None,
    ) -> None:
        self._enabled = enabled
        self._ttl_seconds = ttl_seconds
        self._max_entries = max_entries
        self._lock = asyncio.Lock()
        self._entries: dict[str, CacheEntry] = {}
        self._cache_dir = Path(cache_dir) if cache_dir else None

    def _compute_hash(self, session_id: str, prefix: str) -> str:
        raw = f"{session_id}:::{prefix}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def lookup(self, session_id: str, prefix: str) -> CacheEntry | None:
        if not self._enabled:
            return None
        prefix_hash = self._compute_hash(session_id, prefix)
        async with self._lock:
            entry = self._entries.get(prefix_hash)
            if entry is None:
                return None
            if time.time() - entry.created_at > entry.ttl_seconds:
                del self._entries[prefix_hash]
                return None
            entry.access_count += 1
            return entry

    async def store(
        self,
        session_id: str,
        prefix: str,
        *,
        ttl_seconds: float | None = None,
    ) -> CacheEntry:
        prefix_hash = self._compute_hash(session_id, prefix)
        entry = CacheEntry(
            prefix_hash=prefix_hash,
            prefix_text=prefix,
            created_at=time.time(),
            ttl_seconds=ttl_seconds or self._ttl_seconds,
        )
        async with self._lock:
            self._entries[prefix_hash] = entry
            if len(self._entries) > self._max_entries:
                self._evict_lru()
            self._persist()
        return entry

    async def invalidate(self, session_id: str, prefix: str) -> None:
        prefix_hash = self._compute_hash(session_id, prefix)
        async with self._lock:
            self._entries.pop(prefix_hash, None)

    async def clear(self) -> None:
        async with self._lock:
            self._entries.clear()

    def _evict_lru(self) -> None:
        if not self._entries:
            return
        sorted_entries = sorted(
            self._entries.values(),
            key=lambda e: e.access_count,
        )
        target = len(self._entries) - int(self._max_entries * 0.8)
        for entry in sorted_entries[:target]:
            self._entries.pop(entry.prefix_hash, None)

    def _persist(self) -> None:
        if self._cache_dir is None:
            return
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = self._cache_dir / "prefix_cache.json"
        data = {
            h: {
                "prefix_hash": e.prefix_hash,
                "prefix_text": e.prefix_text[:200],
                "created_at": e.created_at,
                "ttl_seconds": e.ttl_seconds,
                "access_count": e.access_count,
                "provider_cache_id": e.provider_cache_id,
            }
            for h, e in self._entries.items()
        }
        try:
            cache_file.write_text(json.dumps(data, indent=2))
        except OSError:
            pass

    def _load_from_disk(self) -> None:
        if self._cache_dir is None:
            return
        cache_file = self._cache_dir / "prefix_cache.json"
        if not cache_file.exists():
            return
        try:
            data = json.loads(cache_file.read_text())
            for h, d in data.items():
                self._entries[h] = CacheEntry(**d)
        except (json.JSONDecodeError, OSError):
            pass

    @property
    def stats(self) -> dict:
        return {
            "num_entries": len(self._entries),
            "max_entries": self._max_entries,
            "ttl_seconds": self._ttl_seconds,
            "enabled": self._enabled,
        }

    def is_cacheable_prefix(
        self,
        prefix: str,
        provider_info: ProviderCacheInfo | None = None,
    ) -> bool:
        return len(prefix) > 50

    def extract_prefix(self, prompt: str, user_message: str | None = None) -> str:
        if user_message and user_message in prompt:
            idx = prompt.rfind(user_message)
            return prompt[:idx]
        return prompt


_PROVIDER_CACHE_REGISTRY: dict[str, ProviderCacheInfo] = {}


def register_provider_cache(provider_name: str, supports: bool) -> None:
    _PROVIDER_CACHE_REGISTRY[provider_name] = ProviderCacheInfo(
        supports_context_caching=supports,
        provider_name=provider_name,
    )


def get_provider_cache_info(provider_name: str) -> ProviderCacheInfo | None:
    return _PROVIDER_CACHE_REGISTRY.get(provider_name)
