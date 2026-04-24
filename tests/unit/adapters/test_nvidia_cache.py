# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

from datetime import datetime, timedelta, timezone

import pytest

from app.adapters.ai.nvidia.cache import MemoryEmbeddingCache, create_cache


@pytest.mark.asyncio
async def test_memory_embedding_cache_round_trip() -> None:
    cache = MemoryEmbeddingCache(max_size=4)
    embedding = [0.1, 0.2, 0.3]

    await cache.set("incident-1", embedding, ttl=60)

    assert await cache.get("incident-1") == embedding


@pytest.mark.asyncio
async def test_memory_embedding_cache_expires_entries() -> None:
    cache = MemoryEmbeddingCache(max_size=2)
    cache.cache["expired"] = ([1.0], datetime.now(timezone.utc) - timedelta(seconds=1))

    assert await cache.get("expired") is None
    assert "expired" not in cache.cache


@pytest.mark.asyncio
async def test_memory_embedding_cache_evicts_oldest_entry() -> None:
    cache = MemoryEmbeddingCache(max_size=2)

    await cache.set("first", [1.0])
    await cache.set("second", [2.0])
    await cache.set("third", [3.0])

    assert await cache.get("first") is None
    assert await cache.get("second") == [2.0]
    assert await cache.get("third") == [3.0]


def test_create_cache_falls_back_to_memory_when_redis_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    class BrokenRedisCache:
        def __init__(self) -> None:
            raise ValueError("redis unavailable")

    monkeypatch.setattr("app.adapters.ai.nvidia.cache.RedisEmbeddingCache", BrokenRedisCache)

    cache = create_cache("redis")

    assert isinstance(cache, MemoryEmbeddingCache)
