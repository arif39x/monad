from __future__ import annotations

import asyncio

from orchestration.cache import PrefixCacheManager


def test_cache_hit_miss() -> None:
    async def run():
        cache = PrefixCacheManager(enabled=True)
        result = await cache.lookup("session-1", "prefix-text")
        assert result is None
        entry = await cache.store("session-1", "prefix-text")
        assert entry is not None
        result = await cache.lookup("session-1", "prefix-text")
        assert result is not None

    asyncio.run(run())


def test_cache_key_isolation() -> None:
    async def run():
        cache = PrefixCacheManager(enabled=True)
        await cache.store("session-1", "same-prefix")
        await cache.store("session-2", "same-prefix")
        result1 = await cache.lookup("session-1", "same-prefix")
        result2 = await cache.lookup("session-2", "same-prefix")
        assert result1 is not None
        assert result2 is not None

    asyncio.run(run())


def test_cache_ttl() -> None:
    async def run():
        cache = PrefixCacheManager(enabled=True, ttl_seconds=0)
        await cache.store("session-1", "expired-prefix")
        result = await cache.lookup("session-1", "expired-prefix")
        assert result is None

    asyncio.run(run())


def test_cache_eviction() -> None:
    async def run():
        cache = PrefixCacheManager(enabled=True, max_entries=3)
        for i in range(5):
            await cache.store("session-1", f"prefix-{i}")
        assert cache.stats["num_entries"] <= 3

    asyncio.run(run())


def test_disabled_cache() -> None:
    async def run():
        cache = PrefixCacheManager(enabled=False)
        await cache.store("session-1", "prefix")
        result = await cache.lookup("session-1", "prefix")
        assert result is None

    asyncio.run(run())


def test_cache_invalidation() -> None:
    async def run():
        cache = PrefixCacheManager(enabled=True)
        await cache.store("session-1", "prefix")
        result = await cache.lookup("session-1", "prefix")
        assert result is not None
        await cache.invalidate("session-1", "prefix")
        result = await cache.lookup("session-1", "prefix")
        assert result is None

    asyncio.run(run())


def test_cache_clear() -> None:
    async def run():
        cache = PrefixCacheManager(enabled=True)
        await cache.store("session-1", "prefix-1")
        await cache.store("session-1", "prefix-2")
        assert cache.stats["num_entries"] == 2
        await cache.clear()
        assert cache.stats["num_entries"] == 0

    asyncio.run(run())


def test_hash_consistency() -> None:
    cache = PrefixCacheManager(enabled=True)
    h1 = cache._compute_hash("session", "prefix")
    h2 = cache._compute_hash("session", "prefix")
    assert h1 == h2
    h3 = cache._compute_hash("session", "different")
    assert h1 != h3


def test_extract_prefix() -> None:
    cache = PrefixCacheManager(enabled=True)
    prefix = cache.extract_prefix("system prompt\ncontext\nuser: hello", "user: hello")
    assert prefix == "system prompt\ncontext\n"
    full = cache.extract_prefix("just text")
    assert full == "just text"
