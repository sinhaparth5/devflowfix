# Copyright (c) 2025 Parth Sinha and Shine Gupta. All rights reserved.
# DevFlowFix - Autonomous AI agent the detects, analyzes, and resolves CI/CD failures in real-time.

import hashlib
from typing import List, Optional, Dict, Any
import structlog

from app.adapters.ai.nvidia.client import NVIDIAEmbeddingClient
from app.adapters.ai.nvidia.cache import EmbeddingCache, create_cache

logger = structlog.get_logger(__name__)

class EmbeddingAdapter:
    """
    Adapter for text embedding generation.
    
    Provides high-level interface with caching to avoid redundant API calls.
    """
    
    def __init__(
        self,
        model: Optional[str] = None,
        cache: Optional[EmbeddingCache] = None,
        batch_size: int = 32,
    ):
        """
        Initialize embedding adapter.
        
        Args:
            model: Model identifier (defaults to settings)
            cache: Optional cache instance
            batch_size: Maximum batch size for embedding requests
        """
        self.client = NVIDIAEmbeddingClient(model=model)
        self.cache = cache or create_cache()  # Use factory to create proper cache
        self.batch_size = batch_size
        
        logger.info(
            "embedding_adapter_initialized",
            model=self.client.model,
            batch_size=batch_size,
            cache_enabled=self.cache is not None,
        )
    
    async def embed(
        self,
        text: str,
        input_type: str = "query",
        use_cache: bool = True,
        max_length: int = 3000,
    ) -> List[float]:
        """
        Generate embedding for single text.
        
        Args:
            text: Text to embed
            input_type: "query" or "passage"
            use_cache: Whether to use cache
            max_length: Maximum text length before truncation (default 3000 chars)
            
        Returns:
            Embedding vector
        """
        # Truncate text if it exceeds max length to avoid token limit errors
        if len(text) > max_length:
            logger.warning(
                "embedding_text_truncated",
                original_length=len(text),
                truncated_length=max_length,
                input_type=input_type,
            )
            # Keep the most important parts: beginning and end
            # Since error logs often have the root cause at the end
            beginning = text[:max_length // 2]
            end = text[-(max_length // 2):]
            text = f"{beginning}\n...[truncated]...\n{end}"
        
        # Check cache first
        if use_cache and self.cache:
            cache_key = self._get_cache_key(text, input_type)
            cached = await self.cache.get(cache_key)
            
            if cached is not None:
                logger.debug(
                    "embedding_cache_hit",
                    text_length=len(text),
                    input_type=input_type,
                )
                return cached
        
        # Generate embedding
        logger.debug(
            "embedding_generate",
            text_length=len(text),
            input_type=input_type,
        )
        
        try:
            embedding = await self.client.embed_single(text, input_type=input_type)
            
            # Cache result
            if use_cache and self.cache:
                cache_key = self._get_cache_key(text, input_type)
                await self.cache.set(cache_key, embedding)
            
            logger.info(
                "embedding_generate_success",
                text_length=len(text),
                embedding_dim=len(embedding),
            )
            
            return embedding
            
        except Exception as e:
            logger.error(
                "embedding_generate_failed",
                error=str(e),
                text_length=len(text),
                exc_info=True,
            )
            raise
    
    async def embed_batch(
        self,
        texts: List[str],
        input_type: str = "passage",
        use_cache: bool = True,
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.
        
        Automatically handles batching and caching.
        
        Args:
            texts: List of texts to embed
            input_type: "query" or "passage"
            use_cache: Whether to use cache
            
        Returns:
            List of embedding vectors
        """
        if not texts:
            return []
        
        logger.info(
            "embedding_batch_start",
            num_texts=len(texts),
            input_type=input_type,
        )
        
        embeddings = []
        texts_to_embed = []
        text_indices = []
        
        # Check cache for each text
        for i, text in enumerate(texts):
            if use_cache and self.cache:
                cache_key = self._get_cache_key(text, input_type)
                cached = await self.cache.get(cache_key)
                
                if cached is not None:
                    embeddings.append(cached)
                    continue
            
            # Need to embed this text
            texts_to_embed.append(text)
            text_indices.append(i)
            embeddings.append(None)  # Placeholder
        
        cache_hits = len(texts) - len(texts_to_embed)
        logger.info(
            "embedding_batch_cache_check",
            total=len(texts),
            cache_hits=cache_hits,
            cache_misses=len(texts_to_embed),
        )
        
        # Generate embeddings for uncached texts in batches
        if texts_to_embed:
            new_embeddings = await self._embed_in_batches(
                texts_to_embed,
                input_type=input_type,
            )
            
            # Fill in embeddings and cache
            for idx, text, embedding in zip(text_indices, texts_to_embed, new_embeddings):
                embeddings[idx] = embedding
                
                if use_cache and self.cache:
                    cache_key = self._get_cache_key(text, input_type)
                    await self.cache.set(cache_key, embedding)
        
        logger.info(
            "embedding_batch_complete",
            num_texts=len(texts),
            cache_hits=cache_hits,
            generated=len(texts_to_embed),
        )
        
        return embeddings
    
    async def _embed_in_batches(
        self,
        texts: List[str],
        input_type: str = "passage",
    ) -> List[List[float]]:
        """
        Embed texts in batches.
        
        Args:
            texts: List of texts to embed
            input_type: "query" or "passage"
            
        Returns:
            List of embedding vectors
        """
        all_embeddings = []
        
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            
            logger.debug(
                "embedding_batch_request",
                batch_num=i // self.batch_size + 1,
                batch_size=len(batch),
            )
            
            try:
                embeddings = await self.client.embed(batch, input_type=input_type)
                all_embeddings.extend(embeddings)
                
            except Exception as e:
                logger.error(
                    "embedding_batch_failed",
                    batch_num=i // self.batch_size + 1,
                    error=str(e),
                )
                raise
        
        return all_embeddings
    
    def _get_cache_key(self, text: str, input_type: str) -> str:
        """
        Generate cache key for text.
        
        Args:
            text: Text to embed
            input_type: "query" or "passage"
            
        Returns:
            Cache key string
        """
        # Hash text + model + input_type for cache key
        content = f"{self.client.model}:{input_type}:{text}"
        return hashlib.sha256(content.encode()).hexdigest()
    
    async def embed_incident(
        self,
        error_log: str,
        context: Dict[str, Any],
    ) -> List[float]:
        """
        Generate embedding for incident.
        
        Combines error log and context into a single embedding.
        
        Args:
            error_log: Error log or message
            context: Additional context information
            
        Returns:
            Embedding vector
        """
        # Construct incident text
        context_str = " ".join([f"{k}: {v}" for k, v in context.items() if v])
        incident_text = f"{error_log}\n\nContext: {context_str}"
        
        # Truncate if too long (most models have token limits)
        max_chars = 8000
        if len(incident_text) > max_chars:
            incident_text = incident_text[:max_chars] + "..."
            logger.debug(
                "embedding_incident_truncated",
                original_length=len(error_log) + len(context_str),
                truncated_to=max_chars,
            )
        
        return await self.embed(incident_text, input_type="passage")
    
    async def similarity(
        self,
        embedding1: List[float],
        embedding2: List[float],
    ) -> float:
        """
        Calculate cosine similarity between embeddings.
        
        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector
            
        Returns:
            Similarity score (0.0 - 1.0)
        """
        # Cosine similarity
        import math
        
        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
        magnitude1 = math.sqrt(sum(a * a for a in embedding1))
        magnitude2 = math.sqrt(sum(b * b for b in embedding2))
        
        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0
        
        similarity = dot_product / (magnitude1 * magnitude2)
        
        # Normalize to [0, 1] (cosine similarity is [-1, 1])
        return (similarity + 1) / 2
    
    async def clear_cache(self):
        """Clear embedding cache."""
        if self.cache:
            await self.cache.clear()
            logger.info("embedding_cache_cleared")
    
    async def close(self):
        """Close the embedding client."""
        await self.client.close()
        if self.cache:
            await self.cache.close()
    
    async def __aenter__(self):
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()