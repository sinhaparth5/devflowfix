# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import pickle
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)

class EmbeddingCache:
    """
    Base cache interface for embeddings.
    
    Provides get/set/clear operations.
    """
    
    async def get(self, key: str) -> Optional[List[float]]:
        """
        Get embedding from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Embedding vector or None if not found
        """
        raise NotImplementedError
    
    async def set(
        self,
        key: str,
        embedding: List[float],
        ttl: Optional[int] = None,
    ) -> None:
        """
        Store embedding in cache.
        
        Args:
            key: Cache key
            embedding: Embedding vector
            ttl: Time-to-live in seconds (None for no expiry)
        """
        raise NotImplementedError
    
    async def clear(self) -> None:
        """Clear all cached embeddings."""
        raise NotImplementedError
    
    async def close(self) -> None:
        """Close cache connections."""
        pass


class MemoryEmbeddingCache(EmbeddingCache):
    """
    In-memory cache for embeddings.
    
    Fast but doesn't persist across restarts.
    Suitable for development and small-scale deployments.
    """
    
    def __init__(self, max_size: int = 10000):
        """
        Initialize memory cache.
        
        Args:
            max_size: Maximum number of entries to cache
        """
        self.cache: Dict[str, tuple[List[float], Optional[datetime]]] = {}
        self.max_size = max_size
        
        logger.info("memory_cache_initialized", max_size=max_size)
    
    async def get(self, key: str) -> Optional[List[float]]:
        """Get embedding from memory cache."""
        if key not in self.cache:
            return None
        
        embedding, expires_at = self.cache[key]
        
        # Check expiry
        if expires_at and datetime.utcnow() > expires_at:
            del self.cache[key]
            return None
        
        return embedding
    
    async def set(
        self,
        key: str,
        embedding: List[float],
        ttl: Optional[int] = None,
    ) -> None:
        """Store embedding in memory cache."""
        # Evict oldest entry if cache is full
        if len(self.cache) >= self.max_size:
            # Simple FIFO eviction (could use LRU for better performance)
            oldest_key = next(iter(self.cache))
            del self.cache[oldest_key]
            logger.debug("memory_cache_evicted", key=oldest_key)
        
        expires_at = None
        if ttl:
            expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        
        self.cache[key] = (embedding, expires_at)
    
    async def clear(self) -> None:
        """Clear memory cache."""
        self.cache.clear()
        logger.info("memory_cache_cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            "size": len(self.cache),
            "max_size": self.max_size,
            "utilization": len(self.cache) / self.max_size if self.max_size > 0 else 0,
        }

class RedisEmbeddingCache(EmbeddingCache):
    """
    Redis-based cache for embeddings.
    
    Persistent and shared across instances.
    Suitable for production deployments.
    """
    
    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_prefix: str = "embedding:",
        default_ttl: int = 86400,  # 24 hours
    ):
        """
        Initialize Redis cache.
        
        Args:
            redis_url: Redis connection URL (defaults to settings)
            key_prefix: Prefix for cache keys
            default_ttl: Default time-to-live in seconds
        """
        self.redis_url = redis_url or settings.redis_url
        self.key_prefix = key_prefix
        self.default_ttl = default_ttl
        self.redis_client = None
        
        if not self.redis_url:
            raise ValueError("Redis URL is required for Redis cache")
        
        # Import redis here to make it optional dependency
        try:
            import redis.asyncio as redis
            self.redis = redis
        except ImportError:
            raise ImportError(
                "redis package is required for Redis cache. "
                "Install with: pip install redis"
            )
        
        logger.info(
            "redis_cache_initialized",
            redis_url=self.redis_url.split("@")[-1],  # Hide credentials
            key_prefix=key_prefix,
            default_ttl=default_ttl,
        )
    
    async def _get_client(self):
        """Get or create Redis client."""
        if self.redis_client is None:
            self.redis_client = self.redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=False,  # We need bytes for pickle
            )
        return self.redis_client
    
    async def get(self, key: str) -> Optional[List[float]]:
        """Get embedding from Redis cache."""
        try:
            client = await self._get_client()
            cache_key = f"{self.key_prefix}{key}"
            
            data = await client.get(cache_key)
            if data is None:
                return None
            
            # Deserialize embedding
            embedding = pickle.loads(data)
            return embedding
            
        except Exception as e:
            logger.error("redis_cache_get_failed", key=key, error=str(e))
            return None
    
    async def set(
        self,
        key: str,
        embedding: List[float],
        ttl: Optional[int] = None,
    ) -> None:
        """Store embedding in Redis cache."""
        try:
            client = await self._get_client()
            cache_key = f"{self.key_prefix}{key}"
            
            # Serialize embedding
            data = pickle.dumps(embedding)
            
            # Set with TTL
            ttl = ttl or self.default_ttl
            await client.setex(cache_key, ttl, data)
            
        except Exception as e:
            logger.error("redis_cache_set_failed", key=key, error=str(e))
    
    async def clear(self) -> None:
        """Clear Redis cache (all keys with prefix)."""
        try:
            client = await self._get_client()
            
            # Get all keys with prefix
            pattern = f"{self.key_prefix}*"
            keys = []
            async for key in client.scan_iter(match=pattern):
                keys.append(key)
            
            # Delete keys
            if keys:
                await client.delete(*keys)
                logger.info("redis_cache_cleared", num_keys=len(keys))
            
        except Exception as e:
            logger.error("redis_cache_clear_failed", error=str(e))
    
    async def close(self) -> None:
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()
            logger.debug("redis_cache_closed")


def create_cache(cache_type: Optional[str] = None) -> EmbeddingCache:
    """
    Factory function to create appropriate cache.
    
    Args:
        cache_type: "memory" or "redis" (auto-detect if None)
        
    Returns:
        Cache instance
    """
    if cache_type is None:
        # Auto-detect based on settings
        if settings.redis_url:
            cache_type = "redis"
        else:
            cache_type = "memory"
    
    if cache_type == "redis":
        try:
            return RedisEmbeddingCache()
        except (ImportError, ValueError) as e:
            logger.warning(
                "redis_cache_unavailable",
                error=str(e),
                fallback="memory",
            )
            return MemoryEmbeddingCache()
    else:
        return MemoryEmbeddingCache()