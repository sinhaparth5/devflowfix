# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent that detects, analyzes, and resolves CI/CD failures in real-time.

import json
from typing import Optional, Any, List
import structlog
import redis.asyncio as redis
from redis.asyncio import Redis
from redis.exceptions import RedisError, ConnectionError, TimeoutError

from app.core.config import settings

logger = structlog.get_logger(__name__)


class RedisCache:
    """
    Redis cache adapter for caching incident data, LLM responses, and RAG results.

    Features:
    - Async/await support
    - Connection pooling
    - Automatic serialization/deserialization
    - TTL support
    - Error handling with fallback
    """

    def __init__(
        self,
        url: Optional[str] = None,
        password: Optional[str] = None,
        max_connections: Optional[int] = None,
        socket_timeout: Optional[int] = None,
        decode_responses: bool = True,
    ):
        """
        Initialize Redis cache client.

        Args:
            url: Redis connection URL (redis://host:port/db)
            password: Redis password (optional)
            max_connections: Maximum connection pool size
            socket_timeout: Socket timeout in seconds
            decode_responses: Decode responses to strings
        """
        self.url = url or settings.redis_url or settings.redis.url
        self.password = password or settings.redis.password
        self.max_connections = max_connections or settings.redis_max_connections
        self.socket_timeout = socket_timeout or settings.redis_socket_timeout
        self.decode_responses = decode_responses

        self.client: Optional[Redis] = None
        self._connection_pool: Optional[redis.ConnectionPool] = None

        logger.info(
            "redis_cache_initialized",
            url=self._mask_password(self.url),
            max_connections=self.max_connections,
            socket_timeout=self.socket_timeout,
        )

    def _mask_password(self, url: str) -> str:
        """Mask password in URL for logging."""
        if "@" in url and ":" in url:
            parts = url.split("@")
            creds = parts[0].split("://")
            if len(creds) > 1 and ":" in creds[1]:
                user = creds[1].split(":")[0]
                return f"{creds[0]}://{user}:***@{parts[1]}"
        return url

    async def connect(self) -> None:
        """Establish connection to Redis."""
        if self.client:
            logger.debug("redis_already_connected")
            return

        try:
            # Create connection pool
            self._connection_pool = redis.ConnectionPool.from_url(
                self.url,
                password=self.password,
                max_connections=self.max_connections,
                socket_timeout=self.socket_timeout,
                decode_responses=self.decode_responses,
            )

            # Create Redis client
            self.client = Redis(connection_pool=self._connection_pool)

            # Test connection
            await self.client.ping()

            logger.info("redis_connected", url=self._mask_password(self.url))

        except ConnectionError as e:
            logger.error("redis_connection_failed", error=str(e), url=self._mask_password(self.url))
            raise
        except Exception as e:
            logger.error("redis_initialization_failed", error=str(e))
            raise

    async def close(self) -> None:
        """Close Redis connection."""
        if self.client:
            await self.client.close()
            await self._connection_pool.disconnect()
            self.client = None
            self._connection_pool = None
            logger.info("redis_connection_closed")

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found
        """
        if not self.client:
            await self.connect()

        try:
            value = await self.client.get(key)

            if value is None:
                logger.debug("redis_cache_miss", key=key)
                return None

            # Try to deserialize JSON
            try:
                deserialized = json.loads(value)
                logger.debug("redis_cache_hit", key=key, type="json")
                return deserialized
            except (json.JSONDecodeError, TypeError):
                # Return as-is if not JSON
                logger.debug("redis_cache_hit", key=key, type="string")
                return value

        except (RedisError, TimeoutError) as e:
            logger.warning("redis_get_failed", key=key, error=str(e))
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized if dict/list)
            ttl: Time-to-live in seconds (defaults to settings.redis.ttl)

        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            await self.connect()

        try:
            # Serialize to JSON if dict/list
            if isinstance(value, (dict, list)):
                serialized = json.dumps(value)
            else:
                serialized = str(value)

            ttl = ttl or settings.redis.ttl

            await self.client.setex(key, ttl, serialized)

            logger.debug("redis_cache_set", key=key, ttl=ttl)
            return True

        except (RedisError, TimeoutError) as e:
            logger.warning("redis_set_failed", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete key from cache.

        Args:
            key: Cache key

        Returns:
            True if key was deleted, False otherwise
        """
        if not self.client:
            await self.connect()

        try:
            result = await self.client.delete(key)
            logger.debug("redis_cache_delete", key=key, deleted=bool(result))
            return bool(result)

        except (RedisError, TimeoutError) as e:
            logger.warning("redis_delete_failed", key=key, error=str(e))
            return False

    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache.

        Args:
            key: Cache key

        Returns:
            True if key exists, False otherwise
        """
        if not self.client:
            await self.connect()

        try:
            result = await self.client.exists(key)
            return bool(result)

        except (RedisError, TimeoutError) as e:
            logger.warning("redis_exists_failed", key=key, error=str(e))
            return False

    async def get_many(self, keys: List[str]) -> List[Optional[Any]]:
        """
        Get multiple values from cache.

        Args:
            keys: List of cache keys

        Returns:
            List of values (None for missing keys)
        """
        if not self.client:
            await self.connect()

        try:
            values = await self.client.mget(keys)

            results = []
            for value in values:
                if value is None:
                    results.append(None)
                else:
                    try:
                        results.append(json.loads(value))
                    except (json.JSONDecodeError, TypeError):
                        results.append(value)

            logger.debug("redis_cache_get_many", keys_count=len(keys), hits=sum(1 for v in results if v is not None))
            return results

        except (RedisError, TimeoutError) as e:
            logger.warning("redis_get_many_failed", keys_count=len(keys), error=str(e))
            return [None] * len(keys)

    async def set_many(
        self,
        mapping: dict[str, Any],
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set multiple values in cache.

        Args:
            mapping: Dictionary of key-value pairs
            ttl: Time-to-live in seconds

        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            await self.connect()

        try:
            # Serialize values
            serialized = {}
            for key, value in mapping.items():
                if isinstance(value, (dict, list)):
                    serialized[key] = json.dumps(value)
                else:
                    serialized[key] = str(value)

            # Set all values
            await self.client.mset(serialized)

            # Set TTL for each key if specified
            if ttl:
                ttl = ttl or settings.redis.ttl
                for key in serialized.keys():
                    await self.client.expire(key, ttl)

            logger.debug("redis_cache_set_many", keys_count=len(mapping), ttl=ttl)
            return True

        except (RedisError, TimeoutError) as e:
            logger.warning("redis_set_many_failed", keys_count=len(mapping), error=str(e))
            return False

    async def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Increment a counter.

        Args:
            key: Cache key
            amount: Amount to increment by

        Returns:
            New value after increment, or None on error
        """
        if not self.client:
            await self.connect()

        try:
            result = await self.client.incrby(key, amount)
            logger.debug("redis_increment", key=key, amount=amount, new_value=result)
            return result

        except (RedisError, TimeoutError) as e:
            logger.warning("redis_increment_failed", key=key, error=str(e))
            return None

    async def decrement(self, key: str, amount: int = 1) -> Optional[int]:
        """
        Decrement a counter.

        Args:
            key: Cache key
            amount: Amount to decrement by

        Returns:
            New value after decrement, or None on error
        """
        if not self.client:
            await self.connect()

        try:
            result = await self.client.decrby(key, amount)
            logger.debug("redis_decrement", key=key, amount=amount, new_value=result)
            return result

        except (RedisError, TimeoutError) as e:
            logger.warning("redis_decrement_failed", key=key, error=str(e))
            return None

    async def flush_all(self) -> bool:
        """
        Flush all keys from cache.

        WARNING: This deletes ALL data in the Redis database!

        Returns:
            True if successful, False otherwise
        """
        if not self.client:
            await self.connect()

        try:
            await self.client.flushdb()
            logger.warning("redis_flushed_all_keys")
            return True

        except (RedisError, TimeoutError) as e:
            logger.error("redis_flush_failed", error=str(e))
            return False

    async def get_ttl(self, key: str) -> Optional[int]:
        """
        Get remaining TTL for a key.

        Args:
            key: Cache key

        Returns:
            TTL in seconds, -1 if no expiry, -2 if key doesn't exist, None on error
        """
        if not self.client:
            await self.connect()

        try:
            ttl = await self.client.ttl(key)
            return ttl

        except (RedisError, TimeoutError) as e:
            logger.warning("redis_get_ttl_failed", key=key, error=str(e))
            return None

    async def __aenter__(self):
        """Async context manager entry."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Global Redis cache instance
_redis_cache: Optional[RedisCache] = None


def get_redis_cache() -> RedisCache:
    """
    Get global Redis cache instance.

    Returns:
        RedisCache instance
    """
    global _redis_cache

    if _redis_cache is None:
        _redis_cache = RedisCache()

    return _redis_cache


async def init_redis_cache() -> RedisCache:
    """
    Initialize and connect to Redis cache.

    Returns:
        Connected RedisCache instance
    """
    cache = get_redis_cache()
    await cache.connect()
    return cache


async def close_redis_cache() -> None:
    """Close Redis cache connection."""
    global _redis_cache

    if _redis_cache:
        await _redis_cache.close()
        _redis_cache = None
